# DGDF-RAG — Final Ready Prototype

Dynamic Graph-Dense Fusion Retrieval Framework for Domain-Specific Legal Question Answering.

## Included
- React + Vite frontend
- FastAPI backend
- Structure-aware legal chunking
- Dense TF-IDF retrieval
- Lexical/reference-aware retrieval
- Graph-aware retrieval
- Dynamic fusion strategy
- Grounded answer generation
- Evidence/citation display
- Swagger API
- Constitution of India (Santhali / Ol Chiki, as on November 2025) bundled for immediate demo use
- Article 21 parser/retrieval validation

## Mac — first run
From the extracted project folder:

```bash
./setup_mac.sh
```

Then open two Terminal windows.

Terminal 1:
```bash
./run_backend.sh
```

Terminal 2:
```bash
./run_frontend.sh
```

Open the frontend URL shown by Vite (normally `http://localhost:5173`).
Swagger is at `http://127.0.0.1:8000/docs`.

## Built-in demo
The setup script automatically indexes the bundled Constitution PDF. You do **not** need to upload it again for the initial demo.

Try:

> What does Article 21 of the Constitution of India provide?

The prototype deliberately keeps answers grounded in retrieved source text. Without an OpenAI API key, the demo mode shows the retrieved evidence rather than inventing an answer. Add an API key later when you want generated English answers.

## Project validation
Run:

```bash
./check_project.sh
```

The check verifies that Article 21 is exactly one structural chunk on page 48 and that Article 21 retrieval returns that chunk.

## Environment variables
Copy `.env.example` to `.env` if you want to configure OpenAI or external services later. Pinecone, Neo4j and MongoDB are intentionally left for the next production-integration version.

## Next version
The next phase can replace/augment the local TF-IDF and JSON storage with:
- Pinecone for vector retrieval
- Neo4j for persistent graph traversal
- MongoDB for document/metadata storage
- OpenAI or another configured LLM for answer generation
- Vercel deployment architecture
