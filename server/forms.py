"""The site's forms: what they show, what a submission holds, and what it becomes.

The generate form becomes `Settings`; the seed page's download form becomes `PlayerOptions`
and the ROM hashes a download is gated on.

`FormState` is the form's values as strings and sets, the way a browser sends them and the
template renders them, so a refused submission comes back with the player's choices. A
state becomes `Settings` through `settings_from_state`, which raises `FormError` naming the
problem for the template to show. A download submission is a `DownloadState`, checked by
`check_rom_hashes` and turned into `PlayerOptions` by `player_options_from_state`.

The mercy point and excluded tags are not on the form: a seed from the site takes their
`Settings` defaults.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from golf.core.patches.sram_defaults import (
    BAG_SIZE,
    NAME_CHARS,
    NAME_LENGTH,
    VANILLA_CLUBS,
    VANILLA_NAME,
    Club,
    parse_club,
)
from golf.randomizer.build import BuildError, PlayerOptions
from golf.randomizer.layout import COUNTS
from golf.randomizer.manifest import SOURCES, ClubRules, ManifestError, Settings
from golf.randomizer.music import RANDOM, TRACKS
from golf.randomizer.roms import vanilla_rom

#: par targets, largest first, as the form lists them
PARS = tuple(sorted(COUNTS, reverse=True))
#: every club a rule can name: the putter is always allowed and never listed
RULE_CLUBS = tuple(club for club in Club if club != Club.PT)
MUSIC_CHOICES = (RANDOM, *TRACKS)

#: FormError reasons, each shown by its own strings key in generate.html
NO_SOURCES = "no_sources"
REQUIRED_BAG_OVER_MAX = "required_bag_over_max"
REQUIRED_BAG_BANNED = "required_bag_banned"
INVALID = "invalid"

#: FormError reasons a download refuses with, each shown by its own strings key in download.js
INVALID_NAME = "invalid_name"
CLUBS_BANNED = "clubs_banned"
CLUBS_OVER_MAX = "clubs_over_max"
ROMS_MISSING = "roms_missing"

#: the download form's hash fields are this prefix and a catalog ROM id
ROM_HASH_PREFIX = "rom_"


class FormError(ValueError):
    def __init__(self, reason: str, **values: object):
        super().__init__(f"{reason}: {values}" if values else reason)
        self.reason = reason
        self.values = values


@dataclass
class FormState:
    par: str
    sources: set[str]
    allow_family_repeats: bool
    music: str
    clubs_max: str
    banned: set[str] = field(default_factory=set)
    required_bag: set[str] = field(default_factory=set)

    @classmethod
    def default(cls) -> "FormState":
        settings = Settings()
        return cls(
            par=str(settings.par),
            sources=set(settings.sources),
            allow_family_repeats=settings.allow_family_repeats,
            music=settings.music,
            clubs_max=str(settings.clubs.max),
        )

    @classmethod
    def from_form(cls, form) -> "FormState":
        """A submission's values, unchecked. `form` is Starlette's FormData, or anything with get and getlist."""

        def text(name: str) -> str:
            value = form.get(name)
            return value.strip() if isinstance(value, str) else ""

        def chosen(name: str) -> set[str]:
            return {value for value in form.getlist(name) if isinstance(value, str)}

        return cls(
            par=text("par"),
            sources=chosen("sources"),
            allow_family_repeats=bool(text("allow_family_repeats")),
            music=text("music"),
            clubs_max=text("clubs_max"),
            banned=chosen("banned"),
            required_bag=chosen("required_bag"),
        )

    def to_pairs(self) -> list[tuple[str, str]]:
        """The state as the fields a browser would submit for it."""
        pairs = [("par", self.par)]
        pairs += [("sources", source) for source in SOURCES if source in self.sources]
        if self.allow_family_repeats:
            pairs.append(("allow_family_repeats", "on"))
        pairs += [("music", self.music), ("clubs_max", self.clubs_max)]
        pairs += [
            ("banned", club.label) for club in RULE_CLUBS if club.label in self.banned
        ]
        pairs += [
            ("required_bag", club.label)
            for club in RULE_CLUBS
            if club.label in self.required_bag
        ]
        return pairs


def _labels(clubs: Iterable[Club]) -> str:
    return " ".join(club.label for club in sorted(clubs))


def _rule_clubs(labels: set[str], name: str) -> frozenset[Club]:
    try:
        clubs = frozenset(parse_club(label) for label in labels)
    except ValueError:
        raise FormError(INVALID, field=name) from None
    if Club.PT in clubs:
        raise FormError(INVALID, field=name)
    return clubs


def settings_from_state(state: FormState) -> Settings:
    """The settings a submission asks for. Raises FormError for anything the form cannot use."""
    if state.par not in {str(par) for par in PARS}:
        raise FormError(INVALID, field="par")
    if not state.sources:
        raise FormError(NO_SOURCES)
    if not state.sources <= set(SOURCES):
        raise FormError(INVALID, field="sources")
    if state.music not in MUSIC_CHOICES:
        raise FormError(INVALID, field="music")
    if state.clubs_max not in {str(count) for count in range(1, BAG_SIZE + 1)}:
        raise FormError(INVALID, field="clubs_max")

    clubs_max = int(state.clubs_max)
    banned = _rule_clubs(state.banned, "banned")
    required = _rule_clubs(state.required_bag, "required_bag")
    if required:
        bag = required | {Club.PT}
        if bag & banned:
            raise FormError(REQUIRED_BAG_BANNED, clubs=_labels(bag & banned))
        if len(bag) > clubs_max:
            raise FormError(REQUIRED_BAG_OVER_MAX, count=len(bag), max=clubs_max)

    try:
        return Settings(
            par=int(state.par),
            sources=frozenset(state.sources),
            allow_family_repeats=state.allow_family_repeats,
            music=state.music,
            clubs=ClubRules(
                max=clubs_max, banned=banned, required_bag=required or None
            ),
        )
    except (
        ManifestError
    ):  # pragma: no cover - every rule Settings checks is checked above
        raise FormError(INVALID, field="settings") from None


# -- Download ---------------------------------------------------------------------------------


@dataclass
class DownloadState:
    """The seed page's download form: the player's choices and the ROM hashes the script adds."""

    player_name: str
    clubs: set[str]
    #: catalog ROM id -> the SHA-1 the browser's ROM store recorded
    rom_hashes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls, rules: ClubRules) -> "DownloadState":
        """What the form shows first: the vanilla name, and the required bag or the vanilla bag less banned clubs."""
        bag = (
            rules.required_bag
            if rules.required_bag is not None
            else frozenset(VANILLA_CLUBS) - rules.banned
        )
        return cls(
            player_name=VANILLA_NAME,
            clubs={club.label for club in bag if club != Club.PT},
        )

    @classmethod
    def from_form(cls, form) -> "DownloadState":
        """A submission's values, unchecked. `form` is Starlette's FormData, or anything with keys, get and getlist."""
        name = form.get("player_name")
        hashes = {}
        for key in form.keys():  # noqa: SIM118 (FormData, not a dict)
            value = form.get(key)
            if key.startswith(ROM_HASH_PREFIX) and isinstance(value, str):
                hashes[key.removeprefix(ROM_HASH_PREFIX)] = value.strip().lower()
        return cls(
            player_name=name.strip() if isinstance(name, str) else "",
            clubs={value for value in form.getlist("clubs") if isinstance(value, str)},
            rom_hashes=hashes,
        )

    def to_pairs(self) -> list[tuple[str, str]]:
        """The state as the fields a browser would submit for it, hashes included."""
        pairs = [("player_name", self.player_name)]
        pairs += [("clubs", club.label) for club in Club if club.label in self.clubs]
        pairs += [
            (ROM_HASH_PREFIX + rom_id, sha1) for rom_id, sha1 in self.rom_hashes.items()
        ]
        return pairs


def check_rom_hashes(state: DownloadState, required: Iterable[str]) -> None:
    """Raise FormError naming every required ROM the submission has no vanilla hash for."""
    missing = [
        rom_id
        for rom_id in required
        if state.rom_hashes.get(rom_id) != vanilla_rom(rom_id).sha1
    ]
    if missing:
        raise FormError(
            ROMS_MISSING,
            roms=", ".join(vanilla_rom(rom_id).title for rom_id in missing),
        )


def player_options_from_state(state: DownloadState, rules: ClubRules) -> PlayerOptions:
    """The options a download asks for under the seed's club rules. Raises FormError for anything they forbid.

    A seed with a required bag ignores the submitted clubs and uses its bag.
    """
    name = state.player_name.upper()
    bad = "".join(sorted(set(name) - set(NAME_CHARS)))
    if bad:
        raise FormError(INVALID_NAME, chars=bad)
    if not name.strip() or len(name) > NAME_LENGTH:
        raise FormError(INVALID_NAME, chars="")

    if rules.required_bag is not None:
        clubs = rules.required_bag
    else:
        try:
            clubs = frozenset(parse_club(label) for label in state.clubs)
        except ValueError:
            raise FormError(INVALID, field="clubs") from None
    bag = clubs | {Club.PT}
    if bag & rules.banned:
        raise FormError(CLUBS_BANNED, clubs=_labels(bag & rules.banned))
    if len(bag) > rules.max:
        raise FormError(CLUBS_OVER_MAX, count=len(bag), max=rules.max)

    try:
        return PlayerOptions(player_name=name, clubs=bag)
    except (
        BuildError
    ):  # pragma: no cover - every rule PlayerOptions checks is checked above
        raise FormError(INVALID, field="player") from None
