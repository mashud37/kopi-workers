"""Turn diagnosed paragraphs into distillation units, one paragraph and one
band each, with the exact editor's notes and guard settings production
uses. `assign_bands` is shared by both corpus routes.
"""
import random

import editor
from cli import config
from corpus import sample


def assign_bands(state: dict, candidates: list[dict], seed, doc: str) -> list[dict]:
    """Assign each candidate paragraph a band from the mix, returning normalized units.

    Re-queries the editor once per band (cheap; diagnosis is already done) so each
    unit carries that band's mode, floor, and guard ceiling.
    """
    if not candidates:
        return []
    original_words = state.get("original_words") or 0
    bands = []
    for name, spec in (config.settings().get("bands") or {}).items():
        bands.append((name, float(spec.get("reduction_ratio", 0.0)), float(spec.get("weight", 1.0))))
    names = [b[0] for b in bands]
    weights = [b[2] for b in bands]
    reductions = {name: max(0, round(original_words * ratio)) for name, ratio, _ in bands}
    by_band = {name: {c["index"]: c for c in editor.candidates_at(state, reductions[name])}
               for name in names}

    rng = random.Random(f"{seed}")
    units = []
    for c in candidates:
        band = rng.choices(names, weights=weights, k=1)[0]
        bc = by_band[band].get(c["index"])
        if bc is None:
            continue
        units.append({
            "doc": doc,
            "idx": bc["index"],
            "band": band,
            "text": bc["text"],
            "instructions": bc.get("instructions") or [],
            "mode": bc["mode"],
            "floor": bc.get("floor"),
            "max_compression": bc["max_compression"],
        })
    return units


def units_for_paper(path, min_words: int, cap: int, seed: int) -> list[dict]:
    """Up to `cap` units from one corpus paper."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    state = editor.prepare_doc(text, config.lang())
    base = [c for c in editor.candidates_at(state, 0) if sample._is_prose(c["text"], min_words)]
    rng = random.Random(f"{seed}:{path.stem}")
    rng.shuffle(base)
    return assign_bands(state, base[:cap], seed=f"{seed}:{path.stem}", doc=path.stem)


def collect(papers: int, max_paragraphs: int, seed: int) -> list[dict]:
    """Walk the sampled corpus papers and gather up to `max_paragraphs` units."""
    from cli import ui

    corpus_cfg = config.settings().get("corpus", {})
    min_words = int(corpus_cfg.get("min_paragraph_words", 40))
    per_paper = int(corpus_cfg.get("max_paragraphs_per_paper", 6))

    selected = sample.pick_papers(papers, seed)
    ui.info(f"{len(selected)} papers sampled (seed {seed}); capping at {max_paragraphs} paragraphs")
    units: list[dict] = []
    for i, path in enumerate(selected, 1):
        if len(units) >= max_paragraphs:
            break
        ui.info(f"[{i}/{len(selected)}] {path.stem[:60]}")
        try:
            units.extend(units_for_paper(path, min_words, per_paper, seed))
        except Exception as e:
            ui.warn(f"skipped {path.name}: {e}")
    return units[:max_paragraphs]
