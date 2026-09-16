"""What the generate form and the seed page show, built from the library's data.

Nothing here is English: course names, ROM titles, hole ids and club labels are data. The
templates put them into strings from `server/strings.toml`.
"""

from dataclasses import dataclass

from golf.core import jp_rom_utils, rom_utils
from golf.core.patches.sram_defaults import BAG_SIZE
from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, RomSource
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.manifest import SOURCES, required_roms
from golf.randomizer.music import TRACKS, Track
from golf.randomizer.roms import VanillaRom, vanilla_rom

from .forms import MUSIC_CHOICES, PARS, RULE_CLUBS
from .seeds import SeedRow

#: (ROM id, course directory name) -> the course's display name
COURSE_NAMES: dict[tuple[str, str], str] = {
    **{(US_ROM, course["name"]): course["display_name"] for course in rom_utils.COURSES},
    **{(JP_ROM, course["name"]): course["display_name"] for course in jp_rom_utils.COURSES},
}


def track_course(track: Track) -> str:
    """The display name of the course a theme belongs to."""
    course = track.slug.removeprefix("nes_") if track.rom == US_ROM else track.slug
    return COURSE_NAMES[(track.rom, course)]


@dataclass(frozen=True)
class MusicOption:
    slug: str
    rom_title: str
    course: str


@dataclass(frozen=True)
class GenerateOptions:
    """The choices the generate form lists."""

    pars: tuple[int, ...]
    sources: tuple[VanillaRom, ...]
    music: tuple[MusicOption, ...]
    club_labels: tuple[str, ...]
    clubs_max: int


def generate_options() -> GenerateOptions:
    return GenerateOptions(
        pars=PARS,
        sources=tuple(vanilla_rom(source) for source in SOURCES),
        music=tuple(
            MusicOption(slug, vanilla_rom(TRACKS[slug].rom).title, track_course(TRACKS[slug]))
            for slug in MUSIC_CHOICES
            if slug in TRACKS
        ),
        club_labels=tuple(club.label for club in RULE_CLUBS),
        clubs_max=BAG_SIZE,
    )


@dataclass(frozen=True)
class HoleView:
    number: int
    id: str
    display_name: str | None
    par: int
    distance: int
    author: str
    #: set for a vanilla hole: the ROM, course and hole number it comes from
    rom_title: str | None
    course: str | None
    source_hole: int | None


@dataclass(frozen=True)
class SeedView:
    id: str
    magic_words: tuple[str, ...]
    created_at: str
    holes: tuple[HoleView, ...]
    total_par: int
    total_distance: int
    music: MusicOption
    par_target: int
    sources: tuple[VanillaRom, ...]
    allow_family_repeats: bool
    mercy_point: int | None
    clubs_max: int
    banned: tuple[str, ...]
    #: None when the seed has no required bag
    required_bag: tuple[str, ...] | None
    required_roms: tuple[VanillaRom, ...]


def _hole_view(number: int, slot, catalog: Catalog, curation: CurationSnapshot) -> HoleView:
    entry = catalog[slot.id]
    source = entry.source
    vanilla = isinstance(source, RomSource)
    return HoleView(
        number=number,
        id=str(slot.id),
        display_name=curation.for_hole(slot.id).display_name,
        par=slot.par,
        distance=entry.distance,
        author=entry.author,
        rom_title=vanilla_rom(source.rom).title if vanilla else None,
        course=COURSE_NAMES.get((source.rom, source.course), source.course) if vanilla else None,
        source_hole=source.hole if vanilla else None,
    )


def seed_view(row: SeedRow, catalog: Catalog, curation: CurationSnapshot) -> SeedView:
    manifest = row.manifest
    course = manifest.course
    settings = manifest.settings
    holes = tuple(
        _hole_view(number, slot, catalog, curation) for number, slot in enumerate(course.holes, start=1)
    )
    theme = TRACKS[course.music]
    return SeedView(
        id=row.id,
        magic_words=course.magic_words,
        created_at=row.created_at,
        holes=holes,
        total_par=course.par,
        total_distance=sum(hole.distance for hole in holes),
        music=MusicOption(theme.slug, vanilla_rom(theme.rom).title, track_course(theme)),
        par_target=settings.par,
        sources=tuple(vanilla_rom(source) for source in SOURCES if source in settings.sources),
        allow_family_repeats=settings.allow_family_repeats,
        mercy_point=course.mercy_point,
        clubs_max=course.clubs.max,
        banned=tuple(club.label for club in sorted(course.clubs.banned)),
        required_bag=None
        if course.clubs.required_bag is None
        else tuple(club.label for club in sorted(course.clubs.required_bag)),
        required_roms=tuple(vanilla_rom(rom) for rom in required_roms(manifest, catalog)),
    )
