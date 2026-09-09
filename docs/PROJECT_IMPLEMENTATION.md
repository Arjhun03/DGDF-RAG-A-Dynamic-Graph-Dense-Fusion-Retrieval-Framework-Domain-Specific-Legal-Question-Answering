# DGDF-RAG Implementation Mapping

| Project concept | Implementation |
|---|---|
| Structure-aware chunking | `backend/app/document_processor.py` |
| Dense retrieval | `backend/app/retrieval.py` |
| Knowledge graph mapping | `backend/app/graph.py` |
| Graph retrieval | `GraphRetriever` |
| Dynamic hybrid fusion | `fuse()` |
| Grounded generation | `backend/app/llm.py` |
| Source provenance | Evidence/citation UI |
| Full-stack application | React + FastAPI |
| Document ingestion | PDF/DOCX/TXT |
| Demo persistence | JSON files in `data/` |
| Cloud integration points | OpenAI, MongoDB, Pinecone, Neo4j |

## Final demonstration
1. Start backend and frontend.
2. Upload a legal Act.
3. Show document/chunk/graph counts.
4. Ask a section-based question.
5. Show Answer, Evidence and Graph paths.
6. Explain dense retrieval, graph expansion and 70/30 fusion.
7. With `OPENAI_API_KEY`, demonstrate generated grounded answers; without it, demonstrate deterministic evidence extraction.

## Claim discipline
The presentation describes hallucination-free generation. In the viva, phrase this as a design goal/risk reduction mechanism, not a guarantee.
