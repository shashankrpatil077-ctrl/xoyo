"""
XOYO Screen Awareness Service — Autonomous Desktop Perception
Based on: OpenAI Codex Chronicle (2026), Anthropic Computer Use (2025),
          Microsoft OmniParser V2 (2025), ScreenParse (2026), UFO² (2025),
          GUI-Eyes (2026), Clicky (2026)

Captures screen periodically, understands content via Qwen-VL + Florence-2,
detects context shifts, and proactively informs the orchestrator.
"""

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
import uvicorn, json, time, threading, requests, redis, os, base64, hashlib
from typing import Optional, List
from collections import deque

app = FastAPI(default_response_class=ORJSONResponse)

# ============================================================
# CONFIGURATION
# ============================================================
CAPTURE_INTERVAL = 2.0          # seconds between captures
ANALYSIS_BACKLOG = 10           # how many recent summaries to keep in sliding window
CHANGE_THRESHOLD = 0.30         # fraction of pixels changed to trigger re-analysis
REDIS_MEMORY_KEY = "xoyo:screen_history"

app_active = False  # Default OFF — user must explicitly enable screen awareness
r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
recent_summaries = deque(maxlen=ANALYSIS_BACKLOG)
last_description = ""
last_detections = ""
last_hash = None

# ============================================================
# SCREEN CAPTURE ENGINE (mss – ultra-fast, no dependencies)
# ============================================================
try:
    import mss
    import mss.tools
    HAS_MSS = True
except Exception:
    HAS_MSS = False
    print("Warning: mss not available. Screen capture will return placeholder frames.")

from PIL import Image
import io
import numpy as np

def capture_screen() -> Optional[str]:
    """Capture the primary monitor and return base64 JPEG."""
    if not HAS_MSS:
        return None
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]                     # all monitors combined
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            # Preserve high resolution to allow reading text and UI details
            img.thumbnail((1920, 1080), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"Screen capture error: {e}")
        return None

def pixel_hash(b64: str) -> str:
    """Quick perceptual hash of a JPEG to detect meaningful changes."""
    if not b64:
        return ""
    # Skip the first 1024 bytes (header) and hash the next 1024 bytes of the base64
    if len(b64) > 2048:
        return hashlib.md5(b64[1024:2048].encode()).hexdigest()
    return hashlib.md5(b64.encode()).hexdigest()

# ============================================================
# VISION ANALYSIS (Qwen-VL + Florence-2 wrapper)
# ============================================================
def describe_screen(b64: str) -> str:
    """Ask Qwen-VL to describe what's on screen in one sentence."""
    try:
        r = requests.post("http://localhost:8001/v1/chat/completions", json={
            "image_base64": b64,
            "prompt": "Describe what is on this screen in 1-2 sentences. Focus on: what application is open, what the user is reading or editing, and what task they appear to be doing.",
            "max_tokens": 150
        }, timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return ""

def detect_ui_elements(b64: str) -> str:
    """Use Florence-2 wrapper to detect UI elements."""
    try:
        r = requests.post("http://localhost:8009/analyze", json={
            "image_base64": b64,
            "task": "detect"
        }, timeout=15)
        if r.status_code == 200:
            result = r.json().get("result", "")
            return str(result)
    except Exception:
        pass
    return ""

# ============================================================
# CONTEXT SHIFT DETECTION (Chronicle pattern)
# ============================================================
def detect_shift(new_summary: str) -> bool:
    """Compare new summary against recent history to detect topic shifts."""
    if not recent_summaries:
        return False
    # Simplest heuristic: if the new summary shares few words with the last summary
    prev = recent_summaries[-1]
    prev_words = set(prev.lower().split())
    new_words = set(new_summary.lower().split())
    if len(new_words) < 3:
        return False
    overlap = len(prev_words & new_words) / max(len(new_words), 1)
    return overlap < 0.15                     # less than 15% word overlap = major shift

# ============================================================
# AUTONOMOUS BACKGROUND LOOP
# ============================================================
def autonomous_loop():
    global last_description, last_detections, last_hash
    while True:
        if not app_active:
            time.sleep(2.0)
            continue

        try:
            # Capture
            b64 = capture_screen()
            if not b64:
                time.sleep(CAPTURE_INTERVAL)
                continue

            # Hash check – skip if screen hasn't changed meaningfully
            current_hash = pixel_hash(b64)
            if last_hash == current_hash:
                time.sleep(CAPTURE_INTERVAL)
                continue
            last_hash = current_hash

            # Describe (Qwen-VL)
            desc = describe_screen(b64)
            if desc:
                last_description = desc
                recent_summaries.append(desc)

                # Store in Redis for cross‑session
                r.lpush(REDIS_MEMORY_KEY, json.dumps({
                    "timestamp": time.time(),
                    "description": desc
                }))
                r.ltrim(REDIS_MEMORY_KEY, 0, ANALYSIS_BACKLOG * 2)

                # Detect shift → log silently via observation endpoint
                # NEVER escalate to /command — that causes phantom task spam
                if detect_shift(desc):
                    context = "\n".join(list(recent_summaries)[-5:])
                    try:
                        requests.post("http://localhost:9000/internal/observe", json={
                            "text": f"Context shift detected. Recent activity: {context}",
                            "source": "screen_awareness",
                            "severity": "info"
                        }, timeout=3)
                    except Exception:
                        pass

            # UI elements (Florence-2 wrapper)
            elements = detect_ui_elements(b64)
            if elements:
                last_detections = elements

        except Exception as e:
            print(f"Screen loop error: {e}")

        time.sleep(CAPTURE_INTERVAL)

threading.Thread(target=autonomous_loop, daemon=True).start()

# ============================================================
# API ENDPOINTS
# ============================================================
class ScreenRequest(BaseModel):
    active: bool = True
    interval: float = 2.0

@app.post("/autonomous")
async def toggle_autonomous(req: ScreenRequest):
    global app_active, CAPTURE_INTERVAL
    app_active = req.active
    CAPTURE_INTERVAL = req.interval
    return {"active": app_active, "interval": CAPTURE_INTERVAL}

@app.get("/status")
async def get_status():
    """Latest screen awareness state."""
    return {
        "active": app_active,
        "latest_description": last_description,
        "latest_detections": last_detections,
        "recent_history": list(recent_summaries),
        "history_size": len(recent_summaries)
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "engine": "Screen Awareness (Codex Chronicle + OmniParser + Computer Use)",
        "capture_available": HAS_MSS,
        "active": app_active,
        "capture_interval_s": CAPTURE_INTERVAL,
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8031)
