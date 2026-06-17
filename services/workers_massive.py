#!/usr/bin/env python3
"""
XOYO Massive Workers — True Subagent Spawner
Spawns worker_subagent.py as independent subprocess agents.
Max 2 concurrent workers to protect 8GB RAM.
Communicates via Redis pub/sub.
"""
from fastapi import FastAPI
from pydantic import BaseModel
import subprocess, json, uuid, time, threading, logging, os, redis, signal
import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.workers")
app = FastAPI()

rc_pool = redis.ConnectionPool(host='localhost', port=6379, db=0, max_connections=20, decode_responses=True)
rc = redis.Redis(connection_pool=rc_pool)

# ── Configuration ────────────────────────────────────────────
MAX_CONCURRENT_WORKERS = 2   # RAM protection: max 2 subagent processes (~80MB)
WORKER_TIMEOUT_S = 120       # Auto-kill after 2 minutes
MAX_OUTPUT_BYTES = 5 * 1024 * 1024 # Limit stdout/stderr to 5 MB

WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker_subagent.py")
PYTHON_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv", "bin", "python")

# ── Active worker tracking ───────────────────────────────────
_workers = {}  # worker_id -> {"process": Popen, "started": float, "task": str, "pid": int}
_workers_lock = threading.Lock()

# ThreadPoolExecutor to bound thread creation before acquiring resources
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS)

class SpawnRequest(BaseModel):
    tasks: list = []
    context: dict = {}
    max_workers: int = 2

def _kill_process_group(pid):
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception as e:
        log.warning(f"Failed to kill process group {pid}: {e}")

def _spawn_worker(task: str, context: dict, worker_id: str):
    """Spawn a single worker subagent as a subprocess."""
    try:
        cmd = [
            PYTHON_BIN, WORKER_SCRIPT,
            "--task", json.dumps({"text": task}),
            "--worker-id", worker_id,
            "--context", json.dumps(context)
        ]

        log.info(f"Spawning worker {worker_id}: {task[:80]}")

        with tempfile.TemporaryFile() as out_tmp, tempfile.TemporaryFile() as err_tmp:
            process = subprocess.Popen(
                cmd,
                stdout=out_tmp,
                stderr=err_tmp,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                preexec_fn=os.setsid  # Create new process group
            )

            with _workers_lock:
                _workers[worker_id] = {
                    "process": process,
                    "started": time.time(),
                    "task": task[:200],
                    "pid": process.pid
                }

            # Wait for completion or timeout
            try:
                process.wait(timeout=WORKER_TIMEOUT_S)

                # Bounded read to prevent memory exhaustion
                out_tmp.seek(0)
                stdout_str = out_tmp.read(MAX_OUTPUT_BYTES).decode('utf-8', errors='replace')
                err_tmp.seek(0)
                stderr_str = err_tmp.read(MAX_OUTPUT_BYTES).decode('utf-8', errors='replace')

                if process.returncode == 0:
                    # Try to parse result from stdout
                    try:
                        result = json.loads(stdout_str.strip().split('\n')[-1])
                    except (json.JSONDecodeError, IndexError):
                        result = {"answer": stdout_str.strip() or "Task completed.", "status": "completed"}

                    rc.set(f"xoyo:worker:{worker_id}:result", json.dumps(result), ex=3600)
                    rc.hset(f"xoyo:worker:{worker_id}", "status", "completed")
                    log.info(f"Worker {worker_id} completed successfully")
                else:
                    error = stderr_str.strip() if stderr_str else f"Exit code {process.returncode}"
                    rc.hset(f"xoyo:worker:{worker_id}", "status", "error")
                    rc.hset(f"xoyo:worker:{worker_id}", "error", error[:500])
                    log.error(f"Worker {worker_id} failed: {error[:200]}")

            except subprocess.TimeoutExpired:
                _kill_process_group(process.pid)
                process.wait()
                rc.hset(f"xoyo:worker:{worker_id}", "status", "timeout")
                rc.hset(f"xoyo:worker:{worker_id}", "error", "Exceeded 2 minute timeout")
                log.warning(f"Worker {worker_id} killed after timeout")

    except Exception as e:
        log.error(f"Worker {worker_id} spawn error: {e}")
        rc.hset(f"xoyo:worker:{worker_id}", "status", "error")
        rc.hset(f"xoyo:worker:{worker_id}", "error", str(e)[:500])

    finally:
        with _workers_lock:
            _workers.pop(worker_id, None)
        rc.hset(f"xoyo:worker:{worker_id}", "ended", time.time())
        rc.expire(f"xoyo:worker:{worker_id}", 3600)  # TTL: auto-delete after 1 hour


_background_tasks = set()

async def _collect_results(job_id: str, worker_ids: list):
    """Background asyncio task that waits for all workers and collects results."""
    try:
        all_results = []
        for wid in worker_ids:
            # Poll until worker finishes (max wait = WORKER_TIMEOUT_S + 10)
            deadline = time.time() + WORKER_TIMEOUT_S + 10
            while time.time() < deadline:
                status = rc.hget(f"xoyo:worker:{wid}", "status")
                if status in ("completed", "error", "timeout", "crashed", "rejected"):
                    break
                await asyncio.sleep(1)

            # Get result
            result_json = rc.get(f"xoyo:worker:{wid}:result")
            if result_json:
                try:
                    all_results.append(json.loads(result_json))
                except json.JSONDecodeError:
                    all_results.append({"error": "Failed to parse result", "worker_id": wid})
            else:
                status = rc.hget(f"xoyo:worker:{wid}", "status") or "unknown"
                error = rc.hget(f"xoyo:worker:{wid}", "error") or "No result"
                all_results.append({"error": error, "status": status, "worker_id": wid})

        # Store aggregated results
        rc.set(f"xoyo:job_results:{job_id}", json.dumps(all_results), ex=86400)
        log.info(f"Job {job_id} complete. {len(all_results)} worker results collected.")
    except Exception as e:
        log.error(f"Error in _collect_results for job {job_id}: {e}")


@app.post("/spawn")
async def spawn(req: SpawnRequest):
    if not req.tasks:
        return {"error": "No tasks"}

    job_id = uuid.uuid4().hex[:12]
    worker_ids = []

    # Cap concurrency but queue all tasks
    effective_max = min(req.max_workers, MAX_CONCURRENT_WORKERS)
    tasks_to_run = req.tasks

    for task in tasks_to_run:
        # Avoid UUID collision via full UUID string instead of truncated random
        worker_id = str(uuid.uuid4())
        worker_ids.append(worker_id)

        # Spawn worker via ThreadPoolExecutor. This guarantees only MAX_CONCURRENT_WORKERS
        # threads are ever spawned, preventing OOM via thread bombing.
        executor.submit(_spawn_worker, task, req.context, worker_id)

    # Collect results via asyncio task (prevents thread leak)
    task = asyncio.create_task(_collect_results(job_id, worker_ids))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "job_id": job_id,
        "workers": worker_ids,
        "total": len(tasks_to_run),
        "max_concurrent": effective_max,
        "autonomous": True,
        "subagent_mode": True,
        "status": "workers spawning"
    }


@app.get("/workers/status")
def workers_status():
    """Get status of all active workers."""
    with _workers_lock:
        active = [
            {
                "worker_id": wid,
                "pid": info["pid"],
                "task": info["task"],
                "uptime_s": round(time.time() - info["started"], 1)
            }
            for wid, info in _workers.items()
        ]
    return {"active_workers": active, "max_concurrent": MAX_CONCURRENT_WORKERS}


@app.post("/workers/{worker_id}/message")
async def send_message(worker_id: str, message: dict):
    """Send a message to a running worker's pubsub channel."""
    payload = json.dumps({"sender": "orchestrator", "message": message})
    count = rc.publish(f"xoyo:worker:{worker_id}:pubsub", payload)
    return {"status": "sent", "worker_id": worker_id, "listeners": count}


@app.delete("/workers/kill_all")
async def kill_all_workers():
    """Aggressively kill all running workers (e.g. infinite loops)."""
    killed_workers = []
    
    # Snapshot active workers safely
    with _workers_lock:
        active_workers = list(_workers.items())
        
    for worker_id, info in active_workers:
        # Check if process is still running
        if info["process"].poll() is None:
            # Send SIGKILL to the process group
            _kill_process_group(info["process"].pid)
            
            try:
                # Wait briefly to reap process and avoid zombies
                info["process"].wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
                
            # Update status in Redis
            rc.hset(f"xoyo:worker:{worker_id}", "status", "killed")
            killed_workers.append(worker_id)
            
    return {
        "status": "success",
        "action": "kill_all",
        "killed_count": len(killed_workers),
        "killed_workers": killed_workers
    }


@app.delete("/workers/{worker_id}")
async def kill_worker(worker_id: str):
    """Kill a running worker."""
    with _workers_lock:
        info = _workers.get(worker_id)
    if info and info["process"].poll() is None:
        _kill_process_group(info["process"].pid)
        info["process"].wait()
        rc.hset(f"xoyo:worker:{worker_id}", "status", "killed")
        return {"status": "killed", "worker_id": worker_id}
    return {"status": "not_found", "worker_id": worker_id}


@app.get("/job/{job_id}/results")
def get_job_results(job_id: str):
    """Get collected results for a job."""
    results = rc.get(f"xoyo:job_results:{job_id}")
    if results:
        return {"job_id": job_id, "results": json.loads(results)}
    return {"job_id": job_id, "status": "pending"}


@app.get("/health")
def health():
    with _workers_lock:
        active_count = len(_workers)
    return {
        "status": "ok",
        "engine": "XOYO True Subagent Workers",
        "mode": "subprocess",
        "active_workers": active_count,
        "max_concurrent": MAX_CONCURRENT_WORKERS,
        "autonomous": True
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
