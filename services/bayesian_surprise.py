from fastapi import FastAPI
from pydantic import BaseModel
import requests, json, uvicorn
app = FastAPI()
LLM_URL = "http://localhost:9000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
def query_belief(question):
    r = requests.post(LLM_URL, json={"model":MODEL,"messages":[{"role":"user","content":question}],"max_tokens":10}, timeout=30)
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        text = "0.5"
    import re
    nums = re.findall(r"[\d.]+", text)
    return float(nums[0]) if nums else 0.5
class HypothesisRequest(BaseModel):
    hypothesis: str
    context: str = ""
@app.post("/surprise")
async def surprise(req: HypothesisRequest):
    prior = query_belief(f"Before evidence, how likely (0-1): {req.hypothesis}")
    posterior = query_belief(f"After seeing: {req.context}, how likely (0-1): {req.hypothesis}")
    return {"hypothesis":req.hypothesis,"prior":prior,"posterior":posterior,"surprise":abs(posterior-prior)}
@app.post("/auto_explore")
async def auto_explore(payload: dict):
    domain = payload.get("domain","general")
    results = []
    for i in range(payload.get("max_iterations",3)):
        r = requests.post(LLM_URL, json={"model":MODEL,"messages":[{"role":"user","content":f"Generate a novel hypothesis in {domain}. One sentence."}],"max_tokens":80}, timeout=30)
        hyp = r.json().get("response","")
        prior = query_belief(f"Before evidence, how likely (0-1): {hyp}")
        posterior = query_belief(f"Imagine you tested: {hyp}. New confidence (0-1):")
        results.append({"hypothesis":hyp,"prior":prior,"posterior":posterior,"surprise":abs(posterior-prior)})
    results.sort(key=lambda x: x["surprise"], reverse=True)
    return {"domain":domain,"top_discovery":results[0] if results else None,"all":results}
@app.get("/health")
def health(): return {"status":"ok","engine":"AutoDiscovery LLM-as-Observer"}
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8015)
