"""Render a family comparison as markdown."""


def _verdict(report, baseline: float) -> str:
    if not report.clean:
        return f"**disqualified** ({len(report.case_failures)} case failures)"
    if report.sari["sari"] <= baseline:
        return "no gain over doing nothing"
    return "admissible"


def _summary_table(reports, baseline: float) -> list:
    lines = [
        "| Method | Cases | SARI | vs nothing | Fired | Ceiling | Changed | Words | Defects |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in reports:
        passed = r.cases_run - len(r.case_failures)
        mark = "" if r.clean else " **X**"
        name = f"**{r.name}**" if r.baseline else r.name
        lines.append(
            f"| {name} | {passed}/{r.cases_run}{mark} | {r.sari['sari']:.4f} | "
            f"{r.sari['sari'] - baseline:+.4f} | {r.fired} | {r.ceiling:.0%} | "
            f"{r.changed} | {r.words_removed} | {r.defect_paragraphs} |"
        )
    return lines


def _sari_table(reports) -> list:
    lines = ["| Method | add | keep | delete |", "|---|---:|---:|---:|"]
    for r in reports:
        lines.append(f"| {r.name} | {r.sari['add']:.4f} | {r.sari['keep']:.4f} | "
                     f"{r.sari['delete']:.4f} |")
    return lines


def _failures_section(reports) -> list:
    lines = ["## Case failures", ""]
    if all(r.clean for r in reports):
        lines += ["No method failed a case.", ""]
        return lines
    for report in reports:
        if report.clean:
            continue
        lines.append(f"### {report.name}")
        lines.append("")
        for case, what in report.case_failures:
            tag = "observed" if case.observed else "constructed"
            lines.append(f"- *{case.why}* ({tag})")
            lines.append(f"  - `{case.text}`")
            lines.append(f"  - {what}")
        lines.append("")
    return lines


def _defects_section(reports) -> list:
    lines = ["## Grammatical defects introduced", ""]
    seen = sorted({kind for r in reports for kind in r.defects})
    if not seen:
        lines += ["None, by any method.", ""]
        return lines
    lines.append("| Method | " + " | ".join(seen) + " |")
    lines.append("|---" * (len(seen) + 1) + "|")
    for r in reports:
        counts = " | ".join(str(r.defects.get(kind, 0)) for kind in seen)
        lines.append(f"| {r.name} | {counts} |")
    lines.append("")
    return lines


def render(family: str, reports: list, baseline: float, samples: int,
           realisation_failures: list) -> str:
    """Full markdown comparison for one family."""
    lines = [
        f"# Method comparison: {family}",
        "",
        f"{len(reports)} methods over {samples} gold paragraphs. "
        f"Do-nothing baseline SARI {baseline:.4f}.",
        "",
        "Cases are licence conditions from `docs/good.md`. A method that fails one is "
        "disqualified whatever its corpus score, because the case describes text it damages. "
        "Ceiling is an upper bound on precision, not precision.",
        "",
    ]
    lines += _summary_table(reports, baseline)
    lines += ["", "## SARI components", ""]
    lines += _sari_table(reports)
    lines += ["", "## Verdict", ""]
    for r in reports:
        lines.append(f"- `{r.name}`: {_verdict(r, baseline)}. {r.note}")
    lines.append("")
    lines += _failures_section(reports)
    lines += _defects_section(reports)

    lines += ["## Surface repair cases", ""]
    if realisation_failures:
        for case, what in realisation_failures:
            tag = "observed" if case.observed else "constructed"
            lines += [f"- **FAIL** *{case.why}* ({tag})", f"  - `{case.text}`", f"  - {what}"]
    else:
        lines.append("All surface repair cases pass.")
    lines.append("")
    return "\n".join(lines)
