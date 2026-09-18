"""
Title menu trim patch.

The title menu chain is pure data: entries can be removed, retitled and
re-pointed without touching a single instruction, because every menu is
described by four parallel tables in bank 12. See `docs/menu_system.md` for the
full layout.

What this patch does:

  * Menus $00 (main), $01 (1/2 PLAYER) and $02 (course select) share one
    two-line static-text header of three words, drawn where vanilla menu $02
    draws "PLEASE SELECT" / "COURSE".
  * Menu $00 keeps only STROKE PLAY and CLUB HOUSE.
  * Menu $02 offers a single option, RANDOM COURSE, which selects course 0
    (vanilla JAPAN COURSE).
  * Menu $15 (club house) keeps only REGISTER NAME, CHOOSE CLUBS, OPTIONS,
    TRAINING and CLEAR SAVED DATA.

Nothing is relocated. A text list is `count` followed by `count` 2-byte entry
pointers, so shortening a list means writing a smaller count and rewriting the
pointers that stay - the bytes past the new count are never read. The same is
true of `MenuSubmenuIdData`, the parallel one-byte-per-selection list of
destinations.

Header
------

The header's lines are exactly as wide as vanilla's, at the same positions:
line 1 is 13 characters at column 4, row $0A ("PLEASE SELECT"), line 2 is 6
characters at column 4, row $0C ("COURSE"). Each word is padded to a 6-column
slot, so words 1 and 2 always start at columns 4 and 11:

  line 1: word1.ljust(6) + " " + word2.ljust(6)
  line 2: word3.ljust(6)

Matching vanilla's span matters because `SetMenuEntryPalette` sets palette 1
on every 2x2 attribute cell the entry covers. An entry starting at column 3
would share a cell with the box border at column 2 and recolour it.

The header list and its line 1 entry live in the 26 bytes freed by the removed
MATCH,PLAY and TOURNAMENT entries:

  $8BB7  02 BC 8B 5C 8C            list: 2 entries, at $8BBC and $8C5C
  $8BBC  04 0A <13 chars> FF       line 1

Line 2 reuses the vanilla "COURSE" entry at $8C5C, overwriting its 6
characters. Its only reference is list $8C57, which after this patch is read
only by menus $06, $0B, $0F and $12, all unreachable. The three menus'
`MenuTextListPtrTable` static pointers are repointed at $8BB7. Every other menu
keeps the shared "PLEASE SELECT" list at $8B8D.

Course select
-------------

Menu $02's options list $8C65 is shared only with the unreachable menus $06,
$0B, $0F and $12. Its count drops to 1 and its first entry, US COURSE at $8C6C,
is overwritten with RANDOM COURSE, which runs 4 bytes into the unused JAPAN
COURSE entry. At column 12, row $0E the entry, its cursor tiles on rows $0D and
$0F, and its right cursor sprite at column 25 all land on blank background.

`ApplyCourseSelection` ($89E1) maps `CurrentMenuSelection + 1` through an
inline `LookupInlineByteTable` table at $89EA: 1 -> 1 (US), 2 -> 0 (JAPAN),
3 -> 2 (UK). With one option the key is always 1, so its value at $89EB
becomes 0 and `CurrCourse` is 0. The handler then calls $D939 as usual, which
goes to CONTINUE/NEW GAME only when a saved stroke-play game exists for that
slot.

Other wrinkles
--------------

1. Each entry carries its own Y coordinate, so removing an entry from the
   middle of a list leaves a visual gap. The retained entries below a removed
   one move up: CLUB HOUSE from row $14 to $10; club house TRAINING from $12
   to $0C and CLEAR SAVED DATA from $16 to $0E.

2. `ApplyPlayModeSelection` ($89A2), menu $00's choice handler, keys off the
   *selection index*: `sel < 2` sets `GolfGameMode = sel * 4`. CLUB HOUSE is
   index 1 here and would set `GolfGameMode = $04` (match play) on the way in,
   so the guard is `CMP #$01` and only STROKE PLAY writes the mode. The handler
   is shared with menu $09, which is unreachable without TOURNAMENT.

Byte edits, all in bank 12:

  $8BB7  (MATCH,PLAY + TOURNAMENT) -> header list   header, line 1
  $8C5E  "COURSE"                  -> word 3         header, line 2
  $8B35  8D 8B                     -> B7 8B          menu $00 static list ptr
  $8B39  8D 8B                     -> B7 8B          menu $01 static list ptr
  $8B3D  57 8C                     -> B7 8B          menu $02 static list ptr
  $8BA0  04 A9 8B B7 8B            -> 02 A9 8B D1 8B  main options: 2 entries
  $8ACE  01 05                     -> 01 15          main destinations
  $8BD1  0C 14                     -> 0C 10          CLUB HOUSE row
  $89AA  C9 02                     -> C9 01          play-mode guard
  $8C65  03                        -> 01             course select: 1 entry
  $8C6C  (US COURSE + 4 bytes)     -> RANDOM COURSE  course select entry
  $89EB  01                        -> 00             selection 0 -> course 0
  $8D64  09 77 8D ... AF 8D        -> 05 77 8D ... F1 8D  club house: 5 entries
  $8B00  81 82 83 84 85            -> 81 82 83 87 89 club house destinations
  $8DD1  28 12                     -> 28 0C          TRAINING row
  $8DF1  28 16                     -> 28 0E          CLEAR SAVED DATA row
"""

import string
from collections.abc import Sequence

from .byte_patch import BytePatch
from .composite import CompositePatch

# Bank 12 holds the whole title menu system.
_BANK12_PRG_BASE = 12 * 0x4000


def _prg(cpu_addr: int) -> int:
    """Bank 12 CPU address -> absolute PRG offset."""
    return _BANK12_PRG_BASE + (cpu_addr - 0x8000)


# Characters the menu font can actually render. LookupInlineRangeTable ($8A56)
# maps 'A'-'Z' and '0'-'9' to char+$70, plus four punctuation singles; anything
# else falls through to tile $00, which is blank.
RENDERABLE_CHARS = string.ascii_uppercase + string.digits + ".$?_"

DEFAULT_WORDS = ("OPEN", "GOLF", "RANDO")
MIN_WORD_LENGTH = 4
MAX_WORD_LENGTH = 6

# Vanilla menu $02's "PLEASE SELECT" / "COURSE" positions.
HEADER_X = 0x04
HEADER_LINE1_Y = 0x0A

# Header list and its line 1 entry, in the space freed by the removed
# MATCH,PLAY and TOURNAMENT entries.
_HEADER_LIST_ADDR = 0x8BB7
_HEADER_LINE1_ADDR = 0x8BBC  # _HEADER_LIST_ADDR + 5 (count byte + two pointers)
# Line 2 is the vanilla "COURSE" entry; only its characters change.
_HEADER_LINE2_ADDR = 0x8C5C
_HEADER_LINE2_CHARS_ADDR = _HEADER_LINE2_ADDR + 2

# Original bytes of the region the header list overwrites: the MATCH,PLAY
# entry record plus the first 8 bytes of the TOURNAMENT one.
_HEADER_LIST_ORIGINAL = bytes(
    [
        0x0C,
        0x10,
        0x4D,
        0x41,
        0x54,
        0x43,
        0x48,
        0x2C,  # $8BB7 "MATCH,"
        0x50,
        0x4C,
        0x41,
        0x59,
        0xFF,  #       "PLAY" $FF
        0x0C,
        0x12,
        0x54,
        0x4F,
        0x55,
        0x52,
        0x4E,
        0x41,  # $8BC4 "TOURNA"...
    ]
)

RANDOM_COURSE_TEXT = "RANDOM COURSE"
_COURSE_OPTION_ADDR = 0x8C6C

# US COURSE's entry record plus the first 4 bytes of JAPAN COURSE's.
_COURSE_OPTION_ORIGINAL = bytes(
    [
        0x0C,
        0x0E,
        0x55,
        0x53,
        0x20,
        0x43,
        0x4F,
        0x55,  # $8C6C "US COU"
        0x52,
        0x53,
        0x45,
        0xFF,  #       "RSE" $FF
        0x0C,
        0x10,
        0x4A,
        0x41,  # $8C78 "JA"...
    ]
)


def normalize_words(words: str | Sequence[str] | None = None) -> tuple[str, str, str]:
    """
    Validate header words and return them uppercased.

    Args:
        words: three words, as a sequence or one whitespace-separated string.
            Each is MIN_WORD_LENGTH-MAX_WORD_LENGTH characters from
            RENDERABLE_CHARS. Defaults to DEFAULT_WORDS.
    """
    if words is None:
        words = DEFAULT_WORDS
    elif isinstance(words, str):
        words = words.split()
    words = [word.upper() for word in words]

    if len(words) != len(DEFAULT_WORDS):
        raise ValueError(
            f"words must be exactly {len(DEFAULT_WORDS)} words, got {len(words)}: {words!r}"
        )
    for word in words:
        if not MIN_WORD_LENGTH <= len(word) <= MAX_WORD_LENGTH:
            raise ValueError(
                f"each word must be {MIN_WORD_LENGTH}-{MAX_WORD_LENGTH} characters, "
                f"got {word!r} ({len(word)})"
            )
        bad = sorted(set(word) - set(RENDERABLE_CHARS))
        if bad:
            raise ValueError(
                f"word {word!r} contains characters the menu font cannot render: "
                f"{''.join(bad)!r}. Allowed: {RENDERABLE_CHARS}"
            )
    first, second, third = words
    return first, second, third


def header_lines(words: str | Sequence[str] | None = None) -> tuple[str, str]:
    """The header's two lines, each word padded to a MAX_WORD_LENGTH slot."""
    first, second, third = normalize_words(words)
    return (
        f"{first.ljust(MAX_WORD_LENGTH)} {second.ljust(MAX_WORD_LENGTH)}",
        third.ljust(MAX_WORD_LENGTH),
    )


def menu_trim_patches(words: str | Sequence[str] | None = None) -> list[BytePatch]:
    """
    Build the menu trim patch set.

    Args:
        words: the header's three words; see normalize_words.

    Returns:
        The patches in application order.
    """
    line1, line2 = header_lines(words)

    header_list = bytes(
        [
            0x02,  # count: two entries
            _HEADER_LINE1_ADDR & 0xFF,
            _HEADER_LINE1_ADDR >> 8,
            _HEADER_LINE2_ADDR & 0xFF,
            _HEADER_LINE2_ADDR >> 8,
            HEADER_X,
            HEADER_LINE1_Y,
        ]
        + [ord(c) for c in line1]
        + [0xFF]
    )
    assert len(header_list) == len(_HEADER_LIST_ORIGINAL)

    course_option = bytes([0x0C, 0x0E] + [ord(c) for c in RANDOM_COURSE_TEXT] + [0xFF])
    assert len(course_option) == len(_COURSE_OPTION_ORIGINAL)

    header_ptr = bytes([_HEADER_LIST_ADDR & 0xFF, _HEADER_LIST_ADDR >> 8])

    return [
        BytePatch(
            name="menu_trim_header_list",
            description=f"Shared header list for menus $00-$02, with line 1 {line1!r}, in the space freed by the removed main-menu entries",
            prg_offset=_prg(_HEADER_LIST_ADDR),
            original=_HEADER_LIST_ORIGINAL,
            patched=header_list,
        ),
        BytePatch(
            name="menu_trim_header_line2",
            description=f"Header line 2 {line2!r}, over the characters of the 'COURSE' entry",
            prg_offset=_prg(_HEADER_LINE2_CHARS_ADDR),
            original=b"COURSE",
            patched=line2.encode("ascii"),
        ),
        BytePatch(
            name="menu_trim_header_ptr_menu_00",
            description="Point menu $00's static text list at the header",
            prg_offset=_prg(0x8B35),
            original=bytes([0x8D, 0x8B]),
            patched=header_ptr,
        ),
        BytePatch(
            name="menu_trim_header_ptr_menu_01",
            description="Point menu $01's static text list at the header",
            prg_offset=_prg(0x8B39),
            original=bytes([0x8D, 0x8B]),
            patched=header_ptr,
        ),
        BytePatch(
            name="menu_trim_header_ptr_menu_02",
            description="Point menu $02's static text list at the header",
            prg_offset=_prg(0x8B3D),
            original=bytes([0x57, 0x8C]),
            patched=header_ptr,
        ),
        BytePatch(
            name="menu_trim_main_options",
            description="Main menu options: 2 entries (STROKE PLAY, CLUB HOUSE) instead of 4",
            prg_offset=_prg(0x8BA0),
            original=bytes([0x04, 0xA9, 0x8B, 0xB7, 0x8B]),
            patched=bytes([0x02, 0xA9, 0x8B, 0xD1, 0x8B]),
        ),
        BytePatch(
            name="menu_trim_main_destinations",
            description="Main menu destinations: STROKE PLAY -> $01, CLUB HOUSE -> $15",
            prg_offset=_prg(0x8ACE),
            original=bytes([0x01, 0x05]),
            patched=bytes([0x01, 0x15]),
        ),
        BytePatch(
            name="menu_trim_club_house_row",
            description="Move CLUB HOUSE up from row $14 to $10 to close the gap",
            prg_offset=_prg(0x8BD1),
            original=bytes([0x0C, 0x14]),
            patched=bytes([0x0C, 0x10]),
        ),
        BytePatch(
            name="menu_trim_play_mode_guard",
            description="ApplyPlayModeSelection: only selection 0 sets GolfGameMode, so CLUB HOUSE at index 1 no longer forces match play",
            prg_offset=_prg(0x89AA),
            original=bytes([0xC9, 0x02]),
            patched=bytes([0xC9, 0x01]),
        ),
        BytePatch(
            name="menu_trim_course_options",
            description="Course select options: 1 entry instead of 3",
            prg_offset=_prg(0x8C65),
            original=bytes([0x03]),
            patched=bytes([0x01]),
        ),
        BytePatch(
            name="menu_trim_course_option_text",
            description="Course select's only entry reads RANDOM COURSE",
            prg_offset=_prg(_COURSE_OPTION_ADDR),
            original=_COURSE_OPTION_ORIGINAL,
            patched=course_option,
        ),
        BytePatch(
            name="menu_trim_course_select_japan",
            description="ApplyCourseSelection: selection 0 sets CurrCourse to 0 (JAPAN) instead of 1 (US)",
            prg_offset=_prg(0x89EB),
            original=bytes([0x01]),
            patched=bytes([0x00]),
        ),
        BytePatch(
            name="menu_trim_club_house_options",
            description="Club house options: 5 entries (REGISTER NAME, CHOOSE CLUBS, OPTIONS, TRAINING, CLEAR SAVED DATA) instead of 9",
            prg_offset=_prg(0x8D64),
            original=bytes(
                [0x09, 0x77, 0x8D, 0x87, 0x8D, 0x96, 0x8D, 0xA0, 0x8D, 0xAF, 0x8D]
            ),
            patched=bytes(
                [0x05, 0x77, 0x8D, 0x87, 0x8D, 0x96, 0x8D, 0xD1, 0x8D, 0xF1, 0x8D]
            ),
        ),
        BytePatch(
            name="menu_trim_club_house_destinations",
            description="Club house destination codes for the 5 retained entries",
            prg_offset=_prg(0x8B00),
            original=bytes([0x81, 0x82, 0x83, 0x84, 0x85]),
            patched=bytes([0x81, 0x82, 0x83, 0x87, 0x89]),
        ),
        BytePatch(
            name="menu_trim_training_row",
            description="Move TRAINING up from row $12 to $0C",
            prg_offset=_prg(0x8DD1),
            original=bytes([0x28, 0x12]),
            patched=bytes([0x28, 0x0C]),
        ),
        BytePatch(
            name="menu_trim_clear_saved_data_row",
            description="Move CLEAR SAVED DATA up from row $16 to $0E",
            prg_offset=_prg(0x8DF1),
            original=bytes([0x28, 0x16]),
            patched=bytes([0x28, 0x0E]),
        ),
    ]


def menu_trim_patch(
    words: str | Sequence[str] | None = None,
) -> CompositePatch[BytePatch]:
    """Build the menu trim patch set as a single named CompositePatch."""
    patches = menu_trim_patches(words)
    return CompositePatch(
        name="menu_trim",
        description=(
            "Trim the title menu to STROKE PLAY + CLUB HOUSE, course select to "
            "RANDOM COURSE and the club house to 5 entries, under a three-word header"
        ),
        patches=patches,
    )
