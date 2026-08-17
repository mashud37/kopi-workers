"""`lint` command: edit a document deterministically and write the result."""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

INPUT = Path("input")
OUTPUT = Path("output")
_READABLE = (".md", ".txt")


def _resolve(name: str) -> Path:  # lint-style: ignore FN004
    path = Path(name)
    if not path.exists() and not path.is_absolute():
        path = INPUT / name
    if not path.exists():
        raise SystemExit(f"file not found: {name}")
    if path.suffix.lower() not in _READABLE:
        raise SystemExit(f"cannot read {path.suffix} yet, expected one of {', '.join(_READABLE)}")
    return path


def _pick_file() -> Path | None:  # lint-style: ignore FN004
    candidates = sorted(p for p in INPUT.glob("*") if p.suffix.lower() in _READABLE)
    if not candidates:
        raise SystemExit(f"no .md or .txt files in {INPUT}/")
    choice = ui.menu("Document", [(p.name, f"{p.stat().st_size // 1024} KB") for p in candidates])
    return candidates[choice] if choice is not None else None


def _write(path: Path, results: list, band_name: str) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    edited = OUTPUT / f"{path.stem}_linted.md"
    edited.write_text("\n\n".join(r.edited for r in results), encoding="utf-8")

    lines = [f"# Change log: {path.name}", "", f"Band: {band_name}", ""]
    for i, result in enumerate(results, 1):
        if not result.applied and not result.reason:
            continue
        lines.append(f"## Paragraph {i}")
        lines.extend(f"- {edit.note}  `{edit.rule}` (confidence {edit.confidence})"
                     for edit in result.applied)
        if result.reason:
            lines.append(f"- rejected, paragraph left unchanged: {result.reason}")
        lines.append("")
    (OUTPUT / f"{path.stem}_changelog.md").write_text("\n".join(lines), encoding="utf-8")
    return edited


def run(name: str | None = None, band_name: str = "firm") -> None:
    ui.step("Lint")
    ui.info("plan: read document, load parser, lint each paragraph, write result and change log")

    path = _resolve(name) if name else _pick_file()
    if path is None:
        return

    from lint import bands
    band = bands.band(band_name)
    text = path.read_text(encoding="utf-8")
    paragraphs = [block.strip() for block in text.split("\n\n") if block.strip()]
    ui.ok(f"{path.name}: {len(paragraphs)} paragraphs, "
          f"{sum(len(p.split()) for p in paragraphs)} words, band {band.name}")

    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()

    from lint.run import lint_document
    bar = BatchProgress(len(paragraphs), "linting")
    results = lint_document(paragraphs, nlp, band, on_progress=bar.on_item)
    bar.finish()

    broken = set()
    for result in results:
        for name, err in result.failures:
            broken.add(f"{name}: {type(err).__name__}")
    for label in sorted(broken):
        ui.error(f"rule raised while linting: {label}")

    changed = sum(1 for r in results if r.changed)
    saved = sum(r.words_saved for r in results)
    edits = sum(len(r.applied) for r in results)
    ui.ok(f"{edits} edits across {changed} of {len(results)} paragraphs, {saved} words removed")
    for result in results:
        if result.reason:
            ui.warn(f"paragraph left unchanged: {result.reason}")
    print(_write(path, results, band.name))
