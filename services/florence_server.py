from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
import base64, uvicorn, json, time, asyncio, threading, queue, requests
from typing import Optional

app = FastAPI()

VISION_URL = "http://localhost:8001/v1/chat/completions"

def infer(image_b64: str, task: str = "caption", max_tokens: int = 200) -> dict:
    """Route vision tasks to Qwen-VL-7B with Florence-2-compatible prompts."""
    task_prompts = {
        "caption": "Describe this image in one or two sentences.",
        "detailed_caption": "Describe this image in detail, including all objects, their positions, colors, and the overall scene.",
        "detect": "List every object in this image with their approximate locations.",
        "ocr": "Read and transcribe all text visible in this image.",
        "grounding": "Describe the main subject of this image and where it is located.",
        "open_vocab": "Analyze this image and identify all notable elements.",
    }
    prompt = task_prompts.get(task, task_prompts["caption"])
    t0 = time.time()
    r = requests.post(VISION_URL, json={
        "image_base64": image_b64,
        "prompt": prompt,
        "max_tokens": max_tokens
    }, timeout=60)
    latency_ms = round((time.time() - t0) * 1000, 1)
    if r.status_code == 200:
        text = r.json()["choices"][0]["message"]["content"]
        return {"result": text, "task": task, "latency_ms": latency_ms, "model": "Qwen-VL-7B (via Florence-2 wrapper)"}
    return {"result": "Vision service unavailable", "task": task, "error": r.status_code}

# Autonomous background loop
autonomous_active = False
latest_description = ""
latest_detections = ""
descriptions_queue = queue.Queue(maxsize=100)

def auto_loop():
    global latest_description, latest_detections
    while True:
        if autonomous_active:
            try:
                resp = requests.get("http://localhost:8006/camera", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    b64 = data.get("image_base64", "")
                    if b64:
                        cap = infer(b64, "caption")
                        latest_description = str(cap.get("result", ""))
                        det = infer(b64, "detect")
                        latest_detections = str(det.get("result", ""))
                        descriptions_queue.put({
                            "timestamp": time.time(),
                            "description": latest_description,
                            "detections": latest_detections
                        })
            except Exception as e:
                print(f"Vision loop error: {e}")
        time.sleep(2.0 if autonomous_active else 5.0)

threading.Thread(target=auto_loop, daemon=True).start()

class ImageRequest(BaseModel):
    image_base64: str
    task: str = "caption"
    max_tokens: int = 200

class AutonomousRequest(BaseModel):
    active: bool = True

@app.post("/analyze")
async def analyze(req: ImageRequest):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, infer, req.image_base64, req.task, req.max_tokens)

@app.post("/autonomous")
async def set_autonomous(req: AutonomousRequest):
    global autonomous_active
    autonomous_active = req.active
    return {"autonomous_active": autonomous_active}

@app.get("/autonomous/status")
async def status():
    return {"autonomous_active": autonomous_active, "latest_description": latest_description, "latest_detections": latest_detections}

@app.websocket("/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            if not descriptions_queue.empty():
                item = descriptions_queue.get()
                await websocket.send_json(item)
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"WebSocket closed or error: {e}")
            break

@app.get("/health")
def health():
    return {"status": "ok", "model": "Qwen-VL-7B (Florence-2 compatible wrapper)", "autonomous": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8009)
