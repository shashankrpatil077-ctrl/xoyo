#!/usr/bin/env python3
import time, json, os, redis, requests
from tiny_vector_db import TinyVectorDB

rc = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
MEMORY_FILE = "/home/shashank/xoyo/.xoyo_brain/memory.json"
VEC_DB_PATH = "/home/shashank/xoyo/.xoyo_brain/tiny_db"

def get_embedding(text):
    """Get embedding from local Ollama nomic-embed-text."""
    try:
        resp = requests.post("http://localhost:11434/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": text
        }, timeout=10)
        return resp.json().get("embedding")
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def consolidate_memory():
    """Reads logs and tracks user preferences using Vector DB."""
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    db = TinyVectorDB(path=VEC_DB_PATH)
    
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f:
            try:
                memory = json.load(f)
            except:
                memory = {"preferences": []}
    else:
        memory = {"preferences": []}

    print("Memory Consolidator started with Vector DB enabled.")
    
    while True:
        try:
            try:
                vitals = requests.get("http://localhost:8044/vitals", timeout=2).json()
                if vitals.get("cpu_percent", 0) > 85 or vitals.get("ram_percent", 0) > 90:
                    print("Memory Consolidator: System under load. Yielding.")
                    time.sleep(30)
                    continue
            except Exception:
                pass
            
            # Check for explicitly saved preferences
            pref = rc.lpop("xoyo:preferences:queue")
            if pref:
                if pref not in memory["preferences"]:
                    memory["preferences"].append(pref)
                    with open(MEMORY_FILE, 'w') as f:
                        json.dump(memory, f, indent=4)
                    print(f"Memory Consolidator: Saved new preference -> {pref}")
                    
                    # Store in Vector DB
                    emb = get_embedding(pref)
                    if emb:
                        db.add(pref, emb, metadata={"type": "preference"})
                        print("Saved to Vector DB.")
                        
        except Exception as e:
            print(f"Memory Consolidator Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    consolidate_memory()
