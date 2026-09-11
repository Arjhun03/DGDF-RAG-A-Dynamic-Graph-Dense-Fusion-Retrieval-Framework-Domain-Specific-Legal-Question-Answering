from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    article: Optional[str] = None
    clause: Optional[str] = None
    score: float
    excerpt: str
    is_direct_evidence: bool = True


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=15)


class QueryResponse(BaseModel):
    answer: str
    confidence: float
    citations: List[Citation]
    related_candidates: List[Citation] = []
    dense_results: List[Dict[str, Any]]
    lexical_results: List[Dict[str, Any]]
    graph_paths: List[Dict[str, Any]]
    fused_results: List[Dict[str, Any]]
    grounded: bool
    sufficient_evidence: bool = True
    metrics: Optional[Dict[str, Any]] = None
    query_analysis: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    mode: str
    pinecone: Optional[Dict[str, Any]] = None
    neo4j: Optional[Dict[str, Any]] = None
