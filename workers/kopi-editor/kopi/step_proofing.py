import re
from kopi.quote_guard import guard, unguard, word_count
from kopi.quote_guard import _PATTERN as _QUOTE_RE

_BLOCKED_RULES = frozenset([
    "WHITESPACE_RULE",
    "COMMA_PARENTHESIS_WHITESPACE",
    "SENTENCE_WHITESPACE",
    "EN_QUOTES",
    "DASH_RULE",
    "WORD_CONTAINS_UNDERSCORE",
    # Oxford -ise spelling: disabled by default; enable with --oxford-spelling
    "OXFORD_SPELLING_Z_NOT_S",
    "OXFORD_SPELLING_NOUNS",
    "OXFORD_SPELLING_ZE",
])

_AUTO_CATEGORIES = frozenset(["TYPOS", "SPELLING"])
_AUTO_RULE_ISSUE_TYPES = frozenset(["misspelling", "typographical"])


def _quote_ranges(text: str):
    return [(m.start(), m.end()) for m in _QUOTE_RE.finditer(text)]


def _in_quotes(start: int, end: int, ranges) -> bool:
    return any(qs <= start < qe or qs < end <= qe for qs, qe in ranges)


def _build_propn_ranges(text: str) -> list:
    """Return character ranges for PROPN tokens via spaCy, with a capitalisation fallback."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:100000])
        ranges = [(t.idx, t.idx + len(t.text)) for t in doc if t.pos_ == "PROPN"]
    except Exception:
        ranges = []
    return ranges


def _is_propn(start: int, end: int, text: str, propn_ranges: list) -> bool:
    """True if span overlaps a PROPN token or is capitalised but not sentence-initial."""
    if any(ps <= start < pe for ps, pe in propn_ranges):
        return True
    matched = text[start:end] if start < len(text) else ""
    if matched and matched[0].isupper():
        before = text[:start].rstrip()
        if before and before[-1] not in ".!?":
            return True
    return False


def _para_num(text: str, offset: int) -> str:
    paras = text.split("\n\n")
    pos = 0
    for i, para in enumerate(paras, 1):
        if pos <= offset < pos + len(para) + 2:
            return f"P{i}"
        pos += len(para) + 2
    return "P?"


def run(state: dict) -> dict:
    if state.get("rules_only"):
        return state

    try:
        import language_tool_python
    except ImportError:
        state["log"].append({
            "step": "Step 9 — Proofing",
            "detail": "skipped — language-tool-python not installed",
            "para": None,
        })
        return state

    try:
        lang_code = "en-GB" if state["lang"] == "british" else "en-US"
        tool = language_tool_python.LanguageTool(lang_code)
        for rule_id in _BLOCKED_RULES:
            try:
                tool.disable_rules([rule_id])
            except Exception:
                pass
    except Exception as e:
        state["log"].append({
            "step": "Step 9 — Proofing",
            "detail": f"skipped — LanguageTool unavailable: {e}",
            "para": None,
        })
        return state

    restored = unguard(state["text"], state["qmap"])
    qranges = _quote_ranges(restored)
    propn_ranges = _build_propn_ranges(restored)
    changelog = []

    try:
        matches = tool.check(restored)
    except Exception as e:
        state["log"].append({
            "step": "Step 9 — Proofing",
            "detail": f"check failed: {e}",
            "para": None,
        })
        return state
    finally:
        try:
            tool.close()
        except Exception:
            pass

    corrections = []
    flag_groups: dict[tuple, dict] = {}

    for m in matches:
        if m.rule_id in _BLOCKED_RULES:
            continue
        start, end = m.offset, m.offset + m.error_length
        if _in_quotes(start, end, qranges):
            continue
        original = restored[start:end]
        if len(m.replacements) == 1 and (
            m.category in _AUTO_CATEGORIES or m.rule_issue_type in _AUTO_RULE_ISSUE_TYPES
        ) and not _is_propn(start, end, restored, propn_ranges):
            corrections.append((start, end, m.replacements[0], m.rule_id, original))
        elif m.replacements:
            key = (m.rule_id, original.lower())
            para_ref = _para_num(restored, start)
            if key not in flag_groups:
                flag_groups[key] = {
                    "rule_id": m.rule_id,
                    "original": original,
                    "replacements": m.replacements[:3],
                    "message": m.message,
                    "paras": [],
                }
            flag_groups[key]["paras"].append(para_ref)

    applied = 0
    for start, end, repl, rule_id, original in sorted(corrections, key=lambda x: -x[0]):
        restored = restored[:start] + repl + restored[end:]
        para_ref = _para_num(restored, start)
        changelog.append({
            "step": "Step 9 — Proofing",
            "detail": f"'{original}' -> '{repl}' (rule: {rule_id})",
            "para": para_ref,
        })
        applied += 1

    review_items = []
    flagged_log = []
    for (rule_id, _), grp in flag_groups.items():
        count = len(grp["paras"])
        paras_str = ", ".join(grp["paras"])
        repls_str = " / ".join(f"'{r}'" for r in grp["replacements"])
        if count > 1:
            review_items.append({
                "rule_id": grp["rule_id"],
                "original": grp["original"],
                "replacements": grp["replacements"],
                "message": grp["message"],
                "count": count,
                "paras": grp["paras"],
            })
            flagged_log.append({
                "step": "Step 9 — Proofing",
                "detail": (
                    f"[review] '{grp['original']}' -> {repls_str} "
                    f"({count}x: {paras_str}) - rule: {rule_id}"
                ),
                "para": None,
            })
        else:
            flagged_log.append({
                "step": "Step 9 — Proofing",
                "detail": (
                    f"[flag] {grp['message']} - '{grp['original']}' -> {repls_str} "
                    f"({paras_str}, rule: {rule_id})"
                ),
                "para": grp["paras"][0] if grp["paras"] else None,
            })

    state["text"], state["qmap"] = guard(restored)
    current = word_count(state["text"], state["qmap"])
    state["counts"]["step9"] = current
    state["review_items"] = state.get("review_items", []) + review_items
    state["log"].append({
        "step": "Step 9 — Proofing",
        "detail": (
            f"{applied} correction(s) applied, "
            f"{len(flagged_log)} flagged "
            f"({len(review_items)} repeated) -> {current} words"
        ),
        "para": None,
    })
    state["log"].extend(changelog)
    state["log"].extend(flagged_log)
    return state
