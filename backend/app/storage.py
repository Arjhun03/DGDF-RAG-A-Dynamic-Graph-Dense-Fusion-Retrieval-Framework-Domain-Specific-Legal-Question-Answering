import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "data"
BASE.mkdir(exist_ok=True)

DOCS_FILE = BASE / "documents.json"
CHUNKS_FILE = BASE / "chunks.json"
GRAPH_FILE = BASE / "graph.json"


def _read(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def documents():
    return _read(DOCS_FILE, [])


def chunks():
    return _read(CHUNKS_FILE, [])


def graph():
    return _read(GRAPH_FILE, {"nodes": [], "edges": []})


def add_document(doc):
    arr = documents()
    arr.append(doc)
    _write(DOCS_FILE, arr)


def add_chunks(items):
    arr = chunks()
    arr.extend(items)
    _write(CHUNKS_FILE, arr)


def replace_graph(g):
    _write(GRAPH_FILE, g)


def document_exists(filename):
    """
    Check whether a document with the same filename
    has already been indexed.
    """
    return any(
        d.get("filename", "").lower() == filename.lower()
        for d in documents()
    )


def get_document(doc_id):
    """
    Return a document by ID.
    """
    for document in documents():
        if document.get("id") == doc_id:
            return document

    return None


def delete_document(doc_id):
    """
    Delete a document, its chunks, and related graph data.
    """

    # Remove document
    remaining_documents = [
        d for d in documents()
        if d.get("id") != doc_id
    ]

    # Remove chunks belonging to document
    remaining_chunks = [
        c for c in chunks()
        if c.get("document_id") != doc_id
    ]

    # Remove graph nodes belonging to document
    current_graph = graph()

    remaining_nodes = [
        node for node in current_graph.get("nodes", [])
        if node.get("document_id") != doc_id
        and doc_id not in node.get("document_ids", [])
    ]

    # Remove graph edges belonging to document
    remaining_edges = [
        edge for edge in current_graph.get("edges", [])
        if edge.get("document_id") != doc_id
        and doc_id not in edge.get("document_ids", [])
    ]

    updated_graph = {
        "nodes": remaining_nodes,
        "edges": remaining_edges
    }

    _write(DOCS_FILE, remaining_documents)
    _write(CHUNKS_FILE, remaining_chunks)
    _write(GRAPH_FILE, updated_graph)