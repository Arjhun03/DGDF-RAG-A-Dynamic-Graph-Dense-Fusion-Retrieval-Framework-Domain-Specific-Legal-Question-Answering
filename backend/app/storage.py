import json
from pathlib import Path

_ROOT_DATA = Path(__file__).resolve().parents[2] / "data"
_BACKEND_DATA = Path(__file__).resolve().parents[1] / "data"

if _BACKEND_DATA.exists() and (_BACKEND_DATA / "chunks.json").exists():
    BASE = _BACKEND_DATA
elif _ROOT_DATA.exists() and (_ROOT_DATA / "chunks.json").exists():
    BASE = _ROOT_DATA
else:
    BASE = _BACKEND_DATA if _BACKEND_DATA.exists() else _ROOT_DATA

BASE.mkdir(parents=True, exist_ok=True)

DOCS_FILE = BASE / "documents.json"
CHUNKS_FILE = BASE / "chunks.json"
GRAPH_FILE = BASE / "graph.json"


def _read(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
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


def replace_graph(value):
    _write(GRAPH_FILE, value)


def document_exists(filename):
    target = str(filename or "").strip().lower()
    return any(str(d.get("name", d.get("filename", ""))).lower() == target for d in documents())


def get_document(doc_id):
    for doc in documents():
        if doc.get("id") == doc_id:
            return doc
    return None


def delete_document(doc_id):
    _write(DOCS_FILE, [d for d in documents() if d.get("id") != doc_id])
    _write(CHUNKS_FILE, [c for c in chunks() if c.get("document_id") != doc_id])

    current = graph()
    nodes = [
        node for node in current.get("nodes", [])
        if doc_id not in node.get("document_ids", [])
    ]
    # Rebuilding the graph after deletion is safer than trying to surgically
    # remove every edge here.
    _write(GRAPH_FILE, {"nodes": nodes, "edges": []})
