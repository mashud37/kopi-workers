from pathlib import Path
from docx import Document

_BLOCK_STYLE_TERMS = ("block", "quote", "quotation", "long quot")


def _is_block_quote(para) -> bool:
    name = (para.style.name or "").lower()
    if any(t in name for t in _BLOCK_STYLE_TERMS):
        return True
    try:
        indent = para.paragraph_format.left_indent
        if indent is not None and indent.pt >= 36:
            return True
    except Exception:
        pass
    return False


def extract_docx(path: Path) -> str:
    doc = Document(path)
    parts = []
    for p in doc.paragraphs:
        if not p.text.strip():
            continue
        if _is_block_quote(p):
            parts.append(f"⟪{p.text}⟫")
        else:
            parts.append(p.text)
    return "\n\n".join(parts)
