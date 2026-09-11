import re


def extract_legal_references(query: str):
    query = str(query or "")
    patterns = {
        "articles": r"\barticles?\s+([0-9A-Za-z().-]+)",
        "sections": r"\bsections?\s+([0-9A-Za-z().-]+)",
        "clauses": r"\bclauses?\s+([0-9A-Za-z().-]+)",
        "rules": r"\brules?\s+([0-9A-Za-z().-]+)",
        "parts": r"\bparts?\s+([0-9A-Za-z().-]+)",
        "chapters": r"\bchapters?\s+([0-9A-Za-z().-]+)",
    }
    result = {key: [] for key in patterns}
    for key, pattern in patterns.items():
        for value in re.findall(pattern, query, flags=re.IGNORECASE):
            value = value.strip().lower()
            if value and value not in result[key]:
                result[key].append(value)
    return result


def analyze_query(query: str):
    query = str(query or "").strip()
    refs = extract_legal_references(query)
    has_reference = any(refs.values())
    lower = query.lower()

    # Intent Classification
    if any(k in lower for k in ("compare", "difference between", "distinguish", "vs", "versus")):
        intent = "COMPARISON"
        traversal_depth = 2
        strategy_name = "Comparative Traversal"
        strategy = {
            "dense_weight": 0.30,
            "lexical_weight": 0.25,
            "graph_weight": 0.45,
            "rerank_top_k": 6,
        }
    elif any(k in lower for k in ("relationship", "related to", "connected to", "connection between", "linked with", "overlap")):
        intent = "RELATIONSHIP"
        traversal_depth = 2
        strategy_name = "Relationship Graph Traversal"
        strategy = {
            "dense_weight": 0.25,
            "lexical_weight": 0.25,
            "graph_weight": 0.50,
            "rerank_top_k": 6,
        }
    elif any(k in lower for k in ("case", "judgment", "ruling", "court", "precedent", "supreme court", "high court")):
        intent = "CASE_LAW"
        traversal_depth = 2
        strategy_name = "Jurisprudential Traversal"
        strategy = {
            "dense_weight": 0.40,
            "lexical_weight": 0.30,
            "graph_weight": 0.30,
            "rerank_top_k": 5,
        }
    elif any(lower.startswith(w) for w in ("what is", "define", "meaning of", "what does", "who is")) or (has_reference and "explain" not in lower):
        intent = "DEFINITION"
        traversal_depth = 1
        strategy_name = "Definitive Reference Lookup"
        strategy = {
            "dense_weight": 0.20,
            "lexical_weight": 0.60,
            "graph_weight": 0.20,
            "exact_reference_priority": True,
            "rerank_top_k": 5,
        }
    else:
        intent = "EXPLANATION"
        traversal_depth = 1
        strategy_name = "Substantive Explanation Fusion"
        strategy = {
            "dense_weight": 0.45,
            "lexical_weight": 0.35,
            "graph_weight": 0.20,
            "rerank_top_k": 5,
        }

    return {
        "query": query,
        "query_type": intent.lower(),
        "intent": intent,
        "strategy_name": strategy_name,
        "traversal_depth": traversal_depth,
        "candidate_k": 20,
        "references": refs,
        "strategy": strategy,
    }
