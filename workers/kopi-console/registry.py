"""List the kopi apps, the commands offered for each, and the files each takes in.
The console runs every command through the app's own script, never importing an app.
"""
from pathlib import Path

FAMILY = Path(__file__).resolve().parent.parent

LANGS = ("british", "american")
EDITOR_BACKENDS = ("cloud", "local", "api", "skip")
LINTER_BANDS = ("clarity", "firm", "aggressive")

EDITOR_COMMANDS = [
    {
        "name": "analyze",
        "kind": "safe",
        "help": "Report what each paragraph needs, without editing",
        "fields": [
            {"name": "file", "type": "input", "help": "Document"},
        ],
    },
    {
        "name": "proof",
        "kind": "safe",
        "help": "Careful edit by rules alone, no model",
        "fields": [
            {"name": "file", "type": "input", "help": "Document"},
            {"name": "--lang", "type": "choice", "choices": LANGS, "help": "Spelling"},
        ],
    },
    {
        "name": "edit",
        "kind": "heavy",
        "help": "Full plain-language edit through the model backend",
        "fields": [
            {"name": "file", "type": "input", "help": "Document"},
            {"name": "reduction", "type": "int", "optional": True, "help": "Words to remove, as a guide"},
            {"name": "--lang", "type": "choice", "choices": LANGS, "help": "Spelling"},
            {"name": "--llm", "type": "choice", "choices": EDITOR_BACKENDS, "help": "Model backend"},
        ],
    },
    {
        "name": "config",
        "kind": "safe",
        "help": "Show the backend, model and language in use",
        "fields": [],
    },
]

LINTER_COMMANDS = [
    {
        "name": "lint",
        "kind": "safe",
        "help": "Lint a document and write the edited text",
        "fields": [
            {"name": "file", "type": "input", "help": "Document"},
            {"name": "--band", "type": "choice", "choices": LINTER_BANDS, "help": "Editing intensity"},
        ],
    },
    {
        "name": "evaluate",
        "kind": "safe",
        "help": "Score the linter against Opus's edits",
        "fields": [
            {"name": "--limit", "type": "int", "help": "Stop after this many paragraphs"},
            {"name": "--show", "type": "bool", "help": "Show the edits Opus did not make"},
        ],
    },
]

PRESENTER_COMMANDS = [
    {
        "name": "slides",
        "kind": "heavy",
        "help": "Plan the slides with a model and build the deck",
        "argv": [],
        "fields": [
            {"name": "file", "type": "input", "help": "Manuscript or outline"},
            {"name": "--venue", "type": "text", "help": "Venue line, for example ICA 2027"},
            {"name": "--condense", "type": "bool", "help": "Send only each paragraph's first and last sentence"},
            {"name": "--emoji", "type": "bool", "help": "Use colour emoji instead of the default icons"},
            {"name": "--no-pdf", "type": "bool", "help": "Build the deck only, no PDF"},
        ],
    },
]

APPS = [
    {
        "name": "kopi-editor",
        "blurb": "Copy-edit a Word document: diagnose it, proofread it, or edit it with a model",
        "script": "manage.py",
        "accepts": [".docx"],
        "commands": EDITOR_COMMANDS,
    },
    {
        "name": "kopi-linter",
        "blurb": "Edit a text file by rules alone, fully local",
        "script": "manage.py",
        "accepts": [".md", ".txt"],
        "commands": LINTER_COMMANDS,
    },
    {
        "name": "kopi-presenter",
        "blurb": "Turn a manuscript or outline into a styled slide deck and a PDF",
        "script": "run.py",
        "accepts": [".docx", ".txt", ".md"],
        "commands": PRESENTER_COMMANDS,
    },
]


def get_app(name):
    """The app with this name, or None."""
    for app in APPS:
        if app["name"] == name:
            return app
    return None


def get_command(app, command_name):
    """The app's command with this name, or None."""
    for command in app["commands"]:
        if command["name"] == command_name:
            return command
    return None


def app_folder(app):
    """The folder the app lives in, where its commands run."""
    return FAMILY / app["name"]
