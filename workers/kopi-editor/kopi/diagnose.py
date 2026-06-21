"""Shared deterministic diagnosis — the single core behind all three routes.

Parses the document **once** and produces:

* **Document-level estimates** for the analysis report:
    - STEP 2 — unnecessary words: filler/padding count + estimated word reduction.
    - STEP 3 — redundant sentences: count + estimated word reduction.
    - readability (Flesch) and total word count.
* **Per-paragraph instructions**: a small, fixed vocabulary of *categorical*
  editing directives (never verbatim document text), derived from cheap signals.
  The LLM route hands these to the model so a cheaper-than-Opus model knows
  exactly what each paragraph needs; the analysis route reports them.

The detectors are reused, not reinvented: ``data_fillers`` / ``data_padding_tails``
(unnecessary words), ``data_plain`` (clichés + long→short words), ``step_redundancy``
(IDF-weighted restatement + merge candidates), and ``signals.sentence_features``
(passive voice, sentence length, parse depth).

This module never mutates text — it only reads the parse.
"""
import re

from kopi.data_fillers import PHRASE_REPLACEMENTS
from kopi.data_padding_tails import TAIL_PATTERNS
from kopi.data_plain import CLICHE_REPLACEMENTS, WORD_SUBSTITUTIONS
from kopi import signals
from kopi import step_redundancy

# Paragraphs shorter than this are left alone (too little to edit meaningfully).
_MIN_PARA_WORDS = 40

# Per-paragraph density thresholds for raising a tag. Deliberately low — a single
# clear hit is enough to nudge the model, and the directives are non-destructive.
_WORDINESS_HITS = 1          # filler/padding phrases present
_PLAIN_HITS = 1              # clichés or long words present
_LONG_SENTENCE_WORDS = 40    # mean sentence length above this -> suggest splitting
_PASSIVE_RATIO = 0.30        # fraction of sentences with a passive construction

# The plain-language directive is ALWAYS applied — the plain-language rules run
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
    """A title or section heading — never edited, and not a real paragraph.

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


def _snippet(para: str, n: int = 72) -> str:
    """The paragraph's opening, truncated for a table cell."""
    s = " ".join(para.split())
    return (s[:n] + "…") if len(s) > n else s


def _para_flesch(para: str):
    try:
        import textstat
        return round(textstat.flesch_reading_ease(para))
    except Exception:
        return None


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
    return hits, savings


def _plain_hits(text: str) -> int:
    """Clichéd phrases + long-word substitutions present in the text."""
    hits = 0
    for phrase in CLICHE_REPLACEMENTS:
        hits += _phrase_count(text, phrase)
    for word in WORD_SUBSTITUTIONS:
        hits += _phrase_count(text, word)
    return hits


def _redundancy_estimate(text: str, nlp) -> tuple[int, int, set[int]]:
    """(redundant sentence count, estimated words, paragraph indices touched).

    Reuses step_redundancy's IDF-weighted restatement detection on the whole
    document, then maps each flagged restatement back to its paragraph so the
    affected paragraphs can carry the *redundancy* tag.
    """
    paragraphs = text.split("\n\n")
    doc = nlp(text)
    spans = [s for s in doc.sents if len(s.text.split()) >= step_redundancy._MIN_WORDS]
    sentences = [s.text.strip() for s in spans]
    if len(sentences) < 2:
        return 0, 0, set()

    content = [
        {t.lemma_.lower() for t in span if t.pos_ in step_redundancy._CONTENT_POS and not t.is_stop}
        for span in spans
    ]
    idf = step_redundancy._build_idf(content)

    # Lexical similarity from the IDF-weighted overlap (no embedding model needed
    # for the report — keeps `analyze` fast and dependency-light).
    n = len(sentences)
    sim = [[step_redundancy._weighted_overlap(content[i], content[j], idf) for j in range(n)] for i in range(n)]
    pairs = step_redundancy._select_redundant(sentences, content, sim, idf,
                                              sim_threshold=0.55, overlap_threshold=0.40)

    words = sum(p["savings"] for p in pairs)
    touched = set()
    for p in pairs:
        snippet = p["remove"][:40].lower()
        for i, para in enumerate(paragraphs):
            if snippet in para.lower():
                touched.add(i)
                break
    return len(pairs), words, touched


def _paragraph_instructions(para: str, feats: dict, is_redundant: bool) -> tuple[set[str], list[str]]:
    """Tags + ordered instruction list for one paragraph. Plain language always."""
    tags = {"plain-language"}
    instructions = [_PLAIN_LANGUAGE]

    hits, _ = _unnecessary_words(para)
    if hits >= _WORDINESS_HITS:
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

    return tags, instructions


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

    total_hits, total_unnecessary = _unnecessary_words(text)
    red_count, red_words, red_paras = _redundancy_estimate(text, nlp)

    try:
        import textstat
        readability = round(textstat.flesch_reading_ease(text), 1)
    except Exception:
        readability = None

    out_paras = []
    for i, (doc, para) in enumerate(zip(nlp.pipe(paragraphs), paragraphs)):
        words = len(para.split())
        is_quote = signals._is_quote_para(para)
        is_heading = _is_heading(para)
        entry = {
            "index": i, "words": words, "is_quote": is_quote, "is_heading": is_heading,
            "snippet": _snippet(para),
            "flesch": None if is_heading else _para_flesch(para),
            "mean_sent_len": None, "tags": set(), "instructions": [],
        }
        if words < _MIN_PARA_WORDS or is_quote or is_heading:
            out_paras.append(entry)
            continue
        sents = [signals.sentence_features(s) for s in doc.sents if s.text.strip()]
        n_sents = len(sents)
        feats = {
            "n_sents": n_sents,
            "mean_sent_len": sum(s["words"] for s in sents) / n_sents if n_sents else 0.0,
            "passive_sents": sum(1 for s in sents if s["passive"] > 0),
        }
        tags, instructions = _paragraph_instructions(para, feats, i in red_paras)
        entry["mean_sent_len"] = round(feats["mean_sent_len"], 1)
        entry["tags"] = tags
        entry["instructions"] = instructions
        out_paras.append(entry)

    return {
        "words": len(text.split()),
        "readability": readability,
        "unnecessary": {"hits": total_hits, "savings": total_unnecessary},
        "redundancy": {"count": red_count, "savings": red_words},
        "paragraphs": out_paras,
    }
