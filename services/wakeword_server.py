"""
XOYO Wake‑Word Detection Service — “XOYO, …”
Based on: openWakeWord (2024‑2025), ONNX runtime, self‑supervised verifier training.

Continuously listens for the wake word, then activates the voice pipeline
by sending the following audio to the orchestrator’s /voice endpoint.
"""

from fastapi import FastAPI, UploadFile, File
import uvicorn, threading, time, requests, os, json, io, struct, wave, tempfile
import numpy as np
import warnings
warnings.filterwarnings("ignore")

app = FastAPI()

# ============================================================
# CONFIG
# ============================================================
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.2          # seconds per audio chunk
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
WAKE_WORD = "xoyo"
CUSTOM_MODEL_PATH = "/home/shashank/xoyo/workspace/xoyo_wakeword.onnx"
TRAINING_DIR = "/home/shashank/xoyo/workspace/wakeword_training"
os.makedirs(TRAINING_DIR, exist_ok=True)

VLLM_URL = "http://localhost:9000/command"          # where to send transcribed commands
WHISPER_URL = "http://localhost:8002/stt"

wakeword_active = True
use_custom_model = os.path.exists(CUSTOM_MODEL_PATH)

# ============================================================
# 1. LOAD WAKE‑WORD MODEL (LAZY)
# ============================================================
oww_model = None
_oww_initialized = False

def get_oww_model():
    global oww_model, _oww_initialized
    if not _oww_initialized:
        try:
            import openwakeword
            from openwakeword.model import Model
            if use_custom_model:
                oww_model = Model(wakeword_models=[CUSTOM_MODEL_PATH], inference_framework="onnx")
                print(f"Loaded custom wake‑word model: {CUSTOM_MODEL_PATH}")
            else:
                oww_model = Model(wakeword_models=[WAKE_WORD], inference_framework="onnx")
                print(f"Using built‑in model for '{WAKE_WORD}'")
        except Exception as e:
            print(f"openWakeWord not available ({e}); falling back to simple energy‑based trigger")
            oww_model = None
        _oww_initialized = True
    return oww_model

# ============================================================
# 2. MICROPHONE ACCESS
# ============================================================
try:
    import pyaudio
    audio = pyaudio.PyAudio()
    mic_stream = audio.open(format=pyaudio.paInt16, channels=1,
                            rate=SAMPLE_RATE, input=True,
                            frames_per_buffer=CHUNK_SAMPLES)
    mic_available = True
except Exception as e:
    print(f"Microphone not available: {e}")
    mic_available = False

# ============================================================
# 3. MAIN LISTENING LOOP
# ============================================================
def listening_loop():
    """Continuously reads microphone, runs wake‑word detection, triggers voice pipeline."""
    global wakeword_active
    last_trigger_time = 0
    post_trigger_audio = []           # audio collected after the trigger
    TRIGGER_COOLDOWN = 2.0            # seconds before next trigger
    POST_TRIGGER_DURATION = 5.0       # seconds to capture after wake word

    while True:
        if not mic_available:
            time.sleep(0.5)
            continue

        try:
            chunk = mic_stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
            if not wakeword_active:
                continue
            audio_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            time.sleep(0.2)
            continue

        try:
            # Detect wake word
            detected = False
            model = get_oww_model()
            if model is not None:
                prediction = model.predict(audio_np)
                for mdl in model.prediction_buffer.keys():
                    scores = model.prediction_buffer[mdl][-5:]  # last 5 chunks
                    if len(scores) > 0 and max(scores) > 0.5:
                        detected = True
                        break
            else:
                # Simple energy threshold fallback (not ideal, but works as last resort)
                # Threshold 0.15: raised from 0.05 to avoid false triggers on ambient noise/fan hum
                energy = np.sqrt(np.mean(audio_np**2))
                detected = energy > 0.15
        except Exception as e:
            print(f"Wake-word analysis error: {e}")
            continue

        now = time.time()
        if detected and (now - last_trigger_time) > TRIGGER_COOLDOWN:
            last_trigger_time = now
            print("🎤 Wake word detected! Capturing command…")
            # Capture the next few seconds of audio
            command_audio = []
            start = time.time()
            while (time.time() - start) < POST_TRIGGER_DURATION:
                try:
                    chunk = mic_stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                    command_audio.append(chunk)
                except Exception:
                    break
            # Save to WAV and send to Whisper
            raw_audio = b''.join(command_audio)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                with wave.open(tmp, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(raw_audio)
                tmp_path = tmp.name

            # Send to orchestrator via /voice
            _stt_disabled_backoff = 0  # reset per trigger
            try:
                with open(tmp_path, "rb") as f:
                    resp = requests.post(f"http://localhost:9000/voice",
                                         files={"file": f}, timeout=30)
                if resp.status_code == 200:
                    resp_text = resp.json().get('response', '')
                    print(f"✅ XOYO responded: {resp_text[:100]}")
                    # Circuit breaker: if STT is disabled, back off 60s to avoid infinite loop
                    if "Local STT is disabled" in resp_text:
                        print("⚠️  STT disabled — wakeword backing off 5s to avoid loop")
                        time.sleep(5)
            except Exception as e:
                print(f"Voice pipeline error: {e}")
            finally:
                os.unlink(tmp_path)

        time.sleep(0.1)

threading.Thread(target=listening_loop, daemon=True).start()

# ============================================================
# 4. SELF‑TRAINING ENDPOINT (upload a few .wav files of you saying “XOYO”)
# ============================================================
@app.post("/train")
def train_wakeword(files: list[UploadFile] = File(...)):
    """Upload 3‑5 short .wav files of yourself saying 'XOYO', and the service
       will train a personalised wake‑word model using openWakeWord's verifier."""
    global use_custom_model, oww_model
    positives = []
    for f in files:
        data = f.file.read()
        positives.append(data)

    if len(positives) < 3:
        return {"error": "Need at least 3 positive samples", "uploaded": len(positives)}

    # Save positive clips
    for i, clip in enumerate(positives):
        with open(f"{TRAINING_DIR}/positive_{i}.wav", "wb") as wf:
            wf.write(clip)

    # Train using openWakeWord's built‑in utility
    try:
        from openwakeword.utils import train_custom_verifier
        train_custom_verifier(
            positive_clips=[f"{TRAINING_DIR}/positive_{i}.wav" for i in range(len(positives))],
            negative_clips=[],           # we can add room noise later
            output_model_path=CUSTOM_MODEL_PATH,
            wake_word=WAKE_WORD,
            epochs=10,
            steps_per_epoch=20
        )
        if oww_model:
            oww_model.reset()
            oww_model.model = openwakeword.Model(wakeword_models=[CUSTOM_MODEL_PATH], inference_framework="onnx")
        use_custom_model = True
        return {"status": "trained", "model_path": CUSTOM_MODEL_PATH}
    except Exception as e:
        return {"error": f"Training failed ({e}). Using built‑in model instead."}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "openWakeWord + self‑training verifier",
        "model": "custom" if use_custom_model else "built‑in",
        "mic_available": mic_available,
        "autonomous": True
    }

@app.post("/activate")
async def activate():
    global wakeword_active
    wakeword_active = True
    return {"wakeword_active": True}

@app.post("/deactivate")
async def deactivate():
    global wakeword_active
    wakeword_active = False
    return {"wakeword_active": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8036)
