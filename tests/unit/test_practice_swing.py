"""Unit tests for the practice swing patch."""

import pytest

from golf.core.patches import practice_swing_patch, practice_swing_patches
from golf.core.patches.practice_swing import (
    APPLY_GOLFER_OFFSET_ADDR,
    COMMIT_SHOT_ADDR,
    DEFAULT_HOLD_FRAMES,
    GOLFER_PRACTICE_SHIFT,
    HOLD_PRACTICE_ADDR,
    PRACTICE_SWING_OFFSET,
    TOGGLE_PRACTICE_ADDR,
    _APPLY_GOLFER_OFFSET,
    _COMMIT_SHOT_OR_PRACTICE,
    _TOGGLE_PRACTICE_SWING,
    _hold_practice_swing,
)

# Free-space budgets, from docs/practice_swing.md
BANK8_FREE = (0xBFE5, 14)
BANK13_FREE = (0xBFBF, 52)
FIXED_FREE = (0xCAE4, 28)


class MockRomWriter:
    def __init__(self, data: bytes):
        self.data = bytearray(data)

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset : prg_offset + length])

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset : prg_offset + len(data)] = data


def make_vanilla_like_rom() -> MockRomWriter:
    """A 256KB PRG image holding the vanilla bytes at every practice-swing site."""
    rom = MockRomWriter(bytes(16 * 0x4000))
    for p in practice_swing_patches():
        rom.write_prg(p.prg_offset, p.original)
    return rom


class TestRoutineLayout:
    def test_golfer_offset_fits_bank8_free_space(self):
        base, size = BANK8_FREE
        assert APPLY_GOLFER_OFFSET_ADDR == base
        assert len(_APPLY_GOLFER_OFFSET) <= size

    def test_bank13_routines_abut_and_fit(self):
        base, size = BANK13_FREE
        assert COMMIT_SHOT_ADDR == base
        commit_end = COMMIT_SHOT_ADDR + len(_COMMIT_SHOT_OR_PRACTICE)
        assert commit_end == HOLD_PRACTICE_ADDR, "routines must abut, no gap"
        hold = _hold_practice_swing(DEFAULT_HOLD_FRAMES)
        assert HOLD_PRACTICE_ADDR + len(hold) - base <= size

    def test_toggle_fits_fixed_bank_free_space(self):
        base, size = FIXED_FREE
        assert TOGGLE_PRACTICE_ADDR == base
        assert len(_TOGGLE_PRACTICE_SWING) <= size

    def test_bank13_routines_clear_the_mmc1_reset_stub(self):
        """The reset stub at $BFF3 is present in every bank and must survive."""
        hold = _hold_practice_swing(DEFAULT_HOLD_FRAMES)
        assert HOLD_PRACTICE_ADDR + len(hold) <= 0xBFF3
        assert APPLY_GOLFER_OFFSET_ADDR + len(_APPLY_GOLFER_OFFSET) <= 0xBFF3

    def test_toggle_stays_inside_the_ca40_block(self):
        end = TOGGLE_PRACTICE_ADDR + len(_TOGGLE_PRACTICE_SWING)
        assert end <= 0xCB00, "$CB00 starts the half-square-wave table"


class TestRoutineEncoding:
    def test_golfer_offset_subtracts_the_flag(self):
        # LDY $CD / LDA $80FA,Y / SEC / SBC $05BB / STA $26 / RTS
        assert _APPLY_GOLFER_OFFSET == bytes(
            [0xA4, 0xCD, 0xB9, 0xFA, 0x80, 0x38, 0xED, 0xBB, 0x05, 0x85, 0x26, 0x60]
        )

    def test_commit_presets_phase_to_fe_so_the_sites_inc_to_ff(self):
        # the two INC $D2 sites must land on $FF, not $00 (launch)
        assert _COMMIT_SHOT_OR_PRACTICE[0x0C:] == bytes([0xA9, 0xFE, 0x85, 0xD2, 0x60])

    def test_commit_branch_lands_on_the_practice_arm(self):
        offset = _COMMIT_SHOT_OR_PRACTICE[4]
        target = COMMIT_SHOT_ADDR + 0x05 + offset
        assert target == COMMIT_SHOT_ADDR + 0x0C
        assert _COMMIT_SHOT_OR_PRACTICE[0x0C] == 0xA9  # LDA #$FE

    def test_toggle_branches_resolve(self):
        exit_addr = TOGGLE_PRACTICE_ADDR + 0x19
        select_addr = TOGGLE_PRACTICE_ADDR + 0x11
        assert TOGGLE_PRACTICE_ADDR + 0x04 + 2 + _TOGGLE_PRACTICE_SWING[5] == exit_addr
        assert TOGGLE_PRACTICE_ADDR + 0x08 + 2 + _TOGGLE_PRACTICE_SWING[9] == select_addr
        assert _TOGGLE_PRACTICE_SWING[0x19] == 0x4C  # JMP LD_AA2A

    def test_toggle_flips_by_the_pixel_shift(self):
        assert _TOGGLE_PRACTICE_SWING[21] == GOLFER_PRACTICE_SHIFT  # EOR operand

    def test_toggle_reads_both_b_and_select(self):
        assert _TOGGLE_PRACTICE_SWING[2:4] == bytes([0x29, 0x60])  # AND #$60
        assert _TOGGLE_PRACTICE_SWING[6:8] == bytes([0x29, 0x40])  # AND #$40, B wins

    def test_b_button_clears_practice_mode_then_returns_carry_set(self):
        """Backing out to club select must not leave practice mode armed."""
        assert _TOGGLE_PRACTICE_SWING[10:17] == bytes(
            [0xA9, 0x00, 0x8D, 0xBB, 0x05, 0x38, 0x60]  # LDA #0 / STA flag / SEC / RTS
        )

    def test_toggle_needs_no_cpu_guard(self):
        """CPU/demo players branch away at $AAF3 and never reach $AB0B."""
        assert bytes([0x24, 0xD5]) not in _TOGGLE_PRACTICE_SWING  # no BIT $D5

    def test_hold_branches_resolve(self):
        hold = _hold_practice_swing(DEFAULT_HOLD_FRAMES)
        normal = HOLD_PRACTICE_ADDR + 0x19
        loop = HOLD_PRACTICE_ADDR + 0x16
        assert HOLD_PRACTICE_ADDR + 0x03 + 2 + hold[4] == normal
        assert HOLD_PRACTICE_ADDR + 0x11 + 2 + hold[0x12] == loop
        assert hold[0x19:0x1C] == bytes([0xAD, 0xAC, 0x05])  # LDA WaterLandingCount

    def test_hold_frames_is_parameterised(self):
        assert _hold_practice_swing(0x40)[0x10] == 0x40
        assert _hold_practice_swing(0x99)[0x10] == 0x99

    def test_all_routines_reference_the_same_flag(self):
        flag = bytes([PRACTICE_SWING_OFFSET & 0xFF, PRACTICE_SWING_OFFSET >> 8])
        hold = _hold_practice_swing(DEFAULT_HOLD_FRAMES)
        for routine in (_APPLY_GOLFER_OFFSET, _COMMIT_SHOT_OR_PRACTICE, hold, _TOGGLE_PRACTICE_SWING):
            assert flag in routine


class TestSplices:
    def test_every_splice_is_length_preserving(self):
        for p in practice_swing_patches():
            assert len(p.original) == len(p.patched), p.name

    def test_three_commit_sites_share_one_splice_shape(self):
        splices = [p for p in practice_swing_patches() if "commit_splice" in p.name]
        assert len(splices) == 3
        assert len({p.patched for p in splices}) == 1
        assert len({p.original for p in splices}) == 1

    def test_routines_are_written_before_the_calls_into_them(self):
        names = [p.name for p in practice_swing_patches()]
        last_routine = max(i for i, n in enumerate(names) if n.endswith("_routine"))
        first_splice = min(i for i, n in enumerate(names) if n.endswith("_splice"))
        assert last_routine < first_splice

    def test_free_space_patches_expect_erased_rom(self):
        for p in practice_swing_patches():
            if p.name.endswith("_routine"):
                assert set(p.original) == {0xFF}, p.name

    def test_no_two_patches_overlap(self):
        spans = sorted((p.prg_offset, p.prg_offset + len(p.patched)) for p in practice_swing_patches())
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert end <= start


class TestApplication:
    def test_apply_then_is_applied(self):
        rom = make_vanilla_like_rom()
        patch = practice_swing_patch()
        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)

    def test_apply_is_idempotent(self):
        rom = make_vanilla_like_rom()
        patch = practice_swing_patch()
        patch.apply(rom)
        snapshot = bytes(rom.data)
        patch.apply(rom)
        assert bytes(rom.data) == snapshot

    def test_hold_frames_validated(self):
        with pytest.raises(ValueError):
            practice_swing_patch(0x00)
        with pytest.raises(ValueError):
            practice_swing_patch(0x100)

    def test_hold_frames_leaves_room_above_the_live_phase_values(self):
        """$0586 holds 0-2 for the real phases and 3+ for practice hold."""
        for frames in (0x10, DEFAULT_HOLD_FRAMES, 0xFF):
            assert frames > 4
