"""
XOYO Neural TTS – Production Voice Output
Based on: Piper TTS (VITS model optimized with ONNX Runtime).
Provides fast, natural voice synthesis fully offline.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn, subprocess, tempfile, os, base64, hashlib, sys

app = FastAPI()

# ---- CONFIGURATION ----
VOICE_MODEL = "en_US-lessac-medium"  # Calm, authoritative voice, Jarvis-like
VOICE_DIR = "/home/shashank/.local/share/piper-tts/voices"

os.makedirs(VOICE_DIR, exist_ok=True)
if not os.path.exists(os.path.join(VOICE_DIR, f"{VOICE_MODEL}.onnx")):
    print(f"Downloading voice model {VOICE_MODEL}...")
    subprocess.run(
        ["python3", "-m", "piper.download_voices", "--download-dir", VOICE_DIR, VOICE_MODEL],
        check=True
    )

# ---- HELPER ----
def synthesize(text: str) -> str:
    """Convert text to speech and return base64 WAV."""
    if not text.strip():
        return ""
    # Piper expects input as a pipe-friendly command
    try:
        piper_bin = os.path.join(os.path.dirname(sys.executable), "piper")
        if not os.path.exists(piper_bin):
            import shutil
            piper_bin = shutil.which("piper") or "piper"

        result = subprocess.run(
            [piper_bin, "--model", VOICE_MODEL, "--output_file", "-", "--data-dir", VOICE_DIR],
            input=text.encode(),
            capture_output=True,
            timeout=30
        )
        if result.returncode != 0:
            raise Exception(f"Piper error: {result.stderr.decode()}")
        return base64.b64encode(result.stdout).decode()
    except FileNotFoundError:
        print("TTS Error: 'piper' command not found. Ensure Piper TTS is installed and in PATH.")
        raise Exception("Piper TTS binary not found")
    except Exception as e:
        print(f"TTS Error: {e}")
        raise

class SpeakRequest(BaseModel):
    text: str

@app.post("/tts")
def speak(req: SpeakRequest):
    """Synthesize speech from text."""
    try:
        audio_b64 = synthesize(req.text)
        if audio_b64:
            return {"audio_base64": audio_b64, "format": "wav", "voice": VOICE_MODEL}
        raise HTTPException(status_code=500, detail="TTS synthesis returned empty audio")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "Piper TTS (VITS Neural Voice)",
        "voice": VOICE_MODEL,
        "autonomous": True
    }

if __name__ == "__main__":
    uvicorn.run(app, host="::", port=8003)
