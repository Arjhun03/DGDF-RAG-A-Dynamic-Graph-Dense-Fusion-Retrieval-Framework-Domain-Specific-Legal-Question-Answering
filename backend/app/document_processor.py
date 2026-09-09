import re, uuid
from pathlib import Path
import fitz
from docx import Document

SECTION_RE = re.compile(r'\b(?:section|sec\.?)\s+([0-9A-Za-z().-]+)', re.I)
ARTICLE_RE = re.compile(r'\barticle\s+([0-9A-Za-z().-]+)', re.I)
CLAUSE_RE = re.compile(r'\bclause\s+([0-9A-Za-z().-]+)', re.I)
ACT_RE = re.compile(r'([A-Z][A-Za-z0-9,&()\- ]{2,100}\bAct(?:,?\s+\d{4})?)', re.I)

def extract_pages(path: str):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        return [{"page": i+1, "text": page.get_text("text")} for i, page in enumerate(doc)]
    if p.suffix.lower() == ".docx":
        doc = Document(path)
        return [{"page": 1, "text": "\n".join(x.text for x in doc.paragraphs)}]
    if p.suffix.lower() == ".txt":
        return [{"page": 1, "text": p.read_text(encoding="utf-8", errors="ignore")}]
    raise ValueError("Supported files: PDF, DOCX, TXT")

def structure_aware_chunks(path: str, document_id: str):
    pages = extract_pages(path)
    chunks = []
    for pg in pages:
        text = re.sub(r'\s+', ' ', pg["text"]).strip()
        if not text:
            continue
        words = text.split()
        size, overlap = 180, 35
        for start in range(0, len(words), size-overlap):
            body = " ".join(words[start:start+size]).strip()
            if not body: continue
            window = " ".join(words[max(0,start-100):start]) + " " + body
            sm = SECTION_RE.findall(window)
            am = ACT_RE.findall(window)
            art = ARTICLE_RE.findall(window)
            cl = CLAUSE_RE.findall(window)
            chunks.append({
                "id": str(uuid.uuid4()), "document_id": document_id,
                "page": pg["page"], "text": body,
                "section": sm[-1] if sm else None,
                "act": am[-1].strip() if am else None,
                "article": art[-1] if art else None,
                "clause": cl[-1] if cl else None,
            })
            if start + size >= len(words):
                break
    return chunks

def extract_entities(text):
    entities = []
    for label, regex in [("Section", SECTION_RE), ("Article", ARTICLE_RE),
                         ("Clause", CLAUSE_RE), ("Act", ACT_RE)]:
        for value in regex.findall(text):
            value = value.strip()
            if value and not any(x["type"] == label and x["value"] == value for x in entities):
                entities.append({"type": label, "value": value})
    return entities
