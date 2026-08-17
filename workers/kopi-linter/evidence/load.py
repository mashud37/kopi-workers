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


def load_samples(roles=None, bands=None) -> list[Sample]:
    """Every edit record in the corpus, deduplicated on (key, role, band).

    ``data/pairs`` holds the raw mined rows and ``data/out/test.jsonl`` the
    held-out split in the same shape; the SFT/DPO jsonl files are the same
    content already rendered into chat templates, so they are skipped to avoid
    counting an edit twice.

    Args:
        roles: keep only these editor roles (default: all).
        bands: keep only these intensity bands (default: all).

    Returns:
        Samples in corpus order, first occurrence wins on duplicates.
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
            if roles and sample.role not in roles:
                continue
            if bands and sample.band not in bands:
                continue
            fingerprint = (sample.key, sample.role, sample.band, sample.edit[:80])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            samples.append(sample)
    return samples


def contrastive_pairs(gold: str = "opus", foil: str = "qwen") -> list[tuple[Sample, Sample]]:
    """Same paragraph, same band, edited by both models.

    The contrast is the sharpest available signal for what a local linter must
    reproduce: where gold and foil agree the transformation is easy and probably
    already rule-reachable; where they diverge sits the editorial judgement that
    every deterministic attempt so far has failed to capture.
    """
    index = {}
    for sample in load_samples():
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
