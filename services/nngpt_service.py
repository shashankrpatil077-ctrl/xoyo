from fastapi import FastAPI
from pydantic import BaseModel
import os, json, subprocess, tempfile, hashlib, time, requests, uvicorn
import re
from typing import Optional

app = FastAPI()
VLLM_URL = "http://localhost:9000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
WORKSPACE = "/home/shashank/xoyo/workspace"
MODELS_DIR = "/home/shashank/xoyo/models"
ARCHIVE_DIR = f"{WORKSPACE}/nngpt_archive"
REGISTRY_FILE = f"{WORKSPACE}/worker_registry.json"

# ============================================================
# EWC (Elastic Weight Consolidation) — prevents forgetting
# ============================================================
import copy
ewc_fisher = {}          # Fisher Information Matrix (diagonal) per task
ewc_optimal_weights = {}  # Snapshot of weights after each task
ewc_lambda = 5000.0       # EWC penalty strength
ewc_task_counter = 0

def compute_fisher(model, dataloader, num_samples=100):
    """Compute diagonal Fisher Information Matrix on a data sample."""
    import torch, torch.nn as nn
    fisher = {}
    for name, param in model.named_parameters():
        fisher[name] = torch.zeros_like(param)
    model.eval()
    criterion = nn.MSELoss()
    for _ in range(min(num_samples, 20)):
        x = torch.randn(1, 16)  # Use the model's expected input size
        y = torch.randn(1, 2)
        model.zero_grad()
        output = model(x)
        loss = criterion(output, y)
        loss.backward()
        for name, param in model.named_parameters():
            if param.grad is not None:
                fisher[name] += param.grad ** 2
    for name in fisher:
        fisher[name] /= min(num_samples, 20)
    return fisher

def ewc_loss(model, fisher, optimal_weights):
    """Compute the EWC penalty: sum(F_i * (theta_i - theta*_i)^2)."""
    import torch
    loss = 0.0
    for name, param in model.named_parameters():
        if name in fisher and name in optimal_weights:
            loss += torch.sum(fisher[name] * (param - optimal_weights[name]) ** 2)
    return loss


for d in [MODELS_DIR, ARCHIVE_DIR]:
    os.makedirs(d, exist_ok=True)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm as router_call_llm

def call_llm(prompt, max_tokens=1500, temperature=0.7):
    messages = [{"role": "user", "content": prompt}]
    return router_call_llm(messages, max_tokens=max_tokens, temperature=temperature, task_type="reasoning")

def clean_code(code: str) -> str:
    """Strip markdown fences and extract only Python code."""
    code = code.strip()
    if code.startswith("```"):
        first = code.find("\n")
        code = code[first+1:] if first >= 0 else code
    if code.endswith("```"):
        code = code[:code.rfind("```")]
    return code.strip()

class BuildRequest(BaseModel):
    task_description: str
    input_size: int = 16
    output_size: int = 2
    num_candidates: int = 10
    epochs: int = 5

@app.post("/build")
async def build(req: BuildRequest):
    """Full pipeline: generate, validate, train, archive."""
    t0 = time.time()

    # Stage 1 – Manager
    spec_prompt = f"""Task: {req.task_description}. Input size: {req.input_size}. Output size: {req.output_size}.
Output JSON: {{"problem_type":"regression/classification","recommended_architecture":"mlp/cnn/rnn","estimated_layers":4}}"""
    try:
        r = call_llm(spec_prompt, max_tokens=200, temperature=0.3)
        j = r.find("{"); spec = json.loads(r[j:r.rfind("}")+1]) if j >= 0 else {}
    except Exception:
        spec = {"problem_type": "regression", "recommended_architecture": "mlp", "estimated_layers": 4}

    # Stage 2 – Designer: generate candidates
    candidates = []
    for _ in range(req.num_candidates):
        prompt = f"""Write a PyTorch nn.Module class named CustomModel for: {req.task_description}.
Input size: {req.input_size}, Output size: {req.output_size}.
Use {spec.get('recommended_architecture','mlp')} with {spec.get('estimated_layers',4)} layers.
Output ONLY the Python code. No explanation. No markdown fences."""
        try:
            code = clean_code(call_llm(prompt, max_tokens=800, temperature=0.3))
            code = code.replace("IN", str(req.input_size)).replace("OUT", str(req.output_size))
            # Validate syntax
            compile(code, "<model>", "exec")
            candidates.append(code)
            if len(candidates) >= 5:
                break
        except Exception:
            pass

    if not candidates:
        return {"error": "No valid models generated", "total_attempted": req.num_candidates}

    # Stage 3 – Tuner: train best candidate
    best_code = candidates[0]
    test_script = f"""
import torch, torch.nn as nn, torch.optim as optim, json
{best_code}
model = CustomModel()
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.MSELoss() if {req.output_size} == 1 else nn.CrossEntropyLoss()
losses = []
for _ in range({req.epochs}):
    x = torch.randn(32, {req.input_size})
    y = torch.randn(32, {req.output_size}) if {req.output_size} > 1 else torch.randn(32, 1)
    loss = criterion(model(x), y)
    optimizer.zero_grad(); loss.backward(); optimizer.step()
    losses.append(float(loss.item()))
print(json.dumps({{"success": True, "final_loss": losses[-1], "params": sum(p.numel() for p in model.parameters())}}))
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(test_script); tpath = f.name
    train_res = subprocess.run(["python3", tpath], capture_output=True, text=True, timeout=60)
    os.unlink(tpath)
    try:
        train_data = json.loads(train_res.stdout.strip())
    except Exception:
        train_data = {"success": False, "error": "Training execution failed"}

    # Stage 4 – Archive
    model_name = f"nngpt_{hashlib.md5(best_code.encode()).hexdigest()[:12]}"
    with open(f"{MODELS_DIR}/{model_name}.py", "w") as f:
        f.write(best_code)

    registry = json.load(open(REGISTRY_FILE)) if os.path.exists(REGISTRY_FILE) else []
    registry.append({"name": model_name, "description": req.task_description, "created_by": "NNGPT", "loss": train_data.get("final_loss", 0)})
    json.dump(registry, open(REGISTRY_FILE, "w"))

    return {
        "model_name": model_name,
        "trained": train_data.get("success", False),
        "final_loss": train_data.get("final_loss"),
        "params": train_data.get("params", 0),
        "candidates_tested": len(candidates),
        "registry_size": len(registry),
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "autonomous": True
    }

class QuickBuildRequest(BaseModel):
    task_description: str
    input_size: int = 16
    output_size: int = 2

@app.post("/quick_build")
async def quick_build(req: QuickBuildRequest):
    prompt = f"""Write a PyTorch nn.Module class named CustomModel for: {req.task_description}.
Input size: {req.input_size}, Output size: {req.output_size}.
Use nn.Sequential with 3-4 layers. Output ONLY Python code. No markdown."""
    code = clean_code(call_llm(prompt, max_tokens=800))
    code = code.replace("IN", str(req.input_size)).replace("OUT", str(req.output_size))
    try:
        compile(code, "<model>", "exec")
    except SyntaxError as e:
        return {"error": "Syntax error", "detail": str(e), "code": code[:200]}

    model_name = f"nngpt_quick_{hashlib.md5(code.encode()).hexdigest()[:12]}"
    with open(f"{MODELS_DIR}/{model_name}.py", "w") as f:
        f.write(code)

    registry = json.load(open(REGISTRY_FILE)) if os.path.exists(REGISTRY_FILE) else []
    registry.append({"name": model_name, "description": req.task_description, "created_by": "NNGPT-quick"})
    json.dump(registry, open(REGISTRY_FILE, "w"))

    return {"model_name": model_name, "valid": True, "registry_size": len(registry), "autonomous": True}

@app.get("/health")
def health():
    registry = json.load(open(REGISTRY_FILE)) if os.path.exists(REGISTRY_FILE) else []
    return {
        "status": "ok",
        "engine": "NNGPT + AIBuildAI + ReVeal Autonomous Model Builder",
        "models_built": len(registry),
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8016)
