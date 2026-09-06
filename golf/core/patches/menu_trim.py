"""
Title menu trim patch (proof of concept).

Demonstrates that the title menu chain is pure data: entries can be removed,
retitled and re-pointed without touching a single instruction, because every
menu is described by four parallel tables in bank 12. See `docs/menu_system.md`
for the full layout.

What this patch does:

  * Menu $00 gets its own static-text list showing 14 random characters where
    vanilla shows "PLEASE SELECT".
  * Menu $00 drops MATCH,PLAY and TOURNAMENT, keeping STROKE PLAY and
    CLUB HOUSE.
  * Menu $15 (club house) drops PLAYER STATS, PRIZE MONEY, TOURNAMENT ROSTER
    and HALL OF FAME HOLES, keeping REGISTER NAME, CHOOSE CLUBS, OPTIONS,
    TRAINING and CLEAR SAVED DATA.

Nothing is relocated. A text list is `count` followed by `count` 2-byte entry
pointers, so shortening a list means writing a smaller count and rewriting the
pointers that stay - the bytes past the new count are simply never read again.
The same is true of `MenuSubmenuIdData`, the parallel one-byte-per-selection
list of destinations.

Two wrinkles the naive edit would get wrong:

1. Each entry carries its own Y coordinate, so removing an entry from the
   middle of a list leaves a visual gap. The retained entries below a removed
   one have to be moved up. CLUB HOUSE goes from row $14 to $10; club house
   TRAINING from $12 to $0C and CLEAR SAVED DATA from $16 to $0E.

2. `ApplyPlayModeSelection` ($89A2), menu $00's choice handler, keys off the
   *selection index*, not the entry text: `sel < 2` sets
   `GolfGameMode = sel * 4`. In vanilla CLUB HOUSE is index 3, so it leaves
   `GolfGameMode` alone. Once MATCH,PLAY and TOURNAMENT are gone CLUB HOUSE
   becomes index 1 and would silently set `GolfGameMode = $04` (match play) on
   the way in. The guard is tightened to `CMP #$01` so only STROKE PLAY writes
   the mode. That handler is shared with menu $09 (TOURNAMENT's stroke/match
   submenu), but $09 is unreachable once TOURNAMENT is removed.

The 14-character title needs 17 bytes (X, Y, 14 chars, $FF) plus a 3-byte list
header, and the vanilla "PLEASE SELECT" entry at $8B90 has room for 16 and is
shared by ten other menus besides. So instead the new list is built in the
26 bytes freed by the two removed main-menu entries:

  $8BB7  01 BA 8B                  list: 1 entry, at $8BBA
  $8BBA  04 0A <14 chars> FF       entry at column 4, row $0A

and `MenuTextListPtrTable[$00]+0` is repointed from $8B8D to $8BB7. $8BB7 and
$8BC4 (the MATCH,PLAY and TOURNAMENT entry records) are each referenced exactly
once in the whole bank, from the main-menu options list, so freeing them is
safe. Every other menu keeps "PLEASE SELECT".

Byte edits, all in bank 12:

  $8B35  8D 8B                     -> B7 8B         menu $00 static list ptr
  $8BB7  (MATCH,PLAY + TOURNAMENT) -> new list      random title
  $8BA0  04 A9 8B B7 8B            -> 02 A9 8B D1 8B  main options: 2 entries
  $8ACE  01 05                     -> 01 15         main destinations
  $8BD1  0C 14                     -> 0C 10         CLUB HOUSE row
  $89AA  C9 02                     -> C9 01         play-mode guard
  $8D64  09 77 8D ... AF 8D        -> 05 77 8D ... F1 8D  club house: 5 entries
  $8B00  81 82 83 84 85            -> 81 82 83 87 89 club house destinations
  $8DD1  28 12                     -> 28 0C         TRAINING row
  $8DF1  28 16                     -> 28 0E         CLEAR SAVED DATA row
"""

import random
import string

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

TITLE_LENGTH = 14
TITLE_X = 0x04  # same position vanilla uses for "PLEASE SELECT"
TITLE_Y = 0x0A

# New static-text list for menu $00, built in the space freed by the removed
# MATCH,PLAY and TOURNAMENT entries.
_TITLE_LIST_ADDR = 0x8BB7
_TITLE_ENTRY_ADDR = 0x8BBA  # _TITLE_LIST_ADDR + 3 (count byte + one pointer)

# Original bytes of the region the new list overwrites: the MATCH,PLAY entry
# record plus the first 7 bytes of the TOURNAMENT one.
_TITLE_LIST_ORIGINAL = bytes(
    [
        0x0C, 0x10, 0x4D, 0x41, 0x54, 0x43, 0x48, 0x2C,  # $8BB7 "MATCH,"
        0x50, 0x4C, 0x41, 0x59, 0xFF,                    #       "PLAY" $FF
        0x0C, 0x12, 0x54, 0x4F, 0x55, 0x52, 0x4E,        # $8BC4 "TOURN"...
    ]
)


def menu_trim_patches(
    title_text: str | None = None,
    seed: int | None = None,
) -> list[BytePatch]:
    """
    Build the menu trim patch set.

    Args:
        title_text: exact 14-character string to show in place of
            "PLEASE SELECT" on menu $00. Every character must be in
            RENDERABLE_CHARS. Defaults to a random draw.
        seed: seed for the random draw, for a reproducible build. Ignored when
            title_text is given.

    Returns:
        The patches in application order.
    """
    if title_text is None:
        title_text = random_title(seed)
    else:
        title_text = title_text.upper()
        if len(title_text) != TITLE_LENGTH:
            raise ValueError(
                f"title_text must be exactly {TITLE_LENGTH} characters, "
                f"got {len(title_text)}"
            )
        bad = sorted(set(title_text) - set(RENDERABLE_CHARS))
        if bad:
            raise ValueError(
                f"title_text contains characters the menu font cannot render: "
                f"{''.join(bad)!r}. Allowed: {RENDERABLE_CHARS}"
            )

    title_list = bytes(
        [
            0x01,  # count: one entry
            _TITLE_ENTRY_ADDR & 0xFF,
            _TITLE_ENTRY_ADDR >> 8,
            TITLE_X,
            TITLE_Y,
        ]
        + [ord(c) for c in title_text]
        + [0xFF]
    )
    assert len(title_list) == len(_TITLE_LIST_ORIGINAL)

    return [
        BytePatch(
            name="menu_trim_main_title_text",
            description=f"Menu $00 static text list showing {title_text!r}, in the space freed by the removed main-menu entries",
            prg_offset=_prg(_TITLE_LIST_ADDR),
            original=_TITLE_LIST_ORIGINAL,
            patched=title_list,
        ),
        BytePatch(
            name="menu_trim_main_title_ptr",
            description="Repoint menu $00's static text list from the shared 'PLEASE SELECT' list to the new one",
            prg_offset=_prg(0x8B35),
            original=bytes([0x8D, 0x8B]),
            patched=bytes([_TITLE_LIST_ADDR & 0xFF, _TITLE_LIST_ADDR >> 8]),
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
            name="menu_trim_club_house_options",
            description="Club house options: 5 entries (REGISTER NAME, CHOOSE CLUBS, OPTIONS, TRAINING, CLEAR SAVED DATA) instead of 9",
            prg_offset=_prg(0x8D64),
            original=bytes([0x09, 0x77, 0x8D, 0x87, 0x8D, 0x96, 0x8D, 0xA0, 0x8D, 0xAF, 0x8D]),
            patched=bytes([0x05, 0x77, 0x8D, 0x87, 0x8D, 0x96, 0x8D, 0xD1, 0x8D, 0xF1, 0x8D]),
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
    title_text: str | None = None,
    seed: int | None = None,
) -> CompositePatch:
    """Build the menu trim patch set as a single named CompositePatch."""
    patches = menu_trim_patches(title_text=title_text, seed=seed)
    return CompositePatch(
        name="menu_trim",
        description=(
            "Trim the title menu to STROKE PLAY + CLUB HOUSE, trim the club "
            "house to 5 entries, and replace menu $00's static text"
        ),
        patches=patches,
    )


def random_title(seed: int | None = None) -> str:
    """Draw a random renderable 14-character string."""
    rng = random.Random(seed)
    return "".join(rng.choice(RENDERABLE_CHARS) for _ in range(TITLE_LENGTH))
