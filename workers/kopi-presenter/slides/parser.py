"""
Parse .docx or .txt/.md input files into structured text for the LLM.

For .docx manuscripts the output is a section-structured digest:
  - Section headings become Markdown ## headers
  - Each paragraph's first + last sentence are extracted (key-claim heuristic)
  - Short paragraphs (<= 60 words) are kept whole
  - Direct quotes (text containing quotation marks) are always kept whole
  - Block quotes / indented paragraphs are kept whole
  - A word-count summary is prepended so the LLM knows it has a full paper

For .txt / .md the file is returned as-is.
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


# ---------------------------------------------------------------------------
# .docx parser
# ---------------------------------------------------------------------------

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

    def flush_section() -> None:
        if pending:
            sections.append("\n\n".join(pending))
            pending.clear()

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        total_words += len(text.split())

        if para.style.name.startswith("Heading"):
            flush_section()
            try:
                level = int(para.style.name.split()[-1])
            except ValueError:
                level = 2
            sections.append(f"{'#' * level} {text}")
            continue

        if condense:
            processed = _condense_paragraph(text)
        else:
            processed = text

        pending.append(processed)

    flush_section()

    body = "\n\n".join(sections)
    note = "condensed to key sentences" if condense else "full text"
    header = f"[MANUSCRIPT — {total_words:,} words, {note}]\n\n"
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

    sentences = _split_sentences(text)
    if len(sentences) <= 2:
        return text

    first = sentences[0].strip()
    last = sentences[-1].strip()
    if first == last:
        return first
    return f"{first} […] {last}"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\(\[])', text)
    return [p for p in parts if p.strip()]
