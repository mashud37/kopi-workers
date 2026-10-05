"""`sentence` command: ask whether the sentences the gold editor drops whole can
be told apart from the ones it keeps, before any rule drops one.
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


def _report_points(scored: dict) -> list:
    from document import sentences

    lines = [
        "| Threshold | Sentences dropped | Precision | Word recall | Net words | Closure |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for point in scored["points"]:
        lines.append(
            f"| {point['threshold']:.2f} | {point['fired']} | {point['precision']:.1%} | "
            f"{point['recall']:.1%} | {point['words']} | **{point['closure']:.1%}** |"
        )
    lines += [
        "",
        f"Read at threshold {sentences.OPERATING:.2f}, which is where the `sentence` family "
        "would sit in the firm band.",
        "",
    ]
    return lines


def _write(scored: dict, samples: int) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "sentence_drop.md"
    lines = [
        "# Whether a dropped sentence can be told from a kept one",
        "",
        f"Every source sentence of {samples} gold paragraphs, labelled by whether the aligner "
        f"puts it in a delete bead, which is the gold editor cutting it whole rather than "
        f"rewriting it. Fitted on {scored['trained_on']} training sentences and scored on "
        f"{scored['scored_on']} held-out ones, of which Opus dropped {scored['dropped']}.",
        "",
        f"Dropping every sentence would be right **{scored['baseline']:.1%}** of the time, so "
        "that is the number precision has to beat. Projected closure prices a drop at the words "
        f"it moves, over the {scored['gap']} word operations between the held-out originals and "
        "Opus: a right drop gains its own length and a wrong one loses it, which is why this "
        "family is the largest and the most expensive to get wrong.",
        "",
    ]
    lines += _report_points(scored)
    lines += [
        "## Read as a ranking instead",
        "",
        f"The highest score any held-out sentence reached is **{scored['highest']:.2f}**. A class "
        "this rare can be ranked well and still never cross a threshold, so this asks what "
        "dropping the top of the ranking outright would buy.",
        "",
        "| Sentences dropped | Opus dropped them too | Precision | Net words |",
        "|---:|---:|---:|---:|",
    ]
    for row in scored["top"]:
        lines.append(
            f"| {row['size']} | {row['hit']} | {row['precision']:.1%} | {row['words']} |"
        )
    lines += [
        "",
        "## Which features earned it",
        "",
        "`discourse` holds everything a sentence can only know from the paragraph around it: "
        "where it sits, how much of its vocabulary is repeated elsewhere, and whether it opens "
        "with a connective. If dropping is a discourse decision, removing that group is what "
        "should hurt.",
        "",
        "| Features | Columns | Sentences dropped | Precision | Closure | Best closure |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in scored["ablation"]:
        lines.append(
            f"| {row['label']} | {row['columns']} | {row['fired']} | {row['precision']:.1%} | "
            f"{row['closure']:.1%} | {row['best']:.1%} |"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(limit: int | None = None) -> None:
    from document import sentences
    from evidence.load import load_samples

    ui.step("Sentence")
    ui.info("plan: align every gold paragraph, label each sentence kept or dropped, fit the "
            "decision, score it on the held-out documents")
    nlp = _parser()

    samples = load_samples(roles={"opus"})
    held_out = {sample.doc for sample in load_samples(roles={"opus"}, split="test")}
    if limit:
        samples = samples[:limit]
    bar = BatchProgress(len(samples), "aligning paragraphs")
    data = sentences.dataset(samples, nlp, held_out, on_progress=bar.on_item)
    bar.finish()
    ui.ok(f"{len(data['train']['labels'])} training sentences, "
          f"{len(data['test']['labels'])} held-out sentences")

    variants = len(sentences.GROUPS) * 2 + 1
    bar = BatchProgress(variants, "fitting feature sets")
    scored = sentences.fit_and_score(data, on_progress=bar.on_item)
    bar.finish()
    best = max(point["closure"] for point in scored["points"])
    ui.info(f"Opus dropped {scored['dropped']} of {scored['scored_on']} held-out sentences, "
            f"guessing drop everywhere scores {scored['baseline']:.1%}")
    ui.ok(f"best projected closure {best:.1%}, report written to {_write(scored, len(samples))}")
