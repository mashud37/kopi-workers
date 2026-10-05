"""get_candidates: every eligible paragraph is returned for a uniform
plain-language edit, each carrying its deterministic instructions."""
from kopi import step_concision
from kopi.quote_guard import guard, word_count


def _diag(paragraphs, instructions_for=None, quotes=()):
    """Build a minimal diagnosis dict aligned to the given paragraphs."""
    instructions_for = instructions_for or {}
    return {
        "paragraphs": [
            {
                "index": i,
                "words": len(p.split()),
                "is_quote": i in quotes,
                "tags": set(),
                "instructions": instructions_for.get(i, ["Plain language: cut every word that can be cut."]),
            }
            for i, p in enumerate(paragraphs)
        ]
    }


def test_returns_every_eligible_paragraph_with_instructions():
    paras = [f"Paragraph {i} " + "word " * 60 for i in range(8)]
    text = "\n\n".join(paras)
    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {
        "text": guarded,
        "qmap": qmap,
        "target": word_count(guarded, qmap) - 200,
        "diagnosis": _diag(paras),
    }

    cands = step_concision.get_candidates(state)
    assert len(cands) == 8
    for c in cands:
        assert set(c) >= {"index", "text", "instructions", "routing_reason"}
        assert c["routing_reason"] == "plain-language edit"
        assert c["instructions"]  # carried from the diagnosis
    assert [c["index"] for c in cands] == sorted(c["index"] for c in cands)

    # Second pass excludes already-edited paragraphs.
    state["llm_edited_indices"] = {c["index"] for c in cands}
    assert step_concision.get_candidates(state) == []


def test_skips_quotes_and_short_paragraphs():
    paras = [
        "word " * 60,                # 0: eligible
        "“a short block quotation”",  # 1: quote (flagged in diagnosis)
        "too short to bother",        # 2: < 40 words
        "word " * 50,                # 3: eligible
    ]
    text = "\n\n".join(paras)
    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {"text": guarded, "qmap": qmap, "target": 0, "diagnosis": _diag(paras, quotes={1})}

    cands = step_concision.get_candidates(state)
    assert [c["index"] for c in cands] == [0, 3]


def test_no_diagnosis_falls_back_without_spacy():
    """With no diagnosis, eligible non-quote paragraphs still route (no notes)."""
    paras = [f"Paragraph {i} " + "word " * 50 for i in range(3)]
    text = "\n\n".join(paras)
    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    state = {"text": guarded, "qmap": qmap, "target": 0}  # no "diagnosis" key

    cands = step_concision.get_candidates(state)
    assert len(cands) == 3
    assert all(c["instructions"] == [] for c in cands)
