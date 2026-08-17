"""Run deterministic diagnosis, then send every eligible paragraph to the
configured LLM backend (cloud, api, or local) for a plain-language edit. Word
reduction only sets how hard it cuts.
"""
from cli import config, ui, common


def _normalize_british(state):
    """Restore British spelling in the edited text (the model sometimes slips to
    American despite the prompt). Runs on the GUARDED text, so quoted material (where American spelling must be preserved verbatim) is left untouched."""
    from kopi.step_plain import _apply_lookup
    from kopi.data_spelling import AMERICAN_TO_BRITISH
    changes = []
    new_text = _apply_lookup(state["text"], AMERICAN_TO_BRITISH, changes, "Spelling: British")
    state = {**state, "text": new_text}
    if changes:
        state["log"].append({
            "step": "Spelling: British",
            "detail": f"{len(changes)} American spelling(s) normalised to British",
            "para": None,
        })
        state["log"].extend(changes)
    return state


def _tighten(llm, state, candidates=None):
    """Run one editing pass on the configured backend.

    ``candidates is None`` selects every eligible paragraph (pass 1); pass an
    explicit list for a targeted top-up pass.
    """
    if llm == "cloud":
        from cli import cloud
        return cloud.tighten(state, candidates)
    if llm == "api":
        from cli import api
        return api.tighten(state, candidates)
    if llm == "local":
        from kopi import step_concision
        ui.info("running local Ollama editing...")
        return step_concision.run(state, candidates)
    return state


def _load_document(file, reduction):
    """Load the .docx and work out the word-reduction target (an optional soft
    guide; the plain-language pass runs regardless), then print the run's step
    plan so the user sees the full sequence before editing starts."""
    from kopi.progress import StepSpinner
    path = common.resolve_docx(file)
    ui.step(f"Editing {path.name}")

    sp = StepSpinner("loading document")
    sp.start()
    try:
        loaded = common.load_text(file)
        path, text, original = loaded["path"], loaded["text"], loaded["words"]
    finally:
        sp.done()

    target = original - reduction if reduction else original
    if reduction:
        ui.info(f"original {original} words | guide -{reduction} -> ~{target}")
    else:
        ui.info(f"original {original} words | plain-language pass (no reduction target)")

    ui.info("  · 1/3  Diagnose document")
    ui.info("  · 2/3  LLM plain-language edit")
    ui.info("  · 3/3  Write outputs")
    return {"path": path, "text": text, "original": original, "target": target}


def _topup_shortfall(llm, state, reduction):
    """Re-edit the wordiest remaining paragraphs once if pass 1 fell short of
    the reduction target. The model cannot count, so we measure the realised
    cut and top up rather than trust a single pass; one extra pass, bounded cost."""
    from kopi import step_concision
    extra = step_concision.topup_candidates(state)
    if extra:
        ui.info(f"target shortfall after first pass: re-editing {len(extra)} paragraph(s) once more")
        state = _tighten(llm, state, extra)
    return state


def _finalize_text(state, lang, llm):
    """Run the deterministic grammar check, unguard quoted spans back into
    plain text, then apply the British-spelling safety net over the model's output."""
    from kopi import step_check
    from kopi.quote_guard import unguard
    log = [entry for entry in state["log"] if "Step 12" not in entry.get("step", "")]
    state = step_check.run({**state, "log": log})
    state = {**state, "final_text": unguard(state["text"], state["qmap"])}

    if lang == "british" and llm != "skip":
        state = _normalize_british(state)
        state = {**state, "final_text": unguard(state["text"], state["qmap"])}
    return state


def _report_summary(state, original, edited, report_path, diff):
    """Print the run's word-count delta and where the outputs were written."""
    final = state["counts"].get("final", original)
    final_int = final if isinstance(final, int) else original
    stats = state.get("llm_stats", {})
    acc, rej = stats.get("accepted", 0), stats.get("rejected", 0)
    delta = final_int - original
    ui.ok(f"edited {acc} paragraph(s), {rej} kept unchanged; "
          f"{original} -> {final_int} words ({delta:+d})")
    ui.ok(f"edited text: {edited}")
    ui.ok(f"report:      {report_path}")
    if diff:
        ui.ok(f"diff:        {diff}")


def run(file, reduction=None, lang=None, llm=None, verbose=False):
    from datetime import datetime
    from kopi.pipeline import prepare
    from kopi.output import write_outputs

    lang = lang or config.get("LANG")
    llm = llm or config.get("LLM")
    if llm == "api" and not config.get("ANTHROPIC_MODEL"):
        raise SystemExit("no Anthropic model set: choose one with `python manage.py settings`.")
    if llm in ("cloud", "local") and not config.get("MODEL"):
        raise SystemExit("no model set: choose one with `python manage.py settings`.")

    doc = _load_document(file, reduction)
    path, text, original, target = doc["path"], doc["text"], doc["original"], doc["target"]

    state = prepare(text, target, lang, reduction=reduction or 0)
    if llm == "api":
        model_used = config.get("ANTHROPIC_MODEL")
    elif llm in ("cloud", "local"):
        model_used = config.get("MODEL")
    else:
        model_used = None
    state["run_info"] = {"backend": llm, "model": model_used}

    from kopi import intensity
    plan = intensity.plan(reduction or 0, original)
    ui.info(f"editing intensity: {intensity.describe(plan, reduction or 0)}")

    if llm == "skip":
        ui.info("LLM editing skipped (llm=skip)")
    else:
        state = _tighten(llm, state)
        if reduction:
            state = _topup_shortfall(llm, state, reduction)

    state = _finalize_text(state, lang, llm)

    # Each run's outputs go in their own output/<document> <timestamp>/ folder, so
    # repeated runs (and multiple documents) never overwrite or interleave.
    run_dir = config.OUTPUT_DIR / f"{path.stem} {datetime.now():%Y-%m-%d %H%M%S}"

    # Before/after comparison (same measures on each version + key-term survival),
    # merged into the single edit report rather than a separate file.
    from kopi import report
    comparison = report.comparison_lines(
        state.get("original_text", text), state.get("final_text", text),
    )
    written = write_outputs(state, path, run_dir, comparison=comparison)
    edited, report_path, diff = written["edited"], written["report"], written["diff"]

    _report_summary(state, original, edited, report_path, diff)
