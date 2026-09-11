import json
import re
import uuid

def enrich():
    with open("data/chunks.json", "r") as f:
        chunks = json.load(f)

    new_chunks = []

    for c in chunks:
        page = c.get("page", 0)
        text = c.get("text", "").strip()

        # Handle splitting of Article 21 and 21A on Page 74
        if page == 74 and "21. Protection of life and personal liberty" in text and "21A. Right to Education" in text:
            # Split into 2 distinct chunks
            part21_text = "21. Protection of life and personal liberty.—No person shall be deprived of his life or personal liberty except according to procedure established by law."
            part21a_text = "21A. Right to Education.—The State shall provide free and compulsory education to all children of the age of six to fourteen years in such manner as the State may, by law, determine."

            chunk21 = {
                "id": str(uuid.uuid4()),
                "document_id": c.get("document_id"),
                "document": "Constitution of India",
                "document_type": "constitution",
                "part": "Part III",
                "chapter": None,
                "page": 74,
                "article": "21",
                "article_number": "21",
                "article_title": "Protection of life and personal liberty",
                "heading": "Protection of life and personal liberty",
                "clause_number": None,
                "section": None,
                "act": None,
                "rule": None,
                "clause": None,
                "chunk_type": "constitutional_article",
                "legal_number": "21",
                "authority_level": 5,
                "text": part21_text,
            }
            new_chunks.append(chunk21)

            chunk21a = {
                "id": str(uuid.uuid4()),
                "document_id": c.get("document_id"),
                "document": "Constitution of India",
                "document_type": "constitution",
                "part": "Part III",
                "chapter": None,
                "page": 74,
                "article": "21A",
                "article_number": "21A",
                "article_title": "Right to Education",
                "heading": "Right to Education",
                "clause_number": None,
                "section": None,
                "act": None,
                "rule": None,
                "clause": None,
                "chunk_type": "constitutional_article",
                "legal_number": "21A",
                "authority_level": 5,
                "text": part21a_text,
            }
            new_chunks.append(chunk21a)
            continue

        # Standard enrichment
        doc_type = "constitution"
        doc_name = "Constitution of India"

        # Determine Part based on constitutional page ranges
        if page < 58:
            part = "Preamble & Contents"
            is_main = False
        elif 58 <= page <= 60:
            part = "Part I"
            is_main = True
        elif 61 <= page <= 61:
            part = "Part II"
            is_main = True
        elif 62 <= page <= 91:
            part = "Part III"
            is_main = True
        elif 92 <= page <= 97:
            part = "Part IV"
            is_main = True
        elif 98 <= page <= 101:
            part = "Part IVA"
            is_main = True
        elif 102 <= page <= 211:
            part = "Part V"
            is_main = True
        elif 212 <= page <= 275:
            part = "Part VI"
            is_main = True
        elif 276 <= page <= 277:
            part = "Part VII"
            is_main = True
        elif 278 <= page <= 283:
            part = "Part VIII"
            is_main = True
        elif 284 <= page <= 297:
            part = "Part IX"
            is_main = True
        elif 298 <= page <= 325:
            part = "Part X-XI"
            is_main = True
        elif 326 <= page <= 365:
            part = "Part XII"
            is_main = True
        elif 366 <= page <= 371:
            part = "Part XIII"
            is_main = True
        elif 372 <= page <= 395:
            part = "Part XIV"
            is_main = True
        elif 396 <= page <= 403:
            part = "Part XV"
            is_main = True
        elif 404 <= page <= 415:
            part = "Part XVI"
            is_main = True
        elif 416 <= page <= 425:
            part = "Part XVII"
            is_main = True
        elif 426 <= page <= 437:
            part = "Part XVIII"
            is_main = True
        elif 438 <= page <= 447:
            part = "Part XIX"
            is_main = True
        elif 448 <= page <= 453:
            part = "Part XX"
            is_main = True
        elif 454 <= page <= 463:
            part = "Part XXI"
            is_main = True
        elif 464 <= page <= 467:
            part = "Part XXII"
            is_main = True
        else:
            part = "Schedules"
            is_main = False

        art = c.get("article")
        heading = c.get("heading")

        if is_main and art:
            # Check if valid constitutional article (1-395)
            art_clean = str(art).strip().upper()
            base_num_match = re.match(r"^(\d+)", art_clean)
            if base_num_match and 1 <= int(base_num_match.group(1)) <= 395:
                chunk_type = "constitutional_article"
                article_number = art_clean
                authority_level = 5
            else:
                chunk_type = "text"
                article_number = None
                authority_level = 3
                art = None
        elif not is_main:
            # Pages > 467 are schedules or appendices, NOT constitutional articles!
            if "schedule" in text.lower() or "list" in text.lower() or "entry" in text.lower() or "table" in text.lower():
                chunk_type = "schedule_entry"
            else:
                chunk_type = "schedule_paragraph"
            article_number = None
            art = None
            authority_level = 3
        else:
            chunk_type = c.get("chunk_type", "text")
            article_number = None
            authority_level = 3

        enriched = {
            **c,
            "document": doc_name,
            "document_type": doc_type,
            "part": part,
            "chapter": None,
            "article": art,
            "article_number": article_number,
            "article_title": heading if article_number else None,
            "chunk_type": chunk_type,
            "authority_level": authority_level,
        }
        new_chunks.append(enriched)

    with open("data/chunks.json", "w") as f:
        json.dump(new_chunks, f, indent=2)

    print(f"Successfully enriched {len(new_chunks)} chunks.")
    art21s = [c for c in new_chunks if c.get("article_number") == "21"]
    art21as = [c for c in new_chunks if c.get("article_number") == "21A"]
    print(f"Verified Article 21 chunks: {len(art21s)}")
    print(f"Verified Article 21A chunks: {len(art21as)}")
    for a in art21s:
        print("Art 21 -> Page:", a.get("page"), "Part:", a.get("part"), "Title:", a.get("article_title"), "Type:", a.get("chunk_type"))
    for a in art21as:
        print("Art 21A -> Page:", a.get("page"), "Part:", a.get("part"), "Title:", a.get("article_title"), "Type:", a.get("chunk_type"))

if __name__ == "__main__":
    enrich()
