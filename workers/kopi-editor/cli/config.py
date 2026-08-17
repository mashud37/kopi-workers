"""Resolve effective configuration (Cloud Run target, editing defaults) from
environment variable, then env.yaml, then a built-in default. BASE_URL and
JOB_TOKEN come from `manage.py deploy`.
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
ENV_FILE = ROOT / "env.yaml"
ENV_EXAMPLE = ROOT / "env.yaml.example"
_LEGACY_CLOUD_JSON = Path.home() / ".config" / "kopi-editor" / "cloud.json"

# env.yaml key -> overriding environment variable
_ENV_OVERRIDE = {
    "PROJECT": "KOPI_PROJECT",
    "REGION": "KOPI_REGION",
    "SERVICE": "KOPI_SERVICE",
    "BASE_URL": "KOPI_BASE_URL",
    "JOB_TOKEN": "KOPI_JOB_TOKEN",
    "MODEL": "KOPI_MODEL",
    "LANG": "KOPI_LANG",
    "LLM": "KOPI_LLM",
    # Deployed instance shape, used only to estimate run cost accurately.
    "GPU_TYPE": "KOPI_GPU_TYPE",
    "CPU": "KOPI_CPU",
    "MEMORY": "KOPI_MEMORY",
    # Standard Anthropic env var name (also read by the SDK); per security.md §2.
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL": "KOPI_ANTHROPIC_MODEL",
}

# MODEL (self-hosted/cloud) and ANTHROPIC_MODEL (api) have NO default: the user
# chooses explicitly in `settings`, and `edit` refuses to run until one is set.
# This keeps the choice (and its cost) deliberate rather than silently defaulting
# to an expensive model.
_DEFAULTS = {
    # Defaults track the primary vLLM/Qwen3 service on Blackwell; a deploy overwrites
    # them with the real values. The legacy L4 Ollama deploy sets its own (europe-west1).
    "REGION": "europe-west4",
    "SERVICE": "kopi-editor-vllm",
    "LANG": "british",
    "LLM": "cloud",
    "GPU_TYPE": "nvidia-rtx-pro-6000",
    "CPU": 20,
    "MEMORY": 80,
}

LANGS = ("british", "american")
LLM_BACKENDS = ("cloud", "local", "api", "skip")


def _file_values():
    if ENV_FILE.exists():
        return yaml.safe_load(ENV_FILE.read_text(encoding="utf-8")) or {}
    return {}


def get(key, default=None):
    env = _ENV_OVERRIDE.get(key)
    if env and os.environ.get(env):
        return os.environ[env]
    val = _file_values().get(key)
    if val not in (None, ""):
        return val
    return default if default is not None else _DEFAULTS.get(key)


def set_values(updates):
    """Persist settings into env.yaml, preserving everything else. None drops."""
    data = _file_values()
    data.update({k: v for k, v in updates.items() if v is not None})
    ENV_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def legacy_cloud_config():
    """Old ~/.config/kopi-editor/cloud.json, used to seed env.yaml on install."""
    if _LEGACY_CLOUD_JSON.exists():
        import json
        try:
            return json.loads(_LEGACY_CLOUD_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def newest_output():
    files = sorted(OUTPUT_DIR.rglob("*_edited.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def show():
    from cli import ui
    ui.header("kopi-editor: config")
    ui.info(f"env.yaml: {ENV_FILE if ENV_FILE.exists() else '(not created, run install)'}")
    rows = [
        ("llm backend", get("LLM")),
        ("language", get("LANG")),
        ("project", get("PROJECT")),
        ("region", get("REGION")),
        ("service", get("SERVICE")),
        ("base url", get("BASE_URL")),
        ("job token", "(set)" if get("JOB_TOKEN") else None),
        ("self-hosted model", get("MODEL")),
        ("anthropic key", "(set)" if get("ANTHROPIC_API_KEY") else None),
        ("anthropic model", get("ANTHROPIC_MODEL")),
    ]
    for label, val in rows:
        (ui.ok if val else ui.warn)(f"{label}: {val or '(unset)'}")
    backend = get("LLM")
    if backend == "cloud" and not get("BASE_URL"):
        ui.warn("cloud editing needs the service deployed: run `manage.py deploy`")
    if backend == "api" and not get("ANTHROPIC_API_KEY"):
        ui.warn("api editing needs an Anthropic key: set it with `manage.py settings`")
