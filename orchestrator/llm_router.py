"""
XOYO Omega — Intelligent Multi-Provider LLM Router
Zero-failure routing across 8 providers with task-aware model selection.
Cloud APIs are PRIMARY. Ollama is OPTIONAL (user can enable when needed).
"""
import requests, time, random, logging, re, hashlib, json, os, threading
from collections import OrderedDict
from dotenv import load_dotenv

# Load environment variables from project-root .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

log = logging.getLogger("xoyo.router")

import time
import threading

class OpenRouterKeyManager:
    def __init__(self, api_keys_str):
        if not api_keys_str:
            api_keys_str = os.environ.get('OPENROUTER_API_KEY', '')
        self.keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
        if not self.keys:
            self.keys = [""]
        self.available_at = {key: 0.0 for key in self.keys}
        self.lock = threading.Lock()

    async def aget_key(self):
        import asyncio
        while True:
            with self.lock:
                now = time.time()
                best_key = min(self.keys, key=lambda k: self.available_at[k])
                wait_time = self.available_at[best_key] - now
            if wait_time > 0:
                log.warning(f"[KeyManager] All OpenRouter keys rate-limited. Sleeping {wait_time:.2f}s...")
                raise Exception(f"Rate limited, wait {wait_time}s")
            else:
                return best_key

    def mark_rate_limited(self, key, retry_after):
        with self.lock:
            self.available_at[key] = time.time() + retry_after
            log.warning(f"[KeyManager] OpenRouter Key ...{key[-4:]} rate limited. Unlocked in {retry_after:.2f}s.")

openrouter_key_manager = OpenRouterKeyManager(os.environ.get("OPENROUTER_API_KEYS", ""))


# Pre-compiled regex for stripping <think> tags (avoid re-compiling every call)
_THINK_RE = re.compile(r'<think>.*?(?:</think>|$)', re.DOTALL | re.IGNORECASE)

# ── Ollama Toggle (OFF by default — saves RAM) ────────────────
_ollama_enabled = True

def enable_ollama():
    """Enable Ollama as a fallback provider."""
    global _ollama_enabled
    _ollama_enabled = True
    log.info("Ollama LOCAL enabled as fallback provider")

def disable_ollama():
    """Disable Ollama — cloud-only mode."""
    global _ollama_enabled
    _ollama_enabled = False
    log.info("Ollama LOCAL disabled — cloud-only mode")

def is_ollama_enabled():
    return _ollama_enabled

# ── LLM Response Cache (LRU, max 64 entries) ─────────────────
_LLM_CACHE = OrderedDict()
_LLM_CACHE_MAX = 64
_LLM_CACHE_LOCK = threading.Lock()

# ── Semantic Cache (Embeddings) ──────────────────────────────
# DISABLED per user request to save RAM (no sentence-transformers)
def _semantic_search(query: str, threshold: float = 0.95):
    return None

def _semantic_add(query: str, response: str):
    pass

def _cache_key(messages, max_tokens, temperature, task_type):
    """Cache key from system prompt + last 2 messages for better hit/miss accuracy."""
    parts = []
    
    def extract_text(content):
        if isinstance(content, list):
            return " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
        return str(content)
        
    # Include system prompt if present
    if messages and messages[0].get("role") == "system":
        parts.append(extract_text(messages[0].get("content", "")))
    # Include last 2 messages
    for msg in messages[-2:]:
        parts.append(extract_text(msg.get("content", "")))
    content = "|".join(parts)
    return hashlib.md5(f"{content}|{max_tokens}|{temperature}|{task_type}".encode()).hexdigest()

def _cache_get(key):
    with _LLM_CACHE_LOCK:
        val = _LLM_CACHE.get(key)
        if val:
            _LLM_CACHE.move_to_end(key)
        return val

def _cache_put(key, val):
    with _LLM_CACHE_LOCK:
        _LLM_CACHE[key] = val
        if len(_LLM_CACHE) > _LLM_CACHE_MAX:
            _LLM_CACHE.popitem(last=False)


# ── Context Truncation (Performance & OOM Prevention) ──────────
_MAX_CHARS_PER_MSG = 32000

def _extract_skeleton(text: str) -> str:
    lines = text.split('\n')
    skeleton = []
    in_docstring = False
    for line in lines:
        stripped = line.strip()
        if '"""' in stripped or "'''" in stripped:
            skeleton.append(line)
            if stripped.count('"""') % 2 != 0 or stripped.count("'''") % 2 != 0:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
            
        # keep imports, definitions, classes, comments
        if stripped.startswith(('def ', 'class ', 'import ', 'from ', 'async def ', '#', '//', 'function ', 'export ', 'interface ', 'type ')):
            skeleton.append(line)
        elif len(line) - len(line.lstrip()) == 0 and stripped != "":
            # Keep top-level code
            skeleton.append(line)
        elif stripped in ("{", "}"):
            skeleton.append(line)
            
    return "\n".join(skeleton)

def _truncate_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    if len(text) <= _MAX_CHARS_PER_MSG:
        return text
        
    # Attempt structural compression (Skeleton Extraction)
    if 'def ' in text or 'class ' in text or 'function ' in text:
        skeleton = _extract_skeleton(text)
        if len(skeleton) < len(text) * 0.8:
            if len(skeleton) <= _MAX_CHARS_PER_MSG:
                return f"// [AST STRUCTURAL COMPRESSION APPLIED - FUNCTION BODIES OMITTED]\n{skeleton}"
            else:
                text = skeleton # Still too big, but we truncated it a lot, now do standard truncation on skeleton
        
    half = _MAX_CHARS_PER_MSG // 2
    return text[:half] + f"\n\n... [TRUNCATED {len(text) - _MAX_CHARS_PER_MSG} CHARACTERS] ...\n\n" + text[-half:]

def _truncate_messages(messages: list) -> list:
    import copy
    new_messages = []
    
    def _truncate_content_list(content_list, seen=None):
        if seen is None:
            seen = set()
            
        obj_id = id(content_list)
        if obj_id in seen:
            return []
        seen.add(obj_id)
        
        new_content = []
        for item in content_list:
            if isinstance(item, dict):
                new_item = copy.copy(item)
                if new_item.get("type") == "text" and "text" in new_item:
                    new_item["text"] = _truncate_text(new_item["text"])
                new_content.append(new_item)
            elif isinstance(item, list):
                new_content.append(_truncate_content_list(item, seen))
            else:
                new_content.append(item)
                
        seen.remove(obj_id)
        return new_content

    for msg in messages:
        new_msg = copy.copy(msg)
        content = new_msg.get("content")
        if isinstance(content, str):
            new_msg["content"] = _truncate_text(content)
        elif isinstance(content, list):
            new_msg["content"] = _truncate_content_list(content)
        new_messages.append(new_msg)
    return new_messages

# ═══════════════════════════════════════════════════════════
# PROVIDER CONFIGURATIONS (keys loaded from environment)
# ═══════════════════════════════════════════════════════════
PROVIDERS = {

    # ── NEW FRONTIER MODELS ──
    "google_gemini3_5": {
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={os.environ.get('GEMINI_API_KEY', '')}",
        "headers": {"Content-Type": "application/json"},
        "model": "gemini-3.5-flash",
        "timeout": 120,
    },
    "agnes_flash": {
        "url": "https://apihub.agnes-ai.com/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('AGNES_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "agnes-2.0-flash",
        "timeout": 120,
    },
    "groq_llama4maverick": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('GROQ_MAVERICK_API_KEY', os.environ.get('GROQ_API_KEY', ''))}",
            "Content-Type": "application/json",
        },
        "model": "llama-3.3-70b-versatile",
        "timeout": 60,
    },
    "openrouter_deepseekv4": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "deepseek/deepseek-chat",
        "timeout": 20,
    },
    "openrouter_owlalpha": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "google/gemini-pro-vision",
        "timeout": 20,
    },
    "openrouter_nemotron_ultra": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "nvidia/nemotron-4-340b-instruct",
        "timeout": 20,
    },
    "openrouter_trinity": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "liquid/lfm-40b",
        "timeout": 20,
    },
    "openrouter_gptoss": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "openai/gpt-4o-mini",
        "timeout": 20,
    },
    "openrouter_gemma4": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "google/gemma-2-9b-it",
        "timeout": 20,
    },
    "openrouter_gpt4o": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "openai/gpt-4o",
        "timeout": 20,
    },
    "openrouter_claude35": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
        "model": "anthropic/claude-3.5-sonnet",
        "timeout": 180,
    },

    # ── Ollama LOCAL (i3 laptop, 8GB RAM, CPU-only: 3-6 tok/s) ──
    # ONLY suitable for ultra-short completions (<50 tokens)
    # Will OOM on contexts >4096 tokens. Timeout kept short.
    "ollama_local": {
        "url": "http://localhost:11434/v1/chat/completions",
        "headers": {"Content-Type": "application/json"},
        "model": "qwen2.5-coder:7b",
        "timeout": 12,  # SPEED: Reduced from 30s for faster failover to cloud
    },

    # ── Groq (free LPU inference, ultra-fast) ──
    "groq_qwen32b": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "qwen/qwen3-32b",
        "timeout": 90,
    },
    "groq_llama4scout": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "llama-3.1-8b-instant",
        "timeout": 60,
    },
    "groq_llama8b": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "llama-3.1-8b-instant",
        "timeout": 30,
    },

    # ── Cerebras (free, 1M tokens/day, 235B MoE) ──
    # ⚠️ DEPRECATED May 27, 2026 — will stop working after that date.
    # Keep as fallback only. Primary science/reasoning should use NVIDIA or Mistral.
    "cerebras_qwen235b": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('CEREBRAS_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "llama3.1-8b",
        "timeout": 180,
    },

    # ── Mistral (1 BILLION tokens/month, ultimate safety net) ──
    "mistral_large": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('MISTRAL_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "mistral-large-latest",
        "timeout": 180,
    },
    "mistral_small": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('MISTRAL_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "mistral-small-latest",
        "timeout": 120,
    },

    # ── NVIDIA NIM (40 RPM, 136 models, free) ──
    "nvidia_qwen3coder": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('NVIDIA_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "qwen/qwen3-coder-480b-a35b-instruct",
        "timeout": 180,
    },
    "nvidia_nemotron": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('NVIDIA_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "timeout": 120,
    },
    "nvidia_llama405b": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('NVIDIA_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "meta/llama-3.1-405b-instruct",
        "timeout": 180,
    },

    # ── OpenRouter (50 req/day free, access to many models) ──
    "openrouter_auto": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "qwen/qwen3-235b-a22b:free",
        "timeout": 180,
    },

    # ── Cloudflare Workers AI ──
    "cloudflare_qwen32b": {
        "url": "https://api.cloudflare.com/client/v4/accounts/default/ai/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('CLOUDFLARE_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "@cf/qwen/qwen2.5-coder-32b-instruct",
        "timeout": 120,
    },

    # ── SiliconFlow (20M tokens bonus) ──
    "siliconflow_qwen32b": {
        "url": "https://api.siliconflow.cn/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('SILICONFLOW_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "timeout": 120,
    },

    # ── LLM7.io ──
    "llm7_qwen32b": {
        "url": "https://api.llm7.io/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('LLM7_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        "model": "qwen2.5-coder-32b",
        "timeout": 120,
    },
}

# ═══════════════════════════════════════════════════════════
# TASK-TYPE → PROVIDER PRIORITY
# Strategy: Cloud-first for real work, Ollama only as offline fallback.
# Ollama 7B on i3/8GB is too slow (3-6 tok/s, OOMs on long context).
# Groq = fastest (LPU), NVIDIA = best quality, Mistral = safety net.
# ═══════════════════════════════════════════════════════════
# Pools that CAN use Ollama as a last-resort fallback (when enabled)
_OLLAMA_ELIGIBLE_POOLS = {"micro", "simple", "code", "reasoning", "vision", "desktop", "system"}

PROVIDER_POOL = {
    # Ultra-short completions: low latency, fast TTFT
    "micro": [
        "groq_llama8b",
        "groq_llama4maverick",
        "openrouter_gemma4",
        "google_gemini3_5",
        "openrouter_deepseekv4",
        "mistral_small",
    ],
    # Simple tasks: file ops, memory, web search summaries
    "simple": [
        "groq_llama4maverick",
        "google_gemini3_5",
        "groq_llama8b",
        "openrouter_gemma4",
        "groq_qwen32b",
    ],
    # Code generation: max quality and context
    "code": [
        "openrouter_claude35",
        "openrouter_gpt4o",
        "openrouter_deepseekv4",
        "google_gemini3_5",
        "openrouter_gptoss",
        "openrouter_trinity",
        "nvidia_qwen3coder",
        "mistral_large",
    ],
    "reasoning": [
        "openrouter_deepseekv4",
        "openrouter_gpt4o",
        "openrouter_claude35",
        "groq_llama4maverick",
        "openrouter_nemotron_ultra",
        "openrouter_trinity",
        "mistral_large",
        "nvidia_llama405b",
        "groq_llama8b",
    ],
    # Science: academic accuracy, calculation
    "science": [
        "openrouter_nemotron_ultra",
        "openrouter_gptoss",
        "openrouter_trinity",
        "nvidia_nemotron",
        "cerebras_qwen235b",
    ],
    # Creative: image prompts, stories
    "creative": [
        "agnes_flash",
        "groq_llama4maverick",
        "google_gemini3_5",
        "openrouter_gemma4",
        "groq_llama4scout",
    ],
    # Vision: object detection, captioning
    "vision": [
        "openrouter_owlalpha",
        "google_gemini3_5",
        "agnes_flash",
        "cloudflare_qwen32b",
    ],
    # Heavy research: massive context + deep logic
    "heavy_research": [
        "openrouter_claude35",
        "openrouter_gpt4o",
        "google_gemini3_5",
        "openrouter_nemotron_ultra",
        "openrouter_gptoss",
        "openrouter_trinity",
        "mistral_large",
        "nvidia_llama405b",
    ],
    # Desktop control: open apps, type, click (needs speed + vision)
    "desktop": [
        "google_gemini3_5",
        "groq_llama4maverick",
        "openrouter_gemma4",
        "groq_llama8b",
    ],
    # Content generation: PPT, DOCX, long-form writing
    "content": [
        "agnes_flash",
        "groq_llama4maverick",
        "openrouter_gptoss",
        "google_gemini3_5",
        "nvidia_qwen3coder",
    ],
    # System diagnostics: fast, lightweight
    "system": [
        "openrouter_gemma4",
        "openrouter_deepseekv4",
        "google_gemini3_5",
        "groq_llama8b",
    ],
}

def _get_pool(task_type):
    """Get provider pool with dynamic Ollama injection."""
    pool = list(PROVIDER_POOL.get(task_type, PROVIDER_POOL["code"]))
    if _ollama_enabled and task_type in _OLLAMA_ELIGIBLE_POOLS:
        pool.append("ollama_local")  # Add as last fallback
    return pool

# ═══════════════════════════════════════════════════════════
# ACTION → TASK TYPE MAPPING
# ═══════════════════════════════════════════════════════════
_ACTION_TASK = {
    "read_file": "simple", "write_file": "simple", "execute_python": "simple",
    "remember": "simple", "recall": "simple", "speak": "simple",
    "emotion_state": "simple", "sensor_impute": "simple",
    "constitutional_check": "simple", "render_scene": "simple",
    "analyze_prosody": "simple",
    "auto_improve": "code", "build_model": "code", "spawn_workers": "code",
    "flow_trajectory": "code",
    "debate": "reasoning", "predict_intent": "reasoning",
    "imagine_future": "reasoning", "belief_update": "reasoning",
    "memory_search": "reasoning", "lora_from_paper": "reasoning",
    "skillweaver_browse": "reasoning",
    "discover_materials": "science", "auto_simulate": "science",
    "math_optimize": "science", "quantum_circuit": "science",
    "ai_scientist": "science", "federated_learn": "science",
    "auto_explore": "science",
    "generate_image": "creative",
    "detect_objects": "vision", "caption_image": "vision",
    "web_search": "simple",
    # Omega tools
    "open_application": "desktop", "web_search_open": "desktop",
    "type_text": "desktop", "press_key": "desktop", "click_mouse": "desktop",
    "screenshot": "desktop",
    "get_system_vitals": "system",
    "retrieve_memory": "reasoning",
    "generate_ppt": "content", "generate_docx": "content",
    "task_status": "system", "diagnose_task": "system",
}


def get_task_type(action_name: str, user_text: str = "") -> str:
    """Return the best task_type for a given tool action."""
    if action_name in _ACTION_TASK:
        return _ACTION_TASK[action_name]
    
    kw_map = {
        "heavy_research": r"\b(research|discover|autonomous|improve|scientist)\b",
        "science": r"\b(material|physics|quantum|simulate|math)\b",
        "reasoning": r"\b(debate|intent|imagine|belief)\b",
        "code": r"\b(build|model|code|python|write|script|debug)\b",
    }
    
    for ttype, pattern in kw_map.items():
        if re.search(pattern, user_text, re.IGNORECASE):
            return ttype
            
    # Default to fast, lightweight models for standard chat
    return "simple"

import asyncio
import httpx

async def call_llm_autotts(messages, max_tokens=2000, task_type="reasoning", n_samples=3):
    """
    GENESIS UPGRADE: AutoTTS (Test-Time Compute Engine).
    For complex tasks, dynamically generate `n_samples` diverse reasoning paths (Proposer),
    then use a Verifier to critique and select the mathematically optimal path.
    """
    log.info(f"AutoTTS: Triggering Test-Time Compute Scaling. Generating {n_samples} diverse paths...")
    
    # 1. Proposer Phase: Generate N samples in parallel (high temperature for diversity)
    async def _propose():
        try:
            return await acall_llm(messages, max_tokens=max_tokens, temperature=0.4, task_type=task_type)
        except Exception:
            return None
            
    tasks = [_propose() for _ in range(n_samples)]
    results = await asyncio.gather(*tasks)
    
    proposals = [res for res in results if res and not str(res).startswith("Error:")]
                
    if not proposals:
        log.warning("AutoTTS Proposer failed. Falling back to standard LLM call.")
        return await acall_llm(messages, max_tokens=max_tokens, temperature=0.3, task_type=task_type)
        
    if len(proposals) == 1:
        return proposals[0]

    # 2. Verifier Phase: Critique and Select
    log.info(f"AutoTTS: Verification Phase. Analyzing {len(proposals)} proposals...")
    verifier_prompt = "You are the AutoTTS Verifier. The user provided a prompt, and the Proposer generated several potential responses. Evaluate them for logical soundness, safety, and efficiency. Return the EXACT text of the best proposal. DO NOT add any extra text, markdown, or commentary. Output ONLY the winning proposal's raw text.\n\n"
    
    # We include the original prompt in the verifier's context
    orig_prompt = messages[-1]["content"] if messages else ""
    verifier_prompt += f"USER PROMPT:\n{orig_prompt}\n\n"
    
    for i, p in enumerate(proposals):
        verifier_prompt += f"--- PROPOSAL {i+1} ---\n{p}\n\n"
        
    verifier_messages = [{"role": "system", "content": "You are a perfect verification engine. Output ONLY the raw text of the best proposal."},
                         {"role": "user", "content": verifier_prompt}]
                         
    best_response = await acall_llm(verifier_messages, max_tokens=max_tokens, temperature=0.1, task_type="code")
    
    # Fallback if verifier hallucinates weird prefixes
    if len(best_response) < 10 and proposals:
         return proposals[0]
         
    return best_response

async def acall_llm(messages: list, max_tokens: int = 1500, temperature: float = 0.5, task_type: str = "simple", tools: list = None):
    messages = _truncate_messages(messages)
    """
    Smart LLM router: tries providers in priority order for the given task_type.
    Falls back automatically on 429, timeout, or any error.
    Ollama local is always first (laptop-primary architecture).
    """
    # SPEED: Check cache first (for repeated prompts like verification checks)
    ck = _cache_key(messages, max_tokens, temperature, task_type)
    cached = _cache_get(ck)
    if cached:
        log.info("LLM CACHE HIT [%s] — saved a full API call", task_type)
        return cached

    # SPEED: Check Semantic Cache for similar queries
    query = messages[-1].get("content", "") if messages else ""
    if task_type in ("simple", "vmao_plan"):
        sem_res = _semantic_search(query)
        if sem_res:
            log.info("SEMANTIC CACHE HIT — 0ms LLM bypass")
            return sem_res

    # Prevent prompt injection: only first message can be system
    for i in range(1, len(messages)):
        if messages[i].get("role") == "system":
            messages[i]["role"] = "user"

    # Basic sliding window to prevent token overflow
    max_context_chars = 80000
    while len(messages) > 2 and sum(len(str(m.get("content", ""))) for m in messages) > max_context_chars:
        # Keep system prompt at index 0, remove the oldest message at index 1
        messages.pop(1)

    # Pillar 5: Native Multimodal Vision
    import re, base64, os
    # Fast non-backtracking regex to prevent ReDoS
    vision_pattern = re.compile(r'\[NATIVE_VISION_REQUEST:\s*([^\]]+)\]')
    for msg in messages:
        if isinstance(msg.get("content"), str):
            matches = vision_pattern.findall(msg["content"])
            if matches:
                text_content = vision_pattern.sub('', msg["content"]).strip()
                content_array = [{"type": "text", "text": text_content}]
                for path in matches:
                    # Security Patch: Prevent LFI and OOM (Block /dev/ and enforce 10MB limit)
                    if os.path.exists(path) and not path.startswith("/dev/"):
                        try:
                            if os.path.getsize(path) < 10 * 1024 * 1024:
                                with open(path, "rb") as img_file:
                                    b64 = base64.b64encode(img_file.read()).decode('utf-8')
                                ext = path.split('.')[-1].lower()
                                mime = "image/png" if ext == "png" else "image/jpeg"
                                content_array.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                                })
                        except Exception as e:
                            log.error(f"Failed to read image {path}: {e}")
                msg["content"] = content_array
                task_type = "vision" # Force routing to a vision model!

    preferred = _get_pool(task_type)
    last_error = None
    _t0 = time.time()
    for pkey in preferred:
        provider = PROVIDERS.get(pkey)
        if not provider:
            continue


        try:
            # Inject OpenRouter rotating key if applicable
            headers = provider["headers"].copy()
            if "openrouter.ai" in provider["url"]:
                current_or_key = await openrouter_key_manager.aget_key()
                headers["Authorization"] = f"Bearer {current_or_key}"
                headers["HTTP-Referer"] = "https://xoyo.ai"
                headers["X-Title"] = "XOYO Omega"
            
            # Gemini Native API formatting (Gemini doesn't use standard OpenAI schema for /generateContent)
            if "generativelanguage" in provider["url"]:
                # Convert OpenAI messages to Gemini contents
                gemini_contents = []
                for m in messages:
                    role = "model" if m["role"] == "assistant" else "user"
                    parts = []
                    if isinstance(m["content"], str):
                        parts.append({"text": m["content"]})
                    elif isinstance(m["content"], list):
                        for c in m["content"]:
                            if c.get("type") == "text":
                                parts.append({"text": c["text"]})
                            elif c.get("type") == "image_url":
                                b64_data = c["image_url"]["url"].split("base64,")[1]
                                mime = c["image_url"]["url"].split(";")[0].split(":")[1]
                                parts.append({"inlineData": {"mimeType": mime, "data": b64_data}})
                    gemini_contents.append({"role": role, "parts": parts})
                
                payload = {
                    "contents": gemini_contents,
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": temperature,
                    }
                }
            else:
                payload = {
                    "model": provider["model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if tools and "generativelanguage" not in provider["url"]:
                    payload["tools"] = tools

            async with httpx.AsyncClient(timeout=httpx.Timeout(provider["timeout"], connect=5.0)) as client:
                resp = await client.post(
                    provider["url"],
                    json=payload,
                    headers=headers,
                )
            rj = resp.json()

            # Handle OpenRouter Rate Limits
            if resp.status_code == 429 and "openrouter.ai" in provider["url"]:
                retry_after = resp.headers.get("Retry-After")
                x_reset = resp.headers.get("x-ratelimit-reset")
                if retry_after and retry_after.replace('.', '', 1).isdigit():
                    wait_s = float(retry_after)
                elif x_reset and x_reset.replace('.', '', 1).isdigit():
                    reset_val = float(x_reset)
                    wait_s = reset_val - time.time() if reset_val > time.time() else reset_val
                else:
                    wait_s = 2.0
                openrouter_key_manager.mark_rate_limited(current_or_key, wait_s)
                continue # Retry immediately with the next key!

            if "choices" in rj:
                msg = rj["choices"][0]["message"]

                
                # Pillar 1: Native Function Calling Support
                if "tool_calls" in msg and msg["tool_calls"]:
                    log.info("LLM [%s] natively invoked %d tools.", pkey, len(msg["tool_calls"]))
                    return {"tool_calls": msg["tool_calls"]}
                
                out = msg.get("content") or ""
                out = out.strip()
                log.info("LLM [%s] (%s) %.2fs: %s", pkey, provider["model"], time.time()-_t0, out[:200])
                # Cache the result
                _cache_put(ck, out)
                if task_type in ("simple", "vmao_plan"):
                    _semantic_add(query, out)
                return out

            # Rate limited — back off and try next (with jitter to avoid thundering herd)
            if resp.status_code == 429:
                wait = min(int(resp.headers.get("Retry-After", 2)), 5)  # SPEED: Cap wait at 5s
                jitter = random.uniform(0, 1)  # SPEED: Reduced jitter
                log.warning("LLM [%s] rate-limited, waiting %.1fs", pkey, wait + jitter)
                await asyncio.sleep(wait + jitter)
                last_error = f"{pkey} rate limited (429)"
                continue

            # Other error
            try:
                err = rj.get("error", rj)
            except AttributeError:
                err = rj
            log.warning("LLM [%s] error: %s", pkey, str(err)[:200])
            last_error = str(err)

        except json.JSONDecodeError:
            log.warning("LLM [%s] returned invalid JSON (HTTP %d). Response: %s", pkey, resp.status_code, resp.text[:100])
            last_error = f"{pkey} invalid JSON response"
        except httpx.TimeoutException:
            log.warning("LLM [%s] timed out after %ds", pkey, provider["timeout"])
            last_error = f"{pkey} timeout"
        except httpx.ConnectError:
            log.warning("LLM [%s] connection refused (service down)", pkey)
            last_error = f"{pkey} connection refused"
        except Exception as e:
            log.warning("LLM [%s] unexpected error: %s", pkey, str(e)[:200])
            last_error = str(e)

    return f"Error: All {len(preferred)} providers failed for task_type={task_type}. Last error: {last_error}"

def call_llm(messages: list, max_tokens: int = 1500, temperature: float = 0.5, task_type: str = "simple", tools: list = None):
    import asyncio, threading
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        result = None
        exception = None
        def _run():
            nonlocal result, exception
            try:
                result = asyncio.run(acall_llm(messages, max_tokens, temperature, task_type, tools))
            except Exception as e:
                exception = e
        t = threading.Thread(target=_run)
        t.start()
        t.join()
        if exception:
            raise exception
        return result
    else:
        return asyncio.run(acall_llm(messages, max_tokens, temperature, task_type, tools))

async def call_llm_stream(messages: list, max_tokens: int = 1500, temperature: float = 0.5, task_type: str = "simple"):
    messages = _truncate_messages(messages)
    """
    Generator that yields text chunks for SSE streaming.
    Only supports providers that support OpenAI-compatible streaming (Groq, NVIDIA, Ollama).
    """
    import json, asyncio, threading

    # Prevent prompt injection: only first message can be system
    for i in range(1, len(messages)):
        if messages[i].get("role") == "system":
            messages[i]["role"] = "user"

    # Basic sliding window to prevent token overflow
    max_context_chars = 80000
    while len(messages) > 2 and sum(len(str(m.get("content", ""))) for m in messages) > max_context_chars:
        # Keep system prompt at index 0, remove the oldest message at index 1
        messages.pop(1)

    # Pillar 5: Native Multimodal Vision
    import re, base64, os
    # Fast non-backtracking regex to prevent ReDoS
    vision_pattern = re.compile(r'\[NATIVE_VISION_REQUEST:\s*([^\]]+)\]')
    for msg in messages:
        if isinstance(msg.get("content"), str):
            matches = vision_pattern.findall(msg["content"])
            if matches:
                text_content = vision_pattern.sub('', msg["content"]).strip()
                content_array = [{"type": "text", "text": text_content}]
                for path in matches:
                    # Security Patch: Prevent LFI and OOM (Block /dev/ and enforce 10MB limit)
                    if os.path.exists(path) and not path.startswith("/dev/"):
                        try:
                            if os.path.getsize(path) < 10 * 1024 * 1024:
                                with open(path, "rb") as img_file:
                                    b64 = base64.b64encode(img_file.read()).decode('utf-8')
                                ext = path.split('.')[-1].lower()
                                mime = "image/png" if ext == "png" else "image/jpeg"
                                content_array.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
                        except Exception as e:
                            log.error(f"Failed to read image {path}: {e}")
                msg["content"] = content_array
                task_type = "vision" # Force routing to a vision model!

    preferred = _get_pool(task_type)

    for pkey in preferred:
        provider = PROVIDERS.get(pkey)
        if not provider: continue

        q = asyncio.Queue()
        
        def worker():
            yielded_any = False
            try:
                payload = {
                    "model": provider["model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                }
                resp = requests.post(
                    provider["url"],
                    json=payload,
                    headers=provider["headers"],
                    timeout=(5, provider["timeout"]),
                    stream=True,
                )
                
                if resp.status_code != 200:
                    resp.close()
                    q.put_nowait(("next", None))
                    return

                for line in resp.iter_lines():
                    if line.startswith(b"data: "):
                        if line == b"data: [DONE]":
                            break
                        try:
                            chunk = json.loads(line[6:])
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    yielded_any = True
                                    q.put_nowait(("data", delta))
                        except json.JSONDecodeError:
                            pass
                resp.close()
                q.put_nowait(("done", None))
            except Exception as e:
                log.warning("Streaming LLM [%s] error: %s", pkey, str(e)[:100])
                q.put_nowait(("error", e, yielded_any))

        threading.Thread(target=worker, daemon=True).start()

        success = False
        while True:
            msg_type, payload, *args = await q.get()
            if msg_type == "data":
                yield payload
            elif msg_type == "next":
                break
            elif msg_type == "done":
                success = True
                break
            elif msg_type == "error":
                e, yielded_any = payload, args[0]
                if yielded_any:
                    yield "\n\n[Error: Connection dropped mid-stream.]"
                    return
                break

        if success:
            return
            
    # If all fail, yield an error message
    yield "Error: All LLM providers failed to stream."
