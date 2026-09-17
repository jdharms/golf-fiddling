"""Unit tests for the magic word bank."""

import random

import pytest

from golf.randomizer.words import (
    MagicWordsError,
    check_magic_words,
    draw_magic_words,
    load_word_bank,
    scorecard_title,
)


def test_the_checked_in_bank_loads():
    bank = load_word_bank()
    assert len(bank) >= 3
    assert all(word == word.upper() for word in bank)


def test_the_longest_words_still_fit_both_patches():
    longest = sorted(load_word_bank(), key=len)[-3:]
    assert check_magic_words(longest) == tuple(longest)


def test_draws_are_three_distinct_words_and_reproducible():
    first = draw_magic_words(random.Random("x"))
    assert len(set(first)) == 3
    assert set(first) <= set(load_word_bank())
    assert draw_magic_words(random.Random("x")) == first


def test_scorecard_title_joins_the_words():
    assert scorecard_title(("OPEN", "GOLF", "RANDO")) == "OPEN GOLF RANDO"


@pytest.mark.parametrize(
    "lines, message",
    [
        (["ball", "Ball", "golf"], "already in the bank"),
        (["ball", "par", "golf"], "4-6 characters"),
        (["ball", "tee-up", "golf"], "cannot draw"),
        (["ball", "", "golf"], "at least 3"),
    ],
)
def test_rejects_bad_banks(tmp_path, lines, message):
    path = tmp_path / "bank.txt"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(MagicWordsError, match=message):
        load_word_bank(path)


@pytest.mark.parametrize("words", [("BALL", "GOLF"), ("BALL", "BALL", "GOLF"), ("BALL", "GOLF", "PUTTERS")])
def test_rejects_bad_magic_words(words):
    with pytest.raises(MagicWordsError):
        check_magic_words(words)
