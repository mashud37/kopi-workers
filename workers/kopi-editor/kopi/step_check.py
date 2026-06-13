import re
from kopi.quote_guard import unguard, word_count


def _mean_dep_depth(text, nlp):
    try:
        doc = nlp(text[:50000])
        depths = []
        for tok in doc:
            d, cur = 0, tok
            while cur.head != cur and d < 1000:  # bounded — guard against a cyclic parse
                cur = cur.head
                d += 1
            depths.append(d)
        return sum(depths) / len(depths) if depths else None
    except Exception:
        return None


def _para_label(text: str, para: str) -> str:
    search = para.strip()[:60].lower()
    for i, p in enumerate(text.split("\n\n"), 1):
        if search in p.lower():
            return f"P{i}"
    return "P?"


def run(state: dict) -> dict:
    restored = unguard(state["text"], state["qmap"])
    current = len(restored.split())
    target = state["target"]
    state["counts"]["final"] = current

    flags = []
    gap = current - target
    if gap > 0:
        flags.append(f"still {gap} words over target")
    elif gap < 0:
        flags.append(f"note: {abs(gap)} words below target")

    for char, threshold in [(";", 4), ("—", 5), (":", 6)]:
        count = restored.count(char)
        if count > threshold:
            flags.append(f"'{char}' used {count} times — consider reducing")

    try:
        import textstat

        ease_before = state.get("readability_before")
        ease_after = textstat.flesch_reading_ease(restored)
        state["readability_after"] = ease_after
        if ease_before is not None:
            delta = ease_after - ease_before
            direction = "easier" if delta > 0 else "harder"
            flags.append(f"readability: Flesch {ease_after:.1f} (delta {delta:+.1f}, {direction} to read)")

        paragraphs = [p.strip() for p in restored.split("\n\n") if len(p.split()) >= 50]
        hard_paras = []
        for para in paragraphs:
            score = textstat.flesch_reading_ease(para)
            if score < 30:
                label = _para_label(restored, para)
                hard_paras.append((score, label, para[:60]))
        hard_paras.sort(key=lambda x: x[0])
        for score, label, snippet in hard_paras[:3]:
            flags.append(f"hard paragraph {label} (Flesch {score:.0f}): \"{snippet}...\"")

    except Exception:
        pass

    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        dep_before = state.get("dep_depth_before")
        dep_after = _mean_dep_depth(restored, nlp)
        if dep_before is not None and dep_after is not None:
            dep_delta = dep_after - dep_before
            direction = "flatter" if dep_delta < 0 else "deeper"
            pct = abs(dep_delta / dep_before * 100) if dep_before else 0
            flags.append(
                f"mean dep depth: {dep_before:.2f} -> {dep_after:.2f} "
                f"({dep_delta:+.2f}, {pct:.0f}% {direction})"
            )
        doc = nlp(restored[:50000])
        terms = {}
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PERSON", "GPE", "NORP", "WORK_OF_ART"):
                base = ent.text.lower()
                terms.setdefault(base, set()).add(ent.text)
        for base, variants in terms.items():
            if len(variants) > 1:
                flags.append(f"inconsistent term: {', '.join(sorted(variants))}")
    except Exception:
        pass

    for pair in state.get("redundant_pairs", [])[:5]:
        snippet = pair["remove"][:70]
        label = _para_label(restored, pair["remove"][:40])
        flags.append(
            f"redundant sentence flagged for author review ({label}, sim {pair['similarity']:.2f}): "
            f"\"{snippet}{'...' if len(pair['remove']) > 70 else ''}\""
        )

    llm = state.get("llm_stats", {})
    if llm:
        flags.append(
            f"LLM: {llm.get('para', 0)} paragraphs processed, "
            f"{llm.get('accepted', 0)} accepted, {llm.get('rejected', 0)} rejected"
        )

    state["flags"] = flags
    state["log"].append({
        "step": "Step 12 — Final check",
        "detail": f"{current} words (target: {target})" + (f" | {len(flags)} flag(s)" if flags else ""),
        "para": None,
        "items": flags,
    })
    return state
