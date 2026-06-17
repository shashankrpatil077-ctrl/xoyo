#!/usr/bin/env python3
"""
XOYO Task Doctor — Intelligent user-facing explanation engine (v2).
Answers: "why is this taking so long?", "why did this fail?", "diagnose task X".
Integrates with stuck_detector, agent_trace, and progress_vocalizer.
Port: 8051
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import requests, time, logging, json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.task_doctor")
app = FastAPI()

class ExplainRequest(BaseModel):
    question: str = "why is this taking so long?"
    task_id: str = ""

class SpeakExplainRequest(BaseModel):
    question: str = "what's happening?"
    task_id: str = ""
    voice: str = "default"

def _safe_get(url: str, timeout: float = 3.0) -> dict:
    """Safe HTTP GET with logging on failure."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.ok:
            return r.json()
    except Exception as e:
        log.debug(f"Failed to reach {url}: {e}")
    return {}

def _safe_post(url: str, data: dict, timeout: float = 3.0) -> dict:
    """Safe HTTP POST with logging on failure."""
    try:
        r = requests.post(url, json=data, timeout=timeout)
        if r.ok:
            return r.json()
    except Exception as e:
        log.debug(f"Failed to POST {url}: {e}")
    return {}

def _gather_diagnostics() -> dict:
    """Collect diagnostics from all watchdog services."""
    diag = {}
    diag["stall"] = _safe_get("http://localhost:8048/check_stall") or {"stalled": False}
    diag["health"] = _safe_get("http://localhost:8048/cognitive_health") or {"health": "unknown"}
    diag["alerts"] = (_safe_get("http://localhost:8048/alerts") or {}).get("alerts", [])[:5]
    diag["dashboard"] = _safe_get("http://localhost:8048/dashboard") or {}
    diag["vitals"] = _safe_get("http://localhost:8044/vitals") or {}
    diag["patterns"] = _safe_get("http://localhost:8049/patterns") or {}
    return diag

def _build_explanation(question: str, diagnostics: dict, task_traces: list = None) -> str:
    """Build plain-English explanation from diagnostics."""
    parts = []
    q = question.lower()

    if "taking so long" in q or "slow" in q or "waiting" in q:
        stall = diagnostics.get("stall", {})
        if stall.get("stalled"):
            idle = stall.get("idle_seconds", 0)
            last = stall.get("last_action", "?")
            parts.append(f"System has been idle for {idle:.0f}s since '{last}'.")

        vitals = diagnostics.get("vitals", {})
        if vitals.get("cpu_percent", 0) > 80:
            parts.append(f"CPU is at {vitals['cpu_percent']:.0f}% — heavy processing ongoing.")
        if vitals.get("ram_percent", 0) > 85:
            parts.append(f"RAM at {vitals['ram_percent']:.0f}% — memory pressure detected.")
        if vitals.get("cpu_temp_c", 0) > 80:
            parts.append(f"CPU temp is {vitals['cpu_temp_c']}°C — may be thermal throttling.")

        dashboard = diagnostics.get("dashboard", {})
        if dashboard.get("circuit_open"):
            parts.append(f"CIRCUIT BREAKER is OPEN: {dashboard.get('consec_failures', 0)} consecutive failures.")
        h = diagnostics.get("health", {})
        if h.get("health") == "degraded":
            parts.append("System cognitive health is degraded — high failure rate detected.")
        if h.get("health") == "critical":
            parts.append("CRITICAL: System health is critical. Multiple consecutive failures.")

        if not parts:
            parts.append("Everything appears normal. The task may just need more time.")

    elif "fail" in q or "error" in q or "wrong" in q or "broken" in q:
        alerts = diagnostics.get("alerts", [])
        if alerts:
            for a in alerts[:3]:
                if isinstance(a, dict):
                    atype = a.get("type", "?")
                    rec = a.get("recommendation", "")
                    parts.append(f"Alert [{atype}]: {rec}")
        h = diagnostics.get("health", {})
        if h.get("health") == "critical":
            m = h.get("metrics", {})
            parts.append(f"Critical: {m.get('failures',0)}/{m.get('total_actions',0)} "
                         f"recent actions failed ({m.get('failure_rate',0)*100:.0f}% failure rate).")

        # Check patterns
        patterns = diagnostics.get("patterns", {})
        bursts = patterns.get("bursts", [])
        if bursts:
            latest = bursts[-1]
            parts.append(f"Error burst detected: {latest.get('count',0)} errors in "
                         f"{latest.get('window_s',0):.0f}s across domains {latest.get('domains', [])}.")
        correlations = patterns.get("correlations", [])
        if correlations:
            c = correlations[-1]
            parts.append(f"Root cause chain: {c.get('cause','')} failure → {c.get('effect','')} "
                         f"failure (delay: {c.get('delay_s',0):.1f}s).")

        if task_traces:
            domains = [t.get("domain", "") for t in task_traces]
            if domains:
                primary = max(set(domains), key=domains.count)
                fix = task_traces[-1].get("fix", "Check logs")
                parts.append(f"Primary error domain: {primary}. Recommended fix: {fix}")

        if not parts:
            parts.append("No recent errors detected. System is operating normally.")

    else:
        h = diagnostics.get("health", {})
        parts.append(f"Cognitive health: {h.get('health','unknown')} (score: {h.get('score','?')}).")
        v = diagnostics.get("vitals", {})
        if v:
            parts.append(f"CPU: {v.get('cpu_percent',0):.0f}%, RAM: {v.get('ram_percent',0):.0f}%.")
        dashboard = diagnostics.get("dashboard", {})
        if dashboard.get("circuit_open"):
            parts.append("WARNING: Circuit breaker is OPEN.")

    return " ".join(parts) if parts else "System status is unclear."

@app.post("/explain")
def explain(req: ExplainRequest):
    """Generate plain-English explanation of current system state."""
    diagnostics = _gather_diagnostics()

    # Fetch task-specific traces if task_id provided
    task_traces = []
    if req.task_id:
        recent = _safe_get(f"http://localhost:8049/recent?n=50")
        all_traces = recent.get("traces", [])
        task_traces = [t for t in all_traces if t.get("task_id") == req.task_id]

    explanation = _build_explanation(req.question, diagnostics, task_traces)

    return {
        "explanation": explanation,
        "diagnostics": diagnostics,
        "task_traces": task_traces[:5],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

@app.get("/diagnose/{task_id}")
def diagnose_task(task_id: str):
    """Root-cause analysis for a specific task."""
    # Get traces for this task
    recent = _safe_get(f"http://localhost:8049/recent?n=100")
    all_traces = recent.get("traces", [])
    task_traces = [t for t in all_traces if t.get("task_id") == task_id]

    if not task_traces:
        return {
            "task_id": task_id,
            "diagnosis": "No error traces found for this task. It may be running normally.",
            "root_cause": None,
            "traces": [],
        }

    # Analyze
    domains = [t["domain"] for t in task_traces]
    primary_domain = max(set(domains), key=domains.count)
    total_errors = len(task_traces)
    first_error = task_traces[0]
    last_error = task_traces[-1]
    duration = last_error["ts"] - first_error["ts"]

    # Get cross-domain patterns
    patterns = _safe_get("http://localhost:8049/patterns") or {}
    correlations = [c for c in patterns.get("correlations", [])
                    if first_error["ts"] <= c.get("ts", 0) <= last_error["ts"] + 30]

    diagnosis_parts = [
        f"Task {task_id[:8]}... had {total_errors} errors over {duration:.0f}s.",
        f"Primary error domain: {primary_domain}.",
        f"Root cause fix: {last_error.get('fix', 'Check logs')}.",
    ]
    if correlations:
        c = correlations[0]
        diagnosis_parts.append(
            f"Cascade detected: {c['cause']} → {c['effect']} "
            f"({c['cause_action']} → {c['effect_action']})."
        )

    return {
        "task_id": task_id,
        "diagnosis": " ".join(diagnosis_parts),
        "root_cause": {
            "domain": primary_domain,
            "fix": last_error.get("fix", "Check logs"),
            "confidence": last_error.get("confidence", 0),
        },
        "error_count": total_errors,
        "duration_s": round(duration, 1),
        "traces": task_traces[-5:],
        "correlations": correlations[:3],
    }

@app.post("/speak_explanation")
def speak_explanation(req: SpeakExplainRequest):
    """Same as /explain but also sends result to progress_vocalizer."""
    result = explain(ExplainRequest(question=req.question, task_id=req.task_id))
    explanation = result["explanation"]

    # Send to TTS
    _safe_post("http://localhost:8045/speak", {"text": explanation[:500]})

    return {**result, "spoken": True}

@app.get("/health")
def health():
    return {"status": "ok", "service": "task_doctor", "port": 8051}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8051)
