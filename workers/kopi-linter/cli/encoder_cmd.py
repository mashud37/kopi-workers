"""`encoder` command: fit the keep-or-delete decision on a frozen encoder's
vectors and on the shipped one-hot features, and score both held out.
"""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


def _parser():
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()


def _encoder():
    from tagging import encoder

    sp = StepSpinner(f"loading {encoder.MODEL}")
    sp.start()
    try:
        if not encoder.available():
            raise SystemExit("encoder unavailable, run: pip install torch transformers")
        return encoder.width()
    finally:
        sp.done()


def _write(scored: dict, width: int, samples: int) -> Path:
    from tagging import encoder, fit

    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "encoder.md"
    lines = [
        "# A frozen encoder against the one-hot bag",
        "",
        f"The same keep-or-delete decision, fitted three times on {scored['trained_on']} "
        f"training words from {samples} paragraphs and scored on {scored['scored_on']} held-out "
        f"ones. `one-hot` is the feature set the linter ships: parse labels, lemma, frequency "
        f"and length, as sparse columns. `encoder` is {encoder.MODEL} run frozen over the "
        f"paragraph, giving each word the {width} numbers that describe it in its context, with "
        "no lemma column anywhere.",
        "",
        f"Guessing delete for every word scores **{scored['baseline']:.1%}** precision. Projected "
        f"closure counts one deleted word as one word operation over the {scored['gap']} "
        "operations between the held-out originals and Opus, so it is an upper bound on what "
        "wiring a feature set in would give.",
        "",
        f"Read the closure column at threshold {fit.OPERATING:.2f}, which is the dial the engine "
        "sits on, and the last column at whichever threshold each set does best at.",
        "",
        "| Features | Columns | Words fired on | Precision | Recall | Closure | Best closure |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in scored["rows"]:
        lines.append(
            f"| {row['label']} | {row['columns']} | {row['fired']} | {row['precision']:.1%} | "
            f"{row['recall']:.1%} | {row['closure']:.1%} | {row['best']:.1%} |"
        )
    lines += ["", "## Every operating point", ""]
    for name in scored["points"]:
        lines += [
            f"### {name}",
            "",
            "| Threshold | Words fired on | Precision | Recall | Projected closure |",
            "|---:|---:|---:|---:|---:|",
        ]
        for point in scored["points"][name]:
            lines.append(
                f"| {point['threshold']:.2f} | {point['fired']} | {point['precision']:.1%} | "
                f"{point['recall']:.1%} | {point['closure']:.1%} |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(limit: int | None = None) -> None:
    from evidence.load import load_samples
    from tagging import heads

    ui.step("Encoder")
    ui.info("plan: load the parser and the encoder, embed every paragraph, fit each feature "
            "set, score them on the held-out documents")
    nlp = _parser()
    width = _encoder()

    samples = load_samples(roles={"opus"})
    held_out = {sample.doc for sample in load_samples(roles={"opus"}, split="test")}
    if limit:
        samples = samples[:limit]
    bar = BatchProgress(len(samples), "embedding paragraphs")
    data = heads.dataset(samples, nlp, held_out, on_progress=bar.on_item)
    bar.finish()
    ui.ok(f"{len(data['train']['labels'])} training words, "
          f"{len(data['test']['labels'])} held-out words")

    bar = BatchProgress(len(heads.SETS), "fitting feature sets")
    scored = heads.contest(data, on_progress=bar.on_item)
    bar.finish()
    for row in scored["rows"]:
        ui.info(f"{row['label']}: {row['precision']:.1%} precision, "
                f"{row['closure']:.1%} closure, best {row['best']:.1%}")
    ui.ok(f"report written to {_write(scored, width, len(samples))}")
