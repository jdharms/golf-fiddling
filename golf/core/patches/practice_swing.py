"""
Practice swing patch.

Adds a practice-swing mode to the shot loop, modelled on the Famicom Disk
System game *Golf - Japan Course*. From the "ready to swing" state, Select
toggles practice mode: the golfer steps 8 pixels back from the ball and a
full three-press swing can be taken without hitting the ball, counting a
stroke, or advancing wind state. The power and accuracy markers hold on
screen for about two seconds, then the ready state is restored so another
practice swing can be taken. Select toggles back out.

See docs/practice_swing.md for the analysis this is built on, and
docs/golfer_sprites.md for the renderer tables.

Depends on wram_expansion: the toggle routine lives in the fixed-bank free
space at $CAE4, which is the tail of the $CA40-$CAFF block that
wram_expansion carves its relocated tables out of.

Layout
------

  bank 8  $BFE5-$BFF0  (12)  ApplyGolferPracticeOffset
  bank 13 $BFBF-$BFCF  (17)  CommitShotOrPractice
  bank 13 $BFD0-$BFEE  (31)  HoldPracticeSwing
  fixed   $CAE4-$CAFF  (28)  TogglePracticeSwing

Every splice is length-preserving, so nothing else in the ROM moves.

State
-----

`PracticeSwingOffset` ($05BB) is both the mode flag and the pixel shift: 0
in normal play, 8 in practice mode. It has no other reader or writer in the
ROM, and the two indexed tables that come nearest it in bank 13 ($059C,X
and $05A5,X) are both bounded at X = 0..6.

The hold timer reuses `$0586` (the swing phase). Practice hold is entered
with $0586 at 3 or 4, and the dispatch at $AAD6 routes every value >= 3 to
the state-3 handler, so the counter can climb freely to the threshold.
ShotInitialization resets it to 0.

How the four pieces fit together
--------------------------------

1. `ApplyGolferPracticeOffset` replaces the golfer's X-coordinate load in
   the bank 8 renderer, subtracting the offset. The club renderer at $8083
   saves and restores $26/$27, so the club follows the body for free. With
   the offset at 0 the arithmetic is a no-op (SEC/SBC #0).

2. `TogglePracticeSwing` takes over the ready state's B-button test, so one
   routine owns both buttons that matter: Select flips the flag, and B
   clears it before returning `SEC` to back out to club select, so practice
   mode never survives leaving the shot. Only human players reach $AB0B -
   $AAF3 sends CPU and demo players to the timeout path at $AAF5 - so it
   needs no $D5 guard.

3. `CommitShotOrPractice` replaces the `JSR IncrementStrokeCount` /
   `JSR $8D96` pair that all three commit sites share. In practice mode it
   skips both - $8D96 gates $DA17/$D94C, which advances wind RNG state, so
   a practice swing must not reach it or seeded wind desyncs - and presets
   ShotPhaseState to $FE so that the `INC $D2` following two of the three
   sites lands on $FF ("no shot in progress") instead of $00 (launch).

4. `HoldPracticeSwing` takes over the head of the state-3 handler's
   post-animation check. It forces ShotPhaseState to $FF every frame (which
   also covers the third commit site, the whiff at $AC44, that stores $02
   outright), counts frames, and calls ShotInitialization to return to the
   ready state. ShotInitialization is a complete reset here because a
   practice swing happens before the ball has moved: it restores $0586,
   $0587, $0589, $059A, $D0, $D1, $CF, $D2 and $D6/$D7 to exactly their
   values at $AA09, and its one subroutine call ($B75C) merely zeroes the
   velocity accumulators.

Practice mode ends on any exit from the shot: taking a real shot requires
toggling it off, and backing out with B clears it. The flag can therefore
never be set while another player is at the tee.
"""

from .byte_patch import BytePatch
from .composite import CompositePatch

# --- RAM ---------------------------------------------------------------

PRACTICE_SWING_OFFSET = 0x05BB  # 0 = normal play, 8 = practice mode
GOLFER_PRACTICE_SHIFT = 8  # pixels the golfer steps back from the ball

DEFAULT_HOLD_FRAMES = 0x78  # $0586 counts from 3 to here, ~2 s at 60 Hz

# --- Existing ROM entry points the new code calls into -----------------

_INCREMENT_STROKE_COUNT = 0x868C  # bank 13
_SHOT_BOOKKEEPING = 0x8D96  # bank 13, gates the wind-RNG advance
_SHOT_INITIALIZATION = 0xA9A6  # bank 13
_SHOT_LOOP_TOP = 0xAA2A  # bank 13, LD_AA2A
_GOLFER_X_TABLE = 0x80FA  # bank 8, indexed by ClubSelection
_CHECK_SHOT_COMPLETE_RESUME = 0xAC95  # bank 13, the BEQ our splice displaced

# --- New code locations ------------------------------------------------

APPLY_GOLFER_OFFSET_ADDR = 0xBFE5  # bank 8
APPLY_GOLFER_OFFSET_PRG = 0x23FE5

COMMIT_SHOT_ADDR = 0xBFBF  # bank 13
COMMIT_SHOT_PRG = 0x37FBF

HOLD_PRACTICE_ADDR = 0xBFD0  # bank 13
HOLD_PRACTICE_PRG = 0x37FD0

TOGGLE_PRACTICE_ADDR = 0xCAE4  # fixed bank
TOGGLE_PRACTICE_PRG = 0x3CAE4


def _lo(addr: int) -> int:
    return addr & 0xFF


def _hi(addr: int) -> int:
    return addr >> 8


def _rel(from_addr: int, to_addr: int) -> int:
    """Relative branch operand from the byte after the branch to to_addr."""
    delta = to_addr - (from_addr + 2)
    if not (-128 <= delta <= 127):
        raise ValueError(f"branch out of range: ${from_addr:04X} -> ${to_addr:04X}")
    return delta & 0xFF


# --- 1. Golfer X offset (bank 8) ---------------------------------------

_GOLFER_X_SPLICE_PRG = 0x2004F  # bank 8 $804F
_GOLFER_X_SPLICE_ORIGINAL = bytes([
    0xA4, 0xCD,  # LDY ClubSelection
    0xB9, _lo(_GOLFER_X_TABLE), _hi(_GOLFER_X_TABLE),  # LDA GolferScreenXTable,Y
    0x85, 0x26,  # STA $26
])
_GOLFER_X_SPLICE_PATCHED = bytes(
    [0x20, _lo(APPLY_GOLFER_OFFSET_ADDR), _hi(APPLY_GOLFER_OFFSET_ADDR)]
    + [0xEA] * (len(_GOLFER_X_SPLICE_ORIGINAL) - 3)
)

_APPLY_GOLFER_OFFSET = bytes([
    0xA4, 0xCD,  # LDY ClubSelection
    0xB9, _lo(_GOLFER_X_TABLE), _hi(_GOLFER_X_TABLE),  # LDA GolferScreenXTable,Y
    0x38,  # SEC
    0xED, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # SBC PracticeSwingOffset
    0x85, 0x26,  # STA $26
    0x60,  # RTS
])

# --- 2. Toggle and exit (fixed bank) -----------------------------------

# Takes over the ready state's B-button test, so the same routine handles
# both Select (toggle practice mode) and B (leave the shot, which must also
# leave practice mode). Only human players reach $AB0B - $AAF3 branches
# CPU and demo players onto the timeout path at $AAF5 - so no $D5 guard is
# needed here.
_TOGGLE_SPLICE_PRG = 0x36B0B  # bank 13 $AB0B, the ready state's B-button test
_TOGGLE_SPLICE_ORIGINAL = bytes([
    0xB5, 0x18,  # LDA Controller_NewPress_Tmp,X
    0x29, 0x40,  # AND #$40
    0xF0, 0x02,  # BEQ LD_AB13
    0x38,  # SEC
    0x60,  # RTS
])
_TOGGLE_SPLICE_PATCHED = bytes(
    [0x4C, _lo(TOGGLE_PRACTICE_ADDR), _hi(TOGGLE_PRACTICE_ADDR)]
    + [0xEA] * (len(_TOGGLE_SPLICE_ORIGINAL) - 3)
)

_TOGGLE_SELECT = TOGGLE_PRACTICE_ADDR + 0x11
_TOGGLE_EXIT = TOGGLE_PRACTICE_ADDR + 0x19
_TOGGLE_PRACTICE_SWING = bytes([
    0xB5, 0x18,  # LDA Controller_NewPress_Tmp,X ; X = CurrentPlayerIndex, set at $AB03
    0x29, 0x60,  # AND #$60                      ; B or Select
    0xF0, _rel(TOGGLE_PRACTICE_ADDR + 0x04, _TOGGLE_EXIT),  # BEQ Exit
    0x29, 0x40,  # AND #$40                      ; B wins if both are held
    0xF0, _rel(TOGGLE_PRACTICE_ADDR + 0x08, _TOGGLE_SELECT),  # BEQ ToggleSelect
    0xA9, 0x00,  # LDA #$00                      ; B: backing out of the shot
    0x8D, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # STA PracticeSwingOffset
    0x38,  # SEC                                 ; vanilla's "cancelled" return
    0x60,  # RTS                                 ; returns from SwingSequenceEntry
    # ToggleSelect:
    0xAD, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # LDA PracticeSwingOffset
    0x49, GOLFER_PRACTICE_SHIFT,  # EOR #$08
    0x8D, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # STA PracticeSwingOffset
    # Exit:
    0x4C, _lo(_SHOT_LOOP_TOP), _hi(_SHOT_LOOP_TOP),  # JMP LD_AA2A
])

# --- 3. Commit bookkeeping (bank 13) -----------------------------------

# All three commit sites open with the same `JSR IncrementStrokeCount /
# JSR $8D96` pair, so one routine and three identical splices cover them.
_COMMIT_SITE_PRGS = {
    "putter": 0x36BDC,  # bank 13 $ABDC - putter commits at the end of the backswing
    "overrun": 0x36C4B,  # bank 13 $AC4B - accuracy marker ran off the end (the whiff)
    "release": 0x36C77,  # bank 13 $AC77 - A pressed during the downswing
}
_COMMIT_SITE_ORIGINAL = bytes([
    0x20, _lo(_INCREMENT_STROKE_COUNT), _hi(_INCREMENT_STROKE_COUNT),
    0x20, _lo(_SHOT_BOOKKEEPING), _hi(_SHOT_BOOKKEEPING),
])
_COMMIT_SITE_PATCHED = bytes(
    [0x20, _lo(COMMIT_SHOT_ADDR), _hi(COMMIT_SHOT_ADDR)]
    + [0xEA] * (len(_COMMIT_SITE_ORIGINAL) - 3)
)

_COMMIT_PRACTICE = COMMIT_SHOT_ADDR + 0x0C
_COMMIT_SHOT_OR_PRACTICE = bytes([
    0xAD, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # LDA PracticeSwingOffset
    0xD0, _rel(COMMIT_SHOT_ADDR + 0x03, _COMMIT_PRACTICE),  # BNE Practice
    0x20, _lo(_INCREMENT_STROKE_COUNT), _hi(_INCREMENT_STROKE_COUNT),  # JSR IncrementStrokeCount
    0x20, _lo(_SHOT_BOOKKEEPING), _hi(_SHOT_BOOKKEEPING),  # JSR $8D96
    0x60,  # RTS
    # Practice:
    0xA9, 0xFE,  # LDA #$FE                     ; the site's INC $D2 makes this $FF
    0x85, 0xD2,  # STA ShotPhaseState
    0x60,  # RTS
])

# --- 4. Hold and reset (bank 13) ---------------------------------------

_HOLD_SPLICE_PRG = 0x36C92  # bank 13 $AC92
_HOLD_SPLICE_ORIGINAL = bytes([0xAD, 0xAC, 0x05])  # LDA WaterLandingCount
_HOLD_SPLICE_PATCHED = bytes(
    [0x4C, _lo(HOLD_PRACTICE_ADDR), _hi(HOLD_PRACTICE_ADDR)]
)


def _hold_practice_swing(hold_frames: int) -> bytes:
    loop = HOLD_PRACTICE_ADDR + 0x16
    normal = HOLD_PRACTICE_ADDR + 0x19
    return bytes([
        0xAD, _lo(PRACTICE_SWING_OFFSET), _hi(PRACTICE_SWING_OFFSET),  # LDA PracticeSwingOffset
        0xF0, _rel(HOLD_PRACTICE_ADDR + 0x03, normal),  # BEQ Normal
        0xA9, 0xFF,  # LDA #$FF
        0x85, 0xD2,  # STA ShotPhaseState
        0xEE, 0x86, 0x05,  # INC $0586                ; reused as the hold timer
        0xAD, 0x86, 0x05,  # LDA $0586
        0xC9, hold_frames,  # CMP #hold_frames
        0x90, _rel(HOLD_PRACTICE_ADDR + 0x11, loop),  # BCC Loop
        0x20, _lo(_SHOT_INITIALIZATION), _hi(_SHOT_INITIALIZATION),  # JSR ShotInitialization
        # Loop:
        0x4C, _lo(_SHOT_LOOP_TOP), _hi(_SHOT_LOOP_TOP),  # JMP LD_AA2A
        # Normal:
        0xAD, 0xAC, 0x05,  # LDA WaterLandingCount
        0x4C, _lo(_CHECK_SHOT_COMPLETE_RESUME), _hi(_CHECK_SHOT_COMPLETE_RESUME),  # JMP $AC95
    ])


# --- Public builder ----------------------------------------------------


def practice_swing_patches(hold_frames: int = DEFAULT_HOLD_FRAMES) -> list[BytePatch]:
    """
    Build the practice swing patch set.

    Args:
        hold_frames: value $0586 must reach before the ready state is
            restored. The counter starts at 3 (or 4 after a putt), so the
            hold lasts roughly `hold_frames - 3` frames. Must leave room
            above the three live phase values.

    Returns:
        Patches in application order: the four free-space routines first,
        then the six splices that call into them, so a partially applied
        ROM never contains a call to a routine that isn't there yet.
    """
    if not (0x10 <= hold_frames <= 0xFF):
        raise ValueError(f"hold_frames must be $10-$FF, got {hold_frames}")

    hold_routine = _hold_practice_swing(hold_frames)

    patches = [
        BytePatch(
            name="practice_swing_golfer_offset_routine",
            description=(
                "ApplyGolferPracticeOffset in bank8 free space at $BFE5: "
                "golfer X from the per-club table, less PracticeSwingOffset"
            ),
            prg_offset=APPLY_GOLFER_OFFSET_PRG,
            original=bytes([0xFF] * len(_APPLY_GOLFER_OFFSET)),
            patched=_APPLY_GOLFER_OFFSET,
        ),
        BytePatch(
            name="practice_swing_commit_routine",
            description=(
                "CommitShotOrPractice in bank13 free space at $BFBF: skips "
                "stroke counting and the wind-RNG advance in practice mode"
            ),
            prg_offset=COMMIT_SHOT_PRG,
            original=bytes([0xFF] * len(_COMMIT_SHOT_OR_PRACTICE)),
            patched=_COMMIT_SHOT_OR_PRACTICE,
        ),
        BytePatch(
            name="practice_swing_hold_routine",
            description=(
                "HoldPracticeSwing in bank13 free space at $BFD0: holds the "
                "markers, then restores the ready state via ShotInitialization"
            ),
            prg_offset=HOLD_PRACTICE_PRG,
            original=bytes([0xFF] * len(hold_routine)),
            patched=hold_routine,
        ),
        BytePatch(
            name="practice_swing_toggle_routine",
            description=(
                "TogglePracticeSwing in fixed-bank free space at $CAE4: "
                "Select toggles PracticeSwingOffset in the ready state"
            ),
            prg_offset=TOGGLE_PRACTICE_PRG,
            original=bytes([0xFF] * len(_TOGGLE_PRACTICE_SWING)),
            patched=_TOGGLE_PRACTICE_SWING,
        ),
        BytePatch(
            name="practice_swing_golfer_offset_splice",
            description="bank8 $804F: route the golfer's X load through ApplyGolferPracticeOffset",
            prg_offset=_GOLFER_X_SPLICE_PRG,
            original=_GOLFER_X_SPLICE_ORIGINAL,
            patched=_GOLFER_X_SPLICE_PATCHED,
        ),
        BytePatch(
            name="practice_swing_toggle_splice",
            description="bank13 $AB0B: ready state's B-button test runs through TogglePracticeSwing",
            prg_offset=_TOGGLE_SPLICE_PRG,
            original=_TOGGLE_SPLICE_ORIGINAL,
            patched=_TOGGLE_SPLICE_PATCHED,
        ),
    ]

    patches += [
        BytePatch(
            name=f"practice_swing_commit_splice_{label}",
            description=(
                f"bank13 ${(prg - 0x34000 + 0x8000):04X}: route the {label} commit site "
                "through CommitShotOrPractice"
            ),
            prg_offset=prg,
            original=_COMMIT_SITE_ORIGINAL,
            patched=_COMMIT_SITE_PATCHED,
        )
        for label, prg in _COMMIT_SITE_PRGS.items()
    ]

    patches.append(
        BytePatch(
            name="practice_swing_hold_splice",
            description="bank13 $AC92: state-3 completion check runs through HoldPracticeSwing",
            prg_offset=_HOLD_SPLICE_PRG,
            original=_HOLD_SPLICE_ORIGINAL,
            patched=_HOLD_SPLICE_PATCHED,
        )
    )

    return patches


def practice_swing_patch(hold_frames: int = DEFAULT_HOLD_FRAMES) -> CompositePatch:
    """The practice swing patch set as a single named CompositePatch."""
    return CompositePatch(
        name="practice_swing",
        description=(
            "Select toggles a practice swing mode in the ready state: golfer "
            "steps back 8px, swings cost no stroke and launch no ball"
        ),
        patches=practice_swing_patches(hold_frames),
    )
