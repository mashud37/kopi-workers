"""Sample a budgeted, seeded slice of the pepa-prep corpus across authors:
a fixed set of papers, a per-paper cap, and an overall cap on a `generate`
run's Opus cost.
"""
import random
import re
from pathlib import Path

from cli import config

# Lines that are corpus boilerplate, not author prose: front-matter, references,
# figure captions. A paragraph that is mostly these is not a copy-editing target.
_BOILERPLATE = re.compile(
    r"^(ISSN|DOI|To cite|To link|Published online|View |Submit your|Full Terms|"
    r"Article views|https?://|www\.|Downloaded|Correspondence|©|Copyright)",
    re.IGNORECASE,
)
_REFERENCE_LINE = re.compile(r"^\s*\[?\d+\]?\.?\s+[A-Z][a-z]+,?\s+[A-Z]\.")  # "12. Smith, J. ..."


def _is_prose(para: str, min_words: int) -> bool:
    if len(para.split()) < min_words:
        return False
    if para.lstrip().startswith("#"):                     # markdown heading
        return False
    if _BOILERPLATE.match(para.strip()):
        return False
    if _REFERENCE_LINE.match(para):
        return False
    alpha = sum(c.isalpha() or c.isspace() for c in para)
    return alpha / max(len(para), 1) > 0.75               # drop digit/symbol-heavy blocks


def list_papers() -> list[Path]:
    text_dir = config.corpus_text_dir()
    if not text_dir.exists():
        raise SystemExit(
            f"corpus not found at {text_dir}, set corpus.text_dir in config.yaml to "
            "the pepa-prep extraction output."
        )
    return sorted(text_dir.glob("text_*.md"))


def pick_papers(n: int, seed: int) -> list[Path]:
    """A seeded set of `n` papers, drawn to spread across distinct authors first."""
    papers = list_papers()
    by_author: dict[str, list[Path]] = {}
    for p in papers:
        stem = p.stem.removeprefix("text_")
        author = stem.split("_", 1)[0].strip().lower()
        by_author.setdefault(author, []).append(p)
    rng = random.Random(seed)
    authors = list(by_author)
    rng.shuffle(authors)
    picked: list[Path] = []
    for author in authors:                                # one paper per author, round-robin
        picked.append(rng.choice(by_author[author]))
        if len(picked) >= n:
            break
    return picked


def prose_paragraphs(path: Path, min_words: int, cap: int, seed: int) -> list[str]:
    """Up to `cap` prose paragraphs from one paper, seeded by the paper name."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    paras = [p.strip() for p in text.split("\n\n") if _is_prose(p, min_words)]
    rng = random.Random(f"{seed}:{path.stem}")
    rng.shuffle(paras)
    return paras[:cap]
