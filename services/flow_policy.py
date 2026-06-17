"""
Flow-Matching Policy – Continuous Action Trajectory Generator
Based on: Flow Matching (Lipman et al., 2023), OT-CFM (Tong et al., 2023).
Self-trains on synthetic expert trajectories and generates smooth action sequences.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import torch, torch.nn as nn, uvicorn, numpy as np, json, time, threading, redis
from typing import List

app = FastAPI()

# ============================================================
# CONFIG
# ============================================================
ACTION_DIM = 6          # e.g., 3 pos + 3 rot
LATENT_DIM = 64
HIDDEN_DIM = 128
TRAIN_INTERVAL = 60     # seconds between training refreshes
TRAJECTORY_LENGTH = 50  # steps per trajectory

# ============================================================
# VELOCITY FIELD MLP
# ============================================================
class VelocityField(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(ACTION_DIM + 1, HIDDEN_DIM),  # input: (x, t)
            nn.SiLU(),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
            nn.SiLU(),
            nn.Linear(HIDDEN_DIM, ACTION_DIM)
        )

    def forward(self, x, t):
        """x: (B, action_dim), t: (B, 1) → velocity: (B, action_dim)"""
        inp = torch.cat([x, t], dim=-1)
        return self.net(inp)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = VelocityField().to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Try to load saved weights from Redis
r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
saved = r.get("xoyo:flow_weights")
if saved:
    try:
        state = json.loads(saved)
        for name, param in model.named_parameters():
            if name in state:
                param.data = torch.tensor(state[name]).to(device)
        print("Loaded flow weights from Redis")
    except Exception:
        print("Could not load flow weights; starting fresh")
model.train()

# ============================================================
# SELF-TRAINING LOOP
# ============================================================
def generate_expert_trajectory():
    """Synthetic smooth trajectory: sinusoidal movement primitives."""
    t = np.linspace(0, 2*np.pi, TRAJECTORY_LENGTH)
    traj = np.zeros((TRAJECTORY_LENGTH, ACTION_DIM))
    traj[:, 0] = np.sin(t)      # x position
    traj[:, 1] = np.cos(t)      # y position
    traj[:, 2] = np.sin(2*t)/2  # z position
    traj[:, 3] = np.sin(t/2)    # rx rotation
    traj[:, 4] = np.cos(t/2)    # ry rotation
    traj[:, 5] = t / (2*np.pi)  # rz rotation
    return torch.tensor(traj, dtype=torch.float32)

def train_step():
    """One gradient step using OT-CFM loss."""
    traj = generate_expert_trajectory().to(device)   # (T, D)
    x0 = torch.randn(TRAJECTORY_LENGTH, ACTION_DIM, device=device)
    x1 = traj

    # Sample t uniformly
    t_vec = torch.rand(TRAJECTORY_LENGTH, 1, device=device)

    # OT-CFM: x_t = (1-t)*x0 + t*x1 + small noise
    sigma = 0.001
    noise = sigma * torch.randn_like(x0)
    x_t = (1 - t_vec) * x0 + t_vec * x1 + noise

    # Target velocity: (x1 - x0)  (constant along the OT path)
    target_v = x1 - x0

    pred_v = model(x_t, t_vec)
    loss = nn.MSELoss()(pred_v, target_v)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return loss.item()

def background_training():
    while True:
        for _ in range(20):
            train_step()
        # Save to Redis periodically
        state = {name: param.data.cpu().numpy().tolist() for name, param in model.named_parameters()}
        r.set("xoyo:flow_weights", json.dumps(state))
        time.sleep(TRAIN_INTERVAL)

threading.Thread(target=background_training, daemon=True).start()

# ============================================================
# INFERENCE: ODE INTEGRATION
# ============================================================
def integrate_euler(x0, steps=20):
    """Simple Euler integration of the flow ODE from t=0 to t=1."""
    x = x0
    dt = 1.0 / steps
    with torch.no_grad():
        for i in range(steps):
            t = torch.full((x.shape[0], 1), i * dt, device=device)
            v = model(x, t)
            x = x + v * dt
    return x

class PolicyRequest(BaseModel):
    latent_vector: List[float]

@app.post("/forward")
def forward(req: PolicyRequest):
    """Generate a smooth action trajectory from a latent vector."""
    x0 = torch.tensor([req.latent_vector], dtype=torch.float32).to(device)
    # Ensure correct dimension: pad or truncate
    if x0.shape[-1] < ACTION_DIM:
        x0 = torch.cat([x0, torch.zeros(1, ACTION_DIM - x0.shape[-1], device=device)], dim=-1)
    elif x0.shape[-1] > ACTION_DIM:
        x0 = x0[:, :ACTION_DIM]
    trajectory = integrate_euler(x0, steps=20)
    return {"trajectory": trajectory.cpu().numpy().tolist(), "shape": list(trajectory.shape), "engine": "OT-CFM Flow Matching"}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Flow-Matching Policy (OT-CFM, self-training)", "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8011)
