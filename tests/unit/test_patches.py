"""Unit tests for the ROM patching system."""

import pytest

from golf.core.patches import BytePatch, CompositePatch, PatchError
from tests.prg_writer import PrgImageWriter


class MockRomWriter(PrgImageWriter):
    """Mock RomWriter for testing patches."""


class TestBytePatchCanApply:
    """Tests for BytePatch.can_apply()."""

    def test_can_apply_when_original_bytes_present(self):
        """can_apply returns True when original bytes match."""
        rom = MockRomWriter(b"\x00\x00\xaa\xbb\xcc\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.can_apply(rom) is True

    def test_can_apply_false_when_bytes_differ(self):
        """can_apply returns False when bytes don't match original."""
        rom = MockRomWriter(b"\x00\x00\xaa\xbb\xdd\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.can_apply(rom) is False

    def test_can_apply_false_when_patched_bytes_present(self):
        """can_apply returns False when patched bytes are present (already applied)."""
        rom = MockRomWriter(b"\x00\x00\x11\x22\x33\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.can_apply(rom) is False


class TestBytePatchIsApplied:
    """Tests for BytePatch.is_applied()."""

    def test_is_applied_true_when_patched_bytes_present(self):
        """is_applied returns True when patched bytes are present."""
        rom = MockRomWriter(b"\x00\x00\x11\x22\x33\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.is_applied(rom) is True

    def test_is_applied_false_when_original_bytes_present(self):
        """is_applied returns False when original bytes are present."""
        rom = MockRomWriter(b"\x00\x00\xaa\xbb\xcc\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.is_applied(rom) is False

    def test_is_applied_false_when_unexpected_bytes(self):
        """is_applied returns False when bytes are neither original nor patched."""
        rom = MockRomWriter(b"\x00\x00\xff\xff\xff\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        assert patch.is_applied(rom) is False


class TestBytePatchApply:
    """Tests for BytePatch.apply()."""

    def test_apply_writes_patched_bytes(self):
        """apply() writes patched bytes to ROM."""
        rom = MockRomWriter(b"\x00\x00\xaa\xbb\xcc\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        patch.apply(rom)
        assert rom.data == bytearray(b"\x00\x00\x11\x22\x33\x00\x00")

    def test_apply_is_idempotent(self):
        """apply() is a no-op if already applied."""
        rom = MockRomWriter(b"\x00\x00\x11\x22\x33\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        # Should not raise and should not change data
        patch.apply(rom)
        assert rom.data == bytearray(b"\x00\x00\x11\x22\x33\x00\x00")

    def test_apply_raises_on_unexpected_bytes(self):
        """apply() raises PatchError when ROM has unexpected bytes."""
        rom = MockRomWriter(b"\x00\x00\xff\xff\xff\x00\x00")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        with pytest.raises(PatchError) as exc_info:
            patch.apply(rom)
        assert "unexpected bytes" in str(exc_info.value)
        assert "test" in str(exc_info.value)

    def test_apply_preserves_surrounding_bytes(self):
        """apply() only modifies bytes at patch location."""
        rom = MockRomWriter(b"\xde\xad\xaa\xbb\xcc\xbe\xef")
        patch = BytePatch(
            name="test",
            description="Test patch",
            prg_offset=2,
            original=bytes([0xAA, 0xBB, 0xCC]),
            patched=bytes([0x11, 0x22, 0x33]),
        )
        patch.apply(rom)
        # DEAD and BEEF should be preserved
        assert rom.data[0:2] == bytearray(b"\xde\xad")
        assert rom.data[5:7] == bytearray(b"\xbe\xef")


class TestBytePatchRepr:
    """Tests for BytePatch string representation."""

    def test_repr_contains_key_info(self):
        """__repr__ includes name, offset, and bytes."""
        patch = BytePatch(
            name="test_patch",
            description="Test",
            prg_offset=0x1DB78,
            original=bytes([0xAA]),
            patched=bytes([0xBB]),
        )
        repr_str = repr(patch)
        assert "test_patch" in repr_str
        assert "0x1DB78" in repr_str
        assert "AA" in repr_str
        assert "BB" in repr_str


def _make_patch(offset: int, original: int, patched: int, name: str) -> BytePatch:
    return BytePatch(
        name=name,
        description="Test sub-patch",
        prg_offset=offset,
        original=bytes([original]),
        patched=bytes([patched]),
    )


class TestCompositePatch:
    """Tests for CompositePatch, which groups sub-patches into one unit."""

    def test_empty_group_is_applied(self):
        """A composite with no sub-patches is vacuously applied and appliable."""
        rom = MockRomWriter(b"\x00\x00\x00")
        patch = CompositePatch(name="empty", description="Empty group", patches=[])
        assert patch.can_apply(rom) is True
        assert patch.is_applied(rom) is True
        patch.apply(rom)  # should not raise

    def test_can_apply_true_when_all_sub_patches_original(self):
        rom = MockRomWriter(b"\xaa\xbb")
        sub_a = _make_patch(0, 0xAA, 0x11, "a")
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        assert patch.can_apply(rom) is True
        assert patch.is_applied(rom) is False

    def test_can_apply_true_when_partially_already_applied(self):
        """A mix of already-applied and pending sub-patches is still appliable."""
        rom = MockRomWriter(bytes([0x11, 0xBB]))
        sub_a = _make_patch(0, 0xAA, 0x11, "a")  # already applied
        sub_b = _make_patch(1, 0xBB, 0x22, "b")  # pending
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        assert patch.can_apply(rom) is True
        assert patch.is_applied(rom) is False

    def test_can_apply_false_when_any_sub_patch_conflicts(self):
        rom = MockRomWriter(bytes([0xFF, 0xBB]))
        sub_a = _make_patch(0, 0xAA, 0x11, "a")  # neither original nor patched
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        assert patch.can_apply(rom) is False

    def test_apply_applies_every_sub_patch(self):
        rom = MockRomWriter(bytes([0xAA, 0xBB]))
        sub_a = _make_patch(0, 0xAA, 0x11, "a")
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        patch.apply(rom)
        assert rom.data == bytearray([0x11, 0x22])
        assert patch.is_applied(rom) is True

    def test_apply_is_idempotent(self):
        rom = MockRomWriter(bytes([0x11, 0x22]))  # already fully applied
        sub_a = _make_patch(0, 0xAA, 0x11, "a")
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        patch.apply(rom)  # should not raise
        assert rom.data == bytearray([0x11, 0x22])

    def test_apply_raises_on_conflict_and_names_blocked_sub_patch(self):
        rom = MockRomWriter(bytes([0xFF, 0xBB]))
        sub_a = _make_patch(0, 0xAA, 0x11, "a")
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        with pytest.raises(PatchError) as exc_info:
            patch.apply(rom)
        assert "group" in str(exc_info.value)
        assert "a" in str(exc_info.value)
        # Untouched since apply bailed out before writing anything
        assert rom.data == bytearray([0xFF, 0xBB])

    def test_apply_partial_group_completes_pending_sub_patches(self):
        """Re-applying a partially-applied group finishes the pending ones."""
        rom = MockRomWriter(bytes([0x11, 0xBB]))  # sub_a already applied
        sub_a = _make_patch(0, 0xAA, 0x11, "a")
        sub_b = _make_patch(1, 0xBB, 0x22, "b")
        patch = CompositePatch(name="group", description="", patches=[sub_a, sub_b])
        patch.apply(rom)
        assert rom.data == bytearray([0x11, 0x22])
        assert patch.is_applied(rom) is True
