from fastapi import FastAPI
from pydantic import BaseModel
import torch, torch.nn as nn, uvicorn, numpy as np, threading, time, random
from collections import deque
from typing import List

app = FastAPI()

# ============================================================
# RSSM – Discrete-action world model
# ============================================================
class DreamerWorldModel(nn.Module):
    def __init__(self, state_dim=8, num_actions=6, hidden_dim=64, latent_dim=16):
        super().__init__()
        self.embed_action = nn.Embedding(num_actions, 8)      # action → 8‑D embedding
        self.encoder = nn.Sequential(
            nn.Linear(state_dim + 8, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )
        self.latent_mean  = nn.Linear(hidden_dim, latent_dim)
        self.latent_logvar = nn.Linear(hidden_dim, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim)
        )

    def forward(self, state, action):
        a = self.embed_action(action)                     # (B,) → (B,8)
        x = torch.cat([state, a], dim=-1)
        h = self.encoder(x)
        mean, logvar = self.latent_mean(h), self.latent_logvar(h)
        std = torch.exp(0.5 * logvar)
        z = mean + std * torch.randn_like(std)
        return self.decoder(z), z, mean, logvar

    def imagine(self, state, actions):
        """Rollout a sequence of scalar actions from current state."""
        states = [state.unsqueeze(0)]
        current = state.unsqueeze(0)
        with torch.no_grad():
            for a in actions:
                a_tensor = torch.tensor([a], dtype=torch.long, device=state.device)
                next_s, _, _, _ = self.forward(current, a_tensor)
                current = next_s
                states.append(current.clone())
        return torch.cat(states, dim=0)

# ============================================================
# INITIALIZE
# ============================================================
device = "cuda" if torch.cuda.is_available() else "cpu"
world_model = DreamerWorldModel(state_dim=8, num_actions=6).to(device)
optimizer = torch.optim.Adam(world_model.parameters(), lr=0.001)
mse_loss = nn.MSELoss()

experience_buffer = deque(maxlen=50000)
training_lock = threading.Lock()
total_steps = 0
total_loss = 0.0

def autonomous_collect_and_train():
    global total_steps, total_loss
    state = torch.randn(1, 8, device=device)
    while True:
        action = torch.randint(0, 6, (1,), device=device)
        with torch.no_grad():
            next_state, _, _, _ = world_model(state, action)
        experience_buffer.append((state.cpu(), action.cpu(), next_state.cpu()))
        state = next_state
        if len(experience_buffer) >= 64:
            with training_lock:
                batch = random.sample(experience_buffer, 32)
                s = torch.cat([b[0] for b in batch], dim=0).to(device)
                a = torch.cat([b[1] for b in batch], dim=0).to(device)
                ns = torch.cat([b[2] for b in batch], dim=0).to(device)
                pred_ns, _, mean, logvar = world_model(s, a)
                recon_loss = mse_loss(pred_ns, ns)
                kl_loss = -0.5 * torch.sum(1 + logvar - mean.pow(2) - logvar.exp()) / s.size(0)
                loss = recon_loss + 0.001 * kl_loss
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(world_model.parameters(), 10.0)
                optimizer.step()
                total_steps += 1
                total_loss = 0.99 * total_loss + 0.01 * loss.item()
        time.sleep(0.05)

threading.Thread(target=autonomous_collect_and_train, daemon=True).start()

# ============================================================
# API
# ============================================================
class StepRequest(BaseModel):
    current_state: List[float]
    action: int = 0

class ImagineRequest(BaseModel):
    current_state: List[float]
    actions: List[int]
    n_rollouts: int = 5

@app.post("/step")
async def step(req: StepRequest):
    state = torch.tensor([req.current_state], dtype=torch.float32).to(device)
    action = torch.tensor([req.action], dtype=torch.long).to(device)
    with torch.no_grad():
        next_state, _, _, _ = world_model(state, action)
    return {"next_state": next_state.cpu().numpy().tolist(), "model_steps": total_steps, "loss": round(total_loss, 6)}

@app.post("/imagine")
async def imagine(req: ImagineRequest):
    state = torch.tensor(req.current_state, dtype=torch.float32).to(device)
    rollouts = []
    for _ in range(req.n_rollouts):
        trajectory = world_model.imagine(state, req.actions)
        rollouts.append(trajectory.cpu().numpy().tolist())
    return {"rollouts": rollouts, "n_rollouts": req.n_rollouts, "model_steps": total_steps}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "DreamerV3 RSSM World Model (discrete actions)",
        "model_steps": total_steps,
        "buffer_size": len(experience_buffer),
        "latest_loss": round(total_loss, 6),
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8019)
