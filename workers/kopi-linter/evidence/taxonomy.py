"""Classify each aligned edit into a transformation family.

Every span the aligner produces is put through an ordered cascade of structural
detectors. The order matters: the most specific reading of a span wins, so
"participants were given an alias" -> "we gave each participant an alias" is
recorded as a voice change rather than three unrelated word swaps.

Two design commitments, both deliberate:

* **Structural, not lexical.** A family is decided from the dependency parse and
  from derivational morphology (WordNet), never from a hand-written list of
  words. The one exception is :mod:`evidence.editor_rules`, which exists to
  measure what the production tables already cover.
* **An honest remainder.** Anything the cascade cannot name lands in
  ``unclassified`` with its text kept. That bucket is the finding, not a
  failure: it sizes the part of the problem no rule set has touched yet.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from evidence import editor_rules

_NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ity", "ness", "ance", "ence", "ism", "al", "ure")
_PASSIVE_DEPS = frozenset(["nsubjpass", "auxpass", "csubjpass"])
_SUBORD_DEPS = frozenset(["relcl", "acl", "advcl", "ccomp", "xcomp", "csubj", "csubjpass"])
_DEGREE_DEPS = frozenset(["advmod", "npadvmod", "amod"])

@lru_cache(maxsize=1)
def _wn():
    from nltk.corpus import wordnet
    wordnet.ensure_loaded()
    return wordnet


@lru_cache(maxsize=100_000)
def _related_lemmas(word: str) -> frozenset:
    """Lemmas derivationally related to ``word`` in WordNet, cached.

    Covers the noun/verb pairs that carry nominalisation ("anonymisation" ->
    "anonymise") and the adjective/adverb pairs that carry adverbialisation
    ("generic" -> "generically"), which no suffix rule gets right on its own.
    """
    key = word.lower()
    out = set()
    try:
        for synset in _wn().synsets(key):
            for lemma in synset.lemmas():
                if lemma.name().lower().replace("_", " ") != key:
                    continue
                for related in lemma.derivationally_related_forms() + lemma.pertainyms():
                    out.add(related.name().lower().replace("_", " "))
    except Exception:
        return frozenset()
    return frozenset(out)


def _shares_stem(a: str, b: str, minimum: int = 4) -> bool:
    a, b = a.lower(), b.lower()
    n = min(len(a), len(b))
    common = 0
    while common < n and a[common] == b[common]:
        common += 1
    return common >= minimum


def _morphologically_linked(source_word: str, target_word: str) -> bool:
    if _shares_stem(source_word, target_word):
        return True
    return target_word.lower() in _related_lemmas(source_word) or \
        source_word.lower() in _related_lemmas(target_word)


@lru_cache(maxsize=100_000)
def _frequency(word: str) -> float:
    from wordfreq import zipf_frequency
    return zipf_frequency(word.lower(), "en")


@lru_cache(maxsize=100_000)
def _syllables(word: str) -> int:
    import textstat
    return textstat.syllable_count(word)


_FUNCTION_POS = frozenset(["DET", "ADP", "PART", "AUX", "PUNCT", "SPACE", "CCONJ", "PRON"])


def _content_tokens(tokens):
    return [t for t in tokens if not t.is_punct and not t.is_space]


def _is_function_only(tokens) -> bool:
    real = [t for t in tokens if not t.is_space]
    return bool(real) and all(t.pos_ in _FUNCTION_POS for t in real)


def _deictic(token) -> bool:
    return token.pos_ == "ADV" and token.tag_ == "RB" and token.dep_ in ("advmod", "npadvmod")


def _is_nominalisation(token) -> bool:
    if token.pos_ != "NOUN":
        return False
    lemma = token.lemma_.lower()
    if not lemma.endswith(_NOMINAL_SUFFIXES):
        return False
    return any(len(v) > 2 for v in _related_lemmas(lemma))


def _bead_is_passive(sentences) -> bool:
    return any(t.dep_ in _PASSIVE_DEPS for s in sentences for t in s)


@dataclass
class Finding:
    family: str
    subtype: str
    source: str
    target: str
    band: str
    key: str
    delta: int
    covered: str | None = None


@dataclass
class Tally:
    beads: Counter = field(default_factory=Counter)
    families: Counter = field(default_factory=Counter)
    subtypes: Counter = field(default_factory=Counter)
    words_moved: Counter = field(default_factory=Counter)
    covered: Counter = field(default_factory=Counter)
    by_band: dict = field(default_factory=lambda: defaultdict(Counter))
    examples: dict = field(default_factory=lambda: defaultdict(list))
    findings: list = field(default_factory=list)
    content_loss: dict = field(default_factory=lambda: defaultdict(list))


@lru_cache(maxsize=20_000)
def _is_concrete(lemma: str) -> bool:
    """Whether a noun's dominant WordNet sense is a physical entity.

    A cheap stand-in for a concreteness norm, used to spot the dead spatial and
    bodily metaphors academic prose runs on ("through the lens of", "at the
    heart of"): a concrete noun governing an abstract complement is the basic
    versus contextual meaning mismatch the Metaphor Identification Procedure
    looks for.
    """
    try:
        synsets = _wn().synsets(lemma, pos="n")
    except Exception:
        return False
    if not synsets:
        return False
    for path in synsets[0].hypernym_paths():
        for node in path:
            if node.name().startswith("physical_entity."):
                return True
    return False


def _figurative_frame(tokens) -> bool:
    nouns = [t for t in tokens if t.pos_ == "NOUN"]
    if len(nouns) < 2:
        return False
    return _is_concrete(nouns[0].lemma_.lower()) and not _is_concrete(nouns[-1].lemma_.lower())


@dataclass
class BeadContext:
    """Bead-level facts every span detector shares, computed once."""
    voice_shift: bool
    source_lemmas: frozenset
    target_lemmas: frozenset


def bead_context(bead) -> BeadContext:
    return BeadContext(
        voice_shift=_bead_is_passive(bead.source) and not _bead_is_passive(bead.target),
        source_lemmas=frozenset(
            t.lemma_.lower() for s in bead.source for t in s if not t.is_punct and not t.is_stop
        ),
        target_lemmas=frozenset(
            t.lemma_.lower() for s in bead.target for t in s if not t.is_punct and not t.is_stop
        ),
    )


def _touches_passive(tokens) -> bool:
    return any(t.dep_ in _PASSIVE_DEPS or t.tag_ == "VBN" for t in tokens)


def _classify_deletion(span, bead, ctx) -> tuple[str, str]:
    tokens = _content_tokens(span.source_tokens)
    if not tokens:
        return "punctuation", "punctuation-only"
    if ctx.voice_shift and _touches_passive(span.source_tokens):
        return "voice", "passive-auxiliary-dropped"
    if _is_function_only(span.source_tokens):
        return "realisation", "function-word-dropped"
    deps = {t.dep_ for t in tokens}
    pos = {t.pos_ for t in tokens}

    if pos <= {"DET", "PRON"}:
        return "determiner", "determiner-dropped"
    if len(tokens) == 1 and tokens[0].pos_ == "ADV" and tokens[0].dep_ in _DEGREE_DEPS:
        return ("intensifier", "degree-adverb-dropped") if tokens[0].head.pos_ in ("ADJ", "ADV") \
            else ("stance", "sentence-adverb-dropped")
    if any(t.dep_ == "relcl" for t in tokens) or tokens[0].tag_ in ("WDT", "WP"):
        return "relative-clause", "relative-clause-dropped"
    has_predicate = any(t.pos_ == "VERB" and t.dep_ in ("ROOT", "conj", "ccomp", "advcl", "xcomp")
                        for t in tokens)
    if has_predicate and len(tokens) >= 6:
        return "clause", "clause-dropped"
    if has_predicate:
        return "clause", "predicate-absorbed"
    if _figurative_frame(tokens):
        return "figurative", "metaphorical-frame-dropped"
    if tokens[0].pos_ == "ADP" or any(t.dep_ == "prep" for t in tokens):
        return "adjunct", "prepositional-phrase-dropped"
    if pos <= {"ADJ", "ADV"} or deps <= {"amod", "advmod", "npadvmod"}:
        return "modifier", "modifier-dropped"
    if len(tokens) == 1:
        return "lexical", "word-dropped"
    return "phrase", "phrase-dropped"


def _structural_replacement(span, src, tgt, ctx) -> tuple[str, str] | None:
    """The transformations named by a structural relation between the two sides."""
    for s in src:
        if _is_nominalisation(s) and any(
            t.pos_ in ("VERB", "AUX") and _morphologically_linked(s.lemma_, t.lemma_) for t in tgt
        ):
            return "nominalisation", "nominal-to-verb"

    if ctx.voice_shift and _touches_passive(span.source_tokens):
        return "voice", "passive-to-active"

    if len(src) > 1 and len(tgt) == 1 and tgt[0].pos_ in ("VERB", "AUX"):
        if any(s.pos_ == "NOUN" and _morphologically_linked(s.lemma_, tgt[0].lemma_) for s in src):
            return "support-verb", "light-verb-to-lexical-verb"
        if any(s.pos_ in ("VERB", "AUX") for s in src):
            return "support-verb", "verb-phrase-to-verb"

    if len(tgt) == 1 and tgt[0].pos_ == "ADV" and any(t.pos_ == "ADP" for t in span.source_tokens):
        if any(s.pos_ in ("NOUN", "ADJ") and _morphologically_linked(s.lemma_, tgt[0].lemma_)
               for s in src):
            return "adjunct", "prepositional-phrase-to-adverb"
        return "adjunct", "prepositional-phrase-to-deictic"

    if any(t.pos_ == "ADP" and t.lemma_.lower() == "of" for t in span.source_tokens) and \
            any(t.tag_ == "POS" for t in span.target_tokens):
        return "adjunct", "of-phrase-to-genitive"

    if _figurative_frame(src) and not _figurative_frame(tgt):
        return "figurative", "metaphor-to-direct-statement"
    return None


def _word_for_word(source, target) -> tuple[str, str]:
    if source.lemma_.lower() == target.lemma_.lower():
        return "morphology", "inflection-only"
    if source.pos_ in ("ADV", "SCONJ", "CCONJ") and target.pos_ in ("ADV", "SCONJ", "CCONJ"):
        return "connective", "connective-swapped"
    if not (source.is_alpha and target.is_alpha):
        return "phrase", "paraphrase-rewrite"
    if _frequency(target.text) > _frequency(source.text) and \
            _syllables(target.text) <= _syllables(source.text):
        return "lexical", "long-to-plain"
    if _morphologically_linked(source.lemma_, target.lemma_):
        return "lexical", "derivational-swap"
    return "lexical", "synonym-swap"


def _paraphrase_kind(src, tgt) -> tuple[str, str]:
    src_lemmas = {t.lemma_.lower() for t in src}
    tgt_lemmas = {t.lemma_.lower() for t in tgt}
    if src_lemmas and src_lemmas <= tgt_lemmas:
        return "phrase", "phrase-reordered"
    if tgt_lemmas and tgt_lemmas <= src_lemmas:
        return "phrase", "head-preserved-compression"
    if any(_morphologically_linked(s.lemma_, t.lemma_) for s in src for t in tgt):
        return "phrase", "recategorised-compression"
    if len(src) > len(tgt):
        return "phrase", "paraphrase-compression"
    return "phrase", "paraphrase-rewrite"


def _classify_replacement(span, bead, ctx) -> tuple[str, str]:
    src = _content_tokens(span.source_tokens)
    tgt = _content_tokens(span.target_tokens)
    if not src and not tgt:
        return "punctuation", "punctuation-only"
    if not tgt:
        return _classify_deletion(span, bead, ctx)
    if not src:
        return _classify_insertion(span, bead, ctx)
    if _is_function_only(span.source_tokens) and _is_function_only(span.target_tokens):
        return "realisation", "function-word-swapped"
    structural = _structural_replacement(span, src, tgt, ctx)
    if structural:
        return structural
    if len(src) == 1 and len(tgt) == 1:
        return _word_for_word(src[0], tgt[0])
    return _paraphrase_kind(src, tgt)


def _classify_insertion(span, bead, ctx) -> tuple[str, str]:
    tokens = _content_tokens(span.target_tokens)
    if not tokens:
        return "punctuation", "punctuation-only"
    if _is_function_only(span.target_tokens):
        if ctx.voice_shift and any(t.pos_ == "PRON" for t in span.target_tokens):
            return "voice", "agent-restored"
        return "realisation", "function-word-inserted"
    if ctx.voice_shift and any(t.dep_ in ("nsubj", "nsubjpass") for t in tokens):
        return "voice", "agent-restored"
    if len(tokens) == 1 and tokens[0].pos_ in ("SCONJ", "CCONJ", "ADV"):
        return "connective", "connective-inserted"
    if tgt_new := (frozenset(t.lemma_.lower() for t in tokens) - ctx.source_lemmas):
        if len(tgt_new) >= 2:
            return "phrase", "material-introduced"
    return "phrase", "material-inserted"


def classify_span(span, bead, ctx) -> tuple[str, str]:
    """Family and subtype for one span edit, from the parse and its bead context."""
    if span.op == "delete":
        return _classify_deletion(span, bead, ctx)
    if span.op == "insert":
        return _classify_insertion(span, bead, ctx)
    return _classify_replacement(span, bead, ctx)


_EXAMPLE_LIMIT = 12


def _record(result: Tally, finding: Finding) -> None:
    label = f"{finding.family}/{finding.subtype}"
    result.families[finding.family] += 1
    result.subtypes[label] += 1
    result.words_moved[finding.family] += max(0, finding.delta)
    result.by_band[finding.band][finding.family] += 1
    if finding.covered:
        result.covered[finding.covered] += 1
    if len(result.examples[label]) < _EXAMPLE_LIMIT:
        result.examples[label].append((finding.source, finding.target, finding.band))
    result.findings.append(finding)


def _content_loss(ctx: BeadContext) -> float:
    """Share of the source's content lemmas with no surviving relative in the target."""
    if not ctx.source_lemmas:
        return 0.0
    lost = [word for word in ctx.source_lemmas - ctx.target_lemmas
            if not any(_morphologically_linked(word, kept) for kept in ctx.target_lemmas)]
    return len(lost) / len(ctx.source_lemmas)


def _tally_bead(result: Tally, bead, sample) -> None:
    result.beads[bead.op] += 1
    result.by_band[sample.band][f"bead:{bead.op}"] += 1
    if bead.op == "delete":
        _record(result, Finding("sentence", "sentence-dropped", bead.source_text, "",
                                sample.band, sample.key, len(bead.source_text.split())))
        return
    ctx = bead_context(bead)
    if bead.op in ("rewrite", "split", "merge"):
        result.content_loss[sample.band].append(_content_loss(ctx))
    for span in bead.spans:
        family, subtype = classify_span(span, bead, ctx)
        covered = editor_rules.covered_by_table(span.source, span.target)
        if covered:
            family, subtype = "filler", f"table:{covered}"
        _record(result, Finding(family, subtype, span.source, span.target,
                                sample.band, sample.key, span.delta, covered))


def tally(samples, nlp, aligner, limit: int | None = None, on_progress=None) -> Tally:
    """Run the whole corpus through alignment and classification.

    Args:
        samples: :class:`evidence.load.Sample` records to analyse.
        nlp: a loaded spaCy pipeline.
        aligner: the :func:`evidence.align.align` callable.
        limit: stop after this many samples (for a quick pass).
        on_progress: called with (index, total, sample) before each sample.

    Returns:
        A :class:`Tally` holding bead-shape counts, family and subtype counts,
        the words each family moves, table-coverage counts, per-band breakdowns,
        worked examples, and every finding for later export.
    """
    work = samples[:limit] if limit else samples
    result = Tally()
    total = len(work)
    for i, sample in enumerate(work, 1):
        if on_progress:
            on_progress(i, total, sample)
        try:
            beads = aligner(sample.original, sample.edit, nlp)
        except Exception:
            continue
        for bead in beads:
            _tally_bead(result, bead, sample)
    return result
