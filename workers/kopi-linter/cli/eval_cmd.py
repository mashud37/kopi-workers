"""`evaluate` command: score the linter against Opus on the gold corpus."""
from . import ui
from .progress import BatchProgress, StepSpinner


def _load(limit: int | None) -> dict:
    """The gold Opus edits to score, and the served-Qwen edits to score them against."""
    from evidence.load import load_samples

    sp = StepSpinner("loading gold corpus")
    sp.start()
    try:
        gold = load_samples(roles={"opus"})
        foils = {(sample.key, sample.band): sample for sample in load_samples(roles={"qwen"})}
    finally:
        sp.done()
    if not gold:
        raise SystemExit("no Opus edits found in the kopi-learner corpus")
    return {"samples": gold[:limit] if limit else gold, "foils": foils}


def _report_closure(scores) -> None:
    """The master number: per cent of the distance to Opus that has been closed."""
    from eval import closure as closure_mod

    linted = closure_mod.measure(scores.triples_linted)
    ui.rule()
    print("  distance to Opus closed   closure    reach  accuracy")
    for label, triples in (("do-nothing", scores.triples_baseline),
                           ("kopi-linter", scores.triples_linted),
                           ("served Qwen", scores.triples_foil)):
        if not triples:
            continue
        result = closure_mod.measure(triples)
        print(f"  {label:24s}{result.closure:8.1%} {result.reach:8.1%} "
              f"{result.accuracy:9.1%}")
    ui.info(f"{linted.gain} of {linted.gap} word-edits to Opus closed, "
            f"{linted.work} attempted")
    for name, score, expected in closure_mod.anchors(scores.triples_linted):
        ok = score < 0 if expected is None else abs(score - expected) < 1e-9
        (ui.ok if ok else ui.error)(f"scale anchor, {name}: {score:.1%}")


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

    loaded = _load(limit)
    samples, foils = loaded["samples"], loaded["foils"]
    documents = {sample.doc for sample in samples}
    ui.ok(f"{len(samples)} gold paragraphs over {len(documents)} documents")
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()

    from eval import harness
    bar = BatchProgress(len(samples), "linting + scoring")
    scores = harness.evaluate(samples, nlp, foils, on_progress=bar.on_item)
    bar.finish()

    _report_closure(scores)
    _report_headline(scores, harness)
    print(f"  paragraphs       {scores.samples}, changed {scores.changed} "
          f"({100.0 * scores.changed / scores.samples if scores.samples else 0:.1f}%)")
    print(f"  words removed    linter {scores.words_saved}, Opus {scores.words_saved_gold}")
    _report_rules(scores)

    if show and scores.examples:
        ui.rule()
        print("  edits Opus did not make")
        for rule, source, replacement, gold in scores.examples[:12]:
            print(f"  [{rule}] {source!r} -> {replacement!r}")
            print(f"      Opus: {gold}")
