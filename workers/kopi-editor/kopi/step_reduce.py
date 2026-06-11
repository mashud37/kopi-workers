import re
from kopi.data_padding_tails import TAIL_PATTERNS
from kopi.quote_guard import guard, unguard, word_count


def _para_num(text: str, phrase: str) -> str:
    search = phrase.split("\n")[0].strip()[:60].lower()
    for i, para in enumerate(text.split("\n\n"), 1):
        if search in para.lower():
            return f"P{i}"
    return "P?"


def _fix_text(text: str) -> str:
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r" ([.!?,;:])", r"\1", text)
    text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text.strip()


def _apply_filler(text: str, phrase: str, replacement: str) -> str:
    repl_str = (replacement + " ") if replacement else ""

    # Sentence-initial match: keep the boundary punctuation+space, drop filler+comma
    def _sent_repl(m):
        return m.group(1) + repl_str

    combined = re.compile(
        r"([.!?]\s+)\b" + re.escape(phrase) + r"\b[,]?\s*"
        r"|"
        r"\b" + re.escape(phrase) + r"\b[,]?\s*",
        re.IGNORECASE,
    )
    return _fix_text(combined.sub(lambda m: _sent_repl(m) if m.group(1) else repl_str, text))


def _apply_sentence_removal(text: str, sentence: str) -> str:
    escaped = re.escape(sentence.strip())
    result = re.compile(r"\s*" + escaped + r"[ \t]*").sub(" ", text)
    return re.sub(r" {2,}", " ", result).strip()


def _apply_tails(text: str, target: int, current: int, changelog: list) -> tuple[str, int]:
    for pattern, replacement in TAIL_PATTERNS:
        if current <= target:
            break
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            saved = current - len(new_text.split())
            if saved > 0:
                changelog.append({
                    "step": "Step 7 — Reduce",
                    "detail": f"padding tail removed (~{saved} words)",
                    "para": None,
                })
                text = new_text
                current = len(text.split())
    return text, current


def run(state: dict) -> dict:
    restored = unguard(state["text"], state["qmap"])
    target = state["target"]
    current = len(restored.split())
    changelog = []

    if current <= target:
        state["counts"]["step7"] = current
        state["log"].append({
            "step": "Step 7 — Reduce",
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
        para_ref = _para_num(restored, phrase)
        restored = candidate
        current = candidate_count
        applied_fillers += 1
        repl_display = f"'{replacement}'" if replacement else "(deleted)"
        changelog.append({
            "step": "Step 7 — Reduce",
            "detail": f"filler removed: '{phrase}' -> {repl_display}",
            "para": para_ref,
        })

    restored, current = _apply_tails(restored, target, current, changelog)

    state["text"], state["qmap"] = guard(restored)
    state["counts"]["step7"] = current
    state["log"].append({
        "step": "Step 7 — Reduce",
        "detail": f"{applied_fillers} filler(s), tails applied -> {current} words",
        "para": None,
        "items": [],
    })
    state["log"].extend(changelog)
    return state
