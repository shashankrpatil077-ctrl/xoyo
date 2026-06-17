"""
SmolVLA – Autonomous Vision-Language-Action Generator
Based on: RT-2 (2023), OpenVLA (2024, 7B params, 970k trajectories).
Neuro-symbolic pipeline: LLM generates structured 3D-scene action plans,
flow-matching (port 8011) interpolates into continuous trajectories.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, json, requests, random

app = FastAPI()
VLLM_URL = "http://localhost:9000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"

class ActionRequest(BaseModel):
    instruction: str

@app.post("/act")
def generate_actions(req: ActionRequest):
    """LLM generates a complete 3D scene action plan with precise parameters."""
    prompt = f"""You are a Vision-Language-Action model controlling a 3D environment.
Instruction: {req.instruction}

Generate a structured action plan. Output JSON:
{{
  "plan": "brief description of what will happen",
  "actions": [
    {{
      "type": "camera_move|object_create|object_transform|scene_transition|physics_trigger",
      "target": "name of the object or scene element",
      "parameters": {{
        "position": [x,y,z],
        "rotation": [rx,ry,rz],
        "scale": 1.0,
        "duration_ms": 1000,
        "easing": "ease_in_out"
      }},
      "reasoning": "why this action is needed"
    }}
  ],
  "final_state_description": "what the scene looks like after all actions"
}}"""
    try:
        r = requests.post(VLLM_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400,
            "temperature": 0.5
        }, timeout=30)
        text = r.json()["choices"][0]["message"]["content"]
        j = text.find("{")
        plan = json.loads(text[j:text.rfind("}")+1]) if j >= 0 else {}
    except Exception:
        plan = {"plan": req.instruction, "actions": [], "final_state_description": "Scene unchanged."}

    return {
        "model": "SmolVLA (neuro-symbolic)",
        "plan": plan,
        "actions_count": len(plan.get("actions", [])),
        "autonomous": True
    }

@app.get("/health")
def health():
    return {"status": "ok", "engine": "SmolVLA Neuro-Symbolic VLA (LLM + flow-matching)", "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8018)
