#!/usr/bin/env python3
"""
XOYO Image Generator — CPU-optimized via Stable Diffusion + OpenVINO.
Avoids Ollama FLUX (requires Apple MLX). Uses diffusers with OpenVINO
backend on Intel i3 for ~15-30s/image at 512x512.
Port: 8042
"""
from fastapi import FastAPI
from pydantic import BaseModel
import os, time, logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.image_gen")
app = FastAPI()

_pipe = None

def _load_pipeline():
    """Load SD pipeline with OpenVINO acceleration. Falls back to CPU diffusers."""
    global _pipe
    if _pipe is not None:
        return _pipe
    # Strategy 1: OpenVINO (fastest on Intel)
    try:
        from optimum.intel import OVStableDiffusionPipeline
        model_id = "OpenVINO/stable-diffusion-2-1-ov"
        _pipe = OVStableDiffusionPipeline.from_pretrained(
            model_id, export=False, device="CPU")
        log.info("Loaded OpenVINO SD 2.1 pipeline")
        return _pipe
    except ImportError:
        log.warning("optimum-intel not installed")
    except Exception as e:
        log.warning(f"OpenVINO load failed: {e}")
    # Strategy 2: Plain diffusers on CPU (slow but works)
    try:
        import torch
        from diffusers import StableDiffusionPipeline
        _pipe = StableDiffusionPipeline.from_pretrained(
            "stabilityai/sd-turbo", torch_dtype=torch.float32)
        _pipe = _pipe.to("cpu")
        log.info("Loaded diffusers SD-Turbo pipeline (CPU)")
        return _pipe
    except Exception as e:
        log.warning(f"Diffusers load failed: {e}")
    return None

class ImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = "blurry, low quality, distorted"
    width: int = 512
    height: int = 512
    steps: int = 4
    output_dir: str = os.path.expanduser("~/xoyo/output/images")

@app.post("/generate")
async def generate_image(req: ImageRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    filename = f"xoyo_img_{int(time.time())}.png"
    output_path = os.path.join(req.output_dir, filename)

    pipe = _load_pipeline()
    if pipe is None:
        return {"status": "error",
                "message": "No image model available. Install: pip install optimum-intel openvino diffusers"}
    try:
        image = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            width=req.width, height=req.height,
            num_inference_steps=req.steps,
        ).images[0]
        image.save(output_path)
        return {"status": "ok", "path": output_path, "size": f"{req.width}x{req.height}"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}

@app.get("/health")
def health():
    return {"status": "ok", "service": "image_generator", "port": 8042,
            "pipeline_loaded": _pipe is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8042)
