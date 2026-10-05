"""`experiment` command: compare every method for one family, in one run."""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


def _corpus(limit: int | None, split: str):
    from evidence.load import load_samples

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        samples = load_samples(roles={"opus"}, split=split)
    finally:
        sp.done()
    samples = samples[:limit] if limit else samples
    if not samples:
        raise SystemExit("no gold samples found, check the kopi-learner checkout")
    return samples


def _score_each(methods, samples, nlp) -> list:
    from experiments import compare

    reports = []
    for i, method in enumerate(methods, 1):
        ui.info(f"[{i}/{len(methods)}] {method.name}")
        bar = BatchProgress(len(samples), method.name)
        reports.append(compare.run_corpus(method, samples, nlp, on_progress=bar.on_item))
        bar.finish()
        last = reports[-1]
        state = "clean" if last.clean else f"{len(last.case_failures)} case failures"
        ui.ok(f"{method.name}: closure {last.closure:.2%}, SARI {last.sari['sari']:.4f}, "
              f"{last.fired} fired, {state}")
    return reports


def run(family: str | None = None, limit: int | None = None, split: str = "all") -> None:
    from experiments import compare, registry, report

    ui.step("Experiment")
    ui.info("plan: pick family, load corpus, load parser, run each method, "
            "check cases, score corpus, write comparison")

    if not family:
        families = list(registry.FAMILIES)
        choice = ui.menu("Family", [(f, "") for f in families])
        family = families[choice] if choice is not None else None
    if family is None:
        return
    methods = registry.for_family(family)
    if not methods:
        raise SystemExit(f"no methods registered for family: {family}")

    samples = _corpus(limit, split)
    ui.ok(f"{len(methods)} methods, {len(samples)} gold paragraphs, {split} split")
    if split == "all":
        ui.warn("methods reading an induced table were fitted on the train documents; "
                "use --split test for a score none of them has seen")
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()

    ui.step("Surface repair cases")
    realisation = compare.check_realisation(nlp)
    for case, what in realisation:
        ui.error(f"{case.why}: {what}")
    if not realisation:
        ui.ok("all surface repair cases pass")

    reports = _score_each(methods, samples, nlp)

    ui.step("Writing comparison")
    baseline = compare.baseline_sari(samples)["sari"]
    OUTPUT.mkdir(exist_ok=True)
    stem = f"experiment_{family}_{split}" + (f"_first{limit}" if limit else "")
    path = OUTPUT / f"{stem}.md"
    corpus = {"samples": len(samples), "split": split}
    path.write_text(report.render(family, reports, baseline, corpus, realisation),
                    encoding="utf-8")
    ui.ok(f"do-nothing baseline SARI {baseline:.4f}")
    print(path)
