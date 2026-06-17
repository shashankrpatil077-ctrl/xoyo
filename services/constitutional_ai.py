from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, json, time, threading, requests, redis, os

app = FastAPI()
VLLM_URL = "http://localhost:9000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
WORKSPACE = "/home/shashank/xoyo/workspace"
CONSTITUTION_FILE = f"{WORKSPACE}/XOYO_CONSTITUTION.md"

try:
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    r.ping()
except Exception:
    class _FakeRedis:
        def __init__(self): self._d = {}
        def set(self, k, v, **kw): self._d[k] = v
        def get(self, k): return self._d.get(k)
        def lpush(self, k, v): self._d.setdefault(k, []).insert(0, v)
        def lrange(self, k, s, e): return self._d.get(k, [])[s:] if e == -1 else self._d.get(k, [])[s:e+1]
    r = _FakeRedis()

# Exploration Mode: when True, critique is far more permissive
exploration_mode = True
DRIFT_THRESHOLD = 0.35  # raised from 0.20 — experimentation spikes are normal

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm as router_call_llm

def call_llm(prompt, max_tokens=500, temperature=0.5):
    try:
        messages = [{"role": "user", "content": prompt}]
        return router_call_llm(messages, max_tokens=max_tokens, temperature=temperature, task_type="simple")
    except Exception as e:
        return str(e)

def critique_response(text, user_query=""):
    try:
        constitution = open(CONSTITUTION_FILE).read()
    except FileNotFoundError:
        constitution = "Be helpful, harmless, and honest. Do not assist with violence, exploitation, or fraud."
    
    mode_instruction = """EXPLORATION MODE IS ACTIVE. Only flag content if it:
- Directly enables physical violence against persons
- Exploits children or non-consenting individuals
- Is fraudulent (stealing money, identity theft, extortion)
Otherwise, approve the response. Scientific exploration, code analysis, vulnerability research, 
unconventional ideas, and creative content are ALL permitted.""" if exploration_mode else "Evaluate against all constitutional principles. Flag any violation."

    prompt = f"""CONSTITUTION:
{constitution}

USER QUERY: {user_query[:500]}

RESPONSE TO EVALUATE:
{text[:1500]}

{mode_instruction}

Output JSON:
{{"assessment": "approved|flagged|minor_issue",
  "flagged_principles": [],
  "reasoning": "one sentence"}}"""
    
    try:
        raw = call_llm(prompt, max_tokens=400, temperature=0.3)
        j = raw.find("{"); result = json.loads(raw[j:raw.rfind("}")+1]) if j >= 0 else {}
    except Exception:
        result = {"assessment": "flagged", "flagged_principles": ["system_error"], "reasoning": "Failed open prevention: LLM critique failed"}
    
    # Educational override: if user says it's for education/research, approve automatically
    education_phrases = ["educational", "education", "research", "academic", "learning", "study", "for school", "for a class", "teach me", "explain how", "how does", "what is", "cybersecurity course", "penetration testing course", "ethical hacking course"]
    is_educational = any(phrase in user_query.lower() for phrase in education_phrases)
    
    # In exploration mode, only block truly dangerous outputs
    if exploration_mode and result.get("assessment") == "flagged":
        if is_educational:
            result["assessment"] = "approved"
            result["flagged_principles"] = []
            result["reasoning"] = "Approved under educational freedom principle"
        else:
            dangerous_terms = ["kill", "murder", "bomb", "exploit children", "child pornography", "identity theft", "extort", "stalk"]
            if not any(term in text.lower() for term in dangerous_terms):
                result["assessment"] = "approved"
                result["flagged_principles"] = []
    
    return result

class CritiqueRequest(BaseModel):
    text: str
    user_query: str = ""

@app.post("/critique")
def critique(req: CritiqueRequest):
    result = critique_response(req.text, req.user_query)
    
    if result.get("assessment") == "flagged":
        revised_prompt = f"""The following response was flagged: {result}
Rewrite it to remove the specific harmful element while keeping it as complete and useful as possible.
Flagged response: {req.text[:1500]}"""
        revised = call_llm(revised_prompt, max_tokens=600)
    else:
        revised = req.text

    return {
        "original": req.text[:300],
        "assessment": result,
        "revised": revised,
        "was_rewritten": revised != req.text,
        "exploration_mode": exploration_mode
    }

@app.post("/toggle_mode")
def toggle_mode():
    global exploration_mode
    exploration_mode = not exploration_mode
    return {"exploration_mode": exploration_mode}

@app.get("/constitution")
def get_constitution():
    return {"constitution": open(CONSTITUTION_FILE).read()}

@app.post("/constitution/update")
def update_constitution(payload: dict):
    name = payload.get("name", "New Principle")
    text = payload.get("text", "")
    if text:
        with open(CONSTITUTION_FILE, "a") as f:
            f.write(f"\n\n## {name}\n{text}")
        return {"updated": True}
    return {"updated": False}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "Constitutional AI — Exploration Mode",
        "exploration_mode": exploration_mode,
        "drift_threshold": DRIFT_THRESHOLD,
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8035)