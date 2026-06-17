"""
Active Inference Engine – XOYO's Core Drive
Based on: Friston's Free Energy Principle, pymdp library, REBUS model.

Unifies perception, learning, and curiosity under a single mathematical objective:
minimise variational free energy at every timestep.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, json, time, threading, requests, redis, numpy as np
from typing import Optional, List

app = FastAPI()
r = redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)

# ============================================================
# GENERATIVE MODEL (discrete state space)
# ============================================================
# For demonstration: 4 hidden states × 4 observation types
NUM_STATES = 4
NUM_OBS = 4

# A: observation likelihood P(o|s) – learnable
A = np.ones((NUM_OBS, NUM_STATES)) / NUM_OBS

# B: state transition P(s'|s) – learnable (assume identity initially)
B = np.eye(NUM_STATES)

# C: prior preferences (which observations XOYO prefers)
C = np.ones(NUM_OBS) / NUM_OBS   # uniform = curious about everything

# D: initial state belief
q_s = np.ones(NUM_STATES) / NUM_STATES   # current belief

# Precision (REBUS parameter: how much to weight prediction vs evidence)
precision = 1.0

# Running cumulative free energy (curiosity metric)
cumulative_F = 0.0
F_history = []

# ============================================================
# BELIEF UPDATE (Variational Inference)
# ============================================================
def predict():
    """q(s_t) ← B · q(s_{t-1})"""
    global q_s
    q_s = B @ q_s
    return q_s

def infer(observation_idx: int):
    """Update q(s) given observation o_t via Bayes rule."""
    global q_s, A
    likelihood = A[observation_idx, :]           # P(o_t | s)
    q_s = likelihood * q_s                       # element-wise
    q_s /= q_s.sum()                             # normalise
    return q_s

def compute_free_energy(observation_idx: int):
    """F = KL[q(s)‖p(s)] − E[log P(o|s)]"""
    global q_s, A, C, precision
    # Accuracy: expected log likelihood
    accuracy = np.log(A[observation_idx, :] + 1e-9) @ q_s
    # Complexity: KL divergence from prior preferences (C)
    complexity = (q_s * (np.log(q_s + 1e-9) - np.log(C + 1e-9))).sum()
    F = complexity - accuracy
    return float(F / precision)

# ============================================================
# ACTION = SELECT TOOL THAT MINIMISES EXPECTED FREE ENERGY
# ============================================================
def select_action():
    """Simple heuristic: return the observation index with highest probability."""
    global q_s, A
    predicted_obs = A @ q_s
    return int(np.argmax(predicted_obs))

# ============================================================
# AUTONOMOUS ACTIVE INFERENCE LOOP
# ============================================================
active_inference_enabled = True
last_surprise = 0.0

def ai_loop():
    global q_s, cumulative_F, last_surprise
    while True:
        if not active_inference_enabled:
            time.sleep(2.0)
            continue
        try:
            try:
                vitals = requests.get("http://127.0.0.1:8044/vitals", timeout=2).json()
                if vitals.get("cpu_percent", 0) > 85 or vitals.get("ram_percent", 0) > 90:
                    print("Active Inference: System under load. Yielding.")
                    time.sleep(5.0)
                    continue
            except Exception:
                pass
            
            # Step 1: Predict
            predict()

            # Step 2: Get observation (e.g. from Bayesian surprise engine, or random)
            # In practice, use the orchestrator's latest state summary.
            try:
                obs_resp = requests.get("http://127.0.0.1:8015/health", timeout=3)
                obs_idx = hash(obs_resp.text) % NUM_OBS
            except Exception:
                obs_idx = np.random.randint(0, NUM_OBS)

            # Step 3: Infer
            infer(obs_idx)

            # Step 4: Compute free energy
            F = compute_free_energy(obs_idx)
            cumulative_F += F
            F_history.append((time.time(), F))
            if len(F_history) > 100:
                F_history.pop(0)

            # Step 5: If free energy spikes, log observation silently
            # NEVER escalate to /command — that causes phantom task spam
            if F > 2.0 and F > last_surprise * 1.5:
                try:
                    requests.post("http://127.0.0.1:9000/internal/observe", json={
                        "text": f"High free energy detected (F={round(F,3)}). Beliefs shifting — anomaly in sensor fusion.",
                        "source": "active_inference",
                        "severity": "warning" if F > 3.0 else "info"
                    }, timeout=3)
                except Exception:
                    pass
            last_surprise = F

            # Store in Redis
            r.set("xoyo:active_inference_qs", json.dumps(q_s.tolist()))
            r.set("xoyo:active_inference_F", json.dumps({"current": F, "cumulative": cumulative_F}))

            # Slow drift of A (learning)
            global A
            A = 0.95 * A + 0.05 * (np.outer(np.eye(NUM_OBS)[obs_idx], q_s) + 1e-9)
            A /= A.sum(axis=0, keepdims=True)

        except Exception as e:
            pass
        time.sleep(1.5)

threading.Thread(target=ai_loop, daemon=True).start()

# ============================================================
# API ENDPOINTS
# ============================================================
class BeliefUpdate(BaseModel):
    observation: str = ""

@app.post("/belief_update")
async def update_belief(req: BeliefUpdate):
    """Externally feed an observation into the active inference loop."""
    obs_idx = hash(req.observation) % NUM_OBS
    infer(obs_idx)
    F = compute_free_energy(obs_idx)
    return {"observation": req.observation, "free_energy": F, "belief_state": q_s.tolist()}

@app.get("/state")
async def get_state():
    """Current belief state and free energy."""
    return {
        "belief_state": q_s.tolist(),
        "free_energy_current": float(compute_free_energy(0)),
        "free_energy_cumulative": cumulative_F,
        "history_last_10": F_history[-10:]
    }

@app.post("/autonomous")
async def toggle_autonomous(active: bool = True):
    global active_inference_enabled
    active_inference_enabled = active
    return {"active_inference": active_inference_enabled}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "Active Inference Engine (Friston Free Energy Principle)",
        "principle": "Minimise variational free energy → perception + learning + curiosity",
        "belief_dim": NUM_STATES,
        "cumulative_free_energy": round(cumulative_F, 3),
        "active": active_inference_enabled,
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8032)
