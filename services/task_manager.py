#!/usr/bin/env python3
"""
XOYO Task Manager — Checkpoint-and-resume + duration estimation (v2).
Library module (no port) — imported by orchestrator/main.py.
Provides: checkpoint/restore, pending task queue, duration tracking.
"""
import json, time, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.task_manager")

try:
    import redis
    rc = redis.Redis(host='localhost', port=6379, decode_responses=True)
    rc.ping()
except Exception:
    class _FR:
        def __init__(self): self._d = {}
        def set(self, k, v, **kw): self._d[k] = v
        def get(self, k): return self._d.get(k)
        def delete(self, k): self._d.pop(k, None)
        def keys(self, pattern=""): return [k for k in self._d if pattern.replace("*","") in k]
        def lpush(self, k, v): self._d.setdefault(k, []).insert(0, v)
        def lrange(self, k, s, e):
            lst = self._d.get(k, [])
            return lst[s:] if e == -1 else lst[s:e+1]
        def lpop(self, k):
            lst = self._d.get(k, [])
            return lst.pop(0) if lst else None
        def llen(self, k): return len(self._d.get(k, []))
        def hset(self, name, key, val):
            if not hasattr(self, '_h'): self._h = {}
            self._h.setdefault(name, {})[key] = val
        def hget(self, name, key):
            if not hasattr(self, '_h'): self._h = {}
            return self._h.get(name, {}).get(key)
        def hgetall(self, name):
            if not hasattr(self, '_h'): self._h = {}
            return dict(self._h.get(name, {}))
    rc = _FR()

CHECKPOINT_TTL = 3600  # 1 hour
DURATION_KEY = "xoyo:tool_durations"  # Hash: action_name → JSON list of recent durations

# ── Checkpoint & Restore ─────────────────────────────────────

def checkpoint_vmao(task_id: str, state: dict):
    """Save VMAO loop state to Redis for crash recovery."""
    key = f"checkpoint:{task_id}"
    state["checkpoint_ts"] = time.time()
    try:
        rc.set(key, json.dumps(state, default=str), ex=CHECKPOINT_TTL)
        log.info(f"Checkpoint saved: {task_id}")
    except Exception as e:
        log.warning(f"Checkpoint failed: {e}")
        
    # Periodically clean up expired tasks on save to prevent _FR memory leak
    if time.time() % 100 < 5:  # ~5% chance to run cleanup
        auto_cleanup_expired()

def restore_vmao(task_id: str) -> dict:
    """Restore VMAO state from checkpoint. Returns None if no checkpoint."""
    key = f"checkpoint:{task_id}"
    try:
        data = rc.get(key)
        if data:
            state = json.loads(data)
            age = time.time() - state.get('checkpoint_ts', 0)
            log.info(f"Checkpoint restored: {task_id} (age: {age:.0f}s)")
            return state
    except Exception as e:
        log.warning(f"Restore failed: {e}")
    return None

def clear_checkpoint(task_id: str):
    """Remove checkpoint after task completes."""
    try:
        rc.delete(f"checkpoint:{task_id}")
    except Exception:
        pass

# ── Pending Task Queue ───────────────────────────────────────

def queue_pending_task(user: str, task_text: str):
    """Queue a task for autonomous mode to pick up."""
    key = f"pending_tasks:{user}"
    try:
        rc.lpush(key, json.dumps({
            "text": task_text,
            "queued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }))
        return rc.llen(key)
    except Exception as e:
        log.error(f"Failed to queue pending task: {e}")
        return 0

def get_pending_tasks(user: str, n: int = 10):
    """List pending tasks."""
    key = f"pending_tasks:{user}"
    tasks = []
    try:
        raw = rc.lrange(key, 0, n - 1)
        for r in raw:
            try:
                tasks.append(json.loads(r) if isinstance(r, str) else r)
            except Exception:
                tasks.append(r)
    except Exception as e:
        log.error(f"Failed to get pending tasks: {e}")
    return tasks

def pop_pending_task(user: str):
    """Pop the next pending task."""
    key = f"pending_tasks:{user}"
    try:
        raw = rc.lpop(key)
        if raw:
            try:
                return json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                return raw
    except Exception as e:
        log.error(f"Failed to pop pending task: {e}")
    return None

# ── Duration Tracking & Estimation ───────────────────────────

def record_duration(action_name: str, duration_s: float):
    """Store actual duration for a tool action (for estimation)."""
    try:
        raw = rc.hget(DURATION_KEY, action_name)
        durations = json.loads(raw) if raw else []
        durations.append(round(duration_s, 2))
        if len(durations) > 50:
            durations = durations[-50:]  # Keep last 50
        rc.hset(DURATION_KEY, action_name, json.dumps(durations))
    except Exception as e:
        log.debug(f"Duration record failed: {e}")

def estimate_duration(action_name: str) -> dict:
    """Return estimated duration based on historical data."""
    try:
        raw = rc.hget(DURATION_KEY, action_name)
        if raw:
            durations = json.loads(raw)
            if durations:
                avg = sum(durations) / len(durations)
                p95 = sorted(durations)[int(len(durations) * 0.95)] if len(durations) >= 5 else max(durations)
                return {
                    "action": action_name,
                    "avg_s": round(avg, 2),
                    "p95_s": round(p95, 2),
                    "samples": len(durations),
                    "min_s": round(min(durations), 2),
                    "max_s": round(max(durations), 2),
                }
    except Exception as e:
        log.debug(f"Duration estimate failed: {e}")
    return {"action": action_name, "avg_s": None, "samples": 0}

# ── Task Summary ─────────────────────────────────────────────

def get_task_summary(task_id: str) -> dict:
    """Return checkpoint + duration estimate + age for a task."""
    checkpoint = restore_vmao(task_id)
    if not checkpoint:
        return {"task_id": task_id, "status": "no_checkpoint"}

    age = time.time() - checkpoint.get("checkpoint_ts", 0)
    last_results = checkpoint.get("all_results", [])
    last_action = last_results[-1]["action"] if last_results else None
    estimate = estimate_duration(last_action) if last_action else {}

    return {
        "task_id": task_id,
        "status": "checkpointed",
        "age_s": round(age, 1),
        "attempt": checkpoint.get("attempt", 0),
        "consec_errors": checkpoint.get("consec_errors", 0),
        "last_action": last_action,
        "duration_estimate": estimate,
        "results_count": len(last_results),
    }

# ── Auto-cleanup on import ──────────────────────────────────

def auto_cleanup_expired():
    """Delete checkpoints older than TTL. Called on import."""
    try:
        if hasattr(rc, "scan_iter"):
            keys = list(rc.scan_iter(match="checkpoint:*", count=100))
        else:
            keys = rc.keys("checkpoint:*")
        cleaned = 0
        for k in keys:
            data = rc.get(k)
            if data:
                try:
                    state = json.loads(data)
                    age = time.time() - state.get("checkpoint_ts", 0)
                    if age > CHECKPOINT_TTL:
                        rc.delete(k)
                        cleaned += 1
                except Exception:
                    rc.delete(k)
                    cleaned += 1
        if cleaned:
            log.info(f"Auto-cleanup: removed {cleaned} expired checkpoints")
    except Exception as e:
        log.debug(f"Auto-cleanup failed: {e}")

# Run cleanup on import
auto_cleanup_expired()
