#!/usr/bin/env python3
"""
XOYO Stuck Detector — Advanced metacognitive watchdog (v2).
Signals: loop traps, timeouts, cognitive stalls, provider failures,
         consecutive streaks, pattern anomalies, circuit breaker.
Port: 8048
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, List, Optional
import time, threading, logging, json, os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.stuck_detector")
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
        def lpush(self, k, v): self._d.setdefault(k, []).insert(0, v)
        def ltrim(self, k, s, e): self._d[k] = self._d.get(k, [])[s:e+1]
        def lrange(self, k, s, e):
            lst = self._d.get(k, [])
            return lst[s:] if e == -1 else lst[s:e+1]
        def publish(self, *a): pass
    rc = _FR()

# ── Per-tool timeout thresholds (seconds) ────────────────────
TOOL_TIMEOUTS = {
    "web_search": 30, "read_file": 10, "write_file": 15,
    "execute_python": 60, "spawn_workers": 300, "debate": 120,
    "generate_ppt": 300, "generate_docx": 120, "generate_image": 180,
    "deep_research": 600, "auto_improve": 600, "auto_simulate": 300,
    "ai_scientist": 600, "open_application": 10, "screenshot": 15,
    "get_system_vitals": 10, "retrieve_memory": 15,
    "discover_materials": 300, "build_model": 300,
    "default": 60,
}

# ── Thread-safe state ────────────────────────────────────────
_lock = threading.Lock()
_action_history: List[Dict] = []
_MAX_HISTORY = 100
_consec_failures = 0
_circuit_open = False
_provider_failures: Dict[str, int] = {}
CIRCUIT_THRESHOLD = 5

class ActionReport(BaseModel):
    action: str
    params_hash: str = ""
    success: bool = True
    duration_s: float = 0.0
    provider: str = ""

def _emit_alert(alert: dict):
    """Store alert in Redis and publish to event bridge."""
    rc.lpush("stuck:alerts", json.dumps(alert))
    rc.ltrim("stuck:alerts", 0, 49)
    try:
        rc.publish("xoyo:alerts", json.dumps(alert))
    except Exception:
        pass

# ── Signal 1: Loop + Timeout + Provider + Streak Detector ────
@app.post("/report_action")
def report_action(report: ActionReport):
    """Called by orchestrator after each tool execution."""
    global _consec_failures, _circuit_open

    entry = {
        "action": report.action,
        "hash": report.params_hash,
        "success": report.success,
        "duration": report.duration_s,
        "provider": report.provider,
        "ts": time.time(),
    }

    with _lock:
        _action_history.append(entry)
        if len(_action_history) > _MAX_HISTORY:
            _action_history.pop(0)

        # ── Consecutive failure streak tracking ──
        if not report.success:
            _consec_failures += 1
            # Provider failure tracking
            if report.provider:
                _provider_failures[report.provider] = _provider_failures.get(report.provider, 0) + 1
        else:
            _consec_failures = 0

        # ── Circuit breaker ──
        if _consec_failures >= CIRCUIT_THRESHOLD and not _circuit_open:
            _circuit_open = True
            alert = {
                "type": "circuit_break", "severity": "critical",
                "streak": _consec_failures,
                "recommendation": f"CIRCUIT BREAKER OPEN: {_consec_failures} consecutive failures. Halt execution and diagnose.",
                "recovery": ["Check Redis: redis-cli ping", "Check LLM: ollama list", "Check service logs in ~/xoyo/logs/"],
                "ts": time.time(),
            }
            _emit_alert(alert)
            log.critical(f"CIRCUIT BREAKER: {_consec_failures} consecutive failures")
            return {"status": "circuit_open", "alert": alert}

        if report.success and _circuit_open:
            _circuit_open = False
            log.info("Circuit breaker CLOSED — success detected")

    alerts = []

    # ── Loop detection: same action+hash 3x in a row ──
    with _lock:
        if len(_action_history) >= 3:
            last3 = _action_history[-3:]
            if (last3[0]["action"] == last3[1]["action"] == last3[2]["action"] and
                last3[0]["hash"] == last3[1]["hash"] == last3[2]["hash"]):
                alert = {
                    "type": "loop_detected", "severity": "warning",
                    "action": report.action, "count": 3,
                    "recommendation": f"STOP calling {report.action} with same params. Try alternative approach.",
                    "recovery": ["Change parameters", "Use different tool", "Ask user for clarification"],
                    "ts": time.time(),
                }
                _emit_alert(alert)
                log.warning(f"LOOP DETECTED: {report.action} called 3x with same params")
                alerts.append(alert)

    # ── Timeout detection ──
    timeout = TOOL_TIMEOUTS.get(report.action, TOOL_TIMEOUTS["default"])
    if report.duration_s > timeout:
        alert = {
            "type": "timeout_exceeded", "severity": "warning",
            "action": report.action,
            "duration": report.duration_s, "threshold": timeout,
            "recommendation": f"{report.action} took {report.duration_s:.1f}s (limit: {timeout}s). Consider cancellation.",
            "recovery": [f"Increase timeout for {report.action}", "Check target service health", "Retry with simpler params"],
            "ts": time.time(),
        }
        _emit_alert(alert)
        log.warning(f"TIMEOUT: {report.action} took {report.duration_s:.1f}s")
        alerts.append(alert)

    # ── Pattern anomaly: >60% failures from same tool ──
    with _lock:
        recent = _action_history[-20:]
    if len(recent) >= 5:
        fail_by_tool = {}
        total_fails = 0
        for a in recent:
            if not a["success"]:
                total_fails += 1
                fail_by_tool[a["action"]] = fail_by_tool.get(a["action"], 0) + 1
        if total_fails >= 3:
            for tool, count in fail_by_tool.items():
                if count / total_fails > 0.6:
                    alert = {
                        "type": "pattern_anomaly", "severity": "warning",
                        "tool": tool, "failure_count": count, "total_failures": total_fails,
                        "recommendation": f"{tool} accounts for {count}/{total_fails} recent failures. Likely root cause.",
                        "recovery": [f"Check {tool} service health", f"Restart service for {tool}"],
                        "ts": time.time(),
                    }
                    _emit_alert(alert)
                    alerts.append(alert)

    status = "ok" if not alerts else alerts[0]["type"]
    return {"status": status, "alerts": alerts, "consec_failures": _consec_failures, "circuit_open": _circuit_open}

# ── Signal 2: Idle/Stall Detector ────────────────────────────
@app.get("/check_stall")
def check_stall():
    """Check if the system appears stalled (no actions for >60s during a task)."""
    with _lock:
        if not _action_history:
            return {"stalled": False, "reason": "no history"}
        last_ts = _action_history[-1]["ts"]
        last_action = _action_history[-1]["action"]
    idle_s = time.time() - last_ts
    stalled = idle_s > 60
    return {
        "stalled": stalled,
        "idle_seconds": round(idle_s, 1),
        "last_action": last_action,
        "recommendation": "Consider nudging the VMAO loop" if stalled else "System active",
    }

# ── Signal 3: Cognitive Health Monitor ───────────────────────
@app.get("/cognitive_health")
def cognitive_health():
    """Analyze recent action history for health patterns."""
    with _lock:
        history_copy = list(_action_history)
    if len(history_copy) < 3:
        return {"health": "insufficient_data", "score": 1.0}

    recent = history_copy[-20:]
    total = len(recent)
    failures = sum(1 for a in recent if not a["success"])
    avg_duration = sum(a["duration"] for a in recent) / total
    unique_actions = len(set(a["action"] for a in recent))

    fail_penalty = (failures / total) * 0.5
    diversity_bonus = min(unique_actions / 5, 0.3)
    speed_penalty = min(avg_duration / 120, 0.2)
    score = max(0.0, 1.0 - fail_penalty - speed_penalty + diversity_bonus)
    health = "healthy" if score > 0.7 else "degraded" if score > 0.4 else "critical"

    return {
        "health": health, "score": round(score, 3),
        "metrics": {
            "total_actions": total, "failures": failures,
            "failure_rate": round(failures/total, 3),
            "avg_duration_s": round(avg_duration, 2),
            "unique_actions": unique_actions,
        },
        "recommendation": (
            "System healthy" if health == "healthy" else
            "Consider restarting slow services" if health == "degraded" else
            "Critical: high failure rate. Check service connectivity."
        )
    }

@app.get("/alerts")
def get_alerts():
    """Get recent stuck/loop/timeout alerts."""
    raw = rc.lrange("stuck:alerts", 0, 49)
    alerts = []
    for r in raw:
        try:
            alerts.append(json.loads(r) if isinstance(r, str) else r)
        except Exception:
            pass
    return {"alerts": alerts, "count": len(alerts)}

# ── Dashboard: all watchdog state in one call ────────────────
@app.get("/dashboard")
def dashboard():
    """Complete watchdog state for frontend display."""
    with _lock:
        history_snapshot = list(_action_history[-20:])
    stall = check_stall()
    health = cognitive_health()
    alerts_data = get_alerts()
    return {
        "stall": stall,
        "health": health,
        "alerts": alerts_data["alerts"][:10],
        "circuit_open": _circuit_open,
        "consec_failures": _consec_failures,
        "provider_failures": dict(_provider_failures),
        "recent_actions": [
            {"action": a["action"], "success": a["success"], "duration": a["duration"], "ts": a["ts"]}
            for a in history_snapshot[-10:]
        ],
    }

@app.get("/health")
def health():
    return {
        "status": "ok", "service": "stuck_detector", "port": 8048,
        "circuit_open": _circuit_open,
        "total_tracked": len(_action_history),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8048)
