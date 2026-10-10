"""Load spaCy's English model, downloading it the first time it is needed. A fresh install then needs no setup step before its first edit."""
import importlib
import sys
from functools import lru_cache

MODEL = "en_core_web_sm"


@lru_cache(maxsize=1)
def load_english():
    """The loaded English pipeline, downloaded first when it is not installed.

    Raises:
        OSError: the download failed, for example with no internet.
    """
    import spacy
    from spacy.cli import download

    if not spacy.util.is_package(MODEL):
        print(f"downloading spaCy's English model {MODEL} (once)", file=sys.stderr)
        try:
            download(MODEL)
        except SystemExit as error:
            raise OSError(f"could not download {MODEL}") from error
        importlib.invalidate_caches()
    return spacy.load(MODEL)
