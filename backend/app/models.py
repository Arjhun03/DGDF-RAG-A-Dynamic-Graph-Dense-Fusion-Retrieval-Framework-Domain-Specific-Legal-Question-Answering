from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    score: float
    excerpt: str

class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=15)

class QueryResponse(BaseModel):
    answer: str
    confidence: float
    citations: List[Citation]
    dense_results: List[Dict[str, Any]]
    graph_paths: List[Dict[str, Any]]
    fused_results: List[Dict[str, Any]]
    grounded: bool

class HealthResponse(BaseModel):
    status: str
    mode: str
