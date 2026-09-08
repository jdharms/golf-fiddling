"""Integration tests: analysis helpers against the real vanilla ROM.

Each case here is one that actually misled a session before the helper
existed, so they double as regression tests for the failure mode.
"""

from pathlib import Path

import pytest

from golf.core.mlb_labels import LabelStore
from golf.core.rom_analysis import (
    disassemble,
    find_code_references,
    find_data_references,
)
from golf.core.rom_reader import RomReader
from golf.core.rom_utils import cpu_to_prg_switched, cpu_to_prg_fixed

ROM_PATH = "nes_open_us.nes"
MLB_PATH = "NES Open Tournament Golf (USA).mlb"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


@pytest.fixture
def reader():
    return RomReader(ROM_PATH)


@pytest.fixture
def labels():
    if not Path(MLB_PATH).exists():
        pytest.skip("label file not present")
    return LabelStore.load(MLB_PATH)


class TestInlineArgs:
    def test_prize_money_setup_stays_aligned(self, reader):
        """$8F80-$8FA7 is five inline-arg calls in a row; a naive decode
        desynchronises for ~20 instructions."""
        listing = disassemble(reader, cpu_to_prg_switched(0x8F80, 12), count=14)
        assert [r.kind for r in listing.rows] == ["code", "inline"] * 7
        # The last pair must land on the real instruction boundary.
        assert listing.rows[-2].cpu == 0x8FA3
        assert listing.rows[-1].cpu == 0x8FA6

    def test_far_call_target_is_decoded(self, reader):
        listing = disassemble(reader, cpu_to_prg_switched(0x8F85, 12), count=2)
        assert "bank $06 $8000" in listing.rows[1].text

    def test_shot_loop_far_calls_resolve(self, reader):
        """bank13 $AAA2 far-calls the golfer renderer at bank 8 $8000."""
        listing = disassemble(reader, cpu_to_prg_switched(0xAAA2, 13), count=2)
        assert listing.rows[1].kind == "inline"
        assert "bank $08 $8000" in listing.rows[1].text


class TestRoutineMode:
    def test_stops_before_the_swing_rate_table(self, reader, labels):
        """$AB16's block ends at $AB43; $AB46 is data that decodes as garbage."""
        listing = disassemble(
            reader, cpu_to_prg_switched(0xAB16, 13), routine=True, labels=labels
        )
        assert listing.complete
        assert listing.rows[-1].cpu == 0xAB43
        assert listing.rows[-1].text.startswith("JMP")

    def test_cap_reports_incompleteness(self, reader, labels):
        listing = disassemble(
            reader, cpu_to_prg_switched(0xAB16, 13), routine=True,
            max_instructions=3, labels=labels,
        )
        assert not listing.complete
        assert len(listing.rows) == 3


class TestDataRanges:
    def test_golfer_x_table_is_not_decoded(self, reader, labels):
        listing = disassemble(
            reader, cpu_to_prg_switched(0x80FA, 8), count=2, labels=labels
        )
        assert listing.rows[0].kind == "data"
        assert listing.rows[0].label == "GolferScreenXTable"
        assert listing.rows[0].raw[:4] == bytes([0x7C, 0x7C, 0x7C, 0x7C])


class TestFindCodeReferences:
    def test_finds_the_two_callers_of_the_shot_loop(self, reader, labels):
        report = find_code_references(reader, 0xAA09, 13, labels)
        assert sorted(r.cpu for r in report.confirmed) == [0x884F, 0x88C3]

    def test_finds_a_branch_only_reference(self, reader, labels):
        """$D1C0 has no JSR anywhere; a byte search reports nothing and a
        previous session wrongly concluded it was unreachable. Its only
        reference is a relative branch at $D1BC."""
        report = find_code_references(reader, 0xD1C0, 15, labels)
        assert [(r.kind, r.cpu) for r in report.confirmed] == [("BEQ", 0xD1BC)]

    def test_finds_the_golfer_renderer_far_call(self, reader, labels):
        report = find_code_references(reader, 0x8000, 8, labels)
        assert any(r.kind == "far call" and r.cpu == 0xAAA2 for r in report.confirmed)

    def test_menu_handler_reached_only_indirectly_reports_nothing_but_warns(
        self, reader, labels
    ):
        """ApplyPlayModeSelection is called through JMP ($22). The search
        must come back empty AND say why that proves nothing."""
        report = find_code_references(reader, 0x89A2, 12, labels)
        assert report.empty
        assert report.not_covered
        assert any("indirect" in n for n in report.not_covered)

    def test_mid_instruction_false_positive_is_discarded(self, reader, labels):
        """A byte search reports $88B3 -> JSR $91AD, but those bytes straddle
        the operand of STA $20 and the next opcode. The alignment check,
        anchored at LoadMenuEntryPosition ($88AD), rejects it."""
        report = find_code_references(reader, 0x91AD, 12, labels)
        assert report.empty
        assert [r.aligned for r in report.refs] == [False]

    def test_unanchorable_false_positive_is_flagged_not_asserted(self, reader, labels):
        """$A64D -> JMP ($9190) is also a coincidence, but it sits in an
        unlabelled data region with no code label to anchor a check. The tool
        must report it as unverified rather than silently confirming it."""
        report = find_code_references(reader, 0x9190, 12, labels)
        assert len(report.unverified) == 1
        assert not any(r.verified for r in report.refs)

    def test_dispatch_sites_are_actually_searched(self, reader, labels):
        report = find_code_references(reader, 0xAA09, 13, labels)
        assert report.dispatch_sites_checked > 0


class TestFindDataReferences:
    def test_practice_swing_flag_is_untouched_in_vanilla(self, reader, labels):
        direct, _ = find_data_references(reader, 0x05BB, labels)
        assert direct == []

    def test_reach_surfaces_the_two_bases_that_needed_checking(self, reader, labels):
        _, reaching = find_data_references(reader, 0x05BB, labels, reach=48)
        assert 0x059C in reaching
        assert 0x05A5 in reaching

    def test_finds_the_swing_phase_state_writers(self, reader, labels):
        direct, _ = find_data_references(reader, 0x0586, labels)
        kinds = sorted({r.kind for r in direct})
        assert "INC" in kinds and "STA" in kinds
