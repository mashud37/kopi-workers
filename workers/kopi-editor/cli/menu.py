"""Interactive menu shown when manage.py runs with no arguments, mirroring the
subcommands one to one.
"""
from cli import analyze, config, deploy, edit, install, proof, settings, ui, update


def _pick_docx():
    """Return a .docx path string chosen from input/, or None to cancel."""
    docs = sorted(config.INPUT_DIR.glob("*.docx"))
    if docs:
        idx = ui.menu("Select a document", [d.name for d in docs])
        if idx is None:
            return None
        return str(docs[idx])
    ui.warn(f"no .docx files in {config.INPUT_DIR}: drop one in, or type a path")
    return ui.ask("Path to a .docx") or None


def _analyze_flow():
    f = _pick_docx()
    if f:
        analyze.run(f)


def _proof_flow():
    f = _pick_docx()
    if f:
        proof.run(f)


def _edit_flow():
    f = _pick_docx()
    if not f:
        return
    r = ui.ask("Words to remove (optional, blank = plain-language pass)")
    edit.run(f, int(r) if r and r.isdigit() else None)


def _deploy_status_flow():
    deploy.status(ui.confirm("Wait for the build to finish, then deploy?", default_yes=True))


def _cloud_test_flow():
    src = ui.ask("Source text", config.newest_output())
    if not src:
        ui.warn("no source file; run `edit` first or pass a path")
        return
    from backends import llm as model_calls
    model_calls.smoke(config.get("BACKEND"), src, ui.ask("Paragraphs to send (integer or 'all')", "3"))


_ACTIONS = [
    ("Analyze", "diagnose what could be cut + per-paragraph needs (no edits)", _analyze_flow),
    ("Proof", "conservative deterministic edit, no LLM -> output/", _proof_flow),
    ("Full edit", "plain-language edit with the configured model -> output/", _edit_flow),
    ("Settings", "model backend / model / language", settings.run),
    ("Show config", "the effective configuration", config.show),
    ("Deploy service", "fire the vLLM/Qwen3 image build async (frees the terminal)", deploy.run),
    ("Deploy status", "check the pending build; finish + deploy when it's ready",
     _deploy_status_flow),
    ("Model smoke test", "send paragraphs straight to the configured model", _cloud_test_flow),
    ("Update", "upgrade dependencies + spaCy model", update.run),
    ("Install / setup", "env.yaml, folders, dependency check", install.run),
]


def main():
    ui.header("kopi-editor")
    while True:
        choice = ui.menu("Main menu", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return
        ui.run_action(_ACTIONS[choice][2])
