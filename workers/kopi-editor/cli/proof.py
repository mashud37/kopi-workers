"""`proof` — conservative deterministic editing, no LLM. Applies safe mechanical
fixes (fillers, padding, clichés, long→short words, grammar) and writes the
edited text + change log to output/."""
from cli import config, ui, common


def run(file, lang=None):
    from kopi.progress import StepSpinner

    lang = lang or config.lang()

    path = common.resolve_docx(file)
    ui.step(f"Proofing {path.name}")

    sp = StepSpinner("loading document")
    sp.start()
    try:
        path, text, words = common.load_text(file)
    finally:
        sp.done()
    ui.info(f"{words} words | conservative deterministic edit (no LLM)")

    from kopi.pipeline import prepare, finalize
    from kopi.proof import proof
    from kopi.output import write_outputs

    ui.info("  · 1/3  Diagnose document")
    ui.info("  · 2/3  Apply deterministic edits")
    ui.info("  · 3/3  Write outputs")

    # No word target for proofing — pass the current length so the final check
    # reports "at target" rather than a spurious shortfall.
    state = prepare(text, words, lang)
    proof(state)
    finalize(state)

    edited, changelog, diff = write_outputs(state, path, config.OUTPUT_DIR)
    final = state["counts"].get("final", words)
    ui.ok(f"removed {words - final} words; final {final}")
    ui.ok(f"edited text: {edited}")
    ui.ok(f"change log:  {changelog}")
    if diff:
        ui.ok(f"diff:        {diff}")
