"""Parse a .docx, .txt, or .md input into the section-structured digest the model
reads, keeping short paragraphs and direct quotes whole.
"""

import re
from pathlib import Path


def parse_input(path: Path, condense: bool = True) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _parse_docx(path, condense=condense)
    elif suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}. Use .docx or .txt")


# ---- .docx parser ----

def _flush_section(sections: list[str], pending: list[str]) -> dict:
    """Fold the pending paragraphs into one more section, or leave `sections`
    untouched if nothing is pending. Returns the new sections and pending lists,
    it does not change the lists it was given."""
    if not pending:
        return {"sections": sections, "pending": pending}
    new_sections = sections + ["\n\n".join(pending)]
    return {"sections": new_sections, "pending": []}


def _parse_docx(path: Path, condense: bool = True) -> str:
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required for .docx parsing: pip install python-docx"
        )

    doc = Document(str(path))
    sections: list[str] = []
    pending: list[str] = []
    total_words = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        total_words += len(text.split())

        if para.style.name.startswith("Heading"):
            flushed = _flush_section(sections, pending)
            sections, pending = flushed["sections"], flushed["pending"]
            try:
                level = int(para.style.name.split()[-1])
            except ValueError:
                level = 2
            sections = sections + [f"{'#' * level} {text}"]
            continue

        if condense:
            processed = _condense_paragraph(text)
        else:
            processed = text

        pending = pending + [processed]

    flushed = _flush_section(sections, pending)
    sections = flushed["sections"]

    body = "\n\n".join(sections)
    note = "condensed to key sentences" if condense else "full text"
    header = f"[MANUSCRIPT: {total_words:,} words, {note}]\n\n"
    return header + body


def _condense_paragraph(text: str) -> str:
    """
    Keep the paragraph whole if short or contains a quote.
    Otherwise return first + last sentence (topic + conclusion heuristic).
    """
    word_count = len(text.split())

    has_quote = '"' in text or '“' in text or '‘' in text
    if word_count <= 60 or has_quote:
        return text

    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\(\[])', text)
    sentences = [p for p in parts if p.strip()]
    if len(sentences) <= 2:
        return text

    first = sentences[0].strip()
    last = sentences[-1].strip()
    if first == last:
        return first
    return f"{first} […] {last}"
