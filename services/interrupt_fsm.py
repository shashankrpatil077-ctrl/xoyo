#!/usr/bin/env python3
"""
XOYO Interrupt FSM — State machine for voice interaction flow control.
Manages: idle → listening → thinking → speaking with barge-in support.
Port: 8052
"""
from fastapi import FastAPI
from pydantic import BaseModel
import time, logging, threading, requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.interrupt_fsm")
app = FastAPI()

# Redis with fallback
try:
    import redis
    rc = redis.Redis(host='localhost', port=6379, decode_responses=True)
    rc.ping()
except Exception:
    class _FR:
        def __init__(self): self._d = {}
        def set(self, k, v, **kw): self._d[k] = v
        def get(self, k): return self._d.get(k)
        def publish(self, ch, msg): pass
    rc = _FR()

VALID_STATES = {"idle", "listening", "thinking", "speaking"}

# Allowed transitions: (from_state) → set(to_states)
TRANSITIONS = {
    "idle":      {"listening", "thinking", "speaking", "idle"},
    "listening": {"thinking", "idle", "speaking", "listening"},
    "thinking":  {"speaking", "idle", "listening", "thinking"},
    "speaking":  {"listening", "idle", "thinking", "speaking"},
}

class StateTransition(BaseModel):
    to_state: str
    reason: str = ""

class BargeInRequest(BaseModel):
    force: bool = False

def _get_state() -> str:
    return rc.get("interrupt:state") or "idle"

def _toggle_mics(active: bool):
    if not active:
        try:
            requests.post("http://localhost:8036/deactivate", timeout=2)
        except Exception as e:
            log.warning(f"Failed to deactivate wakeword: {e}")
        try:
            requests.post("http://localhost:8002/continuous?active=false", timeout=2)
        except Exception as e:
            log.warning(f"Failed to mute whisper: {e}")
        log.info("Muted microphones (speaking state).")
    else:
        try:
            requests.post("http://localhost:8036/activate", timeout=2)
        except Exception as e:
            log.warning(f"Failed to activate wakeword: {e}")
        try:
            requests.post("http://localhost:8002/continuous?active=true", timeout=2)
        except Exception as e:
            log.warning(f"Failed to unmute whisper: {e}")
        log.info("Un-muted microphones (exited speaking state).")

def _set_state(state: str, reason: str = ""):
    old = _get_state()
    rc.set("interrupt:state", state)
    rc.set("interrupt:last_transition", f"{old}→{state}")
    rc.set("interrupt:transition_ts", str(time.time()))
    rc.set("interrupt:transition_reason", reason)
    log.info(f"FSM: {old} → {state} ({reason})")
    rc.publish("xoyo:fsm", f"{state}:{reason}")

    if old != "speaking" and state == "speaking":
        threading.Thread(target=_toggle_mics, args=(False,), daemon=True).start()
    elif old == "speaking" and state != "speaking":
        threading.Thread(target=_toggle_mics, args=(True,), daemon=True).start()

# Initialize
if not rc.get("interrupt:state"):
    _set_state("idle", "boot")

@app.get("/state")
def get_state():
    return {
        "state": _get_state(),
        "last_transition": rc.get("interrupt:last_transition") or "none",
        "transition_ts": rc.get("interrupt:transition_ts") or "0",
        "barge_in_active": rc.get("interrupt:barge_in") == "1",
    }

@app.post("/transition")
def transition(req: StateTransition):
    """Transition to a new state. Validates against allowed transitions."""
    current = _get_state()
    target = req.to_state.lower()
    if target not in VALID_STATES:
        return {"error": f"Invalid state: {target}", "valid": list(VALID_STATES)}
    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        return {"error": f"Cannot transition from {current} to {target}",
                "allowed": list(allowed)}
    _set_state(target, req.reason)
    return {"status": "ok", "from": current, "to": target}

@app.post("/barge_in")
def barge_in(req: BargeInRequest):
    """
    Barge-in: interrupt current speech and jump to listening.
    Called by wakeword_server when wake word detected during speaking.
    """
    current = _get_state()
    if current == "speaking" or req.force:
        rc.set("interrupt:barge_in", "1")
        _set_state("listening", "barge-in: wake word detected during speech")
        try:
            requests.post("http://localhost:8045/clear", timeout=2)
        except Exception as e:
            log.warning(f"Failed to clear vocalizer queue during barge-in: {e}")
        return {"status": "ok", "interrupted": True, "from": current}
    return {"status": "ok", "interrupted": False, "reason": f"Not in speaking state ({current})"}

@app.post("/reset")
def reset():
    """Force reset to idle."""
    _set_state("idle", "manual reset")
    rc.set("interrupt:barge_in", "0")
    try:
        requests.post("http://localhost:8045/clear", timeout=2)
    except Exception as e:
        log.warning(f"Failed to clear vocalizer queue during reset: {e}")
    return {"status": "ok", "state": "idle"}

# Auto-timeout: if stuck in thinking/speaking > 120s, reset to idle
_watchdog_interval = 30

def _watchdog():
    while True:
        try:
            state = _get_state()
            ts = float(rc.get("interrupt:transition_ts") or "0")
            if state in ("thinking", "speaking") and time.time() - ts > 120:
                log.warning(f"FSM watchdog: {state} for >120s, resetting to idle")
                _set_state("idle", "watchdog timeout")
        except Exception as e:
            log.error(f"FSM watchdog loop exception: {e}")
        time.sleep(_watchdog_interval)

threading.Thread(target=_watchdog, daemon=True).start()

@app.get("/health")
def health():
    return {"status": "ok", "service": "interrupt_fsm", "port": 8052,
            "current_state": _get_state()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8052)
