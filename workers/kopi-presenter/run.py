#!/usr/bin/env python3
"""
kopi-presenter CLI — manuscript/outline -> PowerPoint (.pptx) + PDF.

Pipeline: parse -> LLM slide JSON -> lint -> house rules -> build .pptx -> export PDF.

Usage:
    python run.py input/manuscript.docx
    python run.py input/outline.txt --venue "ICA 2026, Brisbane"
    python run.py input/paper.docx --review          # review/edit the plan first
    python run.py input/paper.docx --emoji            # emoji instead of Fluent icons
    python run.py input/paper.docx --dry-run          # print JSON plan only
    python run.py input/paper.docx --plan plan.json   # skip LLM, rebuild from JSON
    python run.py input/paper.docx --no-pdf           # .pptx only
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Windows consoles default to cp1252; force UTF-8 so progress glyphs (→, …) print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from slides.config import load_config
from slides.emitter_pptx import build_pptx
from slides.linter import lint_and_repair
from slides.llm import generate_slide_json, revise_slide_json
from slides.parser import parse_input
from slides.renderer_pptx import export_pdf
from slides.rules import apply_house_rules

_log = lambda *a, **kw: print(*a, **kw, file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate academic conference slides from a manuscript or outline."
    )
    ap.add_argument("input_file", help="Input .docx or .txt file")
    ap.add_argument("-o", "--output", default=None, help="Output directory (default: beside input)")
    ap.add_argument("--venue", default=None, help="Venue string (overrides manuscript + config default)")
    ap.add_argument("--no-pdf", action="store_true", help="Skip PDF rendering")
    ap.add_argument("--no-render", action="store_true", help="Skip PDF rendering (.pptx only)")
    ap.add_argument("--plan", default=None, metavar="FILE", help="Load existing JSON plan (skip LLM)")
    ap.add_argument("--dry-run", action="store_true", help="Print JSON plan to stdout; write no files")
    ap.add_argument("--review", action="store_true",
                    help="Pause after the plan is generated to review/edit it before rendering")
    ap.add_argument("--emoji", action="store_true",
                    help="Use colour emoji instead of the default Segoe Fluent icons")
    ap.add_argument("--condense", action="store_true",
                    help="Condense long .docx paragraphs (first+last sentence) instead of sending the full text")
    args = ap.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        sys.exit(f"Error: '{args.input_file}' not found.")

    config = load_config()
    if args.emoji:
        config.setdefault("render", {})["icons"] = "emoji"
    output_dir = Path(args.output) if args.output else (ROOT / "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    # ── 1. Parse ────────────────────────────────────────────────────────────
    _log(f"\n[1/5] Parsing  {input_path.name} ...")
    content = parse_input(input_path, condense=args.condense)
    _log(f"       {len(content.split()):,} words "
         f"({'condensed' if args.condense else 'full text'})")

    # ── 2. LLM or load JSON ─────────────────────────────────────────────────
    if args.plan:
        _log(f"[2/5] Loading JSON  {args.plan} ...")
        with open(args.plan, encoding="utf-8") as f:
            slide_data = json.load(f)
    else:
        _log(f"[2/5] Calling {config.get('llm', {}).get('model', 'LLM')} ...")
        slide_data = generate_slide_json(content, config, venue_override=args.venue)

    if args.dry_run:
        _log("\n── JSON plan (dry-run) ──────────────────────────────────")
        print(json.dumps(slide_data, indent=2, ensure_ascii=False))
        return

    # Save JSON for reuse / debugging
    json_path = output_dir / f"{stem}.json"
    _write_json(json_path, slide_data)
    _log(f"       JSON → {json_path.name}")

    # ── 2b. Optional conversational review ──────────────────────────────────
    if args.review:
        slide_data = _review_plan(json_path, slide_data, config)

    # ── 3. Lint ─────────────────────────────────────────────────────────────
    _log("[3/5] Linting ...")
    slide_data = lint_and_repair(slide_data, content, config)
    slide_data = apply_house_rules(slide_data)

    # ── 4. Emit .pptx ───────────────────────────────────────────────────────
    pptx_path = output_dir / f"{stem}.pptx"
    _log(f"[4/5] Building  {pptx_path.name} ...")
    build_pptx(slide_data, pptx_path, config)
    n_slides = len(slide_data.get("slides", []))
    _log(f"       {n_slides} content slides  (+title +closing = {n_slides + 2} total)")
    _log(f"       → {pptx_path.name}  ({pptx_path.stat().st_size // 1024} KB)")

    # ── 5. Render PDF ─────────────────────────────────────────────────────────
    if args.no_render or args.no_pdf:
        _log("[5/5] Skipping PDF (--no-pdf/--no-render).")
    else:
        _log("[5/5] Exporting PDF ...")
        if export_pdf(pptx_path):
            pdf_path = pptx_path.with_suffix(".pdf")
            _log(f"       → {pdf_path.name}  ({pdf_path.stat().st_size // 1024} KB)")
        else:
            _log("       PDF export failed (no PowerPoint or LibreOffice found).")

    _log(f"\nDone.  Output → {output_dir.resolve()}\n")


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _print_outline(data: dict) -> None:
    meta = data.get("meta", {})
    slides = data.get("slides", [])
    _log("\n── Plan ──────────────────────────────────────────────────")
    _log(f"   {meta.get('title', '(untitled)')}")
    last_section = None
    for i, s in enumerate(slides, 1):
        section = s.get("section", "")
        if section != last_section:
            _log(f"\n   {section}")
            last_section = section
        layout = s.get("layout", "bullets")
        _log(f"\n     {i:>2}. [{layout}] {s.get('title', '')}")
        body = s.get("body", {}) or {}
        for b in body.get("bullets", []):
            _log(f"          • {_plain(b.get('text', ''))}")
        for c in body.get("cards", []):
            _log(f"          ▸ {_plain(c.get('title', ''))}: {_plain(c.get('text', ''))}")
        for cell in body.get("cells", []):
            _log(f"          ▸ {_plain(cell.get('label', ''))}: {_plain(cell.get('text', ''))}")
        for step in body.get("steps", []):
            _log(f"          → {_plain(str(step))}")
        for col in body.get("columns", []):
            _log(f"          ◦ {_plain(col.get('lead', ''))}: {_plain(col.get('text', ''))}")
        if body.get("center") or body.get("keywords"):
            _log(f"          ◯ {_plain(body.get('center', ''))} — {', '.join(body.get('keywords', []))}")
        ev = body.get("evidence") or {}
        if ev:
            if ev.get("kind") == "stats":
                detail = "; ".join(f"{it.get('number','')} {it.get('label','')}" for it in ev.get("items", []))
            else:
                detail = ev.get("text") or ev.get("label") or ev.get("number") or ""
            _log(f"          [{ev.get('kind', '')}] {_plain(str(detail))[:90]}")
    _log(f"\n   {len(slides)} content slides (+ title + closing)")
    _log("──────────────────────────────────────────────────────────")


def _plain(text: str) -> str:
    return str(text).replace("**", "")


def _review_plan(json_path: Path, slide_data: dict, config: dict) -> dict:
    """Conversational review: show the plan, take plain-language feedback, let the
    LLM revise it, repeat until the presenter accepts (or aborts)."""
    _log("\n   Review mode: type feedback in plain language and the assistant will")
    _log("   revise the deck (each revision is one LLM call). Press Enter to accept.")
    while True:
        _print_outline(slide_data)
        resp = input("\nFeedback (or [Enter] to accept · [q] to abort):\n> ").strip()
        if resp == "":
            return slide_data
        if resp.lower() in ("q", "quit", "abort"):
            sys.exit("Aborted at review.")
        _log("       Revising with your feedback ...")
        try:
            revised = revise_slide_json(slide_data, resp, config)
            slide_data = apply_house_rules(revised)
            _write_json(json_path, slide_data)
            _log("       Plan updated.")
        except Exception as e:
            _log(f"       Revision failed ({e}). Try rephrasing, or press Enter to accept.")


if __name__ == "__main__":
    main()
