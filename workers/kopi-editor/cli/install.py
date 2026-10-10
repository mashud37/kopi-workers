"""Set up the repo idempotently: env.yaml, folders, and a dependency check.
"""
import shutil
import subprocess
import sys

from cli import config, ui

_DEPS = [
    ("docx", "python-docx"),
    ("spacy", "spacy"),
    ("sentence_transformers", "sentence-transformers"),
    ("numpy", "numpy"),
    ("yaml", "pyyaml"),
    ("textstat", "textstat"),
]


def run():
    ui.step("Install / setup")

    if config.ENV_FILE.exists():
        ui.info("env.yaml already exists")
    else:
        legacy = config.legacy_cloud_config()
        if legacy:
            config.set_values({
                "PROJECT": legacy.get("project"),
                "REGION": legacy.get("region"),
                "SERVICE": "kopi-editor",
                "LANG": "british",
            })
            ui.ok("created env.yaml (seeded project/region from cloud.json)")
        elif config.ENV_EXAMPLE.exists():
            shutil.copy(config.ENV_EXAMPLE, config.ENV_FILE)
            ui.ok("created env.yaml from template")
        else:
            config.set_values(dict(config._DEFAULTS))
            ui.ok("created env.yaml")

    for d in (config.INPUT_DIR, config.OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch(exist_ok=True)
    ui.ok("input/ and output/ ready")

    req = config.ROOT / "requirements.txt"
    if req.exists():
        ui.info("installing dependencies from requirements.txt...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req)])
    total_deps = len(_DEPS)
    for i, (mod, pkg) in enumerate(_DEPS, 1):
        ui.info(f"[{i}/{total_deps}] checking {mod}")
        try:
            __import__(mod)
            ui.ok(f"{mod}: ok")
        except ImportError:
            ui.warn(f"{mod}: MISSING (pip install {pkg})")

    try:
        from kopi.language_model import MODEL, load_english
        ui.info(f"loading spaCy model {MODEL} (downloads once)")
        load_english()
        ui.ok(f"spaCy model {MODEL}: ok")
    except Exception as error:
        ui.warn(f"spaCy model did not load: {error}")

    try:
        from kopi.step_concision import _EMBEDDING_MODEL, _get_model
        ui.info(f"loading embedding model {_EMBEDDING_MODEL} (downloads once)")
        _get_model()
        ui.ok(f"embedding model {_EMBEDDING_MODEL}: ok")
    except Exception as error:
        ui.warn(f"embedding model did not load, edits cannot be checked: {error}")

    g = shutil.which("gcloud")
    (ui.ok if g else ui.warn)(f"gcloud: {'found' if g else 'NOT FOUND (needed for deploy)'}")

    ui.info("Next: `python manage.py deploy` to build + deploy the GPU service, then `edit <file.docx> <words>`.")
