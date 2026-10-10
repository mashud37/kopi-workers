"""Print the presenter's effective configuration: backend, model, key source, folders and defaults, never the key itself."""

import os

from cli import ui
from slides import config as settings


def show() -> None:
    ui.step("Configuration")
    config = settings.load_config()
    key = config.get("api", {}).get("anthropic_key", "")
    if os.getenv("ANTHROPIC_API_KEY"):
        key_source = "ANTHROPIC_API_KEY"
    elif key and key != settings.KEY_PLACEHOLDER:
        key_source = "config.local.yaml"
    else:
        key_source = "not set"
    llm = config.get("llm", {})
    defaults = config.get("defaults", {})
    ui.table(
        [
            {"setting": "backend", "value": llm.get("backend", "anthropic")},
            {"setting": "claude model", "value": llm.get("model", "")},
            {"setting": "server address", "value": llm.get("base_url", "")},
            {"setting": "server model", "value": llm.get("server_model", "")},
            {"setting": "max tokens", "value": llm.get("max_tokens", "")},
            {"setting": "anthropic key", "value": key_source},
            {"setting": "icons", "value": config.get("render", {}).get("icons", "")},
            {"setting": "author", "value": defaults.get("author", "")},
            {"setting": "venue", "value": defaults.get("venue", "")},
            {"setting": "input", "value": settings.INPUT_DIR},
            {"setting": "output", "value": settings.OUTPUT_DIR},
            {"setting": "local config", "value": settings.CONFIG_LOCAL_PATH},
        ],
        ["setting", "value"],
    )
