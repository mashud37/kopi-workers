"""Write the damage set as two documents: the sheet a person reads to judge
each edit, and the rates that fall out of the verdicts already recorded.
"""
from pathlib import Path

from damage import verdicts

OUTPUT = Path("output")


def _paragraph_lines(row: dict, judged: dict) -> list:
    lines = [
        f"## {row['key']} ({row['band']})",
        "",
        f"**Original.** {row['original']}",
        "",
        f"**Linted.** {row['linted']}",
        "",
        f"**Opus.** {row['gold']}",
        "",
    ]
    for edit in row["edits"]:
        verdict = judged.get(edit["id"])
        said = "unjudged"
        if verdict:
            said = verdict["verdict"]
            if verdict["broken"]:
                said = f"{said}, {' '.join(verdict['broken'])}: {verdict['why']}"
        lines.append(f"- `{edit['id']}` deletes `{edit['source']}` at {edit['confidence']:.2f}, "
                     f"{edit['triage']} attests it. **{said}**")
    lines.append("")
    return lines


def write_sheet(sheet: list, judged: dict) -> Path:
    """The judging sheet: every changed paragraph with its edits and any verdict."""
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "damage_sheet.md"
    lines = [
        "# The hand-checked damage set",
        "",
        f"{len(sheet)} paragraphs the linter changed, from the held-out documents, in corpus "
        "order. Each edit is judged against G1 (truth conditions), G2 (attribution) and G3 "
        "(grammaticality) in `docs/good.md` section 2. A paragraph is damaged when any edit in "
        "it is.",
        "",
        "Verdicts live in `damage/verdicts.jsonl`, one row per edit id.",
        "",
    ]
    for row in sheet:
        lines += _paragraph_lines(row, judged)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _table(title: str, rows: dict) -> list:
    lines = [f"| {title} | Edits | Damaged | Rate |", "|---|---:|---:|---:|"]
    for name in sorted(rows, key=lambda name: -rows[name]["edits"]):
        row = rows[name]
        share = row["damaged"] / row["edits"] if row["edits"] else 0.0
        lines.append(f"| {name} | {row['edits']} | {row['damaged']} | {share:.0%} |")
    lines.append("")
    return lines


def write_summary(summary: dict) -> Path:
    """The rates: overall, by criterion, by band, by triage class and by word."""
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "damage_rate.md"
    paragraphs, totals = summary["paragraphs"], summary["totals"]
    hurt = paragraphs["damaged"] / paragraphs["changed"] if paragraphs["changed"] else 0.0
    per_edit = totals["damaged"] / totals["edits"] if totals["edits"] else 0.0
    lines = [
        "# Damage rate on the hand-checked set",
        "",
        f"**{paragraphs['damaged']} of {paragraphs['changed']} changed paragraphs carry an edit "
        f"that violates G1 to G3, {hurt:.0%}.** Per edit, {totals['damaged']} of "
        f"{totals['edits']} ({per_edit:.0%}).",
        "",
        f"{len(summary['unjudged'])} edits in the sheet have no verdict yet.",
        "",
        "| Criterion | Edits that break it |",
        "|---|---:|",
    ]
    for name in verdicts.CRITERIA:
        lines.append(f"| {name} | {summary['broken'][name]} |")
    lines.append(f"| punctuation, outside G1 to G3 | {summary['broken']['punctuation']} |")
    lines += ["", "## By band", ""]
    lines += _table("Band", summary["by_band"])
    lines += [
        "## By who attests the edit",
        "",
        "`both` is Opus and the foil, `gold` is Opus alone, `neither` is the class step 9 was "
        "told to triage by. A high rate in `both` means agreement with the reference does not "
        "protect the reader.",
        "",
    ]
    lines += _table("Attested by", summary["by_triage"])
    lines += ["## Words that damage more than once", ""]
    lines += ["| Deleted word | Edits | Damaged |", "|---|---:|---:|"]
    for row in verdicts.worst_words(summary):
        lines.append(f"| `{row['word']}` | {row['edits']} | {row['damaged']} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
