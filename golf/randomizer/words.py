"""
Magic words: three words from the word bank that let a player see they have the right ROM.

The same three words head the title menus (`menu_trim`) and, joined by spaces, replace the
scorecard title (`scorecard_course_name`), and the seed page shows them. They identify a
seed at a glance, not uniquely. Every word in the bank must fit both: 4 to 6 characters
from the characters both fonts can draw.
"""

import random
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from golf.core.patches.menu_trim import MAX_WORD_LENGTH, MIN_WORD_LENGTH, RENDERABLE_CHARS, normalize_words
from golf.core.patches.scorecard_course_name import TITLE_FONT_CHARS, title_text

WORD_BANK = Path(__file__).resolve().parent / "data" / "word_bank.txt"
WORD_COUNT = 3

_DRAWABLE = frozenset(RENDERABLE_CHARS) & frozenset(TITLE_FONT_CHARS)


class MagicWordsError(ValueError):
    """A word neither patch can draw, a malformed word bank, or a bad set of magic words."""


def check_word(word: str) -> str:
    """The word uppercased, or MagicWordsError if the menu or scorecard cannot draw it."""
    if not isinstance(word, str):
        raise MagicWordsError(f"expected a word, got {word!r}")
    text = word.upper()
    if not MIN_WORD_LENGTH <= len(text) <= MAX_WORD_LENGTH:
        raise MagicWordsError(
            f"{word!r} must be {MIN_WORD_LENGTH}-{MAX_WORD_LENGTH} characters, got {len(text)}"
        )
    bad = sorted(set(text) - _DRAWABLE)
    if bad:
        raise MagicWordsError(f"{word!r} has characters the fonts cannot draw: {''.join(bad)!r}")
    return text


def scorecard_title(words: Sequence[str]) -> str:
    return " ".join(words)


def check_magic_words(words: Sequence[str]) -> tuple[str, ...]:
    """Three distinct drawable words, uppercased, that fit both the menu and the scorecard."""
    checked = tuple(check_word(word) for word in words)
    if len(checked) != WORD_COUNT:
        raise MagicWordsError(f"expected {WORD_COUNT} words, got {len(checked)}")
    if len(set(checked)) != len(checked):
        raise MagicWordsError(f"words repeat: {list(checked)}")
    try:
        normalize_words(checked)
        title_text(scorecard_title(checked))
    except ValueError as problem:
        raise MagicWordsError(str(problem)) from problem
    return checked


@cache
def load_word_bank(path: Path = WORD_BANK) -> tuple[str, ...]:
    """The bank's words uppercased, in file order. Blank lines are skipped."""
    words: list[str] = []
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            word = check_word(line.strip())
        except MagicWordsError as problem:
            raise MagicWordsError(f"{path}:{number}: {problem}") from None
        if word in words:
            raise MagicWordsError(f"{path}:{number}: {word} is already in the bank")
        words.append(word)
    if len(words) < WORD_COUNT:
        raise MagicWordsError(f"{path} needs at least {WORD_COUNT} words, has {len(words)}")
    return tuple(words)


def draw_magic_words(rng: random.Random, bank: Sequence[str] | None = None) -> tuple[str, ...]:
    """Three distinct words, in drawn order."""
    return tuple(rng.sample(list(load_word_bank() if bank is None else bank), WORD_COUNT))
