"""Shared run-record store and code-tarball helpers used by both cloud
training backends (vertex.py, hf.py); backend-specific launch and
adapter-retrieval logic stays in each driver.
"""
import json
import tarfile
import tempfile
from pathlib import Path

from cli import config

_SKIP = {"data", "input", ".git", "__pycache__", ".ruff_cache", ".venv", ".vscode"}
_RUNS = config.data_dir() / "adapters" / "cloud_runs.json"


def _keep_in_tar(info):
    parts = Path(info.name).parts
    if any(p in _SKIP for p in parts) or info.name.endswith(".pyc"):
        return None
    return info


def code_tar() -> Path:
    """Tar the kopi-learner repo (minus data/caches) for staging to the training box."""
    root = config.data_dir().parent
    tmp = Path(tempfile.gettempdir()) / "kopi-learner-code.tar.gz"
    if tmp.exists():
        tmp.unlink()

    with tarfile.open(tmp, "w:gz") as tar:
        for item in sorted(root.iterdir()):
            if item.name in _SKIP:
                continue
            tar.add(item, arcname=item.name, filter=_keep_in_tar)
    return tmp


def save_run(run: str, rec: dict, store: Path = _RUNS) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {"runs": {}}
    data["runs"][run] = rec
    data["last"] = run
    store.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_run(run: str | None, store: Path = _RUNS) -> dict:
    """One recorded run under `name` and `record`, defaulting to the last one submitted."""
    if not store.exists():
        raise SystemExit(f"no runs recorded in {store.name}, submit one first.")
    data = json.loads(store.read_text(encoding="utf-8"))
    run = run or data.get("last")
    rec = data.get("runs", {}).get(run)
    if not rec:
        raise SystemExit(f"unknown run '{run}', see {store}.")
    return {"name": run, "record": rec}
