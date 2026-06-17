#!/usr/bin/env python3
"""
XOYO Agent Trace — Advanced causal error graph & root-cause analysis (v2).
5-domain taxonomy: MEMORY, REFLECTION, PLANNING, ACTION, SYSTEM.
Features: temporal burst detection, cross-domain correlation, trace chains.
Port: 8049
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
import time, json, logging, os, threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.agent_trace")
app = FastAPI()

TRACE_DIR = os.path.expanduser("~/xoyo/logs/traces")
os.makedirs(TRACE_DIR, exist_ok=True)

DOMAINS = {
    "MEMORY":     ["redis", "memory", "key not found", "cache", "recall", "episode", "profile", "checkpoint"],
    "REFLECTION": ["json", "parse", "extract_json", "invalid", "hallucin", "verification", "format", "decode"],
    "PLANNING":   ["unknown action", "missing param", "validation", "schema", "loop", "stuck", "no actions", "done:true"],
    "ACTION":     ["connection refused", "timeout", "500", "503", "exit_code", "permission", "file not found", "404", "refused"],
    "SYSTEM":     ["oom", "killed", "cpu", "ram", "disk full", "temperature", "ollama", "port", "redis", "gpu"],
}

FIXES = {
    "MEMORY":     "Check Redis: redis-cli ping. Restart memory_personal.py (8046). Verify checkpoint keys.",
    "REFLECTION": "Lower temperature. Check extract_json(). Simplify prompt. Use structured output.",
    "PLANNING":   "Verify tool in AVAILABLE_TOOLS. Check required params. Reset VMAO loop state.",
    "ACTION":     "Restart target service. Check logs/ for crash. Verify port is listening.",
    "SYSTEM":     "Run free -h and sensors. Kill unused services. Check ollama list.",
}

_lock = threading.Lock()
_traces: List[Dict] = []
_patterns: Dict[str, list] = {"bursts": [], "correlations": []}
MAX_TRACES = 500

class ErrorEvent(BaseModel):
    action: str
    error_message: str
    params: Dict = {}
    task_id: str = ""

def classify(msg: str) -> Dict:
    lower = msg.lower()
    scores = {}
    for d, pats in DOMAINS.items():
        hits = sum(1 for p in pats if p in lower)
        if hits:
            scores[d] = min(hits / len(pats) * 2, 1.0)
    if not scores:
        scores["ACTION"] = 0.5
    total = sum(scores.values())
    scores = {k: round(v / total, 3) for k, v in scores.items()}
    primary = max(scores, key=scores.get)
    return {"primary": primary, "confidence": scores[primary], "scores": scores}

def _detect_temporal_patterns():
    """Detect bursts (>3 errors in 30s) and cross-domain correlations."""
    with _lock:
        recent = list(_traces[-50:])
    if len(recent) < 3:
        return

    # ── Burst detection: >3 errors within 30s window ──
    bursts = []
    i = 0
    while i < len(recent):
        window = [recent[i]]
        for j in range(i + 1, len(recent)):
            if recent[j]["ts"] - recent[i]["ts"] <= 30.0:
                window.append(recent[j])
            else:
                break
        if len(window) >= 3:
            bursts.append({
                "type": "error_burst",
                "count": len(window),
                "window_s": round(window[-1]["ts"] - window[0]["ts"], 1),
                "domains": list(set(t["domain"] for t in window)),
                "actions": list(set(t["action"] for t in window)),
                "ts": window[0]["ts"],
            })
            i += len(window)
        else:
            i += 1

    # ── Cross-domain correlation: MEMORY→PLANNING within 10s ──
    correlations = []
    CORR_PAIRS = [
        ("MEMORY", "PLANNING"), ("MEMORY", "REFLECTION"),
        ("SYSTEM", "ACTION"), ("ACTION", "PLANNING"),
    ]
    for idx in range(len(recent) - 1):
        for jdx in range(idx + 1, min(idx + 5, len(recent))):
            if recent[jdx]["ts"] - recent[idx]["ts"] > 10.0:
                break
            pair = (recent[idx]["domain"], recent[jdx]["domain"])
            if pair in CORR_PAIRS:
                correlations.append({
                    "type": "cross_domain",
                    "cause": recent[idx]["domain"],
                    "effect": recent[jdx]["domain"],
                    "cause_action": recent[idx]["action"],
                    "effect_action": recent[jdx]["action"],
                    "delay_s": round(recent[jdx]["ts"] - recent[idx]["ts"], 2),
                    "ts": recent[idx]["ts"],
                })

    with _lock:
        _patterns["bursts"] = bursts[-10:]
        _patterns["correlations"] = correlations[-10:]

@app.post("/trace")
def record_trace(event: ErrorEvent):
    c = classify(event.error_message)
    trace = {
        "action": event.action,
        "error": event.error_message[:500],
        "task_id": event.task_id,
        "ts": time.time(),
        "domain": c["primary"],
        "confidence": c["confidence"],
        "scores": c["scores"],
        "fix": FIXES.get(c["primary"], "Check logs"),
        "params_summary": {k: str(v)[:80] for k, v in list(event.params.items())[:5]},
    }
    with _lock:
        _traces.append(trace)
        if len(_traces) > MAX_TRACES:
            _traces.pop(0)

    # Persist to daily log
    ts = time.strftime("%Y-%m-%d")
    try:
        with open(f"{TRACE_DIR}/{ts}.jsonl", "a") as f:
            f.write(json.dumps(trace) + "\n")
    except Exception as e:
        log.warning(f"Failed to write trace: {e}")

    # Update patterns
    _detect_temporal_patterns()

    # Publish to event bridge
    try:
        import redis
        _rc = redis.Redis(host='localhost', port=6379, decode_responses=True)
        _rc.publish("xoyo:alerts", json.dumps({
            "type": "trace", "domain": c["primary"],
            "action": event.action, "confidence": c["confidence"],
            "ts": time.time()
        }))
    except Exception:
        pass

    return {"status": "ok", "trace": trace}

@app.post("/analyze")
def analyze(data: Optional[Dict] = None):
    if data is None:
        data = {}
    n = data.get("last_n", 10)
    with _lock:
        recent = list(_traces[-n:])
    if not recent:
        return {"patterns": [], "total": 0}

    domains = {}
    actions = {}
    for t in recent:
        domains[t["domain"]] = domains.get(t["domain"], 0) + 1
        actions[t["action"]] = actions.get(t["action"], 0) + 1

    # Find dominant domain
    dominant = max(domains, key=domains.get) if domains else None
    dominant_pct = round(domains.get(dominant, 0) / len(recent) * 100, 1) if dominant else 0

    return {
        "total": len(recent),
        "domains": domains,
        "actions": actions,
        "dominant_domain": dominant,
        "dominant_pct": dominant_pct,
        "top_fix": recent[-1]["fix"] if recent else "",
        "task_chains": _build_chains(recent),
    }

def _build_chains(traces: List[Dict]) -> Dict[str, List]:
    """Group traces by task_id to reconstruct error chains."""
    chains = {}
    for t in traces:
        tid = t.get("task_id", "")
        if tid:
            if tid not in chains:
                chains[tid] = []
            chains[tid].append({
                "action": t["action"], "domain": t["domain"],
                "ts": t["ts"], "confidence": t["confidence"],
            })
    return chains

@app.get("/recent")
def get_recent(n: int = 20):
    """Returns last N traces for frontend display."""
    with _lock:
        recent = list(_traces[-n:])
    return {"traces": recent, "count": len(recent)}

@app.get("/patterns")
def get_patterns():
    """Returns detected temporal patterns (bursts, correlations)."""
    with _lock:
        return {
            "bursts": list(_patterns["bursts"]),
            "correlations": list(_patterns["correlations"]),
            "total_traces": len(_traces),
        }

@app.get("/health")
def health():
    with _lock:
        count = len(_traces)
    return {"status": "ok", "service": "agent_trace", "port": 8049, "traces": count}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8049)
