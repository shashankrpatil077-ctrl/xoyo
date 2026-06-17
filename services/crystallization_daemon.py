#!/usr/bin/env python3
"""
XOYO Skill Crystallization Daemon (Genesis Upgrade - Phase 1)
Monitors successful XOYO tasks and distills them into reusable Python skills.
Runs in the background, minimizing RAM usage.
"""

import time
import json
import logging
import os
import re
import requests
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.crystallization")

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

SKILLS_DIR = os.path.expanduser("~/xoyo/crystallized_skills")
os.makedirs(SKILLS_DIR, exist_ok=True)

LLM_URL = "http://localhost:9000/v1/chat/completions"

def call_llm(prompt: str) -> str:
    payload = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": "You are XOYO's internal crystallization engine. Your job is to convert successful task histories into a single reusable Python function. Output ONLY valid raw Python code, no markdown formatting, no explanations."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    try:
        resp = requests.post(LLM_URL, json=payload, timeout=120)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Remove markdown if the LLM hallucinated it
            if content.startswith("```python"):
                content = content[9:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()
    except Exception as e:
        log.error(f"LLM call failed: {e}")
    return ""

def generate_skill_name(prompt: str) -> str:
    """Generate a clean python filename from the user prompt."""
    payload = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": "You are a naming assistant. Convert the following task description into a short, snake_case python filename (without the .py extension). Max 4 words. Output ONLY the name."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    try:
        resp = requests.post(LLM_URL, json=payload, timeout=10)
        name = resp.json()["choices"][0]["message"]["content"].strip().lower()
        name = re.sub(r'[^a-z0-9_]', '', name)
        return name if name else f"skill_{int(time.time())}"
    except Exception:
        return f"skill_{int(time.time())}"

def process_completed_tasks():
    try:
        vitals = requests.get("http://localhost:8044/vitals", timeout=2).json()
        if vitals.get("cpu_percent", 0) > 85 or vitals.get("ram_percent", 0) > 90:
            log.info("Crystallization Daemon: System under heavy load. Yielding.")
            return
    except Exception:
        pass

    keys = redis_client.keys("xoyo:task:*")
    for key in keys:
        try:
            data = redis_client.get(key)
            if not data:
                continue
            task = json.loads(data)
            
            # Only crystallize complex completed tasks that haven't been crystallized yet
            if task.get("status") == "completed" and not task.get("crystallized"):
                history = task.get("history", [])
                
                # If the task took more than 2 steps, it's worth crystallizing
                if len(history) > 2:
                    log.info(f"Crystallizing task {key}: {task.get('prompt')}")
                    
                    llm_prompt = f"The user requested: '{task.get('prompt')}'.\n\nTo solve this, the agent took the following steps:\n{json.dumps(history, indent=2)}\n\nWrite a generalized Python script that implements this workflow directly. Use generic parameters where appropriate. Return ONLY valid python code. Make sure it includes an `if __name__ == '__main__':` block at the bottom that executes the main function and prints a summary of the result."
                    
                    skill_code = call_llm(llm_prompt)
                    if skill_code:
                        skill_name = generate_skill_name(task.get("prompt", ""))
                        filepath = os.path.join(SKILLS_DIR, f"{skill_name}.py")
                        
                        with open(filepath, "w") as f:
                            f.write(skill_code)
                        
                        # Store semantically in memory manager
                        try:
                            requests.post("http://localhost:8012/store", json={
                                "text": f"Crystallized skill to handle: {task.get('prompt')}",
                                "metadata": {"type": "crystallized_skill", "name": skill_name, "path": filepath}
                            }, timeout=5)
                        except Exception as e:
                            log.error(f"Failed to store in memory manager: {e}")

                        log.info(f"Successfully crystallized skill to {filepath}")
                    else:
                        log.warning(f"Failed to generate valid Python code for {key}")
                
                # Mark as processed whether it succeeded or not so we don't spam it
                task["crystallized"] = True
                redis_client.set(key, json.dumps(task))
                
        except Exception as e:
            log.error(f"Error processing {key}: {e}")

if __name__ == "__main__":
    log.info("XOYO Crystallization Daemon started.")
    while True:
        process_completed_tasks()
        time.sleep(30)  # Check every 30 seconds
