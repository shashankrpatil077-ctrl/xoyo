from fastapi import FastAPI
from pydantic import BaseModel
import base64, uvicorn
from PIL import Image
import io

app = FastAPI()

# Global cache to hold the model once loaded
_ml_cache = {}

def get_dino():
    if "model" not in _ml_cache:
        print("[DINO] Lazy loading model and transformers...")
        import torch
        from transformers import AutoImageProcessor, AutoModel
        
        device = "cpu"
        _ml_cache["device"] = device
        _ml_cache["processor"] = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
        # Load with low_cpu_mem_usage if applicable, but this is a small model
        _ml_cache["model"] = AutoModel.from_pretrained("facebook/dinov2-small").to(device)
        _ml_cache["torch"] = torch
        print("[DINO] Load complete.")
    return _ml_cache["processor"], _ml_cache["model"], _ml_cache["device"], _ml_cache["torch"]

class ImageRequest(BaseModel):
    image_base64: str

@app.post("/embed")
async def embed(req: ImageRequest):
    processor, model, device, torch = get_dino()
    img = Image.open(io.BytesIO(base64.b64decode(req.image_base64))).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    emb = outputs.last_hidden_state.mean(dim=1).cpu().numpy().tolist()
    return {"embedding": emb}

@app.get("/health")
def health(): 
    status = "ready" if "model" in _ml_cache else "standby (lazy load pending)"
    return {"status": status, "model": "DINOv2"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8034)

