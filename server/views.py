"""What the generate form and the seed page show, built from the library's data.

Nothing here is English: course names, ROM titles, hole ids, club labels and file names are
data. The templates put them into strings from `server/strings/`.
"""

from dataclasses import dataclass

from golf.core import jp_rom_utils, rom_utils
from golf.core.patches.sram_defaults import BAG_SIZE, NAME_LENGTH
from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, RomSource
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.manifest import SOURCES, required_roms
from golf.randomizer.music import TRACKS, Track
from golf.randomizer.roms import VanillaRom, vanilla_rom

from .forms import MUSIC_CHOICES, PARS, RULE_CLUBS, DownloadState
from .seeds import SeedRow
from .submissions import ScanResult

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


#: every downloaded ROM's file name starts with this, so tools can recognise a randomizer ROM
DOWNLOAD_PREFIX = "notgr"


def download_stem(row: SeedRow) -> str:
    """A seed's download file name without its extension, e.g. `notgr_par72_4np03ChsZL`.

    The prefix marks a randomizer ROM, the par tells seeds apart at a glance, and the id leads
    back to the seed page. It is a file name, not player-facing text: never a strings entry.
    """
    return f"{DOWNLOAD_PREFIX}_par{row.manifest.course.par}_{row.id}"


@dataclass(frozen=True)
class DownloadView:
    """The seed page's download form."""

    #: where the form posts, and the finished IPS comes from
    ips_url: str
    #: the name the patched ROM downloads as
    filename: str
    default_name: str
    name_max: int
    #: every club the form can list: the putter is always carried and never listed
    club_labels: tuple[str, ...]
    default_clubs: frozenset[str]
    banned: frozenset[str]
    clubs_max: int
    #: None when the seed has no required bag, and the form lists clubs
    required_bag: tuple[str, ...] | None
    required_roms: tuple[VanillaRom, ...]

    @property
    def rom_details(self) -> dict[str, dict[str, str]]:
        """What download.js needs to know of each required ROM: id -> title and SHA-1."""
        return {rom.id: {"title": rom.title, "sha1": rom.sha1} for rom in self.required_roms}


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
    download: DownloadView


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
    rules = course.clubs
    required = tuple(vanilla_rom(rom) for rom in required_roms(manifest, catalog))
    required_bag = None if rules.required_bag is None else tuple(club.label for club in sorted(rules.required_bag))
    download = DownloadView(
        ips_url=f"/h/{row.id}/patch.ips",
        filename=download_stem(row) + ".nes",
        default_name=DownloadState.default(rules).player_name,
        name_max=NAME_LENGTH,
        club_labels=tuple(club.label for club in RULE_CLUBS),
        default_clubs=frozenset(DownloadState.default(rules).clubs),
        banned=frozenset(club.label for club in rules.banned),
        clubs_max=rules.max,
        required_bag=required_bag,
        required_roms=required,
    )
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
        required_bag=required_bag,
        required_roms=required,
        download=download,
    )


@dataclass(frozen=True)
class RoundHoleView:
    number: int
    par: int
    strokes: int
    putts: int


@dataclass(frozen=True)
class NineView:
    """One nine of a round, as a table of its own on the scan page, with its totals."""

    holes: tuple[RoundHoleView, ...]

    @property
    def par(self) -> int:
        return sum(hole.par for hole in self.holes)

    @property
    def strokes(self) -> int:
        return sum(hole.strokes for hole in self.holes)

    @property
    def putts(self) -> int:
        return sum(hole.putts for hole in self.holes)


@dataclass(frozen=True)
class SubmissionView:
    """What the scan page shows of a recorded round."""

    seed_id: str
    magic_words: tuple[str, ...]
    player_name: str
    slot: int
    #: whether this scan recorded the round, rather than finding it recorded
    new: bool
    received_at: str
    #: holes 1-9 and 10-18, a table each
    front: NineView
    back: NineView
    total_par: int
    total_strokes: int
    total_putts: int


def submission_view(row: SeedRow, result: ScanResult, player_name: str) -> SubmissionView:
    recorded = result.round
    course = row.manifest.course
    holes = tuple(
        RoundHoleView(hole.position, slot.par, hole.strokes, hole.putts)
        for hole, slot in zip(recorded.holes, course.holes, strict=True)
    )
    return SubmissionView(
        seed_id=row.id,
        magic_words=course.magic_words,
        player_name=player_name,
        slot=recorded.slot,
        new=result.new,
        received_at=recorded.received_at,
        front=NineView(holes[:9]),
        back=NineView(holes[9:]),
        total_par=course.par,
        total_strokes=recorded.total_strokes,
        total_putts=recorded.total_putts,
    )
