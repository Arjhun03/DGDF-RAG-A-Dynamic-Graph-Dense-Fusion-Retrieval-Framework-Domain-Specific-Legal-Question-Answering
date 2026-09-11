#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
DATA = ROOT / "data"
PDF = DATA / "constitution_india_santhali_2025.pdf"

sys.path.insert(0, str(BACKEND))
from app.document_processor import structure_aware_chunks
from app.storage import add_chunks, add_document, documents, chunks
from app.graph import rebuild_graph

# Start from a clean local demo index so setup is repeatable.
for name in ("documents.json", "chunks.json", "graph.json"):
    (DATA / name).unlink(missing_ok=True)

if not PDF.exists():
    raise SystemExit(f"Missing bundled PDF: {PDF}")

doc_id = "bundled-constitution-india-santhali-2025"
indexed = structure_aware_chunks(str(PDF), doc_id)
if not indexed:
    raise SystemExit("No readable text was extracted from the bundled Constitution PDF.")

add_document({
    "id": doc_id,
    "name": PDF.name,
    "filename": PDF.name,
    "type": "pdf",
    "chunks": len(indexed),
    "bundled": True,
})
add_chunks(indexed)
g = rebuild_graph()

article21 = [c for c in chunks() if c.get("article") == "21"]
print(f"Indexed chunks: {len(indexed)}")
print(f"Article 21 chunks: {len(article21)}")
if len(article21) != 1 or article21[0].get("page") != 48 or article21[0].get("chunk_type") != "article":
    raise SystemExit("FAIL: Article 21 validation did not pass.")
print(f"Graph nodes: {len(g.get('nodes', []))}")
print("Demo index ready.")
