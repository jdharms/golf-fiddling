"""Unit tests for the seeded wind patch and its Python RNG model."""

import pytest

from golf.core.patches import PatchError
from golf.core.patches.seeded_wind import (
    SEED_TABLE_MAX_HOLES,
    SEED_TABLE_PRG_OFFSET,
    TRAMPOLINE_CPU_ADDR,
    derive_hole_seeds,
    lfsr_step,
    predict_hole,
    seed_table_bytes,
    seeded_wind_patch,
    seeded_wind_patches,
    wind_adjust,
    wind_jitter,
)


class MockRomWriter:
    def __init__(self, data: bytes):
        self.data = bytearray(data)

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset : prg_offset + length])

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset : prg_offset + len(data)] = data


def make_vanilla_like_rom() -> MockRomWriter:
    """A 256KB PRG image with the vanilla bytes at every seeded-wind site."""
    rom = MockRomWriter(bytes(16 * 0x4000))
    for p in seeded_wind_patches("x"):
        rom.write_prg(p.prg_offset, p.original)
    return rom


# --- RNG model, checked against a Mesen session on the vanilla ROM ----------


class TestLfsrModel:
    def test_step_matches_debugger_vector_1(self):
        # both wind slots held $42=$88 $43=$15 at hole start; after the
        # shot-setup wind draw RngState was $42=$74 $43=$44
        state, a = lfsr_step(0x1588)
        assert state == 0x4474
        assert a == 0x74

    def test_step_matches_debugger_vector_2(self):
        # next swing from a clean slot: $7444 -> $CBA7
        state, a = lfsr_step(0x4474)
        assert state == 0xA7CB
        assert a == 0xCB

    def test_return_value_is_low_byte(self):
        for seed in (0x0000, 0xFFFF, 0x1234, 0xBEEF):
            state, a = lfsr_step(seed)
            assert a == state & 0xFF

    def test_zero_state_does_not_stick(self):
        state, _ = lfsr_step(0)
        assert state != 0


class TestWindModel:
    def test_jitter_table(self):
        # rng&7 -> jitter, from WindAdjustmentRoutine's AND/LSR/SBC sequence
        assert [wind_jitter(v) for v in range(8)] == [0, 0, -1, 0, 0, 1, 1, 2]

    def test_negative_speed_flips_direction(self):
        # find an rng byte with jitter -1 and check anchor 0 flips to speed 1
        state = 0
        for _ in range(64):
            nxt, a = lfsr_step(state)
            if wind_jitter(a) == -1:
                _, direction, speed = wind_adjust(state, 0x30, 0)
                assert direction == 0xB0
                assert speed == 1
                return
            state = nxt
        pytest.fail("no -1 jitter found in 64 steps")

    def test_speed_wraps_by_five(self):
        state = 0
        for _ in range(64):
            nxt, a = lfsr_step(state)
            if wind_jitter(a) == 2:
                _, direction, speed = wind_adjust(state, 0x30, 10)
                assert direction == 0x30
                assert speed == 7  # 12 -> 7
                return
            state = nxt
        pytest.fail("no +2 jitter found in 64 steps")

    def test_predict_hole_shape(self):
        f = predict_hole(0x1234, swings=5)
        assert 0 <= f.pin_index <= 3
        assert f.direction_anchor & 0x0F == 0
        assert 0 <= f.speed_anchor <= 10
        assert len(f.winds) == 5
        for direction, speed in f.winds:
            assert direction in (f.direction_anchor, f.direction_anchor ^ 0x80)
            assert 0 <= speed <= 9

    def test_predict_hole_slot_state_is_three_steps_in(self):
        seed = 0xBEEF
        state = seed
        for _ in range(3):
            state, _ = lfsr_step(state)
        assert predict_hole(seed).slot_state == state

    def test_speed_anchor_high_values_fold(self):
        # any seed whose third draw has low nibble >= 11 must fold to 3-7
        for seed in range(0, 0x4000, 7):
            f = predict_hole(seed, swings=0)
            assert 0 <= f.speed_anchor <= 10


# --- Seed derivation --------------------------------------------------------


class TestSeedDerivation:
    def test_deterministic(self):
        assert derive_hole_seeds("abc") == derive_hole_seeds("abc")

    def test_differs_by_meta_seed(self):
        assert derive_hole_seeds("abc") != derive_hole_seeds("abd")

    def test_hole_count(self):
        assert len(derive_hole_seeds("abc", 18)) == 18
        assert len(derive_hole_seeds("abc", 36)) == 36
        assert derive_hole_seeds("abc", 36)[:18] == derive_hole_seeds("abc", 18)

    def test_hole_count_bounds(self):
        with pytest.raises(ValueError):
            derive_hole_seeds("abc", 0)
        with pytest.raises(ValueError):
            derive_hole_seeds("abc", SEED_TABLE_MAX_HOLES + 1)

    def test_table_layout_is_low_then_high(self):
        assert seed_table_bytes([0x1234, 0xABCD]) == bytes([0x34, 0x12, 0xCD, 0xAB])

    def test_table_rejects_bad_seed(self):
        with pytest.raises(ValueError):
            seed_table_bytes([0x10000])


# --- Patch layout -----------------------------------------------------------


class TestPatchLayout:
    def test_fixed_bank_site_is_byte_neutral(self):
        init = next(p for p in seeded_wind_patches("x") if p.name == "seeded_wind_init_hole")
        assert len(init.original) == len(init.patched) == 10
        assert init.prg_offset == 0x3DB0B

    def test_init_hole_reads_seed_table(self):
        init = next(p for p in seeded_wind_patches("x") if p.name == "seeded_wind_init_hole")
        # LDA $DFE7,X ; STA $42 ; LDA $DFE8,X ; STA $43
        assert init.patched == bytes([0xBD, 0xE7, 0xDF, 0x85, 0x42, 0xBD, 0xE8, 0xDF, 0x85, 0x43])

    def test_writeback_becomes_nops_same_length(self):
        wb = next(p for p in seeded_wind_patches("x") if p.name == "seeded_wind_remove_writeback")
        assert wb.prg_offset == 0x342C0
        assert wb.patched == bytes([0xEA] * len(wb.original))

    def test_trampoline_sits_after_mercy_routines(self):
        tr = next(p for p in seeded_wind_patches("x") if p.name == "seeded_wind_trampoline")
        assert TRAMPOLINE_CPU_ADDR == 0xBFAF
        assert tr.prg_offset == 13 * 0x4000 + (TRAMPOLINE_CPU_ADDR - 0x8000)
        assert tr.original == bytes([0xFF] * 16)
        assert tr.patched[-1] == 0x60  # RTS
        assert tr.patched[2:5] == bytes([0x20, 0x25, 0xDA])  # JSR WindAdjustmentRoutine
        # stays clear of the MMC1 reset stub at $BFF3
        assert TRAMPOLINE_CPU_ADDR + len(tr.patched) <= 0xBFF3

    def test_call_redirect_targets_trampoline(self):
        call = next(p for p in seeded_wind_patches("x") if p.name == "seeded_wind_call_redirect")
        assert call.prg_offset == 0x3424F
        assert call.original == bytes([0x20, 0x25, 0xDA])
        assert call.patched == bytes([0x20, TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8])

    def test_call_redirect_is_last(self):
        assert seeded_wind_patches("x")[-1].name == "seeded_wind_call_redirect"

    def test_seed_table_length_follows_hole_count(self):
        t18 = next(p for p in seeded_wind_patches("x", 18) if p.name == "seeded_wind_seed_table")
        t36 = next(p for p in seeded_wind_patches("x", 36) if p.name == "seeded_wind_seed_table")
        assert t18.prg_offset == SEED_TABLE_PRG_OFFSET
        assert len(t18.patched) == 36
        assert len(t36.patched) == 72
        assert t36.original[:36] == t18.original

    def test_seed_table_matches_derivation(self):
        seeds = derive_hole_seeds("abc", 18)
        t = next(p for p in seeded_wind_patches("abc") if p.name == "seeded_wind_seed_table")
        assert t.patched == seed_table_bytes(seeds)

    def test_explicit_seeds(self):
        t = next(p for p in seeded_wind_patches(seeds=[0x0102]) if p.name == "seeded_wind_seed_table")
        assert t.patched == bytes([0x02, 0x01])

    def test_rejects_both_and_neither(self):
        with pytest.raises(ValueError):
            seeded_wind_patches("abc", seeds=[1])
        with pytest.raises(ValueError):
            seeded_wind_patches()


# --- Application ------------------------------------------------------------


class TestApplication:
    def test_applies_to_vanilla_like_rom(self):
        rom = make_vanilla_like_rom()
        patch = seeded_wind_patch("abc")
        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)
        for p in patch.patches:
            assert rom.read_prg(p.prg_offset, len(p.patched)) == p.patched

    def test_apply_is_idempotent(self):
        rom = make_vanilla_like_rom()
        patch = seeded_wind_patch("abc")
        patch.apply(rom)
        before = bytes(rom.data)
        patch.apply(rom)
        assert bytes(rom.data) == before

    def test_conflict_on_occupied_trampoline_space(self):
        rom = make_vanilla_like_rom()
        rom.write_prg(0x37FAF, bytes([0xA9]))  # something else already lives here
        patch = seeded_wind_patch("abc")
        assert not patch.can_apply(rom)
        with pytest.raises(PatchError):
            patch.apply(rom)

    def test_different_seed_on_patched_rom_is_a_conflict(self):
        rom = make_vanilla_like_rom()
        seeded_wind_patch("abc").apply(rom)
        other = seeded_wind_patch("xyz")
        assert not other.can_apply(rom)
        assert not other.is_applied(rom)
