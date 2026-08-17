"""Render a taxonomy tally as the Markdown evidence report: each
transformation family's corpus share, word count, behaviour across bands,
existing rule coverage, and worked examples.
"""
import json
from datetime import datetime
from pathlib import Path

OUTPUT = Path("output")


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "0.0%"


def _family_table(tally) -> list[str]:
    total = sum(tally.families.values()) or 1
    lines = [
        "| Family | Instances | Share | Words moved | Covered by existing rules |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, count in tally.families.most_common():
        covered = sum(v for k, v in tally.subtypes.items()
                      if k.startswith(f"{family}/table:"))
        lines.append(
            f"| `{family}` | {count} | {_pct(count, total)} | "
            f"{tally.words_moved.get(family, 0)} | {_pct(covered, count)} |"
        )
    return lines


def _subtype_table(tally) -> list[str]:  # lint-style: ignore FN004
    total = sum(tally.subtypes.values()) or 1
    lines = ["| Transformation | Instances | Share |", "|---|---:|---:|"]
    for subtype, count in tally.subtypes.most_common():
        lines.append(f"| `{subtype}` | {count} | {_pct(count, total)} |")
    return lines


def _band_table(tally) -> list[str]:
    bands = [b for b in ("clarity", "light", "firm", "aggressive") if b in tally.by_band]
    if not bands:
        return []
    families = [f for f, _ in tally.families.most_common()]
    header = "| Family | " + " | ".join(bands) + " |"
    lines = [header, "|---" * (len(bands) + 1) + "|"]
    for family in families:
        row = [f"| `{family}` "]
        for band in bands:
            band_total = sum(v for k, v in tally.by_band[band].items() if not k.startswith("bead:"))
            row.append(f"| {_pct(tally.by_band[band].get(family, 0), band_total)} ")
        lines.append("".join(row) + "|")
    return lines


def _bead_table(tally) -> list[str]:
    total = sum(tally.beads.values()) or 1
    labels = {
        "keep": "sentence returned untouched",
        "rewrite": "sentence rewritten in place",
        "merge": "several sentences absorbed into one",
        "split": "one sentence became several",
        "delete": "sentence dropped outright",
        "insert": "sentence added (should be near zero)",
    }
    lines = ["| Sentence operation | Count | Share | Meaning |", "|---|---:|---:|---|"]
    for op, count in tally.beads.most_common():
        lines.append(f"| `{op}` | {count} | {_pct(count, total)} | {labels.get(op, '')} |")
    return lines


def _loss_table(tally) -> list[str]:  # lint-style: ignore FN004
    lines = ["| Band | Median content loss | Sentences |", "|---|---:|---:|"]
    for band in ("clarity", "light", "firm", "aggressive"):
        values = tally.content_loss.get(band, [])
        if not values:
            continue
        ordered = sorted(values)
        median = ordered[len(ordered) // 2]
        lines.append(f"| {band} | {median:.1%} | {len(values)} |")
    return lines


def _examples_section(tally) -> list[str]:
    lines = ["## Worked examples", ""]
    for subtype, _ in tally.subtypes.most_common():
        rows = tally.examples.get(subtype, [])[:6]
        if not rows:
            continue
        block = ["| Original | Edited | Band |", "|---|---|---|"]
        for source, target, band in rows:
            src = (source or "").replace("|", "\\|")[:110] or "(nothing)"
            tgt = (target or "").replace("|", "\\|")[:110] or "(deleted)"
            block.append(f"| {src} | {tgt} | {band} |")
        lines += [f"### `{subtype}`", "", *block, ""]
    return lines


def _header(tally, samples, roles: str, elapsed: float) -> list[str]:
    total_spans = sum(tally.families.values()) or 1
    covered = sum(tally.covered.values())
    return [
        "# Transformation evidence",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} from {len(samples)} edits "
        f"({roles}) over {len({s.doc for s in samples})} documents, in {elapsed:.0f}s.",
        "",
        f"- Sentence beads aligned: **{sum(tally.beads.values())}**",
        f"- Span transformations classified: **{total_spans}**",
        f"- Already covered by kopi-editor's rule tables: **{covered}** "
        f"({_pct(covered, total_spans)})",
        "",
    ]


def render(tally, samples, roles: str, elapsed: float) -> str:
    sections = [
        ("Sentence-level operations", _bead_table(tally)),
        ("Transformation families", _family_table(tally)),
        ("Family share by requested intensity", _band_table(tally)),
        ("Content lemmas lost per rewritten sentence (median)", _loss_table(tally)),
        ("Every transformation, by frequency", _subtype_table(tally)),
    ]
    lines = _header(tally, samples, roles, elapsed)
    for title, table in sections:
        lines += [f"## {title}", "", *table, ""]
    lines += _examples_section(tally)
    return "\n".join(lines)


def write(tally, samples, roles: str, elapsed: float, stem: str = "evidence") -> Path:
    """Write the markdown report and the raw findings, return the report path."""
    OUTPUT.mkdir(exist_ok=True)
    report = OUTPUT / f"{stem}.md"
    report.write_text(render(tally, samples, roles, elapsed), encoding="utf-8")
    findings = OUTPUT / f"{stem}_findings.jsonl"
    with findings.open("w", encoding="utf-8") as handle:
        for item in tally.findings:
            handle.write(json.dumps(item.__dict__, ensure_ascii=False) + "\n")
    return report
