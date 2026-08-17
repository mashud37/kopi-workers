"""Choose the LLM backend, its model, and the editing defaults, storing them in env.yaml.
"""
from cli import config, ui

# Known Anthropic model IDs, cheapest first. No default is baked in: the user
# picks one here, so the cost of the choice is always deliberate.
_ANTHROPIC_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"]


def run():
    ui.step("Settings (blank = keep current)")
    updates = {
        "LLM":     ui.ask_choice("LLM backend [cloud/local/api/skip]", list(config.LLM_BACKENDS), config.get("LLM")),
        "LANG":    ui.ask_choice("Language [british/american]", list(config.LANGS), config.get("LANG")),
        "PROJECT": ui.ask("GCP project id (cloud backend)", config.get("PROJECT")),
        "REGION":  ui.ask("Region (cloud backend)", config.get("REGION")),
        "SERVICE": ui.ask("Cloud Run service name (cloud backend)", config.get("SERVICE")),
        "MODEL":   ui.ask("Self-hosted model (cloud / local Ollama, e.g. qwen2.5:7b)", config.get("MODEL")),
    }

    # Anthropic model: offer the known list; no default forces a deliberate pick.
    current = config.get("ANTHROPIC_MODEL")
    am = ui.ask_choice(
        f"Anthropic model (api backend) [{'/'.join(_ANTHROPIC_MODELS)}]",
        _ANTHROPIC_MODELS, current,
    )
    if am:
        updates["ANTHROPIC_MODEL"] = am

    # The key is a secret: don't echo it as a default; blank keeps the current one.
    held = "set" if config.get("ANTHROPIC_API_KEY") else "unset"
    key = ui.ask(f"Anthropic API key (api backend) [{held}]")
    if key:
        updates["ANTHROPIC_API_KEY"] = key

    config.set_values(updates)
    ui.ok("env.yaml updated")
    if updates.get("LLM") == "api" and not config.get("ANTHROPIC_MODEL") and not updates.get("ANTHROPIC_MODEL"):
        ui.warn("api backend needs a model: re-run settings and choose one")
    ui.info("BASE_URL and JOB_TOKEN are written by `manage.py deploy`.")
