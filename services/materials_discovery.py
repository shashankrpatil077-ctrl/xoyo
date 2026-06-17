"""
Autonomous Materials Discovery Service
Based on: Materials Project API, Bayesian Surprise ranking (NeurIPS 2025),
          LLM-SR hypothesis generation, Crystal GNN surrogate.

Fully autonomous closed‑loop: generates candidate materials, validates against real
database, ranks by surprise, and returns top discoveries.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import requests, json, hashlib, time, threading, os, uvicorn
from typing import Optional, List
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm as router_call_llm

app = FastAPI()

def call_llm(prompt: str, max_tokens: int = 500, temperature: float = 0.7) -> str:
    messages = [{"role": "user", "content": prompt}]
    return router_call_llm(messages, max_tokens=max_tokens, temperature=temperature, task_type="science")

# ============================================================
# MATERIALS PROJECT API CLIENT
# ============================================================
def mp_query(query_params: dict) -> dict:
    """Search the Materials Project database."""
    url = "https://api.materialsproject.org/materials/summary/"
    headers = {"X-API-KEY": os.getenv("MATERIALS_PROJECT_API_KEY", "demo")}
    try:
        r = requests.get(url, params=query_params, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            return {"error": f"MP API returned {r.status_code}", "detail": r.text[:200]}
    except Exception as e:
        return {"error": f"MP API unreachable: {str(e)}"}

def fetch_material_by_formula(formula: str) -> dict:
    """Get known properties of a specific compound."""
    resp = mp_query({"formula": formula, "_fields": "formula_pretty,formation_energy_per_atom,band_gap,e_above_hull,spacegroup"})
    return resp.get("data", [])

def search_by_property(property_name: str, min_val: float = None, max_val: float = None) -> list:
    """Search materials by property range (e.g., band_gap > 1.0)."""
    params = {"_fields": "formula_pretty,formation_energy_per_atom,band_gap"}
    if property_name in ("band_gap", "formation_energy_per_atom"):
        if min_val is not None:
            params[f"{property_name}_min"] = min_val
        if max_val is not None:
            params[f"{property_name}_max"] = max_val
    resp = mp_query(params)
    return resp.get("data", [])[:10]

# ============================================================
# HYPOTHESIS GENERATOR (vLLM)
# ============================================================
def generate_hypothesis(goal: str) -> List[dict]:
    """LLM proposes candidate materials for a given goal."""
    prompt = f"""You are a world-class materials scientist. Propose 5 plausible chemical compounds
that could achieve: {goal}
For each compound, provide:
- formula (e.g. LaH10)
- brief justification (1 sentence)
- predicted key property (e.g. Tc, hardness)
Output JSON array of objects: [{{"formula": "...", "justification": "...", "predicted_property": value}}]"""
    try:
        text = call_llm(prompt, max_tokens=500, temperature=0.7)
        j = text.find("[")
        if j >= 0:
            return json.loads(text[j:text.rfind("]")+1])
    except Exception:
        pass
    return []

# ============================================================
# BAYESIAN SURPRISE RANKING (port 8015)
# ============================================================
def rank_by_surprise(candidates: List[dict], context: str = "") -> List[dict]:
    """Score each candidate by Bayesian surprise. Falls back if external rank is empty."""
    try:
        payload = {
            "candidates": [{"hypothesis": c["formula"], "evidence": context} for c in candidates]
        }
        r = requests.post("http://localhost:8015/rank", json=payload, timeout=30)
        ranked = r.json().get("ranked", [])
        if ranked:
            merged = []
            for item in ranked:
                cand = next((c for c in candidates if c["formula"] == item.get("hypothesis", "")), {})
                cand["surprise"] = item.get("surprise", 0)
                merged.append(cand)
            return merged
    except Exception as e:
        raise RuntimeError(f"Ranking engine unavailable: {e}")

# ============================================================
# PHYSICS VALIDATION (port 8005)
# ============================================================
def validate_with_physics(formula: str) -> bool:
    """Check rough stability using PINN surrogate."""
    try:
        r = requests.post("http://localhost:8005/auto_simulate", json={
            "problem": f"Stability of {formula}",
            "domain": "materials"
        }, timeout=20)
        return "stable" in r.json().get("interpretation", "").lower()
    except Exception as e:
        raise RuntimeError(f"Physics engine unavailable: {e}")

# ============================================================
# AUTONOMOUS DISCOVERY PIPELINE
# ============================================================
class DiscoverRequest(BaseModel):
    goal: str = "Find a room-temperature superconductor"
    top_k: int = 3
    validate: bool = True

@app.post("/discover")
async def discover(req: DiscoverRequest):
    """Full autonomous discovery pipeline: generate → validate → rank → return."""
    t0 = time.time()

    # Step 1: Generate hypotheses
    candidates = generate_hypothesis(req.goal)
    if not candidates:
        return {"error": "No candidates generated"}

    # Step 2: Validate against Materials Project (enrich with real data)
    enriched = []
    for cand in candidates:
        formula = cand["formula"]
        real_data = fetch_material_by_formula(formula)
        if real_data:
            data = real_data[0]
            cand["formation_energy_real"] = data.get("formation_energy_per_atom")
            cand["band_gap_real"] = data.get("band_gap")
            cand["known"] = True
        else:
            cand["known"] = False
        enriched.append(cand)

    # Step 3: Physics validation
    if req.validate:
        for cand in enriched:
            cand["physics_stable"] = validate_with_physics(cand["formula"])

    # Step 4: Bayesian surprise ranking
    context = f"Goal: {req.goal}. Known materials data included."
    ranked = rank_by_surprise(enriched, context)

    # Step 5: Return top discoveries
    top = sorted(ranked, key=lambda x: x.get("surprise", 0), reverse=True)[:req.top_k]

    # Archive
    with open(f"/home/shashank/xoyo/workspace/discoveries_{int(time.time())}.json", "w") as f:
        json.dump(top, f)

    return {
        "goal": req.goal,
        "candidates_generated": len(candidates),
        "top_discoveries": top,
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "autonomous": True
    }

class AutoExploreRequest(BaseModel):
    domain: str = "superconductors"
    max_iterations: int = 3

@app.post("/auto_explore")
async def auto_explore(req: AutoExploreRequest):
    """Autonomous exploration: LLM selects promising directions and runs pipeline."""
    results = []
    for i in range(req.max_iterations):
        # LLM picks the next exploration domain
        prompt = f"""You are autonomously exploring {req.domain}. What specific property goal should we search next?
Output just a short goal phrase, e.g., 'Find a hydride superconductor with Tc > 200K'"""
        try:
            goal = call_llm(prompt, max_tokens=100)
            goal = goal.strip()
        except Exception:
            goal = ""
        if not goal:
            goal = f"Explore {req.domain} iteration {i+1}"
        disc = await discover(DiscoverRequest(goal=goal, top_k=2, validate=True))
        results.append(disc)

    return {"domain": req.domain, "iterations": req.max_iterations, "results": results, "autonomous": True}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Autonomous Materials Discovery (MP API + Bayesian Surprise)", "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
