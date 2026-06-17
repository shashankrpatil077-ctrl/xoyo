#!/usr/bin/env python3
"""
XOYO Progress Vocalizer — Premium Neural TTS
Primary: edge-tts (Microsoft Azure Neural Voices — Alexa-quality)
Fallback: Kokoro ONNX → Piper → spd-say
Port: 8045
"""
import sys, subprocess
try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "pydantic", "edge-tts"])
    from fastapi import FastAPI
    from pydantic import BaseModel
import subprocess, os, tempfile, threading, logging, time, asyncio, queue

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.vocalizer")
app = FastAPI()

# ── Voice Configuration ──────────────────────────────────────
EDGE_VOICES = {
    "en": "en-US-JennyNeural",       # Soft, incredibly friendly, and natural female
    "hi": "hi-IN-SwaraNeural",       # Hindi female
    "fr": "fr-FR-DeniseNeural",      # French female
    "ja": "ja-JP-NanamiNeural",      # Japanese female
    "ko": "ko-KR-SunHiNeural",       # Korean female
    "zh": "zh-CN-XiaoxiaoNeural",    # Chinese female
    "es": "es-ES-ElviraNeural",      # Spanish female
    "de": "de-DE-KatjaNeural",       # German female
}

_audio_queue = queue.Queue()

# ── Language detection ────────────────────────────────────────
def _detect_lang(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        pass
    hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    if hindi_chars > len(text) * 0.2:
        return "hi"
    return "en"

# ── PRIMARY: edge-tts (Alexa-quality neural voices) ───────────
def _synthesize_edge_tts(text: str, lang: str) -> bool:
    """Use Microsoft edge-tts for premium neural voice. Zero RAM."""
    log.info(f"Attempting edge-tts. Lang: {lang}")
    try:
        import edge_tts
    except ImportError:
        log.warning("edge-tts not installed. pip install edge-tts")
        return False

    voice = EDGE_VOICES.get(lang, EDGE_VOICES["en"])
    out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            out = f.name

        async def _generate():
            communicate = edge_tts.Communicate(text, voice, rate="+15%")
            await communicate.save(out)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_generate())
        finally:
            loop.close()

        played = False
        for player_cmd in [
            ["mpv", "--no-video", "--really-quiet", out],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", out],
        ]:
            log.info(f"edge-tts trying player: {player_cmd[0]}")
            try:
                res = subprocess.run(player_cmd, timeout=30, capture_output=True)
                if res.returncode == 0:
                    played = True
                    log.info(f"edge-tts executed with {player_cmd[0]}")
                    break
                else:
                    log.warning(f"edge-tts {player_cmd[0]} failed: returncode {res.returncode}")
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                log.warning(f"edge-tts {player_cmd[0]} failed: {e}")
                continue

        if not played:
            log.info("edge-tts falling back to ffmpeg+aplay")
            wav_out = out.replace(".mp3", ".wav")
            try:
                res = subprocess.run(["ffmpeg", "-y", "-i", out, wav_out],
                             capture_output=True, timeout=10)
                if res.returncode == 0:
                    subprocess.run(["aplay", "-q", wav_out], timeout=30)
                    played = True
                    log.info("edge-tts success with ffmpeg+aplay")
                else:
                    log.error(f"ffmpeg failed: {res.stderr}")
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                log.warning(f"edge-tts aplay failed: {e}")
            finally:
                try:
                    os.unlink(wav_out)
                except Exception:
                    pass

        log.info(f"edge-tts returning {played}")
        return played
    except Exception as e:
        log.error(f"edge-tts error: {e}")
        return False
    finally:
        try:
            if out:
                os.unlink(out)
        except Exception:
            pass

# ── FALLBACK 1: Kokoro ONNX ──────────────────────────────
_kokoro = None
KOKORO_MODEL = os.path.expanduser("~/.kokoro/kokoro-v1.0.onnx")
KOKORO_VOICES_FILE = os.path.expanduser("~/.kokoro/voices-v1.0.bin")

KOKORO_VOICE_MAP = {
    "en": "af_heart", "hi": "hi_alpha", "fr": "ff_siwis",
    "ja": "ja_alpha", "ko": "ko_alpha", "zh": "zh_alpha",
}

def _init_kokoro():
    global _kokoro
    if _kokoro is not None:
        return True
    try:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES_FILE)
        log.info("Kokoro TTS loaded")
        return True
    except Exception as e:
        log.debug(f"Kokoro not available: {e}")
    return False

def _synthesize_kokoro(text: str, lang: str) -> bool:
    log.info("Attempting Kokoro TTS...")
    if not _init_kokoro() or _kokoro is None:
        log.warning("Kokoro failed to init.")
        return False
    try:
        import soundfile as sf
        voice = KOKORO_VOICE_MAP.get(lang, "af_heart")
        samples, sr = _kokoro.create(text, voice=voice, speed=1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, samples, sr)
            out = f.name
        log.info("Playing Kokoro audio...")
        try:
            res = subprocess.run(["aplay", "-q", out], timeout=30)
            if res.returncode == 0:
                log.info("Kokoro finished playing.")
                return True
            return False
        finally:
            try:
                os.unlink(out)
            except Exception:
                pass
    except Exception as e:
        log.error(f"Kokoro error: {e}")
        return False

# ── FALLBACK 2: Piper ────────────────────────────────────
PIPER_MODEL = os.path.expanduser("~/.piper/en_US-lessac-medium.onnx")
PIPER_CONFIG = os.path.expanduser("~/.piper/en_US-lessac-medium.onnx.json")

def _synthesize_piper(text: str) -> bool:
    log.info("Attempting Piper TTS...")
    out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        result = subprocess.run(
            ["piper", "--model", PIPER_MODEL, "--config", PIPER_CONFIG, "--output_file", out],
            input=text, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            res = subprocess.run(["aplay", "-q", out], timeout=30)
            if res.returncode == 0:
                return True
    except Exception as e:
        log.error(f"Piper error: {e}")
    finally:
        try:
            if out:
                os.unlink(out)
        except Exception:
            pass
    return False

# ── FALLBACK 3: spd-say (robotic but always works) ───────────
def _synthesize_spdsay(text: str) -> bool:
    try:
        res = subprocess.run(["spd-say", "-t", "female1", "-r", "10", "--", text], timeout=15)
        return res.returncode == 0
    except Exception as e:
        log.error(f"spd-say error: {e}")
    return False

# ── Main speech worker ───────────────────────────────────────
def _audio_worker():
    import re
    while True:
        text = _audio_queue.get()
        try:
            lang = _detect_lang(text)
            
            # Phonetic replacement for XOYO
            speak_text = re.sub(r'(?i)\bxoyo\b', 'Zoyo', text)
            speak_text = speak_text.replace('[XOYO]', '') # Remove bracketed prefix if present
            
            # We exclusively use edge-tts to maintain XOYO's soft, natural persona.
            # If it fails, we do NOT fall back to older robotic voices.
            success = _synthesize_edge_tts(speak_text, lang)
            if not success:
                log.warning("edge-tts failed. Falling back to Kokoro.")
                success = _synthesize_kokoro(speak_text, lang)
                if not success:
                    log.warning("Kokoro failed. Falling back to Piper.")
                    success = _synthesize_piper(speak_text)
                    if not success:
                        log.warning("Piper failed. Falling back to spd-say.")
                        _synthesize_spdsay(speak_text)
        except Exception as e:
            log.error(f"TTS worker error: {e}")
        finally:
            _audio_queue.task_done()

_worker_thread = threading.Thread(target=_audio_worker, daemon=True)
_worker_thread.start()

class SpeakRequest(BaseModel):
    text: str
    priority: str = "normal"
    voice: str = ""
    lang: str = ""

@app.post("/speak")
async def speak(req: SpeakRequest):
    import re
    sentences = re.split(r'(?<=[.!?])\s+', req.text)
    for s in sentences:
        if s.strip():
            _audio_queue.put(s.strip())
    return {"status": "queued", "spoken": req.text[:100], "lang": _detect_lang(req.text),
            "engine": "edge-tts (primary)"}

@app.post("/clear")
def clear_audio():
    import subprocess
    with _audio_queue.mutex:
        _audio_queue.queue.clear()
    subprocess.run(["pkill", "-9", "-f", "mpv|ffplay|aplay|ffmpeg"], capture_output=True)
    return {"status": "cleared"}

@app.get("/voices")
def list_voices():
    return {"edge_tts_voices": EDGE_VOICES, "kokoro_available": _init_kokoro()}

@app.get("/health")
def health():
    return {"status": "ok", "service": "progress_vocalizer", "port": 8045,
            "primary_engine": "edge-tts", "multilingual": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8045)
