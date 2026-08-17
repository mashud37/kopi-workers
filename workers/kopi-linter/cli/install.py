"""Check that the parser, lexical resources, and edit-corpus link are
present, and report how to fix what is missing. Provisions nothing, since
the linter needs no secrets or network calls.
"""
from pathlib import Path

from . import ui

_PACKAGES = [
    ("spacy", "parser"),
    ("wordfreq", "word frequency, for long-to-plain ranking"),
    ("nltk", "WordNet, for derivational morphology"),
    ("textstat", "syllable counts"),
    ("lemminflect", "inflection, for realisation after a tree edit"),
]


def _check_spacy_model() -> bool:
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except Exception:
        ui.warn("spaCy model en_core_web_sm missing")
        return False
    ui.ok("spaCy model en_core_web_sm")
    return True


def _check_wordnet() -> bool:
    try:
        from nltk.corpus import wordnet
        wordnet.synsets("use")
    except Exception:
        ui.warn("NLTK WordNet corpus missing")
        return False
    ui.ok("NLTK WordNet corpus")
    return True


def run():
    ui.step("Install")
    ui.info("plan: check packages, parser model, WordNet, edit corpus, folders")

    missing = []
    for name, purpose in _PACKAGES:
        try:
            __import__(name)
            ui.ok(f"{name} ({purpose})")
        except ImportError:
            ui.warn(f"{name} missing ({purpose})")
            missing.append(name)
    model_ok = _check_spacy_model()
    wordnet_ok = _check_wordnet()

    from evidence.load import PAIRS, load_samples
    if not PAIRS.exists():
        ui.warn(f"edit corpus not found at {PAIRS}")
    else:
        samples = load_samples(roles={"opus"})
        if not samples:
            ui.warn("edit corpus present but holds no Opus edits")
        else:
            ui.ok(f"edit corpus: {len(samples)} gold Opus edits over "
                  f"{len({s.doc for s in samples})} documents")

    for folder in ("input", "output", "data"):
        Path(folder).mkdir(exist_ok=True)
    ui.ok("input/, output/, data/ present")

    if missing:
        ui.info("fix: pip install -r requirements.txt")
    if not model_ok:
        ui.info("fix: python -m spacy download en_core_web_sm")
    if not wordnet_ok:
        ui.info("fix: python -c \"import nltk; nltk.download('wordnet')\"")
    if not missing and model_ok and wordnet_ok:
        ui.ok("ready, run `python manage.py evidence` to rebuild the transformation report")
