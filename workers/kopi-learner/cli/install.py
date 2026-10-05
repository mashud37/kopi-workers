"""Check what a run depends on. No secrets file: credentials come from kopi-editor's
env.yaml (run `manage.py deploy` / `settings` in kopi-editor to set them once)."""
import shutil
from pathlib import Path

from . import config, ui


def run():
    ui.step("Install / check")

    editor_root = Path(__file__).resolve().parent.parent.parent / "kopi-editor"
    if not editor_root.exists():
        ui.error(f"kopi-editor not found at {editor_root} (required: distillation source + creds)")
        return
    ui.ok(f"kopi-editor linked at {editor_root.name}")

    try:
        url, key = config.qwen_base_url(), config.anthropic_api_key()
    except SystemExit as e:
        ui.error(str(e))
        return
    (ui.ok if url else ui.warn)(f"served Qwen: {url or 'unset, kopi-editor `deploy` writes BASE_URL/JOB_TOKEN'}")
    (ui.ok if key else ui.warn)(f"Anthropic key: {'(set in kopi-editor env.yaml)' if key else 'unset, set it in kopi-editor `settings`'}")
    ui.info(f"Opus model: {config.opus_model()}  ·  language: {config.lang()}")

    bundles = list((editor_root / "output").rglob("*_original.md")) if (editor_root / "output").exists() else []
    (ui.ok if bundles else ui.warn)(f"mineable bundles: {len(bundles)} (kopi-editor/output)")

    corpus = config.corpus_text_dir()
    if corpus.exists():
        ui.ok(f"expansion corpus: {sum(1 for _ in corpus.glob('text_*.md'))} papers (optional)")
    else:
        ui.warn(f"expansion corpus not found at {corpus} (optional: only for `generate`)")

    _cloud_status()

    ui.info("data steps: pip install -r requirements.txt (+ ../kopi-editor/requirements.txt)")
    ui.info("local GPU training: pip install -r requirements-train.txt  ·  or run `train-cloud`")
    ui.ok("done: `python manage.py` opens the menu")


def _cloud_status() -> None:
    if config.backend() == "hf":
        flavor = config.hf_cfg().get("flavor")
        logged_in = bool(shutil.which("hf"))
        (ui.ok if flavor and logged_in else ui.warn)(
            f"HF Jobs training: flavor {flavor or 'unset'} · "
            f"hf CLI {'found' if logged_in else 'missing (pip install -r requirements.txt)'}")
        return
    cloud = config.cloud()
    try:
        project = config.gcp_project()
    except SystemExit:
        project = ""
    bucket = (cloud.get("bucket") or "").strip()
    if project and bucket:
        ui.ok(f"Vertex training: project {project} · gs://{bucket} · {cloud.get('machine_type')}")
    else:
        ui.warn("Vertex training: not configured, run `python manage.py cloud-setup` "
                "before `train-cloud`")
