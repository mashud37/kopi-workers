import re

from kopi.data_plain import CLICHE_REPLACEMENTS, WORD_SUBSTITUTIONS
from kopi.pipeline import load_nlp
from kopi.quote_guard import guard, unguard, word_count

_POS_GATED = frozenset([
    "previously",
    "subsequently",
    "currently",
    "presently",
    "formerly",
    "recently",
    "nowadays",
])


def _para_num(text: str, phrase: str) -> str:
    search = phrase.split("\n")[0].strip()[:60].lower()
    for i, para in enumerate(text.split("\n\n"), 1):
        if search in para.lower():
            return f"P{i}"
    return "P?"


def _preserve_case(original: str, replacement: str) -> str:
    if not replacement:
        return replacement
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _safe_for_adv(doc, word: str) -> set[int]:  # lint-style: ignore FN004
    safe_indices = set()
    for token in doc:
        if token.text.lower() == word and token.pos_ == "ADV":
            if token.i + 1 < len(doc) and doc[token.i + 1].pos_ == "ADJ":
                continue
            safe_indices.add(token.idx)
    return safe_indices


def _apply_lookup(text: str, lookup: dict, changelog: list, step_label: str, doc=None) -> str:
    for phrase, replacement in sorted(lookup.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)

        if doc is not None and phrase.lower() in _POS_GATED:
            safe = _safe_for_adv(doc, phrase.lower())
            matches = [m for m in pattern.finditer(text) if m.start() in safe]
            if not matches:
                continue
            para_ref = _para_num(text, phrase)
            new_text = text
            for m in reversed(matches):
                repl = _preserve_case(m.group(0), replacement) if replacement else ""
                new_text = new_text[:m.start()] + repl + new_text[m.end():]
            if new_text != text:
                repl_display = f"'{replacement}'" if replacement else "(deleted)"
                changelog.append({"step": step_label, "detail": f"'{phrase}' -> {repl_display}", "para": para_ref})
                text = re.sub(r" {2,}", " ", new_text).strip()
            continue

        matches = list(pattern.finditer(text))
        if not matches:
            continue
        para_ref = _para_num(text, phrase)
        new_text = text
        for m in reversed(matches):
            repl = _preserve_case(m.group(0), replacement) if replacement else ""
            new_text = new_text[:m.start()] + repl + new_text[m.end():]
        if new_text != text:
            repl_display = f"'{replacement}'" if replacement else "(deleted)"
            changelog.append({"step": step_label, "detail": f"'{phrase}' -> {repl_display}", "para": para_ref})
            text = re.sub(r" {2,}", " ", new_text).strip()

    return text


def run(state: dict) -> dict:
    restored = unguard(state["text"], state["qmap"])
    changelog = []

    nlp = load_nlp()
    try:
        doc = nlp(restored) if nlp is not None else None
    except Exception:
        doc = None

    restored = _apply_lookup(restored, CLICHE_REPLACEMENTS, changelog, "Step 8: Plain language (cliché)")
    restored = _apply_lookup(restored, WORD_SUBSTITUTIONS, changelog, "Step 8: Plain language (word)", doc)

    quoted = guard(restored)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {**state, "text": guarded, "qmap": qmap}
    current = word_count(guarded, qmap)
    state["counts"]["step8"] = current
    state["log"].append({
        "step": "Step 8: Plain language",
        "detail": f"{len(changelog)} substitution(s) -> {current} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state
