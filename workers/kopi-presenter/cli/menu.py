"""Interactive menu shown when manage.py runs with no arguments, mirroring the subcommands one to one."""

from cli import config, deck, install, ui
from slides import config as settings

INPUT_TYPES = [
    ".docx",
    ".txt",
    ".md",
]


def _pick_input():
    """A manuscript chosen from input/, a typed path, or None to cancel."""
    files = []
    if settings.INPUT_DIR.exists():
        files = sorted(path for path in settings.INPUT_DIR.iterdir() if path.suffix in INPUT_TYPES)
    if not files:
        ui.warn(f"no manuscripts in {settings.INPUT_DIR}: drop one in, or type a path")
        return ui.ask("Path to a manuscript") or None
    choice = ui.menu("Select a manuscript", [path.name for path in files])
    if choice is None:
        return None
    return str(files[choice])


def _slides_flow():
    file_name = _pick_input()
    if not file_name:
        return
    options = {
        "venue": ui.ask("Venue line (blank for the default)") or None,
        "review": ui.confirm("Review the plan before building?", default_yes=False),
    }
    deck.run(file_name, options)


_ACTIONS = [
    ("Build a deck", "plan the slides with the model, then build .pptx and PDF", _slides_flow),
    ("Show config", "the effective configuration", config.show),
    ("Install / setup", "config.local.yaml, folders, dependency check", install.run),
]


def main():
    ui.header("kopi-presenter")
    while True:
        choice = ui.menu("Main menu", [(label, description) for label, description, _ in _ACTIONS])
        if choice is None:
            return
        ui.run_action(_ACTIONS[choice][2])
