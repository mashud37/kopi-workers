"""Show any file an app reads or writes inside the console: markdown rendered, text and Word files as text.
The viewer and the folder browser use it.
"""
import json
import math
import os
from datetime import datetime
from pathlib import Path

import markdown

MARKDOWN_EXTENSIONS = [
    "tables",
    "fenced_code",
    "sane_lists",
]

KIND_BY_SUFFIX = {
    ".md": "markdown",
    ".txt": "text",
    ".diff": "text",
    ".log": "text",
    ".yaml": "text",
    ".csv": "text",
    ".jsonl": "text",
    ".json": "json",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".docx": "docx",
}

TEXT_LIMIT = 2_000_000
PAGE_SIZE = 100
TIME_FORMAT = "%d %b %Y, %H:%M"


# ---- Rendering ----

def render_markdown(text):
    """Markdown as HTML. Every `<` is escaped first, so a file can never put its own HTML or script on the page."""
    safe = text.replace("<", "&lt;")
    return markdown.markdown(safe, extensions=MARKDOWN_EXTENSIONS, tab_length=2)


def docx_text(path):
    """The paragraphs of a Word file as plain text, one per line, or a short note when the file cannot be read."""
    import docx
    from docx.opc.exceptions import PackageNotFoundError
    try:
        document = docx.Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError, OSError):
        return "This Word file could not be read. It may be damaged, or still open in Word."
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs)


def size_text(size):
    """A file size as people read it: bytes, KB or MB."""
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{math.ceil(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def json_text(path):
    """A JSON file laid out with indents, or as it is when it does not parse."""
    raw = path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT]
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        return raw


def document_view(path):
    """Everything the viewer shows for one file: its kind, and its content when it is shown as text.

    Returns:
        dict with "kind", "name", "size", "modified", and "html" or "text" for the kinds shown inline.
    """
    stat = path.stat()
    kind = KIND_BY_SUFFIX.get(path.suffix.lower(), "other")
    view = {
        "kind": kind,
        "name": path.name,
        "size": size_text(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime(TIME_FORMAT),
        "html": "",
        "text": "",
        "cut": stat.st_size > TEXT_LIMIT and kind in ["markdown", "text", "json"],
    }
    if kind == "markdown":
        view["html"] = render_markdown(path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT])
    elif kind == "text":
        view["text"] = path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT]
    elif kind == "json":
        view["text"] = json_text(path)
    elif kind == "docx":
        view["text"] = docx_text(path)
    return view


# ---- Browsing a folder ----

def visible_entries(here, wanted):
    """The files and folders directly in a folder whose names contain the wanted text, hidden ones left out."""
    if not here.is_dir():
        return []
    found = []
    with os.scandir(here) as entries:
        for entry in entries:
            hidden = entry.name.startswith((".", "~$"))
            if not hidden and wanted.lower() in entry.name.lower():
                found.append(entry)
    return found


def folder_listing(folder, inside, wanted, page):
    """One page of a folder's files and sub-folders, newest first, filtered by a piece of the name.

    Args:
        inside: the sub-folder being shown, relative to the folder; empty for the folder itself.
        wanted: only names containing this text, ignoring case; empty shows everything.
        page: which page of PAGE_SIZE entries, counting from 1.

    Returns:
        dict with "rows", "total", "page", "pages", and "parent", the sub-folder one level up.
    """
    rows = []
    for entry in visible_entries(folder / inside, wanted):
        stat = entry.stat()
        rows.append({
            "name": entry.name,
            "relative": str(Path(inside) / entry.name) if inside else entry.name,
            "is_folder": entry.is_dir(),
            "modified": stat.st_mtime,
            "when": datetime.fromtimestamp(stat.st_mtime).strftime(TIME_FORMAT),
            "size": "" if entry.is_dir() else size_text(stat.st_size),
        })
    rows.sort(key=lambda row: row["modified"], reverse=True)
    pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    start = (page - 1) * PAGE_SIZE
    parent = str(Path(inside).parent) if inside else None
    if parent == ".":
        parent = ""
    return {
        "rows": rows[start:start + PAGE_SIZE],
        "total": len(rows),
        "page": page,
        "pages": pages,
        "parent": parent,
    }
