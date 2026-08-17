"""Read non-secret knobs (sampling, splits, hyperparameters) from
config.yaml, and credentials/endpoints from kopi-editor's env.yaml through
the editor bridge, so nothing is duplicated.
"""
import os
from functools import lru_cache
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG = _ROOT / "config.yaml"
_LOCAL = _ROOT / "config.local.yaml"   # gitignored; CLI-written overrides (cloud-setup)


def _load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


@lru_cache(maxsize=1)
def settings() -> dict:
    """Committed config.yaml, overlaid with gitignored config.local.yaml (the file
    `cloud-setup` writes), so instance-specific knobs never touch the committed file."""
    return _merge(_load(_CONFIG), _load(_LOCAL))


def set_local(section: str, updates: dict) -> None:
    """Persist a section into config.local.yaml, preserving the rest. None drops."""
    data = _load(_LOCAL)
    sec = dict(data.get(section) or {})
    sec.update({k: v for k, v in updates.items() if v is not None})
    data[section] = sec
    _LOCAL.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    settings.cache_clear()


def _editor():
    import editor
    return editor.econfig()


def anthropic_api_key() -> str:
    return _editor().anthropic_api_key() or ""


def qwen_base_url() -> str:
    return _editor().base_url() or ""


def qwen_token() -> str:
    return _editor().job_token() or ""


def opus_model() -> str:
    """The Anthropic model to distil from: config override, else the model already
    chosen in kopi-editor's settings, else the current Opus."""
    return (os.environ.get("KOPI_OPUS_MODEL")
            or settings().get("teacher", {}).get("opus_model")
            or _editor().anthropic_model()
            or "claude-opus-4-8")


def lang() -> str:
    return settings().get("teacher", {}).get("lang") or _editor().lang() or "british"


def corpus_text_dir() -> Path:
    rel = settings().get("corpus", {}).get("text_dir", "../../pepa-worker/pepa-prep/output/text")
    return (_ROOT / rel).resolve()


def data_dir() -> Path:
    return _ROOT / "data"


def cloud() -> dict:
    """Cloud training config (backend selector + per-backend targets)."""
    return settings().get("cloud", {})


def backend() -> str:
    """Which cloud training backend a new submit uses: vertex (default) or hf."""
    return cloud().get("backend", "vertex")


def hf_cfg() -> dict:
    """Hugging Face Jobs target (flavor, namespace, timeout, image)."""
    return cloud().get("hf", {})


def gcp_project() -> str:
    """The GCP project for training: KOPI_PROJECT, else the cloud-setup choice in
    config.local.yaml, else kopi-editor's env.yaml. Each step short-circuits, so a
    project can be set (via cloud-setup) without the editor link present."""
    return os.environ.get("KOPI_PROJECT") or cloud().get("project") or (_editor().project() or "")
