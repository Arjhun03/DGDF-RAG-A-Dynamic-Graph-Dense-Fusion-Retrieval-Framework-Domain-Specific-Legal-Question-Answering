import re
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class DenseRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1,2), max_features=30000)
        texts = [c["text"] for c in chunks]
        self.matrix = self.vectorizer.fit_transform(texts) if texts else None

    def search(self, query, top_k=5):
        if not self.chunks or self.matrix is None:
            return []
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        idx = np.argsort(scores)[::-1][:top_k]
        return [{"chunk": self.chunks[i], "score": float(scores[i])} for i in idx if scores[i] > 0]

def tokenize(s):
    return set(re.findall(r'[a-zA-Z0-9]+', s.lower()))

class GraphRetriever:
    def __init__(self, graph):
        self.graph = graph
        self.adj = defaultdict(list)
        for e in graph.get("edges", []):
            self.adj[e["source"]].append(e)
            self.adj[e["target"]].append({**e, "source": e["target"], "target": e["source"]})

    def search(self, query, top_k=8):
        q = tokenize(query)
        hits = []
        for n in self.graph.get("nodes", []):
            score = len(q & tokenize(n["value"])) / max(1, len(q))
            if score > 0:
                hits.append((score, n))
        hits.sort(reverse=True, key=lambda x:x[0])
        paths = []
        for score, n in hits[:top_k]:
            for e in self.adj.get(n["id"], [])[:5]:
                paths.append({"score": float(score), "node": n, "edge": e})
        return paths

def fuse(dense, graph_paths, top_k=5):
    by_id = {}
    for r in dense:
        c = r["chunk"]
        by_id[c["id"]] = {"chunk": c, "dense_score": r["score"], "graph_score": 0.0}
    for gp in graph_paths:
        for cid in gp["node"].get("chunk_ids", []):
            if cid in by_id:
                by_id[cid]["graph_score"] = max(by_id[cid]["graph_score"], gp["score"])
    results = []
    for item in by_id.values():
        d, g = item["dense_score"], item["graph_score"]
        item["fused_score"] = float(0.7*d + 0.3*g)
        results.append(item)
    results.sort(key=lambda x:x["fused_score"], reverse=True)
    return results[:top_k]
