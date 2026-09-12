"""
A small two-pass 6502 assembler, for writing patch code as assembly instead of
hand-counted byte arrays.

It exists because the scorecard QR routine (`golf/qr/port/`) is well over a
thousand bytes of new code: hand-assembling that, and re-hand-assembling it
every time an instruction moves, is not a thing a person should do. Keeping the
assembler in-repo and in Python also means the tests can assemble and run the
code under py65 with no external toolchain.

Syntax is the usual one:

    ; a comment
    .org $8400
    CONSTANT = $1234        ; constants may be defined anywhere
    Label:                  ; global label
    @loop:                  ; local label, scoped to the preceding global one
        lda #<Label         ; < low byte, > high byte
        ldx #$00
        sta $0700,x
        lda (Pointer),y
        jmp (Vector)
        bne @loop
        .byte $01, $02, "text", 'x'
        .word Label, Label + 2
        .res 8, $FF         ; 8 bytes of $FF (fill defaults to $00)

Expressions are labels, `$hex`, `%binary`, decimal, `'c'`, joined by `+` and
`-`, optionally prefixed with `<` or `>`.

Sizing is decided in the first pass: an operand whose value is already known and
below `$100` assembles as zero page, everything else (including every forward
reference) as absolute. Write `zp:` before an operand to force zero page.
"""

import re
from dataclasses import dataclass, field

# Addressing modes, by the name used in the opcode table below.
IMPLIED = "imp"
ACCUMULATOR = "acc"
IMMEDIATE = "imm"
ZERO_PAGE = "zp"
ZERO_PAGE_X = "zpx"
ZERO_PAGE_Y = "zpy"
ABSOLUTE = "abs"
ABSOLUTE_X = "absx"
ABSOLUTE_Y = "absy"
INDIRECT = "ind"
INDIRECT_X = "indx"
INDIRECT_Y = "indy"
RELATIVE = "rel"

#: Operand width in bytes, by mode (the opcode itself is not counted).
_OPERAND_SIZE = {
    IMPLIED: 0,
    ACCUMULATOR: 0,
    IMMEDIATE: 1,
    ZERO_PAGE: 1,
    ZERO_PAGE_X: 1,
    ZERO_PAGE_Y: 1,
    ABSOLUTE: 2,
    ABSOLUTE_X: 2,
    ABSOLUTE_Y: 2,
    INDIRECT: 2,
    INDIRECT_X: 1,
    INDIRECT_Y: 1,
    RELATIVE: 1,
}

#: The legal NMOS 6502 instruction set. Undocumented opcodes are deliberately
#: absent: this assembles code that has to run on a real cartridge.
OPCODES: dict[str, dict[str, int]] = {
    "adc": {
        IMMEDIATE: 0x69,
        ZERO_PAGE: 0x65,
        ZERO_PAGE_X: 0x75,
        ABSOLUTE: 0x6D,
        ABSOLUTE_X: 0x7D,
        ABSOLUTE_Y: 0x79,
        INDIRECT_X: 0x61,
        INDIRECT_Y: 0x71,
    },
    "and": {
        IMMEDIATE: 0x29,
        ZERO_PAGE: 0x25,
        ZERO_PAGE_X: 0x35,
        ABSOLUTE: 0x2D,
        ABSOLUTE_X: 0x3D,
        ABSOLUTE_Y: 0x39,
        INDIRECT_X: 0x21,
        INDIRECT_Y: 0x31,
    },
    "asl": {
        ACCUMULATOR: 0x0A,
        ZERO_PAGE: 0x06,
        ZERO_PAGE_X: 0x16,
        ABSOLUTE: 0x0E,
        ABSOLUTE_X: 0x1E,
    },
    "bcc": {RELATIVE: 0x90},
    "bcs": {RELATIVE: 0xB0},
    "beq": {RELATIVE: 0xF0},
    "bit": {ZERO_PAGE: 0x24, ABSOLUTE: 0x2C},
    "bmi": {RELATIVE: 0x30},
    "bne": {RELATIVE: 0xD0},
    "bpl": {RELATIVE: 0x10},
    "brk": {IMPLIED: 0x00},
    "bvc": {RELATIVE: 0x50},
    "bvs": {RELATIVE: 0x70},
    "clc": {IMPLIED: 0x18},
    "cld": {IMPLIED: 0xD8},
    "cli": {IMPLIED: 0x58},
    "clv": {IMPLIED: 0xB8},
    "cmp": {
        IMMEDIATE: 0xC9,
        ZERO_PAGE: 0xC5,
        ZERO_PAGE_X: 0xD5,
        ABSOLUTE: 0xCD,
        ABSOLUTE_X: 0xDD,
        ABSOLUTE_Y: 0xD9,
        INDIRECT_X: 0xC1,
        INDIRECT_Y: 0xD1,
    },
    "cpx": {IMMEDIATE: 0xE0, ZERO_PAGE: 0xE4, ABSOLUTE: 0xEC},
    "cpy": {IMMEDIATE: 0xC0, ZERO_PAGE: 0xC4, ABSOLUTE: 0xCC},
    "dec": {ZERO_PAGE: 0xC6, ZERO_PAGE_X: 0xD6, ABSOLUTE: 0xCE, ABSOLUTE_X: 0xDE},
    "dex": {IMPLIED: 0xCA},
    "dey": {IMPLIED: 0x88},
    "eor": {
        IMMEDIATE: 0x49,
        ZERO_PAGE: 0x45,
        ZERO_PAGE_X: 0x55,
        ABSOLUTE: 0x4D,
        ABSOLUTE_X: 0x5D,
        ABSOLUTE_Y: 0x59,
        INDIRECT_X: 0x41,
        INDIRECT_Y: 0x51,
    },
    "inc": {ZERO_PAGE: 0xE6, ZERO_PAGE_X: 0xF6, ABSOLUTE: 0xEE, ABSOLUTE_X: 0xFE},
    "inx": {IMPLIED: 0xE8},
    "iny": {IMPLIED: 0xC8},
    "jmp": {ABSOLUTE: 0x4C, INDIRECT: 0x6C},
    "jsr": {ABSOLUTE: 0x20},
    "lda": {
        IMMEDIATE: 0xA9,
        ZERO_PAGE: 0xA5,
        ZERO_PAGE_X: 0xB5,
        ABSOLUTE: 0xAD,
        ABSOLUTE_X: 0xBD,
        ABSOLUTE_Y: 0xB9,
        INDIRECT_X: 0xA1,
        INDIRECT_Y: 0xB1,
    },
    "ldx": {
        IMMEDIATE: 0xA2,
        ZERO_PAGE: 0xA6,
        ZERO_PAGE_Y: 0xB6,
        ABSOLUTE: 0xAE,
        ABSOLUTE_Y: 0xBE,
    },
    "ldy": {
        IMMEDIATE: 0xA0,
        ZERO_PAGE: 0xA4,
        ZERO_PAGE_X: 0xB4,
        ABSOLUTE: 0xAC,
        ABSOLUTE_X: 0xBC,
    },
    "lsr": {
        ACCUMULATOR: 0x4A,
        ZERO_PAGE: 0x46,
        ZERO_PAGE_X: 0x56,
        ABSOLUTE: 0x4E,
        ABSOLUTE_X: 0x5E,
    },
    "nop": {IMPLIED: 0xEA},
    "ora": {
        IMMEDIATE: 0x09,
        ZERO_PAGE: 0x05,
        ZERO_PAGE_X: 0x15,
        ABSOLUTE: 0x0D,
        ABSOLUTE_X: 0x1D,
        ABSOLUTE_Y: 0x19,
        INDIRECT_X: 0x01,
        INDIRECT_Y: 0x11,
    },
    "pha": {IMPLIED: 0x48},
    "php": {IMPLIED: 0x08},
    "pla": {IMPLIED: 0x68},
    "plp": {IMPLIED: 0x28},
    "rol": {
        ACCUMULATOR: 0x2A,
        ZERO_PAGE: 0x26,
        ZERO_PAGE_X: 0x36,
        ABSOLUTE: 0x2E,
        ABSOLUTE_X: 0x3E,
    },
    "ror": {
        ACCUMULATOR: 0x6A,
        ZERO_PAGE: 0x66,
        ZERO_PAGE_X: 0x76,
        ABSOLUTE: 0x6E,
        ABSOLUTE_X: 0x7E,
    },
    "rti": {IMPLIED: 0x40},
    "rts": {IMPLIED: 0x60},
    "sbc": {
        IMMEDIATE: 0xE9,
        ZERO_PAGE: 0xE5,
        ZERO_PAGE_X: 0xF5,
        ABSOLUTE: 0xED,
        ABSOLUTE_X: 0xFD,
        ABSOLUTE_Y: 0xF9,
        INDIRECT_X: 0xE1,
        INDIRECT_Y: 0xF1,
    },
    "sec": {IMPLIED: 0x38},
    "sed": {IMPLIED: 0xF8},
    "sei": {IMPLIED: 0x78},
    "sta": {
        ZERO_PAGE: 0x85,
        ZERO_PAGE_X: 0x95,
        ABSOLUTE: 0x8D,
        ABSOLUTE_X: 0x9D,
        ABSOLUTE_Y: 0x99,
        INDIRECT_X: 0x81,
        INDIRECT_Y: 0x91,
    },
    "stx": {ZERO_PAGE: 0x86, ZERO_PAGE_Y: 0x96, ABSOLUTE: 0x8E},
    "sty": {ZERO_PAGE: 0x84, ZERO_PAGE_X: 0x94, ABSOLUTE: 0x8C},
    "tax": {IMPLIED: 0xAA},
    "tay": {IMPLIED: 0xA8},
    "tsx": {IMPLIED: 0xBA},
    "txa": {IMPLIED: 0x8A},
    "txs": {IMPLIED: 0x9A},
    "tya": {IMPLIED: 0x98},
}

#: Mnemonics whose only mode is a relative branch.
BRANCHES = frozenset(name for name, modes in OPCODES.items() if RELATIVE in modes)

DIRECTIVES = frozenset({".org", ".byte", ".db", ".word", ".dw", ".res", ".align"})


class AsmError(Exception):
    """A source line the assembler cannot make sense of."""

    def __init__(self, message: str, line_number: int | None = None, line: str = ""):
        self.line_number = line_number
        self.line = line
        if line_number is not None:
            message = f"line {line_number}: {message}"
            if line:
                message = f"{message}\n    {line.strip()}"
        super().__init__(message)


@dataclass(frozen=True)
class Program:
    """Assembled bytes, plus where everything ended up."""

    origin: int
    code: bytes
    symbols: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.code)

    @property
    def end(self) -> int:
        """One past the last byte, as a CPU address."""
        return self.origin + len(self.code)

    def symbol(self, name: str) -> int:
        try:
            return self.symbols[name]
        except KeyError:
            raise AsmError(f"no such symbol: {name}") from None

    def at(self, name: str) -> int:
        """A symbol's offset into `code` rather than its CPU address."""
        return self.symbol(name) - self.origin


# --------------------------------------------------------------------------
# Lexing
# --------------------------------------------------------------------------

_LABEL_RE = re.compile(r"^(@?[A-Za-z_][A-Za-z0-9_]*):")
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
_TOKEN_RE = re.compile(
    r"""
    (?P<string>"[^"]*")
  | (?P<char>'[^']')
  | (?P<hex>\$[0-9A-Fa-f]+)
  | (?P<bin>%[01]+)
  | (?P<dec>\d+)
  | (?P<name>@?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[+\-])
""",
    re.VERBOSE,
)


def _strip_comment(line: str) -> str:
    out = []
    in_string = False
    quote = ""
    for ch in line:
        if in_string:
            out.append(ch)
            if ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            out.append(ch)
            continue
        if ch == ";":
            break
        out.append(ch)
    return "".join(out).strip()


def _split_args(text: str) -> list[str]:
    """Split on commas that are not inside a string or character literal."""
    args, current, in_string, quote = [], [], False, ""
    for ch in text:
        if in_string:
            current.append(ch)
            if ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            current.append(ch)
            continue
        if ch == ",":
            args.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if current or not args:
        args.append("".join(current).strip())
    return [a for a in args if a != ""]


# --------------------------------------------------------------------------
# The assembler
# --------------------------------------------------------------------------


class _Assembler:
    def __init__(self, source: str, origin: int, symbols: dict[str, int] | None):
        self.source = source
        self.origin = origin
        self.symbols: dict[str, int] = dict(symbols or {})
        self.pc = origin
        self.scope = ""
        self.line_number = 0
        self.line = ""
        self.defining = True
        #: Addressing mode chosen on the sizing pass, by line number. Pass 2
        #: reuses it: a symbol that was still a forward reference in pass 1
        #: sized as absolute, and must not shrink to zero page once known.
        self.modes: dict[int, str] = {}

    # -- errors and expressions -------------------------------------------

    def _error(self, message: str) -> AsmError:
        return AsmError(message, self.line_number, self.line)

    def _qualify(self, name: str) -> str:
        return f"{self.scope}{name}" if name.startswith("@") else name

    def _value(self, token: str, kind: str, resolve: bool) -> int:
        if kind == "hex":
            return int(token[1:], 16)
        if kind == "bin":
            return int(token[1:], 2)
        if kind == "dec":
            return int(token, 10)
        if kind == "char":
            return ord(token[1])
        name = self._qualify(token)
        if name in self.symbols:
            return self.symbols[name]
        if resolve:
            raise self._error(f"undefined symbol: {token}")
        return -1  # unknown on the sizing pass

    def evaluate(self, text: str, resolve: bool = True) -> int:
        """Evaluate an expression. Returns -1 for an unresolved forward reference."""
        text = text.strip()
        if not text:
            raise self._error("empty expression")

        modifier = ""
        if text[0] in "<>":
            modifier, text = text[0], text[1:].strip()

        total, sign, seen, unknown = 0, 1, False, False
        position = 0
        while position < len(text):
            if text[position].isspace():
                position += 1
                continue
            match = _TOKEN_RE.match(text, position)
            if not match:
                raise self._error(f"cannot parse expression: {text!r}")
            position = match.end()
            kind = match.lastgroup
            assert kind is not None
            token = match.group()
            if kind == "op":
                sign = 1 if token == "+" else -1
                continue
            if kind == "string":
                raise self._error("a string is not a value")
            value = self._value(token, kind, resolve)
            if value < 0:
                unknown = True
            total += sign * value
            sign = 1
            seen = True

        if not seen:
            raise self._error(f"cannot parse expression: {text!r}")
        if unknown:
            return -1
        if modifier == "<":
            return total & 0xFF
        if modifier == ">":
            return (total >> 8) & 0xFF
        return total & 0xFFFF

    # -- operand parsing --------------------------------------------------

    def parse_operand(self, mnemonic: str, operand: str, resolve: bool):
        """Return (mode, expression text) for one instruction's operand."""
        modes = OPCODES[mnemonic]
        operand = operand.strip()

        if not operand:
            if IMPLIED in modes:
                return IMPLIED, ""
            if ACCUMULATOR in modes:
                return ACCUMULATOR, ""
            raise self._error(f"{mnemonic} needs an operand")

        if operand.lower() == "a" and ACCUMULATOR in modes:
            return ACCUMULATOR, ""

        if operand.startswith("#"):
            if IMMEDIATE not in modes:
                return self._reject(mnemonic, "immediate")
            return IMMEDIATE, operand[1:]

        if mnemonic in BRANCHES:
            return RELATIVE, operand

        if operand.startswith("("):
            lowered = operand.lower()
            if lowered.endswith("),y"):
                if INDIRECT_Y not in modes:
                    return self._reject(mnemonic, "(indirect),y")
                return INDIRECT_Y, operand[1:-3]
            if lowered.endswith(",x)"):
                if INDIRECT_X not in modes:
                    return self._reject(mnemonic, "(indirect,x)")
                return INDIRECT_X, operand[1:-3]
            if lowered.endswith(")"):
                if INDIRECT not in modes:
                    return self._reject(mnemonic, "indirect")
                return INDIRECT, operand[1:-1]
            raise self._error(f"malformed operand: {operand}")

        index = ""
        if operand.lower().endswith(",x"):
            index, operand = "x", operand[:-2].strip()
        elif operand.lower().endswith(",y"):
            index, operand = "y", operand[:-2].strip()

        forced_zp = False
        if operand.lower().startswith("zp:"):
            forced_zp, operand = True, operand[3:].strip()

        value = self.evaluate(operand, resolve=False)
        zero_page = forced_zp or (0 <= value <= 0xFF)

        if index == "x":
            if zero_page and ZERO_PAGE_X in modes:
                return ZERO_PAGE_X, operand
            if ABSOLUTE_X not in modes:
                return self._reject(mnemonic, "absolute,x")
            return ABSOLUTE_X, operand
        if index == "y":
            if zero_page and ZERO_PAGE_Y in modes:
                return ZERO_PAGE_Y, operand
            if ABSOLUTE_Y not in modes:
                return self._reject(mnemonic, "absolute,y")
            return ABSOLUTE_Y, operand
        if zero_page and ZERO_PAGE in modes:
            return ZERO_PAGE, operand
        if ABSOLUTE not in modes:
            return self._reject(mnemonic, "absolute")
        return ABSOLUTE, operand

    def _reject(self, mnemonic: str, mode: str):
        raise self._error(f"{mnemonic} has no {mode} mode")

    # -- passes -----------------------------------------------------------

    def _lines(self):
        for number, raw in enumerate(self.source.splitlines(), start=1):
            self.line_number, self.line = number, raw
            text = _strip_comment(raw)
            if text:
                yield text

    def _handle_label(self, text: str) -> str:
        match = _LABEL_RE.match(text)
        if not match:
            return text
        name = match.group(1)
        if name.startswith("@"):
            if not self.scope:
                raise self._error(f"local label {name} before any global label")
            full = f"{self.scope}{name}"
        else:
            full = name
            self.scope = name
        if self.defining:
            if full in self.symbols:
                raise self._error(f"duplicate label: {name}")
            self.symbols[full] = self.pc
        return text[match.end() :].strip()

    def _directive_size(self, name: str, args: list[str]) -> int:
        if name == ".org":
            target = self.evaluate(args[0])
            if target < self.pc:
                raise self._error(".org cannot move backwards")
            return target - self.pc
        if name in (".byte", ".db"):
            total = 0
            for arg in args:
                total += len(self._string_bytes(arg)) if arg.startswith('"') else 1
            return total
        if name in (".word", ".dw"):
            return 2 * len(args)
        if name == ".res":
            count = self.evaluate(args[0])
            if count < 0:
                raise self._error(".res needs a resolved length")
            return count
        if name == ".align":
            boundary = self.evaluate(args[0])
            if boundary <= 0:
                raise self._error(".align needs a positive boundary")
            return (-self.pc) % boundary
        raise self._error(f"unknown directive: {name}")

    def _string_bytes(self, arg: str) -> bytes:
        if not arg.endswith('"') or len(arg) < 2:
            raise self._error(f"unterminated string: {arg}")
        return arg[1:-1].encode("ascii")

    def _emit_directive(self, name: str, args: list[str], out: bytearray) -> None:
        if name == ".org":
            target = self.evaluate(args[0])
            if target < self.pc:
                raise self._error(".org cannot move backwards")
            out.extend(bytes(target - self.pc))
            self.pc = target
            return
        if name in (".byte", ".db"):
            for arg in args:
                if arg.startswith('"'):
                    data = self._string_bytes(arg)
                    out.extend(data)
                    self.pc += len(data)
                    continue
                value = self.evaluate(arg)
                if not 0 <= value <= 0xFF:
                    raise self._error(f".byte value out of range: {arg}")
                out.append(value)
                self.pc += 1
            return
        if name in (".word", ".dw"):
            for arg in args:
                value = self.evaluate(arg)
                out.extend((value & 0xFF, (value >> 8) & 0xFF))
                self.pc += 2
            return
        if name == ".res":
            count = self.evaluate(args[0])
            fill = self.evaluate(args[1]) if len(args) > 1 else 0
            out.extend(bytes([fill & 0xFF]) * count)
            self.pc += count
            return
        if name == ".align":
            boundary = self.evaluate(args[0])
            fill = self.evaluate(args[1]) if len(args) > 1 else 0
            padding = (-self.pc) % boundary
            out.extend(bytes([fill & 0xFF]) * padding)
            self.pc += padding
            return
        raise self._error(f"unknown directive: {name}")

    def _split_statement(self, text: str) -> tuple[str, str]:
        parts = text.split(None, 1)
        return parts[0], (parts[1].strip() if len(parts) > 1 else "")

    def run(self) -> Program:
        # Pass 1: place labels and measure every statement.
        self.defining = True
        self.pc = self.origin
        self.scope = ""
        for text in self._lines():
            text = self._handle_label(text)
            if not text:
                continue
            assignment = _ASSIGN_RE.match(text)
            if assignment:
                name, expression = assignment.groups()
                self.symbols[name] = self.evaluate(expression)
                continue
            head, rest = self._split_statement(text)
            lowered = head.lower()
            if lowered in DIRECTIVES:
                self.pc += self._directive_size(lowered, _split_args(rest))
                continue
            if lowered.startswith("."):
                raise self._error(f"unknown directive: {head}")
            if lowered not in OPCODES:
                raise self._error(f"unknown instruction: {head}")
            mode, _ = self.parse_operand(lowered, rest, resolve=False)
            self.modes[self.line_number] = mode
            self.pc += 1 + _OPERAND_SIZE[mode]

        # Pass 2: emit, with every symbol known.
        self.defining = False
        self.pc = self.origin
        self.scope = ""
        out = bytearray()
        for text in self._lines():
            text = self._handle_label(text)
            if not text:
                continue
            if _ASSIGN_RE.match(text):
                continue
            head, rest = self._split_statement(text)
            lowered = head.lower()
            if lowered in DIRECTIVES:
                self._emit_directive(lowered, _split_args(rest), out)
                continue
            _, expression = self.parse_operand(lowered, rest, resolve=True)
            mode = self.modes[self.line_number]
            opcode = OPCODES[lowered][mode]
            size = _OPERAND_SIZE[mode]
            self.pc += 1 + size
            out.append(opcode)
            if size == 0:
                continue
            value = self.evaluate(expression)
            if mode == RELATIVE:
                offset = value - self.pc
                if not -128 <= offset <= 127:
                    raise self._error(
                        f"branch out of range: {offset} bytes to {expression.strip()}"
                    )
                out.append(offset & 0xFF)
            elif size == 1:
                if not 0 <= value <= 0xFF:
                    raise self._error(f"operand out of range for {mode}: {expression}")
                out.append(value)
            else:
                out.extend((value & 0xFF, (value >> 8) & 0xFF))

        return Program(origin=self.origin, code=bytes(out), symbols=dict(self.symbols))


def assemble(
    source: str, origin: int = 0x8000, symbols: dict[str, int] | None = None
) -> Program:
    """
    Assemble `source`, starting at `origin`.

    `symbols` pre-defines constants — the addresses a routine is spliced against,
    say — exactly as if the source had assigned them at the top.
    """
    return _Assembler(source, origin, symbols).run()
