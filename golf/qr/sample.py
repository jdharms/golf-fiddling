"""
Plausible random rounds, for previews and the validation sweep.

Scores are drawn to look like real golf rather than uniform noise, because the
hole-record bytes are the only part of the payload whose distribution we
control — a mask that only works on uniformly random bytes would be a trap.
A small fraction of rounds are deliberately disastrous so the clamping path
gets exercised too.
"""

import random

from golf.qr.payload import HoleRecord, RoundPayload

#: A par-72 layout: four 3s, ten 4s, four 5s.
DEFAULT_PARS = (4, 3, 5, 4, 4, 3, 4, 5, 4, 4, 5, 3, 4, 4, 3, 5, 4, 4)


def random_key(rng: random.Random) -> bytes:
    return bytes(rng.randrange(256) for _ in range(8))


def random_hole(rng: random.Random, par: int, disaster: bool = False) -> HoleRecord:
    if disaster:
        strokes = rng.randint(12, 22)
        putts = rng.randint(1, 4)
    else:
        strokes = max(1, par + rng.choice((-2, -1, -1, 0, 0, 0, 0, 1, 1, 2, 3)))
        putts = min(strokes, rng.choice((1, 1, 2, 2, 2, 2, 3, 3, 4)))
    return HoleRecord(strokes=strokes, putts=min(putts, strokes))


def random_round(
    rng: random.Random,
    seed_id: bytes | None = None,
    player_id: bytes | None = None,
    player_slot: int = 0,
    disaster_chance: float = 0.05,
) -> RoundPayload:
    return RoundPayload(
        seed_id=seed_id
        if seed_id is not None
        else bytes(rng.randrange(256) for _ in range(8)),
        player_id=player_id
        if player_id is not None
        else bytes(rng.randrange(256) for _ in range(4)),
        player_slot=player_slot,
        holes=tuple(
            random_hole(rng, par, disaster=rng.random() < disaster_chance)
            for par in DEFAULT_PARS
        ),
    )
