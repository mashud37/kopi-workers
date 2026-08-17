import re
from kopi.data_fillers import PHRASE_REPLACEMENTS
from kopi.data_padding_tails import TAIL_PATTERNS
from kopi.quote_guard import unguard


def run(state: dict) -> dict:
    restored = unguard(state["text"], state["qmap"])
    found = []
    total_phrase_savings = 0

    for phrase, replacement in sorted(PHRASE_REPLACEMENTS.items(), key=lambda x: -len(x[0])):
        phrase_pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        count = len(phrase_pattern.findall(restored))
        if count:
            pw = len(phrase.split())
            rw = len(replacement.split()) if replacement else 0
            savings = count * (pw - rw)
            found.append({"phrase": phrase, "replacement": replacement, "count": count, "savings": savings})
            total_phrase_savings += savings

    tail_count = 0
    total_tail_savings = 0
    for pattern, _ in TAIL_PATTERNS:
        matches = pattern.findall(restored)
        if matches:
            tail_count += len(matches)
            total_tail_savings += sum(len(m.split()) for m in matches)

    state = {**state, "fillers": found, "tail_savings_estimate": total_tail_savings}
    state["counts"]["step2_estimate"] = total_phrase_savings + total_tail_savings
    state["log"].append({
        "step": "Step 2: Filler scan",
        "detail": (
            f"{len(found)} phrase type(s) (~{total_phrase_savings} words), "
            f"{tail_count} tail match(es) (~{total_tail_savings} words)"
        ),
        "para": None,
        "items": [
            f"'{f['phrase']}' x{f['count']} (~{f['savings']} words) -> "
            + (f"'{f['replacement']}'" if f["replacement"] else "(delete)")
            for f in found
        ],
    })
    return state
