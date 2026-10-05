"""`probe` command: does the gold editor perform this transformation at all?"""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")

# The probe decides what gets built, which is a decision fitted to the corpus,
# so it reads the same split induction does and leaves the test documents unspent.
PROBE_ON = "train"


def _write(name: str, probe, limit: int | None) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    stem = name.replace("/", "_") + (f"_first{limit}" if limit else "")
    path = OUTPUT / f"probe_{stem}.md"
    lines = [
        f"# Attestation probe: `{name}`",
        "",
        f"Measured on the **{PROBE_ON}** split, so the held-out documents stay unspent.",
        "",
        "Does the gold editor perform this transformation, before anything is built to do it?",
        "The ratio that decides is **attested against declined**. `rewritten or dropped` is the",
        "majority class everywhere, because the editor is usually doing something larger to the",
        "sentence, and counting it either way would answer a different question.",
        "",
        "| Verdict | Candidates |",
        "|---|---:|",
    ]
    for call, count in probe.verdicts.most_common():
        lines.append(f"| {call} | {count} |")
    lines += [
        "",
        f"**{probe.rate:.1%} of {probe.decidable} decidable candidates were attested.**",
        "",
    ]
    for call, examples in probe.examples.items():
        lines.append(f"- *{call}*: " + "; ".join(f"`{e}`" for e in examples))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(name: str | None = None, limit: int | None = None) -> None:
    from evidence.load import load_samples
    from experiments.registry import METHODS

    ui.step("Probe")
    ui.info("plan: pick a generator, load corpus, load parser, propose, compare against the gold")

    methods = {m.name: m for m in METHODS}
    if not name:
        chosen = ui.menu("Which candidate generator?", sorted(methods))
        if chosen is None:
            raise SystemExit("nothing to probe")
        name = chosen
    if name not in methods:
        raise SystemExit(f"unknown generator {name!r}, one of: {', '.join(sorted(methods))}")

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        samples = load_samples(roles={"opus"}, split=PROBE_ON)
    finally:
        sp.done()
    samples = samples[:limit] if limit else samples
    if not samples:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    ui.ok(f"{len(samples)} gold paragraphs, {PROBE_ON} split")

    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()
    from eval import probe as probe_mod

    bar = BatchProgress(len(samples), f"probing {name}")
    probe = probe_mod.run(samples, methods[name].propose, nlp, on_progress=bar.on_item)
    bar.finish()

    for call, count in probe.verdicts.most_common():
        ui.info(f"{call:24s} {count:6d}")
    verdict = ui.ok if probe.rate >= 0.5 else ui.warn
    verdict(f"{probe.rate:.1%} of {probe.decidable} decidable candidates attested")
    if probe.decidable and probe.rate < 0.2:
        ui.error("below 20%: building this adds reach at an accuracy that subtracts closure")
    print(_write(name, probe, limit))
