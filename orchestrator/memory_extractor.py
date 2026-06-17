import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import redis
from orchestrator.llm_router import acall_llm

rc = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

async def extract_and_save_memory(user_text: str):
    prompt = f"Analyze the user's message. Does the user state a personal preference, a name, a fact about themselves, or an important command that should be remembered forever? If NO, reply EXACTLY 'none'. If YES, output a single concise statement summarizing the fact (e.g. 'User's name is Shashank').\nMessage: {user_text}"
    try:
        result = await acall_llm([{"role": "user", "content": prompt}], max_tokens=40, temperature=0.0, task_type="micro")
        res_clean = result.strip().lower()
        if res_clean and res_clean != "none" and "no " not in res_clean[:4] and len(res_clean) > 5:
            rc.rpush("xoyo:preferences:queue", result.strip())
            print(f"[Memory Extractor] Saved: {result.strip()}", flush=True)
    except Exception as e:
        print(f"Memory extraction failed: {e}")

async def extract_and_save_task_memory(req_text: str, result_summary: str):
    try:
        # Don't save trivial conversations
        if len(result_summary) < 20 or "Fast conversational response" in result_summary:
            return
            
        memory_string = f"Task completed: User asked '{req_text[:100]}'. XOYO executed: {result_summary[:200]}"
        rc.rpush("xoyo:preferences:queue", memory_string)
        print(f"[Memory Extractor] Saved Task Episode: {memory_string}", flush=True)
    except Exception as e:
        print(f"Task memory saving failed: {e}")
