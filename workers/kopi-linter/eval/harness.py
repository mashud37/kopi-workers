"""Measure the linter against Opus on the paragraphs Opus actually edited.

Three numbers decide whether a rule earns its place, and all three are needed
together:

* **SARI** against Opus's edit, versus the do-nothing baseline. A linter that
  cannot beat leaving the text alone has negative value, and because SARI
  rewards correct keeping, doing nothing scores well above zero. That is the bar.
* **Agreement**, per rule. For each edit the linter applied, did Opus make a
  compatible change to the same words? This is the per-rule precision that says
  which rules to promote into the cautious bands and which to hold back.
* **Guard rejections**, per reason.

Agreement is judged on content lemmas rather than strings, since Opus reaches
the same transformation by many surface routes: an edit that removes words whose
lemmas are also absent from Opus's version counts as attested, whatever wording
Opus used around them.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from eval.sari import corpus_sari
from lint import bands
from lint.run import lint_paragraph

_STOP_TAGS = frozenset(["DET", "ADP", "PUNCT", "SPACE", "PART", "AUX", "PRON", "CCONJ", "SCONJ"])


@dataclass
class Scores:
    samples: int = 0
    changed: int = 0
    triples_linted: list = field(default_factory=list)
    triples_baseline: list = field(default_factory=list)
    triples_foil: list = field(default_factory=list)
    words_saved: int = 0
    words_saved_gold: int = 0
    rule_fired: Counter = field(default_factory=Counter)
    rule_attested: Counter = field(default_factory=Counter)
    rejections: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    by_band: dict = field(default_factory=lambda: defaultdict(Counter))
    examples: list = field(default_factory=list)


def _content_lemmas(text: str, nlp) -> set:
    return {t.lemma_.lower() for t in nlp(text) if t.pos_ not in _STOP_TAGS and not t.is_punct}


def _survives(span: str, original: str, end: int, gold: str) -> bool:
    """Whether ``span`` is still present in the gold, in the same local context.

    Anchoring on the next word matters: "that is" occurs many times in a
    paragraph, so a bare containment test answers a different question from the
    one being asked.
    """
    tail = original[end:].split()
    anchor = tail[0].strip(".,;:)]”’\"'") if tail else ""
    probe = " ".join(f"{span} {anchor}".split()).lower()
    return probe in " ".join(gold.split()).lower()


def _attested(edit, original: str, gold: str, nlp) -> bool:
    """Whether Opus made a change compatible with this edit.

    A replacement is attested when what it wrote appears in Opus's version. A
    deletion is attested when what it removed does not.

    The deletion test has two cases, and conflating them is a trap this harness
    fell into. Comparing content lemmas works only when the deleted span carries
    content lemmas. A reduction like "that are" deletes nothing but a relativiser
    and a copula, both of which are stop tags, so the removed set is empty and a
    lemma test can only ever return "attested" -- it reports 100% agreement for
    any rule that deletes function words, whatever the rule does. Those are
    checked on the surface instead.

    Surface checking is a floor, not a measure: when Opus rewrote the sentence
    the anchored span will not be found and the edit counts as attested by
    default. It cannot be tightened without a second reference.
    """
    if edit.replacement.strip():
        written = _content_lemmas(edit.replacement, nlp)
        return bool(written) and written <= _content_lemmas(gold, nlp)
    removed = _content_lemmas(edit.source(original), nlp)
    if not removed:
        return not _survives(edit.source(original).strip(), original, edit.end, gold)
    return not (removed & _content_lemmas(gold, nlp))


def triage(edit, original: str, gold: str, foil: str | None, nlp) -> str:
    """Which editors made a change compatible with this edit.

    A second reference cannot score an edit, because the only one the corpus
    supplies alongside Opus is the weaker model, and "Qwen did it too" is not
    evidence of correctness. It can still sort, and the class worth sorting out
    is the one where **both** editors declined: two independent editors passing
    over the same words is the cheapest available signal that an edit is wrong.

    Returns:
        ``"both"``, ``"gold"``, ``"foil"``, ``"neither"``, or ``"gold-only-ref"``
        when no second reference exists for this paragraph.
    """
    by_gold = _attested(edit, original, gold, nlp)
    if foil is None:
        return "gold" if by_gold else "gold-only-ref"
    by_foil = _attested(edit, original, foil, nlp)
    if by_gold and by_foil:
        return "both"
    if by_gold:
        return "gold"
    return "foil" if by_foil else "neither"


def _score_one(sample, nlp, scores: Scores) -> None:
    band = bands.band(sample.band) if sample.band in bands.BANDS else bands.band("firm")
    result = lint_paragraph(sample.original, nlp, band)

    scores.samples += 1
    scores.changed += int(result.changed)
    scores.triples_linted.append((sample.original, result.edited, sample.edit))
    scores.triples_baseline.append((sample.original, sample.original, sample.edit))
    scores.words_saved += result.words_saved
    scores.words_saved_gold += len(sample.original.split()) - len(sample.edit.split())
    scores.by_band[sample.band]["samples"] += 1
    scores.by_band[sample.band]["changed"] += int(result.changed)

    for name, error in result.failures:
        scores.failures[f"{name}: {type(error).__name__}"] += 1
    if result.reason:
        scores.rejections[result.reason.split("(")[0].strip()] += 1
    for edit in result.applied:
        scores.rule_fired[edit.rule] += 1
        if _attested(edit, sample.original, sample.edit, nlp):
            scores.rule_attested[edit.rule] += 1
        elif len(scores.examples) < 25:
            scores.examples.append((edit.rule, edit.source(sample.original),
                                    edit.replacement, sample.edit[:160]))


def evaluate(samples, nlp, foils=None, on_progress=None) -> Scores:
    """Run the linter over ``samples`` and score it against each one's gold edit.

    Args:
        samples: :class:`evidence.load.Sample` records whose ``role`` is the gold
            editor, each carrying the band the edit was requested at.
        nlp: a loaded spaCy pipeline.
        foils: optional ``{key: Sample}`` of another model's edit of the same
            paragraph, scored alongside as a comparison point.
        on_progress: called with (index, total, sample).

    Returns:
        A :class:`Scores` with SARI for the linter, the do-nothing baseline and
        the foil, plus per-rule agreement and guard rejections.
    """
    scores = Scores()
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        _score_one(sample, nlp, scores)
        foil = (foils or {}).get((sample.key, sample.band))
        if foil is not None:
            scores.triples_foil.append((sample.original, foil.edit, sample.edit))
    return scores


def score_of(triples: list) -> dict:
    """Corpus-level SARI for one system's outputs, or zeros when it has none."""
    if not triples:
        return {"sari": 0.0, "add": 0.0, "keep": 0.0, "delete": 0.0}
    return corpus_sari(triples)
