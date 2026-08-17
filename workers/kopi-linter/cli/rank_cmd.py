"""`rank` command: which scoring function orders drop candidates like the gold editor."""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


def _write(rows: list, first: dict, reference: float, limit: int | None,
           extra: list) -> Path:
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
        "| Scorer | precision@k | lift over random | MAP |",
        "|---|---:|---:|---:|",
    ]
    for name, result in sorted(rows, key=lambda r: -r[1]["p_at_k"]):
        lift = result["p_at_k"] / reference if reference else 0.0
        mark = "**" if lift >= 1.5 else ""
        lines.append(f"| {mark}{name}{mark} | {result['p_at_k']:.3f} | {lift:.2f}x | "
                     f"{result['map']:.3f} |")
    lines += extra
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _allocation(groups: list) -> list:
    from experiments import allocation

    outcomes = allocation.evaluate(groups)
    for o in outcomes[:4]:
        ui.info(f"{o.name:26} P {o.precision:.3f}  R {o.recall:.3f}  F1 {o.f1:.3f}")
    lines = [
        "",
        "## Which paragraphs to cut at all",
        "",
        f"{len(groups)} paragraphs, of which "
        f"{sum(1 for g in groups if allocation.label(g))} had a phrase dropped by the gold "
        "editor. Thresholds are swept, not chosen, so the ceiling of each feature is visible "
        "even when it is disappointing.",
        "",
        "| Decision rule | precision | recall | F1 | fires on |",
        "|---|---:|---:|---:|---:|",
    ]
    for o in outcomes:
        lines.append(f"| {o.name} | {o.precision:.3f} | {o.recall:.3f} | {o.f1:.3f} | "
                     f"{o.fired}/{o.total} |")
    return lines


def run(limit: int | None = None) -> None:
    from evidence.load import load_samples
    from experiments import ranking

    ui.step("Rank")
    ui.info("plan: load corpus, load parser, collect candidates, score ordering, "
            "score allocation, write tables")

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

    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()

    bar = BatchProgress(len(samples), "collecting drop candidates")
    every = ranking.observations(samples, nlp, on_progress=bar.on_item, require_choice=False)
    bar.finish()
    # Ordering needs paragraphs where there was a choice; allocation needs all of
    # them, including the ones that dropped nothing. One parse pass, two questions.
    groups = [g for g in every
              if any(c.dropped for c in g) and any(not c.dropped for c in g)]
    if not groups:
        raise SystemExit("no paragraph both dropped and kept a phrase, nothing to rank")
    ui.ok(f"{len(every)} paragraphs with candidates, {len(groups)} with a ranking choice")

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

    ui.step("Allocation")
    extra = _allocation(every)
    print(_write(rows, first, reference, limit, extra))
