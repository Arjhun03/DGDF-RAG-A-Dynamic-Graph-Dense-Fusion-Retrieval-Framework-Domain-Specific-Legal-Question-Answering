import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import QueryRequest, QueryResponse, Citation, HealthResponse
from .storage import (
    documents,
    chunks,
    add_document,
    add_chunks,
    delete_document,
    graph,
    document_exists
)
from .document_processor import structure_aware_chunks
from .graph import rebuild_graph
from .retrieval import DenseRetriever, GraphRetriever, fuse
from .llm import generate_answer


app = FastAPI(
    title="DGDF-RAG API",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        x.strip()
        for x in settings.cors_origins.split(",")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {
        "status": "ok",
        "mode": "cloud" if settings.openai_api_key else "demo"
    }


@app.get("/api/stats")
def stats():
    g = graph()

    return {
        "documents": len(documents()),
        "chunks": len(chunks()),
        "nodes": len(g.get("nodes", [])),
        "edges": len(g.get("edges", [])),
        "mode": "OpenAI" if settings.openai_api_key else "Demo"
    }


@app.get("/api/documents")
def list_documents():
    return documents()


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    # Check supported file type
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX and TXT files are supported."
        )

    # Prevent duplicate documents
    if document_exists(filename):
        raise HTTPException(
            status_code=409,
            detail=f"Document '{filename}' has already been uploaded."
        )

    # Create document ID
    doc_id = str(uuid.uuid4())

    # Temporary file path
    tmp = (
        Path(tempfile.gettempdir())
        / f"dgdf_{doc_id}{suffix}"
    )

    # Save uploaded file temporarily
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # Process and create chunks
        cs = structure_aware_chunks(
            str(tmp),
            doc_id
        )

        # Make sure readable text was found
        if not cs:
            raise HTTPException(
                status_code=400,
                detail="No readable text found."
            )

        # Save document information
        add_document({
            "id": doc_id,
            "name": filename,
            "type": suffix[1:],
            "chunks": len(cs)
        })

        # Save chunks
        add_chunks(cs)

        # Rebuild knowledge graph
        rebuild_graph()

        return {
            "message": "Document indexed successfully",
            "document_id": doc_id,
            "chunks": len(cs)
        }

    finally:
        # Remove temporary file
        tmp.unlink(missing_ok=True)


@app.delete("/api/documents/{document_id}")
def remove_document(document_id: str):
    delete_document(document_id)
    rebuild_graph()

    return {
        "message": "Document deleted"
    }


@app.get("/api/graph")
def get_graph():
    return graph()


@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    cs = chunks()

    # No documents uploaded
    if not cs:
        return QueryResponse(
            answer="Please upload at least one legal document first.",
            confidence=0,
            citations=[],
            dense_results=[],
            graph_paths=[],
            fused_results=[],
            grounded=False
        )

    # Dense retrieval
    dense = DenseRetriever(cs).search(
        req.question,
        req.top_k * 2
    )

    # Graph retrieval
    gp = GraphRetriever(graph()).search(
        req.question,
        req.top_k * 2
    )

    # Fusion
    fr = fuse(
        dense,
        gp,
        req.top_k
    )

    # Generate grounded answer
    answer = await generate_answer(
        req.question,
        fr
    )

    # Create citations
    citations = []

    for x in fr:
        c = x["chunk"]

        doc = next(
            (
                d for d in documents()
                if d["id"] == c["document_id"]
            ),
            {"name": "Unknown"}
        )

        citations.append(
            Citation(
                document_id=c["document_id"],
                document_name=doc["name"],
                chunk_id=c["id"],
                page=c.get("page"),
                section=c.get("section"),
                score=x["fused_score"],
                excerpt=c["text"][:500]
            )
        )

    # Calculate confidence
    confidence = min(
        0.99,
        max(
            [x["fused_score"] for x in fr],
            default=0
        ) * 0.95
    )

    return QueryResponse(
        answer=answer,
        confidence=confidence,
        citations=citations,

        dense_results=[
            {
                "chunk_id": x["chunk"]["id"],
                "score": x["score"]
            }
            for x in dense
        ],

        graph_paths=gp[:req.top_k * 2],

        fused_results=[
            {
                "chunk_id": x["chunk"]["id"],
                "dense_score": x["dense_score"],
                "graph_score": x["graph_score"],
                "fused_score": x["fused_score"]
            }
            for x in fr
        ],

        grounded=bool(fr)
    )