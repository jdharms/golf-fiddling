"""
SPIKE: putting practice mode.

Places the ball at a random point on the green's putting surface at hole
init instead of on the tee. Nothing else is changed - the shot loop at
bank 13 $87B5 recomputes BallLie from the ball's coordinates every shot
and branches to the putting view when it comes back 6, so the putter,
the green view and the green-space HUD all follow for free.

Not wired to a CLI. Not documented. Rough edges are listed at the bottom.

Layout
------

  bank 13 $8173-$8184  (18)  splice: JSR ExecuteFarCall + inline args
  bank 10 $BF6B-$BFD5  (107) PlaceBallOnGreen

Bank 10's tail ($BF6B-$BFF2, 136 bytes of $FF) is claimed by no other
patch. The routine is reached by ExecuteFarCall ($D372), which hands the
caller's A/X/Y to the target and restores A/X on return, so the player
index in X survives the call. The routine only touches zero page, WRAM
and the fixed bank, so it has no dependency on bank 10 being mapped
beyond its own code.
"""

from golf.formats.putting_surface import PUTTING_SURFACE_TILES

from .byte_patch import BytePatch


def _contiguous_runs(values: set[int]) -> list[tuple[int, int]]:
    """Ascending (start, end_exclusive) runs covering `values`."""
    runs: list[tuple[int, int]] = []
    for v in sorted(values):
        if runs and v == runs[-1][1]:
            runs[-1] = (runs[-1][0], v + 1)
        else:
            runs.append((v, v + 1))
    return runs

# --- Splice site -------------------------------------------------------

# bank 13 $8173, inside the per-player init loop at $8155-$8190. The
# vanilla bytes copy TeeBlocksX/Y/YHigh into the player's ball position.
# The $80 fractions written at $816B-$8172 are left alone: they put the
# ball at the centre of whatever tile we pick.
_SPLICE_PRG = 0x34173
_SPLICE_ORIGINAL = bytes([
    0xAD, 0x0E, 0x01,        # LDA TeeBlocksX
    0x9D, 0x15, 0x01,        # STA $0115,X
    0xAD, 0x0F, 0x01,        # LDA TeeBlocksY
    0x9D, 0x19, 0x01,        # STA $0119,X
    0xAD, 0x10, 0x01,        # LDA TeeBlocksYHigh
    0x9D, 0x1B, 0x01,        # STA $011B,X
])

# --- New code ----------------------------------------------------------

ROUTINE_BANK = 10
ROUTINE_ADDR = 0xBF6B
ROUTINE_PRG = ROUTINE_BANK * 0x4000 + (ROUTINE_ADDR - 0x8000)

_EXECUTE_FAR_CALL = 0xD372
_LSFR_RNG_ALGO = 0xD29C
_GREEN_TILE_BUFFER = 0x75A6   # WRAM, 24x24 row-major, filled by DecompressGreen

# The putting surface is defined once, in golf/formats/putting_surface.py
# (shared with the editor's carpet paint tool): $30-$47 dark slopes,
# $88-$A7 light slopes, $B0 flat. Everything else on the 24x24 grid is
# either off the green (< $30) or a fringe/edge transition tile
# ($48-$87) - that latter band is the one the lie check at $EE88-$EE92
# singles out to set $CA = $80. Fringe is still BallLie 6, but it is not
# somewhere to spawn a putt from, so it is rejected here.
#
# The ranges are derived from that set rather than restated, so editing
# the constant re-emits the correct compare chain.
_SURFACE_RUNS = _contiguous_runs(PUTTING_SURFACE_TILES)

_ATTEMPTS = 0xFF
_DEFAULT_TILE = 0x0C          # centre of the 24x24 grid

# Zero page scratch. $2A is Tmp_2A in the label file; $26-$29 are
# unlabelled general scratch. Nothing is live across the splice site -
# the init loop at $8157-$8190 uses only A and X.
_TILE_X = 0x26
_TILE_Y = 0x27
_PTR_LO = 0x28
_PTR_HI = 0x29
_ATTEMPT_COUNTER = 0x2A


def _build_routine() -> bytes:
    """
    PlaceBallOnGreen. Entered with X = player index, which it preserves.

        LDA #$0C            ; default to the centre tile, so a run of
        STA $26             ; rejected draws still lands somewhere sane
        STA $27
        LDA #$FF
        STA $2A             ; attempt counter
    Retry:
        JSR LSFR_RNG_ALGO   ; preserves X and Y, clobbers A
        AND #$1F
        CMP #$18            ; reject 24-31
        BCS Next
        STA $26             ; tileX
        JSR LSFR_RNG_ALGO
        AND #$1F
        CMP #$18
        BCS Next
        STA $27             ; tileY, and A = tileY
        ASL A
        ASL A
        ASL A               ; 8Y, max 184, no carry out
        STA $28
        LDA #$75
        STA $29             ; pointer high starts at the buffer's page
        LDA $28
        ASL A               ; 16Y
        BCC +
        INC $29
    +   CLC
        ADC $28             ; 24Y
        BCC +
        INC $29
    +   CLC
        ADC $26             ; + tileX
        BCC +
        INC $29
    +   CLC
        ADC #$A6            ; + buffer base low
        BCC +
        INC $29
    +   STA $28
        LDY #$00
        LDA ($28),Y
        CMP #$30            ; \
        BCC Next            ;  |
        CMP #$48            ;  | one CMP/BCC pair per contiguous run of
        BCC Found           ;  | _SURFACE_RUNS, emitted in ascending
        CMP #$88            ;  | order, so "below this run's start"
        BCC Next            ;  | means every lower value was already
        CMP #$A8            ;  | tested and rejected
        BCC Found           ;  |
        CMP #$B0            ;  |
        BCC Next            ;  |
        CMP #$B1            ;  |
        BCC Found           ; /
                            ; anything past the last run falls into Next
    Next:
        DEC $2A
        BNE Retry
        ; exhausted: fall through with the last accepted tile
    Found:
        LDA $A3             ; GreenX
        CLC
        ADC $26
        STA $0115,X         ; ball X
        LDA $A4             ; GreenY
        CLC
        ADC $27
        STA $0119,X         ; ball Y low
        LDA #$00
        ADC #$00            ; carry out of the Y add
        STA $011B,X         ; ball Y high
        RTS
    """
    lo = _LSFR_RNG_ALGO & 0xFF
    hi = _LSFR_RNG_ALGO >> 8

    code: list[int] = []

    def emit(*b: int) -> None:
        code.extend(b)

    def here() -> int:
        return ROUTINE_ADDR + len(code)

    emit(0xA9, _DEFAULT_TILE)              # LDA #$0C
    emit(0x85, _TILE_X)                    # STA $26
    emit(0x85, _TILE_Y)                    # STA $27
    emit(0xA9, _ATTEMPTS)                  # LDA #$FF
    emit(0x85, _ATTEMPT_COUNTER)           # STA $2A

    retry = here()
    emit(0x20, lo, hi)                     # JSR LSFR_RNG_ALGO
    emit(0x29, 0x1F)                       # AND #$1F
    emit(0xC9, 0x18)                       # CMP #$18
    branch_x = len(code)
    emit(0xB0, 0x00)                       # BCS Next   (patched below)
    emit(0x85, _TILE_X)                    # STA $26

    emit(0x20, lo, hi)                     # JSR LSFR_RNG_ALGO
    emit(0x29, 0x1F)                       # AND #$1F
    emit(0xC9, 0x18)                       # CMP #$18
    branch_y = len(code)
    emit(0xB0, 0x00)                       # BCS Next   (patched below)
    emit(0x85, _TILE_Y)                    # STA $27

    # A = tileY. Build the 16-bit pointer $75A6 + 24*tileY + tileX.
    emit(0x0A)                             # ASL A
    emit(0x0A)                             # ASL A
    emit(0x0A)                             # ASL A        -> 8Y
    emit(0x85, _PTR_LO)                    # STA $28
    emit(0xA9, _GREEN_TILE_BUFFER >> 8)    # LDA #$75
    emit(0x85, _PTR_HI)                    # STA $29
    emit(0xA5, _PTR_LO)                    # LDA $28
    emit(0x0A)                             # ASL A        -> 16Y
    emit(0x90, 0x02)                       # BCC +2
    emit(0xE6, _PTR_HI)                    # INC $29
    emit(0x18)                             # CLC
    emit(0x65, _PTR_LO)                    # ADC $28      -> 24Y
    emit(0x90, 0x02)                       # BCC +2
    emit(0xE6, _PTR_HI)                    # INC $29
    emit(0x18)                             # CLC
    emit(0x65, _TILE_X)                    # ADC $26
    emit(0x90, 0x02)                       # BCC +2
    emit(0xE6, _PTR_HI)                    # INC $29
    emit(0x18)                             # CLC
    emit(0x69, _GREEN_TILE_BUFFER & 0xFF)  # ADC #$A6
    emit(0x90, 0x02)                       # BCC +2
    emit(0xE6, _PTR_HI)                    # INC $29
    emit(0x85, _PTR_LO)                    # STA $28

    emit(0xA0, 0x00)                       # LDY #$00
    emit(0xB1, _PTR_LO)                    # LDA ($28),Y
    accept_branches: list[int] = []
    reject_branches: list[int] = []

    # Ascending disjoint runs, so "below this run's start" means rejected:
    # everything lower has already been tested.
    for lo, end in _SURFACE_RUNS:
        emit(0xC9, lo)                     # CMP #lo
        reject_branches.append(len(code))
        emit(0x90, 0x00)                   # BCC Next
        emit(0xC9, end)                    # CMP #end
        accept_branches.append(len(code))
        emit(0x90, 0x00)                   # BCC Found

    nxt = here()
    emit(0xC6, _ATTEMPT_COUNTER)           # DEC $2A
    emit(0xD0, (retry - (here() + 2)) & 0xFF)   # BNE Retry

    found = here()
    emit(0xA5, 0xA3)                       # LDA GreenX
    emit(0x18)                             # CLC
    emit(0x65, _TILE_X)                    # ADC $26
    emit(0x9D, 0x15, 0x01)                 # STA $0115,X
    emit(0xA5, 0xA4)                       # LDA GreenY
    emit(0x18)                             # CLC
    emit(0x65, _TILE_Y)                    # ADC $27
    emit(0x9D, 0x19, 0x01)                 # STA $0119,X
    emit(0xA9, 0x00)                       # LDA #$00
    emit(0x69, 0x00)                       # ADC #$00
    emit(0x9D, 0x1B, 0x01)                 # STA $011B,X
    emit(0x60)                             # RTS

    # Resolve forward branches.
    for at in (branch_x, branch_y, *reject_branches):
        code[at + 1] = (nxt - (ROUTINE_ADDR + at + 2)) & 0xFF
    for at in accept_branches:
        code[at + 1] = (found - (ROUTINE_ADDR + at + 2)) & 0xFF

    return bytes(code)


ROUTINE = _build_routine()

# The routine must fit in bank 10's tail padding, which ends at $BFF2 -
# $BFF3-$BFFF is the 13-byte stub every bank carries.
assert ROUTINE_ADDR + len(ROUTINE) - 1 <= 0xBFF2, "routine overruns bank 10 padding"


def putting_practice_patches() -> list[BytePatch]:
    """The two byte patches that make up the spike."""
    splice = bytes([
        0x20, _EXECUTE_FAR_CALL & 0xFF, _EXECUTE_FAR_CALL >> 8,
        ROUTINE_BANK, ROUTINE_ADDR & 0xFF, ROUTINE_ADDR >> 8,
    ])
    splice += bytes([0xEA] * (len(_SPLICE_ORIGINAL) - len(splice)))

    return [
        BytePatch(
            name="putting_practice_routine",
            description=(
                f"PlaceBallOnGreen in bank {ROUTINE_BANK} "
                f"${ROUTINE_ADDR:04X} ({len(ROUTINE)} bytes)"
            ),
            prg_offset=ROUTINE_PRG,
            original=bytes([0xFF] * len(ROUTINE)),
            patched=ROUTINE,
        ),
        BytePatch(
            name="putting_practice_splice",
            description=(
                "bank 13 $8173: far-call PlaceBallOnGreen instead of "
                "copying the tee position into the ball position"
            ),
            prg_offset=_SPLICE_PRG,
            original=_SPLICE_ORIGINAL,
            patched=splice,
        ),
    ]


# Known rough edges (spike):
#   - Each loop iteration draws its own randoms, so RngState advances
#     twice per hole init and the two players get different spots. That
#     desyncs the per-player wind slots written at $8185. Irrelevant for
#     putting, deliberate for now.
#   - The ball can land on the pin's own tile and hole out on contact.
#   - No fallback if 32 attempts all miss: it uses the last accepted
#     tile, or the centre tile if none was ever accepted.
#   - MaybePlayerHoleStatus ($0111,X) is left at 0, so the distance
#     readout uses course units until after the first putt.
