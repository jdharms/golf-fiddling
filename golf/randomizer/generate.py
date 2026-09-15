"""
Generation: a catalog, a curation snapshot and settings in, a manifest out.

Every random choice comes from `settings.prng_seed`, drawn fresh when the settings have
none. Each purpose (the layout, the hole draw, the music, the magic words) gets its own
generator derived from the seed, and the wind seeds come from `derive_hole_seeds`, so a
change to how one thing is drawn leaves the others where they were.

The same catalog, curation, settings and seed give the same manifest under one
`GENERATOR_VERSION`. That is a property the tests hold generation to, not a promise across
versions: a stored manifest, not its inputs, is what a seed is. Bump the version whenever
the same inputs would give a different manifest. See docs/manifest.md.
"""

import random
import secrets
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from golf.core.patches.seeded_wind import derive_hole_seeds

from .catalog import JP_ROM, Catalog, CatalogEntry
from .curation import CurationSnapshot
from .layout import choose_layout
from .manifest import SCHEMA, Course, Manifest, Settings, Slot
from .music import RANDOM, choose_music
from .pool import Family, Pool, build_pool, source_rom
from .words import draw_magic_words

GENERATOR_VERSION = 1
PRNG_SEED_BYTES = 8


class GenerationError(Exception):
    """Settings the catalog cannot satisfy, such as a pool too small for the layout."""


def new_prng_seed() -> str:
    return secrets.token_hex(PRNG_SEED_BYTES)


def stream(prng_seed: str, purpose: str) -> random.Random:
    """The generator for one purpose. String seeds are hashed, so this is stable across runs."""
    return random.Random(f"{purpose}\0{prng_seed}")


def _matchable(pars: Sequence[int], families: Sequence[Family]) -> bool:
    """Whether every par can take a different family with a member of that par.

    A bipartite matching of slots to families, by augmenting paths.
    """
    owner: dict[int, int] = {}  # family index -> slot index

    def augment(slot: int, seen: set[int]) -> bool:
        for index, family in enumerate(families):
            if index in seen or pars[slot] not in family.pars:
                continue
            seen.add(index)
            if index not in owner or augment(owner[index], seen):
                owner[index] = slot
                return True
        return False

    return all(augment(slot, set()) for slot in range(len(pars)))


def _shortfall(pool: Pool, layout: Sequence[int]) -> str:
    needed = Counter(layout)
    wants = ", ".join(f"{needed[par]} par {par}" for par in sorted(needed))
    offers = ", ".join(f"par {par}: {pool.families_with_par(par)}" for par in sorted(needed))
    return (
        f"the pool cannot fill a par {sum(layout)} course from distinct families: it needs "
        f"{wants}, and the families offering each par are {offers}"
    )


def draw_holes(pool: Pool, layout: Sequence[int], rng: random.Random) -> list[CatalogEntry]:
    """One hole per slot, from a different family each time.

    Slot by slot, the candidate families are shuffled and the first one that leaves the
    remaining slots fillable is taken, then one of its members with the slot's par. That
    is the draw a backtracking search makes, with a matching check standing in for the
    backtracking. A family can hold holes of different pars, so a greedy draw could spend
    the only family able to fill some later slot.
    """
    families = list(pool.families)
    if not _matchable(layout, families):
        raise GenerationError(_shortfall(pool, layout))
    chosen = []
    for position, par in enumerate(layout):
        candidates = [family for family in families if par in family.pars]
        rng.shuffle(candidates)
        rest_of_layout = layout[position + 1 :]
        for family in candidates:
            if _matchable(rest_of_layout, [other for other in families if other is not family]):
                break
        else:  # pragma: no cover - the matching above guarantees a candidate
            raise AssertionError("no fillable family for a matchable layout")
        families = [other for other in families if other is not family]
        chosen.append(rng.choice(family.with_par(par)))
    return chosen


def generate(catalog: Catalog, curation: CurationSnapshot, settings: Settings) -> Manifest:
    prng_seed = settings.prng_seed if settings.prng_seed is not None else new_prng_seed()
    pool = build_pool(catalog, curation, settings)
    layout = choose_layout(settings.par, stream(prng_seed, "layout"))
    entries = draw_holes(pool, layout, stream(prng_seed, "holes"))

    if settings.music == RANDOM:
        mario_open = any(source_rom(entry) == JP_ROM for entry in entries)
        music = choose_music(stream(prng_seed, "music"), include_mario_open=mario_open)
    else:
        music = settings.music

    wind_seeds = derive_hole_seeds(prng_seed)
    course = Course(
        holes=tuple(
            Slot(entry.id, entry.par, wind_seed)
            for entry, wind_seed in zip(entries, wind_seeds, strict=True)
        ),
        music=music,
        mercy_point=settings.mercy_point,
        clubs=settings.clubs,
        magic_words=draw_magic_words(stream(prng_seed, "magic_words")),
    )
    return Manifest(
        schema=SCHEMA,
        generator_version=GENERATOR_VERSION,
        catalog_version=catalog.version,
        curation_stamp=curation.stamp,
        settings=replace(settings, prng_seed=prng_seed),
        course=course,
    )
