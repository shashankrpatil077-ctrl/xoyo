from fastapi import FastAPI
from pydantic import BaseModel
import torch, io, base64, uvicorn, requests, json
from diffusers import StableDiffusionPipeline

app = FastAPI()
VLLM_URL = "http://localhost:9000/v1/chat/completions"
device = "cuda"
torch_dtype = torch.float16

print("Loading Stable Diffusion v1.5 on GPU …")
pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch_dtype
)
pipe.to(device)
pipe.enable_attention_slicing()          # memory‑friendly
print("SD v1.5 ready.")

def enhance_prompt(prompt: str) -> str:
    try:
        r = requests.post(VLLM_URL, json={
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "messages": [{"role": "user", "content": f"Enhance this image prompt to be highly detailed and vivid: {prompt}. Output only the enhanced prompt."}],
            "max_tokens": 100
        }, timeout=20)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return prompt

class GenerateRequest(BaseModel):
    prompt: str
    steps: int = 12

@app.post("/generate")
async def generate(req: GenerateRequest):
    enhanced = enhance_prompt(req.prompt)
    image = pipe(enhanced, num_inference_steps=req.steps).images[0]
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"image_base64": b64, "prompt_used": enhanced, "engine": "Stable Diffusion v1.5 (GPU)"}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Stable Diffusion v1.5 (GPU)", "device": device}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8013)
