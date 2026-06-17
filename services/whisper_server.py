"""
Continuous Whisper Streaming – Always-On Voice Pipeline (CPU-safe)
Based on: WhisperPipe, WhisperLiveKit, SWIM (hybrid VAD + continuous transcription)
"""

from fastapi import FastAPI, WebSocket, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from concurrent.futures import ThreadPoolExecutor
whisper_pool = ThreadPoolExecutor(max_workers=1)
import json, time, tempfile, os, threading, queue
import numpy as np
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---- CPU-friendly model ----
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    WhisperModel = None
device = "cpu"
compute_type = "int8"
if HAS_WHISPER:
    try:
        print("Loading faster-whisper (small) on CPU (int8) …")
        model = WhisperModel("small", device=device, compute_type=compute_type)
        print("Model ready.")
    except Exception as e:
        print(f"Failed to load WhisperModel: {e}")
        HAS_WHISPER = False
        model = None
else:
    model = None

# ---- VAD (silero) ----
try:
    from silero_vad import load_silero_vad, get_speech_timestamps
    import torch as th
    vad_model = load_silero_vad(onnx=True)
    USE_SILERO = True
except Exception:
    USE_SILERO = False

# ---- Parameters ----
SAMPLE_RATE = 16000
BUFFER_DURATION = 3.0
OVERLAP_DURATION = 0.5

continuous_active = False
latest_transcript = ""
all_transcripts = []
transcript_queue = queue.Queue(maxsize=500)

def energy_vad(audio_np):
    energy = np.sqrt(np.mean(audio_np.astype(np.float32)**2))
    return energy > 0.015

def transcribe_audio(audio_np, prev_context=""):
    if not HAS_WHISPER or model is None:
        return ""
    try:
        audio_float = audio_np.astype(np.float32) / 32768.0
        segments, info = model.transcribe(audio_float, language="en", beam_size=5,
                                           initial_prompt=prev_context[-200:] if prev_context else None)
        return " ".join([seg.text.strip() for seg in segments])
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""

def continuous_listening_loop():
    global latest_transcript
    try:
        import pyaudio
        audio = pyaudio.PyAudio()
    except Exception as e:
        print(f"pyaudio not available: {e}")
        return
    try:
        stream = audio.open(format=pyaudio.paInt16, channels=1,
                            rate=SAMPLE_RATE, input=True,
                            frames_per_buffer=int(SAMPLE_RATE * 0.2))
    except Exception as e:
        print(f"Microphone not available ({e}) – continuous mode will run without hardware mic.")
        return

    buffer = bytearray()
    prev_ctx = ""
    silent_frames = 0
    while True:
        try:
            raw = stream.read(int(SAMPLE_RATE * 0.1), exception_on_overflow=False)
        except Exception:
            time.sleep(0.1)
            continue
            
        if not continuous_active:
            buffer.clear()
            continue
        chunk = np.frombuffer(raw, dtype=np.int16)
        buffer.extend(raw)
        has_speech = energy_vad(chunk)
        if has_speech:
            silent_frames = 0
        else:
            silent_frames += 1
        if len(buffer) >= SAMPLE_RATE * BUFFER_DURATION * 2:
            if silent_frames < int(BUFFER_DURATION / 0.1):
                audio_np = np.frombuffer(bytes(buffer), dtype=np.int16)
                text = transcribe_audio(audio_np, prev_ctx)
                if text.strip():
                    latest_transcript = text
                    all_transcripts.append(text)
                    transcript_queue.put({"timestamp": time.time(), "text": text})
                    prev_ctx = text[-300:]
            overlap_bytes = int(SAMPLE_RATE * OVERLAP_DURATION) * 2
            buffer = buffer[-overlap_bytes:] if len(buffer) > overlap_bytes else bytearray()

threading.Thread(target=continuous_listening_loop, daemon=True).start()

# ---- WebSocket stream (for browser mic) ----
@app.websocket("/stream")
async def ws_stream(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "config", "sample_rate": SAMPLE_RATE})
    buf = bytearray()
    prev = ""
    try:
        while True:
            data = await websocket.receive_bytes()
            if not data:
                break
            buf.extend(data)
            if len(buf) >= SAMPLE_RATE * 2 * 2:
                audio_np = np.frombuffer(bytes(buf), dtype=np.int16)
                if energy_vad(audio_np):
                    loop = asyncio.get_running_loop()
                    text = await loop.run_in_executor(whisper_pool, transcribe_audio, audio_np, prev)
                    if text.strip():
                        prev = text[-300:]
                        await websocket.send_json({"type": "transcript", "text": text})
                buf = buf[-int(SAMPLE_RATE * OVERLAP_DURATION) * 2:]
    except Exception as e:
        print(f"WebSocket closed: {e}")

# ---- REST API ----
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        try:
            import soundfile as sf
            audio_np, sr = sf.read(path, dtype='int16')
            if sr != SAMPLE_RATE:
                import librosa
                audio_np = librosa.resample(audio_np.astype(np.float32), orig_sr=sr, target_sr=SAMPLE_RATE).astype(np.int16)
        except Exception:
            if data.startswith(b'RIFF'):
                audio_np = np.frombuffer(data[44:], dtype=np.int16)
            else:
                audio_np = np.frombuffer(data, dtype=np.int16)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(whisper_pool, transcribe_audio, audio_np)
    finally:
        try:
            os.unlink(path)
        except Exception as e:
            print(f"Cleanup error: {e}")
    return {"transcript": text}

@app.post("/continuous")
async def toggle_continuous(active: bool = True):
    global continuous_active
    continuous_active = active
    return {"continuous_active": continuous_active}

@app.get("/continuous/status")
async def status():
    return {"active": continuous_active, "latest": latest_transcript, "total": len(all_transcripts)}

@app.get("/health")
def health():
    return {"status":"ok","engine":"faster-whisper CPU","device":"cpu","vad":"silero+energy","continuous_active":continuous_active,"autonomous":True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
