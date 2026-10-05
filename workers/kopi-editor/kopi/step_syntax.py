import re
from kopi.data_syntax_patterns import (
    INTENSIFIER_DEP_PATTERN, SKIP_AFTER_INTENSIFIER,
    RELCL_PATTERN, DEMONSTRATIVE_GERUNDS,
)
from kopi.quote_guard import guard, unguard, word_count
from kopi.quote_guard import _PATTERN as _QUOTE_RE

_nlp = None
_dep_matcher = None
_RELCL_SKIP_SUFFIX = ("ly", "ing", "tion", "ment", "ance", "ence")


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def _get_dep_matcher(nlp):  # lint-style: ignore FN004
    global _dep_matcher
    if _dep_matcher is None:
        from spacy.matcher import DependencyMatcher
        _dep_matcher = DependencyMatcher(nlp.vocab)
        _dep_matcher.add("INTENSIFIER", [INTENSIFIER_DEP_PATTERN])
    return _dep_matcher


def _para_num(text: str, phrase: str) -> str:
    search = phrase.split("\n")[0].strip()[:60].lower()
    for i, para in enumerate(text.split("\n\n"), 1):
        if search in para.lower():
            return f"P{i}"
    return "P?"


def _in_quotes(start: int, end: int, ranges) -> bool:
    return any(qs <= start < qe or qs < end <= qe for qs, qe in ranges)


def _apply_changes(text: str, changes: list) -> str:
    for start, end, repl in sorted(changes, key=lambda x: -x[0]):
        text = text[:start] + repl + text[end:]
    return re.sub(r" {2,}", " ", text).strip()


def _para_index(offset: int, para_offsets: list) -> int:  # lint-style: ignore FN004
    for i, (s, e) in enumerate(para_offsets):
        if s <= offset <= e:
            return i
    return max(0, len(para_offsets) - 1)


def _remove_intensifiers(doc, text: str, qranges: list, changelog: list,
                         para_tracking: dict = None) -> str:
    nlp = _get_nlp()
    dm = _get_dep_matcher(nlp)
    matches = dm(doc)
    changes = []

    for match_id, token_ids in matches:
        if nlp.vocab.strings[match_id] != "INTENSIFIER":
            continue
        head_idx, adv_idx = token_ids[0], token_ids[1]
        head_tok = doc[head_idx]
        adv_tok = doc[adv_idx]

        if adv_tok.i >= head_tok.i:
            continue

        next_i = adv_tok.i + 1
        if next_i < len(doc) and doc[next_i].lemma_.lower() in SKIP_AFTER_INTENSIFIER:
            continue

        start = adv_tok.idx
        end = head_tok.idx
        if _in_quotes(start, end, qranges):
            continue

        if para_tracking is not None:
            hits = para_tracking["hits"]
            offsets = para_tracking["offsets"]
            hits[_para_index(start, offsets)] += 1
        changes.append((start, end, ""))
        changelog.append({
            "step": "Step 4: Syntax",
            "detail": f"intensifier removed: '{adv_tok.text}' before '{head_tok.text}'",
            "para": _para_num(text, adv_tok.text),
        })

    return _apply_changes(text, changes)


_DUP_POS = frozenset(["NOUN", "PROPN", "ADJ", "ADV", "VERB"])


def _remove_dup_tokens(doc, text: str, qranges: list, changelog: list) -> str:
    """Delete an accidentally repeated adjacent content word ('consumer consumer')."""
    changes = []
    for i in range(len(doc) - 1):
        a, b = doc[i], doc[i + 1]
        if not (a.is_alpha and b.is_alpha):
            continue
        if len(a.text) <= 2 or a.text.lower() != b.text.lower():
            continue
        if a.pos_ not in _DUP_POS:
            continue
        start, end = a.idx, b.idx
        if _in_quotes(start, end, qranges):
            continue
        changes.append((start, end, ""))
        changelog.append({
            "step": "Step 4: Syntax",
            "detail": f"duplicate word removed: '{a.text} {b.text}' -> '{b.text}'",
            "para": _para_num(text, a.text),
        })
    return _apply_changes(text, changes)


_RELCL_SKIP = frozenset([
    "more",
    "less",
    "rather",
    "quite",
    "very",
    "too",
    "much",
    "such",
    "about",
    "over",
    "under",
    "further",
    "better",
    "worse",
    "greater",
    "higher",
    "lower",
    "broader",
    "wider",
    "deeper",
    "longer",
    "larger",
])
def _safe_adj(word: str) -> bool:
    w = word.lower()
    return w not in _RELCL_SKIP and not any(w.endswith(s) for s in _RELCL_SKIP_SUFFIX)


def _reduce_relcl(text: str, qranges: list, changelog: list) -> str:
    changes = []
    for m in RELCL_PATTERN.finditer(text):
        if _in_quotes(m.start(), m.end(), qranges):
            continue
        art, noun, adj = m.group(1), m.group(2).lower(), m.group(3).lower()
        if not _safe_adj(adj):
            continue
        if art.lower() in ("a", "an"):
            new_word = "an" if adj[0].lower() in "aeiou" else "a"
            new_art = new_word.capitalize() if art[0].isupper() else new_word
        else:
            new_art = art
        replacement = f"{new_art} {adj} {noun}"
        changes.append((m.start(), m.end(), replacement))
        changelog.append({
            "step": "Step 4: Syntax",
            "detail": f"relative clause reduced: '{m.group(0)}' -> '{replacement}'",
            "para": _para_num(text, m.group(0)[:40]),
        })
    for start, end, replacement in sorted(changes, key=lambda x: -x[0]):
        text = text[:start] + replacement + text[end:]
    return text


def _merge_demonstratives(text: str, qranges: list, changelog: list) -> str:
    verbs = "|".join(re.escape(v) for v in DEMONSTRATIVE_GERUNDS)
    pattern = re.compile(
        r"([.!?])\s+(This|It)\s+(" + verbs + r")\s+that\s+",
        re.IGNORECASE,
    )
    changes = []
    for m in pattern.finditer(text):
        if _in_quotes(m.start(), m.end(), qranges):
            continue
        verb = m.group(3).lower()
        gerund = DEMONSTRATIVE_GERUNDS.get(verb, verb + "ing")
        replacement = f", {gerund} that "
        changes.append((m.start(), m.end(), replacement))
        changelog.append({
            "step": "Step 4: Syntax",
            "detail": f"demonstrative merged: 'S. {m.group(2)} {m.group(3)} that' -> ', {gerund} that'",
            "para": None,
        })
    for start, end, replacement in sorted(changes, key=lambda x: -x[0]):
        text = text[:start] + replacement + text[end:]
    return text


def run(state: dict) -> dict:
    try:
        nlp = _get_nlp()
    except OSError:
        state["log"].append({
            "step": "Step 4: Syntax",
            "detail": "skipped, run: python -m spacy download en_core_web_sm",
            "para": None,
        })
        return state
    except ImportError:
        state["log"].append({
            "step": "Step 4: Syntax",
            "detail": "skipped: spacy not installed",
            "para": None,
        })
        return state

    restored = unguard(state["text"], state["qmap"])
    qranges = [(m.start(), m.end()) for m in _QUOTE_RE.finditer(restored)]
    changelog = []

    # Per-paragraph intensifier counts (before removal): a fat-index input for
    # Step 10 routing. Aligned to the current \n\n split; consumer guards on length.
    paras = restored.split("\n\n")
    para_offsets = []
    pos = 0
    for para in paras:
        para_offsets.append((pos, pos + len(para)))
        pos += len(para) + 2
    para_hits = [0] * len(paras)

    doc = nlp(restored)
    para_tracking = {"hits": para_hits, "offsets": para_offsets}
    restored = _remove_intensifiers(doc, restored, qranges, changelog, para_tracking)
    restored = _remove_dup_tokens(nlp(restored), restored, qranges, changelog)
    restored = _reduce_relcl(restored, qranges, changelog)
    restored = _merge_demonstratives(restored, qranges, changelog)

    quoted = guard(restored)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {
        **state,
        "text": guarded,
        "qmap": qmap,
        "intensifier_para_hits": para_hits,
    }
    current = word_count(guarded, qmap)
    state["counts"]["step4_syntax"] = current
    state["log"].append({
        "step": "Step 4: Syntax",
        "detail": f"{len(changelog)} transform(s) applied -> {current} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state
