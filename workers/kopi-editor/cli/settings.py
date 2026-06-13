"""`settings` — choose the LLM backend, its model, and editing defaults in env.yaml."""
from cli import config, ui

# Known Anthropic model IDs, cheapest first. No default is baked in — the user
# picks one here, so the cost of the choice is always deliberate.
_ANTHROPIC_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"]


def run():
    ui.step("Settings (blank = keep current)")
    updates = {
        "LLM":     ui.ask_choice("LLM backend [cloud/local/api/skip]", list(config.LLM_BACKENDS), config.llm_backend()),
        "LANG":    ui.ask_choice("Language [british/american]", list(config.LANGS), config.lang()),
        "PROJECT": ui.ask("GCP project id (cloud backend)", config.project()),
        "REGION":  ui.ask("Region (cloud backend)", config.region()),
        "SERVICE": ui.ask("Cloud Run service name (cloud backend)", config.service()),
        "MODEL":   ui.ask("Self-hosted model (cloud / local Ollama, e.g. qwen2.5:7b)", config.model()),
    }

    # Anthropic model: offer the known list; no default forces a deliberate pick.
    current = config.anthropic_model()
    am = ui.ask_choice(
        f"Anthropic model (api backend) [{'/'.join(_ANTHROPIC_MODELS)}]",
        _ANTHROPIC_MODELS, current,
    )
    if am:
        updates["ANTHROPIC_MODEL"] = am

    # The key is a secret: don't echo it as a default; blank keeps the current one.
    key = ui.ask(f"Anthropic API key (api backend) [{'set' if config.anthropic_api_key() else 'unset'}]")
    if key:
        updates["ANTHROPIC_API_KEY"] = key

    config.set_values(updates)
    ui.ok("env.yaml updated")
    if updates.get("LLM") == "api" and not config.anthropic_model() and not updates.get("ANTHROPIC_MODEL"):
        ui.warn("api backend needs a model — re-run settings and choose one")
    ui.info("BASE_URL and JOB_TOKEN are written by `manage.py deploy`.")
