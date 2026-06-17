import numpy as np
import json, os
import sqlite3
import threading

class TinyVectorDB:
    def __init__(self, path="tiny_db"):
        self.path = path
        self.dim = 384
        self.vec_file = f"{path}/vectors.npy"
        self.meta_db = f"{path}/metadata.sqlite"
        os.makedirs(path, exist_ok=True)
        
        # Initialize SQLite
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.meta_db, check_same_thread=False)
        self.cursor = self.conn.cursor()
        with self.lock:
            self.cursor.execute("PRAGMA synchronous = OFF")
            self.cursor.execute("PRAGMA journal_mode = WAL")
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS metadata 
                                   (id INTEGER PRIMARY KEY, text TEXT, meta TEXT)''')
            self.conn.commit()

        with self.lock:
            self.cursor.execute("SELECT MAX(id) FROM metadata")
            max_id = self.cursor.fetchone()[0]
            self.active_count = (max_id + 1) if max_id is not None else 0

        # Load or initialize memmap
        if os.path.exists(self.vec_file):
            file_size = os.path.getsize(self.vec_file)
            self.capacity = file_size // (self.dim * 4)
            if self.capacity == 0:
                self.capacity = 10000
                with open(self.vec_file, "wb") as f:
                    f.truncate(self.capacity * self.dim * 4)
            self.vectors = np.memmap(self.vec_file, dtype='float32', mode='r+', shape=(self.capacity, self.dim))
        else:
            self.capacity = 10000
            self.vectors = np.memmap(self.vec_file, dtype='float32', mode='w+', shape=(self.capacity, self.dim))
            
    def add(self, text, embedding, metadata=None):
        embedding = np.asarray(embedding, dtype=np.float32)
        if embedding.ndim != 1 or embedding.shape[0] != self.dim:
            raise ValueError(f"Embedding shape {embedding.shape} does not match DB dimension {self.dim}")
        if np.isnan(embedding).any() or np.isinf(embedding).any():
            raise ValueError("Embedding contains NaN or Inf values")
            
        # L2 Normalize
        norm = np.linalg.norm(embedding)
        emb = (embedding / norm).astype(np.float32) if norm > 0 else embedding.astype(np.float32)
        
        with self.lock:
            try:
                # Save metadata
                meta_str = json.dumps(metadata) if metadata else "{}"
            except Exception as e:
                raise ValueError(f"Invalid metadata: {e}")

            if self.active_count >= self.capacity:
                # Hard ceiling: 500K vectors = ~730MB at 384 dims * 4 bytes
                MAX_VECTORS = 500000
                if self.capacity >= MAX_VECTORS:
                    raise RuntimeError(f"Vector DB capacity limit reached ({MAX_VECTORS} vectors). Cannot grow further to protect RAM.")
                self.capacity = min(self.capacity * 2, MAX_VECTORS)
                with open(self.vec_file, "ab") as f:
                    f.truncate(self.capacity * self.dim * 4)
                self.vectors = np.memmap(self.vec_file, dtype='float32', mode='r+', shape=(self.capacity, self.dim))
                
            self.vectors[self.active_count] = emb
            idx = self.active_count
            
            try:
                self.cursor.execute("INSERT INTO metadata (id, text, meta) VALUES (?, ?, ?)", (idx, text, meta_str))
                self.conn.commit()
                self.active_count += 1
            except Exception as e:
                self.conn.rollback()
                raise RuntimeError(f"Failed to add vector: {e}")
        return idx

    def search(self, query_embedding, k=5):
        query_embedding = np.asarray(query_embedding, dtype=np.float32)
        if query_embedding.ndim != 1 or query_embedding.shape[0] != self.dim:
            raise ValueError(f"Query embedding shape {query_embedding.shape} does not match DB dimension {self.dim}")
        if np.isnan(query_embedding).any() or np.isinf(query_embedding).any():
            raise ValueError("Query embedding contains NaN or Inf values")
            
        current_count = self.active_count
        if current_count == 0: return []
        
        # L2 Normalize query
        norm = np.linalg.norm(query_embedding)
        q = (query_embedding / norm).astype(np.float32) if norm > 0 else query_embedding.astype(np.float32)
        
        # Pure Dot Product (Cosine Similarity) over the memory-mapped array
        scores = np.dot(self.vectors[:current_count], q)
        
        # O(N) Partial sort to get top K indices without a full sort (10x faster)
        # Use argpartition to find the top K, then sort only those K
        k_actual = min(k, current_count)
        top_k_unsorted_idx = np.argpartition(scores, -k_actual)[-k_actual:]
        
        # Sort the top K subset to get exactly descending order
        top_k_sorted = top_k_unsorted_idx[np.argsort(scores[top_k_unsorted_idx])[::-1]]
        
        results = []
        # Fetch metadata in a single batched O(1) query instead of O(K) individual queries
        idx_list = [int(i) for i in top_k_sorted]
        placeholders = ','.join('?' * len(idx_list))
        with self.lock:
            self.cursor.execute(f"SELECT id, text, meta FROM metadata WHERE id IN ({placeholders})", idx_list)
            rows = self.cursor.fetchall()
        
        # Reconstruct exactly in descending score order
        row_map = {row[0]: row for row in rows}
        for idx_int in idx_list:
            if idx_int in row_map:
                row = row_map[idx_int]
                try:
                    meta_dict = json.loads(row[2]) if row[2] else {}
                except Exception:
                    meta_dict = {}
                results.append({
                    "id": idx_int,
                    "score": float(scores[idx_int]),
                    "text": row[1],
                    "metadata": meta_dict
                })
        return results
