"""Base62 ids: the alphabet and codec every public id on the site shares.

A public id is 10 characters of `0-9A-Za-z`, most significant digit first. A seed's is the
encoding of an integer the row also keeps as `qr_seed_id`, because the QR payload carries
that integer (`server/seeds.py`); a round's is drawn as text, because nothing outside the
URL ever holds it (`server/rounds.py`).
"""

import secrets
import string

ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase
ID_LENGTH = 10
#: the largest integer ID_LENGTH base62 digits hold
MAX_VALUE = len(ALPHABET) ** ID_LENGTH - 1

_DIGITS = {char: value for value, char in enumerate(ALPHABET)}


def is_id(text: object) -> bool:
    """Whether this is ID_LENGTH characters of the alphabet, and so could name something."""
    return isinstance(text, str) and len(text) == ID_LENGTH and all(char in _DIGITS for char in text)


def encode_base62(value: int) -> str:
    """An integer of 0 to MAX_VALUE as ID_LENGTH digits. The caller checks the range."""
    digits = []
    for _ in range(ID_LENGTH):
        value, digit = divmod(value, len(ALPHABET))
        digits.append(ALPHABET[digit])
    return "".join(reversed(digits))


def decode_base62(text: str) -> int:
    """ID_LENGTH digits as their integer. The caller checks `is_id` first."""
    value = 0
    for char in text:
        value = value * len(ALPHABET) + _DIGITS[char]
    return value


def new_id() -> str:
    """A uniformly drawn ID_LENGTH-character id."""
    return "".join(secrets.choice(ALPHABET) for _ in range(ID_LENGTH))
