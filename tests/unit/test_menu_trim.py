"""Unit tests for the menu trim patch's title validation and layout."""

import pytest

from golf.core.patches import RENDERABLE_CHARS, menu_trim_patches, random_title
from golf.core.patches.menu_trim import TITLE_LENGTH


def test_random_title_is_reproducible_for_a_seed():
    assert random_title(seed=1234) == random_title(seed=1234)


def test_random_title_is_renderable_and_the_right_length():
    title = random_title(seed=99)
    assert len(title) == TITLE_LENGTH
    assert set(title) <= set(RENDERABLE_CHARS)


def test_title_is_uppercased():
    patches = menu_trim_patches(title_text="abcdefghijklmn")
    title_patch = patches[0]
    assert b"ABCDEFGHIJKLMN" in title_patch.patched


def test_wrong_length_title_is_rejected():
    with pytest.raises(ValueError, match="exactly 14"):
        menu_trim_patches(title_text="TOO SHORT")


def test_unrenderable_title_is_rejected():
    with pytest.raises(ValueError, match="cannot render"):
        menu_trim_patches(title_text="HELLO, WORLD!!")


def test_title_list_exactly_fills_the_freed_region():
    """The new list must not spill past the two entries it replaces."""
    title_patch = menu_trim_patches(title_text="A" * TITLE_LENGTH)[0]
    assert len(title_patch.patched) == len(title_patch.original)


def test_every_sub_patch_is_length_preserving():
    for patch in menu_trim_patches(seed=7):
        assert len(patch.patched) == len(patch.original), patch.name


def test_sub_patch_names_are_unique():
    names = [p.name for p in menu_trim_patches(seed=7)]
    assert len(names) == len(set(names))
