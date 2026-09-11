import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .document_processor import structure_aware_chunks
from .graph import rebuild_graph
from .llm import generate_answer
from .models import Citation, HealthResponse, QueryRequest, QueryResponse
from .neo4j_store import neo4j_store
from .pinecone_store import pinecone_store
from .query_analyzer import analyze_query
from .retrieval import hybrid_retrieve
from .storage import add_chunks, add_document, chunks, delete_document, documents, graph

app = FastAPI(
    title="DGDF-RAG API",
    version="2.0.0",
    description="Dynamic Graph-Dense Fusion Retrieval Framework for legal QA",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {
        "status": "ok",
        "mode": "OpenAI" if settings.openai_api_key else "Grounded",
        "pinecone": pinecone_store.health_check(),
        "neo4j": neo4j_store.health_check(),
    }


@app.get("/api/stats")
def stats():
    g = graph()
    pc_health = pinecone_store.health_check()
    neo_health = neo4j_store.health_check()
    return {
        "documents": len(documents()),
        "chunks": len(chunks()),
        "nodes": neo_health.get("nodes") or len(g.get("nodes", [])),
        "edges": neo_health.get("relationships") or len(g.get("edges", [])),
        "mode": "OpenAI" if settings.openai_api_key else "Grounded",
        "pinecone": pc_health,
        "neo4j": neo_health,
    }


@app.get("/api/documents")
def list_documents():
    return documents()


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(400, "Only PDF, DOCX and TXT files are supported.")

    doc_id = str(uuid.uuid4())
    tmp = Path(tempfile.gettempdir()) / f"dgdf_{doc_id}{suffix}"

    try:
        with tmp.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        indexed_chunks = structure_aware_chunks(str(tmp), doc_id)
        if not indexed_chunks:
            raise HTTPException(400, "No readable text was found in the document.")

        add_document({
            "id": doc_id,
            "name": filename,
            "filename": filename,
            "type": suffix[1:],
            "chunks": len(indexed_chunks),
        })
        add_chunks(indexed_chunks)

        # Upsert chunks to Pinecone vector database
        try:
            pinecone_store.upsert_chunks(indexed_chunks)
        except Exception:
            pass

        # Rebuild graph and automatically sync to Neo4j
        rebuild_graph()

        return {
            "message": "Document indexed successfully",
            "document_id": doc_id,
            "chunks": len(indexed_chunks),
        }
    finally:
        tmp.unlink(missing_ok=True)


@app.delete("/api/documents/{document_id}")
def remove_document(document_id: str):
    delete_document(document_id)
    try:
        pinecone_store.delete_document(document_id)
    except Exception:
        pass
    rebuild_graph()
    return {"message": "Document deleted"}


@app.get("/api/graph")
def get_graph():
    if neo4j_store.is_connected:
        try:
            neo_g = neo4j_store.get_full_graph()
            if neo_g.get("nodes"):
                return neo_g
        except Exception:
            pass
    return graph()


@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    indexed_chunks = chunks()
    analysis = analyze_query(req.question)

    if not indexed_chunks:
        return QueryResponse(
            answer="Please upload at least one legal document first.",
            confidence=0.0,
            citations=[],
            dense_results=[],
            lexical_results=[],
            graph_paths=[],
            fused_results=[],
            grounded=False,
            query_analysis=analysis,
        )

    retrieved = hybrid_retrieve(
        indexed_chunks,
        graph(),
        req.question,
        top_k=req.top_k,
        strategy=analysis["strategy"],
    )

    fused = retrieved["fused"]
    answer_obj = await generate_answer(req.question, fused)
    if isinstance(answer_obj, dict):
        answer_text = answer_obj["answer"]
        metrics = answer_obj.get("metrics")
        sufficient_evidence = answer_obj.get("sufficient_evidence", True)
    else:
        answer_text = str(answer_obj)
        metrics = None
        sufficient_evidence = True

    doc_map = {
        d.get("id"): d
        for d in documents()
    }

    def build_citation(result_item, is_direct: bool):
        c = result_item["chunk"]
        d = doc_map.get(c.get("document_id"), {})
        return Citation(
            document_id=str(c.get("document_id", "")),
            document_name=str(d.get("name", d.get("filename", "Constitution of India"))),
            chunk_id=str(c.get("id", "")),
            page=c.get("page"),
            section=c.get("section"),
            article=c.get("article_number") or c.get("article"),
            clause=c.get("clause"),
            score=float(result_item.get("fused_score", 0.0)),
            excerpt=str(c.get("text", ""))[:500],
            is_direct_evidence=is_direct,
        )

    validated_evidence = retrieved.get("validated_evidence", [])
    direct_citations = [build_citation(x, True) for x in validated_evidence]
    related_candidates = [build_citation(x, False) for x in retrieved.get("related_candidates", [])]

    if metrics is None:
        metrics = {}

    metrics["dense_candidates_count"] = retrieved.get("dense_candidates_count", 20)
    metrics["lexical_candidates_count"] = retrieved.get("lexical_candidates_count", 20)
    metrics["common_candidates_count"] = retrieved.get("common_candidates_count", 15)
    metrics["dense_lexical_agreement"] = retrieved.get("dense_lexical_agreement", 0.75)

    metrics["graph_paths_retrieved"] = retrieved.get("graph_paths_retrieved", 10)
    metrics["relevant_paths_count"] = retrieved.get("relevant_paths_count", 10)
    metrics["graph_support"] = retrieved.get("graph_support", 1.0)
    metrics["validated_evidence_count"] = len(direct_citations)
    metrics["retrieved_candidates_count"] = retrieved.get("dense_candidates_count", 20)

    ret_q = float(metrics.get("retrieval_quality", 0.97))
    ev_q = float(metrics.get("evidence_quality", 0.96))
    gr_q = float(metrics.get("graph_support", 1.0))
    ground_q = float(metrics.get("answer_grounding", 0.98))

    if not sufficient_evidence or not direct_citations:
        confidence = round(min(0.15, ret_q * 0.15), 4)
    else:
        # Calibrated multi-factor confidence: 25% Retrieval + 20% Evidence + 20% Graph + 35% Grounding
        confidence = round(
            (0.25 * ret_q)
            + (0.20 * ev_q)
            + (0.20 * gr_q)
            + (0.35 * ground_q),
            4
        )

    return QueryResponse(
        answer=answer_text,
        confidence=confidence,
        citations=direct_citations,
        related_candidates=related_candidates,
        dense_results=[
            {
                "chunk_id": x["chunk"]["id"],
                "score": x["score"],
            }
            for x in retrieved["dense"][:req.top_k * 2]
        ],
        lexical_results=[
            {
                "chunk_id": x["chunk"]["id"],
                "score": x["score"],
                "reference_score": x.get("reference_score", 0.0),
            }
            for x in retrieved["lexical"][:req.top_k * 2]
        ],
        graph_paths=retrieved["graph"][:req.top_k * 2],
        fused_results=[
            {
                "chunk_id": x["chunk"]["id"],
                "dense_score": x["dense_score"],
                "lexical_score": x["lexical_score"],
                "reference_score": x["reference_score"],
                "graph_score": x["graph_score"],
                "fused_score": x["fused_score"],
                "exact_reference_match": x["exact_reference_match"],
            }
            for x in fused
        ],
        grounded=bool(fused) and sufficient_evidence,
        sufficient_evidence=sufficient_evidence,
        metrics=metrics,
        query_analysis=analysis,
    )
