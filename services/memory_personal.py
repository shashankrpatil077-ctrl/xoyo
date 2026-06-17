#!/usr/bin/env python3
"""
XOYO Memory Personal — Four-tier memory microservice
Port: 8046
Handles: profile CRUD, trait evolution, skill registry, episodic storage
Research: MAGMA (2026), PersonaVLM PEM (CVPR 2026), AutoSkill (2026)
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json, os, time, logging, fcntl

logging.basicConfig(level=logging.INFO)
app = FastAPI()

# ── Storage paths ───────────────────────────────────────
USER = "shashank"
MEM_BASE = os.path.expanduser("~/xoyo/memories")
PROFILE_PATH  = f"{MEM_BASE}/profile/{USER}.json"
TRAITS_PATH   = f"{MEM_BASE}/traits/{USER}.json"
SKILLS_PATH   = f"{MEM_BASE}/skills/{USER}.json"
EPISODES_DIR  = f"{MEM_BASE}/episodes"
RAW_LOGS_DIR  = f"{MEM_BASE}/raw_logs"

for d in [f"{MEM_BASE}/profile", f"{MEM_BASE}/traits",
          f"{MEM_BASE}/skills", EPISODES_DIR, RAW_LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

# ── Redis (with fallback) ────────────────────────────────
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_client.ping()
except Exception:
    # Fallback: in-memory dict pretending to be Redis
    class _FakeRedis:
        def __init__(self):
            self._d = {}
        def rpush(self, k, v):
            self._d.setdefault(k, []).append(v)
        def ltrim(self, k, s, e):
            if k in self._d:
                lst = self._d[k]
                if e < 0: e = len(lst) + e
                self._d[k] = lst[s:e+1] if e >= 0 else lst[s:]
        def lrange(self, k, s, e):
            lst = self._d.get(k, [])
            return lst[s:] if e == -1 else lst[s:e+1]
        def expire(self, k, ttl):
            pass
    redis_client = _FakeRedis()

# ── Default Profile ──────────────────────────────────────
DEFAULT_PROFILE = {
    "name": "Shashank",
    "hardware": "Intel i3-1115G4, 8GB RAM, no GPU, Ubuntu 24.04",
    "project": "XOYO Omega — autonomous multi-agent ecosystem",
    "interests": [],
    "preferences": [],
    "languages": ["English", "Hindi"],
    "coding_stack": ["Python", "FastAPI", "Ollama", "Redis"],
    "personality_preference": "witty, flirty, uses punchlines",
    "updated": time.strftime("%Y-%m-%d")
}

DEFAULT_TRAITS = {
    "formality": 0.3, "verbosity": 0.4, "humor": 0.8,
    "empathy": 0.7, "curiosity": 0.9, "directness": 0.6,
    "creativity": 0.7, "patience": 0.5, "enthusiasm": 0.75,
    "skepticism": 0.6, "warmth": 0.8, "intellectual_depth": 0.85,
    "playfulness": 0.9
}

def _load(path, default):
    try:
        with open(path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except FileNotFoundError:
        return default.copy()
    except json.JSONDecodeError as e:
        logging.error(f"Corruption in {path}: {e}")
        return default.copy()
    except Exception as e:
        logging.error(f"Error loading {path}: {e}")
        return default.copy()

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)

# ── Endpoints ────────────────────────────────────────────

@app.get("/profile")
def get_profile():
    return _load(PROFILE_PATH, DEFAULT_PROFILE)

@app.post("/profile/update")
def update_profile(updates: Dict[str, Any]):
    profile = _load(PROFILE_PATH, DEFAULT_PROFILE)
    for k, v in updates.items():
        if isinstance(v, list) and isinstance(profile.get(k), list):
            existing = set(map(str, profile[k]))
            profile[k] = list(existing | set(map(str, v)))
        else:
            profile[k] = v
    profile["updated"] = time.strftime("%Y-%m-%d")
    _save(PROFILE_PATH, profile)
    return {"status": "ok", "profile": profile}

@app.get("/traits")
def get_traits():
    return _load(TRAITS_PATH, DEFAULT_TRAITS)

@app.post("/traits/update")
def update_traits(observed: Dict[str, float]):
    """
    Update traits using PersonaVLM PEM momentum formula.
    trait_new = 0.85 × trait_old + 0.15 × trait_observed
    """
    traits = _load(TRAITS_PATH, DEFAULT_TRAITS)
    for k, v in observed.items():
        if k in traits:
            traits[k] = round(0.85 * traits[k] + 0.15 * v, 4)
    _save(TRAITS_PATH, traits)
    return {"status": "ok", "traits": traits}

@app.get("/skills")
def get_skills():
    return _load(SKILLS_PATH, {"skills": []})

@app.post("/skills/add")
def add_skill(skill: Dict[str, str]):
    """Add a behavioral skill extracted from repeated patterns."""
    data = _load(SKILLS_PATH, {"skills": []})
    existing_patterns = {s.get("pattern", "") for s in data["skills"]}
    if skill.get("pattern") not in existing_patterns:
        skill["added"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        data["skills"].append(skill)
        _save(SKILLS_PATH, data)
    return {"status": "ok", "skills": len(data["skills"])}

@app.post("/episodes/save")
def save_episode(episode: Dict[str, Any]):
    """Save an episodic memory to disk."""
    ts = time.strftime("%Y-%m-%d-%H%M%S")
    title = episode.get("title", "untitled").replace(" ", "_")[:40]
    path = f"{EPISODES_DIR}/{ts}-{title}.json"
    episode["saved_at"] = ts
    _save(path, episode)
    return {"status": "ok", "path": path}

@app.get("/episodes/search")
def search_episodes(query: str = "", limit: int = 5):
    """Search episodes by filename and content keywords."""
    results = []
    try:
        for fname in sorted(os.listdir(EPISODES_DIR), reverse=True):
            if not fname.endswith(".json"): continue
            try:
                with open(f"{EPISODES_DIR}/{fname}") as f:
                    ep = json.load(f)
                content = json.dumps(ep).lower()
                if not query or query.lower() in content:
                    results.append(ep)
                if len(results) >= limit: break
            except Exception as e: 
                logging.error(f"Error reading episode {fname}: {e}")
    except FileNotFoundError: pass
    return {"results": results, "count": len(results)}

@app.post("/conversation/append")
def append_conversation(turn: Dict[str, str]):
    """Append a turn to working memory (T1). Capped at 50 turns."""
    key = f"memory:conversation:{USER}"
    redis_client.rpush(key, json.dumps(turn))
    redis_client.ltrim(key, -50, -1)
    redis_client.expire(key, 7200)
    return {"status": "ok"}

@app.get("/conversation/recent")
def get_recent_conversation(n: int = 20):
    key = f"memory:conversation:{USER}"
    turns = redis_client.lrange(key, -n, -1)
    return {"turns": [json.loads(t) if isinstance(t, str) else t for t in turns]}

@app.get("/health")
def health():
    return {"status": "ok", "service": "memory_personal", "port": 8046}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8046)
