"""Interactive menu — mirrors the subcommands one-to-one (cli.md §2)."""
from cli import config, install, update, settings, analyze, proof, edit, cloud, deploy, ui


def _pick_docx():
    """Return a .docx path string chosen from input/, or None to cancel."""
    docs = sorted(config.INPUT_DIR.glob("*.docx"))
    if docs:
        idx = ui.menu("Select a document", [d.name for d in docs])
        if idx is None:
            return None
        return str(docs[idx])
    ui.warn(f"no .docx files in {config.INPUT_DIR} — drop one in, or type a path")
    return ui.ask("Path to a .docx") or None


def _analyze_flow():
    f = _pick_docx()
    if not f:
        return
    try:
        analyze.run(f)
    except SystemExit as e:
        ui.warn(str(e))


def _proof_flow():
    f = _pick_docx()
    if not f:
        return
    try:
        proof.run(f)
    except SystemExit as e:
        ui.warn(str(e))


def _edit_flow():
    f = _pick_docx()
    if not f:
        return
    r = ui.ask("Words to remove (optional, blank = plain-language pass)")
    reduction = int(r) if r and r.isdigit() else None
    try:
        edit.run(f, reduction)
    except SystemExit as e:
        ui.warn(str(e))


def _cloud_test_flow():
    src = ui.ask("Source text", config.newest_output())
    if not src:
        ui.warn("no source file; run `edit` first or pass a path")
        return
    n = ui.ask("Paragraphs to send (integer or 'all')", "3")
    try:
        cloud.smoke(src, n)
    except SystemExit as e:
        ui.warn(str(e))


def main():
    ui.header("kopi-editor")
    while True:
        choice = ui.menu(
            "Main menu",
            [
                ("Analyze", "diagnose what could be cut + per-paragraph needs (no edits)"),
                ("Proof", "conservative deterministic edit, no LLM -> output/"),
                ("Full edit", "plain-language edit via the LLM backend -> output/"),
                ("Settings", "LLM backend / model / language"),
                ("Show config", "the effective configuration"),
                ("Deploy service", "build + deploy the GPU LLM service to Cloud Run"),
                ("Cloud smoke test", "send paragraphs straight to the GPU service"),
                ("Update", "upgrade dependencies + spaCy model"),
                ("Install / setup", "env.yaml, folders, dependency check"),
            ],
        )
        if choice is None:
            return
        if choice == 0:
            _analyze_flow()
        elif choice == 1:
            _proof_flow()
        elif choice == 2:
            _edit_flow()
        elif choice == 3:
            settings.run()
        elif choice == 4:
            config.show()
        elif choice == 5:
            deploy.run()
        elif choice == 6:
            _cloud_test_flow()
        elif choice == 7:
            update.run()
        elif choice == 8:
            install.run()
