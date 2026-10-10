"""Turn a manuscript or outline into a styled .pptx and a PDF: parse the input, plan the slides with a model, apply the house rules, then render."""

import json
from datetime import datetime
from pathlib import Path

from cli import ui
from slides import config as settings
from slides.emitter_pptx import build_pptx
from slides.linter import lint_and_repair
from slides.llm import generate_slide_json, revise_slide_json
from slides.parser import parse_input
from slides.renderer_pptx import export_pdf
from slides.rules import apply_house_rules

OPTION_DEFAULTS = {
    "output": None,
    "venue": None,
    "no_pdf": False,
    "plan": None,
    "dry_run": False,
    "review": False,
    "emoji": False,
    "condense": False,
}


def run(file_name: str, options: dict) -> None:
    """Build one deck.

    Args:
        file_name: the manuscript or outline; a bare name resolves against input/.
        options: any of the keys in OPTION_DEFAULTS; missing keys take their default.
    """
    options = {**OPTION_DEFAULTS, **options}
    input_path = settings.resolve_input(file_name)
    config = settings.load_config()
    if options["emoji"]:
        config.setdefault("render", {})["icons"] = "emoji"
    stem = input_path.stem
    if options["output"]:
        output_dir = Path(options["output"])
    else:
        output_dir = settings.OUTPUT_DIR / f"{stem} slides {datetime.now():%Y-%m-%d %H%M%S}"
    output_dir.mkdir(parents=True, exist_ok=True)

    _print_step_plan(input_path, options)
    plan = _build_plan(input_path, options, config)
    content = plan["content"]
    slide_data = plan["slide_data"]

    if options["dry_run"]:
        print(json.dumps(slide_data, indent=2, ensure_ascii=False))
        return

    json_path = output_dir / f"{stem}.json"
    _write_json(json_path, slide_data)
    ui.info(f"plan saved: {json_path.name}")

    if options["review"]:
        slide_data = _review_plan(json_path, slide_data, config)

    ui.step("[3/5] Lint and apply house rules")
    slide_data = lint_and_repair(slide_data, content, config)
    slide_data = apply_house_rules(slide_data)

    pptx_path = output_dir / f"{stem}.pptx"
    ui.step(f"[4/5] Build {pptx_path.name}")
    build_pptx(slide_data, pptx_path, config)
    slide_count = len(slide_data.get("slides", []))
    ui.ok(f"{slide_count} content slides (+ title + closing = {slide_count + 2}), {pptx_path.stat().st_size // 1024} KB")

    if options["no_pdf"]:
        ui.step("[5/5] Export PDF: skipped")
    else:
        ui.step("[5/5] Export PDF")
        if export_pdf(pptx_path):
            pdf_path = pptx_path.with_suffix(".pdf")
            ui.ok(f"{pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)")
        else:
            ui.warn("PDF export failed: neither PowerPoint nor LibreOffice was found")

    ui.ok(f"done, output in {output_dir.resolve()}")


def _print_step_plan(input_path: Path, options: dict) -> None:
    ui.step(f"kopi-presenter: {input_path.name}")
    ui.info("1/5  Parse input")
    if options["plan"]:
        ui.info("2/5  Load the saved plan")
    else:
        ui.info("2/5  Plan the slides with the model")
    ui.info("3/5  Lint and apply house rules")
    ui.info("4/5  Build .pptx")
    if options["no_pdf"]:
        ui.info("5/5  Export PDF (skipped)")
    else:
        ui.info("5/5  Export PDF")


def _build_plan(input_path: Path, options: dict, config: dict) -> dict:
    """Parse the input, then either call the model or load a saved plan."""
    ui.step(f"[1/5] Parse {input_path.name}")
    content = parse_input(input_path, condense=options["condense"])
    if options["condense"]:
        ui.info(f"{len(content.split()):,} words (condensed)")
    else:
        ui.info(f"{len(content.split()):,} words (full text)")

    if options["plan"]:
        ui.step(f"[2/5] Load plan {options['plan']}")
        with open(options["plan"], encoding="utf-8") as f:
            slide_data = json.load(f)
    else:
        ui.step(f"[2/5] Plan the slides with {config.get('llm', {}).get('model', 'the model')}")
        slide_data = generate_slide_json(content, config, venue_override=options["venue"])
    return {"content": content, "slide_data": slide_data}


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _print_outline(data: dict) -> None:
    meta = data.get("meta", {})
    slides = data.get("slides", [])
    ui.rule()
    print(f"  {meta.get('title', '(untitled)')}")
    last_section = None
    for number, slide in enumerate(slides, 1):
        section = slide.get("section", "")
        if section != last_section:
            print(f"\n  {section}")
            last_section = section
        print(f"\n    {number:>2}. [{slide.get('layout', 'bullets')}] {slide.get('title', '')}")
        for line in _body_lines(slide.get("body", {}) or {}):
            print(f"         {line}")
    print(f"\n  {len(slides)} content slides (+ title + closing)")
    ui.rule()


def _body_lines(body: dict) -> list[str]:
    """One short line per bullet, card, cell, step, column or piece of evidence on a slide."""
    lines = []
    for bullet in body.get("bullets", []):
        lines.append(f"• {_plain(bullet.get('text', ''))}")
    for card in body.get("cards", []):
        lines.append(f"▸ {_plain(card.get('title', ''))}: {_plain(card.get('text', ''))}")
    for cell in body.get("cells", []):
        lines.append(f"▸ {_plain(cell.get('label', ''))}: {_plain(cell.get('text', ''))}")
    for step in body.get("steps", []):
        lines.append(f"→ {_plain(str(step))}")
    for column in body.get("columns", []):
        lines.append(f"◦ {_plain(column.get('lead', ''))}: {_plain(column.get('text', ''))}")
    if body.get("center") or body.get("keywords"):
        lines.append(f"◯ {_plain(body.get('center', ''))}: {', '.join(body.get('keywords', []))}")
    evidence = body.get("evidence") or {}
    if evidence:
        if evidence.get("kind") == "stats":
            parts = [f"{item.get('number', '')} {item.get('label', '')}" for item in evidence.get("items", [])]
            detail = "; ".join(parts)
        else:
            detail = evidence.get("text") or evidence.get("label") or evidence.get("number") or ""
        lines.append(f"[{evidence.get('kind', '')}] {_plain(str(detail))[:90]}")
    return lines


def _plain(text: str) -> str:
    return str(text).replace("**", "")


def _review_plan(json_path: Path, slide_data: dict, config: dict) -> dict:
    """Show the plan, take plain-language feedback, let the model revise it, and repeat until it is accepted.
    An empty answer accepts, so a run without input accepts the first plan."""
    ui.info("Review: type feedback in plain language and the model revises the deck (one call each).")
    while True:
        _print_outline(slide_data)
        answer = ui.ask("Feedback (Enter accepts, q stops)", "")
        if not answer:
            return slide_data
        if answer.lower() in ("q", "quit", "abort"):
            raise SystemExit("stopped at review")
        ui.info("revising with your feedback ...")
        try:
            revised = revise_slide_json(slide_data, answer, config)
            slide_data = apply_house_rules(revised)
            _write_json(json_path, slide_data)
            ui.ok("plan updated")
        except Exception as error:
            ui.warn(f"revision failed ({error}); rephrase, or press Enter to accept")
