"""Render a family comparison as markdown."""


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
    defect_kinds = set()
    for report in reports:
        for kind in report.defects:
            defect_kinds.add(kind)
    seen = sorted(defect_kinds)
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
    lines += ["| Method | add | keep | delete |", "|---|---:|---:|---:|"]
    for r in reports:
        lines.append(f"| {r.name} | {r.sari['add']:.4f} | {r.sari['keep']:.4f} | "
                     f"{r.sari['delete']:.4f} |")
    lines += ["", "## Verdict", ""]
    for r in reports:
        if not r.clean:
            verdict = f"**disqualified** ({len(r.case_failures)} case failures)"
        elif r.sari["sari"] <= baseline:
            verdict = "no gain over doing nothing"
        else:
            verdict = "admissible"
        lines.append(f"- `{r.name}`: {verdict}. {r.note}")
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
