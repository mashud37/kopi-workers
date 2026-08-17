"""Classify each aligned edit span into a transformation family through an
ordered cascade of dependency and WordNet-morphology detectors, never a word
list. Unmatched spans land in `unclassified`.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from evidence import editor_rules

_NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ity", "ness", "ance", "ence", "ism", "al", "ure")
_PASSIVE_DEPS = frozenset(["nsubjpass", "auxpass", "csubjpass"])
_DEGREE_DEPS = frozenset(["advmod", "npadvmod", "amod"])
_PREDICATE_DEPS = frozenset(["ROOT", "conj", "ccomp", "advcl", "xcomp"])
_FUNCTION_POS = frozenset(["DET", "ADP", "PART", "AUX", "PUNCT", "SPACE", "CCONJ", "PRON"])
_STEM_PREFIX_MINIMUM = 4
_EXAMPLE_LIMIT = 12


def _counters_by_key():
    return defaultdict(Counter)


def _lists_by_key():
    return defaultdict(list)


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


def _shares_stem(first: str, second: str) -> bool:
    first, second = first.lower(), second.lower()
    shortest = min(len(first), len(second))
    common = 0
    while common < shortest and first[common] == second[common]:
        common += 1
    return common >= _STEM_PREFIX_MINIMUM


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


def _content_tokens(tokens):
    return [token for token in tokens if not token.is_punct and not token.is_space]


def _is_function_only(tokens) -> bool:
    real = [token for token in tokens if not token.is_space]
    return bool(real) and all(token.pos_ in _FUNCTION_POS for token in real)


def _deictic(token) -> bool:
    return token.pos_ == "ADV" and token.tag_ == "RB" and token.dep_ in ("advmod", "npadvmod")


def _is_nominalisation(token) -> bool:
    if token.pos_ != "NOUN":
        return False
    lemma = token.lemma_.lower()
    if not lemma.endswith(_NOMINAL_SUFFIXES):
        return False
    return any(len(related) > 2 for related in _related_lemmas(lemma))


def _bead_is_passive(sentences) -> bool:
    for sentence in sentences:
        for token in sentence:
            if token.dep_ in _PASSIVE_DEPS:
                return True
    return False


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
    by_band: dict = field(default_factory=_counters_by_key)
    examples: dict = field(default_factory=_lists_by_key)
    findings: list = field(default_factory=list)
    content_loss: dict = field(default_factory=_lists_by_key)


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
    nouns = [token for token in tokens if token.pos_ == "NOUN"]
    if len(nouns) < 2:
        return False
    return _is_concrete(nouns[0].lemma_.lower()) and not _is_concrete(nouns[-1].lemma_.lower())


def _content_lemmas(sentences) -> frozenset:
    """Every lemma on one side of a bead, without punctuation or stop words."""
    lemmas = set()
    for sentence in sentences:
        for token in sentence:
            if not token.is_punct and not token.is_stop:
                lemmas.add(token.lemma_.lower())
    return frozenset(lemmas)


@dataclass
class BeadContext:
    """Bead-level facts every span detector shares, computed once."""
    voice_shift: bool
    source_lemmas: frozenset
    target_lemmas: frozenset


def bead_context(bead) -> BeadContext:
    return BeadContext(
        voice_shift=_bead_is_passive(bead.source) and not _bead_is_passive(bead.target),
        source_lemmas=_content_lemmas(bead.source),
        target_lemmas=_content_lemmas(bead.target),
    )


def _touches_passive(tokens) -> bool:
    return any(token.dep_ in _PASSIVE_DEPS or token.tag_ == "VBN" for token in tokens)


def _any_pair_linked(source_tokens, target_tokens) -> bool:
    """Whether any word on one side is morphologically related to any word on the other."""
    for source in source_tokens:
        for target in target_tokens:
            if _morphologically_linked(source.lemma_, target.lemma_):
                return True
    return False


def _classify_deletion(span, bead, ctx) -> dict:
    tokens = _content_tokens(span.source_tokens)
    if not tokens:
        return {"family": "punctuation", "subtype": "punctuation-only"}
    if ctx.voice_shift and _touches_passive(span.source_tokens):
        return {"family": "voice", "subtype": "passive-auxiliary-dropped"}
    if _is_function_only(span.source_tokens):
        return {"family": "realisation", "subtype": "function-word-dropped"}
    deps = {token.dep_ for token in tokens}
    pos = {token.pos_ for token in tokens}

    if pos <= {"DET", "PRON"}:
        return {"family": "determiner", "subtype": "determiner-dropped"}
    if len(tokens) == 1 and tokens[0].pos_ == "ADV" and tokens[0].dep_ in _DEGREE_DEPS:
        if tokens[0].head.pos_ in ("ADJ", "ADV"):
            return {"family": "intensifier", "subtype": "degree-adverb-dropped"}
        return {"family": "stance", "subtype": "sentence-adverb-dropped"}
    if any(token.dep_ == "relcl" for token in tokens) or tokens[0].tag_ in ("WDT", "WP"):
        return {"family": "relative-clause", "subtype": "relative-clause-dropped"}
    has_predicate = any(token.pos_ == "VERB" and token.dep_ in _PREDICATE_DEPS
                        for token in tokens)
    if has_predicate and len(tokens) >= 6:
        return {"family": "clause", "subtype": "clause-dropped"}
    if has_predicate:
        return {"family": "clause", "subtype": "predicate-absorbed"}
    if _figurative_frame(tokens):
        return {"family": "figurative", "subtype": "metaphorical-frame-dropped"}
    if tokens[0].pos_ == "ADP" or any(token.dep_ == "prep" for token in tokens):
        return {"family": "adjunct", "subtype": "prepositional-phrase-dropped"}
    if pos <= {"ADJ", "ADV"} or deps <= {"amod", "advmod", "npadvmod"}:
        return {"family": "modifier", "subtype": "modifier-dropped"}
    if len(tokens) == 1:
        return {"family": "lexical", "subtype": "word-dropped"}
    return {"family": "phrase", "subtype": "phrase-dropped"}


def _structural_replacement(span, src, tgt, ctx) -> dict | None:
    """The transformations named by a structural relation between the two sides."""
    for source in src:
        if _is_nominalisation(source) and any(
            token.pos_ in ("VERB", "AUX") and _morphologically_linked(source.lemma_, token.lemma_)
            for token in tgt
        ):
            return {"family": "nominalisation", "subtype": "nominal-to-verb"}

    if ctx.voice_shift and _touches_passive(span.source_tokens):
        return {"family": "voice", "subtype": "passive-to-active"}

    if len(src) > 1 and len(tgt) == 1 and tgt[0].pos_ in ("VERB", "AUX"):
        if any(source.pos_ == "NOUN" and _morphologically_linked(source.lemma_, tgt[0].lemma_)
               for source in src):
            return {"family": "support-verb", "subtype": "light-verb-to-lexical-verb"}
        if any(source.pos_ in ("VERB", "AUX") for source in src):
            return {"family": "support-verb", "subtype": "verb-phrase-to-verb"}

    if len(tgt) == 1 and tgt[0].pos_ == "ADV" and any(token.pos_ == "ADP"
                                                      for token in span.source_tokens):
        if any(source.pos_ in ("NOUN", "ADJ") and _morphologically_linked(source.lemma_,
                                                                          tgt[0].lemma_)
               for source in src):
            return {"family": "adjunct", "subtype": "prepositional-phrase-to-adverb"}
        return {"family": "adjunct", "subtype": "prepositional-phrase-to-deictic"}

    if any(token.pos_ == "ADP" and token.lemma_.lower() == "of" for token in span.source_tokens) \
            and any(token.tag_ == "POS" for token in span.target_tokens):
        return {"family": "adjunct", "subtype": "of-phrase-to-genitive"}

    if _figurative_frame(src) and not _figurative_frame(tgt):
        return {"family": "figurative", "subtype": "metaphor-to-direct-statement"}
    return None


def _word_for_word(source, target) -> dict:
    if source.lemma_.lower() == target.lemma_.lower():
        return {"family": "morphology", "subtype": "inflection-only"}
    if source.pos_ in ("ADV", "SCONJ", "CCONJ") and target.pos_ in ("ADV", "SCONJ", "CCONJ"):
        return {"family": "connective", "subtype": "connective-swapped"}
    if not (source.is_alpha and target.is_alpha):
        return {"family": "phrase", "subtype": "paraphrase-rewrite"}
    if _frequency(target.text) > _frequency(source.text) and \
            _syllables(target.text) <= _syllables(source.text):
        return {"family": "lexical", "subtype": "long-to-plain"}
    if _morphologically_linked(source.lemma_, target.lemma_):
        return {"family": "lexical", "subtype": "derivational-swap"}
    return {"family": "lexical", "subtype": "synonym-swap"}


def _paraphrase_kind(src, tgt) -> dict:
    src_lemmas = {token.lemma_.lower() for token in src}
    tgt_lemmas = {token.lemma_.lower() for token in tgt}
    if src_lemmas and src_lemmas <= tgt_lemmas:
        return {"family": "phrase", "subtype": "phrase-reordered"}
    if tgt_lemmas and tgt_lemmas <= src_lemmas:
        return {"family": "phrase", "subtype": "head-preserved-compression"}
    if _any_pair_linked(src, tgt):
        return {"family": "phrase", "subtype": "recategorised-compression"}
    if len(src) > len(tgt):
        return {"family": "phrase", "subtype": "paraphrase-compression"}
    return {"family": "phrase", "subtype": "paraphrase-rewrite"}


def _classify_replacement(span, bead, ctx) -> dict:
    src = _content_tokens(span.source_tokens)
    tgt = _content_tokens(span.target_tokens)
    if not src and not tgt:
        return {"family": "punctuation", "subtype": "punctuation-only"}
    if not tgt:
        return _classify_deletion(span, bead, ctx)
    if not src:
        return _classify_insertion(span, bead, ctx)
    if _is_function_only(span.source_tokens) and _is_function_only(span.target_tokens):
        return {"family": "realisation", "subtype": "function-word-swapped"}
    structural = _structural_replacement(span, src, tgt, ctx)
    if structural:
        return structural
    if len(src) == 1 and len(tgt) == 1:
        return _word_for_word(src[0], tgt[0])
    return _paraphrase_kind(src, tgt)


def _classify_insertion(span, bead, ctx) -> dict:
    tokens = _content_tokens(span.target_tokens)
    if not tokens:
        return {"family": "punctuation", "subtype": "punctuation-only"}
    if _is_function_only(span.target_tokens):
        if ctx.voice_shift and any(token.pos_ == "PRON" for token in span.target_tokens):
            return {"family": "voice", "subtype": "agent-restored"}
        return {"family": "realisation", "subtype": "function-word-inserted"}
    if ctx.voice_shift and any(token.dep_ in ("nsubj", "nsubjpass") for token in tokens):
        return {"family": "voice", "subtype": "agent-restored"}
    if len(tokens) == 1 and tokens[0].pos_ in ("SCONJ", "CCONJ", "ADV"):
        return {"family": "connective", "subtype": "connective-inserted"}
    introduced = {token.lemma_.lower() for token in tokens} - ctx.source_lemmas
    if len(introduced) >= 2:
        return {"family": "phrase", "subtype": "material-introduced"}
    return {"family": "phrase", "subtype": "material-inserted"}


def classify_span(span, bead, ctx) -> dict:
    """Family and subtype for one span edit, from the parse and its bead context."""
    if span.op == "delete":
        return _classify_deletion(span, bead, ctx)
    if span.op == "insert":
        return _classify_insertion(span, bead, ctx)
    return _classify_replacement(span, bead, ctx)


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


def _content_loss(ctx) -> float:
    """The share of a bead's content words the edit dropped without keeping a relative."""
    if not ctx.source_lemmas:
        return 0.0
    lost = []
    for word in ctx.source_lemmas - ctx.target_lemmas:
        kept_a_relative = any(_morphologically_linked(word, kept) for kept in ctx.target_lemmas)
        if not kept_a_relative:
            lost.append(word)
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
        kind = classify_span(span, bead, ctx)
        family, subtype = kind["family"], kind["subtype"]
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
