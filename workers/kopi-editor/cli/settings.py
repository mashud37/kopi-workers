"""Choose the model backend, its model, and the editing defaults, storing them in env.yaml.
"""
from cli import config, ui

# Known Anthropic model IDs, cheapest first. No default is baked in: the user
# picks one here, so the cost of the choice is always deliberate.
_ANTHROPIC_MODELS = ["claude-haiku-4-5", "claude-sonnet-5-5", "claude-opus-5-5"]


def run():
    ui.step("Settings (blank = keep current)")
    updates = {
        "BACKEND":      ui.ask_choice("Backend [anthropic/openai-compatible]", list(config.BACKENDS), config.get("BACKEND")),
        "LANG":         ui.ask_choice("Language [british/american]", list(config.LANGS), config.get("LANG")),
        "LLM_BASE_URL": ui.ask("Server address, ending in /v1 (openai-compatible backend)", config.get("LLM_BASE_URL")),
        "LLM_MODEL":    ui.ask("Server model, e.g. qwen3:8b (openai-compatible backend)", config.get("LLM_MODEL")),
        "PROJECT":      ui.ask("GCP project id (manage.py deploy)", config.get("PROJECT")),
        "REGION":       ui.ask("Region (manage.py deploy)", config.get("REGION")),
        "SERVICE":      ui.ask("Cloud Run service name (manage.py deploy)", config.get("SERVICE")),
    }

    # Anthropic model: offer the known list; no default forces a deliberate pick.
    current = config.get("ANTHROPIC_MODEL")
    am = ui.ask_choice(
        f"Claude model (anthropic backend) [{'/'.join(_ANTHROPIC_MODELS)}]",
        _ANTHROPIC_MODELS, current,
    )
    if am:
        updates["ANTHROPIC_MODEL"] = am

    # The key is a secret: don't echo it as a default; blank keeps the current one.
    held = "set" if config.get("ANTHROPIC_API_KEY") else "unset"
    key = ui.ask(f"Anthropic API key (anthropic backend) [{held}]")
    if key:
        updates["ANTHROPIC_API_KEY"] = key
    held = "set" if config.get("LLM_API_KEY") else "unset"
    key = ui.ask(f"Server key, blank for none (openai-compatible backend) [{held}]")
    if key:
        updates["LLM_API_KEY"] = key

    config.set_values(updates)
    ui.ok("env.yaml updated")
    if updates.get("BACKEND") == "anthropic" and not config.get("ANTHROPIC_MODEL") and not updates.get("ANTHROPIC_MODEL"):
        ui.warn("the anthropic backend needs a model: re-run settings and choose one")
    ui.info("`manage.py deploy` prints the server address of your own Cloud Run service; its key is filled in by itself.")
