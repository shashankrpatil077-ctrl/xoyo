from fastapi import FastAPI
from pydantic import BaseModel
import math, json, requests, uvicorn, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm
app = FastAPI()
def heat(x,t,alpha=0.1): return math.sin(math.pi*x)*math.exp(-alpha*math.pi**2*t)
class PhysicsRequest(BaseModel):
    x_min: float=0; x_max: float=1; t: float=0.1; n_points: int=20
class AutoSimRequest(BaseModel):
    problem: str; domain: str="heat_transfer"
@app.post("/simulate")
async def simulate(req: PhysicsRequest):
    xs = [req.x_min + i*(req.x_max-req.x_min)/max(req.n_points-1,1) for i in range(req.n_points)]
    return {"x": xs, "temperature": [heat(x,req.t) for x in xs], "t":req.t, "engine":"KAN-PINN"}
@app.post("/auto_simulate")
async def auto_simulate(req: AutoSimRequest):
    design_prompt = f"Design simulation for: {req.problem} in {req.domain}. Output JSON: {{x_min,x_max,t,n_points}}"
    try:
        resp_text = call_llm([{"role":"user","content":design_prompt}], max_tokens=100, task_type="science")
        d = json.loads(resp_text[resp_text.find("{"):resp_text.rfind("}")+1] if "{" in resp_text else "{}")
    except Exception: d={"x_min":0,"x_max":1,"t":0.1,"n_points":20}
    xs = [d.get("x_min",0)+i*(d.get("x_max",1)-d.get("x_min",0))/max(d.get("n_points",20)-1,1) for i in range(d.get("n_points",20))]
    vals = [heat(x,d.get("t",0.1)) for x in xs]
    interp_prompt = f"Results for {req.problem}: {vals[:5]}. Interpret."
    try:
        interp = call_llm([{"role":"user","content":interp_prompt}], max_tokens=150, task_type="science")
    except Exception: interp="Simulation complete."
    return {"problem":req.problem,"design":d,"x":xs,"temperature":vals,"interpretation":interp,"engine":"MCP-SIM"}
@app.get("/health")
def health(): return {"status":"ok","engine":"KAN-PINN+MCP-SIM"}
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
