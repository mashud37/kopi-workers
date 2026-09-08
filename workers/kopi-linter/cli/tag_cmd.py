"""`tag` command: read the gold corpus as an edit-tagging problem and report
the tag distribution and how much a closed vocabulary covers.
"""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


def _corpus(limit: int | None) -> dict:
    from evidence.load import load_samples

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        gold = load_samples(roles={"opus"})
        held_out = {sample.doc for sample in load_samples(roles={"opus"}, split="test")}
    finally:
        sp.done()
    if not gold:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    return {"samples": gold[:limit] if limit else gold, "held_out": held_out}


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


def _distribution(row: dict) -> list:
    """Base-tag share and the majority-class baseline, as report lines."""
    from tagging import vocabulary

    tokens = row["tokens"] or 1
    lines = ["| Tag | Tokens | Share |", "|---|---:|---:|"]
    for base in vocabulary.BASES:
        count = row["bases"][base]
        lines.append(f"| `{base}` | {count} | {count / tokens:.1%} |")
    lines.append(f"| *carries a phrase* | {row['written']} | {row['written'] / tokens:.1%} |")
    lines.append("")
    return lines


def _curve(train: dict, test: dict) -> list:
    """Held-out phrase coverage against vocabulary size, as report lines."""
    from tagging import vocabulary

    lines = [
        "| Written at least | Vocabulary | Held-out phrases covered |",
        "|---:|---:|---:|",
    ]
    for minimum in vocabulary.COVERAGE_STEPS:
        got = vocabulary.coverage(train, test, minimum)
        lines.append(f"| {got['minimum']}x | {got['size']} | {got['share']:.1%} |")
    lines.append("")
    return lines


def _write(result: dict, samples: int, scored: dict) -> Path:
    train, test = result["train"], result["test"]
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "tag_survey.md"
    lines = [
        "# The corpus as an edit-tagging problem",
        "",
        f"{samples} gold paragraphs, {train['tokens'] + test['tokens']} source words tagged, "
        f"{result['failed']} paragraphs unalignable.",
        "",
        "Every source word carries one tag: keep it or delete it, plus an optional phrase to",
        "write before it. That single scheme expresses deletion, sentence dropping, lexical",
        "swap, connective repair and sentence merge, which is why it is worth measuring before",
        "anything is fitted to it.",
        "",
        "## Tag distribution, training documents",
        "",
        "The `KEEP` share is the baseline a fitted tagger has to beat. A model that predicts it",
        "everywhere is the do-nothing linter, and scores exactly that.",
        "",
    ]
    lines += _distribution(train)
    lines += ["## Tag distribution, held-out documents", ""]
    lines += _distribution(test)
    lines += [
        "## How closed the phrase vocabulary is",
        "",
        "Fitted on the training documents, measured against the phrases the held-out documents",
        "actually need. A vocabulary that stays small while coverage stays high is the whole",
        "case for tagging over generation.",
        "",
    ]
    lines += _curve(train, test)
    lines += _report_model(scored)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _report_model(scored: dict) -> list:
    """The fitted keep-or-delete decision, at every operating point, as report lines."""
    lines = [
        "## A fitted keep-or-delete decision",
        "",
        f"Logistic regression over {scored['features']} parse and frequency features, fitted on "
        f"{scored['trained_on']} training words and scored on {scored['scored_on']} held-out ones. "
        "No embeddings, no tuning: this is the baseline the catalogue has called standard and "
        "never built, and it exists to say whether the ceiling is the features or the learning.",
        "",
        f"Guessing delete for every word scores **{scored['baseline']:.1%}** precision. That is "
        "the number an operating point has to beat.",
        "",
        f"Projected closure is the net word operations a threshold would gain, over the "
        f"{scored['gap']} operations between the held-out originals and Opus. It is an upper "
        "bound: it ignores the repair a deletion forces and the guard that can reject a "
        "paragraph, and both of those only cost.",
        "",
        "| Threshold | Words fired on | Precision | Recall | Projected closure |",
        "|---:|---:|---:|---:|---:|",
    ]
    for point in scored["points"]:
        lines.append(
            f"| {point['threshold']:.2f} | {point['fired']} | {point['precision']:.1%} | "
            f"{point['recall']:.1%} | **{point['closure']:.1%}** |"
        )
    lines.append("")
    return lines


def run(limit: int | None = None) -> None:
    from tagging import vocabulary

    ui.step("Tag")
    ui.info("plan: load corpus, load parser, tag every word, report distribution and coverage")
    loaded = _corpus(limit)
    samples, held_out = loaded["samples"], loaded["held_out"]
    ui.ok(f"{len(samples)} gold paragraphs, {len(held_out)} documents held out")
    nlp = _parser()

    bar = BatchProgress(len(samples), "tagging paragraphs")
    result = vocabulary.survey(samples, nlp, held_out, on_progress=bar.on_item)
    bar.finish()

    train, test = result["train"], result["test"]
    tokens = train["tokens"] + test["tokens"]
    if not tokens:
        raise SystemExit("nothing could be tagged, so the alignment is broken")
    ui.ok(f"{tokens} source words tagged, {result['failed']} paragraphs unalignable")
    for base in vocabulary.BASES:
        count = train["bases"][base] + test["bases"][base]
        ui.info(f"{base:8s} {count:8d}  {count / tokens:6.1%}")
    written = train["written"] + test["written"]
    ui.info(f"{'phrase':8s} {written:8d}  {written / tokens:6.1%} of words are written before")
    for minimum in (2, 5):
        got = vocabulary.coverage(train, test, minimum)
        ui.ok(f"vocabulary at {minimum}x: {got['size']} phrases, "
              f"{got['share']:.1%} of held-out writing covered")

    scored = _fit(samples, nlp, held_out)
    print(_write(result, len(samples), scored))


def _fit(samples, nlp, held_out: set) -> dict:
    """Fit the keep-or-delete decision and report each operating point."""
    from tagging import fit

    bar = BatchProgress(len(samples), "building features")
    data = fit.dataset(samples, nlp, held_out, on_progress=bar.on_item)
    bar.finish()
    sp = StepSpinner("fitting keep-or-delete")
    sp.start()
    try:
        scored = fit.fit_and_score(data)
    finally:
        sp.done()
    ui.info(f"guessing delete everywhere scores {scored['baseline']:.1%} precision")
    for point in scored["points"]:
        ui.info(f"at {point['threshold']:.2f}: precision {point['precision']:6.1%}  "
                f"recall {point['recall']:6.1%}  projected closure {point['closure']:6.1%}")
    return scored
