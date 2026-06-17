from fastapi import FastAPI
import time, requests, redis, json, threading, os
from datetime import datetime, timedelta

app = FastAPI()
WORKSPACE_DIRECTORY = "/home/shashank/xoyo/workspace"
GUARDRAILS_FILE_PATH = f"{WORKSPACE_DIRECTORY}/GUARDRAILS.md"
HEALTH_CHECK_INTERVAL_SECONDS = 60

try:
    redis_connection = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    redis_connection.ping()
except Exception:
    class _FakeRedis:
        def __init__(self): self._d = {}
        def set(self, k, v, **kw): self._d[k] = v
        def get(self, k): return self._d.get(k)
        def lpush(self, k, v): self._d.setdefault(k, []).insert(0, v)
        def lrange(self, k, s, e): return self._d.get(k, [])[s:] if e == -1 else self._d.get(k, [])[s:e+1]
    redis_connection = _FakeRedis()

def is_user_active():
    try:
        last_user_activity_time = redis_connection.get("xoyo:last_command_time")
        if last_user_activity_time:
            activity_timestamp = datetime.fromisoformat(last_user_activity_time)
            if (datetime.utcnow() - activity_timestamp) < timedelta(minutes=5):
                return True
    except Exception:
        pass
    try:
        last_voice_activity_time = redis_connection.get("xoyo:last_voice_time")
        if last_voice_activity_time:
            activity_timestamp = datetime.fromisoformat(last_voice_activity_time)
            if (datetime.utcnow() - activity_timestamp) < timedelta(minutes=5):
                return True
    except Exception:
        pass
    return False

def get_service_health_status():
    service_health_urls = {
        "vllm": "http://localhost:9000/health",
        "vision": "http://localhost:8001/health",
        "whisper": "http://localhost:8002/health",
        "physics": "http://localhost:8005/health",
        "orchestrator": "http://localhost:9000/health",
        "dgm": "http://localhost:8007/health",
        "debate": "http://localhost:8020/health",
        "nngpt": "http://localhost:8016/health",
    }
    health_status = {}
    for service_name, health_url in service_health_urls.items():
        try:
            response = requests.get(health_url, timeout=3)
            health_status[service_name] = response.status_code == 200
        except Exception:
            health_status[service_name] = False
    return health_status

def compute_system_uncertainty():
    try:
        response = requests.post("http://localhost:8015/auto_explore", json={"domain": "general", "max_iterations": 2}, timeout=30)
        data = response.json()
        top_discovery = data.get("top_discovery", {})
        return top_discovery.get("surprise", 0.0)
    except Exception:
        return 0.0

def assess_action_effectiveness(action_classification):
    try:
        current_state_vector = [0.5 for _ in range(8)]
        response = requests.post("http://localhost:8019/imagine", json={"current_state": current_state_vector, "actions": [0,1,2], "n_rollouts": 3}, timeout=15)
        data = response.json()
        rollouts_data = data.get("rollouts", [])
        if rollouts_data:
            average_value = sum(abs(x) for trajectory in rollouts_data for x in trajectory[0]) / len(rollouts_data)
            return min(1.0, average_value * 0.1)
    except Exception:
        pass
    return 0.5

def generate_action_priorities(service_health_status):
    prioritized_actions = []
    for service_name, health_status in service_health_status.items():
        if not health_status:
            prioritized_actions.append(("restart", service_name, 10.0))
    system_uncertainty = compute_system_uncertainty()
    if system_uncertainty > 0.3:
        prioritized_actions.append(("build_model", f"high-uncertainty domain (surprise={system_uncertainty:.2f})", system_uncertainty * 8))
    prioritized_actions.append(("auto_improve", "orchestrator", 7.0))
    prioritized_actions.append(("ai_scientist", "latest AI + physics papers", 5.0))
    prioritized_actions.append(("update_profile", "", 4.0))
    prioritized_actions.append(("memory_consolidate", "", 3.0))
    for index, (action_type, target, priority_score) in enumerate(prioritized_actions):
        effectiveness = assess_action_effectiveness(action_type)
        prioritized_actions[index] = (action_type, target, priority_score * effectiveness)
    prioritized_actions.sort(key=lambda x: x[2], reverse=True)
    return prioritized_actions

def execute_action(action_type, target_service, priority_score):
    try:
        if action_type == "restart":
            with open(GUARDRAILS_FILE_PATH, "a") as file:
                file.write(f"\n## Priority Engine {datetime.utcnow()}\n- Flagged {target_service} as down\n")
            return f"Flagged {target_service}"
        elif action_type == "auto_improve":
            response = requests.post("http://localhost:8007/auto_improve", json={"domain": target_service, "max_cycles": 2}, timeout=120)
            return f"DGM: {response.json()}"
        elif action_type == "build_model":
            response = requests.post("http://localhost:8016/quick_build", json={"task_description": target_service, "input_size": 16, "output_size": 2}, timeout=60)
            return f"NNGPT: {response.json()}"
        elif action_type == "ai_scientist":
            response = requests.post("http://localhost:8026/ai_scientist_cycle", json={"hypothesis": target_service}, timeout=30)
            return f"AI Scientist: {response.json()}"
        elif action_type == "update_profile":
            # Log silently — NEVER post to /command (causes phantom task spam)
            try:
                requests.post("http://localhost:9000/internal/observe", json={
                    "text": "Priority Engine suggests profile update",
                    "source": "priority_engine", "severity": "info"
                }, timeout=3)
            except Exception: pass
            return "Profile update logged"
        elif action_type == "memory_consolidate":
            return "Memory consolidated"
        else:
            return f"Unknown: {action_type}"
    except Exception as error:
        return f"Error: {error}"

def autonomous_system_monitoring():
    while True:
        try:
            vitals = requests.get("http://localhost:8044/vitals", timeout=2).json()
            if vitals.get("cpu_percent", 0) > 85 or vitals.get("ram_percent", 0) > 90:
                print("Priority Engine: System overloaded, yielding.", flush=True)
                time.sleep(60)
                continue
        except Exception as e:
            print(f"Priority Engine: Error checking vitals: {e}", flush=True)
            pass
            
        if not is_user_active():
            service_health_status = get_service_health_status()
            prioritized_actions = generate_action_priorities(service_health_status)
            if prioritized_actions:
                best_action = prioritized_actions[0]
                action_outcome = execute_action(*best_action)
                with open(GUARDRAILS_FILE_PATH, "a") as file:
                    file.write(f"\n## Priority Engine {datetime.utcnow()}\n- Action: {best_action}\n- Result: {action_outcome}\n")
        time.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

threading.Thread(target=autonomous_system_monitoring, daemon=True).start()

@app.get("/health")
def health_check():
    return {"status":"ok","engine":"Priority Engine v2 – Bayesian Autonomous Idle Loop","autonomous":True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8022)