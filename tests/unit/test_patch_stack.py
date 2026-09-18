"""Unit tests for PatchStack, against a blank synthetic ROM."""

import hashlib

import pytest

from golf.core import ips
from golf.core.patches import (
    BytePatch,
    CompositePatch,
    PatchStack,
    ROMPatch,
    StackError,
)

BLANK = b"NES\x1a" + bytes([16]) + bytes(11) + bytes(16 * 0x4000)
BLANK_SHA1 = hashlib.sha1(BLANK).hexdigest()


def byte_patch(
    name: str, prg_offset: int, patched: bytes, original: bytes | None = None
):
    return BytePatch(name, name, prg_offset, original or bytes(len(patched)), patched)


class RawWrite(ROMPatch):
    """Writes without checking, through whichever RomWriter method it is given."""

    def __init__(self, name: str, write):
        self.name = name
        self.description = name
        self.write = write

    def can_apply(self, rom_writer) -> bool:
        return True

    def is_applied(self, rom_writer) -> bool:
        return False

    def apply(self, rom_writer) -> None:
        self.write(rom_writer)


def stack(*steps) -> PatchStack:
    return PatchStack(list(steps), base_sha1=None)


class TestBuild:
    def test_applies_steps_and_leaves_the_base_alone(self):
        base = bytearray(BLANK)
        result = stack(byte_patch("a", 0x100, b"\x01\x02")).build(bytes(base))
        assert result.rom[16 + 0x100 : 16 + 0x102] == b"\x01\x02"
        assert bytes(base) == BLANK

    def test_regions_record_what_each_step_wrote(self):
        result = stack(
            byte_patch("a", 0x100, b"\x01\x02\x03"),
            byte_patch("b", 0x3C000, b"\x04"),
            RawWrite(
                "c",
                lambda w: (w.write_prg(0x200, b"\x05"), w.write_prg(0x202, b"\x06")),
            ),
        ).build(BLANK)
        assert result.regions == {
            "a": [(0x100, 0x103)],
            "b": [(0x3C000, 0x3C001)],
            "c": [(0x200, 0x201), (0x202, 0x203)],
        }

    def test_duplicate_names_are_rejected(self):
        with pytest.raises(StackError, match="duplicate step names: a"):
            PatchStack([byte_patch("a", 0, b"\x01"), byte_patch("a", 1, b"\x01")])

    def test_a_failing_step_is_named(self):
        wrong = byte_patch("wrong", 0x100, b"\x01", original=b"\x99")
        with pytest.raises(StackError, match="step 'wrong'.*unexpected bytes"):
            stack(wrong).build(BLANK)

    def test_ips_turns_the_base_into_the_build(self):
        s = stack(
            byte_patch("a", 0x100, b"\x01\x02"), byte_patch("b", 0x3FFF0, b"\x03")
        )
        assert ips.apply(BLANK, s.ips(BLANK)) == s.build(BLANK).rom


class TestBaseRom:
    def test_the_default_expects_the_vanilla_us_rom(self):
        with pytest.raises(StackError, match="SHA-1"):
            PatchStack([]).build(BLANK)

    def test_a_matching_hash_builds(self):
        PatchStack([], base_sha1=BLANK_SHA1).build(BLANK)

    def test_none_builds_on_any_base(self):
        PatchStack([], base_sha1=None).build(BLANK)


class TestRequirements:
    def setup_method(self):
        self.needed = byte_patch("needed", 0x100, b"\x01")
        self.needy = CompositePatch(
            "needy",
            "",
            [byte_patch("needy_byte", 0x200, b"\x02")],
            requires=[self.needed],
        )

    def test_satisfied_by_an_earlier_step(self):
        stack(self.needed, self.needy).build(BLANK)

    def test_satisfied_by_the_base(self):
        base = bytearray(BLANK)
        base[16 + 0x100] = 0x01
        stack(self.needy).build(bytes(base))

    def test_missing_from_the_stack(self):
        with pytest.raises(
            StackError, match=r"'needy' requires needed \(not in the stack\)"
        ):
            stack(self.needy).build(BLANK)

    def test_listed_after_the_step_that_needs_it(self):
        with pytest.raises(
            StackError, match=r"'needy' requires needed \(listed after it\)"
        ):
            stack(self.needy, self.needed).build(BLANK)


class TestOverlaps:
    def test_a_later_step_writing_an_earlier_steps_byte_is_refused(self):
        with pytest.raises(StackError) as error:
            stack(
                RawWrite("first", lambda w: w.write_prg(0x8100, b"\x01\x02")),
                RawWrite("second", lambda w: w.write_prg(0x8101, b"\x09")),
            ).build(BLANK)
        assert str(error.value) == (
            "step 'second' writes bank 2 $8101 (PRG 0x08101), which step 'first' already wrote"
        )

    def test_even_the_same_value(self):
        with pytest.raises(StackError, match="already wrote"):
            stack(
                RawWrite("first", lambda w: w.write_prg(0x100, b"\x01")),
                RawWrite("second", lambda w: w.write_prg(0x100, b"\x01")),
            ).build(BLANK)

    def test_a_step_may_rewrite_its_own_bytes(self):
        stack(
            RawWrite(
                "twice",
                lambda w: (w.write_prg(0x100, b"\x01"), w.write_prg(0x100, b"\x02")),
            )
        ).build(BLANK)

    def test_a_shared_sub_patch_is_not_an_overlap(self):
        shared = byte_patch("shared", 0x100, b"\x01")
        one = CompositePatch(
            "one", "", [shared, byte_patch("one_only", 0x200, b"\x02")]
        )
        two = CompositePatch(
            "two", "", [shared, byte_patch("two_only", 0x300, b"\x03")]
        )
        result = stack(one, two).build(BLANK)
        assert result.regions["two"] == [(0x300, 0x301)]

    @pytest.mark.parametrize(
        ("prg_offset", "write"),
        [
            (0x3C000, lambda w: w.write_prg_byte(0x3C000, 1)),
            (0x3C000, lambda w: w.write_prg_word(0x3C000, 0x0101)),
            (0x3C000, lambda w: w.write_fixed(0xC000, b"\x01")),
            (0x3C000, lambda w: w.write_fixed_byte(0xC000, 1)),
            (0x3C000, lambda w: w.write_fixed_word(0xC000, 0x0101)),
            (0x38000, lambda w: w.write_switched(0x8000, 14, b"\x01")),
        ],
    )
    def test_every_write_method_is_tracked(self, prg_offset, write):
        first = RawWrite("first", lambda w: w.write_prg(prg_offset, b"\x07"))
        with pytest.raises(StackError, match="already wrote"):
            stack(first, RawWrite("second", write)).build(BLANK)
