"""Turn files dropped into kopi-learner/input/ into distillation units the
same way kopi-editor would: diagnose once, then draw the configured band mix
per paragraph.
"""
from pathlib import Path

import editor
from cli import config, ui
from corpus import paragraphs, sample

_EXTS = (".docx", ".md", ".txt")


def input_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "input"


def list_documents() -> list[Path]:
    d = input_dir()
    if not d.exists():
        raise SystemExit(f"no input folder at {d}, create it and add .docx/.md/.txt files.")
    return sorted(p for p in d.iterdir() if p.suffix.lower() in _EXTS and p.name != ".gitkeep")


def collect() -> list[dict]:
    """Every eligible paragraph of every input document, at a band from the mix."""
    docs = list_documents()
    if not docs:
        raise SystemExit(f"input/ has no .docx/.md/.txt documents ({input_dir()}).")
    min_words = int(config.settings().get("corpus", {}).get("min_paragraph_words", 40))
    ui.info(f"{len(docs)} document(s) in input/")
    units: list[dict] = []
    for i, path in enumerate(docs, 1):
        ui.info(f"[{i}/{len(docs)}] {path.name}")
        try:
            if path.suffix.lower() == ".docx":
                text = editor.extract_docx(path)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
            state = editor.prepare_doc(text, config.lang())
            base = [c for c in editor.candidates_at(state, 0)
                    if sample._is_prose(c["text"], min_words)]
            units.extend(paragraphs.assign_bands(state, base, seed=path.stem, doc=path.stem))
        except Exception as e:
            ui.warn(f"skipped {path.name}: {e}")
    ui.ok(f"{len(units)} paragraph units from input/")
    return units
