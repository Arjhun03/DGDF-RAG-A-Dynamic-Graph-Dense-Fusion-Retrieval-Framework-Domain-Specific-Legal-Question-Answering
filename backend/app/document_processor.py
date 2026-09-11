import re
import uuid
from pathlib import Path

import fitz
from docx import Document

# ============================================================
# LEGAL REFERENCE PATTERNS
# ============================================================

SECTION_RE = re.compile(r"\b(?:section|sec\.?)\s+([0-9A-Za-z().\-]+)", re.IGNORECASE)
ARTICLE_RE = re.compile(r"\b(?:article|art\.?)\s+([0-9A-Za-z().\-]+)", re.IGNORECASE)
CLAUSE_RE = re.compile(r"\b(?:clause|cl\.?)\s+([0-9A-Za-z().\-]+)", re.IGNORECASE)
RULE_RE = re.compile(r"\b(?:rule|r\.?)\s+([0-9A-Za-z().\-]+)", re.IGNORECASE)

ACT_RE = re.compile(
    r"([A-Z][A-Za-z0-9,&()'\- ]{2,100}\bAct(?:,?\s+\d{4})?)",
    re.IGNORECASE,
)

ARTICLE_HEADING_RE = re.compile(
    r"^\s*(?:article|art\.?)\s+([0-9A-Za-z().\-]+)\.?\s*(.*)$",
    re.IGNORECASE,
)
SECTION_HEADING_RE = re.compile(
    r"^\s*(?:section|sec\.?)\s+([0-9A-Za-z().\-]+)\.?\s*(.*)$",
    re.IGNORECASE,
)
CLAUSE_HEADING_RE = re.compile(
    r"^\s*(?:clause|cl\.?)\s+([0-9A-Za-z().\-]+)\.?\s*(.*)$",
    re.IGNORECASE,
)

# Important: this is deliberately NOT automatically an Article.
# A line such as "21. ..." can be an Article in the main body,
# but it can also be item 21 in a Schedule/table/list.
NUMBERED_LEGAL_HEADING_RE = re.compile(
    r"^\s*(\d{1,3})\.\s+(.{3,180})$"
)

CONSTITUTIONAL_ARTICLE_RE = re.compile(
    r"^\s*(\d{1,3}[A-Z]?)\.\s+([A-Z][A-Za-z0-9\s,()'\/\-]{2,120}?)(?:[.—–—:]\s*(.*)|$)",
    re.DOTALL
)

SUBCLAUSE_RE = re.compile(r"^\s*(\([0-9A-Za-z]+\))\s*(.*)$")

# The uploaded Constitution is in Santhali (Ol Chiki), so the
# parser recognizes both generic English markers and the actual
# Santhali marker used for "Part" / "Schedule" in that edition.
PART_MARKER_RE = re.compile(
    r"(?:\bpart\s+[IVXLCM0-9]+\b|ᱦᱤᱸᱥ\s+[IVXLCM0-9]+(?:\s*[-–—:]|\b))",
    re.IGNORECASE,
)

SCHEDULE_MARKER_RE = re.compile(
    r"(?:\bschedules?\b|\bannex(?:ure|ures)?\b|\bappendix\b|\bappendices\b|ᱚᱱᱩᱥᱩᱪᱤ)",
    re.IGNORECASE,
)

# ============================================================
# TEXT NORMALIZATION
# ============================================================


def normalize_line(text: str) -> str:
    text = str(text or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = normalize_line(line)
        if line:
            lines.append(line)
    return "\n".join(lines)

# ============================================================
# DOCUMENT EXTRACTION
# ============================================================


def extract_pages(path: str):
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".pdf":
        pages = []
        doc = fitz.open(path)
        try:
            for index, page in enumerate(doc):
                pages.append({
                    "page": index + 1,
                    "text": page.get_text("text") or "",
                })
        finally:
            doc.close()
        return pages

    if suffix == ".docx":
        doc = Document(path)
        text = "\n".join(
            paragraph.text
            for paragraph in doc.paragraphs
            if paragraph.text and paragraph.text.strip()
        )
        return [{"page": 1, "text": text}]

    if suffix == ".txt":
        return [{
            "page": 1,
            "text": p.read_text(encoding="utf-8", errors="ignore"),
        }]

    raise ValueError("Supported files: PDF, DOCX, TXT")

# ============================================================
# BASIC STRUCTURE DETECTION
# ============================================================


def detect_structure_from_line(line: str):
    """Detect explicit legal headings without guessing context."""
    line = normalize_line(line)
    if not line:
        return None

    match = ARTICLE_HEADING_RE.match(line)
    if match:
        return {
            "type": "article",
            "number": match.group(1).strip(),
            "heading": match.group(2).strip(),
        }

    match = SECTION_HEADING_RE.match(line)
    if match:
        return {
            "type": "section",
            "number": match.group(1).strip(),
            "heading": match.group(2).strip(),
        }

    match = CLAUSE_HEADING_RE.match(line)
    if match:
        return {
            "type": "clause",
            "number": match.group(1).strip(),
            "heading": match.group(2).strip(),
        }

    match = CONSTITUTIONAL_ARTICLE_RE.match(line)
    if match:
        heading = match.group(2).strip()
        if len(heading) <= 120 and not heading.lower().startswith(("subs", "ins", "see", "vide")):
            return {
                "type": "article",
                "number": match.group(1).strip(),
                "heading": heading,
            }

    match = NUMBERED_LEGAL_HEADING_RE.match(line)
    if match:
        return {
            "type": "numbered_heading",
            "number": match.group(1).strip(),
            "heading": match.group(2).strip(),
        }

    return None

# ============================================================
# CONTEXT / ENTITY EXTRACTION
# ============================================================


def detect_context(text: str):
    section_matches = SECTION_RE.findall(text or "")
    article_matches = ARTICLE_RE.findall(text or "")
    clause_matches = CLAUSE_RE.findall(text or "")
    rule_matches = RULE_RE.findall(text or "")
    act_matches = ACT_RE.findall(text or "")

    return {
        "section": section_matches[-1].strip() if section_matches else None,
        "article": article_matches[-1].strip() if article_matches else None,
        "clause": clause_matches[-1].strip() if clause_matches else None,
        "rule": rule_matches[-1].strip() if rule_matches else None,
        "act": act_matches[-1].strip() if act_matches else None,
    }


def _append_entity(entities, entity_type, value):
    value = normalize_line(value)
    if not value:
        return
    key = (entity_type.lower(), value.lower())
    if not any((e["type"].lower(), e["value"].lower()) == key for e in entities):
        entities.append({"type": entity_type, "value": value})


def extract_entities(text: str):
    entities = []
    text = normalize_text(text)

    for label, regex in [
        ("Section", SECTION_RE),
        ("Article", ARTICLE_RE),
        ("Clause", CLAUSE_RE),
        ("Rule", RULE_RE),
        ("Act", ACT_RE),
    ]:
        for value in regex.findall(text):
            _append_entity(entities, label, value)

    # Explicit "21. ..." lines are intentionally NOT treated as
    # Articles here because this function has no document-state context.
    # structure_aware_chunks() handles that safely.
    return entities

# ============================================================
# CHUNK CREATION
# ============================================================


def _make_chunk(
    *,
    document_id,
    page_number,
    text,
    context,
):
    article = context.get("article")
    section = context.get("section")
    clause = context.get("clause")
    rule = context.get("rule")
    act = context.get("act")

    article_number = context.get("article_number") or article
    article_title = context.get("article_title") or context.get("heading")

    return {
        "id": str(uuid.uuid4()),
        "document_id": document_id,
        "document": context.get("document", "Constitution of India"),
        "document_type": context.get("document_type", "constitution"),
        "part": context.get("part"),
        "chapter": context.get("chapter"),
        "page": page_number,
        "text": normalize_line(text),
        "section": section,
        "act": act,
        "article": article,
        "article_number": article_number,
        "article_title": article_title if article_number else None,
        "clause": clause,
        "clause_number": clause,
        "rule": rule,
        "heading": context.get("heading"),
        "chunk_type": context.get("chunk_type", "text"),
        "legal_number": article or section or clause or rule,
        "authority_level": context.get("authority_level", 5 if context.get("chunk_type") == "constitutional_article" else 3),
    }


def create_word_chunks(
    text: str,
    page_number: int,
    document_id: str,
    structure_context=None,
    chunk_size: int = 180,
    overlap: int = 35,
):
    structure_context = dict(structure_context or {})
    words = normalize_line(text).split()
    if not words:
        return []

    chunks = []
    step = max(1, chunk_size - overlap)

    for start in range(0, len(words), step):
        body = " ".join(words[start:start + chunk_size]).strip()
        if not body:
            continue

        detected = detect_context(body)
        context = {
            **structure_context,
            "article": detected.get("article") or structure_context.get("article"),
            "section": detected.get("section") or structure_context.get("section"),
            "clause": detected.get("clause") or structure_context.get("clause"),
            "rule": detected.get("rule") or structure_context.get("rule"),
            "act": detected.get("act") or structure_context.get("act"),
        }
        chunks.append(_make_chunk(
            document_id=document_id,
            page_number=page_number,
            text=body,
            context=context,
        ))

        if start + chunk_size >= len(words):
            break

    return chunks

# ============================================================
# STRUCTURE-AWARE CHUNKING
# ============================================================


def _empty_context():
    return {
        "article": None,
        "section": None,
        "clause": None,
        "rule": None,
        "act": None,
        "heading": None,
        "chunk_type": "text",
    }


def _is_part_marker(line: str) -> bool:
    return bool(PART_MARKER_RE.search(line))


def _is_schedule_marker(line: str) -> bool:
    # The Santhali edition contains the Schedule word inside ordinary
    # provisions as well, so a loose substring check would be wrong.
    # Treat the Santhali marker as a heading only when it is very short.
    text = normalize_line(line)
    if not text:
        return False

    if "ᱚᱱᱩᱥᱩᱪᱤ" in text:
        # In this edition the standalone Schedule heading is very short
        # (for example, "ᱛᱩᱨᱩᱭᱟᱜ ᱚᱱᱩᱥᱩᱪᱤ"). Ordinary provisions can
        # mention the same word, so require a tiny heading-like phrase.
        return len(text) <= 35 and len(text.split()) <= 3 and not text.startswith(("(", "["))

    # Generic English heading markers.
    if len(text) > 80:
        return False
    if not SCHEDULE_MARKER_RE.search(text):
        return False
    stripped = text.strip("()[]-–—: ")
    return len(stripped.split()) <= 8


def structure_aware_chunks(path: str, document_id: str):
    """
    Parse legal documents while keeping document state.

    Critical rule:
      - Explicit "Article 21" is always an Article.
      - Generic "21. ..." becomes an Article ONLY while the parser
        is inside the main constitutional body.
      - Once a Schedule/Annexure/Appendix marker is encountered,
        numbered items remain numbered headings and never become Articles.
    """
    pages = extract_pages(path)
    chunks = []

    current_context = _empty_context()
    in_main_body = False
    in_schedule = False

    for pg in pages:
        page_number = pg["page"]
        normalized = normalize_text(pg.get("text", ""))
        if not normalized:
            continue

        lines = normalized.split("\n")

        # A Part marker appears in the table of contents too. Therefore it
        # is only a candidate until the page also looks like real statutory
        # body text (a numbered heading plus at least one sub-clause).
        page_has_numbered_heading = any(
            detect_structure_from_line(line or "")
            and detect_structure_from_line(line or "")["type"] == "numbered_heading"
            for line in lines
        )
        page_has_subclause = any(
            SUBCLAUSE_RE.match(normalize_line(line or ""))
            for line in lines
        )
        page_has_body_signal = page_has_numbered_heading and page_has_subclause
        page_has_part_marker = any(_is_part_marker(line) for line in lines)

        if (not in_main_body and not in_schedule
                and page_has_part_marker and page_has_body_signal):
            in_main_body = True

        blocks = []
        current_block_lines = []
        block_context = dict(current_context)

        def flush_block():
            nonlocal current_block_lines
            if current_block_lines:
                blocks.append({
                    "text": "\n".join(current_block_lines),
                    "context": dict(block_context),
                })
                current_block_lines = []

        for line in lines:
            line = normalize_line(line)
            if not line:
                continue

            # Schedule is a one-way state for constitutional documents.
            # We check it BEFORE generic numbered headings so a Schedule
            # heading on the same page prevents "21." from becoming Article 21.
            # Schedule markers appearing in the table of contents or
            # preliminary pages must NOT end the main-body parser before
            # the actual constitutional text starts.
            if _is_schedule_marker(line) and in_main_body:
                flush_block()
                in_schedule = True
                in_main_body = False
                current_context = _empty_context()
                block_context = _empty_context()
                current_block_lines.append(line)
                continue

            structure = detect_structure_from_line(line)

            if structure is None:
                current_block_lines.append(line)
                continue

            # Save the previous block before starting a new legal structure.
            flush_block()

            structure_type = structure["type"]

            # Generic numbered headings are context-sensitive.
            if structure_type == "numbered_heading":
                if in_main_body and not in_schedule:
                    structure_type = "article"
                else:
                    # Keep schedules/lists/tables as generic numbered headings.
                    current_block_lines.append(line)
                    block_context = dict(current_context)
                    continue

            if structure_type == "article":
                block_context = {
                    "article": structure["number"],
                    "section": None,
                    "clause": None,
                    "rule": None,
                    "act": current_context.get("act"),
                    "heading": structure["heading"],
                    "chunk_type": "article",
                }
                current_context = dict(block_context)

            elif structure_type == "section":
                block_context = {
                    "article": current_context.get("article"),
                    "section": structure["number"],
                    "clause": None,
                    "rule": None,
                    "act": current_context.get("act"),
                    "heading": structure["heading"],
                    "chunk_type": "section",
                }
                current_context = dict(block_context)

            elif structure_type == "clause":
                block_context = {
                    "article": current_context.get("article"),
                    "section": current_context.get("section"),
                    "clause": structure["number"],
                    "rule": None,
                    "act": current_context.get("act"),
                    "heading": structure["heading"],
                    "chunk_type": "clause",
                }
                current_context = dict(block_context)

            current_block_lines.append(line)

        flush_block()

        # Convert blocks to final chunks.
        for block in blocks:
            text = block["text"].strip()
            if not text:
                continue

            context = dict(block["context"])
            detected = detect_context(text)

            # IMPORTANT: explicit references inside the body are allowed to
            # supplement metadata, but must not overwrite a known structural
            # Article with a random cross-reference from the body.
            article = context.get("article") or detected.get("article")
            section = context.get("section") or detected.get("section")
            clause = context.get("clause") or detected.get("clause")
            rule = context.get("rule") or detected.get("rule")
            act = context.get("act") or detected.get("act")

            final_context = {
                "article": article,
                "section": section,
                "clause": clause,
                "rule": rule,
                "act": act,
                "heading": context.get("heading"),
                "chunk_type": context.get("chunk_type", "text"),
            }

            words = text.split()
            if len(words) <= 240:
                chunks.append(_make_chunk(
                    document_id=document_id,
                    page_number=page_number,
                    text=" ".join(words),
                    context=final_context,
                ))
            else:
                chunks.extend(create_word_chunks(
                    text=text,
                    page_number=page_number,
                    document_id=document_id,
                    structure_context=final_context,
                    chunk_size=180,
                    overlap=35,
                ))

        # Carry the last structural context to the next page only while
        # still inside the main body. Never carry an Article into Schedules.
        if in_schedule:
            current_context = _empty_context()
        else:
            for block in reversed(blocks):
                ctx = block["context"]
                if (
                    ctx.get("article")
                    or ctx.get("section")
                    or ctx.get("clause")
                    or ctx.get("rule")
                    or ctx.get("act")
                ):
                    current_context = dict(ctx)
                    break

    return chunks
