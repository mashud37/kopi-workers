"""Interactive menu shown when manage.py runs with no arguments. Loops until
the user closes it, returning here after every action finishes or fails, and
mirrors the subcommands one-to-one."""
from . import (
    eval_cmd,
    evidence_cmd,
    execute_cmd,
    experiment_cmd,
    induce_cmd,
    install,
    lint_cmd,
    probe_cmd,
    rank_cmd,
    ui,
)

_ACTIONS = [
    ("lint", "Lint a document and write the edited text", lint_cmd.run),
    ("probe", "Ask whether Opus performs a transformation, before building it", probe_cmd.run),
    ("execute", "Probe whether a local backend can perform the gold edits", execute_cmd.run),
    ("experiment", "Compare every method for one transformation family", experiment_cmd.run),
    ("rank", "Compare scoring functions for which phrase to drop first", rank_cmd.run),
    ("evaluate", "Score the linter against Opus on the gold corpus", eval_cmd.run),
    ("evidence", "Mine the gold edit corpus into a transformation report", evidence_cmd.run),
    ("induce", "Rebuild rule tables from the gold corpus", induce_cmd.run),
    ("install", "Check dependencies, models, and the corpus link", install.run),
]


def main() -> int:
    ui.header("kopi-linter")
    while True:
        choice = ui.menu("Action", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        ui.run_action(_ACTIONS[choice][2])
