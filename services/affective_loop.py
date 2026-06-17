"""
Affective Loop — Emotion‑Driven Adaptive Interface
Based on: EAAUI (Mar 2026, 89.6% accuracy, 21% faster tasks), RAGE‑Fusion (Mar 2026),
          MOON Framework (2025), Psycho‑Physiological Computing (2026)

Architecture: Multi‑modal emotion detection → Reliability‑gated fusion → PID controller →
               Adaptive outputs (hologram color, speech rate, information density).
Fully autonomous background loop: observe, model, optimize, nurture.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, json, time, threading, requests, redis
from typing import Optional

app = FastAPI()

# ============================================================
# PERSISTENT EMOTION STATE
# ============================================================
current_emotion = "neutral"
current_valence = 0.5      # 0 = negative, 1 = positive
current_arousal = 0.5      # 0 = calm, 1 = excited
emotion_confidence = 0.7

EMOTION_MAP = {
    "happy":      {"valence": 0.85, "arousal": 0.75},
    "excited":    {"valence": 0.90, "arousal": 0.90},
    "surprised":  {"valence": 0.70, "arousal": 0.80},
    "neutral":    {"valence": 0.50, "arousal": 0.40},
    "calm":       {"valence": 0.60, "arousal": 0.20},
    "sad":        {"valence": 0.20, "arousal": 0.30},
    "angry":      {"valence": 0.10, "arousal": 0.90},
    "fearful":    {"valence": 0.15, "arousal": 0.85},
    "disgust":    {"valence": 0.10, "arousal": 0.70},
}

# ============================================================
# PID CONTROLLER (EAAUI — target optimal flow state)
# ============================================================
TARGET_VALENCE = 0.75
TARGET_AROUSAL = 0.55
pid_integral_v = 0.0
pid_integral_a = 0.0

def pid_update(valence, arousal):
    """Compute adaptive parameters from current emotional state using PID."""
    global pid_integral_v, pid_integral_a

    # Proportional error
    error_v = TARGET_VALENCE - valence
    error_a = TARGET_AROUSAL - arousal

    # Integral (dampened)
    pid_integral_v = 0.9 * pid_integral_v + 0.1 * error_v
    pid_integral_a = 0.9 * pid_integral_a + 0.1 * error_a

    # Derivative (simplified: difference from last)
    derivative_v = -valence   # rough
    derivative_a = -arousal

    # PID outputs
    kp, ki, kd = 0.4, 0.1, 0.05
    output_v = kp * error_v + ki * pid_integral_v + kd * derivative_v
    output_a = kp * error_a + ki * pid_integral_a + kd * derivative_a

    # Map to interface parameters
    # Hologram colour: warm (low valence) → cool (high valence)
    hue = 0.55 + output_v * 0.15          # range ~ 0.4-0.7 (cyan-blue)
    saturation = 0.8
    lightness = 0.5 + output_a * 0.1      # brighter when excited
    hologram_color = f"hsl({int(hue*360)}, {int(saturation*100)}%, {int(lightness*100)}%)"

    # Speech rate: slow down when user is confused/stressed
    speech_rate = max(0.7, min(1.5, 1.0 + output_a * 0.2 - output_v * 0.1))

    # Information density: simplify when confused, deepen when engaged
    if output_v < -0.1:   # low valence → simplify
        detail_level = "simple"
    elif output_v > 0.1:
        detail_level = "deep"
    else:
        detail_level = "moderate"

    return {
        "hologram_color": hologram_color,
        "speech_rate": round(speech_rate, 2),
        "detail_level": detail_level,
        "valence_error": round(error_v, 3),
        "arousal_error": round(error_a, 3),
        "pid_integrals": (round(pid_integral_v, 3), round(pid_integral_a, 3))
    }

# ============================================================
# RELIABILITY‑GATED MULTI‑MODAL FUSION (RAGE‑Fusion)
# ============================================================
def fetch_camera_emotion():
    """Get emotion from the camera service (port 8006)."""
    try:
        r = requests.get("http://localhost:8006/health", timeout=2)
        if r.status_code == 200:
            data = r.json()
            if data.get("mediapipe_available") and data.get("camera_available"):
                # In full implementation, would call /camera endpoint to get actual emotion
                return {"emotion": "neutral", "confidence": 0.6}
        return None
    except Exception:
        return None

def fetch_prosody_emotion():
    """Get emotion from the voice prosody service (port 8023)."""
    try:
        r = requests.get("http://localhost:8023/health", timeout=2)
        if r.status_code == 200:
            # The prosody service requires an audio file; we'd use the latest from continuous whisper.
            # For autonomous mode, this returns None unless recent audio is available.
            return None
        return None
    except Exception:
        return None

def fetch_text_sentiment():
    """Get sentiment from recent transcripts via the orchestrator (port 9000)."""
    try:
        r = requests.get("http://localhost:8002/continuous/status", timeout=2)
        if r.status_code == 200:
            data = r.json()
            latest = data.get("latest", "")
            if latest:
                from textblob import TextBlob
                blob = TextBlob(latest)
                polarity = (blob.sentiment.polarity + 1) / 2   # map [-1,1] → [0,1]
                return {"valence": polarity, "confidence": 0.7}
        return None
    except Exception:
        return None

def fuse_emotions():
    """RAGE‑Fusion: combine available modalities with reliability weighting."""
    sources = []
    cam = fetch_camera_emotion()
    if cam:
        sources.append({"source": "camera", "emotion": cam["emotion"], "confidence": cam.get("confidence", 0.6)})
    pros = fetch_prosody_emotion()
    if pros:
        sources.append({"source": "prosody", **pros})
    text = fetch_text_sentiment()
    if text:
        sources.append({"source": "text", **text})

    if not sources:
        return EMOTION_MAP["neutral"]

    # Weighted average of valence/arousal
    total_valence = 0.0
    total_arousal = 0.0
    total_weight = 0.0
    for src in sources:
        em = src.get("emotion", "neutral")
        conf = src.get("confidence", 0.6)
        mapping = EMOTION_MAP.get(em, EMOTION_MAP["neutral"])
        total_valence += mapping["valence"] * conf
        total_arousal += mapping["arousal"] * conf
        total_weight += conf

    if total_weight > 0:
        return {"valence": total_valence / total_weight, "arousal": total_arousal / total_weight}
    return EMOTION_MAP["neutral"]

# ============================================================
# AUTONOMOUS BACKGROUND LOOP (MOON – observe→model→optimize→nurture)
# ============================================================
adaptive_state = {"hologram_color": "#00ccff", "speech_rate": 1.0, "detail_level": "moderate"}
autonomous_active = True

def autonomous_loop():
    """Runs continuously: observe emotion, model the best response, optimize interface, nurture over time."""
    global current_valence, current_arousal, adaptive_state
    while True:
        if autonomous_active:
            try:
                vitals = requests.get("http://localhost:8044/vitals", timeout=2).json()
                if vitals.get("cpu_percent", 0) > 85 or vitals.get("ram_percent", 0) > 90:
                    print("Affective Loop: System under load. Yielding.")
                    time.sleep(10.0)
                    continue
            except Exception:
                pass
                
            try:
                # Observe
                fused = fuse_emotions()
                current_valence = 0.8 * current_valence + 0.2 * fused["valence"]    # EMA smoothing
                current_arousal = 0.8 * current_arousal + 0.2 * fused["arousal"]

                # Model → Optimize (PID)
                new_state = pid_update(current_valence, current_arousal)

                # Nurture: store in Redis for the orchestrator/frontend
                adaptive_state = {
                    "hologram_color": new_state["hologram_color"],
                    "speech_rate": new_state["speech_rate"],
                    "detail_level": new_state["detail_level"],
                    "valence": round(current_valence, 3),
                    "arousal": round(current_arousal, 3)
                }
                try:
                    r = redis.Redis(host="localhost", port=6379, db=0)
                    r.set("xoyo:affective_state", json.dumps(adaptive_state))
                except Exception:
                    pass
            except Exception as e:
                print(f"Affective loop error: {e}")
        time.sleep(2.0)   # update every 2 seconds

threading.Thread(target=autonomous_loop, daemon=True).start()

# ============================================================
# API ENDPOINTS
# ============================================================
class EmotionUpdate(BaseModel):
    emotion: str = "neutral"
    confidence: float = 0.8

@app.post("/emotion")
async def set_emotion(req: EmotionUpdate):
    """Manually set emotion (for demo/testing)."""
    global current_valence, current_arousal
    mapping = EMOTION_MAP.get(req.emotion, EMOTION_MAP["neutral"])
    current_valence = mapping["valence"]
    current_arousal = mapping["arousal"]
    return {"set": req.emotion, "valence": current_valence, "arousal": current_arousal}

@app.get("/state")
async def get_state():
    """Current adaptive interface state."""
    return {
        "emotion": {"valence": round(current_valence, 3), "arousal": round(current_arousal, 3)},
        "adaptive": adaptive_state,
        "autonomous_active": autonomous_active
    }

@app.post("/autonomous")
async def toggle_autonomous(active: bool = True):
    global autonomous_active
    autonomous_active = active
    return {"autonomous_active": autonomous_active}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "EAAUI + RAGE-Fusion + MOON Affective Loop",
        "valence": round(current_valence, 3),
        "arousal": round(current_arousal, 3),
        "autonomous": autonomous_active,
        "pid_targets": {"valence": TARGET_VALENCE, "arousal": TARGET_AROUSAL}
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8030)
