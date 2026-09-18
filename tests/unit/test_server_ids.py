"""Base62 ids: the alphabet and codec seed ids and round permalinks share."""

import pytest

from server.ids import (
    ALPHABET,
    ID_LENGTH,
    MAX_VALUE,
    decode_base62,
    encode_base62,
    is_id,
    new_id,
)


def test_the_alphabet_is_base62_in_ascending_order():
    assert len(ALPHABET) == 62
    assert ALPHABET.startswith("0123456789ABC")
    assert ALPHABET.endswith("xyz")
    assert MAX_VALUE == 62**ID_LENGTH - 1


@pytest.mark.parametrize(
    "value, text",
    [(0, "0000000000"), (1, "0000000001"), (61, "000000000z"), (62, "0000000010"), (MAX_VALUE, "zzzzzzzzzz")],
)
def test_integers_round_trip_through_base62(value, text):
    assert encode_base62(value) == text
    assert decode_base62(text) == value


@pytest.mark.parametrize("text", ["0000000001", "zzzzzzzzzz", "aA0zZ9aA0z"])
def test_ids_are_ten_characters_of_the_alphabet(text):
    assert is_id(text)


@pytest.mark.parametrize("text", ["", "123", "0" * 11, "0" * 9 + "-", "0" * 9 + " ", None, 1234567890])
def test_anything_else_is_not_an_id(text):
    assert not is_id(text)


def test_drawn_ids_are_ids_and_do_not_repeat():
    drawn = {new_id() for _ in range(500)}
    assert len(drawn) == 500
    assert all(is_id(text) for text in drawn)
    # every position is drawn from the whole alphabet, not just its digits
    assert len({char for text in drawn for char in text}) > 40
