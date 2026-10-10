"""Test the edit pass end to end, with deterministic editors in place of the model and the similarity check forced to 1.0."""
import pytest

np = pytest.importorskip("numpy")  # hard dependency of step_concision

from backends import llm as model_calls
from kopi import step_concision
from kopi.quote_guard import guard, unguard, word_count


def _build_document() -> str:
    """~1,500 words of wordy lowercase prose across 20 distinct paragraphs."""
    filler = (
        "it is important to note that the present analysis clearly demonstrates "
        "that the underlying theoretical framework remains fundamentally relevant "
        "throughout the broader discussion concerning these particular interpretive "
        "questions that scholars have repeatedly examined within the existing literature"
    )
    paras = []
    for i in range(20):
        cite = " (Smith, 2020)" if i % 3 == 0 else ""
        num = f" approximately {40 + i} cases" if i % 4 == 0 else ""
        paras.append(f"Paragraph {i}: {filler}{cite}{num}. {filler} again here.")
    return "\n\n".join(paras)


def _word_dropper(paragraph, style=None) -> str:
    """Deterministically drop ~28% of long lowercase words; keep numbers/citations."""
    out = []
    eligible = 0
    for tok in paragraph.split():
        if tok.isalpha() and tok.islower() and len(tok) > 3:
            keep = (eligible % 7) >= 2
            eligible += 1
            if not keep:
                continue
        out.append(tok)
    return " ".join(out)


def _make_state(text: str, reduction: int = 0) -> dict:
    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    words = word_count(guarded, qmap)
    return {
        "text": guarded,
        "qmap": qmap,
        "target": words - reduction,
        "reduction": reduction,          # drives the editing intensity (kopi.intensity)
        "original_words": words,
        "counts": {"step1": words},
        "log": [],
    }


def _always_similar(a, b):
    return 1.0


class _StubAsk:
    """Stands in for backends.llm.ask, handing each paragraph to a deterministic editor."""

    def __init__(self, editor):
        self.editor = editor

    def __call__(self, session, text, instructions, style):
        return self.editor(text, {"instructions": instructions})


def _stub_session(backend):
    return {
        "backend": backend,
        "model": "stub",
        "base_url": "http://localhost:11434/v1",
        "lang": "british",
        "workers": 2,
        "tally": model_calls.Tally(),
    }


def _no_preload():
    return None


def _stub_llm(monkeypatch, editor):
    monkeypatch.setattr(model_calls, "ask", _StubAsk(editor))
    monkeypatch.setattr(model_calls, "open_session", _stub_session)
    monkeypatch.setattr(model_calls, "_preload_embedding_model", _no_preload)
    monkeypatch.setattr(step_concision, "_cosine_sim", _always_similar)


def test_edits_every_paragraph_and_preserves_guards(monkeypatch):
    _stub_llm(monkeypatch, _word_dropper)

    text = _build_document()
    # A large reduction request -> aggressive band, whose ceiling admits the
    # ~28% cuts the stub makes; the guards (citation/numeric/expansion) still run.
    quoted = guard(text)
    state = _make_state(text, reduction=word_count(quoted["text"], quoted["qmap"]))
    original = state["counts"]["step1"]

    state = model_calls.tighten(state, "openai-compatible")

    # Every eligible paragraph was processed and the document got shorter.
    assert state["llm_stats"]["para"] == 20
    assert state["llm_stats"]["accepted"] > 0
    assert state["counts"]["step10"] < original

    # Guards preserved every citation and numeric token in the edited text.
    edited = unguard(state["text"], state["qmap"])
    assert "(Smith, 2020)" in edited
    for num in step_concision._get_numerics(text):
        assert num in edited, f"numeric {num} lost"


def _bloat_editor(paragraph, style=None):
    return (paragraph + " ") * 3


def test_rejected_edit_keeps_original(monkeypatch):
    # An editor that bloats the paragraph well past the expansion cap -> rejected.
    # (A small length increase is now allowed: plain-language editing need not
    # shorten. Only clear padding/gutting is rejected.)
    _stub_llm(monkeypatch, _bloat_editor)
    state = _make_state(_build_document())
    state = model_calls.tighten(state, "openai-compatible")
    assert state["llm_stats"]["accepted"] == 0
    assert state["llm_stats"]["rejected"] == 20


def _small_expansion_editor(paragraph, style=None):
    return paragraph + " here too"


def test_small_expansion_is_accepted(monkeypatch):
    # Plain-language rephrase that adds a couple of words must NOT be rejected.
    _stub_llm(monkeypatch, _small_expansion_editor)
    state = _make_state(_build_document())
    state = model_calls.tighten(state, "openai-compatible")
    assert state["llm_stats"]["accepted"] == 20


def _over_compression_editor(paragraph, style=None):
    # First attempt guts the paragraph (over-compressed -> rejected); the
    # corrective retry (which carries a "lightly" note) makes a gentle edit that
    # passes. The goal is an *edited* paragraph, not a silent fallback to original.
    instructions = (style or {}).get("instructions") or []
    if any("at least" in note for note in instructions):   # the numeric corrective note
        return " ".join(paragraph.split()[:-3])             # gentle: drop 3 words -> accepted
    return " ".join(paragraph.split()[:3])                  # gut it -> over-compressed


def test_over_compression_triggers_softer_retry(monkeypatch):
    _stub_llm(monkeypatch, _over_compression_editor)
    state = _make_state(_build_document())
    state = model_calls.tighten(state, "openai-compatible")
    assert state["llm_stats"]["accepted"] == 20
    assert state["llm_stats"]["rejected"] == 0


def test_no_reduction_is_clarity_and_rejects_deep_cuts(monkeypatch):
    # The safeguard for editing WITHOUT a reduction target: a model that cuts a big
    # share of every paragraph is rejected (original kept), so a manuscript nobody
    # asked to shorten is not quietly gutted. The retry can't rescue a deterministic
    # over-cutter, so every paragraph falls back to its original.
    _stub_llm(monkeypatch, _word_dropper)
    state = _make_state(_build_document())  # reduction defaults to 0 -> clarity
    original = state["counts"]["step1"]
    state = model_calls.tighten(state, "openai-compatible")
    assert state["llm_stats"]["accepted"] == 0
    assert state["llm_stats"]["rejected"] == 20
    assert state["counts"]["step10"] == original  # document unchanged


def test_corrective_instruction_maps_reasons():
    ci = step_concision._corrective_instruction
    note = ci("over-compressed (142 -> 60 words)", "word " * 142)
    assert "at least" in note and "86" in note  # concrete floor: int(142*0.6)+1
    assert "(2012)" in ci("citation set changed: {'(2012)'}", "Smith (2012) said it.")
    assert ci("meaning drift (cosine similarity 0.70 < 0.85)", "text")
    assert ci("empty edit", "text") is None  # not recoverable by a softer prompt
