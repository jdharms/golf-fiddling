"""
Mercy tap-in patch.

Quality-of-life patch: cuts a hole short once a player reaches a configurable
stroke count, instead of making them keep playing out an already-lost hole.

Earlier draft (superseded): this used to force `BallLie = 6` at bank 13's
`LD_8621` shot-lie dispatch, on the theory that 6 meant "holed out". Testing
showed that's wrong - forcing it just set the stroke count and did nothing
else. Tracing an actual hole-out with a Mesen breakpoint (on writes to
`MaybePerHoleStrokes`, $0134-$0145) instead traced backward through the real
mechanism:

  - A hole only finishes once *every* active player's `$0111,X` reads 3 (bank
    13, `LD_8383`'s per-player loop, right before it falls into `LD_8392`
    which commits `CurrentHoleStrokes` into `MaybePerHoleStrokes`).
  - `$0111,X` only becomes 3 at bank 13 `$8332`, gated on `$05B9 != 0`
    ($8326).
  - `$05B9` has exactly one writer in the whole ROM: bank 9 `$8311`
    (`INC $05B9`), at the tail of the ball-to-flag distance routine, right
    after that routine sets `ShotPhaseState = 2` (stopped). Every other
    reference to `$05B9` is a reader gating on zero-vs-nonzero (bank 13
    `$900C` skips ball-sprite drawing, `$ACA1` fires the completion
    `ExecuteFarCall` once `ShotPhaseState==2 && $05B9`).

So `$05B9` - not `BallLie` - is the real "ball is in the cup" signal.
`BallLie == 6` (the earlier theory) turned out to feed `$0111,X` as 1-vs-2
for something else (plausibly "reached the green" bookkeeping, per
discussion), not hole completion.

Patching bank 9's distance routine directly to force `$05B9` was considered
and rejected: that routine only reaches its `INC $05B9` once the ball is
already geometrically close to the flag, so it wouldn't fire for e.g. a
mercy-triggering shot that lands in a bunker far from the pin. Instead this
hooks bank 13's `LD_B3DC_BallStopped` ($B3DC) - the general
"ball velocity has reached zero" handler every shot (drive, approach, or
putt) already passes through once it comes to rest, regardless of where.
Splicing there to conditionally set `$05B9` reuses the exact real completion
signal the rest of the game already checks, for a ball resting anywhere.

New code occupies free space at $BF83 (29 bytes, all $FF in a vanilla ROM) in
bank 13 - the same bank as the splice site, so no bank-switch concerns.

  MercyCheckAndStop ($BF83):
    LDA #$02                 ; replicated original
    STA BounceState
    STA ShotPhaseState
    LDX CurrentPlayerIndex
    LDA CurrentHoleStrokes,X
    CMP #<mercy_point>
    BCC Skip                 ; strokes-so-far < mercy_point: leave $05B9 alone
    LDA #<mercy_result>       ; cap the score at mercy_result regardless of
    STA CurrentHoleStrokes,X  ; how far past mercy_point the count already is
    LDA #$01                  ; set (not INC) - idempotent if this handler
    STA $05B9                 ; runs again next frame while still at rest
  Skip:
    JMP ClearVelocityBytes    ; $B3E3, original continuation

The splice at `LD_B3DC_BallStopped` replaces its original 7 bytes with a
same-length redirect into the routine above, padded with NOPs - byte-neutral,
nothing else shifts:

  original: A9 02 8D B0 05 85 D2         (LDA #2; STA BounceState; STA ShotPhaseState)
  patched:  4C 83 BF EA EA EA EA         (JMP $BF83; NOP x4)

Update: playtesting found that even with the ball resting far from the pin,
forcing `$05B9` still triggered the real "ball is falling into the hole"
animation (bank 9, entered at `$8050`) - visibly wrong for a bunker/fairway
lie. Traced the trigger to bank 13 `LD_AC92`/`$ACA1`: once
`ShotPhaseState==2 && $05B9 != 0`, it unconditionally fires
`JSR ExecuteFarCall` into bank 9 `$8050` with no distance check at all - our
forced `$05B9` satisfies that gate just as well as a genuine sink would.

Fix: distinguish "genuine" from "mercy-forced" by using `$FF` as the value
this patch writes to `$05B9` instead of `$01` (bank 9's own `INC $05B9` at
`$8311` only ever produces small values, realistically never reaching `$FF`
within a round), and add a second splice at `$ACA1` that only lets the
animation-trigger fire when `$05B9` is nonzero and not `$FF` - suppressing
the animation specifically for our forced case while leaving `$8326`'s
"mark player done" check (which only tests zero-vs-nonzero) working
unchanged for both genuine and mercy-forced completions.

New code occupies free space at $BF83 (44 bytes total, all $FF in a vanilla
ROM) in bank 13 - the same bank as both splice sites, so no bank-switch
concerns.

  MercyCheckAndStop ($BF83, 29 bytes):
    LDA #$02                 ; replicated original
    STA BounceState
    STA ShotPhaseState
    LDX CurrentPlayerIndex
    LDA CurrentHoleStrokes,X
    CMP #<mercy_point>
    BCC Skip                 ; strokes-so-far < mercy_point: leave $05B9 alone
    LDA #<mercy_result>       ; cap the score at mercy_result regardless of
    STA CurrentHoleStrokes,X  ; how far past mercy_point the count already is
    LDA #$FF                  ; sentinel (not $01) - distinguishes a
    STA $05B9                 ; mercy-forced completion from a genuine one
  Skip:
    JMP ClearVelocityBytes    ; $B3E3, original continuation

  SuppressAnimationIfMercy ($BFA0, 15 bytes):
    LDA $05B9
    BEQ SkipAnimation         ; 0: no completion at all yet, same as vanilla
    CMP #$FF
    BEQ SkipAnimation         ; mercy sentinel: suppress the animation
    JMP $ACA6                 ; genuine (1..$FE): proceed to the real far call
  SkipAnimation:
    JMP LD_ACAC                ; $ACAC: original CLC/RTS, animation skipped

The splices replace their original bytes with same-length redirects into the
routines above, padded with NOPs - byte-neutral, nothing else shifts:

  LD_B3DC_BallStopped ($B3DC, 7 bytes):
    original: A9 02 8D B0 05 85 D2   (LDA #2; STA BounceState; STA ShotPhaseState)
    patched:  4C 83 BF EA EA EA EA   (JMP $BF83; NOP x4)

  LD_AC92's $05B9 check ($ACA1, 5 bytes):
    original: AD B9 05 F0 06         (LDA $05B9; BEQ LD_ACAC)
    patched:  4C A0 BF EA EA         (JMP $BFA0; NOP x2)
"""

from .byte_patch import BytePatch

_STOP_DISPATCH_PRG_OFFSET = 0x373DC  # CPU $B3DC, bank 13 (LD_B3DC_BallStopped)
_STOP_DISPATCH_ORIGINAL = bytes([0xA9, 0x02, 0x8D, 0xB0, 0x05, 0x85, 0xD2])
_STOP_DISPATCH_PATCHED = bytes([0x4C, 0x83, 0xBF, 0xEA, 0xEA, 0xEA, 0xEA])

_STOP_FREE_SPACE_PRG_OFFSET = 0x37F83  # CPU $BF83, bank 13
_STOP_FREE_SPACE_LEN = 29

_SKIP = 0xBF9D  # $BF83 + 26
_CLEAR_VELOCITY_BYTES = 0xB3E3  # original continuation after LD_B3DC_BallStopped

_MERCY_SENTINEL = 0xFF  # written to $05B9 instead of $01

_ANIM_DISPATCH_PRG_OFFSET = 0x36CA1  # CPU $ACA1, bank 13 (LD_AC92's $05B9 check)
_ANIM_DISPATCH_ORIGINAL = bytes([0xAD, 0xB9, 0x05, 0xF0, 0x06])
_ANIM_DISPATCH_PATCHED = bytes([0x4C, 0xA0, 0xBF, 0xEA, 0xEA])

_ANIM_FREE_SPACE_PRG_OFFSET = 0x37FA0  # CPU $BFA0, bank 13 (right after the first routine)
_ANIM_FREE_SPACE_LEN = 15

_ANIM_SKIP = 0xBFAC  # $BFA0 + 12
_REAL_FAR_CALL = 0xACA6  # original JSR ExecuteFarCall (+ its 3 inline params)
_LD_ACAC = 0xACAC  # original CLC/RTS


def mercy_tap_in_patches(mercy_point: int, mercy_result: int | None = None) -> list[BytePatch]:
    """
    Build the mercy tap-in patch set.

    Args:
        mercy_point: stroke count at which a hole is cut short. The player is
            allowed to finish playing this stroke; if it doesn't hole out,
            the hole ends there instead of letting them take another.
        mercy_result: score recorded for the hole when mercy triggers.
            Defaults to `mercy_point + 1` (the natural "tap it in" score).
            Callers wanting a bigger gap (e.g. a flat penalty score) can pass
            this explicitly.

    Returns:
        [stop_free_space_patch, stop_dispatch_patch, anim_free_space_patch,
        anim_dispatch_patch], in application order.
    """
    if mercy_result is None:
        mercy_result = mercy_point + 1
    if not (1 <= mercy_point <= 0xFF):
        raise ValueError(f"mercy_point must be 1-255, got {mercy_point}")
    if not (1 <= mercy_result <= 0xFF):
        raise ValueError(f"mercy_result must be 1-255, got {mercy_result}")

    stop_routine = _build_stop_routine(mercy_point, mercy_result)
    assert len(stop_routine) == _STOP_FREE_SPACE_LEN

    stop_free_space_patch = BytePatch(
        name="mercy_tap_in_free_space",
        description=(
            f"Mercy tap-in check (stroke {mercy_point} -> score {mercy_result}) "
            "in bank13 free space at $BF83"
        ),
        prg_offset=_STOP_FREE_SPACE_PRG_OFFSET,
        original=bytes([0xFF] * _STOP_FREE_SPACE_LEN),
        patched=stop_routine,
    )

    stop_dispatch_patch = BytePatch(
        name="mercy_tap_in_dispatch",
        description="Redirect bank13's LD_B3DC_BallStopped through the mercy tap-in routine",
        prg_offset=_STOP_DISPATCH_PRG_OFFSET,
        original=_STOP_DISPATCH_ORIGINAL,
        patched=_STOP_DISPATCH_PATCHED,
    )

    anim_routine = _build_anim_suppress_routine()
    assert len(anim_routine) == _ANIM_FREE_SPACE_LEN

    anim_free_space_patch = BytePatch(
        name="mercy_tap_in_anim_suppress_free_space",
        description="Suppress the ball-drop animation for a mercy-forced completion, in bank13 free space at $BFA0",
        prg_offset=_ANIM_FREE_SPACE_PRG_OFFSET,
        original=bytes([0xFF] * _ANIM_FREE_SPACE_LEN),
        patched=anim_routine,
    )

    anim_dispatch_patch = BytePatch(
        name="mercy_tap_in_anim_suppress_dispatch",
        description="Redirect bank13's $05B9 animation-trigger check through the suppress routine",
        prg_offset=_ANIM_DISPATCH_PRG_OFFSET,
        original=_ANIM_DISPATCH_ORIGINAL,
        patched=_ANIM_DISPATCH_PATCHED,
    )

    return [stop_free_space_patch, stop_dispatch_patch, anim_free_space_patch, anim_dispatch_patch]


def _build_stop_routine(mercy_point: int, mercy_result: int) -> bytes:
    bcc_operand = _SKIP - (0xBF91 + 2)
    assert 0 <= bcc_operand <= 0x7F

    return bytes(
        [
            0xA9, 0x02,  # $BF83 LDA #$02
            0x8D, 0xB0, 0x05,  # $BF85 STA BounceState
            0x85, 0xD2,  # $BF88 STA ShotPhaseState
            0xA6, 0x99,  # $BF8A LDX CurrentPlayerIndex
            0xBD, 0x1F, 0x01,  # $BF8C LDA CurrentHoleStrokes,X
            0xC9, mercy_point,  # $BF8F CMP #mercy_point
            0x90, bcc_operand,  # $BF91 BCC Skip ($BF9D)
            0xA9, mercy_result,  # $BF93 LDA #mercy_result
            0x9D, 0x1F, 0x01,  # $BF95 STA CurrentHoleStrokes,X
            0xA9, _MERCY_SENTINEL,  # $BF98 LDA #$FF
            0x8D, 0xB9, 0x05,  # $BF9A STA $05B9
            0x4C, _CLEAR_VELOCITY_BYTES & 0xFF, _CLEAR_VELOCITY_BYTES >> 8,  # $BF9D Skip: JMP ClearVelocityBytes
        ]
    )


def _build_anim_suppress_routine() -> bytes:
    beq1_operand = _ANIM_SKIP - (0xBFA3 + 2)
    beq2_operand = _ANIM_SKIP - (0xBFA7 + 2)
    assert 0 <= beq1_operand <= 0x7F
    assert 0 <= beq2_operand <= 0x7F

    return bytes(
        [
            0xAD, 0xB9, 0x05,  # $BFA0 LDA $05B9
            0xF0, beq1_operand,  # $BFA3 BEQ SkipAnimation (zero: no completion yet)
            0xC9, _MERCY_SENTINEL,  # $BFA5 CMP #$FF
            0xF0, beq2_operand,  # $BFA7 BEQ SkipAnimation (mercy sentinel)
            0x4C, _REAL_FAR_CALL & 0xFF, _REAL_FAR_CALL >> 8,  # $BFA9 JMP $ACA6 (genuine)
            0x4C, _LD_ACAC & 0xFF, _LD_ACAC >> 8,  # $BFAC SkipAnimation: JMP LD_ACAC
        ]
    )
