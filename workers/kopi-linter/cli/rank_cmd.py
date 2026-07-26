"""`rank` command: which scoring function orders drop candidates like the gold editor."""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


def _load_parser():
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()


def _table(rows: list, reference: float) -> list:
    lines = [
        "| Scorer | precision@k | lift over random | MAP |",
        "|---|---:|---:|---:|",
    ]
    for name, result in sorted(rows, key=lambda r: -r[1]["p_at_k"]):
        lift = result["p_at_k"] / reference if reference else 0.0
        mark = "**" if lift >= 1.5 else ""
        lines.append(f"| {mark}{name}{mark} | {result['p_at_k']:.3f} | {lift:.2f}x | "
                     f"{result['map']:.3f} |")
    return lines


def _write(rows: list, first: dict, reference: float, limit: int | None) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    stem = "ranking_adjunct" + (f"_first{limit}" if limit else "")
    path = OUTPUT / f"{stem}.md"
    lines = [
        "# Ranking comparison: which phrase goes first",
        "",
        f"{first['groups']} paragraphs that dropped at least one phrase and kept at least "
        f"one, {first['candidates']} candidate phrases.",
        "",
        "`k` is the number the gold editor actually dropped, so a scorer is judged purely on "
        "ordering and never on knowing how deep to cut.",
        "",
        f"**The bar is `random` at {reference:.3f}, not the corpus drop rate of "
        f"{first['base']:.3f}.** Shuffling scores above the corpus rate because paragraphs "
        "where many phrases were dropped contribute more picks, so a blind order gets more "
        "chances in exactly the paragraphs where hits are easy. Comparing against the corpus "
        "rate would credit every scorer with about 0.6x of lift it has not earned.",
        "",
    ]
    lines += _table(rows, reference)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(limit: int | None = None) -> None:
    from evidence.load import load_samples
    from experiments import ranking

    ui.step("Rank")
    ui.info("plan: load corpus, load parser, collect candidates, score each function, write table")

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        samples = load_samples(roles={"opus"})
    finally:
        sp.done()
    samples = samples[:limit] if limit else samples
    if not samples:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    ui.ok(f"{len(samples)} gold paragraphs")

    nlp = _load_parser()
    bar = BatchProgress(len(samples), "collecting drop candidates")
    groups = ranking.observations(samples, nlp, on_progress=lambda i, n, s: bar.advance())
    bar.finish()
    if not groups:
        raise SystemExit("no paragraph both dropped and kept a phrase, nothing to rank")

    rows = []
    names = list(ranking.SCORERS)
    for i, name in enumerate(names, 1):
        ui.info(f"[{i}/{len(names)}] {name}")
        rows.append((name, ranking.score(groups, name)))

    first = rows[0][1]
    reference = dict(rows)["random"]["p_at_k"]
    ui.ok(f"{first['groups']} paragraphs, {first['candidates']} candidates, "
          f"random baseline {reference:.3f} (corpus drop rate {first['base']:.3f})")
    for name, result in sorted(rows, key=lambda r: -r[1]["p_at_k"]):
        lift = result["p_at_k"] / reference if reference else 0.0
        ui.info(f"{name:12} p@k {result['p_at_k']:.3f}  ({lift:.2f}x random)  "
                f"MAP {result['map']:.3f}")
    print(_write(rows, first, reference, limit))
