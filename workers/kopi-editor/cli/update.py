"""`update` — upgrade Python dependencies and refresh the spaCy model."""
import subprocess
import sys

from cli import config, ui


def run():
    ui.step("Update")

    req = config.ROOT / "requirements.txt"
    ui.info("upgrading dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "-r", str(req)])
    ui.ok("dependencies upgraded")

    ui.info("refreshing spaCy model en_core_web_sm...")
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    ui.ok("spaCy model up to date")

    ui.info("To rebuild the Cloud Run image with a different model, run `python manage.py deploy`.")
