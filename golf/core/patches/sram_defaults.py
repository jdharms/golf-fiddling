"""
SRAM defaults: change what a new save starts with - the player name, both
players' club bags and the BGM option - and the magic that marks a save as
initialised.

`InitializeSram` (bank 9 $ACBC) runs at boot and returns if $6001/$6002 hold
the magic, "5S" ($35 $53). Otherwise, and when "clear saved data" option 3
enters it at $ACCB past the check, it zeroes $6003-$7185, copies in the
default name, roster names and club bags, fills $6F98-$6FAF with $FF, and
writes the magic last. Each parameter is a byte edit in that routine or its
tables:

- player_name: `DefaultPlayerNameText` at $AD5B, 10 bytes. The name-entry
  screen stores only A-Z, '.' and space, and draws nothing else.
- clubs: `DefaultClubBagTable` at $AE23, copied to both players' bags. It is
  written the way the choose-clubs screen saves a bag: at most 14 club ids,
  the putter always among them, in ascending order, padded with $FF.
- bgm: off turns the $FF fill loop's `BPL` at $AD4E into `BNE`, so the loop
  stops before X=0 and BGMOnFlag ($6F98) keeps $00 from the zero fill. The
  other bytes the loop fills are unchanged.
- sram_magic: the operands of the check's two `CMP #` and the final two
  `LDA #`. A save holding any other magic is wiped and rebuilt at boot, so a
  save from another ROM cannot carry its bag in. Neither byte may be $00 or
  $FF, what blank SRAM usually holds: blank SRAM would pass the check and
  never be initialised.

Only a save being initialised gets these defaults.

Future option for bag contents: repoint the bank 13 bag reads (`LDA $6027,Y`
at $8AF8, $8B71, $8B99) at a table in PRG ROM, so no save can change the bag.
"""

import string
from collections.abc import Iterable
from enum import IntEnum

from golf.core import rom_utils

from .byte_patch import BytePatch
from .composite import CompositePatch

BANK = 9

NAME_ADDR = 0xAD5B
NAME_LENGTH = 10
NAME_CHARS = string.ascii_uppercase + ". "
VANILLA_NAME = "MARIO"

CLUB_BAG_ADDR = 0xAE23
BAG_SIZE = 14
EMPTY_SLOT = 0xFF

BGM_BRANCH_ADDR = 0xAD4E
_BPL = 0x10
_BNE = 0xD0

#: "5S": the high byte is stored at $6001, the low byte at $6002
VANILLA_MAGIC = 0x3553
MAGIC_CHECK_ADDRS = (0xACC0, 0xACC7)  # CMP #$35 / CMP #$53
MAGIC_WRITE_ADDRS = (0xAD51, 0xAD56)  # LDA #$35 / LDA #$53


class Club(IntEnum):
    """Club ids, in the choose-clubs screen's order."""

    W1 = 0x00
    W2 = 0x01
    W3 = 0x02
    W4 = 0x03
    I1 = 0x04
    I2 = 0x05
    I3 = 0x06
    I4 = 0x07
    I5 = 0x08
    I6 = 0x09
    I7 = 0x0A
    I8 = 0x0B
    I9 = 0x0C
    PW = 0x0D
    SW = 0x0E
    PT = 0x0F

    @property
    def label(self) -> str:
        """The name `parse_club` reads: 1W-4W, 1I-9I, PW, SW or PT."""
        if self.name[0] in "WI":
            return self.name[1] + self.name[0]
        return self.name


VANILLA_CLUBS = tuple(club for club in Club if club not in (Club.W4, Club.I1))


def parse_club(label: str) -> Club:
    """A club from its label, case-insensitive. Raises ValueError for anything else."""
    clubs = {club.label: club for club in Club}
    try:
        return clubs[label.strip().upper()]
    except KeyError:
        raise ValueError(
            f"unknown club {label!r}; clubs are {', '.join(clubs)}"
        ) from None


def club_bag_bytes(clubs: Iterable[Club | str]) -> bytes:
    """
    A bag as the choose-clubs screen saves it: ascending ids, padded with $FF.

    The putter is added if missing. Raises ValueError for unknown or repeated
    clubs, or more than 14 with the putter.
    """
    bag = [club if isinstance(club, Club) else parse_club(club) for club in clubs]
    repeated = sorted({club for club in bag if bag.count(club) > 1})
    if repeated:
        raise ValueError(
            f"clubs listed more than once: {', '.join(club.label for club in repeated)}"
        )
    if Club.PT not in bag:
        bag.append(Club.PT)
    if len(bag) > BAG_SIZE:
        raise ValueError(
            f"a bag holds at most {BAG_SIZE} clubs including the putter, got {len(bag)}"
        )
    return bytes(sorted(bag)) + bytes([EMPTY_SLOT] * (BAG_SIZE - len(bag)))


def club_labels(bag: bytes) -> list[str]:
    """The labels of the clubs in a saved bag, in bag order."""
    return [Club(slot).label for slot in bag if slot != EMPTY_SLOT]


def player_name_bytes(name: str) -> bytes:
    """The name as stored: upper-cased, padded with spaces. Raises ValueError if it cannot be stored."""
    text = name.upper()
    bad = sorted(set(text) - set(NAME_CHARS))
    if bad:
        raise ValueError(
            f"name contains characters the name-entry screen cannot store: {''.join(bad)!r}. "
            "Allowed: A-Z, '.' and space"
        )
    if not 1 <= len(text) <= NAME_LENGTH:
        raise ValueError(f"name must be 1-{NAME_LENGTH} characters, got {len(text)}")
    return text.ljust(NAME_LENGTH).encode("ascii")


def magic_bytes(magic: int) -> bytes:
    """The magic as stored at $6001/$6002. Raises ValueError for a $00 or $FF byte."""
    if not 0 <= magic <= 0xFFFF:
        raise ValueError(f"sram_magic must be a 16-bit value, got {magic!r}")
    stored = bytes([magic >> 8, magic & 0xFF])
    if any(byte in (0x00, 0xFF) for byte in stored):
        raise ValueError(
            f"sram_magic bytes may not be $00 or $FF, which blank SRAM holds; "
            f"got ${stored[0]:02X} ${stored[1]:02X}"
        )
    return stored


def _prg(cpu_addr: int) -> int:
    return rom_utils.cpu_to_prg_switched(cpu_addr, BANK)


def sram_defaults_patches(
    player_name: str | None = None,
    clubs: Iterable[Club | str] | None = None,
    bgm: bool = True,
    sram_magic: int = VANILLA_MAGIC,
) -> list[BytePatch]:
    """The patches for every default that differs from vanilla."""
    magic = magic_bytes(sram_magic)
    patches = []
    if player_name is not None:
        patches.append(
            BytePatch(
                name="sram_defaults_player_name",
                description=f"Start a new save named {player_name.upper()!r}",
                prg_offset=_prg(NAME_ADDR),
                original=player_name_bytes(VANILLA_NAME),
                patched=player_name_bytes(player_name),
            )
        )
    if clubs is not None:
        bag = club_bag_bytes(clubs)
        patches.append(
            BytePatch(
                name="sram_defaults_clubs",
                description=f"Start both club bags with {' '.join(club_labels(bag))}",
                prg_offset=_prg(CLUB_BAG_ADDR),
                original=club_bag_bytes(VANILLA_CLUBS),
                patched=bag,
            )
        )
    if not bgm:
        patches.append(
            BytePatch(
                name="sram_defaults_bgm_off",
                description="Stop the $FF fill before BGMOnFlag, so a new save has music off",
                prg_offset=_prg(BGM_BRANCH_ADDR),
                original=bytes([_BPL]),
                patched=bytes([_BNE]),
            )
        )
    if sram_magic != VANILLA_MAGIC:
        vanilla = magic_bytes(VANILLA_MAGIC)
        for kind, addrs in (("check", MAGIC_CHECK_ADDRS), ("write", MAGIC_WRITE_ADDRS)):
            for index, addr in enumerate(addrs):
                patches.append(
                    BytePatch(
                        name=f"sram_defaults_magic_{kind}_{0x6001 + index:04X}",
                        description=f"SRAM magic ${0x6001 + index:04X} {kind}: ${magic[index]:02X}",
                        prg_offset=_prg(addr),
                        original=vanilla[index : index + 1],
                        patched=magic[index : index + 1],
                    )
                )
    return patches


def sram_defaults_patch(
    player_name: str | None = None,
    clubs: Iterable[Club | str] | None = None,
    bgm: bool = True,
    sram_magic: int = VANILLA_MAGIC,
) -> CompositePatch[BytePatch]:
    return CompositePatch(
        name="sram_defaults",
        description="Change what a new save starts with",
        patches=sram_defaults_patches(player_name, clubs, bgm, sram_magic),
    )
