"""Set up the presenter idempotently: config.local.yaml, the input and output folders, and a dependency check."""

import shutil

from cli import ui
from slides import config as settings

DEPENDENCIES = [
    ("anthropic", "anthropic"),
    ("openai", "openai"),
    ("yaml", "pyyaml"),
    ("docx", "python-docx"),
    ("pptx", "python-pptx"),
]


def run() -> None:
    ui.step("Install / setup")

    if settings.CONFIG_LOCAL_PATH.exists():
        ui.info("config.local.yaml already exists")
    else:
        settings.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copy(settings.CONFIG_PATH, settings.CONFIG_LOCAL_PATH)
        ui.ok(f"created {settings.CONFIG_LOCAL_PATH}: set api.anthropic_key there, or ANTHROPIC_API_KEY")

    for folder in (settings.INPUT_DIR, settings.OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    ui.ok("input/ and output/ ready")

    total = len(DEPENDENCIES)
    for number, (module, package) in enumerate(DEPENDENCIES, 1):
        ui.info(f"[{number}/{total}] checking {module}")
        try:
            __import__(module)
            ui.ok(f"{module}: ok")
        except ImportError:
            ui.warn(f"{module}: missing (pip install {package})")
