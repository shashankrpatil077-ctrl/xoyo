import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sentence_transformers import SentenceTransformer
import PyPDF2
from services.tiny_vector_db import TinyVectorDB

class WorkspaceRAG:
    def __init__(self, workspace_path="/home/shashank/xoyo/workspace"):
        self.workspace_path = workspace_path
        self.vector_db = TinyVectorDB(path=os.path.join(workspace_path, ".rag_db"))
        # Initialize SentenceTransformer (could be replaced with ONNX for pure CPU optimization)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.tfidf = TfidfVectorizer()
        self.corpus = {}
        
        # Restore corpus from TinyVectorDB to prevent state desync
        with self.vector_db.lock:
            self.vector_db.cursor.execute("SELECT id, text, meta FROM metadata ORDER BY id ASC")
            for row in self.vector_db.cursor.fetchall():
                try:
                    import json
                    meta = json.loads(row[2])
                except:
                    meta = {}
                self.corpus[row[0]] = {"text": row[1], "meta": meta}
        
        # Fit TF-IDF for sparse retrieval if we restored any corpus
        if self.corpus:
            self.tfidf_keys = list(self.corpus.keys())
            texts = [self.corpus[k]["text"] for k in self.tfidf_keys]
            self.tfidf.fit(texts)
            self.tfidf_matrix = self.tfidf.transform(texts)
        
    def ingest_workspace(self):
        # Removed self.corpus = [] to prevent clearing while TinyVectorDB appends
        for root, _, files in os.walk(self.workspace_path):
            if ".rag_db" in root or ".git" in root: continue
            for file in files:
                filepath = os.path.join(root, file)
                text = ""
                try:
                    if file.endswith('.pdf'):
                        with open(filepath, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)
                            for page in reader.pages:
                                text += page.extract_text() + "\n"
                    # Added C/C++, Rust, Go, and Java extensions
                    elif file.endswith(('.py', '.txt', '.md', '.json', '.html', '.js', '.c', '.cpp', '.h', '.hpp', '.rs', '.go', '.java')):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            text = f.read()
                except Exception as e:
                    print(f"Failed to read {filepath}: {e}")
                
                if text.strip():
                    # Very simple chunking
                    chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
                    for idx_chunk, chunk in enumerate(chunks):
                        metadata = {"source": filepath, "chunk": idx_chunk}
                        
                        # Embed and store
                        emb = self.model.encode(chunk)
                        try:
                            idx = self.vector_db.add(chunk, emb, metadata)
                            self.corpus[idx] = {"text": chunk, "meta": metadata}
                        except Exception as e:
                            print(f"Failed to ingest chunk from {filepath}: {e}")
                        
        # Fit TF-IDF for sparse retrieval
        if self.corpus:
            self.tfidf_keys = list(self.corpus.keys())
            texts = [self.corpus[k]["text"] for k in self.tfidf_keys]
            self.tfidf.fit(texts)
            self.tfidf_matrix = self.tfidf.transform(texts)

    def _rrf_merge(self, list1, list2, k=60):
        scores = {}
        for rank, item in enumerate(list1):
            scores[item['id']] = scores.get(item['id'], 0) + 1.0 / (k + rank)
        for rank, item in enumerate(list2):
            scores[item['id']] = scores.get(item['id'], 0) + 1.0 / (k + rank)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def search(self, query: str, top_k=5):
        if not self.corpus: return []
        
        # Dense search
        q_emb = self.model.encode(query)
        dense_results = self.vector_db.search(q_emb, k=top_k*2)
        
        # Sparse search (TF-IDF)
        q_tfidf = self.tfidf.transform([query])
        from sklearn.metrics.pairwise import linear_kernel
        cosine_similarities = linear_kernel(q_tfidf, self.tfidf_matrix).flatten()
        related_docs_indices = cosine_similarities.argsort()[:-top_k*2-1:-1]
        
        sparse_results = [{"id": self.tfidf_keys[int(i)], "score": cosine_similarities[i]} for i in related_docs_indices if cosine_similarities[i] > 0]
        
        # Merge via RRF
        merged = self._rrf_merge(dense_results, sparse_results)
        
        final_results = []
        for item_id, score in merged[:top_k]:
            doc = self.corpus.get(item_id)
            if doc:
                final_results.append(doc)
            
        return final_results
