"""Resolve effective configuration (model backend, Cloud Run target, editing defaults) from
environment variable, then env.yaml, then a built-in default. BASE_URL and
JOB_TOKEN come from `manage.py deploy`.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = os.environ.get("KOPI_DATA")
DATA_ROOT = Path(DATA) / "kopi-editor" if DATA else ROOT
INPUT_DIR = DATA_ROOT / "input"
OUTPUT_DIR = DATA_ROOT / "output"
ENV_FILE = DATA_ROOT / "env.yaml"
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
    "BACKEND": "KOPI_BACKEND",
    # Deployed instance shape, used only to estimate run cost accurately.
    "GPU_TYPE": "KOPI_GPU_TYPE",
    "CPU": "KOPI_CPU",
    "MEMORY": "KOPI_MEMORY",
    # Standard Anthropic env var name (also read by the SDK); per security.md §2.
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL": "KOPI_ANTHROPIC_MODEL",
    "LLM_BASE_URL": "KOPI_LLM_BASE_URL",
    "LLM_MODEL": "KOPI_LLM_MODEL",
    "LLM_API_KEY": "KOPI_LLM_API_KEY",
}

# ANTHROPIC_MODEL and LLM_MODEL have NO default: the user chooses explicitly in
# `settings` or on the console's Models page, and `edit` refuses to run until one is set.
# This keeps the choice (and its cost) deliberate rather than silently defaulting
# to an expensive model.
_DEFAULTS = {
    # Defaults track the primary vLLM/Qwen3 service on Blackwell; a deploy overwrites
    # them with the real values. The legacy L4 Ollama deploy sets its own (europe-west1).
    "REGION": "europe-west4",
    "SERVICE": "kopi-editor-vllm",
    "LANG": "british",
    "BACKEND": "anthropic",
    "GPU_TYPE": "nvidia-rtx-pro-6000",
    "CPU": 20,
    "MEMORY": 80,
}

# Published Anthropic list prices, USD per 1M tokens (input, output), cached 2026-10.
# Prompt-cache writes bill at 1.25x the input rate, reads at 0.10x.
ANTHROPIC_PRICES = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
CACHE_WRITE_FACTOR = 1.25
CACHE_READ_FACTOR = 0.10

# Cloud Run list prices, USD per second while the instance is active (cached 2026-06).
# Google has published no per-second SKU for the RTX PRO 6000 on Cloud Run, so its
# figure is an estimate at about four times the L4; KOPI_GPU_PER_SEC overrides it.
GPU_PRICE_PER_SECOND = {
    "nvidia-l4": 0.000233,
    "nvidia-rtx-pro-6000": 0.00093,
}
VCPU_PRICE_PER_SECOND = 0.0000180
MEMORY_PRICE_PER_SECOND = 0.0000020

LANGS = ("british", "american")
BACKENDS = ("anthropic", "openai-compatible")


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


def llm_connection():
    """The server address, key and model the openai-compatible backend uses; your own Cloud Run service's key is its job token."""
    base_url = get("LLM_BASE_URL")
    model = get("LLM_MODEL")
    if not base_url or not model:
        raise SystemExit(
            "The openai-compatible backend needs LLM_BASE_URL and LLM_MODEL in env.yaml, "
            "or the KOPI_LLM_BASE_URL and KOPI_LLM_MODEL variables."
        )
    api_key = get("LLM_API_KEY")
    if not api_key and is_own_cloud(base_url):
        api_key = get("JOB_TOKEN")
    return {"base_url": base_url, "api_key": api_key, "model": model}


def is_own_cloud(base_url):
    """Whether an address points at the service `manage.py deploy` put on Cloud Run."""
    if not base_url or not get("BASE_URL"):
        return False
    return urlparse(base_url).hostname == urlparse(get("BASE_URL")).hostname


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
        ("backend", get("BACKEND")),
        ("language", get("LANG")),
        ("project", get("PROJECT")),
        ("region", get("REGION")),
        ("service", get("SERVICE")),
        ("base url", get("BASE_URL")),
        ("job token", "(set)" if get("JOB_TOKEN") else None),
        ("deployed model", get("MODEL")),
        ("anthropic key", "(set)" if get("ANTHROPIC_API_KEY") else None),
        ("anthropic model", get("ANTHROPIC_MODEL")),
        ("server address", get("LLM_BASE_URL")),
        ("server model", get("LLM_MODEL")),
        ("server key", "(set)" if get("LLM_API_KEY") else None),
    ]
    for label, val in rows:
        (ui.ok if val else ui.warn)(f"{label}: {val or '(unset)'}")
    backend = get("BACKEND")
    if backend == "anthropic" and not get("ANTHROPIC_API_KEY"):
        ui.warn("Claude needs an Anthropic key: set it with `manage.py settings`")
    if backend == "openai-compatible" and not (get("LLM_BASE_URL") and get("LLM_MODEL")):
        ui.warn("the openai-compatible backend needs LLM_BASE_URL and LLM_MODEL: set them with `manage.py settings`")
