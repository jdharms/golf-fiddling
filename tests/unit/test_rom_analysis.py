"""Unit tests for the ROM static-analysis helpers."""

import pytest

from golf.core.mlb_labels import Label, LabelIndex, LabelStore
from golf.core.rom_analysis import (
    FIXED,
    PAIRS,
    TRIPLES,
    InlineArgSpec,
    ReferenceReport,
    Reference,
    data_range_at,
    disassemble,
    find_code_references,
    find_data_references,
    find_pointer_references,
    inline_spec_for,
    is_data_range,
)

BANK_SIZE = 0x4000
BANKS = 16


class MockReader:
    """A 256KB PRG image, banks addressable the same way the real ROM is."""

    def __init__(self):
        self.data = bytearray(BANKS * BANK_SIZE)

    @property
    def prg_size(self) -> int:
        return len(self.data)

    def read_prg(self, offset: int, length: int) -> bytes:
        return bytes(self.data[offset : offset + length])

    def write(self, offset: int, data: bytes):
        self.data[offset : offset + len(data)] = data


def store(*labels) -> LabelStore:
    return LabelStore(LabelIndex(list(labels)), LabelIndex([]))


class TestInlineArgSpec:
    def test_fixed_length(self):
        spec = InlineArgSpec("X", FIXED, 3)
        assert spec.measure(bytes([1, 2, 3, 4, 5])) == 3

    def test_pairs_stop_at_terminator(self):
        spec = InlineArgSpec("X", PAIRS)
        assert spec.measure(bytes([0x01, 0x02, 0x03, 0x04, 0x00, 0xFF])) == 5

    def test_triples_stop_at_terminator(self):
        spec = InlineArgSpec("X", TRIPLES)
        assert spec.measure(bytes([0xFF, 0x3E, 0x91, 0xFE, 0x4B, 0x91, 0x00, 0x4C])) == 7

    def test_empty_table_is_just_the_terminator(self):
        assert InlineArgSpec("X", TRIPLES).measure(bytes([0x00, 0xAA])) == 1

    def test_bank_addr_rendering_decodes_the_target(self):
        spec = InlineArgSpec("X", FIXED, 3, "bank_addr")
        assert "bank $0B $9033" in spec.render(bytes([0x0B, 0x33, 0x90]))

    def test_word_rendering(self):
        spec = InlineArgSpec("X", FIXED, 2, "word")
        assert spec.render(bytes([0x45, 0x91])) == ".dw $9145"


class TestInlineSpecLookup:
    def test_fixed_bank_routine_resolves_from_any_bank(self):
        assert inline_spec_for(0xD372, 13).name == "ExecuteFarCall"
        assert inline_spec_for(0xD372, None).name == "ExecuteFarCall"

    def test_bank_specific_routine_needs_the_right_bank(self):
        assert inline_spec_for(0x8A14, 12).name == "LookupInlineByteTable"
        assert inline_spec_for(0x8A14, 13) is None

    def test_unknown_target(self):
        assert inline_spec_for(0x8000, 13) is None

    def test_dispatch_table_does_not_return(self):
        assert inline_spec_for(0xD227, None).returns is False


class TestDataRanges:
    def test_range_label_is_data(self):
        assert is_data_range(Label("NesPrgRom", 0x100, 0x120, "Table"))

    def test_single_address_label_is_not(self):
        assert not is_data_range(Label("NesPrgRom", 0x100, None, "Routine"))
        assert not is_data_range(Label("NesPrgRom", 0x100, 0x100, "Routine"))

    def test_lookup_ignores_code_labels(self):
        labels = store(Label("NesPrgRom", 0x100, None, "Routine"))
        assert data_range_at(labels, 0x100) is None


class TestDisassembleInlineArgs:
    def build(self):
        rom = MockReader()
        # bank 13 $8000: JSR ExecuteFarCall + inline bank/addr, then LDA #$01, RTS
        rom.write(13 * BANK_SIZE, bytes([
            0x20, 0x72, 0xD3,        # JSR $D372
            0x0B, 0x33, 0x90,        # inline: bank $0B, $9033
            0xA9, 0x01,              # LDA #$01
            0x60,                    # RTS
        ]))
        return rom

    def test_inline_args_keep_the_listing_aligned(self):
        listing = disassemble(self.build(), 13 * BANK_SIZE, count=4)
        kinds = [r.kind for r in listing.rows]
        assert kinds == ["code", "inline", "code", "code"]
        assert listing.rows[2].text.startswith("LDA #$01")
        assert listing.rows[3].text.startswith("RTS")

    def test_disabling_inline_args_desynchronises(self):
        """The vanilla behaviour, kept as an escape hatch."""
        listing = disassemble(self.build(), 13 * BANK_SIZE, count=4, inline_args=False)
        assert all(r.kind != "inline" for r in listing.rows)
        assert not listing.rows[2].text.startswith("LDA #$01")

    def test_inline_row_carries_the_routine_name(self):
        listing = disassemble(self.build(), 13 * BANK_SIZE, count=2)
        assert listing.rows[1].note == "ExecuteFarCall"
        assert "bank $0B $9033" in listing.rows[1].text


class TestDisassembleDataRanges:
    def test_labelled_range_becomes_db_rows(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes(range(0x10)))
        labels = store(Label("NesPrgRom", 13 * BANK_SIZE, 13 * BANK_SIZE + 7, "MyTable"))
        listing = disassemble(rom, 13 * BANK_SIZE, count=3, labels=labels)
        assert listing.rows[0].kind == "data"
        assert listing.rows[0].text.startswith(".db $00, $01")
        assert listing.rows[0].label == "MyTable"

    def test_opt_out_decodes_the_table(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes(range(0x10)))
        labels = store(Label("NesPrgRom", 13 * BANK_SIZE, 13 * BANK_SIZE + 7, "MyTable"))
        listing = disassemble(rom, 13 * BANK_SIZE, count=3, labels=labels, expand_data=False)
        assert all(r.kind != "data" for r in listing.rows)


class TestRoutineMode:
    def test_stops_at_rts(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xA9, 0x01, 0x60, 0xEA, 0xEA]))
        listing = disassemble(rom, 13 * BANK_SIZE, routine=True)
        assert [r.text.split()[0] for r in listing.rows] == ["LDA", "RTS"]
        assert listing.complete

    def test_early_rts_does_not_end_a_routine_with_a_pending_forward_branch(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([
            0xF0, 0x01,  # BEQ +1  -> $8003
            0x60,        # RTS      (early return, but $8003 is still pending)
            0xA9, 0x02,  # LDA #$02
            0x60,        # RTS
        ]))
        listing = disassemble(rom, 13 * BANK_SIZE, routine=True)
        assert len(listing.rows) == 4
        assert listing.rows[-1].text.startswith("RTS")

    def test_backward_jmp_terminates(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x10, bytes([0x4C, 0x00, 0x80, 0xAA, 0xBB]))
        listing = disassemble(rom, 13 * BANK_SIZE + 0x10, routine=True)
        assert len(listing.rows) == 1
        assert listing.complete

    def test_stops_at_a_data_range(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xA9, 0x01, 0xA9, 0x02, 0xFF, 0xFF]))
        labels = store(Label("NesPrgRom", 13 * BANK_SIZE + 4, 13 * BANK_SIZE + 5, "Tbl"))
        listing = disassemble(rom, 13 * BANK_SIZE, routine=True, labels=labels)
        assert len(listing.rows) == 2
        assert "Tbl" in listing.stop_reason

    def test_cap_is_reported_as_incomplete(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xEA] * 100))
        listing = disassemble(rom, 13 * BANK_SIZE, routine=True, max_instructions=10)
        assert len(listing.rows) == 10
        assert not listing.complete
        assert "cap" in listing.stop_reason

    def test_non_returning_call_terminates(self):
        """JSR DispatchInlineJumpTable JMPs away instead of returning."""
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([
            0x20, 0x27, 0xD2,  # JSR DispatchInlineJumpTable
            0x80, 0x00, 0x90,  # inline triple
            0x00,              # terminator
            0xEA, 0xEA,
        ]))
        listing = disassemble(rom, 13 * BANK_SIZE, routine=True)
        assert [r.kind for r in listing.rows] == ["code", "inline"]
        assert listing.complete

    def test_count_mode_is_never_flagged_incomplete(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xEA] * 100))
        assert disassemble(rom, 13 * BANK_SIZE, count=5).complete


class TestFindCodeReferences:
    def test_finds_jsr_in_the_same_bank(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([0x20, 0x00, 0xA0]))  # JSR $A000
        report = find_code_references(rom, 0xA000, 13)
        assert [r.kind for r in report.confirmed] == ["JSR"]

    def test_ignores_a_same_address_jsr_in_another_bank(self):
        """Bank 5's $A000 is not bank 13's $A000."""
        rom = MockReader()
        rom.write(5 * BANK_SIZE + 0x100, bytes([0x20, 0x00, 0xA0]))
        assert find_code_references(rom, 0xA000, 13).empty

    def test_fixed_bank_target_is_reachable_from_every_bank(self):
        rom = MockReader()
        rom.write(5 * BANK_SIZE + 0x100, bytes([0x20, 0x00, 0xD0]))  # JSR $D000
        assert len(find_code_references(rom, 0xD000, 15).confirmed) == 1

    def test_finds_a_relative_branch(self):
        """The case a byte-pattern search structurally cannot find."""
        rom = MockReader()
        # at $8100: BEQ +4 -> $8106
        rom.write(13 * BANK_SIZE + 0x100, bytes([0xF0, 0x04]))
        report = find_code_references(rom, 0x8106, 13)
        assert [r.kind for r in report.confirmed] == ["BEQ"]

    def test_finds_a_backward_branch(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([0xD0, 0xFC]))  # BNE -4 -> $80FE
        assert len(find_code_references(rom, 0x80FE, 13).confirmed) == 1

    def test_finds_a_far_call(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([0x20, 0x72, 0xD3, 0x08, 0x00, 0x80]))
        report = find_code_references(rom, 0x8000, 8)
        assert [r.kind for r in report.confirmed] == ["far call"]

    def test_far_call_to_a_different_bank_is_not_a_match(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([0x20, 0x72, 0xD3, 0x08, 0x00, 0x80]))
        assert find_code_references(rom, 0x8000, 9).empty

    def test_finds_an_entry_in_an_inline_dispatch_table(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([
            0x20, 0x27, 0xD2,  # JSR DispatchInlineJumpTable
            0x80, 0x11, 0x91,  # $80 -> $9111
            0x40, 0x22, 0x92,  # $40 -> $9222
            0x00,
        ]))
        report = find_code_references(rom, 0x9222, 13)
        assert [r.kind for r in report.confirmed] == ["dispatch table"]
        assert report.dispatch_sites_checked == 1

    def test_hit_inside_a_data_range_is_marked_suspect(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE + 0x100, bytes([0x20, 0x00, 0xA0]))
        labels = store(Label("NesPrgRom", 13 * BANK_SIZE + 0x0FF, 13 * BANK_SIZE + 0x110, "Tbl"))
        report = find_code_references(rom, 0xA000, 13, labels)
        assert len(report.refs) == 1
        assert report.refs[0].suspect
        assert report.empty, "suspect hits must not count as confirmed references"

    def test_report_always_states_what_it_could_not_cover(self):
        rom = MockReader()
        report = find_code_references(rom, 0xA000, 13)
        assert report.not_covered, "a null result must never stand alone"
        assert any("indirect" in item for item in report.not_covered)


class TestFindDataReferences:
    def test_finds_absolute_access(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xAD, 0xBB, 0x05]))  # LDA $05BB
        direct, _ = find_data_references(rom, 0x05BB)
        assert [r.kind for r in direct] == ["LDA"]

    def test_finds_zero_page_access(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0x85, 0x26]))  # STA $26
        direct, _ = find_data_references(rom, 0x26)
        assert [r.kind for r in direct] == ["STA"]

    def test_reach_lists_indexed_bases_below_the_target(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xBD, 0x9C, 0x05]))  # LDA $059C,X
        direct, reaching = find_data_references(rom, 0x05BB, reach=48)
        assert not direct
        assert 0x059C in reaching

    def test_reach_excludes_bases_further_than_asked(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xBD, 0x00, 0x05]))  # LDA $0500,X
        _, reaching = find_data_references(rom, 0x05BB, reach=16)
        assert not reaching

    def test_reach_ignores_non_indexed_opcodes(self):
        rom = MockReader()
        rom.write(13 * BANK_SIZE, bytes([0xAD, 0x9C, 0x05]))  # LDA $059C (no index)
        _, reaching = find_data_references(rom, 0x05BB, reach=48)
        assert not reaching


class TestFindPointerReferences:
    def test_finds_a_little_endian_pair(self):
        rom = MockReader()
        rom.write(12 * BANK_SIZE + 0x50, bytes([0xA2, 0x89]))
        hits = find_pointer_references(rom, 0x89A2)
        assert len(hits) == 1
        assert hits[0].bank == 12
