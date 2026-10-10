"""List the kopi apps, the commands offered for each, and the files each takes in.
The console runs every command through the app's own script, never importing an app.
"""
import os
from pathlib import Path

FAMILY = Path(__file__).resolve().parent.parent

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
        ],
    },
    {
        "name": "edit",
        "kind": "heavy",
        "help": "Full plain-language edit by the model chosen in Settings",
        "fields": [
            {"name": "file", "type": "input", "help": "Document"},
            {"name": "reduction", "type": "int", "optional": True, "help": "Words to remove, as a guide"},
        ],
    },
    {
        "name": "config",
        "kind": "safe",
        "help": "Show the backend, model and language in use",
        "fields": [],
    },
]

PRESENTER_COMMANDS = [
    {
        "name": "slides",
        "kind": "heavy",
        "help": "Plan the slides with a model and build the deck",
        "fields": [
            {"name": "file", "type": "input", "help": "Manuscript or outline"},
            {"name": "--venue", "type": "text", "help": "Venue line, for example ICA 2027"},
            {"name": "--condense", "type": "bool", "help": "Send only each paragraph's first and last sentence"},
            {"name": "--emoji", "type": "bool", "help": "Use colour emoji instead of the default icons"},
            {"name": "--no-pdf", "type": "bool", "help": "Build the deck only, no PDF"},
        ],
    },
    {
        "name": "config",
        "kind": "safe",
        "help": "Show the model, key source and folders in use",
        "fields": [],
    },
]

APPS = [
    {
        "name": "kopi-editor",
        "blurb": "Copy-edit a Word document: diagnose it, proofread it, or edit it with a model",
        "script": "manage.py",
        "accepts": [".docx"],
        "keys": ["ANTHROPIC_API_KEY"],
        "commands": EDITOR_COMMANDS,
    },
    {
        "name": "kopi-presenter",
        "blurb": "Turn a manuscript or outline into a styled slide deck and a PDF",
        "script": "manage.py",
        "accepts": [".docx", ".txt", ".md"],
        "keys": ["ANTHROPIC_API_KEY"],
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


def documents_folder():
    """The one folder of documents every app reads from: under KOPI_DATA when it is set, the console's own input folder otherwise."""
    if os.environ.get("KOPI_DATA"):
        return Path(os.environ["KOPI_DATA"]) / "documents"
    return Path(__file__).resolve().parent / "input"


def data_folder(app):
    """The folder holding the app's results: under KOPI_DATA when it is set, the app's own folder otherwise."""
    if os.environ.get("KOPI_DATA"):
        return Path(os.environ["KOPI_DATA"]) / app["name"]
    return app_folder(app)
