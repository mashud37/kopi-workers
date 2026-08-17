import re
from functools import lru_cache

from kopi.quote_guard import guard, unguard, word_count
from kopi.quote_guard import _PATTERN as _QUOTE_RE
 
_ENABLED_CATEGORIES = frozenset([
    "redundancy",
    "needless_variants",
    "weasel_words",
    "cliches",
    "industrial_language",
])
_AUTO_CATEGORIES = frozenset(["redundancy", "needless_variants"])
 
 
def _para_num(text, offset):
    paras = text.split("\n\n")
    pos = 0
    for i, para in enumerate(paras, 1):
        if pos <= offset < pos + len(para) + 2:
            return f"P{i}"
        pos += len(para) + 2
    return "P?"
 
 
@lru_cache(maxsize=1)
def _register_checks() -> None:
    """Load proselint's check registry, once per process."""
    from proselint.tools import CheckRegistry
    from proselint.checks import __register__

    CheckRegistry().register_many(__register__)


def _run_proselint(text):
    from proselint.tools import LintFile
    from proselint import config as cfg_mod

    _register_checks()
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
 
 
def _hit_para(offset: int, para_offsets: list, num_paras: int) -> int:
    for i, (s, e) in enumerate(para_offsets):
        if s <= offset <= e:
            return i
    return num_paras - 1


def _index_paragraphs(text: str) -> dict:
    # Per-paragraph hit counts (all enabled categories, before any edit): a
    # fat-index input for Step 10 routing. Aligned to the \n\n split of the
    # text as it stands now; the consumer guards on length, so a later split
    # change degrades gracefully rather than misattributing hits.
    paras = text.split("\n\n")
    para_offsets = []
    pos = 0
    for para in paras:
        para_offsets.append((pos, pos + len(para)))
        pos += len(para) + 2
    return {"offsets": para_offsets, "count": len(paras)}


def _select_corrections(errors: list, qranges: list, para_index: dict, restored: str) -> dict:
    # Only a single-replacement hit in an auto-apply category is corrected;
    # every other hit is left as a flag for a human to decide.
    to_apply = []
    flagged = []
    para_hits = [0] * para_index["count"]
    for err in errors:
        check = err["check"]
        category = check.split(".")[0]
        if category not in _ENABLED_CATEGORIES:
            continue
        start, end = err["start"], err["end"]
        if end <= start:
            continue
        if any(qs <= start < qe or qs < end <= qe for qs, qe in qranges):
            continue
        para_hits[_hit_para(start, para_index["offsets"], para_index["count"])] += 1

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
                "step": "Step 3: Proselint",
                "detail": f"[flag] {err['message']} ({check})",
                "para": _para_num(restored, start),
                "source": f"Proselint:{check}",
            })
    return {"to_apply": to_apply, "flagged": flagged, "para_hits": para_hits}


def _dedupe_overlaps(to_apply: list, restored: str) -> dict:
    ordered = sorted(to_apply, key=lambda x: (x[0], -(x[1] - x[0])))
    kept = []
    last_end = -1
    skipped = []
    for span in ordered:
        start, end, repl, check, original = span
        if start < last_end:
            skipped.append({
                "step": "Step 3: Proselint",
                "detail": f"[skip overlap] '{original}' -> '{repl}' ({check})",
                "para": _para_num(restored, start),
                "source": f"Proselint:{check}",
            })
            continue
        kept.append(span)
        last_end = end
    return {"kept": kept, "skipped": skipped}


def _apply_corrections(to_apply: list, restored: str) -> dict:
    changelog = []
    for start, end, repl, check, original in sorted(to_apply, key=lambda x: x[0]):
        changelog.append({
            "step": "Step 3: Proselint",
            "detail": f"'{original}' -> '{repl}'",
            "para": _para_num(restored, start),
            "source": f"Proselint:{check}",
        })
    for start, end, repl, check, _ in sorted(to_apply, key=lambda x: -x[0]):
        restored = restored[:start] + repl + restored[end:]
    restored = re.sub(r" {2,}", " ", restored).strip()
    return {"text": restored, "changelog": changelog}


def run(state: dict) -> dict:
    if state.get("rules_only"):
        return state

    restored = unguard(state["text"], state["qmap"])
    qranges = [(m.start(), m.end()) for m in _QUOTE_RE.finditer(restored)]

    try:
        errors = _run_proselint(restored)
    except ImportError:
        state["log"].append({
            "step": "Step 3: Proselint",
            "detail": "skipped: proselint not installed (pip install proselint)",
            "para": None,
        })
        return state
    except Exception as e:
        state["log"].append({
            "step": "Step 3: Proselint",
            "detail": f"skipped, {type(e).__name__}: {e}",
            "para": None,
        })
        return state

    para_index = _index_paragraphs(restored)
    selection = _select_corrections(errors, qranges, para_index, restored)
    overlaps = _dedupe_overlaps(selection["to_apply"], restored)
    correction = _apply_corrections(overlaps["kept"], restored)

    quoted = guard(correction["text"])
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {
        **state,
        "text": guarded,
        "qmap": qmap,
        "proselint_para_hits": selection["para_hits"],
    }
    current = word_count(guarded, qmap)
    state["counts"]["step3_proselint"] = current
    state["log"].append({
        "step": "Step 3: Proselint",
        "detail": (
            f"{len(overlaps['kept'])} correction(s), {len(selection['flagged'])} flag(s) -> {current} words"
        ),
        "para": None,
    })
    state["log"].extend(correction["changelog"])
    state["log"].extend(selection["flagged"])
    state["log"].extend(overlaps["skipped"])
    return state
