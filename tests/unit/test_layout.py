"""Unit tests for course layout generation."""

import random
from itertools import permutations
from math import factorial, prod

import pytest

from golf.randomizer.layout import (
    COUNTS,
    LayoutError,
    choose_layout,
    distinct_permutations,
    joined_nines,
    layouts,
    nine_splits,
    nines_balanced,
    satisfies,
)


@pytest.mark.parametrize("par, size", [(72, 188_802), (71, 165_564), (70, 35_574)])
def test_pins_the_size_of_each_layout_space(par, size):
    assert len(layouts(par)) == size


@pytest.mark.parametrize("par", sorted(COUNTS))
def test_every_layout_satisfies_every_predicate(par):
    found = layouts(par)
    assert all(satisfies(layout, COUNTS[par]) for layout in found)
    assert sum(found[0]) == par
    assert len(set(found)) == len(found)


@pytest.mark.parametrize("par", sorted(COUNTS))
def test_layouts_are_sorted(par):
    found = layouts(par)
    assert list(found) == sorted(found)


def test_joining_nines_matches_filtering_every_permutation():
    """On a six-hole course with nines of three, where brute force is cheap."""
    counts = {3: 2, 4: 3, 5: 1}
    holes = [value for value, count in counts.items() for _ in range(count)]
    brute = sorted(
        {order for order in permutations(holes) if satisfies(order, counts, nine=3)}
    )
    assert brute
    assert joined_nines(counts, nine=3) == brute


def test_distinct_permutations_counts_the_multiset():
    counts = {3: 2, 4: 5, 5: 2}
    found = distinct_permutations(counts)
    assert len(found) == factorial(9) // prod(factorial(n) for n in counts.values())
    assert len(set(found)) == len(found)
    assert found == sorted(found)


def test_odd_counts_split_either_way():
    splits = nine_splits(COUNTS[71])
    assert {(front[4], front[5], back[4], back[5]) for front, back in splits} == {
        (5, 2, 6, 1),
        (6, 1, 5, 2),
    }
    assert all(front[3] == back[3] == 2 for front, back in splits)


def test_consecutive_rule_spans_the_turn():
    layout = (4, 3, 4, 5, 4, 4, 5, 4, 3, 3, 4, 5, 4, 4, 5, 4, 3, 4)
    assert nines_balanced(layout)
    assert not satisfies(layout, COUNTS[72])


def test_same_seed_draws_the_same_layout():
    assert choose_layout(72, random.Random("abc")) == choose_layout(
        72, random.Random("abc")
    )
    assert choose_layout(72, random.Random("abc")) in layouts(72)


def test_rejects_unsupported_par():
    with pytest.raises(LayoutError, match="par 69"):
        layouts(69)
