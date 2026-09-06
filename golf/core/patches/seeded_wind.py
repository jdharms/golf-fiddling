"""
Seeded wind patch: make every hole's pin position and wind sequence a pure
function of a build-time seed, identical for every player of the ROM.

Vanilla behavior (see docs/seeded_wind.md for the full trace)
--------------------------------------------------------------
The game has one 16-bit LFSR, `LSFR_RNG_ALGO` (fixed $D29C), on `RngState`
($42/$43). Per hole, `InitHole` (fixed $DA90) draws from it three times:
pin position ($DB15), wind direction anchor ($DBA0) and wind speed anchor
($DBA8). It also saves the pre-draw state to $04F9/$04FA at $DB0B.

Per shot, bank 13 keeps a per-player copy of the RNG state in $0525,X /
$0527,X ("wind slot"). Shot setup ($823A) loads the slot into RngState and
calls `WindAdjustmentRoutine` ($DA25), which draws once for the speed
jitter. Shot end ($82BE) writes RngState back into the slot. Both slots are
filled with the same state right after `InitHole` ($8185), so shot 1 is
already fair. The unfairness comes from in-shot RNG draws (putt aim noise,
rough/bunker variance, water-skip check) advancing RngState before the
write-back, so a player's *next* jitter depends on what happened during
their previous shot. The hole anchor is similarly whatever the global RNG
happened to be at hole start.

Patch
-----
1. `InitHole` seeding (fixed bank, byte-neutral). The 10-byte snapshot save
   at $DB0B is dead under this patch: every consumer of $04F9/$04FA copies
   it into RngState immediately before calling `InitHole`, and `InitHole`
   now overwrites RngState from the seed table. So those 10 bytes become:

       LDA SeedTable,X   ; X = doubled global hole index (set at $DAEE)
       STA $42
       LDA SeedTable+1,X
       STA $43

   Pin position, both anchors and both player slots then derive from the
   seed. The vanilla distributions are preserved exactly.

2. Wind slot write-back moved (bank 13). The 10 bytes after `LDX $99` at
   $82BE become NOPs, and the `JSR WindAdjustmentRoutine` at $824F is
   redirected to a 16-byte trampoline in bank 13 tail padding ($BFAF):

       LDX CurrentPlayerIndex
       JSR WindAdjustmentRoutine
       LDA $42 ; STA $0525,X
       LDA $43 ; STA $0527,X
       RTS

   The slot now advances exactly one LFSR step per swing, no matter what
   the shot draws afterwards. The resume path at $8D28 re-derives the wind
   from the shot-start snapshot and never touches the slots, so it stays
   correct.

3. Seed table: 2 bytes per hole ([$42, $43] order) in the course-3 block
   of `GreenFlagXTable` ($DFE7-$E02E, 72 bytes = 36 holes). That block is
   dead once `COURSE3_MIRROR_PATCH` is applied, which `PackedCourseWriter`
   always does. The writer never touches metadata slots 36-53, so the seed
   table survives a `golf-write` in either order.

Requires COURSE3_MIRROR_PATCH (otherwise the UK flag X offsets get
clobbered). Practice-mode manual wind ($04F6 bit 7) and replay playback are
untouched.

`predict_hole()` models the seeded chain in Python so a Mesen session can
be checked against the expected pin index, anchors and per-swing wind.
"""

import hashlib
from dataclasses import dataclass
from typing import Sequence

from .byte_patch import BytePatch
from .composite import CompositePatch

# --- Seed table -------------------------------------------------------------

SEED_TABLE_CPU_ADDR = 0xDFE7  # GreenFlagXTable ($DF57) + 36 holes * 4 bytes
SEED_TABLE_PRG_OFFSET = 0x3DFE7
SEED_TABLE_MAX_HOLES = 36  # 72 bytes: the whole course-3 flag X block

# Vanilla UK flag X offsets that the seed table overwrites (holes 36-53).
_SEED_TABLE_VANILLA = bytes([
    0x4C, 0x7F, 0x35, 0x6F, 0x4D, 0x30, 0x48, 0x70, 0x3B, 0x90, 0x58, 0x62,
    0x3E, 0x76, 0x83, 0x46, 0x36, 0x31, 0x84, 0x7D, 0x90, 0x3C, 0x48, 0x71,
    0x44, 0x88, 0x40, 0x73, 0x4E, 0x34, 0x5E, 0x89, 0x36, 0x5D, 0x8C, 0x3D,
    0x57, 0x54, 0x2D, 0x7E, 0x68, 0x38, 0x7C, 0x68, 0x5F, 0x27, 0x87, 0x38,
    0x68, 0x68, 0x40, 0x48, 0x68, 0x37, 0x5F, 0x77, 0x50, 0x30, 0x88, 0x68,
    0x30, 0x5F, 0x6E, 0x38, 0x62, 0x38, 0x5E, 0x36, 0x58, 0x80, 0x40, 0x80,
])
assert len(_SEED_TABLE_VANILLA) == SEED_TABLE_MAX_HOLES * 2

# --- 1. InitHole seeding (fixed bank $DB0B) ---------------------------------

_INIT_HOLE_SEED_PRG_OFFSET = 0x3DB0B
_INIT_HOLE_SEED_ORIGINAL = bytes([
    0xA5, 0x42,  # LDA RngState
    0x8D, 0xF9, 0x04,  # STA $04F9
    0xA5, 0x43,  # LDA RngState+1
    0x8D, 0xFA, 0x04,  # STA $04FA
])
_INIT_HOLE_SEED_PATCHED = bytes([
    0xBD, SEED_TABLE_CPU_ADDR & 0xFF, SEED_TABLE_CPU_ADDR >> 8,  # LDA SeedTable,X
    0x85, 0x42,  # STA RngState
    0xBD, (SEED_TABLE_CPU_ADDR + 1) & 0xFF, (SEED_TABLE_CPU_ADDR + 1) >> 8,  # LDA SeedTable+1,X
    0x85, 0x43,  # STA RngState+1
])
assert len(_INIT_HOLE_SEED_ORIGINAL) == len(_INIT_HOLE_SEED_PATCHED) == 10

# --- 2a. Remove shot-end slot write-back (bank 13 $82C0) --------------------

_WRITEBACK_PRG_OFFSET = 0x342C0  # bank 13 $82C0, right after LDX CurrentPlayerIndex
_WRITEBACK_ORIGINAL = bytes([
    0xA5, 0x42,  # LDA RngState
    0x9D, 0x25, 0x05,  # STA $0525,X
    0xA5, 0x43,  # LDA RngState+1
    0x9D, 0x27, 0x05,  # STA $0527,X
])
_WRITEBACK_PATCHED = bytes([0xEA] * len(_WRITEBACK_ORIGINAL))

# --- 2b. Trampoline in bank 13 tail padding ($BFAF) -------------------------

TRAMPOLINE_CPU_ADDR = 0xBFAF  # first free byte after the mercy tap-in routines
_TRAMPOLINE_PRG_OFFSET = 0x37FAF
_WIND_ADJUSTMENT_ROUTINE = 0xDA25
_TRAMPOLINE = bytes([
    0xA6, 0x99,  # LDX CurrentPlayerIndex
    0x20, _WIND_ADJUSTMENT_ROUTINE & 0xFF, _WIND_ADJUSTMENT_ROUTINE >> 8,  # JSR WindAdjustmentRoutine
    0xA5, 0x42,  # LDA RngState
    0x9D, 0x25, 0x05,  # STA $0525,X
    0xA5, 0x43,  # LDA RngState+1
    0x9D, 0x27, 0x05,  # STA $0527,X
    0x60,  # RTS
])
assert len(_TRAMPOLINE) == 16

# --- 2c. Redirect the shot-setup wind call (bank 13 $824F) ------------------

_WIND_CALL_PRG_OFFSET = 0x3424F
_WIND_CALL_ORIGINAL = bytes([0x20, _WIND_ADJUSTMENT_ROUTINE & 0xFF, _WIND_ADJUSTMENT_ROUTINE >> 8])
_WIND_CALL_PATCHED = bytes([0x20, TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8])


# --- Public builders --------------------------------------------------------


def derive_hole_seeds(meta_seed: str, hole_count: int = 18) -> list[int]:
    """
    Expand a meta-seed string into one 16-bit LFSR seed per hole.

    Deterministic: the same meta_seed always yields the same table, so a
    ROM can be rebuilt from the seed string alone.
    """
    if not (1 <= hole_count <= SEED_TABLE_MAX_HOLES):
        raise ValueError(f"hole_count must be 1-{SEED_TABLE_MAX_HOLES}, got {hole_count}")
    seeds = []
    for hole in range(hole_count):
        digest = hashlib.sha256(f"nes-open-seeded-wind\0{meta_seed}\0{hole}".encode()).digest()
        seeds.append(digest[0] | (digest[1] << 8))
    return seeds


def seed_table_bytes(seeds: list[int]) -> bytes:
    """Lay out 16-bit seeds as the ROM table: [$42 (low), $43 (high)] per hole."""
    if not (1 <= len(seeds) <= SEED_TABLE_MAX_HOLES):
        raise ValueError(f"need 1-{SEED_TABLE_MAX_HOLES} seeds, got {len(seeds)}")
    out = bytearray()
    for s in seeds:
        if not (0 <= s <= 0xFFFF):
            raise ValueError(f"seed out of range: {s}")
        out += bytes([s & 0xFF, s >> 8])
    return bytes(out)


def seeded_wind_patches(
    meta_seed: str | None = None,
    hole_count: int = 18,
    *,
    seeds: list[int] | None = None,
) -> list[BytePatch]:
    """
    Build the seeded wind patch set, in application order.

    Pass either `meta_seed` (expanded via `derive_hole_seeds`) or explicit
    16-bit `seeds`. The call redirect comes last so a partially applied ROM
    never calls a trampoline that isn't there yet.
    """
    if seeds is None:
        if meta_seed is None:
            raise ValueError("need meta_seed or seeds")
        seeds = derive_hole_seeds(meta_seed, hole_count)
    elif meta_seed is not None:
        raise ValueError("pass meta_seed or seeds, not both")

    table = seed_table_bytes(seeds)

    seed_table_patch = BytePatch(
        name="seeded_wind_seed_table",
        description=(
            f"Per-hole RNG seed table ({len(seeds)} holes) in the course-3 block "
            f"of GreenFlagXTable at ${SEED_TABLE_CPU_ADDR:04X}"
        ),
        prg_offset=SEED_TABLE_PRG_OFFSET,
        original=_SEED_TABLE_VANILLA[: len(table)],
        patched=table,
    )
    init_hole_patch = BytePatch(
        name="seeded_wind_init_hole",
        description="InitHole: load RngState from the seed table instead of snapshotting it to $04F9",
        prg_offset=_INIT_HOLE_SEED_PRG_OFFSET,
        original=_INIT_HOLE_SEED_ORIGINAL,
        patched=_INIT_HOLE_SEED_PATCHED,
    )
    writeback_patch = BytePatch(
        name="seeded_wind_remove_writeback",
        description="bank13 $82C0: stop writing the post-shot RngState back into the wind slot",
        prg_offset=_WRITEBACK_PRG_OFFSET,
        original=_WRITEBACK_ORIGINAL,
        patched=_WRITEBACK_PATCHED,
    )
    trampoline_patch = BytePatch(
        name="seeded_wind_trampoline",
        description=f"Wind draw + slot write-back trampoline in bank13 free space at ${TRAMPOLINE_CPU_ADDR:04X}",
        prg_offset=_TRAMPOLINE_PRG_OFFSET,
        original=bytes([0xFF] * len(_TRAMPOLINE)),
        patched=_TRAMPOLINE,
    )
    call_patch = BytePatch(
        name="seeded_wind_call_redirect",
        description="bank13 $824F: call the trampoline instead of WindAdjustmentRoutine directly",
        prg_offset=_WIND_CALL_PRG_OFFSET,
        original=_WIND_CALL_ORIGINAL,
        patched=_WIND_CALL_PATCHED,
    )
    return [seed_table_patch, init_hole_patch, writeback_patch, trampoline_patch, call_patch]


def seeded_wind_patch(
    meta_seed: str | None = None,
    hole_count: int = 18,
    *,
    seeds: list[int] | None = None,
) -> CompositePatch:
    """The seeded wind patch set as one CompositePatch."""
    return CompositePatch(
        name="seeded_wind",
        description="Seed pin position and wind per hole; advance wind once per swing, per player",
        patches=seeded_wind_patches(meta_seed, hole_count, seeds=seeds),
    )


# --- Python model of the seeded chain, for verification --------------------


def lfsr_step(state: int) -> tuple[int, int]:
    """
    One call of LSFR_RNG_ALGO ($D29C).

    `state` is ($43 << 8) | $42. Returns (new_state, A), where A is the
    routine's return value (the new $42).
    """
    lo, hi = state & 0xFF, (state >> 8) & 0xFF
    a = 0x35
    for _ in range(11):
        c = lo >> 7
        lo = (lo << 1) & 0xFF  # ASL $42
        c, hi = hi >> 7, ((hi << 1) | c) & 0xFF  # ROL $43
        c, a = a >> 7, ((a << 1) | c) & 0xFF  # ROL A
        c, a = a >> 7, ((a << 1) | c) & 0xFF  # ROL A
        a ^= lo  # EOR $42
        c, a = a >> 7, ((a << 1) | c) & 0xFF  # ROL A
        a ^= lo  # EOR $42
        a >>= 2  # LSR A; LSR A
        a = (a ^ 0xFF) & 0x01  # EOR #$FF; AND #$01
        lo |= a  # ORA $42; STA $42
    return (hi << 8) | lo, lo


def wind_jitter(a: int) -> int:
    """Map an RNG byte to WindAdjustmentRoutine's speed jitter (-1..+2)."""
    r = (a & 0x07) >> 1
    if r == 0:
        return 0
    # SBC #$01 with C = bit 0 shifted out by the LSR
    return r - 1 if (a & 1) else r - 2


def wind_adjust(state: int, direction_anchor: int, speed_anchor: int) -> tuple[int, int, int]:
    """One WindAdjustmentRoutine call. Returns (new_state, direction, speed)."""
    state, a = lfsr_step(state)
    direction = direction_anchor
    speed = (speed_anchor + wind_jitter(a)) & 0xFF
    if speed & 0x80:
        direction ^= 0x80
        speed = 1
    while speed >= 10:
        speed -= 5
    return state, direction, speed


@dataclass
class HoleWindForecast:
    seed: int
    pin_index: int  # 0-3, which of the hole's 4 flag positions
    direction_anchor: int  # WindDirectionAnchor ($012F): high nibble, bit 7 = reversed
    speed_anchor: int  # WindSpeedAnchor ($0130): 0-10
    slot_state: int  # value both wind slots hold after InitHole (($0527<<8)|$0525)
    winds: list[tuple[int, int]]  # per swing: (WindDirection $96, WindSpeed $97)


def predict_hole(seed: int, swings: int = 12) -> HoleWindForecast:
    """Predict a hole's pin, anchors and first `swings` wind values from its seed."""
    state, a = lfsr_step(seed)
    pin_index = a & 0x03
    state, a = lfsr_step(state)
    direction_anchor = a & 0xF0
    state, a = lfsr_step(state)
    speed_anchor = a & 0x0F
    if speed_anchor >= 0x0B:
        speed_anchor -= 8
    slot_state = state

    winds = []
    for _ in range(swings):
        state, direction, speed = wind_adjust(state, direction_anchor, speed_anchor)
        winds.append((direction, speed))

    return HoleWindForecast(
        seed=seed,
        pin_index=pin_index,
        direction_anchor=direction_anchor,
        speed_anchor=speed_anchor,
        slot_state=slot_state,
        winds=winds,
    )
