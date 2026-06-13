"""Shared helpers for the analyze / proof / edit routes."""
from pathlib import Path

from cli import config


def resolve_docx(file: str) -> Path:
    """Resolve a .docx path, accepting a bare name (looked up in input/)."""
    path = Path(file)
    if not path.exists() and not path.is_absolute():
        candidate = config.INPUT_DIR / file
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise SystemExit(f"'{file}' not found (looked in '.' and '{config.INPUT_DIR}').")
    if path.suffix.lower() != ".docx":
        raise SystemExit("input must be a .docx file.")
    return path


def load_text(file: str) -> tuple[Path, str, int]:
    """Resolve + extract a .docx. Returns (path, text, word_count)."""
    from kopi.extract import extract_docx
    path = resolve_docx(file)
    text = extract_docx(path)
    return path, text, len(text.split())
