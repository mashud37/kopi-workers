import difflib
import re
from pathlib import Path
from datetime import date


def _step_num(label: str) -> str | None:
    m = re.match(r"Step\s+(\d+)", label)
    return m.group(1) if m else None


def _count_table(counts: dict) -> str:
    rows = [
        ("Original", counts.get("step1", "—")),
        ("After proselint", counts.get("step3_proselint", "—")),
        ("After syntax transforms", counts.get("step4_syntax", "—")),
        ("After merge", counts.get("step6_merge", "—")),
        ("After reduce", counts.get("step7", "—")),
        ("After plain language", counts.get("step8", "—")),
        ("After proofing", counts.get("step9", "—")),
        ("After concision (LLM)", counts.get("step10", "—")),
        ("Final", counts.get("final", "—")),
    ]
    lines = ["| Stage | Words |", "|-------|-------|"]
    for label, val in rows:
        if val != "—":
            lines.append(f"| {label} | {val} |")
    return "\n".join(lines)


_SECTION_KEYS = [
    "Step 1 — Count",
    "Step 2 — Filler scan",
    "Step 3 — Proselint",
    "Step 4 — Syntax",
    "Step 5 — Redundancy scan",
    "Step 6 — Merge",
    "Step 7 — Reduce",
    "Step 8 — Plain language",
    "Step 9 — Proofing",
    "Step 10 — Concision",
    "Step 11 — Evaluate",
    "Step 12 — Final check",
]


def write_outputs(state: dict, source_path: Path, out_dir: Path = None) -> tuple[Path, Path]:
    stem = source_path.stem
    out_dir = Path(out_dir) if out_dir is not None else source_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    edited_path = out_dir / f"{stem}_edited.md"
    changelog_path = out_dir / f"{stem}_changelog.md"
    diff_path = out_dir / f"{stem}.diff"
    review_path = out_dir / f"{stem}_review.md"

    edited_path.write_text(state["final_text"], encoding="utf-8-sig")

    sections = {k: [] for k in _SECTION_KEYS}

    for entry in state["log"]:
        step = entry.get("step", "")
        step_n = _step_num(step)
        matched = False
        for key in sections:
            if step_n and _step_num(key) == step_n:
                sections[key].append(entry)
                matched = True
                break
        if not matched and step:
            for key in sections:
                if key in step:
                    sections[key].append(entry)
                    break

    lines = [
        "# kopi-editor — Change Log",
        "",
        f"**Source:** {source_path.name}  ",
        f"**Target:** {state['target']} words  ",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        "## Word Count",
        "",
        _count_table(state["counts"]),
        "",
        "---",
        "",
        "## Changes by Step",
        "",
    ]

    for section_key, entries in sections.items():
        if not entries:
            continue
        lines.append(f"### {section_key}")
        lines.append("")
        for entry in entries:
            para = entry.get("para")
            detail = entry.get("detail", "")
            source = entry.get("source")
            prefix = f"{para}: " if para else ""
            source_tag = f" `[{source}]`" if source else ""
            lines.append(f"- {prefix}{detail}{source_tag}")
            for item in entry.get("items", []):
                lines.append(f"  - {item}")
        lines.append("")

    if state.get("flags"):
        lines += ["---", "", "## Flags for Author Review", ""]
        for flag in state["flags"]:
            lines.append(f"- {flag}")
        lines.append("")

    if state.get("eval_metrics"):
        m = state["eval_metrics"]
        lines += ["---", "", "## Evaluation (Mu & Lim 2022 sample)", ""]
        lines.append(f"- Pairs tested: {m.get('n', 0)}")
        lines.append(f"- Mean TER vs human reference: {m.get('mean_ter', 0):.3f}")
        lines.append(f"- Sentences shortened: {m.get('improvements', 0)}/{m.get('n', 0)}")
        if m.get("mean_cosine_sim") is not None:
            lines.append(f"- Mean cosine similarity to reference: {m['mean_cosine_sim']:.3f}")
        lines.append("")

    changelog_path.write_text("\n".join(lines), encoding="utf-8-sig")

    review_items = state.get("review_items", [])
    if review_items:
        rlines = [
            "# kopi-editor — Proofing Review",
            "",
            f"**Source:** {source_path.name}  ",
            f"**Date:** {date.today().isoformat()}  ",
            "",
            "These suggestions appeared multiple times. Decide once — mark `[x]` to apply globally.",
            "",
            "---",
            "",
        ]
        for item in review_items:
            repls = " / ".join(f"`{r}`" for r in item["replacements"])
            paras = ", ".join(item["paras"])
            rlines += [
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
        review_path.write_text("\n".join(rlines), encoding="utf-8-sig")

    original = state.get("original_text", "")
    final = state.get("final_text", "")
    written_diff = None
    if original and final and original != final:
        diff_text = _build_diff(original, final, source_path.name)
        if diff_text.strip():
            # Plain UTF-8 (no BOM) so diff viewers parse the headers cleanly.
            diff_path.write_text(diff_text, encoding="utf-8")
            written_diff = diff_path

    return edited_path, changelog_path, written_diff


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
    highlight exactly what changed. Plain unified-diff text — no markdown — so it
    renders in any `.diff`/patch viewer.
    """
    udiff = difflib.unified_diff(
        _diff_lines(original), _diff_lines(final),
        fromfile=f"a/{name}", tofile=f"b/{name}", n=3,
    )
    return "".join(udiff)
