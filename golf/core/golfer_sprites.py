"""
The six playable golfers: animation frames, metasprites, CHR and palette.

Everything here is read out of the ROM rather than hardcoded, so a modified ROM
reports its own values.  See `docs/golfer_sprites.md` for how each table was
identified.

Layout, all in bank 8 unless noted:

- ``$80DB`` / ``$80E1``   per-golfer base into the body pointer tables
- ``$810A`` / ``$8158``   body metasprite pointers, 6 golfers x 13 swing frames
- ``$81A6`` / ``$81CA``   body metasprite pointers, 6 golfers x 6 putt frames
- ``$80FA``               golfer screen X by club (the drawing origin)
- ``$9597`` / ``$959D``   club-set base per golfer / per club
- ``$95AD`` / ``$9621``   club metasprite pointers
- ``$9695`` / ``$96A5`` / ``$96AB``   the three bases of the club position nudge
- ``$96B8`` / ``$96FA``   club nudge dX / dY

The body's drawing origin is golfer-independent - `$804F` indexes it by club and
scroll alone - so each golfer's height lives entirely in the signed ``dY`` values
of its own metasprites, and all six share the same ``dY +24`` foot line.
"""

from dataclasses import dataclass

from golf.core.graphics_codec import VideoMemory, load_graphics_table

GOLFER_NAMES = ["Mario", "Luigi", "Steve", "Mark", "Tony", "Billy"]
SWING_FRAMES = 13
PUTT_FRAMES = 6

# Frames $05 and $0B write the body to OAM first ($8060), and a lower OAM index
# is in front on the NES - so on those two frames the body is drawn over the
# club, and on the other eleven the club is drawn over the body.
BODY_IN_FRONT_FRAMES = (5, 11)

BODY_BASE_SWING = 0x80DB
BODY_BASE_PUTT = 0x80E1
BODY_PTR_LO_SWING, BODY_PTR_HI_SWING = 0x810A, 0x8158
BODY_PTR_LO_PUTT, BODY_PTR_HI_PUTT = 0x81A6, 0x81CA
GOLFER_SCREEN_X = 0x80FA

CLUB_BASE_GOLFER = 0x9597
CLUB_BASE_CLUB = 0x959D
CLUB_PTR_LO, CLUB_PTR_HI = 0x95AD, 0x9621
NUDGE_BASE_CLUB = 0x9695
NUDGE_BASE_GOLFER = 0x96A5
NUDGE_BASE_FRAME = 0x96AB
NUDGE_X, NUDGE_Y = 0x96B8, 0x96FA

SPRITE_BANK = 8
PUTTER_CLUB = 15

# GolferClubGroupBaseTable ($959D) collapses 16 clubs into five animation groups;
# ClubNudgeClubBaseTable ($9695) collapses the same 16 into only two nudge
# classes, so groups 1-3 share one set of position corrections.
CLUB_GROUPS = [(0, 3), (4, 7), (8, 11), (12, 14), (15, 15)]
SWING_CLUB_GROUPS = CLUB_GROUPS[:-1]

# bank 5 $BEEC..$BF0F: one LoadCompressedGraphics stub per golfer
GOLFER_CHR_TABLES = [(1, 0xA1E0), (0, 0xA238), (1, 0xA9A6), (1, 0xB1DF), (0, 0xAA89), (2, 0xA54E)]
# bank 4 $A8AB..$A8DC: 5 club groups x 2 body types
CLUB_CHR_TABLES = {
    0: [(4, 0xA8AB), (4, 0xA8B0), (4, 0xA8B5), (4, 0xA8BA), (4, 0xA8BF)],
    1: [(4, 0xA8C4), (4, 0xA8C9), (4, 0xA8CE), (4, 0xA8D3), (4, 0xA8D8)],
}
# bank 5: per-golfer palette and build
SHOT_SPRITE_PALETTES = (5, 0xBEA0)   # 16 bytes -> $0486
SHIRT_COLOUR_TABLE = (5, 0xBF1B)
BODY_TYPE_TABLE = (5, 0xBF21)
BILLY_COLOUR3 = 0x27                 # bank 5 $BF0F overrides it in his stub


def _signed(value: int) -> int:
    return value - 256 if value > 127 else value


@dataclass(frozen=True)
class Sprite:
    """One 8x8 OAM entry, as an offset from the drawing origin."""

    dy: int
    tile: int
    dx: int


@dataclass
class Metasprite:
    cpu_addr: int
    sprites: list[Sprite]

    def __len__(self) -> int:
        return len(self.sprites)

    @property
    def byte_length(self) -> int:
        return 1 + 3 * len(self.sprites)

    def bounds(self) -> tuple[int, int, int, int]:
        """(min_dx, min_dy, max_dx, max_dy) covering all eight pixels of each sprite."""
        xs = [s.dx for s in self.sprites]
        ys = [s.dy for s in self.sprites]
        return min(xs), min(ys), max(xs) + 8, max(ys) + 8

    def peak_per_scanline(self) -> int:
        """Most sprites sharing one scanline - the NES drops beyond 8."""
        rows: dict[int, int] = {}
        for s in self.sprites:
            for y in range(s.dy, s.dy + 8):
                rows[y] = rows.get(y, 0) + 1
        return max(rows.values()) if rows else 0


class GolferSprites:
    """Reads the golfer and club sprite tables out of a ROM."""

    def __init__(self, rom):
        self.rom = rom
        self._bank8 = rom.read_switched(0x8000, SPRITE_BANK, 0x4000)

    def _b(self, cpu_addr: int, length: int = 1) -> bytes:
        start = cpu_addr - 0x8000
        return self._bank8[start : start + length]

    def _metasprite(self, cpu_addr: int) -> Metasprite:
        start = cpu_addr - 0x8000
        count = self._bank8[start]
        sprites = [
            Sprite(
                dy=_signed(self._bank8[start + 1 + 3 * i]),
                tile=self._bank8[start + 2 + 3 * i],
                dx=_signed(self._bank8[start + 3 + 3 * i]),
            )
            for i in range(count)
        ]
        return Metasprite(cpu_addr=cpu_addr, sprites=sprites)

    # -- body ---------------------------------------------------------------

    def body_frames(self, golfer: int, putt: bool = False) -> list[Metasprite]:
        if putt:
            base = self._b(BODY_BASE_PUTT, 6)[golfer]
            lo = self._b(BODY_PTR_LO_PUTT, 36)
            hi = self._b(BODY_PTR_HI_PUTT, 36)
            count = PUTT_FRAMES
        else:
            base = self._b(BODY_BASE_SWING, 6)[golfer]
            lo = self._b(BODY_PTR_LO_SWING, 78)
            hi = self._b(BODY_PTR_HI_SWING, 78)
            count = SWING_FRAMES
        return [
            self._metasprite(lo[base + f] | (hi[base + f] << 8)) for f in range(count)
        ]

    # -- club ---------------------------------------------------------------

    def club_frames(self, golfer: int, club: int, putt: bool = False) -> list[Metasprite]:
        """Club metasprites for one animation.

        Each club set is 58 entries: four club groups of 13 swing frames, then
        the putter's 6.  The putter therefore has no swing frames and the other
        clubs have no putt frames - putting always selects club 15.
        """
        if putt and club != PUTTER_CLUB:
            raise ValueError(
                f"putting uses club {PUTTER_CLUB}; club {club} has no putt frames"
            )
        if not putt and club == PUTTER_CLUB:
            raise ValueError("club 15 is the putter, which has no swing frames")
        golfer_base = self._b(CLUB_BASE_GOLFER, 6)[golfer]
        club_base = self._b(CLUB_BASE_CLUB, 16)[club]
        lo = self._b(CLUB_PTR_LO, 116)
        hi = self._b(CLUB_PTR_HI, 116)
        count = PUTT_FRAMES if putt else SWING_FRAMES
        frames = []
        for f in range(count):
            i = club_base + f + golfer_base
            frames.append(self._metasprite(lo[i] | (hi[i] << 8)))
        return frames

    def club_nudge(self, golfer: int, club: int, frame: int) -> tuple[int, int]:
        """Per-golfer club offset, or (0, 0) where the ROM skips it.

        `$80AC` / `$80B4` skip the whole adjustment when either the club base or
        the golfer base is negative, which is why the putter never moves and why
        Mario, Mark and Billy have no correction.
        """
        club_base = self._b(NUDGE_BASE_CLUB, 16)[club]
        golfer_base = self._b(NUDGE_BASE_GOLFER, 6)[golfer]
        if club_base & 0x80 or golfer_base & 0x80:
            return 0, 0
        index = club_base + golfer_base + self._b(NUDGE_BASE_FRAME, 13)[frame]
        return (
            _signed(self._b(NUDGE_X, 132)[index]),
            _signed(self._b(NUDGE_Y, 132)[index]),
        )

    def nudge_slot(self, golfer: int, club: int, frame: int) -> int | None:
        """Which nudge-table entry a frame uses, or None when it is skipped.

        Several frames share a slot - `$96AB` maps 13 frames onto 11 - so moving
        the club on frame 4 also moves it on frame 6.
        """
        club_base = self._b(NUDGE_BASE_CLUB, 16)[club]
        golfer_base = self._b(NUDGE_BASE_GOLFER, 6)[golfer]
        if club_base & 0x80 or golfer_base & 0x80:
            return None
        return club_base + golfer_base + self._b(NUDGE_BASE_FRAME, 13)[frame]

    # -- appearance ---------------------------------------------------------

    def body_type(self, golfer: int) -> int:
        """0 for the 56px build (Mario, Mark), 1 for the 64px build."""
        bank, addr = BODY_TYPE_TABLE
        return self.rom.read_switched(addr, bank, 6)[golfer]

    def body_palette(self, golfer: int) -> list[int | None]:
        """The four entries of sprite palette 0; index 0 is never displayed."""
        bank, addr = SHOT_SPRITE_PALETTES
        base = list(self.rom.read_switched(addr, bank, 16)[0:4])
        shirt_bank, shirt_addr = SHIRT_COLOUR_TABLE
        base[1] = self.rom.read_switched(shirt_addr, shirt_bank, 6)[golfer]
        if golfer == 5:
            base[3] = BILLY_COLOUR3
        return [None, base[1], base[2], base[3]]

    def club_palette(self) -> list[int | None]:
        """Sprite palette 1, used for the club."""
        bank, addr = SHOT_SPRITE_PALETTES
        entries = self.rom.read_switched(addr, bank, 16)[4:8]
        return [None, entries[1], entries[2], entries[3]]

    def club_group(self, club: int) -> int:
        """Which of the five animation groups a club belongs to."""
        for index, (low, high) in enumerate(CLUB_GROUPS):
            if low <= club <= high:
                return index
        raise ValueError(f"club {club} out of range")

    def nudge_class(self, club: int) -> int | None:
        """Which nudge class a club shares, or None where the nudge is skipped."""
        base = self._b(NUDGE_BASE_CLUB, 16)[club]
        return None if base & 0x80 else base

    def screen_x(self, club: int) -> int:
        """The drawing origin's X for a club - the same for every golfer."""
        return self._b(GOLFER_SCREEN_X, 16)[club]

    def load_chr(self, golfer: int, club: int) -> VideoMemory:
        """Sprite pattern memory as it stands during a shot: body then club."""
        vram = VideoMemory()
        bank, addr = GOLFER_CHR_TABLES[golfer]
        load_graphics_table(self.rom, bank, addr, vram)
        group = self._b(CLUB_BASE_CLUB, 16)[club] // 13
        bank, addr = CLUB_CHR_TABLES[self.body_type(golfer)][group]
        load_graphics_table(self.rom, bank, addr, vram)
        return vram
