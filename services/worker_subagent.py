#!/usr/bin/env python3
"""
XOYO Worker Subagent — True Autonomous Agent Process
Spawned as a subprocess by workers_massive.py.
Has its own ReAct planning loop, tool access, and Redis communication.
Auto-terminates after task completion or timeout.
"""
import sys, os, json, time, signal, argparse, logging, redis, re

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.llm_router import call_llm
from services.agent_tools import TOOLS_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Worker %(process)d] %(message)s")
log = logging.getLogger("xoyo.worker")

# ── Redis connection ─────────────────────────────────────────
rc = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# ── Auto-kill after timeout ──────────────────────────────────
MAX_RUNTIME_S = 120  # 2 minutes max

def _timeout_handler(signum, frame):
    log.error("Worker hit timeout limit. Self-terminating.")
    sys.exit(1)

signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(MAX_RUNTIME_S)

from services.agent_tools import TOOLS_SCHEMA

from services.native_schemas import NATIVE_TOOLS
import concurrent.futures

# ── ReAct Loop ───────────────────────────────────────────────
def run_react_loop(task: str, worker_id: str, context: dict = None, max_steps: int = 15):
    """Independent ReAct planning and execution loop."""

    # Report status
    rc.hset(f"xoyo:worker:{worker_id}", mapping={
        "status": "running",
        "task": task[:200],
        "started": time.time(),
        "pid": os.getpid(),
        "step": 0
    })

    context_str = ""
    if context:
        context_str = f"\nAdditional context: {json.dumps(context)[:500]}"

    # We tell the LLM it has native tools. We remove the old markdown JSON prompt.
    SYSTEM_PROMPT = """You are an autonomous XOYO Worker Subagent, part of a massive swarm executing parallel tasks.
    Your objective is to accomplish the task assigned to you efficiently and accurately with zero compromise on quality.
    You have native tool access. Do NOT fall back to dummy responses if a tool fails; instead, try another approach or report the error clearly.
    Maintain full context of the user's ultimate goal. Think step by step."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}{context_str}\n\nBegin. Think step by step."}
    ]

    # Set up Redis Pub/Sub for true peer-to-peer communication
    pubsub = rc.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(f"xoyo:worker:{worker_id}:pubsub", "xoyo:workers:broadcast")

    for step in range(max_steps):
        # Update heartbeat
        rc.hset(f"xoyo:worker:{worker_id}", "heartbeat", time.time())
        rc.hset(f"xoyo:worker:{worker_id}", "step", step)

        # Check pub/sub for true peer-to-peer messages
        while True:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if not msg:
                break
            try:
                data = json.loads(msg['data'])
                messages.append({"role": "user", "content": f"[PEER MESSAGE]: {data.get('message', msg['data'])}"})
                log.info(f"Received peer message: {str(msg['data'])[:100]}")
            except (json.JSONDecodeError, TypeError):
                messages.append({"role": "user", "content": f"[PEER MESSAGE]: {msg['data']}"})
                log.info(f"Received raw peer message: {str(msg['data'])[:100]}")

        # Check inbox for messages from orchestrator
        while True:
            msg = rc.rpop(f"xoyo:worker:{worker_id}:inbox")
            if not msg:
                break
            messages.append({"role": "user", "content": f"[MESSAGE FROM ORCHESTRATOR]: {msg}"})
            log.info(f"Received message: {msg[:100]}")

        try:
            # Pass NATIVE_TOOLS to llm_router!
            response = call_llm(messages, max_tokens=4096, temperature=0.3, task_type="reasoning", tools=NATIVE_TOOLS)
        except Exception as e:
            log.error(f"LLM call failed: {e}")
            rc.hset(f"xoyo:worker:{worker_id}", "status", "error")
            rc.hset(f"xoyo:worker:{worker_id}", "error", str(e))
            return {"error": str(e), "steps": step}

        # BULLETPROOF RE-ACT JSON EXTRACTOR (Stack-based)
        def bulletproof_json_extract(text):
            if not isinstance(text, str): return None
            # Limit length to prevent OOM/hangs on malformed JSON
            if len(text) > 50000: text = text[:50000]
            try:
                return json.loads(text)
            except:
                pass
            import re
            match = re.search(r'(\{.*?\}|\[.*?\])', text, re.DOTALL)
            if match:
                candidate = match.group(1)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    fixed = re.sub(r'\bTrue\b', 'true', candidate)
                    fixed = re.sub(r'\bFalse\b', 'false', fixed)
                    fixed = re.sub(r'\bNone\b', 'null', fixed)
                    fixed = re.sub(r"(?<![a-zA-Z])'([^'\\\\]*)'(?![a-zA-Z])", r'"\1"', fixed)
                    def fix_args(m):
                        args_str = m.group(1).replace('"', '\\"')
                        return f'"arguments": "{args_str}"'
                    fixed = re.sub(r'"arguments"\s*:\s*"(\{.*?\})"', fix_args, fixed, flags=re.DOTALL)
                    fixed = re.sub(r',\s*([\}\]])', r'\1', fixed)
                    try:
                        return json.loads(fixed)
                    except:
                        pass
            return None

        if isinstance(response, str):
            extracted = bulletproof_json_extract(response)
            if extracted:
                if isinstance(extracted, dict):
                    if "tool_calls" in extracted:
                        response = {"tool_calls": extracted["tool_calls"]}
                    elif "function" in extracted or "name" in extracted:
                        response = {"tool_calls": [extracted]}
                elif isinstance(extracted, list) and all(isinstance(x, dict) for x in extracted):
                    response = {"tool_calls": extracted}

        # Pillar 1 & 2: Native Function Calling & Parallel Execution
        if isinstance(response, dict) and "tool_calls" in response:
            tool_calls = response["tool_calls"]
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
            
            def execute_single_tool(tc):
                # Anthropic/OpenAI schema differences handling
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                
                try:
                    kwargs_str = func.get("arguments", "{}")
                    kwargs = json.loads(kwargs_str) if isinstance(kwargs_str, str) else kwargs_str
                except Exception:
                    kwargs = {}

                if tool_name == "final_answer":
                    return {"tool_name": tool_name, "result": "FINAL_ANSWER_REACHED", "kwargs": kwargs}
                
                if tool_name in TOOLS_REGISTRY:
                    try:
                        observation = TOOLS_REGISTRY[tool_name](**kwargs)
                        obs_str = str(observation)
                        if len(obs_str) > 4000:
                            observation = obs_str[:2000] + "\n\n... [MASSIVE OUTPUT TRUNCATED] ...\n\n" + obs_str[-2000:]
                        return {"tool_name": tool_name, "result": observation, "kwargs": kwargs}
                    except Exception as e:
                        return {"tool_name": tool_name, "result": f"Tool Error: {str(e)}", "kwargs": kwargs}
                else:
                    return {"tool_name": tool_name, "result": f"Unknown tool '{tool_name}'", "kwargs": kwargs}

            # Run parallel fan-out execution
            results = []
            final_answer_reached = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(execute_single_tool, tc) for tc in tool_calls]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    results.append(res)
                    if res["tool_name"] == "final_answer":
                        final_answer_reached = res
            
            if final_answer_reached:
                answer = final_answer_reached["kwargs"].get("answer", "Task completed.")
                res_obj = {"answer": answer, "steps": step + 1, "status": "completed"}
                rc.hset(f"xoyo:worker:{worker_id}", "status", "completed")
                rc.set(f"xoyo:worker:{worker_id}:result", json.dumps(res_obj), ex=3600)
                return res_obj
            
            # Fan-in aggregation
            obs_str = "Parallel Tool Observations:\n"
            for res in results:
                obs_str += f"[{res['tool_name']}]: {res['result']}\n"
            
            messages.append({"role": "user", "content": obs_str})
            log.info(f"Executed {len(results)} tools concurrently.")

        else:
            # Regular text response
            messages.append({"role": "assistant", "content": response})
            log.info(f"Step {step}: {str(response)[:150]}...")
            
            rc.publish("xoyo:events", json.dumps({
                "type": "worker_progress",
                "worker_id": worker_id,
                "step": step,
                "snippet": str(response)[:100]
            }))
            
            # If no tools were called, and it's just text, we consider it done
            res_obj = {"answer": response, "steps": step + 1, "status": "completed"}
            rc.hset(f"xoyo:worker:{worker_id}", "status", "completed")
            rc.set(f"xoyo:worker:{worker_id}:result", json.dumps(res_obj), ex=3600)
            return res_obj

    # Max steps reached
    result = {"error": "Max steps reached", "steps": max_steps, "status": "timeout"}
    rc.hset(f"xoyo:worker:{worker_id}", "status", "timeout")
    rc.set(f"xoyo:worker:{worker_id}:result", json.dumps(result), ex=3600)
    return result


# ── Entry Point ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XOYO Worker Subagent")
    parser.add_argument("--task", required=True, help="Task JSON string")
    parser.add_argument("--worker-id", required=True, help="Unique worker ID")
    parser.add_argument("--context", default="{}", help="Context JSON string")
    args = parser.parse_args()

    try:
        task_data = json.loads(args.task) if args.task.startswith('{') else {"text": args.task}
        context = json.loads(args.context)
    except json.JSONDecodeError:
        task_data = {"text": args.task}
        context = {}

    task_text = task_data.get("text", args.task)

    log.info(f"Worker {args.worker_id} starting with task: {task_text[:100]}")

    try:
        result = run_react_loop(task_text, args.worker_id, context)
        print(json.dumps(result))
    except Exception as e:
        log.error(f"Worker crashed: {e}")
        rc.hset(f"xoyo:worker:{args.worker_id}", "status", "crashed")
        rc.hset(f"xoyo:worker:{args.worker_id}", "error", str(e))
        print(json.dumps({"error": str(e), "status": "crashed"}))
    finally:
        # Always report termination
        rc.hset(f"xoyo:worker:{args.worker_id}", "ended", time.time())
        log.info(f"Worker {args.worker_id} terminated.")
