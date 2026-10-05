import difflib
import re
from datetime import date
from pathlib import Path

_SECTION_KEYS = [
    "Step 1: Count",
    "Step 2: Filler scan",
    "Step 3: Proselint",
    "Step 4: Syntax",
    "Step 5: Redundancy scan",
    "Step 6: Merge",
    "Step 7: Reduce",
    "Step 8: Plain language",
    "Step 9: Proofing",
    "Step 10: Concision",
    "Step 11: Evaluate",
    "Step 12: Final check",
]

_BACKEND_LABEL = {
    "api": "Anthropic API",
    "cloud": "self-hosted (Cloud Run)",
    "local": "local Ollama",
}


def _step_num(label: str) -> str | None:
    m = re.match(r"Step\s+(\d+)", label)
    return m.group(1) if m else None


def _count_table(counts: dict) -> str:
    rows = [
        ("Original", counts.get("step1", "-")),
        ("After proselint", counts.get("step3_proselint", "-")),
        ("After syntax transforms", counts.get("step4_syntax", "-")),
        ("After merge", counts.get("step6_merge", "-")),
        ("After reduce", counts.get("step7", "-")),
        ("After plain language", counts.get("step8", "-")),
        ("After proofing", counts.get("step9", "-")),
        ("After concision (LLM)", counts.get("step10", "-")),
        ("Final", counts.get("final", "-")),
    ]
    lines = ["| Stage | Words |", "|-------|-------|"]
    for label, val in rows:
        if val != "-":
            lines.append(f"| {label} | {val} |")
    return "\n".join(lines)


def _section_for(step: str, sections: dict) -> str | None:
    """Which report section a log entry belongs to, by step number then by name."""
    if not step:
        return None
    number = _step_num(step)
    for key in sections:
        if number and _step_num(key) == number:
            return key
    for key in sections:
        if key in step:
            return key
    return None


def _group_by_step(log: list) -> dict:
    """Every log entry filed under the step that produced it."""
    sections = {key: [] for key in _SECTION_KEYS}
    for entry in log:
        key = _section_for(entry.get("step", ""), sections)
        if key is not None:
            sections[key].append(entry)
    return sections


def _models_line(run_info: dict) -> str | None:
    """Which backend and model produced the edit, or None when nothing was recorded."""
    backend = run_info.get("backend")
    model = run_info.get("model")
    if not backend:
        return None
    if backend == "skip" or not model:
        return "**Models:** deterministic only (no LLM)  "
    return f"**Models:** {model} via {_BACKEND_LABEL.get(backend, backend)}  "


def _report_header(state: dict, source_path: Path, comparison: list[str] | None) -> list[str]:
    """The report's front matter: what was edited, by what, and the word counts."""
    title = "# kopi-editor: Edit Report" if comparison else "# kopi-editor: Change Log"
    lines = [
        title,
        "",
        f"**Source:** {source_path.name}  ",
        f"**Target:** {state['target']} words  ",
    ]
    models = _models_line(state.get("run_info") or {})
    if models:
        lines.append(models)
    lines += [
        f"**Date:** {date.today().isoformat()}  ",
        "",
    ]
    if comparison:
        lines += ["## Before / After", "", *comparison, "---", ""]
    lines += [
        "## Word Count",
        "",
        _count_table(state["counts"]),
        "",
        "---",
        "",
        "## Changes by Step",
        "",
    ]
    return lines


def _changes_by_step(sections: dict) -> list[str]:
    """The per-step change list, skipping any step that did nothing."""
    lines = []
    for section_key, entries in sections.items():
        if not entries:
            continue
        lines.append(f"### {section_key}")
        lines.append("")
        for entry in entries:
            para = entry.get("para")
            prefix = f"{para}: " if para else ""
            source = entry.get("source")
            source_tag = f" `[{source}]`" if source else ""
            lines.append(f"- {prefix}{entry.get('detail', '')}{source_tag}")
            for item in entry.get("items", []):
                lines.append(f"  - {item}")
        lines.append("")
    return lines


def _evaluation_lines(metrics: dict) -> list[str]:
    """The sample evaluation block, when the run measured itself."""
    lines = ["---", "", "## Evaluation (Mu & Lim 2022 sample)", ""]
    lines.append(f"- Pairs tested: {metrics.get('n', 0)}")
    lines.append(f"- Mean TER vs human reference: {metrics.get('mean_ter', 0):.3f}")
    lines.append(f"- Sentences shortened: {metrics.get('improvements', 0)}/{metrics.get('n', 0)}")
    if metrics.get("mean_cosine_sim") is not None:
        lines.append(f"- Mean cosine similarity to reference: {metrics['mean_cosine_sim']:.3f}")
    lines.append("")
    return lines


def _write_review(review_items: list, source_path: Path, review_path: Path) -> None:
    """Write the repeated-suggestion sheet the author ticks through once."""
    lines = [
        "# kopi-editor: Proofing Review",
        "",
        f"**Source:** {source_path.name}  ",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        "These suggestions appeared multiple times. Decide once: mark `[x]` to apply globally.",
        "",
        "---",
        "",
    ]
    for item in review_items:
        repls = " / ".join(f"`{r}`" for r in item["replacements"])
        paras = ", ".join(item["paras"])
        lines += [
            f"## `{item['original']}` -> {repls}",
            "",
            f"- Rule: `{item['rule_id']}`",
            f"- Appears: {item['count']}x ({paras})",
            f"- Message: {item['message']}",
            "",
            "- [ ] Apply all",
            "- [ ] Skip all",
            "",
        ]
    review_path.write_text("\n".join(lines), encoding="utf-8-sig")


def _write_diff(state: dict, source_path: Path, diff_path: Path) -> Path | None:
    """Write the unified diff, or None when the edit changed nothing."""
    original = state.get("original_text", "")
    final = state.get("final_text", "")
    if not (original and final and original != final):
        return None
    diff_text = _build_diff(original, final, source_path.name)
    if not diff_text.strip():
        return None
    # Plain UTF-8 (no BOM) so diff viewers parse the headers cleanly.
    diff_path.write_text(diff_text, encoding="utf-8")
    return diff_path


def _table_cell(paragraphs: list[str]) -> str:
    """Paragraphs as one markdown table cell: line breaks become spaces and a pipe is escaped."""
    text = " ¶ ".join(" ".join(paragraph.split()) for paragraph in paragraphs)
    return text.replace("|", "\\|")


def _side_by_side_rows(original: str, final: str) -> list[str]:
    """One table row per paragraph, original beside edited, paired by matching unchanged paragraphs.

    Unchanged paragraphs say so in the edited column, so the changed ones stand out.
    """
    before = [part for part in original.split("\n\n") if part.strip()]
    after = [part for part in final.split("\n\n") if part.strip()]
    rows = []
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        old_part = before[start_a:end_a]
        new_part = after[start_b:end_b]
        if tag == "equal":
            for paragraph in old_part:
                rows.append(f"| {_table_cell([paragraph])} | _unchanged_ |")
        elif tag == "replace" and len(old_part) == len(new_part):
            for paragraph, edited in zip(old_part, new_part):
                rows.append(f"| {_table_cell([paragraph])} | {_table_cell([edited])} |")
        else:
            left = _table_cell(old_part) if old_part else "_new_"
            right = _table_cell(new_part) if new_part else "_removed_"
            rows.append(f"| {left} | {right} |")
    return rows


def _write_side_by_side(state: dict, source_path: Path, path: Path) -> Path | None:
    """Write the original and edited paragraphs side by side as a markdown table, for review and copying."""
    original = state.get("original_text", "")
    final = state.get("final_text", "")
    if not (original and final):
        return None
    lines = [
        f"# {source_path.name}: original and edited",
        "",
        "| Original | Edited |",
        "|---|---|",
    ]
    lines += _side_by_side_rows(original, final)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def write_outputs(
    state: dict, source_path: Path, out_dir: Path = None, comparison: list[str] | None = None
) -> dict:
    """Write the edited text, the report, the review sheet, the side-by-side table and the diff.

    Returns:
        Mapping with `edited`, `report`, `side_by_side` and `diff`; `diff` is None when the
        edit changed nothing.
    """
    stem = source_path.stem
    out_dir = Path(out_dir) if out_dir is not None else source_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    original_path = out_dir / f"{stem}_original.md"
    edited_path = out_dir / f"{stem}_edited.md"
    # When a before/after comparison is supplied (the edit route), the change log
    # and the comparison are merged into one '_report.md'; otherwise (proof) the
    # plain '_changelog.md' is written.
    log_path = out_dir / (f"{stem}_report.md" if comparison else f"{stem}_changelog.md")
    diff_path = out_dir / f"{stem}.diff"
    review_path = out_dir / f"{stem}_review.md"
    side_by_side_path = out_dir / f"{stem}_side-by-side.md"

    edited_path.write_text(state["final_text"], encoding="utf-8-sig")
    # Also write the extracted source as text, so it can be diffed side-by-side
    # against the edit in an editor (the source .docx is binary, the edit is .md).
    if state.get("original_text"):
        original_path.write_text(state["original_text"], encoding="utf-8-sig")

    lines = _report_header(state, source_path, comparison)
    lines += _changes_by_step(_group_by_step(state["log"]))

    if state.get("flags"):
        lines += ["---", "", "## Flags for Author Review", ""]
        for flag in state["flags"]:
            lines.append(f"- {flag}")
        lines.append("")

    if state.get("eval_metrics"):
        lines += _evaluation_lines(state["eval_metrics"])

    log_path.write_text("\n".join(lines), encoding="utf-8-sig")

    review_items = state.get("review_items", [])
    if review_items:
        _write_review(review_items, source_path, review_path)

    return {
        "edited": edited_path,
        "report": log_path,
        "side_by_side": _write_side_by_side(state, source_path, side_by_side_path),
        "diff": _write_diff(state, source_path, diff_path),
    }


def _diff_lines(text: str) -> list[str]:
    """Render text one sentence per line (blank line between paragraphs) so the
    unified diff localises changes to the sentence, not the whole paragraph."""
    lines = []
    for para in text.split("\n\n"):
        para = " ".join(para.split())
        if not para:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para):
            if sent:
                lines.append(sent + "\n")
        lines.append("\n")  # paragraph break
    return lines


def _build_diff(original: str, final: str, name: str) -> str:
    """A standard **unified diff** (real `.diff` syntax) of original vs edited.

    Sentence-per-line granularity keeps hunks small and lets a diff viewer
    highlight exactly what changed. Plain unified-diff text, no markdown, so it
    renders in any `.diff`/patch viewer.
    """
    udiff = difflib.unified_diff(
        _diff_lines(original), _diff_lines(final),
        fromfile=f"a/{name}", tofile=f"b/{name}", n=3,
    )
    return "".join(udiff)
