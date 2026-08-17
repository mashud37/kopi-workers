import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from kopi.citations import CITATION_RE as _CITATION_RE, restore_casing
from kopi.quote_guard import guard, unguard, word_count
from kopi.progress import LLMProgress

_MIN_PARA_WORDS = 40
# Max fraction a paragraph may shrink before we reject the edit as too aggressive.
# qwen2.5:7b tends to cut ~50%, so a 0.40 cap rejected everything; the cosine
# Reject an edit that cut more than this fraction: plain-language editing tightens
# wording, it does not summarise, so a paragraph cut in half has lost content. The
# softer-retry re-prompts an over-compressed paragraph for a lighter edit. Tune via
# KOPI_MAX_COMPRESSION (e.g. 0.30 stricter, 0.50 looser).
try:
    _MAX_COMPRESSION = float(os.environ.get("KOPI_MAX_COMPRESSION", "0.40"))
except ValueError:
    _MAX_COMPRESSION = 0.40
# Absolute slack on the compression ceiling: a paragraph may always shed up to this
# many words even when that exceeds ``max_compression``. The fractional ceiling alone
# rejects a 3-word trim of a 48-word paragraph in a 6% clarity pass: the failure mode
# that gutted half the edits. A clarity edit that loses <= this many words is a light
# tightening, not a summary; ~10 paragraphs at this slack is ~100 words, manageable.
# In the firm/aggressive bands the fractional allowance dominates, so this never binds.
try:
    _COMPRESSION_SLACK_WORDS = int(os.environ.get("KOPI_COMPRESSION_SLACK", "10"))
except ValueError:
    _COMPRESSION_SLACK_WORDS = 10
# Plain-language editing need not shorten a paragraph: a clearer rephrase (active
# voice, plain words, split sentences) can be the same length or a touch longer.
# We only reject a paragraph the model clearly *padded out* beyond this factor.
_MAX_EXPANSION = 1.10
_MIN_COSINE_SIM = 0.85
# When a reduction was requested, do one top-up pass if the realised cut falls
# below this fraction of the ask (e.g. asked -600, got < 480).
_TOPUP_TOLERANCE = 0.80

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    return _embedding_model


def _cosine_sim(a: str, b: str) -> float:  # lint-style: ignore FN004
    model = _get_model()
    embs = model.encode([a, b], show_progress_bar=False)
    na, nb = embs[0], embs[1]
    denom = np.linalg.norm(na) * np.linalg.norm(nb)
    return float(np.dot(na, nb) / denom) if denom > 1e-10 else 0.0


def _get_numerics(text: str) -> list:
    return re.findall(r"\b\d[\d.,]*\b", text)


def _get_citations(text: str) -> list:
    return _CITATION_RE.findall(text)


def _para_num(text: str, para: str) -> str:
    search = para.split("\n")[0].strip()[:60].lower()
    for i, p in enumerate(text.split("\n\n"), 1):
        if search in p.lower():
            return f"P{i}"
    return "P?"


def _compression_floor(orig_words: int, max_compression: float) -> float:
    """Fewest words an edit may keep before it counts as over-compressed.

    The looser of the fractional ceiling and a small absolute slack
    (``_COMPRESSION_SLACK_WORDS``), so a light tightening of a short paragraph is not
    rejected just because a handful of words exceeds the percentage on a ~100-word
    paragraph. Shared by the guard and the corrective retry so both agree.
    """
    allowed_cut = max(orig_words * max_compression, _COMPRESSION_SLACK_WORDS)
    return orig_words - allowed_cut


def _accept_edit(original: str, edited: str, max_compression: float = _MAX_COMPRESSION) -> dict:
    """Whether one LLM edit may stand, and the reason under `accepted`/`reason`."""
    orig_words = len(original.split())
    edit_words = len(edited.split())

    if not edited.strip():
        return {"accepted": False, "reason": "empty edit"}

    # ``max_compression`` is set per run from the requested reduction (kopi.intensity):
    # tight in a clarity pass so an over-eager model can't gut a paragraph nobody
    # asked to shorten, wide when a major cut was requested. Reject only the two
    # failure modes: the model padded the paragraph out, or cut past the ceiling.
    if edit_words > orig_words * _MAX_EXPANSION:
        return {"accepted": False,
                "reason": f"expanded ({orig_words} -> {edit_words} words)"}

    if edit_words < _compression_floor(orig_words, max_compression):
        return {"accepted": False,
                "reason": f"over-compressed ({orig_words} -> {edit_words} words)"}

    orig_cites = set(_get_citations(original))
    edit_cites = set(_get_citations(edited))
    if orig_cites != edit_cites:
        changed = orig_cites ^ edit_cites
        return {"accepted": False, "reason": f"citation set changed: {changed}"}

    for num in _get_numerics(original):
        if num not in edited:
            return {"accepted": False, "reason": f"numeric lost: {num}"}

    sim = _cosine_sim(original, edited)
    if sim < _MIN_COSINE_SIM:
        return {"accepted": False,
                "reason": f"meaning drift (cosine similarity {sim:.2f} < {_MIN_COSINE_SIM})"}

    return {"accepted": True, "reason": "ok"}


def guard_result(original: str, edited: str, max_compression: float = _MAX_COMPRESSION) -> dict:
    """Run the acceptance guard on one LLM edit and package the outcome.

    Shared by the local pass and the cloud client so the accept/reject rules
    live in one place. On rejection the original is kept unchanged.
    ``max_compression`` is the run's per-paragraph compression ceiling.
    """
    verdict = _accept_edit(original, edited, max_compression)
    accepted = verdict["accepted"]
    return {
        "edited": edited if accepted else original,
        "accepted": accepted,
        "reason": verdict["reason"],
        "saved": (len(original.split()) - len(edited.split())) if accepted else 0,
    }


def _corrective_instruction(reason: str, text: str, max_compression: float = _MAX_COMPRESSION) -> str | None:
    """A targeted directive for a *recoverable* guard rejection, or None.

    Re-prompts a paragraph once when the first edit failed in a way the model can
    fix. Small models follow concrete numbers far better than vague guidance, so
    the over-compression note states the exact word floor and the citations to keep.
    The floor tracks the run's compression ceiling (tight in a clarity pass).
    """
    if reason.startswith("over-compressed"):
        orig = len(text.split())
        floor = math.ceil(_compression_floor(orig, max_compression))
        return (f"Your previous edit cut too much. The paragraph has {orig} words; your edit MUST "
                f"keep at least {floor} words. Do NOT delete whole sentences or drop any point: "
                f"only tighten wording within each sentence.")
    if reason.startswith("expanded"):
        return "Be more concise: do not add words; the edit must not be longer than the original."
    if "citation" in reason:
        cites = _get_citations(text)
        keep = ", ".join(sorted(set(cites))) or "(Author, Year)"
        return (f"Your previous edit altered a citation. Reproduce these EXACTLY and unchanged, and "
                f"add or drop none: {keep}.")
    if "numeric" in reason:
        return "Keep every number exactly as written: do not change or drop any figure."
    if "meaning" in reason or "cosine" in reason:
        return "Stay very close to the original meaning; edit only for plain language, do not rephrase the argument."
    return None


# Editorial meta-comments the model sometimes appends despite the prompt, e.g.
# "(Note: the original sentence was split for clarity.)". Matched by the
# tell-tale editorial phrasing inside a parenthetical, so genuine content
# parentheticals are left alone.
_META_PAREN = re.compile(
    r"\s*\([^)]*\b(?:note:|original sentence|for clarity|split into|rephrased|"
    r"shortened|edited for|combined into|merged|revised for)\b[^)]*\)\s*",
    re.IGNORECASE,
)
# Qwen3 (and other reasoning models) may wrap a chain-of-thought in <think>…</think>
# before the answer. We disable thinking in the request, but strip any block as a
# belt-and-braces guard so reasoning never reaches the edited text.
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _clean_edit(edited: str) -> str:
    """Normalise a raw model edit before guarding/applying.

    Fixes model quirks deterministically (prompt rules reduce but don't eliminate
    them on smaller models): a stray reasoning ``<think>`` block, the paragraph
    returned across several lines after a sentence is removed (collapsed back to
    one paragraph), and an appended editorial note about the model's own changes.
    """
    edited = _THINK.sub(" ", edited)                 # drop any reasoning trace
    edited = re.sub(r"\s*[\r\n]+\s*", " ", edited)   # keep it ONE paragraph
    edited = _META_PAREN.sub(" ", edited)            # drop self-referential notes
    return re.sub(r"\s{2,}", " ", edited).strip()


def edit_with_retry(edit_fn, text: str, instructions, max_compression: float = _MAX_COMPRESSION) -> dict:
    """Edit + guard; on a recoverable rejection, retry **once** with a corrective note.

    ``edit_fn(text, instructions) -> edited_text``. The aim is an accepted edit, so
    rather than silently keep the original on (say) over-compression, we re-prompt
    the paragraph once asking for a softer/targeted edit. Each raw edit is cleaned
    (`_clean_edit`) before guarding so length/meaning checks see the real text.
    ``max_compression`` is the run's per-paragraph ceiling (from the requested
    reduction). Returns a guard_result dict; if the retry also fails, the original
    is kept and the reason records both attempts.
    """
    res = guard_result(text, restore_casing(text, _clean_edit(edit_fn(text, instructions))), max_compression)
    if res["accepted"]:
        return res
    note = _corrective_instruction(res["reason"], text, max_compression)
    if not note:
        return res
    retry = guard_result(text, restore_casing(text, _clean_edit(edit_fn(text, [note] + list(instructions or [])))), max_compression)
    if retry["accepted"]:
        retry["reason"] = "ok (softer retry)"
        return retry
    res["reason"] = f"{res['reason']}; softer retry also rejected ({retry['reason']})"
    return res


def get_candidates(state: dict) -> list[dict]:
    """Return **every** paragraph eligible for a plain-language edit, each carrying
    its deterministic ``instructions`` from :mod:`kopi.diagnose` and the run's
    editing intensity.

    Eligible = at least ``_MIN_PARA_WORDS`` words, not a (block) quotation, and not
    already edited in a prior pass. The whole document is edited so the output reads
    consistently, but each candidate now carries the intensity derived from the
    requested reduction (:mod:`kopi.intensity`): ``mode`` (selects the prompt
    stance), ``max_compression`` (the guard ceiling), and a soft per-paragraph
    ``floor``. With no reduction requested this is a clarity pass: the model is
    told to barely change length and the guard rejects deep cuts.
    """
    from kopi.intensity import paragraph_floor
    from kopi import intensity
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    already = set(state.get("llm_edited_indices", set()))
    # The run's editing intensity, from the requested reduction and document size.
    original = (
        state.get("original_words")
        or (state.get("counts") or {}).get("step1")
        or len(restored.split())
    )
    plan = intensity.plan(state.get("reduction") or 0, original)

    diag = state.get("diagnosis") or {}
    by_index = {p["index"]: p for p in diag.get("paragraphs", [])}

    candidates = []
    for i, para in enumerate(paragraphs):
        words = len(para.split())
        if i in already or words < _MIN_PARA_WORDS:
            continue
        info = by_index.get(i)
        if info is not None:
            if info.get("is_quote") or info.get("is_heading"):
                continue
            instructions = info.get("instructions", [])
        else:
            # No diagnosis (spaCy unavailable): skip quotes cheaply, no notes.
            from kopi import signals
            if signals._is_quote_para(para):
                continue
            instructions = []
        candidates.append({
            "index": i,
            "text": para,
            "instructions": instructions,
            "mode": plan["mode"],
            "max_compression": plan["max_compression"],
            "floor": paragraph_floor(words, plan["frac"]),
            "routing_reason": "plain-language edit",
        })
    return candidates


def topup_candidates(state: dict) -> list[dict]:
    """Paragraphs to re-edit once when pass 1 under-delivered on the reduction.

    Returns ``[]`` when no reduction was requested or the realised cut already
    covers most of the ask (``_TOPUP_TOLERANCE``). Otherwise it re-plans the
    *remaining* reduction over the wordiest still-reducible paragraphs and pushes
    each toward the band's ceiling: we are now explicitly chasing a target the
    first pass missed. Bounded by design: only as many paragraphs as the remaining
    reduction needs, so it approaches the target without overshooting.
    """
    from kopi import intensity
    reduction = state.get("reduction") or 0
    if not reduction:
        return []
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    original = state.get("original_words") or len(restored.split())
    realised = original - len(restored.split())
    if realised >= reduction * _TOPUP_TOLERANCE:
        return []
    remaining = reduction - realised

    diag = state.get("diagnosis") or {}
    by_index = {p["index"]: p for p in diag.get("paragraphs", [])}
    pool = []
    for i, para in enumerate(paragraphs):
        words = len(para.split())
        if words < _MIN_PARA_WORDS:
            continue
        info = by_index.get(i)
        if info is not None:
            if info.get("is_quote") or info.get("is_heading"):
                continue
            instructions = info.get("instructions", [])
        else:
            from kopi import signals
            if signals._is_quote_para(para):
                continue
            instructions = []
        pool.append((i, para, words, instructions))

    plan = intensity.plan(remaining, sum(w for _, _, w, _ in pool) or 1)
    pool.sort(key=lambda t: -t[2])  # wordiest first: concentrate the remaining cut
    candidates = []
    budget = remaining
    for i, para, words, instructions in pool:
        if budget <= 0:
            break
        floor = intensity.paragraph_floor(words, plan["max_compression"])
        candidates.append({
            "index": i,
            "text": para,
            "instructions": instructions,
            "mode": plan["mode"],
            "max_compression": plan["max_compression"],
            "floor": floor,
            "routing_reason": "top-up (target shortfall)",
        })
        budget -= (words - floor)
    return candidates


def apply_results(state: dict, results: list[dict]) -> dict:
    """Apply LLM editing results (from local or cloud) to state."""
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    accepted = 0
    rejected = 0
    changelog = []
    edited_indices = set(state.get("llm_edited_indices", set()))

    for result in results:
        idx = result["index"]
        if idx >= len(paragraphs):
            continue
        original = paragraphs[idx]
        edited = result.get("edited", original)
        orig_wc = len(original.split())
        edit_wc = len(edited.split())
        is_ok = bool(result.get("accepted"))
        if is_ok:
            saved = orig_wc - edit_wc
            paragraphs[idx] = edited
            accepted += 1
            edited_indices.add(idx)
            changelog.append({
                "step": "Step 10: Concision",
                "detail": f"accepted (~{saved} words saved) [{result.get('routing_reason', 'edited')}]",
                "para": f"P{idx + 1}",
                "items": [
                    f"original -> \"{original[:100]}{'...' if len(original) > 100 else ''}\"",
                    f"edited   -> \"{edited[:100]}{'...' if len(edited) > 100 else ''}\"",
                ],
            })
        else:
            rejected += 1
            changelog.append({
                "step": "Step 10: Concision",
                "detail": f"rejected: {result.get('reason', 'guard')} (kept original)",
                "para": f"P{idx + 1}",
            })

    quoted = guard("\n\n".join(paragraphs))
    guarded, qmap = quoted["text"], quoted["qmap"]
    final_count = word_count(guarded, qmap)
    state = {
        **state,
        "text": guarded,
        "qmap": qmap,
        "llm_edited_indices": edited_indices,
        "llm_stats": _bumped_stats(state, len(results), accepted, rejected),
    }
    state["counts"]["step10"] = final_count
    state["log"].append({
        "step": "Step 10: Concision",
        "detail": f"{len(results)} paragraph(s) processed: {accepted} accepted, {rejected} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state


def _bumped_stats(state: dict, para: int, accepted: int, rejected: int) -> dict:
    """Accumulate LLM stats across passes (pass 1 + any top-up) instead of
    overwriting, so the summary reflects the whole edit, not just the last pass."""
    prev = state.get("llm_stats") or {}
    return {
        "para": prev.get("para", 0) + para,
        "accepted": prev.get("accepted", 0) + accepted,
        "rejected": prev.get("rejected", 0) + rejected,
    }


def _record_outcome(state: dict, applied: dict, para_count: int) -> dict:
    """Store the edited text, the counts and the change log back into the run state."""
    quoted = guard("\n\n".join(applied["paragraphs"]))
    guarded, qmap = quoted["text"], quoted["qmap"]
    final_count = word_count(guarded, qmap)
    state = {
        **state,
        "text": guarded,
        "qmap": qmap,
        "llm_edited_indices": applied["edited"],
        "llm_stats": _bumped_stats(state, para_count, applied["accepted"], applied["rejected"]),
    }
    state["counts"]["step10"] = final_count
    state["log"].append({
        "step": "Step 10: Concision",
        "detail": f"{para_count} paragraphs processed: {applied['accepted']} accepted, "
                  f"{applied['rejected']} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(applied["changelog"])
    return state


def _backend_unavailable() -> str | None:
    """Why the local model cannot be reached, or None when it can."""
    try:
        import ollama
        ollama.list()
    except ImportError:
        return "skipped: ollama package not installed"
    except Exception as error:
        return f"skipped, Ollama not running: {error}"
    return None


def _worker_count(para_count: int) -> int:
    """How many paragraphs to edit at once.

    Conservative by default because Ollama serialises on CPU. Raise
    KOPI_LLM_WORKERS when the backend can serve requests in parallel, on a GPU
    or with OLLAMA_NUM_PARALLEL above one.
    """
    try:
        wanted = int(os.environ.get("KOPI_LLM_WORKERS", "2"))
    except ValueError:
        wanted = 2
    return max(1, min(wanted, para_count))


def _preload_embedding_model() -> None:
    """Load the shared embedding model before the workers race to initialise it."""
    from kopi.progress import StepSpinner

    sp = StepSpinner("loading embedding model")
    sp.start()
    try:
        _get_model()
    except Exception:
        pass
    finally:
        sp.done()


class _ModelCall:
    """One paragraph's call settings, held so a corrective retry asks on the same terms."""

    def __init__(self, lang: str, mode: str, floor) -> None:
        self.lang = lang
        self.mode = mode
        self.floor = floor

    def edit(self, text: str, instructions):
        from kopi.llm import edit_paragraph

        return edit_paragraph(text, {
            "instructions": instructions,
            "lang": self.lang,
            "mode": self.mode,
            "floor": self.floor,
        })


def _edit_one(cand: dict, paragraphs: list[str], lang: str) -> dict:
    """Edit and guard a single paragraph, with one corrective retry.

    Touches nothing shared, so paragraphs can be edited concurrently; the results
    are applied later in document order.
    """
    para = paragraphs[cand["index"]]
    caller = _ModelCall(lang, cand.get("mode", "firm"), cand.get("floor"))
    try:
        res = edit_with_retry(caller.edit, para, cand.get("instructions"),
                              cand.get("max_compression", _MAX_COMPRESSION))
    except Exception as error:
        return {"cand": cand, "para": para, "error": str(error)}
    return {
        "cand": cand,
        "para": para,
        "edited": res["edited"],
        "ok": res["accepted"],
        "reason": res["reason"],
    }


def _track(progress, result: dict) -> dict:
    """Report one finished paragraph to the live progress line."""
    if result.get("error") or not result.get("ok"):
        progress.advance(0, accepted=False)
    else:
        cut = len(result["para"].split()) - len(result["edited"].split())
        progress.advance(cut, accepted=True)
    return result


def _run_edits(candidates: list[dict], paragraphs: list[str], lang: str, workers: int) -> list[dict]:
    """Edit every candidate paragraph, on one thread or several."""
    progress = LLMProgress(len(candidates))
    results = []
    if workers == 1:
        for cand in candidates:
            results.append(_track(progress, _edit_one(cand, paragraphs, lang)))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_edit_one, cand, paragraphs, lang) for cand in candidates]
            for future in as_completed(futures):
                results.append(_track(progress, future.result()))
    progress.finish()
    return results


def _apply_edits(paragraphs: list[str], results: list[dict]) -> dict:
    """Fold the finished edits back into the paragraphs, in document order.

    Sorted by paragraph index first, so the change log and the applied text read
    the same however the workers happened to finish.
    """
    kept = list(paragraphs)
    changelog = []
    edited = set()
    accepted = 0
    rejected = 0
    for result in sorted(results, key=lambda one: one["cand"]["index"]):
        idx = result["cand"]["index"]
        para = result["para"]
        para_ref = f"P{idx + 1}"
        if result.get("error"):
            changelog.append({
                "step": "Step 10: Concision",
                "detail": f"LLM error: {result['error']}",
                "para": para_ref,
            })
            continue
        if not result["ok"]:
            rejected += 1
            changelog.append({
                "step": "Step 10: Concision",
                "detail": f"rejected: {result['reason']}",
                "para": para_ref,
            })
            continue
        saved = len(para.split()) - len(result["edited"].split())
        accepted += 1
        kept[idx] = result["edited"]
        edited.add(idx)
        changelog.append({
            "step": "Step 10: Concision",
            "detail": f"accepted (~{saved} words saved)",
            "para": para_ref,
            "items": [
                f"original -> \"{para[:100]}{'...' if len(para) > 100 else ''}\"",
                f"edited   -> \"{result['edited'][:100]}{'...' if len(result['edited']) > 100 else ''}\"",
            ],
        })
    return {
        "paragraphs": kept,
        "changelog": changelog,
        "edited": edited,
        "accepted": accepted,
        "rejected": rejected,
    }


def run(state: dict, candidates: list[dict] | None = None) -> dict:
    """Local Ollama path: edit every eligible paragraph in parallel at the run's
    intensity.

    Each candidate carries its ``instructions`` (from :mod:`kopi.diagnose`) and the
    intensity derived from the requested reduction: ``mode`` (prompt stance),
    ``max_compression`` (guard ceiling), and a soft ``floor``. The guard
    (`_accept_edit`) protects meaning and enforces the ceiling; rejected edits keep
    the original. Pass explicit ``candidates`` for a targeted top-up pass; otherwise
    every eligible paragraph is selected.
    """
    unavailable = _backend_unavailable()
    if unavailable:
        state["log"].append({
            "step": "Step 10: Concision",
            "detail": unavailable,
            "para": None,
        })
        return state
    from kopi.llm import DEFAULT_MODEL

    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    candidates = candidates if candidates is not None else get_candidates(state)
    edited_indices = set(state.get("llm_edited_indices", set()))
    para_count = len(candidates)

    if not candidates:
        state["counts"]["step10"] = word_count(state["text"], state["qmap"])
        state["log"].append({
            "step": "Step 10: Concision",
            "detail": "no paragraphs qualified for editing",
            "para": None,
        })
        return {**state, "llm_stats": _bumped_stats(state, 0, 0, 0)}

    workers = _worker_count(para_count)
    print(
        f"  {para_count} paragraph(s) queued for editing "
        f"(model: {DEFAULT_MODEL}, {workers} worker{'s' if workers > 1 else ''})."
    )
    _preload_embedding_model()

    results = _run_edits(candidates, paragraphs, state.get("lang", "british"), workers)
    applied = _apply_edits(paragraphs, results)
    applied["edited"] |= edited_indices
    return _record_outcome(state, applied, para_count)
