"""restore_casing: repair author-name casing the model flips inside citations,
without masking a genuinely changed or dropped citation."""
from kopi.citations import restore_casing


def test_restores_lowercased_second_author():
    original = "Polymedia reshapes practice (Hallinan & Striphas 2016)."
    edited = "Polymedia reshapes practice (Hallinan & striphas 2016)."
    assert restore_casing(original, edited) == original


def test_restores_lowercased_single_author():
    original = "Domestication matters (Silverstone 1994)."
    edited = "Domestication matters (silverstone 1994)."
    assert "(Silverstone 1994)" in restore_casing(original, edited)


def test_leaves_correct_citation_untouched():
    original = "A point (Burgess and Green, 2016) holds."
    assert restore_casing(original, original) == original


def test_does_not_fabricate_a_missing_citation():
    # The model dropped the citation entirely: restoration must not re-add it,
    # so the guard still rejects a genuine loss.
    original = "A claim (Herzog 1941) stands."
    edited = "A claim stands."
    assert "Herzog" not in restore_casing(original, edited)


def test_leaves_unknown_citation_for_the_guard():
    original = "As shown (Malinowski 1923)."
    edited = "As shown (Different 2099)."
    assert restore_casing(original, edited) == edited
