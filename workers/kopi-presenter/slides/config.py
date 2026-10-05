"""Load user configuration from config.yaml overlaid with config.local.yaml, and name the folders the app writes to."""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = os.environ.get("KOPI_DATA")
DATA_ROOT = Path(DATA) / "kopi-presenter" if DATA else ROOT
INPUT_DIR = DATA_ROOT / "input"
OUTPUT_DIR = DATA_ROOT / "output"
CONFIG_PATH = ROOT / "config.yaml"
CONFIG_LOCAL_PATH = DATA_ROOT / "config.local.yaml"
KEY_PLACEHOLDER = "YOUR_ANTHROPIC_API_KEY_HERE"

# Published Anthropic list prices, USD per 1M tokens (input, output), cached 2026-10.
MODEL_PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"config.yaml not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if CONFIG_LOCAL_PATH.exists():
        with open(CONFIG_LOCAL_PATH, encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)

    env_key = os.getenv("ANTHROPIC_API_KEY")
    if env_key:
        config.setdefault("api", {})["anthropic_key"] = env_key

    env_model = os.getenv("KOPI_PRESENTER_MODEL")
    if env_model:
        config.setdefault("llm", {})["model"] = env_model

    return config


def resolve_input(name: str) -> Path:
    """The input file a name points at: the path itself when it exists, otherwise that name inside input/."""
    path = Path(name)
    if path.exists():
        return path
    in_input = INPUT_DIR / name
    if in_input.exists():
        return in_input
    raise SystemExit(f"'{name}' not found, here or in {INPUT_DIR}.")


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged
