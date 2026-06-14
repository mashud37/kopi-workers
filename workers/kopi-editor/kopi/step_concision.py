import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from kopi.quote_guard import guard, unguard, word_count
from kopi.progress import LLMProgress

_CITATION_RE = re.compile(
    r"\("
    r"(?:[A-Z][\w-]+(?:\s+(?:and|&|et\s+al\.?))?\s*[A-Z]?[\w-]*,?\s*)?"
    r"(?:\d{4}[a-z]?|199X|202X|REF)"
    r"(?:,\s*pp?\.?\s*\d+(?:[-–]\d+)?)?"
    r"\)",
    re.IGNORECASE,
)
_MIN_PARA_WORDS = 40
# Max fraction a paragraph may shrink before we reject the edit as too aggressive.
# qwen2.5:7b tends to cut ~50%, so a 0.40 cap rejected everything; the cosine
# Reject an edit that cut more than this fraction — plain-language editing tightens
# wording, it does not summarise, so a paragraph cut in half has lost content. The
# softer-retry re-prompts an over-compressed paragraph for a lighter edit. Tune via
# KOPI_MAX_COMPRESSION (e.g. 0.30 stricter, 0.50 looser).
try:
    _MAX_COMPRESSION = float(os.environ.get("KOPI_MAX_COMPRESSION", "0.40"))
except ValueError:
    _MAX_COMPRESSION = 0.40
# Plain-language editing need not shorten a paragraph — a clearer rephrase (active
# voice, plain words, split sentences) can be the same length or a touch longer.
# We only reject a paragraph the model clearly *padded out* beyond this factor.
_MAX_EXPANSION = 1.10
_MIN_COSINE_SIM = 0.85

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    return _embedding_model


def _cosine_sim(a: str, b: str) -> float:
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


def _accept_edit(original: str, edited: str) -> tuple[bool, str]:
    orig_words = len(original.split())
    edit_words = len(edited.split())

    if not edited.strip():
        return False, "empty edit"

    # Plain-language editing is about clarity, not only length: an edit that keeps
    # (or barely changes) the word count is fine. Reject only the two failure
    # modes — the model padded the paragraph out, or gutted it.
    if edit_words > orig_words * _MAX_EXPANSION:
        return False, f"expanded ({orig_words} -> {edit_words} words)"

    if edit_words < orig_words * (1 - _MAX_COMPRESSION):
        return False, f"over-compressed ({orig_words} -> {edit_words} words)"

    orig_cites = set(_get_citations(original))
    edit_cites = set(_get_citations(edited))
    if orig_cites != edit_cites:
        changed = orig_cites ^ edit_cites
        return False, f"citation set changed: {changed}"

    for num in _get_numerics(original):
        if num not in edited:
            return False, f"numeric lost: {num}"

    sim = _cosine_sim(original, edited)
    if sim < _MIN_COSINE_SIM:
        return False, f"meaning drift (cosine similarity {sim:.2f} < {_MIN_COSINE_SIM})"

    return True, "ok"


def guard_result(original: str, edited: str) -> dict:
    """Run the acceptance guard on one LLM edit and package the outcome.

    Shared by the local pass and the cloud client so the accept/reject rules
    live in one place. On rejection the original is kept unchanged.
    """
    ok, reason = _accept_edit(original, edited)
    return {
        "edited": edited if ok else original,
        "accepted": ok,
        "reason": reason,
        "saved": (len(original.split()) - len(edited.split())) if ok else 0,
    }


def _corrective_instruction(reason: str, text: str) -> str | None:
    """A targeted directive for a *recoverable* guard rejection, or None.

    Re-prompts a paragraph once when the first edit failed in a way the model can
    fix. Small models follow concrete numbers far better than vague guidance, so
    the over-compression note states the exact word floor and the citations to keep.
    """
    if reason.startswith("over-compressed"):
        orig = len(text.split())
        floor = int(orig * (1 - _MAX_COMPRESSION)) + 1
        return (f"Your previous edit cut too much. The paragraph has {orig} words; your edit MUST "
                f"keep at least {floor} words. Do NOT delete whole sentences or drop any point — "
                f"only tighten wording within each sentence.")
    if reason.startswith("expanded"):
        return "Be more concise: do not add words; the edit must not be longer than the original."
    if "citation" in reason:
        cites = _get_citations(text)
        keep = ", ".join(sorted(set(cites))) or "(Author, Year)"
        return (f"Your previous edit altered a citation. Reproduce these EXACTLY and unchanged, and "
                f"add or drop none: {keep}.")
    if "numeric" in reason:
        return "Keep every number exactly as written — do not change or drop any figure."
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


def edit_with_retry(edit_fn, text: str, instructions) -> dict:
    """Edit + guard; on a recoverable rejection, retry **once** with a corrective note.

    ``edit_fn(text, instructions) -> edited_text``. The aim is an accepted edit, so
    rather than silently keep the original on (say) over-compression, we re-prompt
    the paragraph once asking for a softer/targeted edit. Each raw edit is cleaned
    (`_clean_edit`) before guarding so length/meaning checks see the real text.
    Returns a guard_result dict; if the retry also fails, the original is kept and
    the reason records both attempts.
    """
    res = guard_result(text, _clean_edit(edit_fn(text, instructions)))
    if res["accepted"]:
        return res
    note = _corrective_instruction(res["reason"], text)
    if not note:
        return res
    retry = guard_result(text, _clean_edit(edit_fn(text, [note] + list(instructions or []))))
    if retry["accepted"]:
        retry["reason"] = "ok (softer retry)"
        return retry
    res["reason"] = f"{res['reason']}; softer retry also rejected ({retry['reason']})"
    return res


# Paragraphs are independent jobs, so they can be edited concurrently. Default
# is conservative (Ollama serialises on CPU); raise KOPI_LLM_WORKERS when the
# backend can serve requests in parallel (GPU, or OLLAMA_NUM_PARALLEL > 1).
def _worker_count(n: int) -> int:
    try:
        workers = int(os.environ.get("KOPI_LLM_WORKERS", "2"))
    except ValueError:
        workers = 2
    return max(1, min(workers, n))

def get_candidates(state: dict) -> list[dict]:
    """Return **every** paragraph eligible for a plain-language edit, each carrying
    its deterministic ``instructions`` from :mod:`kopi.diagnose`.

    Eligible = at least ``_MIN_PARA_WORDS`` words, not a (block) quotation, and not
    already edited in a prior pass. The whole document is edited — no fat-index
    routing, no per-paragraph word budget, no candidate cap — so the output reads
    consistently. Each candidate's ``instructions`` (e.g. "remove hedges and
    padding", the always-on plain-language directive) steer the model so a
    cheaper-than-Opus model edits well; the word target is a soft guide only.
    """
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    already = set(state.get("llm_edited_indices", set()))

    diag = state.get("diagnosis") or {}
    by_index = {p["index"]: p for p in diag.get("paragraphs", [])}

    candidates = []
    for i, para in enumerate(paragraphs):
        if i in already or len(para.split()) < _MIN_PARA_WORDS:
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
            "routing_reason": "plain-language edit",
        })
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
                "step": "Step 10 — Concision",
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
                "step": "Step 10 — Concision",
                "detail": f"rejected — {result.get('reason', 'guard')} (kept original)",
                "para": f"P{idx + 1}",
            })

    restored = "\n\n".join(paragraphs)
    state["text"], state["qmap"] = guard(restored)
    state["llm_edited_indices"] = edited_indices
    final_count = word_count(state["text"], state["qmap"])
    state["counts"]["step10"] = final_count
    state["llm_stats"] = {"para": len(results), "accepted": accepted, "rejected": rejected}
    state["log"].append({
        "step": "Step 10 — Concision",
        "detail": f"{len(results)} paragraph(s) processed: {accepted} accepted, {rejected} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state


def run(state: dict) -> dict:
    """Local Ollama path: plain-language-edit every eligible paragraph in parallel.

    Each paragraph is sent with its deterministic ``instructions`` from
    :mod:`kopi.diagnose`. The acceptance guard (`_accept_edit`) protects meaning;
    rejected edits keep the original. No target gating — the whole document is
    edited for plain language regardless of word count.
    """
    try:
        from kopi.llm import edit_paragraph, DEFAULT_MODEL
        import ollama
        ollama.list()
    except ImportError:
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": "skipped — ollama package not installed",
            "para": None,
        })
        return state
    except Exception as e:
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": f"skipped — Ollama not running: {e}",
            "para": None,
        })
        return state

    restored = unguard(state["text"], state["qmap"])
    changelog = []
    accepted = 0
    rejected = 0

    paragraphs = restored.split("\n\n")
    candidates = get_candidates(state)
    edited_indices = set(state.get("llm_edited_indices", set()))
    para_count = len(candidates)

    if not candidates:
        state["counts"]["step10"] = word_count(state["text"], state["qmap"])
        state["llm_stats"] = {"para": 0, "accepted": 0, "rejected": 0}
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": "no paragraphs qualified for editing",
            "para": None,
        })
        return state

    workers = _worker_count(para_count)
    print(
        f"  {para_count} paragraph(s) queued for editing "
        f"(model: {DEFAULT_MODEL}, {workers} worker{'s' if workers > 1 else ''})."
    )

    # Pre-load the shared embedding model so concurrent acceptance checks don't
    # race to initialise it.
    try:
        _get_model()
    except Exception:
        pass

    def _edit_one(cand: dict) -> dict:
        """Edit + guard a single paragraph (with one corrective retry). Pure w.r.t.
        shared state — results are applied later in deterministic index order."""
        idx = cand["index"]
        para = paragraphs[idx]
        lang = state.get("lang", "british")
        try:
            res = edit_with_retry(
                lambda t, instr: edit_paragraph(t, instructions=instr, lang=lang),
                para, cand.get("instructions"),
            )
        except Exception as e:
            return {"cand": cand, "para": para, "error": str(e)}
        return {"cand": cand, "para": para, "edited": res["edited"],
                "ok": res["accepted"], "reason": res["reason"]}

    progress = LLMProgress(para_count)

    def _track(result: dict) -> dict:
        if result.get("error") or not result.get("ok"):
            progress.advance(0, accepted=False)
        else:
            cut = len(result["para"].split()) - len(result["edited"].split())
            progress.advance(cut, accepted=True)
        return result

    results = []
    if workers == 1:
        for cand in candidates:
            results.append(_track(_edit_one(cand)))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_edit_one, cand) for cand in candidates]
            for future in as_completed(futures):
                results.append(_track(future.result()))
    progress.finish()

    # Apply in document order so the change log and applied edits are
    # deterministic regardless of which worker finished first.
    results.sort(key=lambda r: r["cand"]["index"])
    for result in results:
        cand = result["cand"]
        idx = cand["index"]
        para = result["para"]
        para_ref = f"P{idx + 1}"

        if result.get("error"):
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"LLM error: {result['error']}",
                "para": para_ref,
            })
            continue

        edited = result["edited"]
        ok = result["ok"]
        reason = result["reason"]
        orig_wc = len(para.split())
        edit_wc = len(edited.split())
        if ok:
            saved = orig_wc - edit_wc
            accepted += 1
            paragraphs[idx] = edited
            edited_indices.add(idx)
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"accepted (~{saved} words saved)",
                "para": para_ref,
                "items": [
                    f"original -> \"{para[:100]}{'...' if len(para) > 100 else ''}\"",
                    f"edited   -> \"{edited[:100]}{'...' if len(edited) > 100 else ''}\"",
                ],
            })
        else:
            rejected += 1
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"rejected — {reason}",
                "para": para_ref,
            })

    restored = "\n\n".join(paragraphs)
    state["text"], state["qmap"] = guard(restored)
    state["llm_edited_indices"] = edited_indices
    final_count = word_count(state["text"], state["qmap"])
    state["counts"]["step10"] = final_count
    state["llm_stats"] = {"para": para_count, "accepted": accepted, "rejected": rejected}
    state["log"].append({
        "step": "Step 10 — Concision",
        "detail": f"{para_count} paragraphs processed: {accepted} accepted, {rejected} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(changelog)
    return state
