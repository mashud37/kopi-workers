import re
from kopi.quote_guard import guard, unguard, word_count
from kopi.quote_guard import _PATTERN as _QUOTE_RE
 
_ENABLED_CATEGORIES = frozenset([
    "redundancy", "needless_variants", "weasel_words",
    "cliches", "industrial_language",
])
_AUTO_CATEGORIES = frozenset(["redundancy", "needless_variants"])
 
 
def _quote_ranges(text):
    return [(m.start(), m.end()) for m in _QUOTE_RE.finditer(text)]
 
 
def _in_quotes(start, end, ranges):
    return any(qs <= start < qe or qs < end <= qe for qs, qe in ranges)
 
 
def _para_num(text, offset):
    paras = text.split("\n\n")
    pos = 0
    for i, para in enumerate(paras, 1):
        if pos <= offset < pos + len(para) + 2:
            return f"P{i}"
        pos += len(para) + 2
    return "P?"
 
 
_REGISTRY_READY = False
 
 
def _ensure_registry():
    global _REGISTRY_READY
    if _REGISTRY_READY:
        return
    from proselint.tools import CheckRegistry
    from proselint.checks import __register__
    CheckRegistry().register_many(__register__)
    _REGISTRY_READY = True
 
 
def _run_proselint(text):
    from proselint.tools import LintFile
    from proselint import config as cfg_mod
 
    _ensure_registry()
 
    lint_file = LintFile(source="kopi-buffer.txt", content=text)
    results = lint_file.lint(cfg_mod.DEFAULT)
 
    out = []
    text_len = len(text)
    for r in results:
        cr = r.check_result
        start = max(0, cr.span[0] - 1)
        end = max(start, cr.span[1] - 1)
        start = min(start, text_len)
        end = min(end, text_len)
        out.append({
            "check": cr.check_path,
            "start": start,
            "end": end,
            "replacements": cr.replacements,  # str | None
            "message": cr.message,
        })
    return out
 
 
def run(state: dict) -> dict:
    if state.get("rules_only"):
        return state
 
    restored = unguard(state["text"], state["qmap"])
    qranges = _quote_ranges(restored)
 
    try:
        errors = _run_proselint(restored)
    except ImportError:
        state["log"].append({
            "step": "Step 3 — Proselint",
            "detail": "skipped — proselint not installed (pip install proselint)",
            "para": None,
        })
        return state
    except Exception as e:
        state["log"].append({
            "step": "Step 3 — Proselint",
            "detail": f"skipped — {type(e).__name__}: {e}",
            "para": None,
        })
        return state
 
    # Per-paragraph hit counts (all enabled categories, before any edit) — a
    # fat-index input for Step 10 routing. Aligned to the \n\n split of the
    # text as it stands now; the consumer guards on length, so a later split
    # change degrades gracefully rather than misattributing hits.
    paras = restored.split("\n\n")
    para_offsets = []
    pos = 0
    for para in paras:
        para_offsets.append((pos, pos + len(para)))
        pos += len(para) + 2
    para_hits = [0] * len(paras)

    def _hit_para(offset: int) -> int:
        for i, (s, e) in enumerate(para_offsets):
            if s <= offset <= e:
                return i
        return len(paras) - 1

    to_apply = []
    flagged = []
    for err in errors:
        check = err["check"]
        category = check.split(".")[0]
        if category not in _ENABLED_CATEGORIES:
            continue
        start, end = err["start"], err["end"]
        if end <= start:
            continue
        if _in_quotes(start, end, qranges):
            continue
        para_hits[_hit_para(start)] += 1
 
        repl_raw = err["replacements"]
        if isinstance(repl_raw, str):
            repls = [repl_raw] if repl_raw else []
        elif isinstance(repl_raw, list):
            repls = [r for r in repl_raw if isinstance(r, str) and r]
        else:
            repls = []
 
        if len(repls) == 1 and category in _AUTO_CATEGORIES:
            to_apply.append((start, end, repls[0], check, restored[start:end]))
        else:
            flagged.append({
                "step": "Step 3 — Proselint",
                "detail": f"[flag] {err['message']} ({check})",
                "para": _para_num(restored, start),
                "source": f"Proselint:{check}",
            })

    to_apply.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    deduped = []
    last_end = -1
    skipped_overlaps = []
    for span in to_apply:
        start, end, repl, check, original = span
        if start < last_end:
            skipped_overlaps.append({
                "step": "Step 3 — Proselint",
                "detail": f"[skip overlap] '{original}' -> '{repl}' ({check})",
                "para": _para_num(restored, start),
                "source": f"Proselint:{check}",
            })
            continue
        deduped.append(span)
        last_end = end
    to_apply = deduped
 
    changelog = []
    for start, end, repl, check, original in sorted(to_apply, key=lambda x: x[0]):
        changelog.append({
            "step": "Step 3 — Proselint",
            "detail": f"'{original}' -> '{repl}'",
            "para": _para_num(restored, start),
            "source": f"Proselint:{check}",
        })
    for start, end, repl, check, _ in sorted(to_apply, key=lambda x: -x[0]):
        restored = restored[:start] + repl + restored[end:]
    restored = re.sub(r" {2,}", " ", restored).strip()
 
    state["text"], state["qmap"] = guard(restored)
    state["proselint_para_hits"] = para_hits
    current = word_count(state["text"], state["qmap"])
    state["counts"]["step3_proselint"] = current
    state["log"].append({
        "step": "Step 3 — Proselint",
        "detail": (
            f"{len(to_apply)} correction(s), {len(flagged)} flag(s) -> {current} words"
        ),
        "para": None,
    })
    state["log"].extend(changelog)
    state["log"].extend(flagged)
    state["log"].extend(skipped_overlaps)
    return state
