"""Keep the settings chosen on each app's page and hand them to its runs as environment variables.
A blank setting is not sent, so the app reads its own file.
"""
import json
import os

from settings import SETTINGS

OPTIONS_FILE_NAME = "options.json"

CLAUDE_MODELS = {
    "claude-haiku-4-5": "Claude Haiku 4.5: cheapest, $1 in, $5 out per million tokens",
    "claude-sonnet-5-5": "Claude Sonnet 5.5: $2 in, $10 out per million tokens",
    "claude-opus-5-5": "Claude Opus 5.5: strongest, $4 in, $20 out per million tokens",
}

# Each app's settings: the environment variable it arrives in, its label, and its choices,
# each value with the words shown for it.
OPTIONS = {
    "kopi-editor": [
        {"variable": "KOPI_LLM", "label": "Who edits", "choices": {
            "api": "Claude, through the Anthropic API",
            "cloud": "Your Qwen server on Google Cloud",
            "local": "Ollama on this computer",
            "skip": "No model: rules only",
        }},
        {"variable": "KOPI_ANTHROPIC_MODEL", "label": "Claude model", "choices": CLAUDE_MODELS},
        {"variable": "KOPI_LANG", "label": "Spelling", "choices": {
            "british": "British",
            "american": "American",
        }},
    ],
    "kopi-presenter": [
        {"variable": "KOPI_PRESENTER_MODEL", "label": "Claude model", "choices": CLAUDE_MODELS},
    ],
}


# ---- The store ----

def store_file():
    """Where the settings are kept: in the user profile, outside the workspace."""
    return SETTINGS["store_folder"] / OPTIONS_FILE_NAME


def load_store():
    """Every value chosen so far, as {app: {variable: value}}; a setting never chosen is absent."""
    if not store_file().exists():
        return {}
    return json.loads(store_file().read_text(encoding="utf-8"))


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ---- Saving one app's card ----

def save_choices(app_name, form):
    """Check and store one app's settings card; a blank field leaves that setting to the app's own file.

    Raises:
        ValueError: the app has no settings, or a value the setting does not accept.
    """
    if app_name not in OPTIONS:
        raise ValueError(f"{app_name} has no settings here.")
    chosen = {}
    for option in OPTIONS[app_name]:
        value = form.get(option["variable"], "").strip()
        if not value:
            continue
        if value not in option["choices"]:
            raise ValueError(f"{option['label']}: choose one of {', '.join(option['choices'])}.")
        chosen[option["variable"]] = value
    store = load_store()
    store[app_name] = chosen
    save_store(store)


# ---- What a run receives ----

def environment_for(app_name):
    """The settings a run of this app receives. A variable already set in the console's own environment wins."""
    chosen = load_store().get(app_name, {})
    environment = {}
    for variable, value in chosen.items():
        if not os.environ.get(variable):
            environment[variable] = value
    return environment


def card_view(app_name):
    """The settings card on an app's page: each setting with the value chosen; empty for an app without settings."""
    chosen = load_store().get(app_name, {})
    fields = []
    for option in OPTIONS.get(app_name, []):
        field = dict(option)
        field["value"] = chosen.get(option["variable"], "")
        fields.append(field)
    return fields
