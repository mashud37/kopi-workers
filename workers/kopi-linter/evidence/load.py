"""Normalise kopi-learner's mined edit corpus (`data/pairs/*.jsonl`,
`data/out/*.jsonl`) into flat `Sample` records; this is the only module that
knows those file layouts. The corpus is read-only.
"""
import json
from dataclasses import dataclass
from pathlib import Path

LEARNER = Path(__file__).resolve().parents[2] / "kopi-learner"
PAIRS = LEARNER / "data" / "pairs"
OUT = LEARNER / "data" / "out"

GOLD_ROLES = frozenset(["opus"])
BANDS = ("clarity", "light", "firm", "aggressive")
SPLITS = ("all", "train", "test")

_HELD_OUT_EVERY = 5


@dataclass(frozen=True)
class Sample:
    """One paragraph, one editor, one band.

    Attributes:
        key: ``<doc>#<paragraph index>``, stable across models and bands, so the
            same original can be joined across editors.
        role: the editor that produced ``edit`` (``opus``, ``qwen``, ``sonnet``,
            ``haiku``). ``opus`` is the gold standard this linter chases.
        band: requested intensity (``clarity`` .. ``aggressive``).
        notes: the deterministic per-paragraph directives kopi-editor's diagnosis
            attached to this paragraph, i.e. what the rule layer already detected.
    """
    key: str
    doc: str
    idx: int
    role: str
    model: str
    band: str
    original: str
    edit: str
    notes: tuple
    accepted: bool

    @property
    def cut(self) -> float:
        words = len(self.original.split())
        return (words - len(self.edit.split())) / words if words else 0.0


def _row_to_sample(row: dict) -> Sample | None:
    original = (row.get("original") or "").strip()
    edit = (row.get("edit") or "").strip()
    if not original or not edit:
        return None
    return Sample(
        key=row.get("key") or f"{row.get('doc')}#{row.get('idx')}",
        doc=row.get("doc") or "?",
        idx=int(row.get("idx") or 0),
        role=(row.get("role") or "?").lower(),
        model=row.get("model") or "?",
        band=(row.get("mode") or "?").lower(),
        original=original,
        edit=edit,
        notes=tuple(row.get("instructions") or ()),
        accepted=bool(row.get("accepted", True)),
    )


def _read_corpus() -> list[Sample]:
    """Every edit record on disk, deduplicated on (key, role, band).

    ``data/pairs`` holds the raw mined rows and ``data/out/test.jsonl`` repeats
    a subset of them in the same shape; the SFT/DPO jsonl files are that content
    already rendered into chat templates, so they are skipped to avoid counting
    an edit twice.

    The fingerprint is the paragraph, the editor and the band, and nothing else.
    Including the edit text as well let a paragraph re-edited by the same model
    at the same band enter twice, which double-weighted 33 of the gold slots and
    made the corpus read as 1,523 paragraphs when it holds 1,490.

    Returns:
        Samples in corpus order, first occurrence winning on duplicates.
    """
    seen = set()
    samples = []
    files = sorted(PAIRS.glob("*.jsonl")) + [OUT / "test.jsonl"]
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            sample = _row_to_sample(json.loads(line))
            if sample is None:
                continue
            fingerprint = (sample.key, sample.role, sample.band)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            samples.append(sample)
    return samples


def load_samples(roles=None, bands=None, split: str = "all") -> list[Sample]:
    """The corpus, filtered to the editors, bands and split a caller asked for.

    Args:
        roles: keep only these editor roles (default: all).
        bands: keep only these intensity bands (default: all).
        split: ``train``, ``test`` or ``all``. Anything fitted to the corpus is
            fitted on ``train`` and scored on ``test``, or its score is read off
            its own training data.

    Returns:
        Samples in corpus order, first occurrence winning on duplicates.

    The split holds out every fifth document by name, and it is a split by
    **document** rather than by paragraph. Paragraphs from one document share an
    author, a topic and a vocabulary, so splitting inside a document puts
    near-copies of the training data into the test set and the leak survives the
    split. Which documents are held out does not depend on the filters, so every
    caller sees the same test set.
    """
    if split not in SPLITS:
        raise SystemExit(f"unknown split '{split}', expected one of {', '.join(SPLITS)}")
    corpus = _read_corpus()
    documents = sorted({sample.doc for sample in corpus})
    held_out = set(documents[::_HELD_OUT_EVERY])
    samples = []
    for sample in corpus:
        if roles and sample.role not in roles:
            continue
        if bands and sample.band not in bands:
            continue
        if split == "train" and sample.doc in held_out:
            continue
        if split == "test" and sample.doc not in held_out:
            continue
        samples.append(sample)
    return samples


def contrastive_pairs(gold: str = "opus", foil: str = "qwen",
                      split: str = "all") -> list[tuple[Sample, Sample]]:
    """Same paragraph, same band, edited by both models.

    The contrast is the sharpest available signal for what a local linter must
    reproduce: where gold and foil agree the transformation is easy and probably
    already rule-reachable; where they diverge sits the editorial judgement that
    every deterministic attempt so far has failed to capture.
    """
    index = {}
    for sample in load_samples(split=split):
        index.setdefault((sample.key, sample.band), {})[sample.role] = sample
    pairs = []
    for models in index.values():
        if gold in models and foil in models:
            pairs.append((models[gold], models[foil]))
    return pairs


def corpus_stats(samples: list[Sample]) -> dict:
    from collections import Counter
    return {
        "samples": len(samples),
        "documents": len({s.doc for s in samples}),
        "paragraphs": len({s.key for s in samples}),
        "by_role": Counter(s.role for s in samples),
        "by_band": Counter(s.band for s in samples),
    }
