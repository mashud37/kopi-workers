"""Parse the document once, producing document-level estimates (fillers,
redundant sentences, readability) plus per-paragraph editing instructions,
shared by analyze, proof, and edit. Only reads the parse, never mutates text.
"""
import re

from kopi import signals, step_redundancy
from kopi.data_fillers import PHRASE_REPLACEMENTS
from kopi.data_padding_tails import TAIL_PATTERNS
from kopi.data_plain import CLICHE_REPLACEMENTS, WORD_SUBSTITUTIONS

# Paragraphs shorter than this are left alone (too little to edit meaningfully).
_MIN_PARA_WORDS = 40

# Per-paragraph density thresholds for raising a tag. Deliberately low: a single
# clear hit is enough to nudge the model, and the directives are non-destructive.
_WORDINESS_HITS = 1          # filler/padding phrases present
_PLAIN_HITS = 1              # clichés or long words present
_LONG_SENTENCE_WORDS = 40    # mean sentence length above this -> suggest splitting
_PASSIVE_RATIO = 0.30        # fraction of sentences with a passive construction

# The plain-language directive is ALWAYS applied: the plain-language rules run
# regardless of their impact on word count.
_PLAIN_LANGUAGE = (
    "Plain language: replace long or Latinate words with short plain ones; "
    "remove clichéd metaphors, similes, and idioms in favour of direct statement."
)
_WORDINESS = (
    "Remove hedges, fillers, and padding phrases "
    "(e.g. 'it is worth noting that', 'in order to', 'the fact that')."
)
_REDUNDANCY = (
    "Consolidate sentences that repeat a point already made; "
    "merge a short follow-on sentence into the one before it."
)
_PASSIVE = "Prefer the active voice where it reads naturally."
_LONG_SENTENCE = "Split only a genuinely overlong or hard-to-follow sentence; keep the prose flowing, not choppy."

# Public map of tag -> the exact directive the LLM editor receives. The analysis
# report shows these verbatim so a human editing by hand follows the same guidance.
INSTRUCTION_BY_TAG = {
    "plain-language": _PLAIN_LANGUAGE,
    "wordiness": _WORDINESS,
    "redundancy": _REDUNDANCY,
    "passive": _PASSIVE,
    "long-sentence": _LONG_SENTENCE,
}


_SECTION_NUM = re.compile(r"^\d+(\.\d+)*\.?\s+\S")


def _is_heading(para: str) -> bool:
    """A title or section heading, never edited, and not a real paragraph.

    Caught: markdown headings (``# …``), numbered headings (``1.``, ``1.1 …``,
    ``2.3.4 …``), and short unnumbered titles (a handful of words, no terminal
    sentence punctuation, capitalised).
    """
    first = (para.strip().split("\n", 1)[0]).strip()
    if not first:
        return False
    if first.startswith("#") or _SECTION_NUM.match(first):
        return True
    words = first.split()
    return len(words) <= 10 and first[-1] not in ".?!:;," and first[0].isupper()


def _phrase_count(text: str, phrase: str) -> int:
    return len(re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE).findall(text))


def _unnecessary_words(text: str) -> tuple[int, int]:
    """(hit count, estimated removable words) from filler phrases + padding tails."""
    hits = 0
    savings = 0
    for phrase, replacement in PHRASE_REPLACEMENTS.items():
        c = _phrase_count(text, phrase)
        if c:
            hits += c
            savings += c * (len(phrase.split()) - (len(replacement.split()) if replacement else 0))
    for pattern, _ in TAIL_PATTERNS:
        for m in pattern.findall(text):
            hits += 1
            savings += len(m.split())
    return {"hits": hits, "savings": savings}


def _plain_hits(text: str) -> int:
    """Clichéd phrases + long-word substitutions present in the text."""
    hits = 0
    for phrase in CLICHE_REPLACEMENTS:
        hits += _phrase_count(text, phrase)
    for word in WORD_SUBSTITUTIONS:
        hits += _phrase_count(text, word)
    return hits


def _content_lemmas(spans) -> list[set]:
    """The content lemmas of each sentence, stop words and function words dropped."""
    per_sentence = []
    for span in spans:
        lemmas = set()
        for token in span:
            if token.pos_ in step_redundancy._CONTENT_POS and not token.is_stop:
                lemmas.add(token.lemma_.lower())
        per_sentence.append(lemmas)
    return per_sentence


def _similarity_matrix(content: list[set], idf: dict) -> list[list[float]]:
    """Every sentence against every other, by IDF-weighted overlap.

    Lexical rather than embedded, so `analyze` stays fast and needs no model.
    """
    matrix = []
    for left in content:
        row = []
        for right in content:
            row.append(step_redundancy._weighted_overlap(left, right, idf))
        matrix.append(row)
    return matrix


def _redundancy_estimate(text: str, nlp) -> dict:
    """Redundant sentence `count`, estimated `words`, and the `paragraphs` touched.

    Reuses step_redundancy's IDF-weighted restatement detection on the whole
    document, then maps each flagged restatement back to its paragraph so the
    affected paragraphs can carry the *redundancy* tag.
    """
    paragraphs = text.split("\n\n")
    doc = nlp(text)
    spans = [s for s in doc.sents if len(s.text.split()) >= step_redundancy._MIN_WORDS]
    sentences = [s.text.strip() for s in spans]
    if len(sentences) < 2:
        return {"count": 0, "words": 0, "paragraphs": set()}

    content = _content_lemmas(spans)
    idf = step_redundancy._build_idf(content)
    sim = _similarity_matrix(content, idf)
    thresholds = {"similarity": 0.55, "overlap": 0.40}
    pairs = step_redundancy._select_redundant(sentences, content, sim, idf, thresholds)

    words = sum(p["savings"] for p in pairs)
    touched = set()
    for p in pairs:
        snippet = p["remove"][:40].lower()
        for i, para in enumerate(paragraphs):
            if snippet in para.lower():
                touched.add(i)
                break
    return {"count": len(pairs), "words": words, "paragraphs": touched}


def _paragraph_instructions(para: str, feats: dict, is_redundant: bool) -> dict:
    """The `tags` and ordered `instructions` for one paragraph. Plain language always."""
    tags = {"plain-language"}
    instructions = [_PLAIN_LANGUAGE]

    if _unnecessary_words(para)["hits"] >= _WORDINESS_HITS:
        tags.add("wordiness")
        instructions.append(_WORDINESS)

    if is_redundant:
        tags.add("redundancy")
        instructions.append(_REDUNDANCY)

    if feats.get("mean_sent_len", 0) >= _LONG_SENTENCE_WORDS:
        tags.add("long-sentence")
        instructions.append(_LONG_SENTENCE)

    n_sents = feats.get("n_sents", 0)
    if n_sents and feats.get("passive_sents", 0) / n_sents >= _PASSIVE_RATIO:
        tags.add("passive")
        instructions.append(_PASSIVE)

    return {"tags": tags, "instructions": instructions}


def _paragraph_entry(i: int, para: str, doc, red_paras: set[int]) -> dict:
    """Diagnosis entry for one paragraph: display fields plus tags/instructions."""
    words = len(para.split())
    is_quote = signals._is_quote_para(para)
    is_heading = _is_heading(para)

    snippet_text = " ".join(para.split())
    snippet = (snippet_text[:72] + "…") if len(snippet_text) > 72 else snippet_text

    if is_heading:
        flesch = None
    else:
        try:
            import textstat
            flesch = round(textstat.flesch_reading_ease(para))
        except Exception:
            flesch = None

    entry = {
        "index": i,
        "words": words,
        "is_quote": is_quote,
        "is_heading": is_heading,
        "snippet": snippet,
        "flesch": flesch,
        "mean_sent_len": None,
        "tags": set(),
        "instructions": [],
    }
    if words < _MIN_PARA_WORDS or is_quote or is_heading:
        return entry

    sents = [signals.sentence_features(s) for s in doc.sents if s.text.strip()]
    n_sents = len(sents)
    feats = {
        "n_sents": n_sents,
        "mean_sent_len": sum(s["words"] for s in sents) / n_sents if n_sents else 0.0,
        "passive_sents": sum(1 for s in sents if s["passive"] > 0),
    }
    asked = _paragraph_instructions(para, feats, i in red_paras)
    entry["mean_sent_len"] = round(feats["mean_sent_len"], 1)
    entry["tags"] = asked["tags"]
    entry["instructions"] = asked["instructions"]
    return entry


def diagnose(text: str, nlp) -> dict:
    """Parse once; return document estimates + per-paragraph tags/instructions.

    ``nlp`` is a loaded spaCy pipeline. Returns::

        {
          "words": int,
          "readability": float | None,
          "unnecessary": {"hits": int, "savings": int},   # STEP 2
          "redundancy":  {"count": int, "savings": int},   # STEP 3
          "paragraphs": [
            {"index", "words", "is_quote", "tags": set, "instructions": [str]}
          ],
        }
    """
    paragraphs = text.split("\n\n")

    unnecessary = _unnecessary_words(text)
    redundancy = _redundancy_estimate(text, nlp)
    red_paras = redundancy["paragraphs"]

    try:
        import textstat
        readability = round(textstat.flesch_reading_ease(text), 1)
    except Exception:
        readability = None

    out_paras = [
        _paragraph_entry(i, para, doc, red_paras)
        for i, (doc, para) in enumerate(zip(nlp.pipe(paragraphs), paragraphs))
    ]

    return {
        "words": len(text.split()),
        "readability": readability,
        "unnecessary": unnecessary,
        "redundancy": {"count": redundancy["count"], "savings": redundancy["words"]},
        "paragraphs": out_paras,
    }
