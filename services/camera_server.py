from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mediapipe as mp
import cv2
import numpy as np
import uvicorn
import base64

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

mp_holistic = mp.solutions.holistic
holistic = mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5)

cap = None  # lazy init to avoid crash on headless servers

def get_camera():
    global cap
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(0)
    return cap

@app.get("/camera")
async def camera_state():
    cam = get_camera()
    if cam is None or not cam.isOpened():
        return {"error": "No webcam available", "face_detected": False}
    ret, frame = cam.read()
    if not ret:
        return {"error": "No webcam frame"}
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = holistic.process(rgb)
    data = {
        "face_detected": results.face_landmarks is not None,
        "left_hand_detected": results.left_hand_landmarks is not None,
        "right_hand_detected": results.right_hand_landmarks is not None,
        "pose_detected": results.pose_landmarks is not None,
        "emotion": "neutral"
    }
    _, buffer = cv2.imencode('.jpg', frame)
    data["snapshot_base64"] = base64.b64encode(buffer).decode()
    return data

@app.get("/health")
def health():
    cam = get_camera()
    return {"status":"ok","camera_available": cam is not None and cam.isOpened()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)
