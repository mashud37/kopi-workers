"""Render the oracle execution probe as markdown: what each backend wrote at
gold sites, in span closure and exact match.
"""
from execute import backends, oracle

_FAMILY_MINIMUM = 40


def _preamble(corpus: dict, target: float) -> list:
    return [
        "# Oracle execution probe",
        "",
        f"{corpus['tasks']} tasks from {corpus['paragraphs']} gold paragraphs"
        f"{corpus['filter']}. One task is one span Opus changed. The backend is handed that",
        "span, four words of context each side, and the name of the change an editor makes",
        "there, and is asked for the replacement. The site is a gift; the wording is not.",
        "",
        "**Span closure** is the project's master metric read at span level. Leaving the span",
        "as the author wrote it scores 0, writing Opus's own words scores 100%, and writing",
        "something further from Opus than the original scores below zero. `keep` and `delete`",
        "are anchors rather than candidates: they are what the engine can already do.",
        "",
        f"The bar was named before the run at **{target:.0%} exact-or-near match** on the",
        "rewriting spans. Near match, defined as landing within one word of Opus, turned out",
        "to be degenerate: doing nothing scores 39% on it, because a one-word replacement is",
        "one word away from its own source. So near match is dropped and the figure is applied",
        "to exact match, with a second gate a do-nothing also cannot pass: a rewriting backend",
        "has to close more of the span-level gap than blindly deleting the span does.",
        "",
    ]


def _summary(results: dict) -> list:
    lines = [
        "## Every backend",
        "",
        "| Backend | Tasks | Answered | Exact | Beats keep | Beats delete | "
        "Span closure | Median call |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        row = oracle.summarise(result["total"])
        seconds = oracle.latency(result["seconds"])
        mark = " *(reads the gold)*" if backends.BACKENDS[name]["reads_gold"] else ""
        lines.append(
            f"| `{name}`{mark} | {row['tasks']} | {row['answered']:.0%} | "
            f"{row['exact']:.1%} | {row['beats_keep']:.1%} | {row['beats_delete']:.1%} | "
            f"{row['closure']:.1%} | {seconds * 1000:.1f} ms |"
        )
    lines.append("")
    return lines


def _rewriting(result: dict) -> dict:
    return oracle.summarise(result["kind"].get("rewriting", oracle.blank()))


def _by_kind(results: dict) -> list:
    lines = [
        "## Deleting against rewriting",
        "",
        "The whole question of the tier. Deletion is what the linter can already do; the",
        "rewriting spans are the `add` column it has never opened.",
        "",
        "| Backend | Deletion closure | Rewriting closure | Rewriting exact | "
        "Rewriting beats delete |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        deletion = oracle.summarise(result["kind"].get("deletion", oracle.blank()))
        rewriting = _rewriting(result)
        lines.append(
            f"| `{name}` | {deletion['closure']:.1%} | {rewriting['closure']:.1%} | "
            f"{rewriting['exact']:.1%} | {rewriting['beats_delete']:.1%} |"
        )
    lines.append("")
    return lines


def _by_family(results: dict) -> list:
    names = list(results)
    counts = {}
    for name in names:
        for family, row in results[name]["family"].items():
            counts[family] = row["tasks"]
    ranked = sorted(counts, key=lambda family: -counts[family])
    lines = [
        "## Span closure by family",
        "",
        f"Families with at least {_FAMILY_MINIMUM} tasks.",
        "",
        "| Family | Tasks | " + " | ".join(f"`{name}`" for name in names) + " |",
        "|---|---:" + "|---:" * len(names) + "|",
    ]
    for family in ranked:
        if counts[family] < _FAMILY_MINIMUM:
            continue
        cells = []
        for name in names:
            row = results[name]["family"].get(family, oracle.blank())
            cells.append(f"{oracle.summarise(row)['closure']:.1%}")
        lines.append(f"| {family} | {counts[family]} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _by_split(results: dict) -> list:
    lines = [
        "## Training documents against held-out ones",
        "",
        "Only `tagger-ceiling` is fitted to anything, so only its two columns are allowed to",
        "differ for a reason. A gap there is the induced vocabulary failing to transfer.",
        "",
        "| Backend | Train closure | Held-out closure | Held-out tasks |",
        "|---|---:|---:|---:|",
    ]
    for name, result in results.items():
        train = oracle.summarise(result["split"].get("train", oracle.blank()))
        test = oracle.summarise(result["split"].get("test", oracle.blank()))
        lines.append(f"| `{name}` | {train['closure']:.1%} | {test['closure']:.1%} | "
                     f"{test['tasks']} |")
    lines.append("")
    return lines


def _call(name: str, result: dict, floor: float, target: float) -> str:
    """Whether one backend cleared both gates, or is exempt from being asked."""
    entry = backends.BACKENDS[name]
    if entry["anchor"]:
        return "anchor, not a candidate"
    if entry["reads_gold"]:
        return "ceiling, not a system score"
    rewriting = _rewriting(result)
    if rewriting["exact"] >= target and rewriting["closure"] > floor:
        return "**clears both gates**"
    if rewriting["closure"] > floor:
        return f"below {target:.0%} exact, but closes more than deleting does"
    return "**refused**: it does not beat dropping the span"


def _verdicts(results: dict, target: float) -> list:
    floor = _rewriting(results["delete"])["closure"] if "delete" in results else 0.0
    lines = [
        "## Verdict",
        "",
        f"The delete anchor closes {floor:.1%} of the rewriting gap. That is the floor.",
        "",
    ]
    for name, result in results.items():
        rewriting = _rewriting(result)
        lines.append(
            f"- `{name}`: {_call(name, result, floor, target)}. "
            f"{backends.BACKENDS[name]['what']}. Rewriting closure {rewriting['closure']:.1%}, "
            f"exact {rewriting['exact']:.1%} over {rewriting['tasks']} spans."
        )
    lines.append("")
    return lines


def render(results: dict, corpus: dict, target: float) -> str:
    """Full markdown for one oracle run.

    Args:
        results: ``{backend name: oracle.score result}`` in report order.
        corpus: ``{"tasks", "paragraphs", "vocabulary", "filter"}``, the last
            naming a family filter when one was applied.
        target: the exact-match rate on rewriting spans a backend must reach,
            fixed before the run so the probe is able to refuse something.
    """
    lines = _preamble(corpus, target)
    lines += _summary(results)
    lines += _by_kind(results)
    lines += _by_family(results)
    lines += _by_split(results)
    lines += _verdicts(results, target)
    lines += [
        "## The induced vocabulary",
        "",
        f"{corpus['vocabulary']} phrases, counted from the training documents only, where a",
        "phrase enters once it has been written twice. That set is what `tagger-ceiling` is",
        "allowed to spell; anything outside it is left as the author wrote it.",
        "",
    ]
    return "\n".join(lines)
