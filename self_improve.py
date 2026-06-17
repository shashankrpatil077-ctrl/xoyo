#!/usr/bin/env python3
"""XOYO Autonomous Self-Improvement Daemon (DGM-H Architecture)"""
import requests, time, os

try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_client.ping()
except Exception:
    class _FakeRedis:
        def lrange(self, *a): return []
        def lpop(self, *a): return None
    redis_client = _FakeRedis()

ORCHESTRATOR = "http://localhost:9000/command"
TOKEN = "xoyo-research-2026"
INTERVAL = 600  # 10 minutes
LOG_DIR = os.path.expanduser("~/xoyo/logs")
os.makedirs(LOG_DIR, exist_ok=True)

def _gather_telemetry():
    import json
    telemetry = {"logs": "", "lessons": []}
    try:
        with open(f"{LOG_DIR}/orchestrator.log", "r") as f:
            lines = f.readlines()[-200:]
            # Filter only WARNING and ERROR to save tokens
            error_lines = [l for l in lines if "WARNING" in l or "ERROR" in l or "Traceback" in l]
            if error_lines:
                telemetry["logs"] = "".join(error_lines[-20:])
            else:
                telemetry["logs"] = "System operating normally. No recent errors."
    except Exception:
        telemetry["logs"] = "Could not read logs."
        
    try:
        keys = redis_client.keys("ace:lesson:*")
        for k in keys[-5:]:
            val = redis_client.get(k)
            if val: telemetry["lessons"].append(val)
    except Exception:
        pass
    return telemetry

AUTONOMOUS_PROMPT_TEMPLATE = """[SELF-EVOLUTION MODE]
You are XOYO's autonomous self-improvement daemon.

### Recent Telemetry (Errors & Warnings):
{logs}

### Recent ACE Lessons:
{lessons}

### Task:
Analyze the telemetry above. Identify the single most impactful improvement or bug fix you can make to XOYO right now based on recent errors or learned lessons.
Plan it, execute it, verify it, log it, then report what you changed.
Focus on: error reduction, response speed, memory efficiency, service reliability.
Do NOT do anything unrelated to improving XOYO."""


def run_self_improvement():
    # Check for pending user tasks first
    pending = redis_client.lrange("pending_tasks:shashank", 0, -1)
    if pending:
        prompt = f"Complete this pending user task ONLY: {pending[0]}. Then stop."
        redis_client.lpop("pending_tasks:shashank")
    else:
        telem = _gather_telemetry()
        prompt = AUTONOMOUS_PROMPT_TEMPLATE.format(
            logs=telem["logs"] or "None",
            lessons="\n".join(telem["lessons"]) or "None"
        )

    try:
        r = requests.post(ORCHESTRATOR, json={
            "text": prompt,
            "developer_token": TOKEN
        }, timeout=600)
        result = r.json()
        with open(f"{LOG_DIR}/self_improve.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {str(result)[:200]}\n")
    except Exception as e:
        print(f"Self-improvement cycle error: {e}")


if __name__ == "__main__":
    print("XOYO Self-Improvement Daemon started")
    while True:
        run_self_improvement()
        time.sleep(INTERVAL)
