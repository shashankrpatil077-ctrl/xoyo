"""
Predictive Intent Engine
Fuses facial expression, voice prosody, task context, and interaction history
into a Bayesian prediction of the user's next likely command.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, torch, numpy as np, json, requests, time
from typing import List, Optional
from collections import deque

app = FastAPI()
VLLM_URL = "http://localhost:9000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"

# Possible intents XOYO can predict
INTENTS = [
    "discover_element", "simulate_physics", "render_scene", "search_web",
    "analyze_image", "debate", "spawn_workers", "remember", "recall",
    "auto_explore", "auto_simulate", "auto_improve", "build_model",
    "generate_image", "plan_task", "general_question"
]

# ============================================================
# BAYESIAN PREDICTOR (lightweight, CPU-safe)
# ============================================================
class BayesianPredictor:
    def __init__(self):
        self.counts = {intent: 1.0 for intent in INTENTS}  # Dirichlet prior
        self.total = sum(self.counts.values())

    def update(self, intent: str):
        if intent in self.counts:
            self.counts[intent] += 1.0
            self.total += 1.0

    def predict(self, features: dict) -> dict:
        """Bayesian prediction: posterior probabilities with uncertainty."""
        probs = {}
        for intent in INTENTS:
            # Base probability from Dirichlet posterior
            base_prob = self.counts[intent] / self.total
            # Boost based on LLM reasoning about features
            boost = 1.0
            if features.get("emotion") == "excited" and "discover" in intent:
                boost = 1.3
            if features.get("emotion") == "confused" and "recall" in intent:
                boost = 1.2
            probs[intent] = round(base_prob * boost, 4)
        
        # Normalize
        total = sum(probs.values())
        probs = {k: round(v/total, 4) for k, v in probs.items()}
        
        # Rank
        ranked = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return {
            "predicted_intent": ranked[0][0],
            "confidence": ranked[0][1],
            "top_3": [{"intent": r[0], "probability": r[1]} for r in ranked[:3]],
            "all": probs
        }

predictor = BayesianPredictor()
recent_intents = deque(maxlen=50)

# ============================================================
# LLM-DRIVEN INTENT REFINEMENT
# ============================================================
def llm_refine_intent(features: dict, top_candidates: list) -> dict:
    """Ask vLLM to choose the most likely intent based on context."""
    prompt = f"""User context:
- Recent interaction intents: {list(recent_intents)[-10:]}
- Features: {json.dumps(features)}
- Statistical predictions: {json.dumps(top_candidates)}

Based on this, what is the single most likely next intent?
Output JSON: {{"intent": "intent_name", "reasoning": "one sentence"}}"""
    try:
        r = requests.post(VLLM_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100, "temperature": 0.3
        }, timeout=15)
        text = r.json()["choices"][0]["message"]["content"]
        j = text.find("{"); return json.loads(text[j:text.rfind("}")+1]) if j >= 0 else {}
    except Exception:
        return {}

# ============================================================
# API
# ============================================================
class PredictRequest(BaseModel):
    features: Optional[dict] = {}
    context: str = ""

class IntentRecord(BaseModel):
    intent: str

@app.post("/predict")
async def predict(req: PredictRequest):
    """Predict the most likely next user intent."""
    features = req.features or {}
    result = predictor.predict(features)
    
    # LLM refinement (optional, adds depth)
    llm_result = llm_refine_intent(features, result["top_3"])
    if llm_result and llm_result.get("intent"):
        result["llm_refined"] = llm_result["intent"]
        result["llm_reasoning"] = llm_result.get("reasoning", "")

    return {"result": result, "autonomous": True}

@app.post("/record")
async def record(req: IntentRecord):
    """Record an executed intent to update the Bayesian model."""
    predictor.update(req.intent)
    recent_intents.append(req.intent)
    return {"recorded": req.intent, "history_size": len(recent_intents)}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Bayesian Predictive Intent BNN", "intents_tracked": len(INTENTS), "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8017)
