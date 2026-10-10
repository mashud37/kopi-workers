"""Run deterministic diagnosis, then send every eligible paragraph to the configured model, Claude or an
OpenAI-compatible server, for a plain-language edit. Word reduction only sets how hard it cuts.
"""
from cli import common, config, ui


def _normalize_british(state):
    """Restore British spelling in the edited text (the model sometimes slips to
    American despite the prompt). Runs on the GUARDED text, so quoted material (where American spelling must be preserved verbatim) is left untouched."""
    from kopi.data_spelling import AMERICAN_TO_BRITISH
    from kopi.step_plain import _apply_lookup
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


def _topup_shortfall(backend, state, reduction):
    """Re-edit the wordiest remaining paragraphs once if pass 1 fell short of
    the reduction target. The model cannot count, so we measure the realised
    cut and top up rather than trust a single pass; one extra pass, bounded cost."""
    from backends import llm as model_calls
    from kopi import step_concision
    extra = step_concision.topup_candidates(state)
    if extra:
        ui.info(f"target shortfall after first pass: re-editing {len(extra)} paragraph(s) once more")
        state = model_calls.tighten(state, backend, extra)
    return state


def _finalize_text(state, lang):
    """Run the deterministic grammar check, unguard quoted spans back into
    plain text, then apply the British-spelling safety net over the model's output."""
    from kopi import step_check
    from kopi.quote_guard import unguard
    log = [entry for entry in state["log"] if "Step 12" not in entry.get("step", "")]
    state = step_check.run({**state, "log": log})
    state = {**state, "final_text": unguard(state["text"], state["qmap"])}

    if lang == "british":
        state = _normalize_british(state)
        state = {**state, "final_text": unguard(state["text"], state["qmap"])}
    return state


def _report_summary(state, original, written):
    """Print the run's word-count delta and where the outputs were written."""
    final = state["counts"].get("final", original)
    final_int = final if isinstance(final, int) else original
    stats = state.get("llm_stats", {})
    acc, rej = stats.get("accepted", 0), stats.get("rejected", 0)
    delta = final_int - original
    ui.ok(f"edited {acc} paragraph(s), {rej} kept unchanged; "
          f"{original} -> {final_int} words ({delta:+d})")
    ui.ok(f"edited text:  {written['edited']}")
    ui.ok(f"side by side: {written['side_by_side']}")
    ui.ok(f"report:       {written['report']}")
    if written["diff"]:
        ui.ok(f"diff:         {written['diff']}")


def run(file, reduction=None, lang=None, backend=None, verbose=False):
    from kopi.output import write_outputs
    from kopi.pipeline import prepare

    lang = lang or config.get("LANG")
    backend = backend or config.get("BACKEND")
    if backend == "anthropic" and not config.get("ANTHROPIC_MODEL"):
        raise SystemExit("no Claude model set: choose one on the console's Models page, or with `python manage.py settings`.")
    if backend == "anthropic":
        model_used = config.get("ANTHROPIC_MODEL")
    else:
        model_used = config.llm_connection()["model"]

    doc = _load_document(file, reduction)
    path, text, original, target = doc["path"], doc["text"], doc["original"], doc["target"]

    state = prepare(text, target, lang, reduction=reduction or 0)
    state["run_info"] = {"backend": backend, "model": model_used}

    from kopi import intensity
    plan = intensity.plan(reduction or 0, original)
    ui.info(f"editing intensity: {intensity.describe(plan, reduction or 0)}")

    from backends import llm as model_calls
    state = model_calls.tighten(state, backend)
    if reduction:
        state = _topup_shortfall(backend, state, reduction)

    state = _finalize_text(state, lang)

    run_dir = common.run_folder(path, "edit")

    # Before/after comparison (same measures on each version + key-term survival),
    # merged into the single edit report rather than a separate file.
    from kopi import report
    comparison = report.comparison_lines(
        state.get("original_text", text), state.get("final_text", text),
    )
    written = write_outputs(state, path, run_dir, comparison=comparison)
    _report_summary(state, original, written)
