"""
The pre-hole signpost card: replaying it out of the ROM, and reading art back in.

`LC_AC2F_DrawSignpostCard` (bank 12 `$AC2F`) loads the signpost CHR, picks one of
five banner blobs and draws the hole number / par / distance with the big 2x2-tile
digit font.  `build_screen` reproduces that; `convert_banner` is the return leg,
turning an edited screen image back into the banner's nametable bytes plus the CHR
tiles that do not exist yet.  See docs/prehole_signpost.md.

The banner bodies are **raw nametable bytes**, not `$D4C3`-compressed, so new
wording that reuses existing tiles is a plain byte swap.  New *pixels* are the
expensive half: those need pattern-table space and a way to get there.
"""

from dataclasses import dataclass, field

from golf.core.aseprite import AsepriteFile
from golf.core.graphics_codec import VideoMemory, load_graphics_table
from golf.core.palettes import NES_SYSTEM_PALETTE

BANK = 12
BANNER_TABLE = 0xAD86  # 5 x 6-byte WriteNametableTiles descriptors
PALETTE_ADDR = 0xADC4  # JapanSignpostData - shared by all 5 banners
DIGIT_PTR_TABLE = 0xB01C  # 11 entries (digits 0-9, then the narrow "1" prefix)
DIGIT_COUNT = 11

CHR_BANK = 5
CHR_TABLES = (
    0xA69F,
    0xA6DD,
    0xB3B3,
)  # -> $0000, $1000 (font/texture), $2000 (blank card+attrs)

# The background pattern table the card's tiles come from.
PATTERN_BASE = 0x1000

COURSE_HOLE_OFFSET = 0xDBBB
PAR = 0xDD05
DISTANCE = (0xDD3B, 0xDD71, 0xDDA7)  # hundreds, tens, ones

BANNER_JAPAN, BANNER_US, BANNER_UK, BANNER_LONG_DRIVE, BANNER_NEAREST_PIN = range(5)

BANNER_NAMES = {
    "japan": BANNER_JAPAN,
    "us": BANNER_US,
    "uk": BANNER_UK,
    "long-drive": BANNER_LONG_DRIVE,
    "nearest-pin": BANNER_NEAREST_PIN,
}


def parse_banner(text: str) -> int:
    """A banner name from `BANNER_NAMES`, or its index as a number."""
    if text in BANNER_NAMES:
        return BANNER_NAMES[text]
    return int(text, 0)


NAMETABLE = 0x2000
ATTRIBUTES = 0x23C0
SCREEN_COLS = 32
SCREEN_ROWS = 30


@dataclass(frozen=True)
class BannerDescriptor:
    """One entry of the `$AD86` table - a `WriteNametableTiles` call's arguments."""

    index: int
    dest: int
    header: int
    rows: int
    pointer: int

    @property
    def width(self) -> int:
        return self.header & 0x3F

    @property
    def col(self) -> int:
        return (self.dest - NAMETABLE) % SCREEN_COLS

    @property
    def row(self) -> int:
        return (self.dest - NAMETABLE) // SCREEN_COLS

    @property
    def length(self) -> int:
        return self.width * self.rows


def chr_rows(pattern: bytes):
    """A 16-byte pattern -> 8 rows of 8 two-bit values."""
    return [
        [
            ((pattern[y] >> (7 - x)) & 1) | (((pattern[y + 8] >> (7 - x)) & 1) << 1)
            for x in range(8)
        ]
        for y in range(8)
    ]


def freeable_patterns(rom, reference: VideoMemory, target: BannerDescriptor) -> dict:
    """Pattern slots this screen does not need, and what makes them spare.

    Three tiers, loosest first: patterns that are blank, patterns the drawn
    screen never references, and patterns referenced only by the *other* four
    banner blobs - reclaimable as soon as those banners stop being drawn, which
    is the whole premise of a single "RANDOM COURSE" sign.
    """
    patterns = pattern_tiles(reference)
    blank = {index for index, pattern in enumerate(patterns) if not any(pattern)}

    target_cells = {
        (target.col + col, target.row + row)
        for row in range(target.rows)
        for col in range(target.width)
    }
    rest_of_screen = {
        reference.data[NAMETABLE + row * SCREEN_COLS + col]
        for row in range(SCREEN_ROWS)
        for col in range(SCREEN_COLS)
        if (col, row) not in target_cells
    }
    on_screen = rest_of_screen | {
        reference.data[NAMETABLE + row * SCREEN_COLS + col] for col, row in target_cells
    }

    other_banners = set()
    for index in range(len(BANNER_NAMES)):
        if index != target.index:
            other_banners.update(
                read_banner_body(rom, read_banner_descriptor(rom, index))
            )

    return {
        "blank": sorted(blank),
        "unreferenced_by_screen": sorted(set(range(256)) - on_screen - blank),
        "only_other_banners": sorted(other_banners - rest_of_screen - blank),
    }


def read_banner_descriptor(rom, index: int) -> BannerDescriptor:
    dest_lo, dest_hi, header, rows, ptr_lo, ptr_hi = rom.read_switched(
        BANNER_TABLE + index * 6, BANK, 6
    )
    return BannerDescriptor(
        index=index,
        dest=dest_lo | (dest_hi << 8),
        header=header,
        rows=rows,
        pointer=ptr_lo | (ptr_hi << 8),
    )


def read_banner_body(rom, descriptor: BannerDescriptor) -> bytes:
    return bytes(rom.read_switched(descriptor.pointer, BANK, descriptor.length))


def read_descriptor(rom, address: int) -> BannerDescriptor:
    """Any `WriteNametableTiles` descriptor, wherever it lives in bank 12."""
    dest_lo, dest_hi, header, rows, ptr_lo, ptr_hi = rom.read_switched(address, BANK, 6)
    return BannerDescriptor(
        index=-1,
        dest=dest_lo | (dest_hi << 8),
        header=header,
        rows=rows,
        pointer=ptr_lo | (ptr_hi << 8),
    )


def apply_descriptor(rom, vram: VideoMemory, descriptor: BannerDescriptor) -> None:
    """Run one descriptor's transfer, wherever it points - a nametable or, with
    a destination inside `$0000`-`$1FFF`, the pattern table itself."""
    write_rect(
        vram,
        descriptor.dest,
        descriptor.width,
        descriptor.rows,
        read_banner_body(rom, descriptor),
    )


def banner_index(course: int, hole_match_status: int) -> int:
    """`$AC5D`-`$AC69`: a non-zero `HoleMatchStatus` overwrites X with
    `status + 2` entirely, so `CurrCourse` is discarded and the contest banners
    are course-independent."""
    return hole_match_status + 2 if hole_match_status else course


def write_rect(vram: VideoMemory, ppu: int, width: int, rows: int, data) -> None:
    """`WriteNametableTiles` (`$CE84`): literal bytes, one nametable row per row."""
    for row in range(rows):
        for col in range(width):
            vram.write(ppu + row * SCREEN_COLS + col, data[row * width + col])


def load_scene_chr(rom, vram: VideoMemory | None = None) -> VideoMemory:
    """The three `LoadCompressedGraphics` calls at the top of `LC_AC2F`."""
    if vram is None:
        vram = VideoMemory()
    for addr in CHR_TABLES:
        load_graphics_table(rom, CHR_BANK, addr, vram)
    return vram


def digit_tiles(rom, digit: int) -> bytes:
    """`LC_AD0D_BufferBigDigit`: digit -> (TL, TR, BL, BR)."""
    ptr_lo, ptr_hi = rom.read_switched(DIGIT_PTR_TABLE + digit * 2, BANK, 2)
    return bytes(rom.read_switched(ptr_lo | (ptr_hi << 8), BANK, 4))


def write_big_digits(rom, vram: VideoMemory, dest: int, digits) -> None:
    """`LC_AD31_FlushBigDigitBuffer`: lay out N digits' 2x2 blocks side by side."""
    blocks = [digit_tiles(rom, d) for d in digits]
    top = [t for tl, tr, bl, br in blocks for t in (tl, tr)]
    bottom = [t for tl, tr, bl, br in blocks for t in (bl, br)]
    write_rect(vram, dest, len(digits) * 2, 2, top + bottom)


def hole_number_digits(hole_number_0based: int):
    """`$AC84`-`$ACAF`: `HoleNumber` is 0-based; 10 is the narrow '1' glyph."""
    if hole_number_0based < 9:
        return 0x2174, [hole_number_0based + 1]
    return 0x2172, [10, hole_number_0based - 9]


def build_screen(
    rom,
    course: int,
    hole_1based: int,
    hole_match_status: int = 0,
    contest_palette_patch: bool = False,
):
    """Rebuild one signpost screen; returns its video memory and 32-byte palette."""
    vram = load_scene_chr(rom)

    descriptor = read_banner_descriptor(rom, banner_index(course, hole_match_status))
    write_rect(
        vram,
        descriptor.dest,
        descriptor.width,
        descriptor.rows,
        read_banner_body(rom, descriptor),
    )

    hole0 = hole_1based - 1
    dest, digits = hole_number_digits(hole0)
    write_big_digits(rom, vram, dest, digits)

    base = rom.read_fixed(COURSE_HOLE_OFFSET, 3)[course]
    hole_idx = base + hole0
    par = rom.read_fixed(PAR, 54)[hole_idx]
    write_big_digits(rom, vram, 0x21D4, [par])

    hundreds, tens, ones = (rom.read_fixed(a, 54)[hole_idx] for a in DISTANCE)
    write_big_digits(rom, vram, 0x222A, [hundreds, tens, ones])

    palette = bytearray(rom.read_switched(PALETTE_ADDR, BANK, 32))
    if contest_palette_patch:
        palette[0x047D - 0x0476] = 0x12
    return vram, palette


def subpalette_at(vram: VideoMemory, col: int, row: int) -> int:
    """Which of the four palettes the attribute table assigns to a tile."""
    attribute = vram.data[ATTRIBUTES + (row // 4) * 8 + (col // 4)]
    shift = ((row % 4) // 2) * 4 + ((col % 4) // 2) * 2
    return (attribute >> shift) & 3


def render_screen(vram: VideoMemory, palette) -> list:
    """The screen as 240 rows of 256 NES colour values."""
    pixels = []
    for row in range(SCREEN_ROWS):
        lines = [[0] * (SCREEN_COLS * 8) for _ in range(8)]
        for col in range(SCREEN_COLS):
            tile = vram.data[NAMETABLE + row * SCREEN_COLS + col]
            sub = subpalette_at(vram, col, row)
            for y, values in enumerate(vram.tile(tile, PATTERN_BASE)):
                for x, value in enumerate(values):
                    lines[y][col * 8 + x] = (
                        palette[0] if value == 0 else palette[sub * 4 + value]
                    )
        pixels.extend(lines)
    return pixels


def tile_to_chr(values) -> bytes:
    """8 rows of 8 two-bit values -> the NES's planar 16-byte pattern."""
    low = bytearray(8)
    high = bytearray(8)
    for y, row in enumerate(values):
        for x, value in enumerate(row):
            low[y] |= (value & 1) << (7 - x)
            high[y] |= ((value >> 1) & 1) << (7 - x)
    return bytes(low) + bytes(high)


def pattern_tiles(vram: VideoMemory, base: int = PATTERN_BASE) -> list:
    """The 256 raw 16-byte patterns of one table."""
    return [bytes(vram.data[base + i * 16 : base + i * 16 + 16]) for i in range(256)]


# ---------------------------------------------------------------------------
# Reading art back in
# ---------------------------------------------------------------------------


@dataclass
class TileImport:
    """One 8x8 cell of an edited banner."""

    col: int  # screen coordinates
    row: int
    chr_bytes: bytes
    subpalette: int
    tile: int | None = None  # existing pattern index, once resolved
    unchanged: bool = False

    @property
    def is_new(self) -> bool:
        return self.tile is None


@dataclass
class BannerImport:
    descriptor: BannerDescriptor
    tiles: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    outside: list = field(default_factory=list)  # changed tiles beyond the banner

    @property
    def new_patterns(self) -> dict:
        """Distinct new CHR patterns -> the banner cells that want them."""
        out: dict[bytes, list] = {}
        for tile in self.tiles:
            if tile.is_new:
                out.setdefault(tile.chr_bytes, []).append(tile)
        return out

    def nametable(self, placement: dict | None = None) -> bytes:
        """The banner's `width * rows` raw bytes.

        `placement` maps a new CHR pattern to the pattern index it will occupy;
        without it, a banner that needs new art cannot be serialised.
        """
        placement = placement or {}
        body = bytearray()
        for tile in self.tiles:
            index = tile.tile
            if index is None:
                index = placement.get(tile.chr_bytes)
            if index is None:
                raise ValueError(
                    f"tile at column {tile.col}, row {tile.row} needs new CHR "
                    "and has no assigned pattern index"
                )
            body.append(index)
        return bytes(body)


def _colour_lookup(palette) -> dict:
    """NES colour value -> the 2-bit value that draws it, per subpalette.

    Keyed by RGB rather than by palette value: `$20` and `$30` are the same
    white, and an artist picking one swatch or the other must mean the same
    pixel.
    """
    table = []
    background = NES_SYSTEM_PALETTE[palette[0] & 0x3F]
    for sub in range(4):
        entries = {background: 0}
        for value in range(1, 4):
            rgb = NES_SYSTEM_PALETTE[palette[sub * 4 + value] & 0x3F]
            entries.setdefault(rgb, value)
        table.append(entries)
    return table


def convert_banner(
    screen,
    reference: VideoMemory,
    palette,
    descriptor: BannerDescriptor,
) -> BannerImport:
    """Read an edited screen back into `descriptor`'s banner.

    `screen` is 240 rows of 256 RGB triples - whatever the artist drew.
    `reference` supplies the pattern table to match against and the attribute
    table that decides each cell's three usable colours.
    """
    result = BannerImport(descriptor=descriptor)
    lookup = _colour_lookup(palette)
    patterns = pattern_tiles(reference)
    by_pattern: dict[bytes, int] = {}
    for index, pattern in enumerate(patterns):
        by_pattern.setdefault(pattern, index)

    for row_offset in range(descriptor.rows):
        for col_offset in range(descriptor.width):
            col = descriptor.col + col_offset
            row = descriptor.row + row_offset
            sub = subpalette_at(reference, col, row)
            entries = lookup[sub]

            values = []
            illegal = []
            for y in range(8):
                line = []
                for x in range(8):
                    rgb = screen[row * 8 + y][col * 8 + x]
                    value = entries.get(rgb)
                    if value is None:
                        illegal.append((col * 8 + x, row * 8 + y, rgb))
                        value = 0
                    line.append(value)
                values.append(line)

            if illegal:
                x, y, rgb = illegal[0]
                result.errors.append(
                    f"tile at column {col}, row {row} uses {len(illegal)} pixel(s) "
                    f"outside palette {sub} "
                    f"({', '.join(f'${palette[sub * 4 + v] & 0x3F:02X}' for v in range(1, 4))} "
                    f"on ${palette[0] & 0x3F:02X}); first at pixel ({x}, {y}) = rgb{rgb}"
                )

            chr_bytes = tile_to_chr(values)
            original = reference.data[NAMETABLE + row * SCREEN_COLS + col]
            tile = TileImport(col=col, row=row, chr_bytes=chr_bytes, subpalette=sub)
            if patterns[original] == chr_bytes:
                # Unchanged cell: keep the byte the ROM already had, so an
                # untouched region round-trips exactly even where two pattern
                # slots hold identical art.
                tile.tile = original
                tile.unchanged = True
            else:
                tile.tile = by_pattern.get(chr_bytes)
            result.tiles.append(tile)

    return result


def free_pattern_slots(rom, reference: VideoMemory, kept_tiles) -> list:
    """Pattern indices the signpost screen stops needing once a banner changes.

    Everything the screen draws outside the banner has to keep its tiles, and so
    do the banner cells whose art is unchanged.  What is left over is the other
    banners' wordmarks - unique letter art that nothing else references.

    `reference` is one hole's card, but the hole number, par and yardage change
    from hole to hole, so every big-digit record is kept whether or not this
    card happens to draw it.
    """
    descriptor = read_banner_descriptor(rom, BANNER_JAPAN)
    banner_cells = {
        (descriptor.col + col, descriptor.row + row)
        for row in range(descriptor.rows)
        for col in range(descriptor.width)
    }
    needed = {
        reference.data[NAMETABLE + row * SCREEN_COLS + col]
        for row in range(SCREEN_ROWS)
        for col in range(SCREEN_COLS)
        if (col, row) not in banner_cells
    }
    needed.update(
        tile for digit in range(DIGIT_COUNT) for tile in digit_tiles(rom, digit)
    )
    needed.update(tile for tile in kept_tiles if tile is not None)
    return sorted(set(range(256)) - needed)


def allocate_patterns(free: list, count: int) -> list:
    """Lay `count` new patterns into runs of free slots, largest run first.

    `WriteNametableTiles` advances its destination by one nametable row - `$20`
    bytes - per row, which over the pattern table is exactly two tiles.  So a
    run has to start on an even tile index and cover an even number of them,
    and its row count may not exceed the 32-byte width (`$CEE8` abandons the
    transfer when width < rows), capping one descriptor at 64 tiles.
    """
    runs = []
    for slot in free:
        if runs and slot == runs[-1][0] + runs[-1][1]:
            runs[-1][1] += 1
        else:
            runs.append([slot, 1])

    usable = []
    for start, length in runs:
        if start % 2:  # an odd start wastes its first slot
            start, length = start + 1, length - 1
        length -= length % 2
        while length > 0:
            take = min(length, 64)
            usable.append((start, take))
            start, length = start + take, length - take

    chunks = []
    remaining = count
    for start, length in sorted(usable, key=lambda run: -run[1]):
        if remaining <= 0:
            break
        take = min(length, remaining if remaining % 2 == 0 else remaining + 1)
        chunks.append((start, take))
        remaining -= take
    if remaining > 0:
        raise ValueError(
            f"{count} new patterns do not fit: {sum(n for _, n in usable)} usable "
            "slots, none of the runs long enough"
        )
    return sorted(chunks)


@dataclass
class EditedScreen:
    """An artist's export, reduced to what the NES can actually hold."""

    pixels: list  # 240 rows of 256 RGB triples
    scale: int  # the canvas zoom the artist worked at
    ragged: list  # NES pixels whose zoom x zoom block was not one colour
    source: AsepriteFile


def screen_from_aseprite(path) -> EditedScreen:
    """Read a `.aseprite` export of the whole screen.

    The canvas is the 256x240 screen at an integer zoom, so every zoom x zoom
    block has to be a single colour.  Anything finer is detail the hardware
    cannot show; it is collected rather than quietly averaged away, because the
    artist needs to be told which marks to redraw.
    """
    ase = AsepriteFile.read(path)
    scale, remainder = divmod(ase.width, SCREEN_COLS * 8)
    scale_y, remainder_y = divmod(ase.height, SCREEN_ROWS * 8)
    if remainder or remainder_y or scale != scale_y or scale < 1:
        raise ValueError(
            f"canvas is {ase.width}x{ase.height}; expected the 256x240 NES screen "
            "at an integer zoom (256x240, 512x480, 768x720, ...)"
        )

    colours = [
        (entry[0], entry[1], entry[2]) if entry[3] else None for entry in ase.palette
    ]
    flat = ase.composite()

    pixels = []
    ragged = []
    for y in range(SCREEN_ROWS * 8):
        line = []
        for x in range(SCREEN_COLS * 8):
            block = {
                flat[(y * scale + dy) * ase.width + x * scale + dx]
                for dy in range(scale)
                for dx in range(scale)
            }
            if len(block) > 1:
                ragged.append((x, y))
            index = min(block)
            rgb = colours[index] if index < len(colours) else None
            if rgb is None:
                raise ValueError(
                    f"pixel ({x}, {y}) uses palette index {index}, which is "
                    "transparent or undefined - the screen must be fully painted"
                )
            line.append(rgb)
        pixels.append(line)
    return EditedScreen(pixels=pixels, scale=scale, ragged=ragged, source=ase)


def changed_tiles(screen, reference: VideoMemory, palette) -> list:
    """Every screen cell whose pixels differ from the ROM's own render."""
    rendered = render_screen(reference, palette)
    changed = []
    for row in range(SCREEN_ROWS):
        for col in range(SCREEN_COLS):
            for y in range(8):
                for x in range(8):
                    expected = NES_SYSTEM_PALETTE[
                        rendered[row * 8 + y][col * 8 + x] & 0x3F
                    ]
                    if screen[row * 8 + y][col * 8 + x] != expected:
                        changed.append((col, row))
                        break
                else:
                    continue
                break
    return changed
