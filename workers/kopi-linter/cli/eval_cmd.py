"""`evaluate` command: score the linter against Opus on the gold corpus."""
from . import ui
from .progress import BatchProgress, StepSpinner


def _load(limit: int | None):
    from evidence.load import load_samples

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        gold = load_samples(roles={"opus"})
        foils = {(s.key, s.band): s for s in load_samples(roles={"qwen"})}
    finally:
        sp.done()
    if not gold:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    return (gold[:limit] if limit else gold), foils


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


def _report_headline(scores, harness) -> None:
    linted = harness.score_of(scores.triples_linted)
    baseline = harness.score_of(scores.triples_baseline)
    foil = harness.score_of(scores.triples_foil)
    ui.rule()
    print("  corpus SARI vs Opus      total     add    keep  delete")
    for label, score in (("do-nothing", baseline), ("kopi-linter", linted),
                         ("served Qwen", foil)):
        if score["sari"]:
            print(f"  {label:24s}{score['sari']:.4f}  {score['add']:.4f}  "
                  f"{score['keep']:.4f}  {score['delete']:.4f}")
    delta = linted["sari"] - baseline["sari"]
    (ui.ok if delta > 0 else ui.warn)(
        f"linter beats the do-nothing baseline by {delta:+.4f}" if delta > 0
        else f"linter does NOT beat doing nothing ({delta:+.4f})")
    headroom = foil["sari"] - baseline["sari"]
    if headroom > 0:
        ui.info(f"that closes {delta / headroom:.1%} of the gap to the served Qwen")


def _report_activity(scores) -> None:
    print(f"  paragraphs       {scores.samples}, changed {scores.changed} "
          f"({100.0 * scores.changed / scores.samples if scores.samples else 0:.1f}%)")
    print(f"  words removed    linter {scores.words_saved}, Opus {scores.words_saved_gold}")


def _report_rules(scores) -> None:
    if scores.failures:
        for label, count in scores.failures.most_common():
            ui.error(f"rule raised on {count} paragraphs: {label}")
    if not scores.rule_fired:
        ui.warn("no rule fired on any paragraph")
        return
    ui.rule()
    print("  rule                        fired   attested by Opus")
    for rule, fired in scores.rule_fired.most_common():
        attested = scores.rule_attested[rule]
        print(f"  {rule:26s}{fired:7d}   {attested:5d}  ({100.0 * attested / fired:.1f}%)")
    if scores.rejections:
        ui.rule()
        print("  guard rejections")
        for reason, count in scores.rejections.most_common():
            print(f"  {reason[:60]:62s}{count}")


def run(limit: int | None = None, show: bool = False) -> None:
    ui.step("Evaluate")
    ui.info("plan: load gold corpus, load parser, lint each paragraph, score against Opus")

    samples, foils = _load(limit)
    ui.ok(f"{len(samples)} gold paragraphs over {len({s.doc for s in samples})} documents")
    nlp = _parser()

    from eval import harness
    bar = BatchProgress(len(samples), "linting + scoring")
    scores = harness.evaluate(samples, nlp, foils, on_progress=lambda i, n, s: bar.advance())
    bar.finish()

    _report_headline(scores, harness)
    _report_activity(scores)
    _report_rules(scores)

    if show and scores.examples:
        ui.rule()
        print("  edits Opus did not make")
        for rule, source, replacement, gold in scores.examples[:12]:
            print(f"  [{rule}] {source!r} -> {replacement!r}")
            print(f"      Opus: {gold}")
