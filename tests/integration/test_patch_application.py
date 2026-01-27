"""Integration tests for ROM patch application."""

import tempfile
from pathlib import Path

import pytest

from golf.core.patches import (
    AVAILABLE_PATCHES,
    COURSE2_MIRROR_PATCH,
    COURSE3_MIRROR_PATCH,
    MULTI_BANK_CODE_PATCH,
    PatchError,
)
from golf.core.rom_writer import RomWriter


def create_test_rom_with_original_bytes() -> bytearray:
    """
    Create a minimal test ROM with original bytes at patch locations.

    The ROM needs:
    - Valid iNES header (16 bytes)
    - PRG ROM data large enough to contain patch locations
    - Original bytes placed at the correct PRG offsets
    """
    # iNES header: "NES\x1a" + PRG banks (16) + CHR banks (0) + flags
    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = 16  # 16 PRG banks (256KB)
    header[5] = 0  # 0 CHR banks

    # Create PRG ROM filled with zeros
    prg_size = 16 * 16384  # 16 banks * 16KB
    prg_rom = bytearray(prg_size)

    # Place original bytes for multi_bank_lookup patch at PRG offset 0x3DB68
    # (CPU $DB68 in fixed bank = bank 15)
    prg_rom[0x3DB68 : 0x3DB68 + 9] = MULTI_BANK_CODE_PATCH.original

    # Place original bytes for course2_mirror patch at PRG offset 0x3DBBC
    # (CPU $DBBC in fixed bank)
    prg_rom[0x3DBBC : 0x3DBBC + 1] = COURSE2_MIRROR_PATCH.original

    # Place original bytes for course3_mirror patch at PRG offset 0x3DBBD
    # (CPU $DBBD in fixed bank)
    prg_rom[0x3DBBD : 0x3DBBD + 1] = COURSE3_MIRROR_PATCH.original

    return header + prg_rom


class TestMultiBankPatchApplication:
    """Integration tests for multi-bank patches."""

    @pytest.fixture
    def test_rom_path(self, tmp_path):
        """Create a temporary test ROM file."""
        rom_data = create_test_rom_with_original_bytes()
        rom_path = tmp_path / "test_rom.nes"
        rom_path.write_bytes(rom_data)
        return rom_path

    def test_multi_bank_lookup_patch_applies(self, test_rom_path, tmp_path):
        """multi_bank_lookup patch applies correctly."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Verify original state
        assert MULTI_BANK_CODE_PATCH.can_apply(rom_writer)
        assert not MULTI_BANK_CODE_PATCH.is_applied(rom_writer)

        # Apply patch
        MULTI_BANK_CODE_PATCH.apply(rom_writer)

        # Verify patched state
        assert not MULTI_BANK_CODE_PATCH.can_apply(rom_writer)
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)

        # Verify actual bytes
        patched_bytes = rom_writer.read_prg(0x3DB68, 9)
        assert patched_bytes == MULTI_BANK_CODE_PATCH.patched

    def test_course2_mirror_patch_applies(self, test_rom_path, tmp_path):
        """course2_mirror patch applies correctly."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Verify original state
        assert COURSE2_MIRROR_PATCH.can_apply(rom_writer)
        assert not COURSE2_MIRROR_PATCH.is_applied(rom_writer)

        # Apply patch
        COURSE2_MIRROR_PATCH.apply(rom_writer)

        # Verify patched state
        assert not COURSE2_MIRROR_PATCH.can_apply(rom_writer)
        assert COURSE2_MIRROR_PATCH.is_applied(rom_writer)

        # Verify actual byte
        patched_byte = rom_writer.read_prg(0x3DBBC, 1)
        assert patched_byte == COURSE2_MIRROR_PATCH.patched

    def test_course3_mirror_patch_applies(self, test_rom_path, tmp_path):
        """course3_mirror patch applies correctly."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Verify original state
        assert COURSE3_MIRROR_PATCH.can_apply(rom_writer)
        assert not COURSE3_MIRROR_PATCH.is_applied(rom_writer)

        # Apply patch
        COURSE3_MIRROR_PATCH.apply(rom_writer)

        # Verify patched state
        assert not COURSE3_MIRROR_PATCH.can_apply(rom_writer)
        assert COURSE3_MIRROR_PATCH.is_applied(rom_writer)

        # Verify actual byte
        patched_byte = rom_writer.read_prg(0x3DBBD, 1)
        assert patched_byte == COURSE3_MIRROR_PATCH.patched

    def test_both_patches_apply_together(self, test_rom_path, tmp_path):
        """Both multi-bank patches can be applied to same ROM."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Apply both patches
        MULTI_BANK_CODE_PATCH.apply(rom_writer)
        COURSE3_MIRROR_PATCH.apply(rom_writer)

        # Verify both applied
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)
        assert COURSE3_MIRROR_PATCH.is_applied(rom_writer)

    def test_patches_are_idempotent(self, test_rom_path, tmp_path):
        """Applying patches multiple times is safe."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Apply twice
        MULTI_BANK_CODE_PATCH.apply(rom_writer)
        MULTI_BANK_CODE_PATCH.apply(rom_writer)

        # Should still be applied correctly
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)
        patched_bytes = rom_writer.read_prg(0x3DB68, 9)
        assert patched_bytes == MULTI_BANK_CODE_PATCH.patched

    def test_patches_persisted_to_disk(self, test_rom_path, tmp_path):
        """Patches are saved when ROM is written to disk."""
        output_path = tmp_path / "patched.nes"
        rom_writer = RomWriter(str(test_rom_path), str(output_path))

        # Apply patches
        MULTI_BANK_CODE_PATCH.apply(rom_writer)
        COURSE3_MIRROR_PATCH.apply(rom_writer)

        # Save to disk
        rom_writer.save()

        # Load the saved ROM and verify patches
        rom_writer2 = RomWriter(str(output_path), str(tmp_path / "patched2.nes"))
        assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer2)
        assert COURSE3_MIRROR_PATCH.is_applied(rom_writer2)


class TestAvailablePatchesRegistry:
    """Tests for the AVAILABLE_PATCHES registry."""

    def test_all_patches_registered(self):
        """All defined patches are in the registry."""
        assert "multi_bank_lookup" in AVAILABLE_PATCHES
        assert "course2_mirror" in AVAILABLE_PATCHES
        assert "course3_mirror" in AVAILABLE_PATCHES

    def test_registry_contains_correct_patches(self):
        """Registry maps to correct patch instances."""
        assert AVAILABLE_PATCHES["multi_bank_lookup"] is MULTI_BANK_CODE_PATCH
        assert AVAILABLE_PATCHES["course2_mirror"] is COURSE2_MIRROR_PATCH
        assert AVAILABLE_PATCHES["course3_mirror"] is COURSE3_MIRROR_PATCH

    def test_patch_names_match_registry_keys(self):
        """Patch.name matches the registry key."""
        for name, patch in AVAILABLE_PATCHES.items():
            assert patch.name == name


class TestPatchOnUnexpectedRom:
    """Tests for patch behavior on unexpected ROM state."""

    @pytest.fixture
    def corrupted_rom_path(self, tmp_path):
        """Create a ROM with unexpected bytes at patch locations."""
        header = bytearray(16)
        header[0:4] = b"NES\x1a"
        header[4] = 16

        prg_size = 16 * 16384
        prg_rom = bytearray(prg_size)

        # Place WRONG bytes at patch locations
        prg_rom[0x3DB68 : 0x3DB68 + 9] = bytes([0xFF] * 9)
        prg_rom[0x3DBBD : 0x3DBBD + 1] = bytes([0xFF])

        rom_path = tmp_path / "corrupted.nes"
        rom_path.write_bytes(header + prg_rom)
        return rom_path

    def test_cannot_apply_to_unexpected_bytes(self, corrupted_rom_path, tmp_path):
        """Patches reject ROMs with unexpected bytes."""
        output_path = tmp_path / "output.nes"
        rom_writer = RomWriter(str(corrupted_rom_path), str(output_path))

        # Neither can_apply nor is_applied should be true
        assert not MULTI_BANK_CODE_PATCH.can_apply(rom_writer)
        assert not MULTI_BANK_CODE_PATCH.is_applied(rom_writer)

    def test_apply_raises_on_unexpected_bytes(self, corrupted_rom_path, tmp_path):
        """apply() raises PatchError on unexpected bytes."""
        output_path = tmp_path / "output.nes"
        rom_writer = RomWriter(str(corrupted_rom_path), str(output_path))

        with pytest.raises(PatchError) as exc_info:
            MULTI_BANK_CODE_PATCH.apply(rom_writer)

        assert "multi_bank_lookup" in str(exc_info.value)
        assert "unexpected bytes" in str(exc_info.value)
