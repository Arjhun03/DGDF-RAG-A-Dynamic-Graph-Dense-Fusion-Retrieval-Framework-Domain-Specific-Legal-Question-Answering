import re
import string
from typing import Any, Dict

# Standard English legal vocabulary set for language density scoring
COMMON_LEGAL_TERMS = {
    "constitution", "article", "section", "clause", "subclause", "act", "rule",
    "order", "amendment", "schedule", "part", "chapter", "law", "court",
    "liberty", "life", "rights", "fundamental", "justice", "state", "person",
    "procedure", "established", "prohibition", "equality", "freedom", "citizen",
    "authority", "parliament", "legislature", "president", "governor", "council",
    "judiciary", "jurisdiction", "power", "provision", "provided", "subject",
    "notwithstanding", "manner", "prescribed", "gazette", "notification", "valid",
}

# Suspicious font-mapping corruptions typical in legacy Malayalam/regional fonts
# e.g. '\S-]-Sn-Iƒ', 'a‰phn[-Øn¬ hyhÿ sNbvXn-´p≈'
CORRUPT_FONT_PATTERNS = [
    re.compile(r"[\\][S\-]+"),
    re.compile(r"[a-z]¬"),
    re.compile(r"°[a-z]"),
    re.compile(r"sNbvX"),
    re.compile(r"hyhÿ"),
    re.compile(r"a‰phn"),
    re.compile(r"[I|ƒ][¬°]"),
    re.compile(r"[-–—]{3,}"),
]


def clean_text_encoding(text: str) -> str:
    """Normalize unicode quotes, dashes, ligatures and clean whitespace."""
    if not text:
        return ""

    # Replace common typographic variants
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "—",
        "\u2013": "–",
        "\u00a0": " ",
        "\ufeff": "",
        "\r\n": "\n",
        "\r": "\n",
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)

    # Normalize excessive spaces and blank lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def evaluate_text_quality(text: str, source_type: str = "constitution") -> Dict[str, Any]:
    """
    Computes an Evidence Quality Score (0.0 to 1.0) for a text chunk:
      evidence_quality = 0.30*encoding + 0.30*ocr + 0.20*source + 0.20*linguistic

    Identifies and penalizes legacy font glyph corruption (e.g. ASCII font mapped Malayalam).
    """
    cleaned = clean_text_encoding(text)
    if not cleaned:
        return {
            "evidence_quality": 0.0,
            "encoding_quality": 0.0,
            "ocr_quality": 0.0,
            "language_quality": 0.0,
            "source_quality": 0.0,
            "is_usable": False,
            "reasons": ["Empty text"],
        }

    total_chars = len(cleaned)
    words = re.findall(r"\b[A-Za-z0-9'-]+\b", cleaned)
    total_words = len(words)

    reasons = []

    # 1. Encoding Quality (0.0 - 1.0)
    # Check printable ASCII ratio and corrupt font patterns
    printable_chars = sum(1 for c in cleaned if c in string.printable or c in "—–‘’“”")
    printable_ratio = printable_chars / max(1, total_chars)

    # Check for corrupt font signatures
    corrupt_matches = sum(len(p.findall(cleaned)) for p in CORRUPT_FONT_PATTERNS)
    corrupt_penalty = min(0.60, corrupt_matches * 0.15)

    encoding_quality = max(0.0, min(1.0, printable_ratio - corrupt_penalty))
    if corrupt_matches > 0:
        reasons.append(f"Detected {corrupt_matches} legacy font glyph corruptions")

    # 2. OCR Quality (0.0 - 1.0)
    # Checks character-to-word ratio, broken hyphenations, symbol density
    symbols = sum(1 for c in cleaned if c not in string.ascii_letters and c not in string.digits and c not in " \n.,'-—")
    symbol_ratio = symbols / max(1, total_chars)
    symbol_penalty = min(0.50, symbol_ratio * 2.0)

    # Average word length check (gibberish often has extreme word lengths)
    avg_word_len = (sum(len(w) for w in words) / max(1, total_words)) if words else 0
    word_len_score = 1.0 if 3.0 <= avg_word_len <= 10.0 else max(0.2, 1.0 - abs(avg_word_len - 6.0) * 0.1)

    ocr_quality = max(0.0, min(1.0, (1.0 - symbol_penalty) * 0.6 + word_len_score * 0.4))
    if symbol_ratio > 0.15:
        reasons.append(f"High non-standard symbol density: {symbol_ratio:.1%}")

    # 3. Linguistic Quality (0.0 - 1.0)
    # Checks ratio of recognizable English/legal tokens vs gibberish
    if total_words > 0:
        legal_words = sum(1 for w in words if w.lower() in COMMON_LEGAL_TERMS)
        legal_density = min(1.0, (legal_words / max(1, total_words)) * 5.0)

        # Standard dictionary word heuristic (letters only)
        valid_words = sum(1 for w in words if re.match(r"^[A-Za-z]{2,20}$", w))
        valid_word_ratio = valid_words / max(1, total_words)

        language_quality = (valid_word_ratio * 0.7) + (legal_density * 0.3)
    else:
        language_quality = 0.0

    # 4. Source Authority Quality (0.0 - 1.0)
    source_weights = {
        "constitution": 1.0,
        "statute": 0.90,
        "act": 0.90,
        "supreme_court": 0.95,
        "high_court": 0.85,
        "subordinate_rule": 0.80,
        "regulation": 0.75,
        "secondary": 0.60,
    }
    source_quality = source_weights.get(source_type.lower(), 0.85)

    # Combined Evidence Quality Score
    final_evidence_quality = (
        (0.30 * encoding_quality)
        + (0.30 * ocr_quality)
        + (0.20 * source_quality)
        + (0.20 * language_quality)
    )

    is_usable = final_evidence_quality >= 0.60 and corrupt_matches == 0

    return {
        "evidence_quality": round(final_evidence_quality, 4),
        "encoding_quality": round(encoding_quality, 4),
        "ocr_quality": round(ocr_quality, 4),
        "language_quality": round(language_quality, 4),
        "source_quality": round(source_quality, 4),
        "is_usable": is_usable,
        "corrupt_font_matches": corrupt_matches,
        "reasons": reasons,
        "cleaned_text": cleaned,
    }
