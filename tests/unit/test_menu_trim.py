"""Unit tests for the menu trim patch's header words and layout."""

import pytest

from golf.core.patches import menu_trim_patches
from golf.core.patches.menu_trim import DEFAULT_WORDS, header_lines, normalize_words


def test_words_default_to_open_golf_rando():
    assert normalize_words() == DEFAULT_WORDS == ("OPEN", "GOLF", "RANDO")


def test_words_take_a_list_or_a_whitespace_separated_string():
    assert normalize_words(["open", "golf", "rando"]) == ("OPEN", "GOLF", "RANDO")
    assert normalize_words("  open golf\trando ") == ("OPEN", "GOLF", "RANDO")


@pytest.mark.parametrize("words", ["OPEN GOLF", "OPEN GOLF RANDO MORE", []])
def test_wrong_word_count_is_rejected(words):
    with pytest.raises(ValueError, match="exactly 3 words"):
        normalize_words(words)


@pytest.mark.parametrize("word", ["GOL", "RANDOMS"])
def test_word_length_is_4_to_6(word):
    with pytest.raises(ValueError, match="4-6 characters"):
        normalize_words(["OPEN", "GOLF", word])


def test_unrenderable_word_is_rejected():
    with pytest.raises(ValueError, match="cannot render"):
        normalize_words(["OPEN", "GOLF!", "RANDO"])


def test_a_space_inside_a_listed_word_is_rejected():
    with pytest.raises(ValueError, match="cannot render"):
        normalize_words(["OPEN", "GO LF", "RANDO"])


def test_header_lines_use_fixed_word_slots():
    assert header_lines(["OPEN", "GOLF", "RANDO"]) == ("OPEN   GOLF  ", "RANDO ")
    assert header_lines(["PLEASE", "SELECT", "COURSE"]) == ("PLEASE SELECT", "COURSE")


def test_header_lines_are_as_wide_as_vanilla():
    """PLEASE SELECT / COURSE: the attribute cells the header colours."""
    for words in (["ABCD", "ABCD", "ABCD"], ["ABCDEF", "ABCDEF", "ABCDEF"]):
        line1, line2 = header_lines(words)
        assert (len(line1), len(line2)) == (13, 6)


def test_header_words_are_uppercased_into_the_patch():
    header, line2 = menu_trim_patches("open golf rando")[:2]
    assert b"OPEN   GOLF  " in header.patched
    assert line2.patched == b"RANDO "


def test_every_sub_patch_is_length_preserving():
    for patch in menu_trim_patches():
        assert len(patch.patched) == len(patch.original), patch.name


def test_sub_patch_names_are_unique():
    names = [p.name for p in menu_trim_patches()]
    assert len(names) == len(set(names))
