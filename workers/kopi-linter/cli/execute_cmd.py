"""`execute` command: can a local backend perform the transformations Opus
performs, once it is handed the site and does not have to find it?
"""
import hashlib
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")

# Named before the run, as docs/method.md requires: a backend that cannot reach
# this exact-match rate on the rewriting spans is refused, not deferred. The
# figure was first stated for exact-or-near match, which turned out degenerate
# (docs/good.md section 7), so it now applies to exact match alone.
TARGET_EXACT_MATCH = 0.40

_REPRODUCE_TASKS = 40


def _corpus(limit: int | None) -> dict:
    """The gold Opus paragraphs to mine for spans, and the held-out documents."""
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


def _run_backends(names: list, everything: list, scored: list) -> dict:
    """Prepare and score each backend in turn, cheapest first.

    Args:
        names: backend names in report order.
        everything: every oracle task, which is what a backend fits its state on.
        scored: the tasks to score, narrowed by a family filter when one was given.

    Returns:
        ``{"results": {name: score}, "vocabulary": int}``.
    """
    from execute import backends, oracle

    results, vocabulary = {}, 0
    for name in names:
        entry = backends.BACKENDS[name]
        sp = StepSpinner(f"preparing {name}")
        sp.start()
        try:
            state = entry["prepare"]({"tasks": everything})
        finally:
            sp.done()
        if state.get("available") is False:
            ui.warn(f"{name} unavailable: {state['why']}")
        if "phrases" in state:
            vocabulary = len(state["phrases"])
        bar = BatchProgress(len(scored), f"{name} over {len(scored)} spans")
        results[name] = oracle.score(scored, entry["execute"], state, on_progress=bar.on_item)
        bar.finish()
        row = oracle.summarise(results[name]["total"])
        ui.ok(f"{name:16s} span closure {row['closure']:7.1%}   exact {row['exact']:6.1%}")
    return {"results": results, "vocabulary": vocabulary}


def _write(results: dict, corpus: dict, limit: int | None) -> Path:
    from execute import report

    OUTPUT.mkdir(exist_ok=True)
    stem = f"oracle_first{limit}" if limit else "oracle"
    path = OUTPUT / f"execute_{stem}.md"
    path.write_text(report.render(results, corpus, TARGET_EXACT_MATCH), encoding="utf-8")
    return path


def _fingerprint(sample_tasks: list, execute, state: dict, label: str) -> str:
    """SHA-256 over every replacement a backend writes, in task order."""
    digest = hashlib.sha256()
    bar = BatchProgress(len(sample_tasks), label)
    for task in sample_tasks:
        produced = execute(task, state)
        digest.update(b"refused" if produced is None else produced.encode("utf-8"))
        digest.update(b"\x00")
        bar.advance()
    bar.finish()
    return digest.hexdigest()


def _control(sample_tasks: list) -> None:
    """A check nothing can fail proves nothing, so a sampling decoder is run at it."""
    from execute import decoder

    state = decoder.prepare({})
    if not state["available"]:
        ui.warn(f"control not run: {state['why']}, so the check is unproven here")
        return
    state["options"] = dict(decoder.GREEDY)
    state["options"].update({"temperature": 1.5, "top_k": 0, "seed": -1})
    first = _fingerprint(sample_tasks, decoder.execute, state, "control pass 1")
    second = _fingerprint(sample_tasks, decoder.execute, state, "control pass 2")
    if first == second:
        ui.error("control did not differ: this check cannot fail and proves nothing")
    else:
        ui.ok("control: the sampling decoder differs across runs, as it must")


def _reproduce(everything: list, sample_tasks: list, names: list) -> None:
    """Two passes over the same spans have to produce the same bytes."""
    from execute import backends

    ui.step("Reproduce")
    ui.info(f"two passes over {len(sample_tasks)} spans per backend, then the control")
    ui.info("the thread-count axis arrives with the encoder; today this is two passes")
    for name in names:
        entry = backends.BACKENDS[name]
        state = entry["prepare"]({"tasks": everything})
        first = _fingerprint(sample_tasks, entry["execute"], state, f"{name} pass 1")
        second = _fingerprint(sample_tasks, entry["execute"], state, f"{name} pass 2")
        same = first == second
        report = f"{name:16s} {first[:16]}  {'matches' if same else 'DIFFERS'}"
        (ui.ok if same else ui.error)(report)
    _control(sample_tasks)


def _chosen(backend: str | None) -> list:
    from execute import backends

    if not backend:
        return list(backends.FREE)
    if backend not in backends.BACKENDS:
        raise SystemExit(f"unknown backend {backend!r}, one of: {', '.join(backends.NAMES)}")
    return [backend]


def run(mode: str = "oracle", backend: str | None = None,
        family: str | None = None, limit: int | None = None) -> None:
    from execute import oracle

    ui.step("Execute")
    ui.info("plan: load corpus, load parser, build oracle tasks, prepare backends, score, report")
    names = _chosen(backend)
    ui.info("backends: " + ", ".join(names))
    ui.info(f"bar named before the run: {TARGET_EXACT_MATCH:.0%} exact match on the rewriting "
            "spans, and more span closure than deleting them")

    loaded = _corpus(limit)
    samples, held_out = loaded["samples"], loaded["held_out"]
    ui.ok(f"{len(samples)} gold paragraphs, {len(held_out)} documents held out")
    nlp = _parser()

    bar = BatchProgress(len(samples), "aligning paragraphs")
    everything = oracle.tasks(samples, nlp, held_out, on_progress=bar.on_item)
    bar.finish()
    if not everything:
        raise SystemExit("no gold span edits found, so there is nothing to execute")
    ui.ok(f"{len(everything)} oracle tasks")

    scored = [task for task in everything if task["family"] == family] if family else everything
    if not scored:
        raise SystemExit(f"no oracle tasks in family {family!r}")
    if mode == "reproduce":
        return _reproduce(everything, scored[:_REPRODUCE_TASKS], names)

    ran = _run_backends(names, everything, scored)
    corpus = {
        "tasks": len(scored),
        "paragraphs": len(samples),
        "vocabulary": ran["vocabulary"],
        "filter": f", family `{family}`" if family else "",
    }
    print(_write(ran["results"], corpus, limit))
