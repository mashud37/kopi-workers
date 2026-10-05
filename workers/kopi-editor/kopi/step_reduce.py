import re

from kopi.data_padding_tails import TAIL_PATTERNS
from kopi.quote_guard import guard, unguard


def _capitalize_after_sentence(match) -> str:
    return match.group(1) + match.group(2).upper()


def _apply_filler(text: str, phrase: str, replacement: str) -> str:
    repl_str = (replacement + " ") if replacement else ""

    # Sentence-initial match: keep the boundary punctuation+space, drop filler+comma
    combined = re.compile(
        r"([.!?]\s+)\b" + re.escape(phrase) + r"\b[,]?\s*"
        r"|"
        r"\b" + re.escape(phrase) + r"\b[,]?\s*",
        re.IGNORECASE,
    )
    changes = []
    for m in combined.finditer(text):
        if m.group(1):
            changes.append((m.start(), m.end(), m.group(1) + repl_str))
        else:
            changes.append((m.start(), m.end(), repl_str))
    fixed = text
    for start, end, repl in sorted(changes, key=lambda x: -x[0]):
        fixed = fixed[:start] + repl + fixed[end:]
    fixed = re.sub(r" {2,}", " ", fixed)
    fixed = re.sub(r" ([.!?,;:])", r"\1", fixed)
    fixed = re.sub(r"([.!?]\s+)([a-z])", _capitalize_after_sentence, fixed)
    if fixed and fixed[0].islower():
        fixed = fixed[0].upper() + fixed[1:]
    return fixed.strip()


def _apply_sentence_removal(text: str, sentence: str) -> str:
    escaped = re.escape(sentence.strip())
    result = re.compile(r"\s*" + escaped + r"[ \t]*").sub(" ", text)
    return re.sub(r" {2,}", " ", result).strip()


def _apply_tails(text: str, target: int, current: int, changelog: list) -> dict:
    for pattern, replacement in TAIL_PATTERNS:
        if current <= target:
            break
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            saved = current - len(new_text.split())
            if saved > 0:
                changelog.append({
                    "step": "Step 7: Reduce",
                    "detail": f"padding tail removed (~{saved} words)",
                    "para": None,
                })
                text = new_text
                current = len(text.split())
    return {"text": text, "current": current}


def run(state: dict) -> dict:
    restored = unguard(state["text"], state["qmap"])
    target = state["target"]
    current = len(restored.split())
    changelog = []

    if current <= target:
        state["counts"]["step7"] = current
        state["log"].append({
            "step": "Step 7: Reduce",
            "detail": f"already at or below target ({current} words)",
            "para": None,
        })
        return state

    applied_fillers = 0
    for filler in sorted(state["fillers"], key=lambda x: -x["savings"]):
        if current <= target:
            break
        phrase, replacement = filler["phrase"], filler["replacement"]
        if not re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE).search(restored):
            continue
        candidate = _apply_filler(restored, phrase, replacement)
        candidate_count = len(candidate.split())
        search = phrase.split("\n")[0].strip()[:60].lower()
        para_ref = "P?"
        for para_index, para in enumerate(restored.split("\n\n"), 1):
            if search in para.lower():
                para_ref = f"P{para_index}"
                break
        restored = candidate
        current = candidate_count
        applied_fillers += 1
        repl_display = f"'{replacement}'" if replacement else "(deleted)"
        changelog.append({
            "step": "Step 7: Reduce",
            "detail": f"filler removed: '{phrase}' -> {repl_display}",
            "para": para_ref,
        })

    tails_result = _apply_tails(restored, target, current, changelog)
    restored = tails_result["text"]
    current = tails_result["current"]

    quoted = guard(restored)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {**state, "text": guarded, "qmap": qmap}
    state["counts"]["step7"] = current
    state["log"].append({
        "step": "Step 7: Reduce",
        "detail": f"{applied_fillers} filler(s), tails applied -> {current} words",
        "para": None,
        "items": [],
    })
    state["log"].extend(changelog)
    return state
