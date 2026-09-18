"""Dump course data from the US and JP ROMs to the hole JSON files `HoleData` reads.

`dump_us_courses` writes `japan/`, `us/` and `uk/` under a root; `dump_jp_courses` writes
the five Mario Open courses, `jp_japan/` and so on, under a root of their own (`courses/jp`
by convention). Both write the same schema; the tables they read from differ, as
`docs/jp_extraction.md` describes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from golf.core import jp_rom_utils, rom_utils
from golf.core.decompressor import (
    DecompressionStats,
    GreensDecompressor,
    TerrainDecompressor,
    bcd_to_int,
    unpack_attributes,
)
from golf.core.palettes import ATTR_TOTAL_BYTES, TERRAIN_ROW_WIDTH
from golf.core.rom_reader import RomReader
from golf.formats import compact_json as json
from golf.formats.hex_utils import format_hex_rows

#: the most compressed greens bytes a hole can need: one byte per tile of a 24x24 grid
GREENS_READ_SIZE = 576

#: called with each hole file as it is written
Progress = Callable[[Path], None]


@dataclass
class DumpStats:
    """Compression statistics over a dump, for `golf-dump`'s `meta.json`."""

    terrain: DecompressionStats
    greens: DecompressionStats

    @classmethod
    def empty(cls) -> "DumpStats":
        return cls(DecompressionStats(), DecompressionStats())


@dataclass
class _HoleTables:
    """What one hole's table entries hold, before its data is decompressed."""

    hole_idx: int
    par: int
    distance: int
    handicap: int
    scroll_limit: int
    green_x: int
    green_y: int
    tee_x: int
    tee_y: int
    flag_positions: list[dict]
    terrain_start_ptr: int
    terrain_end_ptr: int
    greens_ptr: int
    greens_size: int


def write_meta(output_dir: Path, rom_path: str, stats: DumpStats, courses: int) -> None:
    """Write a dump's compression statistics to meta.json, which golf-expand-dict reads."""
    global_meta = {
        "rom": rom_path,
        "total_courses": courses,
        "total_holes": courses * rom_utils.HOLES_PER_COURSE,
        "statistics": {
            "terrain": stats.terrain.to_dict(),
            "greens": stats.greens.to_dict(),
        },
    }
    with open(output_dir / "meta.json", "w") as f:
        json.dump(global_meta, f, indent=2)


def dump_us_courses(
    rom: RomReader,
    root: Path,
    stats: DumpStats | None = None,
    progress: Progress | None = None,
) -> None:
    """Dump the US ROM's three courses to `root/japan`, `root/us` and `root/uk`."""
    for course_idx, course in enumerate(rom_utils.COURSES):
        hole_offset = rom.annotate(f"course {course_idx} hole offset").read_fixed_byte(
            rom_utils.TABLE_COURSE_HOLE_OFFSET + course_idx
        )
        terrain_bank = rom.annotate(
            f"course {course_idx} terrain bank"
        ).read_fixed_byte(rom_utils.TABLE_COURSE_BANK_TERRAIN + course_idx)
        greens_bank = 3  # every course's greens share bank 3

        course_dir = _write_course(root, course, hole_offset, terrain_bank, greens_bank)
        terrain_decomp = TerrainDecompressor(rom)
        greens_decomp = GreensDecompressor(rom, greens_bank)

        for hole_in_course in range(rom_utils.HOLES_PER_COURSE):
            hole_idx = hole_offset + hole_in_course
            tables = _read_us_tables(rom, hole_idx)
            _dump_hole(
                rom,
                tables,
                course_dir,
                course["name"],
                hole_in_course + 1,
                terrain_bank,
                greens_bank,
                ATTR_TOTAL_BYTES,
                terrain_decomp,
                greens_decomp,
                stats,
                progress,
            )


def dump_jp_courses(
    rom: RomReader,
    root: Path,
    stats: DumpStats | None = None,
    progress: Progress | None = None,
) -> None:
    """Dump the JP ROM's five courses to `root/jp_japan` through `root/jp_uk`."""
    for course_idx, course in enumerate(jp_rom_utils.COURSES):
        hole_offset = rom.read_fixed_byte(
            jp_rom_utils.TABLE_COURSE_HOLE_OFFSET + course_idx
        )
        terrain_bank = rom.read_fixed_byte(
            jp_rom_utils.TABLE_COURSE_BANK_TERRAIN + course_idx
        )
        greens_bank = terrain_bank  # JP keeps each course's greens with its terrain

        course_dir = _write_course(root, course, hole_offset, terrain_bank, greens_bank)
        terrain_decomp = TerrainDecompressor(
            rom,
            horiz_addr=jp_rom_utils.TABLE_TERRAIN_HORIZ_TRANSITION,
            vert_addr=jp_rom_utils.TABLE_TERRAIN_VERT_CONTINUATION,
            dict_addr=jp_rom_utils.TABLE_TERRAIN_DICTIONARY,
        )
        greens_decomp = GreensDecompressor(
            rom,
            bank=greens_bank,
            horiz_addr=jp_rom_utils.TABLE_GREENS_HORIZ_TRANSITION,
            vert_addr=jp_rom_utils.TABLE_GREENS_VERT_CONTINUATION,
            dict_addr=jp_rom_utils.TABLE_GREENS_DICTIONARY,
            tables_in_fixed_bank=True,
        )

        for hole_in_course in range(jp_rom_utils.HOLES_PER_COURSE):
            hole_idx = hole_offset + hole_in_course
            tables = _read_jp_tables(rom, hole_idx)
            _dump_hole(
                rom,
                tables,
                course_dir,
                course["name"],
                hole_in_course + 1,
                terrain_bank,
                greens_bank,
                jp_rom_utils.JP_ATTR_BYTES,
                terrain_decomp,
                greens_decomp,
                stats,
                progress,
            )


def _write_course(
    root: Path, course: dict, hole_offset: int, terrain_bank: int, greens_bank: int
) -> Path:
    course_dir = root / course["name"]
    course_dir.mkdir(parents=True, exist_ok=True)
    course_meta = {
        "name": course["display_name"],
        "hole_offset": hole_offset,
        "terrain_bank": terrain_bank,
        "greens_bank": greens_bank,
    }
    with open(course_dir / "course.json", "w") as f:
        json.dump(course_meta, f, indent=2)
    return course_dir


def _read_us_tables(rom: RomReader, hole_idx: int) -> _HoleTables:
    def byte(table: int, label: str, index: int = hole_idx) -> int:
        return rom.annotate(f"global hole {hole_idx} {label}").read_fixed_byte(
            table + index
        )

    def word(table: int, label: str) -> int:
        return rom.annotate(f"global hole {hole_idx} {label}").read_fixed_word(
            table + hole_idx * 2
        )

    flag_positions = []
    for i in range(4):
        flag_y = byte(
            rom_utils.TABLE_FLAG_Y_OFFSET, f"flag {i + 1} Y", hole_idx * 4 + i
        )
        flag_x = byte(
            rom_utils.TABLE_FLAG_X_OFFSET, f"flag {i + 1} X", hole_idx * 4 + i
        )
        flag_positions.append({"x_offset": flag_x, "y_offset": flag_y})

    greens_ptr = word(rom_utils.TABLE_GREENS_PTR, "greens ptr")
    # The game decompresses until its output buffer is full, so the size only bounds
    # the read: up to the next hole's greens, or the worst case at a course boundary.
    greens_size = GREENS_READ_SIZE
    if hole_idx < rom_utils.TOTAL_HOLES - 1:
        next_greens_ptr = rom.annotate(
            f"global hole {hole_idx + 1} greens ptr (for size calc)"
        ).read_fixed_word(rom_utils.TABLE_GREENS_PTR + (hole_idx + 1) * 2)
        if next_greens_ptr > greens_ptr:
            greens_size = next_greens_ptr - greens_ptr

    return _HoleTables(
        hole_idx=hole_idx,
        par=byte(rom_utils.TABLE_PAR, "par"),
        distance=bcd_to_int(
            byte(rom_utils.TABLE_DISTANCE_100, "distance (100s)"),
            byte(rom_utils.TABLE_DISTANCE_10, "distance (10s)"),
            byte(rom_utils.TABLE_DISTANCE_1, "distance (1s)"),
        ),
        handicap=byte(rom_utils.TABLE_HANDICAP, "handicap"),
        scroll_limit=byte(rom_utils.TABLE_SCROLL_LIMIT, "scroll limit"),
        green_x=byte(rom_utils.TABLE_GREEN_X, "green X"),
        green_y=byte(rom_utils.TABLE_GREEN_Y, "green Y"),
        tee_x=byte(rom_utils.TABLE_TEE_X, "tee X"),
        tee_y=word(rom_utils.TABLE_TEE_Y, "tee Y"),
        flag_positions=flag_positions,
        terrain_start_ptr=word(rom_utils.TABLE_TERRAIN_START_PTR, "terrain start ptr"),
        terrain_end_ptr=word(rom_utils.TABLE_TERRAIN_END_PTR, "terrain end ptr"),
        greens_ptr=greens_ptr,
        greens_size=greens_size,
    )


def _read_jp_tables(rom: RomReader, hole_idx: int) -> _HoleTables:
    def fixed(table: int) -> int:
        return rom.read_fixed_byte(table + hole_idx)

    # The rest of the metadata is in switched bank $0B
    def byte(table: int, index: int = hole_idx) -> int:
        return jp_rom_utils.read_metadata_byte(rom, table, index)

    def word(table: int) -> int:
        return jp_rom_utils.read_metadata_word(rom, table, hole_idx)

    flag_positions = [
        {
            "x_offset": byte(jp_rom_utils.TABLE_FLAG_X_OFFSET, hole_idx * 4 + i),
            "y_offset": byte(jp_rom_utils.TABLE_FLAG_Y_OFFSET, hole_idx * 4 + i),
        }
        for i in range(4)
    ]
    return _HoleTables(
        hole_idx=hole_idx,
        par=fixed(jp_rom_utils.TABLE_PAR),
        distance=bcd_to_int(
            fixed(jp_rom_utils.TABLE_DISTANCE_100),
            fixed(jp_rom_utils.TABLE_DISTANCE_10),
            fixed(jp_rom_utils.TABLE_DISTANCE_1),
        ),
        handicap=fixed(jp_rom_utils.TABLE_HANDICAP),
        scroll_limit=byte(jp_rom_utils.TABLE_SCROLL_LIMIT),
        green_x=byte(jp_rom_utils.TABLE_GREEN_X),
        green_y=byte(jp_rom_utils.TABLE_GREEN_Y),
        tee_x=byte(jp_rom_utils.TABLE_TEE_X),
        tee_y=word(jp_rom_utils.TABLE_TEE_Y),
        flag_positions=flag_positions,
        terrain_start_ptr=word(jp_rom_utils.TABLE_TERRAIN_START_PTR),
        terrain_end_ptr=word(jp_rom_utils.TABLE_TERRAIN_END_PTR),
        greens_ptr=word(jp_rom_utils.TABLE_GREENS_PTR),
        greens_size=GREENS_READ_SIZE,
    )


def _dump_hole(
    rom: RomReader,
    tables: _HoleTables,
    course_dir: Path,
    course_name: str,
    hole_num: int,
    terrain_bank: int,
    greens_bank: int,
    attr_byte_count: int,
    terrain_decomp: TerrainDecompressor,
    greens_decomp: GreensDecompressor,
    stats: DumpStats | None,
    progress: Progress | None,
) -> None:
    if stats is not None:
        stats.terrain.set_hole_context(course_name, hole_num)
        stats.greens.set_hole_context(course_name, hole_num)
    label = f"global hole {tables.hole_idx}"

    terrain_compressed_size = tables.terrain_end_ptr - tables.terrain_start_ptr
    terrain_compressed = rom.annotate(
        f"{label} terrain data ({terrain_compressed_size} bytes)"
    ).read_prg(
        rom_utils.cpu_to_prg_switched(tables.terrain_start_ptr, terrain_bank),
        terrain_compressed_size,
    )
    # The attribute bytes follow the terrain data
    attr_bytes = rom.annotate(f"{label} attributes ({attr_byte_count} bytes)").read_prg(
        rom_utils.cpu_to_prg_switched(tables.terrain_end_ptr, terrain_bank),
        attr_byte_count,
    )
    terrain_rows = terrain_decomp.decompress(
        terrain_compressed, stats=stats.terrain if stats else None
    )
    terrain_height = len(terrain_rows)
    attr_rows = unpack_attributes(attr_bytes, (terrain_height + 1) // 2)

    greens_compressed = rom.annotate(
        f"{label} greens data ({tables.greens_size} bytes)"
    ).read_prg(
        rom_utils.cpu_to_prg_switched(tables.greens_ptr, greens_bank),
        tables.greens_size,
    )
    greens_rows = greens_decomp.decompress(
        greens_compressed, stats=stats.greens if stats else None
    )

    hole_data = {
        "hole": hole_num,
        "par": tables.par,
        "distance": tables.distance,
        "handicap": tables.handicap,
        "scroll_limit": tables.scroll_limit,
        "green": {"x": tables.green_x, "y": tables.green_y},
        "tee": {"x": tables.tee_x, "y": tables.tee_y},
        "flag_positions": tables.flag_positions,
        "terrain": {
            "width": TERRAIN_ROW_WIDTH,
            "height": terrain_height,
            "rows": format_hex_rows(terrain_rows),
        },
        "attributes": {
            "width": len(attr_rows[0]) if attr_rows else 11,
            "height": len(attr_rows),
            "rows": attr_rows,
        },
        "greens": {
            "width": 24,
            "height": len(greens_rows),
            "rows": format_hex_rows(greens_rows),
        },
        "_debug": {
            "terrain_ptr": f"${tables.terrain_start_ptr:04X}",
            "terrain_end_ptr": f"${tables.terrain_end_ptr:04X}",
            "terrain_compressed_size": terrain_compressed_size,
            "greens_ptr": f"${tables.greens_ptr:04X}",
            "attr_raw": " ".join(f"{b:02X}" for b in attr_bytes),
        },
    }
    path = course_dir / f"hole_{hole_num:02d}.json"
    with open(path, "w") as f:
        json.dump(hole_data, f, indent=2)
    if progress is not None:
        progress(path)
