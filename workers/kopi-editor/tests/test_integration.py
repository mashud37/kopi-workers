"""End-to-end wiring for the local edit pass (Step 10), without Ollama or a model.

`edit_paragraph` is stubbed with a deterministic word-dropper and `_cosine_sim`
is forced to 1.0, so the real candidate selection (every eligible paragraph),
the compression/citation/numeric guards, and the apply logic all run.
"""
import sys
import types

import pytest

np = pytest.importorskip("numpy")  # hard dependency of step_concision

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


def _word_dropper(paragraph, **kwargs) -> str:
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


def _make_state(text: str) -> dict:
    guarded, qmap = guard(text)
    return {
        "text": guarded,
        "qmap": qmap,
        "target": word_count(guarded, qmap),  # soft guide only
        "counts": {"step1": word_count(guarded, qmap)},
        "log": [],
    }


def _stub_llm(monkeypatch, editor):
    monkeypatch.setattr("kopi.llm.edit_paragraph", editor)
    monkeypatch.setattr(step_concision, "_cosine_sim", lambda a, b: 1.0)
    fake_ollama = types.ModuleType("ollama")
    fake_ollama.list = lambda: {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)


def test_edits_every_paragraph_and_preserves_guards(monkeypatch):
    _stub_llm(monkeypatch, _word_dropper)

    text = _build_document()
    state = _make_state(text)
    original = state["counts"]["step1"]

    state = step_concision.run(state)

    # Every eligible paragraph was processed and the document got shorter.
    assert state["llm_stats"]["para"] == 20
    assert state["llm_stats"]["accepted"] > 0
    assert state["counts"]["step10"] < original

    # Guards preserved every citation and numeric token in the edited text.
    edited = unguard(state["text"], state["qmap"])
    assert "(Smith, 2020)" in edited
    for num in step_concision._get_numerics(text):
        assert num in edited, f"numeric {num} lost"


def test_rejected_edit_keeps_original(monkeypatch):
    # An editor that bloats the paragraph well past the expansion cap -> rejected.
    # (A small length increase is now allowed: plain-language editing need not
    # shorten. Only clear padding/gutting is rejected.)
    _stub_llm(monkeypatch, lambda p, **k: (p + " ") * 3)
    state = _make_state(_build_document())
    state = step_concision.run(state)
    assert state["llm_stats"]["accepted"] == 0
    assert state["llm_stats"]["rejected"] == 20


def test_small_expansion_is_accepted(monkeypatch):
    # Plain-language rephrase that adds a couple of words must NOT be rejected.
    _stub_llm(monkeypatch, lambda p, **k: p + " here too")
    state = _make_state(_build_document())
    state = step_concision.run(state)
    assert state["llm_stats"]["accepted"] == 20


def test_over_compression_triggers_softer_retry(monkeypatch):
    # First attempt guts the paragraph (over-compressed -> rejected); the
    # corrective retry (which carries a "lightly" note) makes a gentle edit that
    # passes. The goal is an *edited* paragraph, not a silent fallback to original.
    def editor(p, **k):
        instr = k.get("instructions") or []
        if any("at least" in i for i in instr):   # the numeric corrective note
            return " ".join(p.split()[:-3])        # gentle: drop 3 words -> accepted
        return " ".join(p.split()[:3])             # gut it -> over-compressed

    _stub_llm(monkeypatch, editor)
    state = _make_state(_build_document())
    state = step_concision.run(state)
    assert state["llm_stats"]["accepted"] == 20
    assert state["llm_stats"]["rejected"] == 0


def test_corrective_instruction_maps_reasons():
    ci = step_concision._corrective_instruction
    note = ci("over-compressed (142 -> 60 words)", "word " * 142)
    assert "at least" in note and "86" in note  # concrete floor: int(142*0.6)+1
    assert "(2012)" in ci("citation set changed: {'(2012)'}", "Smith (2012) said it.")
    assert ci("meaning drift (cosine similarity 0.70 < 0.85)", "text")
    assert ci("empty edit", "text") is None  # not recoverable by a softer prompt
