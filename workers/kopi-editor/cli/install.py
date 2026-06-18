"""`install` — idempotent first-time setup: env.yaml, folders, dependency check."""
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
                "PROJECT": legacy.get("project"), "REGION": legacy.get("region"),
                "SERVICE": "kopi-editor", "LANG": "british", "LLM": "cloud",
            })
            ui.ok("created env.yaml (seeded project/region from cloud.json)")
        elif config.ENV_EXAMPLE.exists():
            shutil.copy(config.ENV_EXAMPLE, config.ENV_FILE)
            ui.ok("created env.yaml from template")
        else:
            config.set_values(dict(config._DEFAULTS))
            ui.ok("created env.yaml")

    for d in (config.INPUT_DIR, config.OUTPUT_DIR):
        d.mkdir(exist_ok=True)
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
        import spacy
        spacy.load("en_core_web_sm")
        ui.ok("spaCy model en_core_web_sm: ok")
    except Exception:
        ui.warn("spaCy model missing (run: python -m spacy download en_core_web_sm)")

    g = shutil.which("gcloud")
    (ui.ok if g else ui.warn)(f"gcloud: {'found' if g else 'NOT FOUND (needed for deploy)'}")

    ui.info("Next: `python manage.py deploy` to build + deploy the GPU service, then `edit <file.docx> <words>`.")
