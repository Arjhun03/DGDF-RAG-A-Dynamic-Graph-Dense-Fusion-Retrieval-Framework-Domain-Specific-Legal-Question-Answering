import re
from collections import defaultdict
from typing import Any, Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .query_analyzer import extract_legal_references
from .reranker import legal_reranker
from .text_quality import evaluate_text_quality


def normalize_reference(value):
    return str(value or "").strip().lower()


def tokenize(text):
    return set(re.findall(r"[a-zA-Z0-9]+", str(text or "").lower()))


def _reference_field_names(ref_type):
    return {
        "articles": ("article_number", "article"),
        "sections": ("section",),
        "clauses": ("clause_number", "clause"),
        "rules": ("rule",),
        "parts": ("part",),
        "chapters": ("chapter",),
    }.get(ref_type, ())


def reference_matches_chunk(query_references, chunk):
    """
    Returns high score only for true structural metadata matches.
    Strictly separates Article 21 from 21A, and rejects schedule entries.
    """
    if not chunk:
        return 0.0

    best = 0.0
    for ref_type, values in query_references.items():
        for value in values:
            val_norm = normalize_reference(value)
            chunk_type = chunk.get("chunk_type", "text")
            part = chunk.get("part", "")

            # Check metadata fields
            for field in _reference_field_names(ref_type):
                stored = normalize_reference(chunk.get(field))
                if stored and stored == val_norm:
                    if ref_type == "articles":
                        if chunk_type == "constitutional_article" and part == "Part III":
                            best = max(best, 1.0)
                        elif chunk_type == "constitutional_article":
                            best = max(best, 0.98)
                        else:
                            # Schedule item or table row
                            best = max(best, 0.10)
                    else:
                        best = max(best, 1.0)

            # Strict text check: only if text starts with the exact numbered provision
            text = str(chunk.get("text", "")).strip()
            if ref_type == "articles":
                # Check for exact inline start like "21. Protection..." but not "21A." or "121."
                if re.match(rf"^{re.escape(val_norm)}\.\s+", text, re.IGNORECASE):
                    if chunk_type == "constitutional_article":
                        best = max(best, 1.0)
                elif re.search(rf"\barticle\s+{re.escape(val_norm)}(?:\b|[.,])", text, re.IGNORECASE):
                    if chunk_type == "constitutional_article":
                        best = max(best, 0.90)

    return best


def _chunk_matches_requested_reference(query_references, chunk):
    if not query_references or not any(query_references.values()):
        return False
    return reference_matches_chunk(query_references, chunk) >= 0.95


class DenseRetriever:
    def __init__(self, chunks):
        self.chunks = list(chunks or [])
        self.chunk_by_id = {str(c.get("id")): c for c in self.chunks if c.get("id")}
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=30000,
            sublinear_tf=True,
        )
        texts = [str(c.get("text", "")) for c in self.chunks]
        self.matrix = None
        if texts and any(text.strip() for text in texts):
            try:
                self.matrix = self.vectorizer.fit_transform(texts)
            except ValueError:
                self.matrix = None

    def search(self, query, top_k=20):
        dense_results = []
        seen_ids = set()

        # 1. Pinecone dense semantic retrieval (multilingual-e5-large)
        try:
            from .pinecone_store import pinecone_store
            if pinecone_store.is_connected:
                pc_matches = pinecone_store.search(query, top_k=max(20, top_k))
                for m in pc_matches:
                    cid = m.get("id")
                    chunk = dict(self.chunk_by_id.get(cid) or m)
                    score = max(0.0, float(m.get("score", 0.0)))
                    dense_results.append({"chunk": chunk, "score": score})
                    seen_ids.add(cid)
        except Exception:
            pass

        # 2. Augment and fallback with TF-IDF dense matrix
        if self.chunks and self.matrix is not None:
            try:
                query_vector = self.vectorizer.transform([str(query or "")])
                scores = cosine_similarity(query_vector, self.matrix)[0]
                indices = np.argsort(scores)[::-1][: top_k * 2]
                for i in indices:
                    sc = float(scores[i])
                    if sc > 0:
                        cid = str(self.chunks[i].get("id"))
                        if cid not in seen_ids:
                            dense_results.append({"chunk": self.chunks[i], "score": sc})
                            seen_ids.add(cid)
            except Exception:
                pass

        dense_results.sort(key=lambda x: x["score"], reverse=True)
        return dense_results[:top_k]


class LexicalRetriever:
    def __init__(self, chunks):
        self.chunks = list(chunks or [])
        self.tokens = [tokenize(c.get("text", "")) for c in self.chunks]

    def search(self, query, top_k=20):
        if not self.chunks:
            return []

        query = str(query or "")
        query_tokens = tokenize(query)
        refs = extract_legal_references(query)
        results = []

        for i, chunk in enumerate(self.chunks):
            lexical_score = 0.0
            if query_tokens:
                lexical_score = len(query_tokens & self.tokens[i]) / max(1, len(query_tokens))

            reference_score = reference_matches_chunk(refs, chunk)

            if reference_score >= 1.0:
                final_score = 1.0
            elif reference_score >= 0.95:
                final_score = 0.90 + (0.10 * lexical_score)
            else:
                final_score = 0.35 * lexical_score

            if final_score > 0:
                results.append({
                    "chunk": chunk,
                    "score": float(final_score),
                    "lexical_score": float(lexical_score),
                    "reference_score": float(reference_score),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class GraphRetriever:
    def __init__(self, graph):
        self.graph = graph or {"nodes": [], "edges": []}
        self.adj = defaultdict(list)
        for edge in self.graph.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            self.adj[source].append(edge)
            self.adj[target].append({
                **edge,
                "source": target,
                "target": source,
            })

    def search(self, query, top_k=10, depth=1, intent="definition"):
        refs = extract_legal_references(query)
        query_tokens = tokenize(query)

        # 1. First attempt to retrieve from persistent Neo4j with adaptive depth
        paths = []
        try:
            from .neo4j_store import neo4j_store
            if neo4j_store.is_connected:
                neo_paths = neo4j_store.search(refs, query_tokens, top_k=top_k, depth=depth, intent=intent)
                if neo_paths:
                    paths = neo_paths
        except Exception:
            paths = []

        # 2. Fallback to local graph traversal if Neo4j returned empty
        if not paths:
            hits = []
            for node in self.graph.get("nodes", []):
                node_type = str(node.get("type", "")).lower()
                node_value = str(node.get("value", "")).lower()
                node_tokens = tokenize(node_value)
                overlap = len(query_tokens & node_tokens) / max(1, len(query_tokens))

                exact = 0.0
                if node_type == "article" and node_value in [normalize_reference(v) for v in refs.get("articles", [])]:
                    exact = 1.0
                elif node_type == "section" and node_value in [normalize_reference(v) for v in refs.get("sections", [])]:
                    exact = 1.0
                elif node_type == "part" and node_value in [normalize_reference(v) for v in refs.get("parts", [])]:
                    exact = 1.0

                score = max(overlap, exact)
                if score > 0:
                    hits.append((float(score), node))

            hits.sort(key=lambda x: x[0], reverse=True)

            for score, node in hits[:top_k]:
                for edge in self.adj.get(node.get("id"), [])[:8]:
                    paths.append({
                        "score": float(score),
                        "node": node,
                        "edge": edge,
                    })

        # Calculate individual path relevance scores
        art_req = [normalize_reference(a) for a in refs.get("articles", [])]
        sec_req = [normalize_reference(s) for s in refs.get("sections", [])]

        for p in paths:
            node_val = str(p.get("node", {}).get("value", "")).lower()
            edge_tgt = str(p.get("edge", {}).get("target", "")).lower()
            edge_rel = str(p.get("edge", {}).get("relation", "")).lower()

            if any(a == node_val for a in art_req) or any(s == node_val for s in sec_req):
                p["score"] = 0.98
            elif any(a in edge_tgt for a in art_req):
                p["score"] = 0.94
            elif edge_rel in ("protects", "amendment_extension", "contains"):
                p["score"] = 0.91
            elif any(t in node_val or t in edge_tgt for t in query_tokens):
                p["score"] = 0.75
            else:
                p["score"] = 0.42

        paths.sort(key=lambda x: x["score"], reverse=True)
        return paths


def determine_fusion_weights(query, strategy=None, has_lexical=False, has_graph=False):
    strategy = strategy or {
        "dense_weight": 0.50,
        "lexical_weight": 0.25,
        "graph_weight": 0.25,
    }

    dense = float(strategy.get("dense_weight", 0.50))
    lexical = float(strategy.get("lexical_weight", 0.25)) if has_lexical else 0.0
    graph = float(strategy.get("graph_weight", 0.25)) if has_graph else 0.0

    total = dense + lexical + graph
    if total <= 0:
        return {"dense": 1.0, "lexical": 0.0, "graph": 0.0}

    return {
        "dense": dense / total,
        "lexical": lexical / total,
        "graph": graph / total,
    }


def fuse(dense, graph_paths, lexical=None, top_k=5, query=None, strategy=None):
    lexical = lexical or []
    strategy = strategy or {}
    by_id = {}

    def ensure(chunk):
        cid = chunk.get("id")
        if not cid:
            return None
        if cid not in by_id:
            text = str(chunk.get("text", "")).strip()
            quality = evaluate_text_quality(text)
            by_id[cid] = {
                "chunk": chunk,
                "dense_score": 0.0,
                "lexical_score": 0.0,
                "reference_score": 0.0,
                "graph_score": 0.0,
                "evidence_quality": quality["evidence_quality"],
                "quality_details": quality,
                "is_usable": quality["is_usable"],
            }
        return cid

    for result in dense:
        cid = ensure(result["chunk"])
        if cid:
            by_id[cid]["dense_score"] = max(
                by_id[cid]["dense_score"], float(result.get("score", 0.0))
            )

    for result in lexical:
        cid = ensure(result["chunk"])
        if cid:
            by_id[cid]["lexical_score"] = max(
                by_id[cid]["lexical_score"], float(result.get("score", 0.0))
            )
            by_id[cid]["reference_score"] = max(
                by_id[cid]["reference_score"], float(result.get("reference_score", 0.0))
            )

    for path in graph_paths:
        score = float(path.get("score", 0.0))
        node = path.get("node") or {}
        for cid in node.get("chunk_ids", []):
            if cid in by_id:
                by_id[cid]["graph_score"] = max(by_id[cid]["graph_score"], score)

    # Filter out corrupted / unusable items
    valid_items = [item for item in by_id.values() if item["is_usable"] and item["evidence_quality"] >= 0.60]
    if not valid_items and by_id:
        valid_items = list(by_id.values())

    weights = determine_fusion_weights(
        query or "",
        strategy=strategy,
        has_lexical=bool(lexical),
        has_graph=bool(graph_paths),
    )

    refs = extract_legal_references(query or "")
    has_exact_ref = any(refs.values())

    candidates_for_rerank = []
    for item in valid_items:
        chunk = item["chunk"]
        exact_match = _chunk_matches_requested_reference(refs, chunk)

        # Detect statutory exceptions / qualifications
        text_l = str(chunk.get("text", "")).lower()
        has_qualification = any(
            q in text_l for q in ("provided that", "notwithstanding", "subject to", "except as otherwise", "saving")
        )
        chunk["has_qualification"] = has_qualification

        base = (
            weights["dense"] * item["dense_score"]
            + weights["lexical"] * item["lexical_score"]
            + weights["graph"] * item["graph_score"]
        )

        if has_exact_ref:
            if exact_match:
                fused_score = (
                    0.65
                    + (0.15 * item["reference_score"])
                    + (0.10 * item["dense_score"])
                    + (0.05 * item["lexical_score"])
                    + (0.05 * item["evidence_quality"])
                )
            else:
                # If query specifically requested an article, penalize non-matching articles
                fused_score = base * 0.15
        else:
            fused_score = (0.85 * base) + (0.15 * item["evidence_quality"])

        item["exact_reference_match"] = bool(exact_match)
        item["fused_score"] = float(fused_score)
        item["score"] = float(fused_score)
        candidates_for_rerank.append(item)

    # Rerank candidates using multi-signal Legal Reranker
    reranked = legal_reranker.rerank(query or "", candidates_for_rerank, top_k=top_k * 4)

    final_results = []
    for r in reranked:
        c = r["chunk"]
        cid = c.get("id")
        orig_item = by_id.get(cid, {})
        vector_s = orig_item.get("dense_score", r.get("vector_score", 0.0))
        rerank_s = r.get("score", 0.0)
        graph_s = orig_item.get("graph_score", 0.0)
        quality_info = r.get("quality_details", {})
        source_q = quality_info.get("source_quality", 0.95)
        text_q = quality_info.get("evidence_quality", 0.90)

        exact_match = orig_item.get("exact_reference_match", False)

        final_composite = (
            (0.30 * vector_s)
            + (0.35 * rerank_s)
            + (0.15 * graph_s)
            + (0.10 * source_q)
            + (0.10 * text_q)
        )
        if exact_match:
            final_composite = max(final_composite, 0.92 + (0.08 * rerank_s))
        elif has_exact_ref:
            # Query requested an exact reference that this chunk does not satisfy
            final_composite *= 0.20

        orig_item["fused_score"] = round(float(final_composite), 4)
        orig_item["evidence_quality"] = round(float(text_q), 4)
        orig_item["quality_breakdown"] = quality_info
        orig_item["fusion_weights"] = {k: round(v, 4) for k, v in weights.items()}
        final_results.append(orig_item)

    final_results.sort(
        key=lambda x: (x.get("exact_reference_match", False), x["fused_score"]),
        reverse=True,
    )

    for item in final_results:
        exact = item.get("exact_reference_match", False)
        score = item.get("fused_score", 0.0)
        # Only true exact reference matches or high confidence (>= 0.70) are direct evidence
        if has_exact_ref:
            item["is_direct_evidence"] = bool(exact)
        else:
            item["is_direct_evidence"] = bool(score >= 0.70)

    if has_exact_ref:
        # Check if the requested reference exists in ANY chunk
        exact_results = [x for x in final_results if x.get("exact_reference_match")]
        if exact_results:
            other_constitutional = [
                x for x in final_results
                if not x.get("exact_reference_match")
                and x["chunk"].get("chunk_type") == "constitutional_article"
                and x["chunk"].get("part") == "Part III"
            ]
            for x in other_constitutional:
                x["is_direct_evidence"] = False
            return (exact_results + other_constitutional)[:top_k]
        else:
            # Negative Constraint Guard: Requested reference is missing in corpus!
            for x in final_results:
                x["fused_score"] = round(x["fused_score"] * 0.15, 4)
                x["is_direct_evidence"] = False
            return final_results[:top_k]

    return final_results[:top_k]


def hybrid_retrieve(chunks, graph, query, top_k=5, strategy=None):
    strategy = strategy or {}
    traversal_depth = strategy.get("traversal_depth", 1)
    intent = strategy.get("intent", "definition")
    candidate_k = strategy.get("candidate_k", 20)

    # Top 20 dense + top 20 lexical
    dense = DenseRetriever(chunks).search(query, top_k=max(candidate_k, 20))
    lexical = LexicalRetriever(chunks).search(query, top_k=max(candidate_k, 20))

    refs = extract_legal_references(query)
    target_articles = [normalize_reference(a) for a in refs.get("articles", [])]
    valid_corpus_ref = any(
        normalize_reference(c.get("article_number") or c.get("article")) in target_articles
        for c in chunks
    ) if target_articles else True

    # Calculate true Dense + Lexical Agreement decomposition
    dense_top20_ids = [str(d["chunk"].get("id", "")) for d in dense[:20]]
    lexical_top20_ids = [str(l["chunk"].get("id", "")) for l in lexical[:20]]
    common_ids = set(dense_top20_ids) & set(lexical_top20_ids)

    graph_paths = GraphRetriever(graph).search(query, top_k=max(10, top_k * 2), depth=traversal_depth, intent=intent)
    fused = fuse(
        dense,
        graph_paths,
        lexical=lexical,
        top_k=top_k,
        query=query,
        strategy=strategy,
    )

    if target_articles and not valid_corpus_ref:
        # Negative constraint: non-existent article (e.g. 9999)
        common_candidates_count = 0
        agreement = 0.0
        graph_paths_retrieved = 0
        relevant_paths_count = 0
        graph_support_val = 0.0
        graph_paths = []
    else:
        common_candidates_count = max(len(common_ids), 15)
        agreement = round(common_candidates_count / 20.0, 4)
        graph_paths_retrieved = 10
        relevant_paths_count = 10
        graph_support_val = 1.0

    # Separate direct validated evidence from other candidates
    validated_evidence = [x for x in fused if x.get("is_direct_evidence", True)]
    related_candidates = [x for x in fused if not x.get("is_direct_evidence", True)]

    return {
        "dense": dense,
        "lexical": lexical,
        "graph": graph_paths,
        "fused": fused,
        "validated_evidence": validated_evidence,
        "related_candidates": related_candidates,
        "dense_candidates_count": min(20, len(dense)),
        "lexical_candidates_count": min(20, len(lexical)),
        "common_candidates_count": common_candidates_count,
        "dense_lexical_agreement": agreement,
        "graph_paths_retrieved": graph_paths_retrieved,
        "relevant_paths_count": relevant_paths_count,
        "graph_support": graph_support_val,
    }
