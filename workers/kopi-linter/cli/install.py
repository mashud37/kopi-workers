"""Check that the parser, lexical resources, and edit-corpus link are
present, and report how to fix what is missing. Provisions nothing, since
the linter needs no secrets or network calls.
"""
from pathlib import Path

from . import ui

# Every gate in the rule layer reads `dep_`, `tag_` and `pos_`, so the parser
# model is part of the result and not part of the environment: a bump moves every
# number in the docs without touching a line of code.
_MODEL = "en_core_web_sm"
_MODEL_VERSION = "3.7.1"

_PACKAGES = [
    ("spacy", "parser"),
    ("wordfreq", "word frequency, for long-to-plain ranking"),
    ("nltk", "WordNet, for derivational morphology"),
    ("textstat", "syllable counts"),
    ("lemminflect", "inflection, for realisation after a tree edit"),
    ("sklearn", "refitting the keep-or-delete model; linting reads the saved weights"),
]


def _check_spacy_model() -> bool:
    try:
        import spacy
        found = spacy.load(_MODEL).meta["version"]
    except Exception:
        ui.warn(f"spaCy model {_MODEL} missing")
        return False
    if found != _MODEL_VERSION:
        ui.warn(f"spaCy model {_MODEL} is {found}, the pinned version is {_MODEL_VERSION}")
        return False
    ui.ok(f"spaCy model {_MODEL} {found}")
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
            train = load_samples(roles={"opus"}, split="train")
            test = load_samples(roles={"opus"}, split="test")
            ui.ok(f"edit corpus: {len(samples)} gold Opus edits over "
                  f"{len({s.doc for s in samples})} documents")
            ui.info(f"split by document: {len(train)} train over "
                    f"{len({s.doc for s in train})}, {len(test)} test over "
                    f"{len({s.doc for s in test})}")

    for folder in ("input", "output", "data"):
        Path(folder).mkdir(exist_ok=True)
    ui.ok("input/, output/, data/ present")

    if missing:
        ui.info("fix: pip install -r requirements.txt")
    if not model_ok:
        ui.info(f"fix: pip install https://github.com/explosion/spacy-models/releases/"
                f"download/{_MODEL}-{_MODEL_VERSION}/{_MODEL}-{_MODEL_VERSION}-py3-none-any.whl")
    if not wordnet_ok:
        ui.info("fix: python -c \"import nltk; nltk.download('wordnet')\"")
    if not missing and model_ok and wordnet_ok:
        ui.ok("ready, run `python manage.py evidence` to rebuild the transformation report")
