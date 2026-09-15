"""
Course layouts: the sequence of par values for holes 1 to 18.

A layout is every distinct permutation of a par's counts that passes the predicates in
docs/randomizer.md: each par value split evenly across the nines (an odd count puts the
extra hole in either nine), and no consecutive par 3s or par 5s, including holes 9 and 10.
Permutations are built a nine at a time and joined, which gives the same set as permuting
all 18 holes and filtering, without the millions of candidates.

`layouts(par)` is sorted, so a draw from it with a seeded `random.Random` is reproducible.
"""

import random
from collections.abc import Mapping, Sequence
from functools import cache
from itertools import pairwise, product

NINE = 9

# Par 70 and 71 drop par 5s rather than add par 3s.
COUNTS: Mapping[int, Mapping[int, int]] = {
    72: {3: 4, 4: 10, 5: 4},
    71: {3: 4, 4: 11, 5: 3},
    70: {3: 4, 4: 12, 5: 2},
}

NO_CONSECUTIVE = (3, 5)

Layout = tuple[int, ...]


class LayoutError(ValueError):
    """A par with no count table."""


def distinct_permutations(counts: Mapping[int, int]) -> list[Layout]:
    """Every distinct ordering of a multiset, in lexicographic order of its values."""
    remaining = dict(sorted(counts.items()))
    size = sum(remaining.values())
    current: list[int] = []
    result: list[Layout] = []

    def backtrack():
        if len(current) == size:
            result.append(tuple(current))
            return
        for value in remaining:
            if remaining[value] > 0:
                remaining[value] -= 1
                current.append(value)
                backtrack()
                current.pop()
                remaining[value] += 1

    backtrack()
    return result


def nine_splits(
    counts: Mapping[int, int], nine: int = NINE
) -> list[tuple[dict[int, int], dict[int, int]]]:
    """Every (front, back) pair of nine-hole counts that splits each par value evenly."""
    choices = [
        sorted({count // 2, count - count // 2}) for _, count in sorted(counts.items())
    ]
    splits = []
    for picks in product(*choices):
        front = dict(zip(sorted(counts), picks, strict=True))
        if sum(front.values()) == nine:
            back = {value: counts[value] - front[value] for value in front}
            splits.append((front, back))
    return splits


def has_counts(layout: Sequence[int], counts: Mapping[int, int]) -> bool:
    return sorted(layout) == sorted(
        value for value, count in counts.items() for _ in range(count)
    )


def nines_balanced(layout: Sequence[int], nine: int = NINE) -> bool:
    front, back = layout[:nine], layout[nine:]
    return all(
        abs(front.count(value) - back.count(value)) <= 1 for value in set(layout)
    )


def no_consecutive(layout: Sequence[int], par: int) -> bool:
    return all(not (a == b == par) for a, b in pairwise(layout))


def satisfies(
    layout: Sequence[int], counts: Mapping[int, int], nine: int = NINE
) -> bool:
    """Whether a layout passes every predicate for a count table."""
    return (
        has_counts(layout, counts)
        and nines_balanced(layout, nine)
        and all(no_consecutive(layout, par) for par in NO_CONSECUTIVE)
    )


def joined_nines(counts: Mapping[int, int], nine: int = NINE) -> list[Layout]:
    """Every layout for a count table, built a nine at a time, sorted."""
    found = []
    for front_counts, back_counts in nine_splits(counts, nine):
        fronts = [part for part in distinct_permutations(front_counts) if _clean(part)]
        backs = [part for part in distinct_permutations(back_counts) if _clean(part)]
        found.extend(front + back for front, back in product(fronts, backs))
    return sorted(layout for layout in found if satisfies(layout, counts, nine))


def _clean(part: Layout) -> bool:
    return all(no_consecutive(part, par) for par in NO_CONSECUTIVE)


@cache
def layouts(par: int) -> tuple[Layout, ...]:
    """Every valid layout for a course par, sorted."""
    if par not in COUNTS:
        raise LayoutError(
            f"no layout counts for par {par}: expected one of {sorted(COUNTS)}"
        )
    return tuple(joined_nines(COUNTS[par]))


def choose_layout(par: int, rng: random.Random) -> Layout:
    """A uniform draw from `layouts(par)`."""
    return rng.choice(layouts(par))
