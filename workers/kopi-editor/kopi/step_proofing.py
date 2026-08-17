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
# Characters of the document handed to spaCy for proper-noun detection.
_PARSE_LIMIT = 100000
_AUTO_RULE_ISSUE_TYPES = frozenset(["misspelling", "typographical"])


def _in_quotes(start: int, end: int, ranges) -> bool:
    return any(qs <= start < qe or qs < end <= qe for qs, qe in ranges)


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


def _open_tool(lang: str) -> dict:
    """A LanguageTool for this language, or under `error` why one could not start."""
    try:
        import language_tool_python
    except ImportError:
        return {"tool": None, "error": "skipped: language-tool-python not installed"}

    try:
        code = "en-GB" if lang == "british" else "en-US"
        tool = language_tool_python.LanguageTool(code)
    except Exception as error:
        return {"tool": None, "error": f"skipped, LanguageTool unavailable: {error}"}

    for rule_id in _BLOCKED_RULES:
        try:
            tool.disable_rules([rule_id])
        except Exception:
            pass
    return {"tool": tool, "error": None}


def _propn_ranges(restored: str) -> list:
    """Character ranges of the proper nouns, so no correction rewrites a name.

    Falls back to an empty list when spaCy is unavailable; `_is_propn` then reads
    capitalisation instead.
    """
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(restored[:_PARSE_LIMIT])
        return [(t.idx, t.idx + len(t.text)) for t in doc if t.pos_ == "PROPN"]
    except Exception:
        return []


def _sort_matches(matches, restored: str, qranges: list, propn_ranges: list) -> dict:
    """Split LanguageTool's matches into what to correct and what to flag.

    A match is corrected only when it offers exactly one replacement in an
    auto-apply category and does not sit on a proper noun. Everything else with a
    suggestion is grouped by (rule, surface form) so a repeat becomes one review
    item rather than one line per occurrence.
    """
    corrections = []
    flag_groups: dict[tuple, dict] = {}
    for m in matches:
        if m.rule_id in _BLOCKED_RULES:
            continue
        start, end = m.offset, m.offset + m.error_length
        if _in_quotes(start, end, qranges):
            continue
        original = restored[start:end]
        automatic = m.category in _AUTO_CATEGORIES or m.rule_issue_type in _AUTO_RULE_ISSUE_TYPES
        if len(m.replacements) == 1 and automatic and not _is_propn(
                start, end, restored, propn_ranges):
            corrections.append((start, end, m.replacements[0], m.rule_id, original))
        elif m.replacements:
            key = (m.rule_id, original.lower())
            if key not in flag_groups:
                flag_groups[key] = {
                    "rule_id": m.rule_id,
                    "original": original,
                    "replacements": m.replacements[:3],
                    "message": m.message,
                    "paras": [],
                }
            flag_groups[key]["paras"].append(_para_num(restored, start))
    return {"corrections": corrections, "flag_groups": flag_groups}


def _apply_corrections(restored: str, corrections: list) -> dict:
    """Apply every correction back to front, so earlier offsets stay valid."""
    changelog = []
    applied = 0
    for start, end, repl, rule_id, original in sorted(corrections, key=lambda x: -x[0]):
        restored = restored[:start] + repl + restored[end:]
        changelog.append({
            "step": "Step 9: Proofing",
            "detail": f"'{original}' -> '{repl}' (rule: {rule_id})",
            "para": _para_num(restored, start),
        })
        applied += 1
    return {"text": restored, "changelog": changelog, "applied": applied}


def _flag_lines(flag_groups: dict) -> dict:
    """Turn each flagged group into a log line, and a review item when it repeats."""
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
                "step": "Step 9: Proofing",
                "detail": (
                    f"[review] '{grp['original']}' -> {repls_str} "
                    f"({count}x: {paras_str}) - rule: {rule_id}"
                ),
                "para": None,
            })
        else:
            flagged_log.append({
                "step": "Step 9: Proofing",
                "detail": (
                    f"[flag] {grp['message']} - '{grp['original']}' -> {repls_str} "
                    f"({paras_str}, rule: {rule_id})"
                ),
                "para": grp["paras"][0] if grp["paras"] else None,
            })
    return {"review_items": review_items, "flagged_log": flagged_log}


def _record_outcome(state: dict, corrected: dict, flags: dict) -> dict:
    """Store the proofed text, the review items and the change log into the run state."""
    quoted = guard(corrected["text"])
    guarded, qmap = quoted["text"], quoted["qmap"]
    review_items = flags["review_items"]
    state = {
        **state,
        "text": guarded,
        "qmap": qmap,
        "review_items": state.get("review_items", []) + review_items,
    }
    current = word_count(guarded, qmap)
    state["counts"]["step9"] = current
    state["log"].append({
        "step": "Step 9: Proofing",
        "detail": (
            f"{corrected['applied']} correction(s) applied, "
            f"{len(flags['flagged_log'])} flagged "
            f"({len(review_items)} repeated) -> {current} words"
        ),
        "para": None,
    })
    state["log"].extend(corrected["changelog"])
    state["log"].extend(flags["flagged_log"])
    return state


def run(state: dict) -> dict:
    if state.get("rules_only"):
        return state

    opened = _open_tool(state["lang"])
    if opened["tool"] is None:
        state["log"].append({
            "step": "Step 9: Proofing",
            "detail": opened["error"],
            "para": None,
        })
        return state
    tool = opened["tool"]

    restored = unguard(state["text"], state["qmap"])
    qranges = [(m.start(), m.end()) for m in _QUOTE_RE.finditer(restored)]
    propn_ranges = _propn_ranges(restored)

    try:
        matches = tool.check(restored)
    except Exception as e:
        state["log"].append({
            "step": "Step 9: Proofing",
            "detail": f"check failed: {e}",
            "para": None,
        })
        return state
    finally:
        try:
            tool.close()
        except Exception:
            pass

    sorted_matches = _sort_matches(matches, restored, qranges, propn_ranges)
    corrected = _apply_corrections(restored, sorted_matches["corrections"])
    flags = _flag_lines(sorted_matches["flag_groups"])
    return _record_outcome(state, corrected, flags)
