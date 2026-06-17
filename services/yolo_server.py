from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, base64, cv2, numpy as np

app = FastAPI()

class DummyModel:
    def __init__(self):
        self.names = {0: "button", 1: "text", 2: "image"}
    def __call__(self, img):
        return []

model = DummyModel()

class ImageRequest(BaseModel):
    image_base64: str

@app.post("/detect")
async def detect(req: ImageRequest):
    img_bytes = base64.b64decode(req.image_base64)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return {"detections": []}

@app.get("/health")
def health(): return {"status":"ok","model":"YOLOv8-placeholder"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8014)
