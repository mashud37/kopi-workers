"""`induce` command: rebuild rule tables from what the gold editor actually did."""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

TABLES = {
    "support-verb": Path("rules/induced_support_verbs.py"),
    "adjunct": Path("rules/induced_adjuncts.py"),
}
FAMILIES = tuple(TABLES)
_MINIMUM_SIGHTINGS = 4


def _setup(label: str):
    from evidence.load import load_samples

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        samples = load_samples(roles={"opus"})
    finally:
        sp.done()
    if not samples:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    ui.ok(f"{len(samples)} gold paragraphs, inducing {label}")

    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()
    return {"samples": samples, "nlp": nlp}


def _support_verbs(samples, nlp, minimum: int) -> Path:
    from evidence import induce

    bar = BatchProgress(len(samples), "surveying constructions")
    result = induce.survey(samples, nlp, on_progress=bar.on_item)
    bar.finish()

    seen = sum(result["seen"].values())
    collapsed = sum(result["collapsed"].values())
    ui.ok(f"{seen} light-verb constructions, {collapsed} resolved away by the gold editor "
          f"({100.0 * collapsed / seen if seen else 0:.1f}% base rate)")
    written = induce.write_table(result, TABLES["support-verb"], minimum=minimum)
    ui.ok(f"{written} constructions seen at least {minimum} times written to the table")
    return TABLES["support-verb"]


def _adjuncts(samples, nlp, minimum: int) -> Path:
    from evidence import adjuncts

    bar = BatchProgress(len(samples), "surveying prepositional phrases")
    result = adjuncts.survey(samples, nlp, on_progress=bar.on_item)
    bar.finish()

    base = adjuncts.base_rate(result)
    seen, dropped = base["seen"], base["dropped"]
    ui.ok(f"{seen} prepositional phrases, {dropped} dropped by the gold editor "
          f"({100.0 * dropped / seen if seen else 0:.1f}% base rate)")

    bar = BatchProgress(len(samples), "surveying governor attachment")
    attach = adjuncts.attachment(samples, nlp, on_progress=bar.on_item)
    bar.finish()
    ui.ok(f"{len(attach['governors'])} governors, {len(attach['pairs'])} governor-preposition "
          f"pairs, measured on the originals alone")

    written = adjuncts.write_table(result, TABLES["adjunct"], minimum=minimum, attach=attach)
    for level, count in written.items():
        ui.info(f"{level}: {count} keys seen at least {minimum} times")
    return TABLES["adjunct"]


def run(minimum: int = _MINIMUM_SIGHTINGS, family: str = "support-verb") -> None:
    ui.step("Induce")
    ui.info("plan: load gold corpus, load parser, survey the corpus, write table")
    if family not in TABLES:
        raise SystemExit(f"unknown family '{family}', expected one of {', '.join(FAMILIES)}")

    setup = _setup(family)
    builder = _adjuncts if family == "adjunct" else _support_verbs
    print(builder(setup["samples"], setup["nlp"], minimum))
