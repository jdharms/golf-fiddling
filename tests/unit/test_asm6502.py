"""
The in-repo 6502 assembler.

Two kinds of check. The first is direct: hand-known encodings, addressing-mode
selection, label and branch arithmetic, and the errors that stop a bad splice
from being assembled quietly. The second is differential — when `ca65` is on the
machine, a body of source is assembled both ways and the bytes must match, which
is a far stronger statement about the opcode table than any hand-written case.
"""

import shutil
import subprocess
import textwrap

import pytest

from golf.core.asm6502 import OPCODES, AsmError, assemble


def code(source: str, origin: int = 0x8000, **kwargs) -> bytes:
    return assemble(textwrap.dedent(source), origin, **kwargs).code


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------


def test_addressing_modes_pick_the_right_opcode() -> None:
    assert code("lda #$12") == bytes([0xA9, 0x12])
    assert code("lda $12") == bytes([0xA5, 0x12])
    assert code("lda $12,x") == bytes([0xB5, 0x12])
    assert code("lda $1234") == bytes([0xAD, 0x34, 0x12])
    assert code("lda $1234,x") == bytes([0xBD, 0x34, 0x12])
    assert code("lda $1234,y") == bytes([0xB9, 0x34, 0x12])
    assert code("lda ($12,x)") == bytes([0xA1, 0x12])
    assert code("lda ($12),y") == bytes([0xB1, 0x12])
    assert code("ldx $12,y") == bytes([0xB6, 0x12])
    assert code("jmp ($1234)") == bytes([0x6C, 0x34, 0x12])
    assert code("asl") == bytes([0x0A])
    assert code("asl a") == bytes([0x0A])
    assert code("asl $1234,x") == bytes([0x1E, 0x34, 0x12])
    assert code("rts") == bytes([0x60])


def test_zero_page_is_forced_when_asked() -> None:
    """`zp:` matters for an address the assembler has not seen yet."""
    assert code("lda zp:Pointer\nPointer = $44") == bytes([0xA5, 0x44])
    assert code("lda Pointer\nPointer = $44") == bytes([0xAD, 0x44, 0x00])


def test_a_forward_reference_stays_absolute_in_both_passes() -> None:
    """A label that turns out to be in zero page must not shrink the code."""
    program = assemble("lda Later\nrts\nLater = $22", 0x8000)
    assert program.code == bytes([0xAD, 0x22, 0x00, 0x60])


def test_numbers_and_characters() -> None:
    assert code("lda #%00001111") == bytes([0xA9, 0x0F])
    assert code("lda #65") == bytes([0xA9, 0x41])
    assert code("lda #'A'") == bytes([0xA9, 0x41])


def test_high_and_low_byte_modifiers() -> None:
    source = """
        Target = $ABCD
        lda #<Target
        lda #>Target
    """
    assert code(source) == bytes([0xA9, 0xCD, 0xA9, 0xAB])


def test_expressions_add_and_subtract() -> None:
    source = """
        Base = $0300
        lda Base + 4
        lda Base - 1
        lda #<Base + 2
    """
    assert code(source) == bytes([0xAD, 0x04, 0x03, 0xAD, 0xFF, 0x02, 0xA9, 0x02])


# --------------------------------------------------------------------------
# Labels and branches
# --------------------------------------------------------------------------


def test_labels_resolve_forwards_and_backwards() -> None:
    source = """
        Start:
            jsr Later
            jmp Start
        Later:
            rts
    """
    program = assemble(textwrap.dedent(source), 0x8400)
    assert program.symbols["Start"] == 0x8400
    assert program.symbols["Later"] == 0x8406
    assert program.code == bytes([0x20, 0x06, 0x84, 0x4C, 0x00, 0x84, 0x60])


def test_local_labels_are_scoped_to_the_preceding_global() -> None:
    source = """
        First:
        @loop:
            dex
            bne @loop
            rts
        Second:
        @loop:
            iny
            bne @loop
            rts
    """
    program = assemble(textwrap.dedent(source), 0x8000)
    assert program.symbols["First@loop"] == 0x8000
    assert program.symbols["Second@loop"] == 0x8004
    assert program.code == bytes([0xCA, 0xD0, 0xFD, 0x60, 0xC8, 0xD0, 0xFD, 0x60])


def test_branch_displacements_are_relative_to_the_next_instruction() -> None:
    assert code("bne Target\nTarget:") == bytes([0xD0, 0x00])
    assert code("Target:\n.res 4\nbne Target") == bytes([0, 0, 0, 0, 0xD0, 0xFA])


def test_a_branch_out_of_range_is_an_error() -> None:
    with pytest.raises(AsmError, match="branch out of range"):
        assemble("bne Target\n.res 200\nTarget:\nrts", 0x8000)


# --------------------------------------------------------------------------
# Directives
# --------------------------------------------------------------------------


def test_data_directives() -> None:
    source = """
        .byte $01, 2, '3'
        .word $1234, Label
        .res 3, $EA
        Label:
    """
    assert code(source, 0x8000) == bytes(
        [0x01, 0x02, 0x33, 0x34, 0x12, 0x0A, 0x80, 0xEA, 0xEA, 0xEA]
    )


def test_strings_in_byte_directives() -> None:
    assert code('.byte "hi", $00') == b"hi\x00"
    assert code('.byte "a,b"') == b"a,b"


def test_org_pads_forward_and_refuses_to_move_back() -> None:
    program = assemble("lda #$00\n.org $8004\nrts", 0x8000)
    assert program.code == bytes([0xA9, 0x00, 0x00, 0x00, 0x60])
    assert program.symbols == {}
    with pytest.raises(AsmError, match="cannot move backwards"):
        assemble(".res 8\n.org $8004", 0x8000)


def test_align_pads_to_the_boundary() -> None:
    program = assemble(".res 3\n.align 4, $FF\nTable:\n.byte $01", 0x8000)
    assert program.code == bytes([0, 0, 0, 0xFF, 0x01])
    assert program.symbols["Table"] == 0x8004


def test_predefined_symbols_are_visible() -> None:
    program = assemble("lda GameProgress", 0x8000, {"GameProgress": 0x95})
    assert program.code == bytes([0xA5, 0x95])


def test_program_reports_size_end_and_offsets() -> None:
    program = assemble("Entry:\nrts\nTable:\n.byte $01", 0x8400)
    assert program.size == 2
    assert program.end == 0x8402
    assert program.symbol("Table") == 0x8401
    assert program.at("Table") == 1


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("lda", "needs an operand"),
        ("sta #$01", "no immediate mode"),
        ("lda ($1234)", "no indirect mode"),
        ("foo $12", "unknown instruction"),
        ("lda Missing", "undefined symbol"),
        ("Label:\nLabel:", "duplicate label"),
        ("@loop:", "before any global label"),
        (".byte $100", "out of range"),
        (".nonsense 1", "unknown directive"),
    ],
)
def test_bad_source_is_rejected(source: str, message: str) -> None:
    with pytest.raises(AsmError, match=message):
        assemble(textwrap.dedent(source), 0x8000)


def test_errors_name_the_line() -> None:
    with pytest.raises(AsmError, match="line 3"):
        assemble("rts\nrts\nlda Missing\n", 0x8000)


def test_comments_and_blank_lines_are_ignored() -> None:
    source = """
        ; leading comment

            lda #$01    ; trailing comment
            rts
    """
    assert code(source) == bytes([0xA9, 0x01, 0x60])


# --------------------------------------------------------------------------
# Differential against ca65
# --------------------------------------------------------------------------

CA65_SOURCE = """
    .setcpu "6502"
    .org $8400
Start:
        lda #$12
        ldx #$00
        ldy #$FF
@loop:
        lda Table,x
        sta $0700,y
        adc ($40),y
        eor ($41,x)
        and $42,x
        ora $4300,y
        cmp Table
        cpx #$10
        cpy $44
        asl a
        lsr Table,x
        rol $45
        ror $4600,x
        inc Table
        dec $47,x
        inx
        dey
        bne @loop
        beq Start
        bcc @loop
        bcs Start
        bmi @loop
        bpl Start
        bvc @loop
        bvs Start
        jsr Helper
        jmp (Vector)
        sec
        sbc #$01
        clc
        cld
        cli
        clv
        sei
        sed
        pha
        php
        pla
        plp
        tax
        tay
        tsx
        txa
        txs
        tya
        stx $48
        sty $49,x
        stx $4A00
        bit $4B
        bit $4C00
        nop
        brk
        rti
Helper:
        rts
Vector:
        .word Start
Table:
        .byte $01,$02,$03
"""

OUR_SOURCE = CA65_SOURCE.replace('.setcpu "6502"\n', "").replace("@loop", "@loop")


def _ca65_bytes(tmp_path) -> bytes:
    source = tmp_path / "probe.s"
    source.write_text(CA65_SOURCE)
    obj = tmp_path / "probe.o"
    config = tmp_path / "probe.cfg"
    config.write_text(
        "MEMORY { RAM: start = $8400, size = $1000, file = %O; }\n"
        "SEGMENTS { CODE: load = RAM, type = ro; }\n"
    )
    subprocess.run(
        ["ca65", "-o", str(obj), str(source)], check=True, capture_output=True
    )
    out = tmp_path / "probe.bin"
    subprocess.run(
        ["ld65", "-C", str(config), "-o", str(out), str(obj)],
        check=True,
        capture_output=True,
    )
    return out.read_bytes()


@pytest.mark.skipif(
    shutil.which("ca65") is None or shutil.which("ld65") is None,
    reason="cc65 is not installed",
)
def test_matches_ca65_byte_for_byte(tmp_path) -> None:
    ours = assemble(OUR_SOURCE, 0x8400)
    assert ours.code == _ca65_bytes(tmp_path)


def test_every_opcode_in_the_table_is_unique() -> None:
    """A typo in the table would otherwise assemble silently to the wrong byte."""
    seen: dict[int, str] = {}
    for mnemonic, modes in OPCODES.items():
        for mode, opcode in modes.items():
            assert 0 <= opcode <= 0xFF
            assert opcode not in seen, f"{mnemonic} {mode} collides with {seen[opcode]}"
            seen[opcode] = f"{mnemonic} {mode}"
    assert len(seen) == 151  # the documented NMOS 6502 instruction set
