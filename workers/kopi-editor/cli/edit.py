"""`edit` — full plain-language edit via the LLM backend.

Runs the deterministic diagnosis (per-paragraph instructions), then sends every
eligible paragraph to the configured LLM backend (cloud / api / local), which
edits it for plain-language accessibility. The word reduction is an optional soft
guide; the plain-language pass runs regardless.
"""
from cli import config, ui, common


def _normalize_british(state):
    """Restore British spelling in the edited text (the model sometimes slips to
    American despite the prompt). Runs on the GUARDED text, so quoted material —
    where American spelling must be preserved verbatim — is left untouched."""
    from kopi.step_plain import _apply_lookup
    from kopi.data_spelling import AMERICAN_TO_BRITISH
    changes = []
    state["text"] = _apply_lookup(state["text"], AMERICAN_TO_BRITISH, changes, "Spelling — British")
    if changes:
        state["log"].append({
            "step": "Spelling — British",
            "detail": f"{len(changes)} American spelling(s) normalised to British",
            "para": None,
        })
        state["log"].extend(changes)


def _refresh_final_check(state):
    from kopi import step_check
    from kopi.quote_guard import unguard
    state["log"] = [e for e in state["log"] if "Step 12" not in e.get("step", "")]
    step_check.run(state)
    state["final_text"] = unguard(state["text"], state["qmap"])


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


def _require_model(llm):
    """The model must be chosen explicitly (no baked default) before editing."""
    if llm == "api" and not config.anthropic_model():
        raise SystemExit("no Anthropic model set — choose one with `python manage.py settings`.")
    if llm in ("cloud", "local") and not config.model():
        raise SystemExit("no model set — choose one with `python manage.py settings`.")


def _summary(state, original):
    final = state["counts"].get("final", original)
    final_int = final if isinstance(final, int) else original
    stats = state.get("llm_stats", {})
    acc, rej = stats.get("accepted", 0), stats.get("rejected", 0)
    delta = final_int - original
    ui.ok(f"edited {acc} paragraph(s), {rej} kept unchanged; "
          f"{original} -> {final_int} words ({delta:+d})")


def _model_used(llm):
    if llm == "api":
        return config.anthropic_model()
    if llm in ("cloud", "local"):
        return config.model()
    return None


def run(file, reduction=None, lang=None, llm=None, verbose=False):
    from datetime import datetime
    from kopi.pipeline import prepare
    from kopi.output import write_outputs
    from kopi.progress import StepSpinner

    lang = lang or config.lang()
    llm = llm or config.llm_backend()
    _require_model(llm)

    path = common.resolve_docx(file)
    ui.step(f"Editing {path.name}")

    sp = StepSpinner("loading document")
    sp.start()
    try:
        path, text, original = common.load_text(file)
    finally:
        sp.done()

    # Reduction is an optional soft guide; the plain-language pass runs regardless.
    target = original - reduction if reduction else original
    if reduction:
        ui.info(f"original {original} words | guide -{reduction} -> ~{target}")
    else:
        ui.info(f"original {original} words | plain-language pass (no reduction target)")

    ui.info("  · 1/3  Diagnose document")
    ui.info("  · 2/3  LLM plain-language edit")
    ui.info("  · 3/3  Write outputs")

    state = prepare(text, target, lang, reduction=reduction or 0)
    state["run_info"] = {"backend": llm, "model": _model_used(llm)}

    from kopi import intensity
    plan = intensity.plan(reduction or 0, original)
    ui.info(f"editing intensity: {intensity.describe(plan, reduction or 0)}")

    if llm == "skip":
        ui.info("LLM editing skipped (llm=skip)")
    else:
        state = _tighten(llm, state)
        # When a reduction was requested and pass 1 fell short of it, re-edit the
        # wordiest remaining paragraphs once more to approach the target (the model
        # cannot count, so we measure the realised cut and top up rather than trust
        # a single pass). One extra pass only — bounded cost.
        if reduction:
            from kopi import step_concision
            extra = step_concision.topup_candidates(state)
            if extra:
                ui.info(f"target shortfall after first pass — re-editing {len(extra)} paragraph(s) once more")
                state = _tighten(llm, state, extra)
    _refresh_final_check(state)

    # Deterministic British-spelling safety net over the model's output.
    if lang == "british" and llm != "skip":
        from kopi.quote_guard import unguard
        _normalize_british(state)
        state["final_text"] = unguard(state["text"], state["qmap"])

    # Each run's outputs go in their own output/<document> <timestamp>/ folder, so
    # repeated runs (and multiple documents) never overwrite or interleave.
    run_dir = config.OUTPUT_DIR / f"{path.stem} {datetime.now():%Y-%m-%d %H%M%S}"

    # Before/after comparison (same measures on each version + key-term survival),
    # merged into the single edit report rather than a separate file.
    from kopi import report
    comparison = report.comparison_lines(
        state.get("original_text", text), state.get("final_text", text),
    )
    edited, report_path, diff = write_outputs(state, path, run_dir, comparison=comparison)

    _summary(state, original)
    ui.ok(f"edited text: {edited}")
    ui.ok(f"report:      {report_path}")
    if diff:
        ui.ok(f"diff:        {diff}")
