"""
Course patch: write one 18-hole course into the ROM, packed across terrain
banks 0 and 1.

See docs/multi_bank_terrain.md for the layout.

Everything is computed when the patch is built: the holes are validated and
compressed, terrain is allocated to banks, and every byte the patch will write
is laid out in `writes`. A course that does not fit raises `BankOverflowError`
from the constructor, so building the patch is also how a course is checked
for fit.

The patch writes course data: terrain and attributes in banks 0 and 1, the
per-hole bank table and greens in bank 3, and the pointer and metadata tables
for holes 0-17 in the fixed bank. It also writes the course's totals onto the
scorecard in bank 2, where vanilla stores them as constants rather than adding
up the metadata tables (docs/scorecard.md): the total yardage digits, and the
`TOTAL 72` par cell in both blank cards. Like `ScorecardQrPatch`'s image, these
writes do not check what they overwrite - the regions hold vanilla course data,
or another course's, and carrying a copy to compare against would be absurd -
so `can_apply` is always true.

The data is only playable on a ROM carrying three other patches, listed in
`requires` and checked by `apply`:

- `multi_bank_lookup`: the bank table means nothing until the terrain bank is
  looked up per hole
- `course_mirrors`: every course slot plays holes 0-17; slots 18-53 are never
  written
- `attr_streaming`: attributes are written at their real size, which can exceed
  the vanilla 72-byte buffer

Bank 2's terrain region is left to other patches (the scorecard QR image lives
there), and so are the metadata slots for holes 18-53 (`seeded_wind` keeps its
seed table in the course-3 block of the flag X table).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from golf.core import rom_utils
from golf.core.compressor import GreensCompressor, TerrainCompressor
from golf.core.course_validation import CourseValidator
from golf.core.packing import int_to_bcd, pack_attributes
from golf.core.rom_writer import BankOverflowError
from golf.formats.hole_data import HoleData

from .attr_streaming import ATTR_STREAMING_PATCH
from .base import ROMPatch
from .multi_bank import COURSE_MIRRORS_PATCH, MULTI_BANK_CODE_PATCH

# Terrain bank boundaries - each bank has lookup tables that limit the terrain region
TERRAIN_BOUNDS = {
    0: (0x8000, 0xA23E),  # 8,766 bytes
    1: (0x8000, 0xA1E6),  # 8,678 bytes
}

# Per-hole bank table location in bank 3, between the greens and bank 3's code
BANK_TABLE_CPU_ADDR = 0xA700
BANK_TABLE_SIZE = rom_utils.HOLES_PER_COURSE * 2  # doubled indexing

# Greens region boundaries in bank 3
GREENS_BANK = 3
GREENS_DATA_START = 0x81C0  # First byte after the decompression tables
GREENS_DATA_END = BANK_TABLE_CPU_ADDR  # Stop before bank table

# Scorecard totals in bank 2 (docs/scorecard.md). The yardage code at $AF2F
# loads the thousands tile as an immediate (`LDA #$47` at $AF32), then ORs $40
# into one raw digit from each of three tables indexed by CurrCourse. Every
# course slot plays this course, so each table gets its digit three times.
SCORECARD_BANK = 2
YARDAGE_THOUSANDS_OPERAND = 0xAF33
YARDAGE_DIGIT_TABLES = (0xAF71, 0xAF74, 0xAF77)  # hundreds, tens, ones
COURSE_SLOTS = 3
# The two par digits of `TOTAL 72`, literals in each blank card's compressed
# nametable stream: the main card, and the 36-hole match play tournament card.
PAR_TOTAL_CELLS = (0xB9BF, 0xBAD5)
DIGIT_TILES = 0x40  # the small table font's `0`

TOTAL_YARDS_RANGE = range(1000, 10000)
TOTAL_PAR_RANGE = range(10, 100)


@dataclass
class HoleCompressedData:
    """Compressed data for a single hole."""

    hole_index: int
    terrain: bytes
    attributes: bytes
    greens: bytes


@dataclass
class BankAllocation:
    """Terrain bank allocation for a single hole."""

    hole_index: int
    bank: int
    terrain_start: int  # CPU address
    terrain_end: int  # CPU address (attr start)


@dataclass
class CourseWriteStats:
    """How the holes were packed."""

    bank_usage: dict = field(default_factory=dict)  # bank -> bytes used
    bank_capacity: dict = field(default_factory=dict)  # bank -> total capacity
    bank_assignments: list = field(default_factory=list)  # hole -> bank
    terrain_bytes_per_hole: list = field(default_factory=list)
    attribute_bytes_per_hole: list = field(default_factory=list)
    greens_bytes_per_hole: list = field(default_factory=list)
    total_terrain_bytes: int = 0
    total_greens_bytes: int = 0
    total_yards: int = 0
    total_par: int = 0


@dataclass(frozen=True)
class DataWrite:
    """One run of course data, at an absolute PRG offset."""

    name: str
    prg_offset: int
    data: bytes


def hole_par(hole: HoleData) -> int:
    return hole.metadata.get("par", 4)


def hole_distance(hole: HoleData) -> int:
    return hole.metadata.get("distance", 400)


def compress_holes(holes: Sequence[HoleData]) -> list[HoleCompressedData]:
    """Validate every hole, then compress terrain, attributes and greens."""
    validator = CourseValidator()
    for i, hole in enumerate(holes):
        validator.validate_hole(i, hole)

    terrain_compressor = TerrainCompressor()
    greens_compressor = GreensCompressor()
    return [
        HoleCompressedData(
            hole_index=i,
            terrain=terrain_compressor.compress(hole.terrain[: hole.terrain_height]),
            attributes=pack_attributes(hole.attributes),
            greens=greens_compressor.compress(hole.greens),
        )
        for i, hole in enumerate(holes)
    ]


def allocate_terrain(compressed: Sequence[HoleCompressedData]) -> list[BankAllocation]:
    """
    Allocate holes to banks using greedy first-fit.

    Each hole's terrain + attributes must fit contiguously in a bank.
    Banks are filled in order: 0, then 1.
    """
    allocations: list[BankAllocation] = []
    bank_next_addr = {bank: start for bank, (start, _) in TERRAIN_BOUNDS.items()}

    for hole in compressed:
        hole_size = len(hole.terrain) + len(hole.attributes)
        for bank, (_, end) in TERRAIN_BOUNDS.items():
            start = bank_next_addr[bank]
            if end - start >= hole_size:
                allocations.append(
                    BankAllocation(
                        hole_index=hole.hole_index,
                        bank=bank,
                        terrain_start=start,
                        terrain_end=start + len(hole.terrain),
                    )
                )
                bank_next_addr[bank] += hole_size
                break
        else:
            total_required = sum(len(h.terrain) + len(h.attributes) for h in compressed)
            total_available = sum(end - start for start, end in TERRAIN_BOUNDS.values())
            raise BankOverflowError(
                f"Hole {hole.hole_index} terrain ({hole_size} bytes) "
                f"doesn't fit in any remaining bank space.\n"
                f"Total required: {total_required:,} bytes, "
                f"Total available: {total_available:,} bytes"
            )

    return allocations


def bank_table_bytes(allocations: Sequence[BankAllocation]) -> bytes:
    """
    The per-hole bank lookup table at $A700 in bank 3.

    Doubled indexing: table[hole * 2] = bank number. Odd-offset bytes are
    don't-care values (set to 0).
    """
    table = bytearray(BANK_TABLE_SIZE)
    for alloc in allocations:
        table[alloc.hole_index * 2] = alloc.bank
    return bytes(table)


def scorecard_total_writes(holes: Sequence[HoleData]) -> list[DataWrite]:
    """
    The scorecard's total yardage and total par for these holes.

    Raises ValueError when a total does not fit its cell: four digits of
    yardage, two of par.
    """
    yards = sum(hole_distance(hole) for hole in holes)
    par = sum(hole_par(hole) for hole in holes)
    if yards not in TOTAL_YARDS_RANGE:
        raise ValueError(
            f"Total yardage {yards:,} does not fit the scorecard's four digits "
            f"({TOTAL_YARDS_RANGE.start}-{TOTAL_YARDS_RANGE.stop - 1})"
        )
    if par not in TOTAL_PAR_RANGE:
        raise ValueError(
            f"Total par {par} does not fit the scorecard's two digits "
            f"({TOTAL_PAR_RANGE.start}-{TOTAL_PAR_RANGE.stop - 1})"
        )

    def write(what: str, cpu_addr: int, data: bytes) -> DataWrite:
        return DataWrite(
            f"scorecard {what}",
            rom_utils.cpu_to_prg_switched(cpu_addr, SCORECARD_BANK),
            data,
        )

    thousands, *digits = (int(digit) for digit in f"{yards:04d}")
    writes = [
        write(
            f"total yardage {yards} (thousands tile)",
            YARDAGE_THOUSANDS_OPERAND,
            bytes([DIGIT_TILES + thousands]),
        )
    ]
    for place, table, digit in zip(
        ("hundreds", "tens", "ones"), YARDAGE_DIGIT_TABLES, digits, strict=True
    ):
        writes.append(
            write(
                f"total yardage {yards} ({place})", table, bytes([digit] * COURSE_SLOTS)
            )
        )
    for card, cell in zip(
        ("main card", "36-hole match play card"), PAR_TOTAL_CELLS, strict=True
    ):
        writes.append(
            write(
                f"total par {par} ({card})",
                cell,
                bytes([DIGIT_TILES + par // 10, DIGIT_TILES + par % 10]),
            )
        )
    return writes


def _fixed(cpu_addr: int) -> int:
    return rom_utils.cpu_to_prg_fixed(cpu_addr)


def _word(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _metadata_writes(hole_idx: int, hole: HoleData) -> list[DataWrite]:
    metadata = hole.metadata
    tee = metadata.get("tee", {"x": 0, "y": 0})
    flags = metadata.get("flag_positions", [])
    flag_y = bytes(
        flags[i].get("y_offset", 0) if i < len(flags) else 0 for i in range(4)
    )
    flag_x = bytes(
        flags[i].get("x_offset", 0) if i < len(flags) else 0 for i in range(4)
    )
    dist_100, dist_10, dist_1 = int_to_bcd(hole_distance(hole))

    def write(what: str, cpu_addr: int, data: bytes) -> DataWrite:
        return DataWrite(f"hole {hole_idx} {what}", _fixed(cpu_addr), data)

    return [
        write("par", rom_utils.TABLE_PAR + hole_idx, bytes([hole_par(hole)])),
        write(
            "handicap",
            rom_utils.TABLE_HANDICAP + hole_idx,
            bytes([metadata.get("handicap", 1)]),
        ),
        write(
            "distance (100s)",
            rom_utils.TABLE_DISTANCE_100 + hole_idx,
            bytes([dist_100]),
        ),
        write(
            "distance (10s)", rom_utils.TABLE_DISTANCE_10 + hole_idx, bytes([dist_10])
        ),
        write("distance (1s)", rom_utils.TABLE_DISTANCE_1 + hole_idx, bytes([dist_1])),
        write(
            "scroll limit",
            rom_utils.TABLE_SCROLL_LIMIT + hole_idx,
            bytes([metadata.get("scroll_limit", 32)]),
        ),
        write("green X", rom_utils.TABLE_GREEN_X + hole_idx, bytes([hole.green_x])),
        write("green Y", rom_utils.TABLE_GREEN_Y + hole_idx, bytes([hole.green_y])),
        write("tee X", rom_utils.TABLE_TEE_X + hole_idx, bytes([tee["x"]])),
        write("tee Y", rom_utils.TABLE_TEE_Y + hole_idx * 2, _word(tee["y"])),
        write("flag Y offsets", rom_utils.TABLE_FLAG_Y_OFFSET + hole_idx * 4, flag_y),
        write("flag X offsets", rom_utils.TABLE_FLAG_X_OFFSET + hole_idx * 4, flag_x),
    ]


class CoursePatch(ROMPatch):
    """Write one 18-hole course. Requires the code patches that can play it."""

    name = "course"
    description = "Write one 18-hole course, packed across terrain banks 0 and 1"
    requires = (MULTI_BANK_CODE_PATCH, COURSE_MIRRORS_PATCH, ATTR_STREAMING_PATCH)

    def __init__(self, holes: Sequence[HoleData]):
        if len(holes) != rom_utils.HOLES_PER_COURSE:
            raise ValueError(
                f"Expected {rom_utils.HOLES_PER_COURSE} holes, got {len(holes)}"
            )
        self.holes = list(holes)
        self.scorecard_writes = scorecard_total_writes(self.holes)
        self.compressed = compress_holes(self.holes)
        self.allocations = allocate_terrain(self.compressed)
        self.writes: list[DataWrite] = []
        self._layout()
        self.stats = self._calculate_stats()

    # -- construction ---------------------------------------------------

    def _layout(self) -> None:
        for hole, alloc in zip(self.compressed, self.allocations, strict=True):
            self.writes.append(
                DataWrite(
                    f"hole {alloc.hole_index} terrain ({len(hole.terrain)} bytes, bank {alloc.bank})",
                    rom_utils.cpu_to_prg_switched(alloc.terrain_start, alloc.bank),
                    hole.terrain,
                )
            )
            self.writes.append(
                DataWrite(
                    f"hole {alloc.hole_index} attributes ({len(hole.attributes)} bytes, bank {alloc.bank})",
                    rom_utils.cpu_to_prg_switched(alloc.terrain_end, alloc.bank),
                    hole.attributes,
                )
            )
            self.writes.append(
                DataWrite(
                    f"hole {alloc.hole_index} terrain start ptr",
                    _fixed(rom_utils.TABLE_TERRAIN_START_PTR + alloc.hole_index * 2),
                    _word(alloc.terrain_start),
                )
            )
            self.writes.append(
                DataWrite(
                    f"hole {alloc.hole_index} terrain end ptr",
                    _fixed(rom_utils.TABLE_TERRAIN_END_PTR + alloc.hole_index * 2),
                    _word(alloc.terrain_end),
                )
            )

        self.writes.append(
            DataWrite(
                f"per-hole bank table ({BANK_TABLE_SIZE} bytes)",
                rom_utils.cpu_to_prg_switched(BANK_TABLE_CPU_ADDR, GREENS_BANK),
                bank_table_bytes(self.allocations),
            )
        )

        self._layout_greens()

        for index, hole in enumerate(self.holes):
            self.writes += _metadata_writes(index, hole)

        self.writes += self.scorecard_writes

    def _layout_greens(self) -> None:
        """Lay greens out sequentially after bank 3's decompression tables."""
        total_size = sum(len(hole.greens) for hole in self.compressed)
        available = GREENS_DATA_END - GREENS_DATA_START
        if total_size > available:
            raise BankOverflowError(
                f"Greens data ({total_size:,} bytes) exceeds "
                f"available space ({available:,} bytes) in bank {GREENS_BANK} "
                f"(region ${GREENS_DATA_START:04X}-${GREENS_DATA_END:04X})"
            )

        cursor = GREENS_DATA_START
        for hole in self.compressed:
            self.writes.append(
                DataWrite(
                    f"hole {hole.hole_index} greens ({len(hole.greens)} bytes)",
                    rom_utils.cpu_to_prg_switched(cursor, GREENS_BANK),
                    hole.greens,
                )
            )
            self.writes.append(
                DataWrite(
                    f"hole {hole.hole_index} greens ptr",
                    _fixed(rom_utils.TABLE_GREENS_PTR + hole.hole_index * 2),
                    _word(cursor),
                )
            )
            cursor += len(hole.greens)

    def _calculate_stats(self) -> CourseWriteStats:
        stats = CourseWriteStats()
        for bank, (start, end) in TERRAIN_BOUNDS.items():
            stats.bank_capacity[bank] = end - start
            stats.bank_usage[bank] = 0

        for hole, alloc in zip(self.compressed, self.allocations, strict=True):
            stats.bank_usage[alloc.bank] += len(hole.terrain) + len(hole.attributes)
            stats.bank_assignments.append(alloc.bank)
            stats.terrain_bytes_per_hole.append(len(hole.terrain))
            stats.attribute_bytes_per_hole.append(len(hole.attributes))
            stats.greens_bytes_per_hole.append(len(hole.greens))

        stats.total_terrain_bytes = sum(stats.bank_usage.values())
        stats.total_greens_bytes = sum(stats.greens_bytes_per_hole)
        stats.total_yards = sum(hole_distance(hole) for hole in self.holes)
        stats.total_par = sum(hole_par(hole) for hole in self.holes)
        return stats

    # -- ROMPatch -------------------------------------------------------

    def can_apply(self, rom_writer) -> bool:
        """Always true: the course data regions are deliberately not checked
        (see the module docstring). Requirements are checked by `apply`."""
        return True

    def is_applied(self, rom_writer) -> bool:
        return all(
            rom_writer.read_prg(w.prg_offset, len(w.data)) == w.data
            for w in self.writes
        )

    def apply(self, rom_writer) -> None:
        self.check_requirements(rom_writer)
        for write in self.writes:
            rom_writer.annotate(write.name).write_prg(write.prg_offset, write.data)

    def __repr__(self) -> str:
        return f"CoursePatch(writes={len(self.writes)}, stats={self.stats!r})"
