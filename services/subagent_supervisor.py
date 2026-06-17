import time
import os
import redis
import psutil

try:
    redis_client = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
except Exception:
    redis_client = None

def supervise():
    if not redis_client:
        print("Supervisor: Redis not available. Exiting.")
        return
        
    print("Subagent Supervisor started.")
    while True:
        try:
            active_agents = redis_client.smembers("xoyo:active_subagents")
            now = time.time()
            
            MAX_SUBAGENTS = 50
            if len(active_agents) > MAX_SUBAGENTS:
                print(f"Supervisor: Active agents ({len(active_agents)}) exceeds limit ({MAX_SUBAGENTS}). Enforcing limit.")
                # We cull agents over the limit. The system should ideally prevent them from spawning, but this acts as a hard backstop.
                excess = list(active_agents)[MAX_SUBAGENTS:]
                for cid in excess:
                    agent_key = f"xoyo:agent_state:{cid}"
                    pid = redis_client.hget(agent_key, "pid")
                    if pid:
                        try:
                            p = psutil.Process(int(pid))
                            if p.pid not in (1, os.getpid()) and p.name() not in ['systemd', 'init']:
                                p.terminate()
                                try: 
                                    pass  # Removed blocking wait
                                except psutil.TimeoutExpired: 
                                    p.kill()
                                    try: pass  # Removed blocking wait
                                    except psutil.TimeoutExpired: pass
                        except psutil.NoSuchProcess:
                            pass
                    redis_client.hset(agent_key, "status", "killed")
                    redis_client.srem("xoyo:active_subagents", cid)
                    redis_client.unlink(agent_key)
                # Refresh active agents list after cull
                active_agents = redis_client.smembers("xoyo:active_subagents")
            
            for cid in active_agents:
                agent_key = f"xoyo:agent_state:{cid}"
                
                # Check status
                status = redis_client.hget(agent_key, "status")
                if status in ["completed", "failed", "killed"]:
                    redis_client.srem("xoyo:active_subagents", cid)
                    redis_client.unlink(agent_key)
                    continue
                
                # Check heartbeat
                last_heartbeat = redis_client.hget(agent_key, "heartbeat")
                if last_heartbeat:
                    try:
                        last_heartbeat_float = float(last_heartbeat)
                    except ValueError:
                        print(f"Supervisor: Invalid heartbeat for agent {cid}. Skipping.")
                        continue
                    elapsed = now - last_heartbeat_float
                    if elapsed > 120:  # 2 minutes hung threshold
                        print(f"Supervisor: Agent {cid} hung (no heartbeat for {elapsed:.1f}s). Killing.")
                        pid = redis_client.hget(agent_key, "pid")
                        if pid:
                            try:
                                p = psutil.Process(int(pid))
                                if p.pid in (1, os.getpid()) or p.name() in ['systemd', 'init']:
                                    print(f"Supervisor: Protected process {pid} spoofed. Ignoring.")
                                else:
                                    p.terminate()
                                    try: 
                                        pass  # Removed blocking wait
                                    except psutil.TimeoutExpired: 
                                        p.kill()
                                        try: pass  # Removed blocking wait
                                        except psutil.TimeoutExpired: pass
                            except psutil.NoSuchProcess:
                                pass
                            except Exception as e:
                                print(f"Supervisor: Error killing pid {pid}: {e}")
                        
                        redis_client.hset(agent_key, "status", "killed")
                        redis_client.srem("xoyo:active_subagents", cid)
                        redis_client.unlink(agent_key)
                        
            # Ensure Redis memory usage is in check (Pruning old states)
            # This can be expanded for more complex GC.
            
        except Exception as e:
            print(f"Supervisor loop error: {e}")
            
        time.sleep(10)

if __name__ == "__main__":
    supervise()
