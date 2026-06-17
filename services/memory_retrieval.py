#!/usr/bin/env python3
"""
XOYO Five-Path Memory Retrieval Engine
Research: MAGMA, MemORAI, Synrix, Alibaba Dual-Engine QA
Port: 8047
"""
from fastapi import FastAPI
import json, os, time, math

app = FastAPI()

# Redis with fallback
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_client.ping()
except Exception:
    class _FakeRedis:
        def get(self, k): return None
    redis_client = _FakeRedis()

MEM_BASE     = os.path.expanduser("~/xoyo/memories")
EPISODES_DIR = f"{MEM_BASE}/episodes"
PROFILE_PATH = f"{MEM_BASE}/profile/shashank.json"
SKILLS_PATH  = f"{MEM_BASE}/skills/shashank.json"

# ── Path 1: Redis direct key lookup (O(1), ~0.08ms) ─────
def _path1_redis(query: str) -> list:
    results = []
    for key in [f"research:summary:{query[:20]}", "memory:profile:shashank"]:
        val = redis_client.get(key)
        if val:
            results.append({"source": "redis", "key": key, "content": str(val)[:500], "score": 1.0})
    return results

# ── Path 2: Keyword similarity against profile + skills ─
def _path2_keyword(query: str) -> list:
    results = []
    query_lower = query.lower()
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
        content = json.dumps(profile)
        if any(word in content.lower() for word in query_lower.split()):
            results.append({"source": "semantic_profile", "content": content[:500], "score": 0.8})
    except Exception: pass
    try:
        with open(SKILLS_PATH) as f:
            skills = json.load(f)
        for skill in skills.get("skills", []):
            if any(w in str(skill).lower() for w in query_lower.split()):
                results.append({"source": "skill", "content": str(skill), "score": 0.7})
    except Exception: pass
    return results

# ── Path 3: BM25 keyword search over episodic memories ──
def _bm25_score(query_terms: list, doc: str, avg_dl: float = 200) -> float:
    k1, b = 1.5, 0.75
    # Strict 2MB length bound to prevent split() Out-Of-Memory errors on massive payloads
    doc_words = doc[:2000000].lower().split()
    dl = len(doc_words)
    if dl == 0:
        return 0.0
        
    from collections import Counter
    term_counts = Counter(doc_words)
    score = 0.0
    
    # Safe float conversion and math guards
    try:
        avg_dl_safe = max(1.0, float(avg_dl))
        length_norm = 1.0 - b + b * (dl / avg_dl_safe)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        length_norm = 1.0
        
    # Deduplicate query terms to prevent duplicate score accumulation
    for term in set(query_terms):
        tf = term_counts.get(term, 0)
        if tf > 0:
            try:
                den = tf + k1 * length_norm
                if den != 0:
                    score += (tf * (k1 + 1.0)) / den
            except (ZeroDivisionError, OverflowError):
                continue
    return score

def _path3_bm25(query: str) -> list:
    results = []
    terms = query.lower().split()
    try:
        files = sorted(os.listdir(EPISODES_DIR), reverse=True)[:50]
        for fname in files:
            if not fname.endswith(".json"): continue
            try:
                with open(f"{EPISODES_DIR}/{fname}") as f:
                    ep = json.load(f)
                content = json.dumps(ep)
                score = _bm25_score(terms, content)
                if score > 0.1:
                    results.append({"source": "episode_bm25", "file": fname,
                                    "content": ep.get("summary", "")[:300], "score": score})
            except Exception: pass
    except FileNotFoundError: pass
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:5]

# ── Path 4: Temporal / timeline search ──────────────────
def _path4_temporal(query: str) -> list:
    results = []
    months = ["january","february","march","april","may","june",
              "july","august","september","october","november","december"]
    query_lower = query.lower()
    target_month = next((m for m in months if m in query_lower), None)
    try:
        files = sorted(os.listdir(EPISODES_DIR), reverse=True)
        for fname in files:
            if not fname.endswith(".json"): continue
            if target_month and target_month[:3] not in fname.lower():
                continue
            try:
                with open(f"{EPISODES_DIR}/{fname}") as f:
                    ep = json.load(f)
                results.append({"source": "episode_temporal", "file": fname,
                                "content": ep.get("summary", "")[:300], "score": 0.9})
            except Exception: pass
            if len(results) >= 3: break
    except FileNotFoundError: pass
    return results

# ── Path 5: Research archive search ─────────────────────
def _path5_research(query: str) -> list:
    research_dir = f"{MEM_BASE}/research"
    results = []
    try:
        files = sorted(os.listdir(research_dir), reverse=True)[:20]
        query_lower = query.lower()
        for fname in files:
            if not fname.endswith(".json"): continue
            if any(w in fname.lower() for w in query_lower.split()):
                try:
                    with open(f"{research_dir}/{fname}") as f:
                        data = json.load(f)
                    summary = data.get("full_report", "")[:400]
                    results.append({"source": "research_archive", "file": fname,
                                    "content": summary, "score": 0.85})
                except Exception: pass
    except FileNotFoundError: pass
    return results[:3]

# ── Path 6: Dense Vector Database (TinyDB + Ollama) ─────
def _path6_vector_db(query: str) -> list:
    import requests
    from tiny_vector_db import TinyVectorDB
    results = []
    try:
        resp = requests.post("http://localhost:11434/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": query
        }, timeout=2)
        if resp.status_code == 200:
            emb = resp.json().get("embedding")
            if emb:
                db = TinyVectorDB(path="/home/shashank/xoyo/.xoyo_brain/tiny_db")
                vec_results = db.search(emb, k=3)
                for res in vec_results:
                    # Filter out weak matches
                    if res["score"] > 0.4:
                        results.append({
                            "source": "vector_db",
                            "content": res["text"],
                            "score": res["score"]
                        })
    except Exception as e:
        pass
    return results

# ── Reciprocal Rank Fusion ───────────────────────────────
def _rrf_merge(result_lists: list, k: int = 60) -> list:
    scores = {}
    for results in result_lists:
        for rank, item in enumerate(results):
            key = item.get("content", "")[:100]
            if key not in scores:
                scores[key] = {"item": item, "score": 0.0}
            scores[key]["score"] += 1.0 / (k + rank + 1)
    merged = [v["item"] for v in sorted(scores.values(),
                                        key=lambda x: x["score"], reverse=True)]
    return merged[:8]

# ── Main retrieval endpoint ──────────────────────────────
@app.post("/retrieve")
async def retrieve(query_data: dict):
    query = query_data.get("query", "")
    p1 = _path1_redis(query)
    p2 = _path2_keyword(query)
    p3 = _path3_bm25(query)
    p4 = _path4_temporal(query)
    p5 = _path5_research(query)
    p6 = _path6_vector_db(query)
    merged = _rrf_merge([p1, p2, p3, p4, p5, p6])
    context = "\n".join(
        f"[Memory {i+1} from {m.get('source','?')}]: {m.get('content','')}"
        for i, m in enumerate(merged[:5])
    )
    # Fixed key names to match main.py _auto_recall expectations
    return {"results": [m.get("content", "") for m in merged], "memories": merged, "context_for_prompt": context, "count": len(merged)}

@app.get("/graph")
def memory_graph():
    """Return memory nodes and edges for D3.js graph visualization."""
    nodes = []
    edges = []
    node_id = 0

    # Node: profile
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
        nodes.append({"id": node_id, "label": "Profile", "type": "profile", "importance": 10})
        profile_id = node_id
        node_id += 1
        for key in list(profile.keys())[:15]:
            nodes.append({"id": node_id, "label": key, "type": "fact", "importance": 5})
            edges.append({"source": profile_id, "target": node_id})
            node_id += 1
    except Exception:
        pass

    # Node: skills
    try:
        with open(SKILLS_PATH) as f:
            skills = json.load(f)
        for skill in skills.get("skills", [])[:10]:
            name = skill.get("name", str(skill)[:30]) if isinstance(skill, dict) else str(skill)[:30]
            nodes.append({"id": node_id, "label": name, "type": "skill", "importance": 4})
            if nodes and profile_id is not None:
                edges.append({"source": profile_id, "target": node_id})
            node_id += 1
    except Exception:
        pass

    # Node: episodes
    try:
        files = sorted(os.listdir(EPISODES_DIR), reverse=True)[:15]
        ep_ids = []
        for fname in files:
            if not fname.endswith(".json"):
                continue
            try:
                with open(f"{EPISODES_DIR}/{fname}") as f:
                    ep = json.load(f)
                label = ep.get("summary", fname)[:40]
                nodes.append({"id": node_id, "label": label, "type": "episode", "importance": 3})
                ep_ids.append(node_id)
                node_id += 1
            except Exception:
                pass
        # Link consecutive episodes
        for i in range(len(ep_ids) - 1):
            edges.append({"source": ep_ids[i], "target": ep_ids[i + 1]})
    except Exception:
        pass

    # Node: research
    research_dir = f"{MEM_BASE}/research"
    try:
        files = sorted(os.listdir(research_dir), reverse=True)[:10]
        for fname in files:
            if not fname.endswith(".json"):
                continue
            nodes.append({"id": node_id, "label": fname.replace(".json", "")[:30], "type": "research", "importance": 6})
            node_id += 1
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "total_edges": len(edges)}

@app.get("/health")
def health():
    return {"status": "ok", "service": "memory_retrieval", "port": 8047}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8047)
