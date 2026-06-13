"""`edit` — full plain-language edit via the LLM backend.

Runs the deterministic diagnosis (per-paragraph instructions), then sends every
eligible paragraph to the configured LLM backend (cloud / api / local), which
edits it for plain-language accessibility. The word reduction is an optional soft
guide; the plain-language pass runs regardless.
"""
from cli import config, ui, common


def _refresh_final_check(state):
    from kopi import step_check
    from kopi.quote_guard import unguard
    state["log"] = [e for e in state["log"] if "Step 12" not in e.get("step", "")]
    step_check.run(state)
    state["final_text"] = unguard(state["text"], state["qmap"])


def _local_tighten(state):
    from kopi import step_concision
    ui.info("running local Ollama editing...")
    step_concision.run(state)
    _refresh_final_check(state)


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


def run(file, reduction=None, lang=None, llm=None, verbose=False):
    from kopi.pipeline import prepare
    from kopi.output import write_outputs

    lang = lang or config.lang()
    llm = llm or config.llm_backend()
    _require_model(llm)

    path, text, original = common.load_text(file)

    # Reduction is an optional soft guide; the plain-language pass runs regardless.
    target = original - reduction if reduction else original
    ui.step(f"Editing {path.name}")
    if reduction:
        ui.info(f"original {original} words | guide -{reduction} -> ~{target}")
    else:
        ui.info(f"original {original} words | plain-language pass (no reduction target)")

    state = prepare(text, target, lang)

    if llm == "cloud":
        from cli import cloud
        state = cloud.tighten(state)
        _refresh_final_check(state)
    elif llm == "api":
        from cli import api
        state = api.tighten(state)
        _refresh_final_check(state)
    elif llm == "local":
        _local_tighten(state)
    else:
        ui.info("LLM editing skipped (llm=skip)")
        _refresh_final_check(state)

    edited, changelog, diff = write_outputs(state, path, config.OUTPUT_DIR)

    # Before/after comparison: the same measures on each version + key-term survival.
    from kopi import report
    comparison = report.write_comparison(
        state.get("original_text", text), state.get("final_text", text), path.name, config.OUTPUT_DIR,
    )

    _summary(state, original)
    ui.ok(f"edited text: {edited}")
    ui.ok(f"change log:  {changelog}")
    if diff:
        ui.ok(f"diff:        {diff}")
    ui.ok(f"comparison:  {comparison}")
