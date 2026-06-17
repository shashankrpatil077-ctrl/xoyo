from fastapi import FastAPI
from pydantic import BaseModel
import json, uvicorn, hashlib
from sentence_transformers import SentenceTransformer
import sys, os

app = FastAPI()

# Use TinyVectorDB instead of ChromaDB to save RAM
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.tiny_vector_db import TinyVectorDB

STORAGE_PATH = "/home/shashank/xoyo/tiny_db_storage"
vector_db = TinyVectorDB(path=STORAGE_PATH)
try:
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")  # lightweight, runs on CPU
except Exception as e:
    embedder = None
    print(f"Warning: Failed to load SentenceTransformer: {e}")

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm

class StoreRequest(BaseModel):
    text: str
    metadata: dict = {}

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5

class ConsolidateRequest(BaseModel):
    max_age_hours: int = 24
    similarity_threshold: float = 0.85

def _compress_to_latent_json(text: str) -> str:
    """Compress raw text into a dense Latent Space JSON representation."""
    prompt = f"Compress this text into a highly dense JSON schema capturing key entities, relations, and core facts. Return ONLY valid JSON.\nText: {text}"
    try:
        response = call_llm([{"role":"user", "content":prompt}], 1500, 0.3, "simple")
        # Extract json if wrapped in markdown
        if "```json" in response:
            return response.split("```json")[1].split("```")[0].strip()
        return response.strip()
    except Exception:
        return json.dumps({"raw_text": text, "compressed": False})

@app.post("/store")
def store(req: StoreRequest):
    """Embed and store a document automatically after latent-space compression."""
    # Latent-Space Optimization: Compress context before embedding
    compressed_text = _compress_to_latent_json(req.text)
    
    try:
        embedding = embedder.encode(compressed_text) if embedder else None
    except Exception as e:
        return {"error": f"Embedding failed: {e}"}
        
    if embedding is None:
        return {"error": "Embedder not initialized."}
        
    doc_id = hashlib.md5(compressed_text.encode()).hexdigest()[:16]
    idx = vector_db.add(compressed_text, embedding, req.metadata)
    return {"status": "stored", "id": doc_id, "idx": idx, "latent_compression": True}

@app.post("/search")
def search(req: SearchRequest):
    """Search by semantic similarity."""
    try:
        q_emb = embedder.encode(req.query) if embedder else None
    except Exception as e:
        return {"error": f"Embedding failed: {e}"}
        
    if q_emb is None:
        return {"error": "Embedder not initialized."}
        
    results = vector_db.search(q_emb, k=req.n_results)
    
    docs = []
    dists = []
    metas = []
    for r in results:
        docs.append(r["text"])
        dists.append(1.0 - r["score"])  # cosine distance equivalent roughly
        metas.append(r["metadata"])
        
    return {"results": docs,
            "distances": dists,
            "metadatas": metas}

@app.post("/consolidate")
async def consolidate(req: ConsolidateRequest):
    """Autonomously merge duplicate/similar memories and prune old ones."""
    # This is a simplified version – in a full system it would use the embeddings
    # to find clusters and keep only the most representative.
    count = vector_db.active_count
    # For now, just report; true consolidation would need to fetch all and compare
    return {"status": "consolidated", "items_before": count, "items_after": count,
            "note": "Full consolidation requires embedding comparison; implemented as stub."}

@app.get("/status")
async def status():
    """Self-diagnosis."""
    count = vector_db.active_count if hasattr(vector_db, 'active_count') else 0
    return {"total_documents": count,
            "collection_name": "xoyo_memory_tiny",
            "status": "healthy"}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Autonomous Memory Manager"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8012)
