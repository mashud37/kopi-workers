"""End-to-end routing + guard wiring for Step 10, without Ollama or a model.

`edit_paragraph` is stubbed with a deterministic word-dropper and `_cosine_sim`
is forced to 1.0, so the real candidate selection, the 40%/citation/numeric
guards, and the apply/second-pass logic all run. Asserts the routed reduction
meets >= 70% of target on a ~1,500-word fixture with a 200-word target.
"""
import sys
import types

import pytest

np = pytest.importorskip("numpy")  # hard dependency of step_concision

from kopi import step_concision
from kopi.quote_guard import guard, word_count


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
        # Keep a citation and a number in some paragraphs to exercise the guards.
        cite = " (Smith, 2020)" if i % 3 == 0 else ""
        num = f" approximately {40 + i} cases" if i % 4 == 0 else ""
        paras.append(f"Paragraph {i}: {filler}{cite}{num}. {filler} again here.")
    return "\n\n".join(paras)


def _word_dropper(paragraph: str, **kwargs) -> str:
    """Deterministically drop ~28% of long lowercase words; keep numbers/citations."""
    out = []
    eligible = 0
    for tok in paragraph.split():
        is_droppable = (
            tok.isalpha() and tok.islower() and len(tok) > 3
        )
        if is_droppable:
            keep = (eligible % 7) >= 2  # drop 2 of every 7 -> ~28%
            eligible += 1
            if not keep:
                continue
        out.append(tok)
    return " ".join(out)


def _make_state(text: str, reduction: int) -> dict:
    guarded, qmap = guard(text)
    original = word_count(guarded, qmap)
    return {
        "text": guarded,
        "qmap": qmap,
        "target": original - reduction,
        "counts": {"step1": original},
        "log": [],
    }


def _stub_llm(monkeypatch, editor):
    """Stub the LLM, the embedding guard, the parser, and ollama availability.

    Forcing _load_nlp -> None exercises the routing/guard/apply wiring via the
    deterministic fallback selector (the spaCy fat-index path is covered by the
    signals/routing unit tests, and spaCy cold-load is unreliable in CI).
    """
    monkeypatch.setattr("kopi.llm.edit_paragraph", editor)
    monkeypatch.setattr(step_concision, "_cosine_sim", lambda a, b: 1.0)
    monkeypatch.setattr(step_concision, "_load_nlp", lambda: None)
    fake_ollama = types.ModuleType("ollama")
    fake_ollama.list = lambda: {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)


def test_routing_meets_target(monkeypatch, tmp_path):
    monkeypatch.setenv("KOPI_CALIBRATION_LOG", str(tmp_path / "cal.jsonl"))
    _stub_llm(monkeypatch, _word_dropper)

    text = _build_document()
    reduction = 200
    state = _make_state(text, reduction)
    original = state["counts"]["step1"]

    state = step_concision.run(state)

    final = state["counts"]["step10"]
    removed = original - final
    assert removed >= 0.70 * reduction, f"only removed {removed} of target {reduction}"

    # Guards preserved every citation and numeric token in the edited text.
    from kopi.quote_guard import unguard
    edited = unguard(state["text"], state["qmap"])
    assert "(Smith, 2020)" in edited
    for num in step_concision._get_numerics(text):
        assert num in edited, f"numeric {num} lost"

    # Calibration log was written.
    assert (tmp_path / "cal.jsonl").exists()


def test_second_pass_triggers_when_short(monkeypatch, tmp_path):
    monkeypatch.setenv("KOPI_CALIBRATION_LOG", str(tmp_path / "cal.jsonl"))

    # A weak editor that barely trims, so the first pass undershoots.
    def _weak(paragraph, **kwargs):
        toks = paragraph.split()
        # drop a single long lowercase word if present
        for i, t in enumerate(toks):
            if t.isalpha() and t.islower() and len(t) > 5:
                return " ".join(toks[:i] + toks[i + 1:])
        return " ".join(toks[:-1])

    _stub_llm(monkeypatch, _weak)

    state = _make_state(_build_document(), 200)
    state = step_concision.run(state)
    # After one weak pass we should still be short -> a second pass is warranted.
    assert step_concision.needs_second_pass(state)
    # And a second run flags additional (new) paragraphs without error.
    before = dict(state["counts"])
    state = step_concision.run(state)
    assert state["counts"]["step10"] <= before["step10"]
