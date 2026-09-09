from .document_processor import extract_entities
from .storage import graph, replace_graph, chunks

def rebuild_graph():
    nodes, edges, index = [], [], {}
    def node(nt, value, chunk_id):
        key = (nt, value.lower())
        if key not in index:
            index[key] = {"id": f"{nt}:{value.lower()}", "type": nt, "value": value, "chunk_ids": []}
            nodes.append(index[key])
        if chunk_id not in index[key]["chunk_ids"]:
            index[key]["chunk_ids"].append(chunk_id)
        return index[key]["id"]

    for c in chunks():
        ents = extract_entities(c["text"])
        for e in ents:
            node(e["type"], e["value"], c["id"])
        for i, a in enumerate(ents):
            for b in ents[i+1:]:
                aid, bid = node(a["type"],a["value"],c["id"]), node(b["type"],b["value"],c["id"])
                relation = "related_to"
                if a["type"]=="Act" and b["type"]=="Section": relation="contains"
                elif a["type"]=="Section" and b["type"]=="Clause": relation="contains"
                elif a["type"]=="Article" and b["type"]=="Clause": relation="contains"
                edges.append({"source":aid,"target":bid,"relation":relation,"chunk_id":c["id"]})

    seen, dedup = set(), []
    for e in edges:
        k=(e["source"],e["target"],e["relation"],e["chunk_id"])
        if k not in seen: seen.add(k); dedup.append(e)
    g={"nodes":nodes,"edges":dedup}
    replace_graph(g)
    return g
