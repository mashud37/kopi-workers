"""Unit tests for the diagnosis helpers and the LLM prompt builder.

The pure helpers (filler/plain detection, per-paragraph instruction derivation)
need neither spaCy nor a model. The full `diagnose()` entry point is covered by
the route smoke tests that run with spaCy available.
"""
from kopi import diagnose
from kopi.llm import _build_user_message, _PARA_SYSTEM


def test_unnecessary_words_detects_fillers_and_padding():
    text = "It is worth noting that the fact that this matters, in this regard."
    hits, savings = diagnose._unnecessary_words(text)
    assert hits >= 1
    assert savings >= 1


def test_plain_hits_detects_cliches_and_long_words():
    # "utilise" is a long-word substitution; "sheds light on" is a cliché.
    assert diagnose._plain_hits("We utilise this method.") >= 1
    assert diagnose._plain_hits("This sheds light on the question.") >= 1
    assert diagnose._plain_hits("A plain ordinary sentence.") == 0


def test_paragraph_instructions_always_includes_plain_language():
    feats = {"n_sents": 2, "mean_sent_len": 10, "passive_sents": 0}
    tags, instructions = diagnose._paragraph_instructions("A clean short paragraph.", feats, False)
    assert "plain-language" in tags
    assert any("Plain language" in i for i in instructions)


def test_paragraph_instructions_flags_wordiness_redundancy_passive():
    para = "It is worth noting that the fact that this is the case matters here."
    feats = {"n_sents": 3, "mean_sent_len": 40, "passive_sents": 2}  # long + passive
    tags, instructions = diagnose._paragraph_instructions(para, feats, is_redundant=True)
    assert {"wordiness", "redundancy", "long-sentence", "passive"} <= tags
    assert len(instructions) >= 4


def test_build_user_message_without_notes_is_just_the_paragraph():
    para = "The paragraph text to edit."
    assert _build_user_message(para) == para


def test_build_user_message_with_notes_fences_instructions():
    para = "The paragraph text to edit."
    msg = _build_user_message(para, ["Remove hedges and padding.", "Prefer active voice."])
    assert para in msg
    assert "Remove hedges and padding." in msg
    assert "do not repeat" in msg.lower()
    # The system prompt forbids echoing the notes (leak guard).
    assert "never repeat" in _PARA_SYSTEM.lower()
