#!/usr/bin/env python3
"""
XOYO Voice Pipeline — Alexa-style offline voice assistant
Handles: Wake Word → VAD → STT → Orchestrator → TTS
Hardware target: i3-1115G4, 8 GB RAM, no GPU
"""
import threading, time, os, tempfile, requests
import numpy as np

# ── Configuration ──────────────────────────────────────
ORCHESTRATOR_URL = "http://127.0.0.1:9000/command"
VOCALIZER_URL    = "http://127.0.0.1:8045/speak"
WAKEWORD_URL     = "http://127.0.0.1:8036/status"  # wakeword_server.py runs on 8036, NOT 8050
DEVELOPER_TOKEN  = "xoyo-research-2026"
SILENCE_THRESHOLD_S = 1.5
SAMPLE_RATE = 16000

# ── Silero VAD (loaded once, kept in RAM — tiny model) ──
_silero_model = None

def load_silero():
    global _silero_model
    if _silero_model is None:
        try:
            import torch
            # trust_repo=True required — without it, running as daemon hangs waiting for stdin
            _silero_model, _ = torch.hub.load(
                'snakers4/silero-vad', 'silero_vad', force_reload=False, trust_repo=True)
        except Exception as e:
            print(f"Silero VAD not available: {e}")

def is_speech(audio_chunk: np.ndarray) -> bool:
    """Returns True if Silero VAD detects speech in the chunk."""
    if _silero_model is None:
        # Fallback: energy-based detection
        energy = np.sqrt(np.mean(audio_chunk ** 2))
        return energy > 0.02
    try:
        import torch
        tensor = torch.from_numpy(audio_chunk).float()
        confidence = _silero_model(tensor, SAMPLE_RATE).item()
        return confidence > 0.5
    except Exception:
        return False

# ── STT (faster-whisper primary, Vosk fallback) ──────────
_whisper_model = None

def _transcribe_whisper(audio_path: str) -> str:
    """Primary STT: faster-whisper tiny (int8)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = _whisper_model.transcribe(audio_path, beam_size=1)
    text = " ".join(seg.text for seg in segments).strip()
    return text

def _transcribe_vosk(audio_path: str) -> str:
    """Fallback STT: Vosk (50MB model, supports 20+ languages inc. Hindi)."""
    import wave
    from vosk import Model, KaldiRecognizer
    import json as _json
    model_path = os.path.expanduser("~/.vosk/vosk-model-small-en-us-0.15")
    if not os.path.isdir(model_path):
        # Try Hindi model
        model_path = os.path.expanduser("~/.vosk/vosk-model-small-hi-0.22")
    if not os.path.isdir(model_path):
        return ""
    model = Model(model_path)
    wf = wave.open(audio_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0: break
        if rec.AcceptWaveform(data):
            results.append(_json.loads(rec.Result()).get("text", ""))
    results.append(_json.loads(rec.FinalResult()).get("text", ""))
    wf.close()
    return " ".join(results).strip()

def transcribe(audio_path: str) -> str:
    """Run STT. Tries faster-whisper first, falls back to Vosk."""
    # Try faster-whisper
    try:
        return _transcribe_whisper(audio_path)
    except ImportError:
        print("faster-whisper not installed, trying Vosk...")
    except Exception as e:
        print(f"faster-whisper error: {e}, trying Vosk...")
    # Try Vosk
    try:
        return _transcribe_vosk(audio_path)
    except ImportError:
        print("Vosk not installed. pip install vosk")
    except Exception as e:
        print(f"Vosk error: {e}")
    return ""

def speak(text: str):
    """Non-blocking TTS via progress_vocalizer.py"""
    try:
        requests.post(VOCALIZER_URL, json={"text": text}, timeout=3)
    except Exception:
        pass

# ── Main Voice Loop ─────────────────────────────────────
def voice_loop():
    """
    Runs forever. Listens for wake word via wakeword_server.py,
    then records until silence, then STT, then sends to orchestrator.
    """
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError:
        print("sounddevice/soundfile not installed. Voice pipeline disabled.")
        print("Install with: pip install sounddevice soundfile")
        while True:
            time.sleep(60)
        return

    load_silero()
    speak("XOYO voice assistant is ready. Say Hey XOYO to begin.")

    while True:
        # Wait for wake word signal from wakeword_server.py
        try:
            r = requests.get(WAKEWORD_URL, timeout=1)
            if not r.json().get("detected"):
                time.sleep(0.5)
                continue
        except Exception:
            time.sleep(0.5)
            continue

        speak("Listening.")

        # Record until silence
        audio_chunks = []
        silence_start = None

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
                max_record_time = time.time() + 30  # Safety: max 30s recording
                while time.time() < max_record_time:
                    chunk, _ = stream.read(SAMPLE_RATE // 10)  # 100ms chunks
                    chunk_np = chunk.flatten()
                    audio_chunks.append(chunk_np)

                    if is_speech(chunk_np):
                        silence_start = None
                    else:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > SILENCE_THRESHOLD_S:
                            break
        except Exception as e:
            print(f"Audio recording error: {e}")
            time.sleep(1)
            continue

        if not audio_chunks:
            continue

        # Save audio and transcribe
        audio = np.concatenate(audio_chunks)
        f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = f.name
        f.close()

        try:
            sf.write(tmp_path, audio, SAMPLE_RATE)
            transcript = transcribe(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if not transcript.strip():
            speak("I didn't catch that. Try again.")
            continue

        # Send to orchestrator
        speak(f"Got it. Processing: {transcript[:60]}")
        try:
            r = requests.post(ORCHESTRATOR_URL, json={
                "text": transcript,
                "developer_token": DEVELOPER_TOKEN,
                "source": "user"  # Voice commands are user-initiated
            }, timeout=120)
            response_text = r.json().get("response", "")
            speak(response_text)
        except Exception as e:
            speak(f"Error communicating with XOYO brain: {str(e)[:60]}")


if __name__ == "__main__":
    print("Starting XOYO Voice Pipeline...")
    voice_loop()
