"""Load user configuration from config.yaml overlaid with config.local.yaml."""

import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _ROOT / "config.yaml"
CONFIG_LOCAL_PATH = _ROOT / "config.local.yaml"


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

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged
