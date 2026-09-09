from .config import settings

SYSTEM = """You are DGDF-RAG, a source-grounded legal question-answering assistant.
Use ONLY the supplied evidence. Never invent statutes, sections, cases, dates or citations.
If the evidence is insufficient, say that clearly.
Give a concise answer and cite supplied evidence as [1], [2], etc.
This is an educational system, not legal advice."""

def grounded_fallback(question, fused):
    if not fused:
        return ("I could not find sufficient evidence in the indexed legal documents to answer this question. "
                "Please upload the relevant legal source.")
    parts = []
    for x in fused[:3]:
        c = x["chunk"]
        parts.append(f'[{len(parts)+1}] {c["text"][:550]} (page {c.get("page")})')
    return " ".join(parts) + "\n\nThis response is restricted to retrieved evidence and should be verified against the original source."

async def generate_answer(question, fused):
    if not settings.openai_api_key:
        return grounded_fallback(question, fused)
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        evidence = "\n\n".join(f"[{i+1}] {x['chunk']['text']} (page {x['chunk'].get('page')})"
                               for i,x in enumerate(fused))
        r = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role":"system","content":SYSTEM},
                      {"role":"user","content":f"QUESTION:\n{question}\n\nEVIDENCE:\n{evidence}"}],
            temperature=0.0,
        )
        return r.choices[0].message.content
    except Exception:
        return grounded_fallback(question, fused)
