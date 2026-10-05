import re

from kopi.quote_guard import guard, unguard, word_count

_CONNECTOR_DROP = re.compile(
    r"([.!?])\s+(And|Also)\s+",
    re.IGNORECASE,
)

_CONNECTOR_SEMI = re.compile(
    r"([.!?])\s+(Furthermore|Moreover|In addition,|Additionally,)\s+",
    re.IGNORECASE,
)

_THIS_IS = re.compile(
    r"([.!?])\s+This\s+is\s+(?:because|due\s+to\s+the\s+fact\s+that|why|how)\s+",
    re.IGNORECASE,
)


def _para_num(text: str, phrase: str) -> str:
    search = phrase.split("\n")[0].strip()[:60].lower()
    for i, para in enumerate(text.split("\n\n"), 1):
        if search in para.lower():
            return f"P{i}"
    return "P?"


def _drop_replacement(m):
    connector = m.group(2).lower()
    return f", {connector} "


def _semi_replacement(m):
    connector = m.group(2).rstrip(",").lower()
    return f"; {connector}, "


def _this_is_replacement(m):
    conjunction = m.group(0).split()[-1].lower().rstrip()
    return f" {conjunction} "


def run(state: dict) -> dict:
    if state.get("no_llm") is None:
        pass

    restored = unguard(state["text"], state["qmap"])
    changelog = []

    for m in _CONNECTOR_DROP.finditer(restored):
        connector = m.group(2).lower()
        changelog.append({
            "step": "Step 6: Merge",
            "detail": f"connector merge: '. {m.group(2)}' -> ', {connector}'",
            "para": _para_num(restored, m.group(2)),
        })
    text = _CONNECTOR_DROP.sub(_drop_replacement, restored)

    for m in _CONNECTOR_SEMI.finditer(text):
        connector = m.group(2).rstrip(",").lower()
        changelog.append({
            "step": "Step 6: Merge",
            "detail": f"connector merge: '. {m.group(2)}' -> '; {connector},'",
            "para": _para_num(restored, m.group(2)),
        })
    text = _CONNECTOR_SEMI.sub(_semi_replacement, text)

    for m in _THIS_IS.finditer(text):
        conjunction = m.group(0).split()[-1].lower().rstrip()
        changelog.append({
            "step": "Step 6: Merge",
            "detail": f"'This is {conjunction}' bridge removed",
            "para": None,
        })
    text = _THIS_IS.sub(_this_is_replacement, text)

    text = re.sub(r" {2,}", " ", text)

    quoted = guard(text)
    guarded_text, qmap = quoted["text"], quoted["qmap"]
    state = {**state, "text": guarded_text, "qmap": qmap}
    current = word_count(state["text"], state["qmap"])
    state["counts"]["step6_merge"] = current
    state["log"].append({
        "step": "Step 6: Merge",
        "detail": f"{len(changelog)} deterministic merge(s) -> {current} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state
