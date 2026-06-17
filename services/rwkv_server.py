from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, requests, redis, json, time, threading
import numpy as np

app = FastAPI()

_ml_cache = {}

def get_rwkv():
    if "model" not in _ml_cache:
        print("[RWKV] Lazy loading Raven 1.5B model and tokenizer...")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _ml_cache["device"] = device
        
        MODEL_NAME = "RWKV/rwkv-raven-1b5"
        _ml_cache["tokenizer"] = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        # using low_cpu_mem_usage for safetensors if possible
        _ml_cache["model"] = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        _ml_cache["model"].eval()
        _ml_cache["torch"] = torch
        _ml_cache["HIDDEN_DIM"] = _ml_cache["model"].config.hidden_size
        print(f"[RWKV] Load complete. Hidden dim: {_ml_cache['HIDDEN_DIM']}")
    return _ml_cache["tokenizer"], _ml_cache["model"], _ml_cache["device"], _ml_cache["torch"], _ml_cache["HIDDEN_DIM"]

class Observer:
    def __init__(self):
        self.state = None
        
    def update(self, text):
        tokenizer, model, device, torch, hidden_dim = get_rwkv()
        if self.state is None:
            self.state = torch.zeros(1, hidden_dim, device=device)
            
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256).to(device)
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)
            last_hidden = outputs.hidden_states[-1].mean(dim=1)
        self.state = 0.95 * self.state + 0.05 * last_hidden
        return self.state

def kl_div(a, b):
    _, _, _, torch, _ = get_rwkv()
    s1 = torch.softmax(a, -1)
    s2 = torch.softmax(b, -1)
    return (s1 * (torch.log(s1+1e-9) - torch.log(s2+1e-9))).sum().item()

observer = Observer()
last_state = None
monitor_active = True
r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def monitor():
    global last_state
    while monitor_active:
        try:
            resp = requests.get("http://localhost:8002/continuous/status", timeout=5)
            if resp.status_code == 200:
                text = resp.json().get("latest","")
                if text and len(text) > 5:
                    ns = observer.update(text)
                    if last_state is not None and kl_div(last_state, ns) > 0.4:
                        try:
                            requests.post("http://localhost:9000/internal/observe", json={
                                "text": f"RWKV state shift detected. Latest: {text[:200]}",
                                "source": "rwkv_monitor",
                                "severity": "info"
                            }, timeout=3)
                        except Exception: pass
                    last_state = ns.clone()
                    
                    import json
                    r.set("xoyo:rwkv_hidden", json.dumps(ns.cpu().tolist()))
        except Exception:
            pass
        time.sleep(2.5)

threading.Thread(target=monitor, daemon=True).start()

class TextRequest(BaseModel):
    prompt: str

@app.post("/process")
async def process(req: TextRequest):
    tokenizer, model, device, torch, _ = get_rwkv()
    inp = tokenizer(req.prompt, return_tensors="pt", truncation=True, max_length=256).to(device)
    with torch.no_grad():
        out = model.generate(inp["input_ids"], max_new_tokens=100)
    return {"response": tokenizer.decode(out[0], skip_special_tokens=True), "engine": "RWKV Raven 1.5B"}

@app.get("/state")
async def state():
    if last_state is not None:
        return {"summary": last_state.cpu().numpy().tolist()[0][:10], "shape": list(last_state.shape)}
    return {"summary": None}

@app.get("/health")
def health():
    status = "ready" if "model" in _ml_cache else "standby (lazy load pending)"
    return {"status": status, "engine": "RWKV Raven 1.5B (GPU)", "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8024)
