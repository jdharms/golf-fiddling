"""
Scorecard course name: show "<NAME> COURSE" on the scorecard for every course
slot, in place of JAPAN / US / UK COURSE, and optionally replace the
"18H STROKE PLAY" title under it.

See docs/scorecard.md. `DrawScorecardScreen` ($AE76, bank 2) picks a
course-name handler from an inline jump table at $AEAA, keyed on CurrCourse;
each handler draws one `WriteNametableTiles` descriptor. Three writes:

1. The US and UK entries of the jump table are repointed at the Japan handler
   ($AFC2), so every slot draws the same name. The name is only true when every
   slot plays the same course, which is why the patch requires `course_mirrors`.
2. The Japan descriptor at $AFC8 is rewritten in place, centred on the row the
   way vanilla centres its own names. With the US and UK handlers unreachable,
   it may run past its vanilla 16 bytes into theirs ($AFD8-$AFFD).
3. The course-name row is red only where the attribute table says so. The
   whole top attribute row, $B9F0-$B9F7, sits inside one literal in the blank
   card's compressed nametable stream, so all eight bytes are rebuilt in place
   with palette 3 under every column the name uses. The frame tiles the wider
   band also covers use only colours 0 and 3, which are the same in every
   palette. The 36-hole match play tournament card has its own attributes,
   which already cover columns 2-29.

The optional title replaces what GolfGameMode $00's handler ($AFFE) draws. Its
vanilla descriptor at $B00D is 15 tiles, followed directly by the mode $01
handler, so the new one goes in the rest of the unreachable US and UK handler
bytes, after the longest possible name descriptor, and the handler's inline
`.dw` at $B00A is repointed at it. The title row is palette 2 across the whole
card, so no attributes change. Other game modes keep their own titles.

The unreachable bytes, $AFC8-$AFFD, hold a 20-tile name and a 26-tile title,
the width of the card's interior.

Both strings must be in the title font: A-Z, 0-9 and space. The course intro
scene has its own copy of the course name and is not changed.
"""

import string

from golf.core import rom_utils

from .byte_patch import BytePatch
from .composite import CompositePatch
from .multi_bank import COURSE_MIRRORS_PATCH

BANK = 2

DEFAULT_NAME = "RANDOM"
SUFFIX = " COURSE"

# The ($01, lo, hi) and ($02, lo, hi) entries of the course jump table, from
# the US entry's pointer through the UK entry's pointer.
DISPATCH_POINTERS_ADDR = 0xAEAE
JAPAN_HANDLER = 0xAFC2

DESCRIPTOR_ADDR = 0xAFC8
NAME_ROW_PPU = 0x2060  # row 3, column 0
ROW_TILES = 32

ATTRIBUTES_ADDR = 0xB9F0  # attribute row 0, PPU $23C0-$23C7
NAME_PALETTE = 3
MAX_TILES = 20

# The stroke play title: the inline `.dw` after the mode $00 handler's
# `JSR WriteNametableTiles`, and where the new descriptor goes.
TITLE_POINTER_ADDR = 0xB00A
TITLE_DESCRIPTOR_ADDR = DESCRIPTOR_ADDR + 4 + MAX_TILES  # $AFE0
TITLE_ROW_PPU = 0x2080  # row 4, column 0
MAX_TITLE_TILES = 26  # columns 3-28, the card's interior
UNREACHABLE_END = 0xAFFE  # the mode $00 handler
assert TITLE_DESCRIPTOR_ADDR + 4 + MAX_TITLE_TILES <= UNREACHABLE_END

TITLE_FONT_CHARS = string.ascii_uppercase + string.digits + " "

_VANILLA_DISPATCH_POINTERS = bytes([0xD8, 0xAF, 0x02, 0xEB, 0xAF])

# $AFC8-$AFFD: the Japan descriptor, then the US and UK handlers and descriptors.
_VANILLA_UNREACHABLE_REGION = bytes(
    [
        0x6A,
        0x20,
        0x0C,
        0x01,  # PPU $206A, width 12, 1 row
        0x13,
        0x0A,
        0x19,
        0x0A,
        0x17,
        0x24,  # JAPAN_
        0x0C,
        0x18,
        0x1E,
        0x1B,
        0x1C,
        0x0E,  # COURSE
        0x20,
        0x84,
        0xCE,
        0xDE,
        0xAF,
        0x60,  # $AFD8: JSR $CE84 / .dw $AFDE / RTS
        0x6B,
        0x20,
        0x09,
        0x01,  # PPU $206B, width 9, 1 row
        0x1E,
        0x1C,
        0x24,
        0x0C,
        0x18,
        0x1E,
        0x1B,
        0x1C,
        0x0E,  # US COURSE
        0x20,
        0x84,
        0xCE,
        0xF1,
        0xAF,
        0x60,  # $AFEB: JSR $CE84 / .dw $AFF1 / RTS
        0x6B,
        0x20,
        0x09,
        0x01,  # PPU $206B, width 9, 1 row
        0x1E,
        0x14,
        0x24,
        0x0C,
        0x18,
        0x1E,
        0x1B,
        0x1C,
        0x0E,  # UK COURSE
    ]
)
assert DESCRIPTOR_ADDR + len(_VANILLA_UNREACHABLE_REGION) == UNREACHABLE_END

_VANILLA_DESCRIPTOR_REGION = _VANILLA_UNREACHABLE_REGION[: 4 + MAX_TILES]
_VANILLA_TITLE_REGION = _VANILLA_UNREACHABLE_REGION[4 + MAX_TILES :]

# Columns 10-21 of row 3 are palette 3, sized for JAPAN COURSE.
_VANILLA_ATTRIBUTES = bytes([0x00, 0x00, 0xC0, 0xF0, 0xF0, 0x30, 0x00, 0x00])

_VANILLA_TITLE_POINTER = bytes([0x0D, 0xB0])


def _prg(cpu_addr: int) -> int:
    return rom_utils.cpu_to_prg_switched(cpu_addr, BANK)


def _check_title_font(text: str, what: str) -> None:
    bad = sorted(set(text) - set(TITLE_FONT_CHARS))
    if bad:
        raise ValueError(
            f"{what} contains characters the scorecard title font cannot render: "
            f"{''.join(bad)!r}. Allowed: A-Z, 0-9 and space"
        )


def course_name_text(name: str) -> str:
    """The full name as drawn: upper-cased, with " COURSE" appended.

    Raises ValueError for characters the title font lacks, or a name too long
    for its descriptor's space.
    """
    text = name.upper() + SUFFIX
    _check_title_font(text, "name")
    if len(text) > MAX_TILES:
        raise ValueError(
            f"name must be at most {MAX_TILES - len(SUFFIX)} characters "
            f"({MAX_TILES} with {SUFFIX.strip()!r}), got {len(name)}"
        )
    return text


def title_text(title: str) -> str:
    """The title as drawn: upper-cased. Raises ValueError if it cannot be drawn."""
    text = title.upper()
    _check_title_font(text, "title")
    if not 1 <= len(text) <= MAX_TITLE_TILES:
        raise ValueError(
            f"title must be 1-{MAX_TITLE_TILES} characters, got {len(text)}"
        )
    return text


def title_font_tiles(text: str) -> bytes:
    """Title font tile indexes: 0-9 are $00-$09, A-Z $0A-$23, space $24."""
    tiles = []
    for char in text:
        if char == " ":
            tiles.append(0x24)
        elif char in string.digits:
            tiles.append(int(char))
        else:
            tiles.append(0x0A + ord(char) - ord("A"))
    return bytes(tiles)


def first_column(text: str) -> int:
    """The column vanilla would start a course name at: 10 for JAPAN COURSE, 11 for US COURSE."""
    return (ROW_TILES - len(text)) // 2


def title_first_column(text: str) -> int:
    """The column vanilla would start a short title at: 9 for 18H STROKE PLAY and 18H MATCH PLAY.

    Vanilla rounds the other way from the course names, so this is its own rule.
    """
    return (ROW_TILES + 1 - len(text)) // 2


def _one_row_descriptor(dest: int, text: str) -> bytes:
    return bytes([dest & 0xFF, dest >> 8, len(text), 0x01]) + title_font_tiles(text)


def descriptor_bytes(text: str) -> bytes:
    """A one-row `WriteNametableTiles` descriptor drawing the name, centred on row 3."""
    return _one_row_descriptor(NAME_ROW_PPU + first_column(text), text)


def title_descriptor_bytes(text: str) -> bytes:
    """A one-row `WriteNametableTiles` descriptor drawing the title, centred on row 4."""
    return _one_row_descriptor(TITLE_ROW_PPU + title_first_column(text), text)


def attribute_bytes(text: str) -> bytes:
    """
    Attribute row 0, one byte per four columns, with palette 3 under the text.

    Bits 4-5 of each byte colour its lower-left 2x2 tiles, bits 6-7 its
    lower-right; the lower half is tile row 3. The upper half belongs to the
    row above, and keeps its vanilla value.
    """
    start = first_column(text)
    used = range(start, start + len(text))
    attributes = bytearray()
    for index, vanilla in enumerate(_VANILLA_ATTRIBUTES):
        value = vanilla & 0x0F
        for offset, shift in ((0, 4), (2, 6)):
            column = 4 * index + offset
            if column in used or column + 1 in used:
                value |= NAME_PALETTE << shift
        attributes.append(value)
    return bytes(attributes)


def scorecard_course_name_patches(
    name: str = DEFAULT_NAME, title: str | None = None
) -> list[BytePatch]:
    """The patches that draw "<name> COURSE" for every course slot, and the title if given."""
    text = course_name_text(name)
    descriptor = descriptor_bytes(text)
    handler = bytes([JAPAN_HANDLER & 0xFF, JAPAN_HANDLER >> 8])
    patches = [
        BytePatch(
            name="scorecard_course_name_dispatch",
            description="Point the US and UK course-name handlers at the Japan one",
            prg_offset=_prg(DISPATCH_POINTERS_ADDR),
            original=_VANILLA_DISPATCH_POINTERS,
            patched=handler + _VANILLA_DISPATCH_POINTERS[2:3] + handler,
        ),
        BytePatch(
            name="scorecard_course_name_descriptor",
            description=f"Draw {text!r} in place of 'JAPAN COURSE'",
            prg_offset=_prg(DESCRIPTOR_ADDR),
            original=_VANILLA_DESCRIPTOR_REGION[: len(descriptor)],
            patched=descriptor,
        ),
        BytePatch(
            name="scorecard_course_name_attributes",
            description="Colour the course-name row red under the new name",
            prg_offset=_prg(ATTRIBUTES_ADDR),
            original=_VANILLA_ATTRIBUTES,
            patched=attribute_bytes(text),
        ),
    ]
    if title is not None:
        drawn = title_text(title)
        title_descriptor = title_descriptor_bytes(drawn)
        patches += [
            BytePatch(
                name="scorecard_course_name_title_descriptor",
                description=f"Draw {drawn!r} in the unreachable US and UK course-name handlers",
                prg_offset=_prg(TITLE_DESCRIPTOR_ADDR),
                original=_VANILLA_TITLE_REGION[: len(title_descriptor)],
                patched=title_descriptor,
            ),
            BytePatch(
                name="scorecard_course_name_title_pointer",
                description="Point the stroke play title at the new descriptor",
                prg_offset=_prg(TITLE_POINTER_ADDR),
                original=_VANILLA_TITLE_POINTER,
                patched=bytes(
                    [TITLE_DESCRIPTOR_ADDR & 0xFF, TITLE_DESCRIPTOR_ADDR >> 8]
                ),
            ),
        ]
    return patches


def scorecard_course_name_patch(
    name: str = DEFAULT_NAME, title: str | None = None
) -> CompositePatch[BytePatch]:
    description = (
        f"Show {course_name_text(name)!r} on the scorecard for every course slot"
    )
    if title is not None:
        description += f", titled {title_text(title)!r} in stroke play"
    return CompositePatch(
        name="scorecard_course_name",
        description=description,
        patches=scorecard_course_name_patches(name, title),
        requires=(COURSE_MIRRORS_PATCH,),
    )
