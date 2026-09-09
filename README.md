# DGDF-RAG — Dynamic Graph-Dense Fusion Retrieval Framework

Final-year-project implementation of **DGDF-RAG: A Dynamic Graph-Dense Fusion Retrieval Framework for Domain-Specific Legal Question Answering**.

## Included
- React + Vite frontend
- FastAPI backend
- PDF/DOCX/TXT ingestion
- Structure-aware legal chunking
- Dense retrieval
- Legal entity/relationship graph
- Dynamic dense + graph fusion
- Grounded answer generation
- Evidence/citation panel
- Graph-path panel
- Demo mode that works without paid APIs
- Optional OpenAI, MongoDB, Pinecone and Neo4j integration points

## Run

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally http://localhost:5173.

Copy `.env.example` to `.env` if you want cloud services. Without an OpenAI key the app uses a deterministic evidence-grounded fallback, so it is still demonstrable on a college laptop.

## API
- GET `/api/health`
- GET `/api/stats`
- GET `/api/documents`
- POST `/api/documents/upload`
- POST `/api/query`
- GET `/api/graph`
- DELETE `/api/documents/{document_id}`

## Academic note
The application is an educational/research prototype, not legal advice. “Hallucination-free” should be presented as a design objective/risk-reduction goal rather than a mathematical guarantee. The system refuses to fabricate an answer when no evidence is retrieved.
