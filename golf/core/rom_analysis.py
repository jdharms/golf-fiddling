"""
Static analysis helpers for ROM exploration.

Three things a plain byte search or a naive disassembler gets wrong on this
ROM, factored out so `golf-rom-peek` (and tests) can share them:

1. **Inline arguments.** Several routines read bytes that follow their own
   `JSR` and then skip past them, so a linear disassembly desynchronises for
   ten or twenty instructions afterwards. `INLINE_ARG_ROUTINES` records how
   many bytes each consumes.

2. **Data mistaken for code.** Range labels in the `.mlb` mark tables; a
   disassembler that decodes them produces plausible-looking nonsense.

3. **References the obvious search misses.** A branch target is stored as a
   displacement, not an address, so no byte pattern finds it. Far calls bury
   the target in inline arguments. `find_references` covers those, and -
   just as importantly - reports what it could *not* cover, because a null
   result from any static scan is never proof that an address is dead.
"""

from dataclasses import dataclass, field

from golf.core.rom_utils import (
    FIXED_BANK_PRG_START,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
    prg_to_bank_and_cpu,
)

FIXED_BANK = 15

# --- Inline argument routines ------------------------------------------

FIXED = "fixed"
PAIRS = "pairs"
TRIPLES = "triples"


@dataclass(frozen=True)
class InlineArgSpec:
    """How many bytes a routine consumes from after its own JSR."""

    name: str
    kind: str = FIXED
    length: int = 0  # FIXED only
    style: str = "bytes"  # "bytes" | "word" | "bank_addr"
    returns: bool = True  # False = control never comes back to the call site

    def measure(self, data: bytes) -> int:
        """Byte count consumed, given the bytes starting just after the JSR."""
        if self.kind == FIXED:
            return self.length
        stride = 2 if self.kind == PAIRS else 3
        n = 0
        while n < len(data) and data[n] != 0x00:
            n += stride
        return min(n + 1, len(data))  # include the $00 terminator

    def render(self, args: bytes) -> str:
        if self.style == "bank_addr" and len(args) >= 3:
            addr = args[1] | (args[2] << 8)
            return f".db ${args[0]:02X}, ${args[1]:02X}, ${args[2]:02X}   ; -> bank ${args[0]:02X} ${addr:04X}"
        if self.style == "word" and len(args) >= 2:
            addr = args[0] | (args[1] << 8)
            return f".dw ${addr:04X}"
        body = ", ".join(f"${b:02X}" for b in args)
        if self.kind in (PAIRS, TRIPLES):
            stride = 2 if self.kind == PAIRS else 3
            entries = []
            for i in range(0, len(args) - 1, stride):
                chunk = args[i : i + stride]
                if len(chunk) < stride or chunk[0] == 0x00:
                    break
                if self.kind == TRIPLES and self.style == "key_addr":
                    entries.append(f"${chunk[0]:02X}->${chunk[2] << 8 | chunk[1]:04X}")
                else:
                    entries.append("/".join(f"${b:02X}" for b in chunk))
            if entries:
                return f".db {body}   ; {', '.join(entries)}, end"
        return f".db {body}"


# Keyed by (bank, cpu_addr); bank None means the always-mapped fixed bank.
# Every entry below was confirmed by disassembling the routine and checking
# that it advances its own return address past the arguments.
INLINE_ARG_ROUTINES: dict[tuple[int | None, int], InlineArgSpec] = {
    (None, 0xD372): InlineArgSpec("ExecuteFarCall", FIXED, 3, "bank_addr"),
    (None, 0xD45F): InlineArgSpec("LoadCompressedGraphics", FIXED, 3, "bank_addr"),
    (None, 0xCE84): InlineArgSpec("WriteNametableTiles", FIXED, 2, "word"),
    (None, 0xD80A): InlineArgSpec("Load32BytesToBuffer", FIXED, 2, "word"),
    (None, 0xD8A2): InlineArgSpec("ReadInlineWordParameter", FIXED, 2, "word"),
    (None, 0xD227): InlineArgSpec(
        "DispatchInlineJumpTable", TRIPLES, style="key_addr", returns=False
    ),
    (12, 0x8A14): InlineArgSpec("LookupInlineByteTable", PAIRS),
    (12, 0x8A56): InlineArgSpec("LookupInlineRangeTable", TRIPLES),
}

# The dispatcher whose inline tables find_references can actually search.
DISPATCH_INLINE_JUMP_TABLE = 0xD227


def inline_spec_for(target_cpu: int, bank: int | None) -> InlineArgSpec | None:
    """The inline-argument spec for a JSR target, or None."""
    if target_cpu >= 0xC000:
        return INLINE_ARG_ROUTINES.get((None, target_cpu))
    if bank is None:
        return None
    return INLINE_ARG_ROUTINES.get((bank, target_cpu))


# --- Opcode groups ------------------------------------------------------

BRANCH_OPCODES = {
    0x10: "BPL", 0x30: "BMI", 0x50: "BVC", 0x70: "BVS",
    0x90: "BCC", 0xB0: "BCS", 0xD0: "BNE", 0xF0: "BEQ",
}

JSR = 0x20
JMP_ABS = 0x4C
JMP_IND = 0x6C
RTS = 0x60
RTI = 0x40

# Absolute addressing, no index - "this instruction names this address".
ABS_OPCODES = {
    0x0D: "ORA", 0x0E: "ASL", 0x2C: "BIT", 0x2D: "AND", 0x2E: "ROL",
    0x4D: "EOR", 0x4E: "LSR", 0x6D: "ADC", 0x6E: "ROR", 0x8C: "STY",
    0x8D: "STA", 0x8E: "STX", 0xAC: "LDY", 0xAD: "LDA", 0xAE: "LDX",
    0xCC: "CPY", 0xCD: "CMP", 0xCE: "DEC", 0xEC: "CPX", 0xED: "SBC",
    0xEE: "INC",
}

# Absolute indexed - the named address is a *base*, so a store or load can
# reach past it by however far the index register ranges.
ABS_INDEXED_OPCODES = {
    0x1D: "ORA abs,X", 0x1E: "ASL abs,X", 0x3D: "AND abs,X", 0x3E: "ROL abs,X",
    0x5D: "EOR abs,X", 0x5E: "LSR abs,X", 0x7D: "ADC abs,X", 0x7E: "ROR abs,X",
    0x9D: "STA abs,X", 0xBC: "LDY abs,X", 0xBD: "LDA abs,X", 0xDD: "CMP abs,X",
    0xDE: "DEC abs,X", 0xFD: "SBC abs,X", 0xFE: "INC abs,X",
    0x19: "ORA abs,Y", 0x39: "AND abs,Y", 0x59: "EOR abs,Y", 0x79: "ADC abs,Y",
    0x99: "STA abs,Y", 0xB9: "LDA abs,Y", 0xBE: "LDX abs,Y", 0xD9: "CMP abs,Y",
    0xF9: "SBC abs,Y",
}

ZP_OPCODES = {
    0x05: "ORA", 0x06: "ASL", 0x24: "BIT", 0x25: "AND", 0x26: "ROL",
    0x45: "EOR", 0x46: "LSR", 0x65: "ADC", 0x66: "ROR", 0x84: "STY",
    0x85: "STA", 0x86: "STX", 0xA4: "LDY", 0xA5: "LDA", 0xA6: "LDX",
    0xC4: "CPY", 0xC5: "CMP", 0xC6: "DEC", 0xE4: "CPX", 0xE5: "SBC",
    0xE6: "INC",
}

ZP_INDEXED_OPCODES = {
    0x15: "ORA zp,X", 0x16: "ASL zp,X", 0x35: "AND zp,X", 0x36: "ROL zp,X",
    0x55: "EOR zp,X", 0x56: "LSR zp,X", 0x75: "ADC zp,X", 0x76: "ROR zp,X",
    0x94: "STY zp,X", 0x95: "STA zp,X", 0xB4: "LDY zp,X", 0xB5: "LDA zp,X",
    0xD5: "CMP zp,X", 0xD6: "DEC zp,X", 0xF5: "SBC zp,X", 0xF6: "INC zp,X",
    0x96: "STX zp,Y", 0xB6: "LDX zp,Y",
}


# --- Data ranges --------------------------------------------------------


def is_data_range(label) -> bool:
    """True if a label marks a span of bytes rather than a single address.

    In this project's `.mlb` convention, code labels are single-address
    (`LD_AA09`, `SwingSequenceEntry`) while tables get an explicit range
    (`GolferScreenXTable:$80FA-$8109`), so a range is a reliable "this is
    data, do not decode it" marker.
    """
    return label is not None and label.end is not None and label.end != label.start


def data_range_at(labels, prg_offset: int):
    """The data-range label covering prg_offset, or None."""
    if labels is None:
        return None
    label = labels.lookup("NesPrgRom", prg_offset)
    return label if is_data_range(label) else None


# --- Disassembly --------------------------------------------------------


@dataclass
class Row:
    """One rendered line: an instruction, an inline-argument blob, or data."""

    kind: str  # "code" | "inline" | "data" | "undecoded"
    cpu: int
    prg: int
    raw: bytes
    text: str
    label: str | None = None
    note: str | None = None


@dataclass
class Listing:
    rows: list[Row] = field(default_factory=list)
    stop_reason: str = ""
    complete: bool = True  # False when the cap was hit, i.e. output is truncated


def _bank_window(bank: int) -> tuple[int, int]:
    if bank == FIXED_BANK:
        return FIXED_BANK_PRG_START, FIXED_BANK_PRG_START + PRG_BANK_SIZE
    return bank * PRG_BANK_SIZE, (bank + 1) * PRG_BANK_SIZE


def disassemble(
    reader,
    prg_offset: int,
    *,
    bank_arg: int | None = None,
    count: int | None = None,
    routine: bool = False,
    max_instructions: int = 200,
    labels=None,
    expand_data: bool = True,
    inline_args: bool = True,
) -> Listing:
    """Disassemble from prg_offset.

    `count` decodes a fixed number of rows. `routine=True` instead decodes
    until the routine plausibly ends - an RTS/RTI/JMP with no unresolved
    forward branch past it, a non-returning call, or the start of a labelled
    data range - capped at `max_instructions` so a wrong guess about where
    code lives can't dump the whole bank.
    """
    from py65.devices.mpu6502 import MPU
    from py65.disassembler import Disassembler

    bank, start_cpu = prg_to_bank_and_cpu(prg_offset)
    window_start, window_end = _bank_window(bank)

    span = reader.read_prg(window_start, window_end - window_start)
    mpu = MPU()
    base_cpu = start_cpu - (prg_offset - window_start)
    top = min(base_cpu + len(span), 0x10000)
    mpu.memory[base_cpu:top] = list(span[: top - base_cpu])
    dis = Disassembler(mpu)

    listing = Listing()
    limit = count if count is not None else max_instructions
    pc = start_cpu
    # Highest address a forward branch/jump targets. A terminator only ends
    # the routine once execution has passed every pending target, so an
    # early RTS in the middle of a branchy routine doesn't truncate it.
    max_forward = start_cpu
    emitted = 0

    while emitted < limit:
        cur_prg = window_start + (pc - base_cpu)
        if not (window_start <= cur_prg < window_end):
            listing.stop_reason = "ran past the end of the bank"
            break

        # A labelled data range: emit raw bytes instead of decoding them.
        data_label = data_range_at(labels, cur_prg) if expand_data else None
        if data_label is not None:
            if routine and cur_prg != prg_offset:
                listing.stop_reason = f"start of data range {data_label.name}"
                break
            end_prg = min(data_label.end, window_end - 1)
            emitted += _emit_data(listing, reader, cur_prg, pc, end_prg, data_label, limit - emitted)
            pc += (end_prg - cur_prg) + 1
            if emitted >= limit:
                listing.stop_reason = f"reached the {limit}-row cap"
                listing.complete = routine
            continue

        length, text = dis.instruction_at(pc)
        opcode = span[cur_prg - window_start]
        if length <= 0:
            listing.rows.append(
                Row("undecoded", pc, cur_prg, bytes([opcode]), f".db ${opcode:02X}   ; undecoded")
            )
            pc += 1
            emitted += 1
            continue

        raw = span[cur_prg - window_start : cur_prg - window_start + length]
        listing.rows.append(
            Row("code", pc, cur_prg, bytes(raw), text.upper(), _label_name(labels, cur_prg))
        )
        emitted += 1
        pc += length

        # Track forward control flow so `routine` knows when a terminator
        # really is the end and not just an early return.
        if opcode in BRANCH_OPCODES:
            target = pc + ((raw[1] ^ 0x80) - 0x80)
            max_forward = max(max_forward, target)
        elif opcode == JMP_ABS:
            target = raw[1] | (raw[2] << 8)
            if target > pc:
                max_forward = max(max_forward, target)

        terminator = opcode in (RTS, RTI, JMP_ABS, JMP_IND)

        if opcode == JSR and inline_args:
            target = raw[1] | (raw[2] << 8)
            spec = inline_spec_for(target, bank if bank != FIXED_BANK else None)
            if spec is None and bank != FIXED_BANK:
                spec = inline_spec_for(target, bank)
            if spec is not None:
                arg_prg = window_start + (pc - base_cpu)
                tail = span[arg_prg - window_start : arg_prg - window_start + 64]
                n = spec.measure(tail)
                args = bytes(tail[:n])
                listing.rows.append(
                    Row("inline", pc, arg_prg, args, spec.render(args), note=spec.name)
                )
                pc += n
                emitted += 1
                if not spec.returns:
                    terminator = True

        if routine and terminator and pc > max_forward:
            listing.stop_reason = f"${listing.rows[-1].cpu:04X} ends the routine"
            break
    else:
        if routine:
            listing.stop_reason = (
                f"reached the {limit}-instruction cap without finding an end"
            )
            listing.complete = False
        else:
            listing.stop_reason = f"decoded {limit} rows"

    return listing


def _label_name(labels, prg_offset: int) -> str | None:
    if labels is None:
        return None
    label = labels.lookup("NesPrgRom", prg_offset)
    if label is None or label.start != prg_offset:
        return None
    return label.name


def _emit_data(listing, reader, start_prg, start_cpu, end_prg, label, budget) -> int:
    """Emit a labelled data range as .db rows of 8. Returns rows emitted."""
    rows = 0
    prg = start_prg
    cpu = start_cpu
    first = True
    while prg <= end_prg and rows < budget:
        chunk_len = min(8, end_prg - prg + 1)
        chunk = reader.read_prg(prg, chunk_len)
        text = ".db " + ", ".join(f"${b:02X}" for b in chunk)
        listing.rows.append(
            Row("data", cpu, prg, chunk, text, label.name if first else None,
                note=f"data range {label.name}" if first else None)
        )
        first = False
        prg += chunk_len
        cpu += chunk_len
        rows += 1
    return rows


# --- References ---------------------------------------------------------


@dataclass
class Reference:
    kind: str
    bank: int
    cpu: int
    prg: int
    detail: str = ""
    in_data_range: str | None = None
    # True  = starts on a real instruction boundary
    # False = lands mid-instruction, so the "match" is a byte coincidence
    # None  = no nearby code label to anchor a check from
    aligned: bool | None = None

    @property
    def suspect(self) -> bool:
        """Byte matches that are very unlikely to be real references."""
        return self.in_data_range is not None or self.aligned is False

    @property
    def verified(self) -> bool:
        return self.aligned is True and self.in_data_range is None


@dataclass
class ReferenceReport:
    target_desc: str
    refs: list[Reference] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    pointer_hits: list[Reference] = field(default_factory=list)
    dispatch_sites_checked: int = 0

    @property
    def confirmed(self) -> list[Reference]:
        return [r for r in self.refs if not r.suspect]

    @property
    def unverified(self) -> list[Reference]:
        """Confirmed hits with no nearby label to anchor an alignment check."""
        return [r for r in self.confirmed if r.aligned is None]

    @property
    def empty(self) -> bool:
        return not self.confirmed


def _iter_banks(reader):
    n = reader.prg_size // PRG_BANK_SIZE
    for bank in range(n):
        start = bank * PRG_BANK_SIZE
        yield bank, start, reader.read_prg(start, PRG_BANK_SIZE)


def _annotate(labels, prg: int) -> str | None:
    label = data_range_at(labels, prg)
    return label.name if label is not None else None


def _nearest_code_label_before(labels, prg: int, max_scan: int) -> int | None:
    """Start offset of the closest single-address (code) label at or before prg."""
    if labels is None:
        return None
    best = None
    for label, _ in labels.iter_merged():
        if label.type != "NesPrgRom" or is_data_range(label):
            continue
        if prg - max_scan <= label.start <= prg and (best is None or label.start > best):
            best = label.start
    return best


def check_alignment(reader, prg: int, labels, max_scan: int = 192) -> bool | None:
    """Does an instruction actually start at prg?

    Decodes forward from the nearest preceding code label. Returns None when
    there is no anchor close enough to decide - "unknown", not "fine".
    """
    anchor = _nearest_code_label_before(labels, prg, max_scan)
    if anchor is None:
        return None
    if anchor == prg:
        return True

    from py65.devices.mpu6502 import MPU
    from py65.disassembler import Disassembler

    bank, anchor_cpu = prg_to_bank_and_cpu(anchor)
    span = reader.read_prg(anchor, (prg - anchor) + 8)
    mpu = MPU()
    top = min(anchor_cpu + len(span), 0x10000)
    mpu.memory[anchor_cpu:top] = list(span[: top - anchor_cpu])
    dis = Disassembler(mpu)

    pc = anchor_cpu
    target_cpu = anchor_cpu + (prg - anchor)
    while pc < target_cpu:
        length, _ = dis.instruction_at(pc)
        pc += max(length, 1)
    return pc == target_cpu


def find_code_references(reader, target_cpu: int, target_bank: int, labels=None) -> ReferenceReport:
    """Every static control-flow reference to a code address we can find."""
    lo, hi = target_cpu & 0xFF, target_cpu >> 8
    fixed_target = target_cpu >= 0xC000
    report = ReferenceReport(
        target_desc=f"${target_cpu:04X} "
        + ("(fixed bank)" if fixed_target else f"(bank {target_bank})")
    )

    for bank, base, data in _iter_banks(reader):
        # A JSR/JMP/branch only reaches the target if that bank is the one
        # mapped at $8000 when it runs. Fixed-bank targets are reachable
        # from everywhere.
        same_context = fixed_target or bank == target_bank

        for i in range(len(data) - 2):
            op = data[i]
            if same_context and op in (JSR, JMP_ABS, JMP_IND):
                if data[i + 1] == lo and data[i + 2] == hi:
                    prg = base + i
                    _, cpu = prg_to_bank_and_cpu(prg)
                    kind = {JSR: "JSR", JMP_ABS: "JMP", JMP_IND: "JMP (ind)"}[op]
                    report.refs.append(
                        Reference(kind, bank, cpu, prg, in_data_range=_annotate(labels, prg))
                    )
            if op == JSR and data[i + 1] == 0x72 and data[i + 2] == 0xD3:
                # ExecuteFarCall: bank, lo, hi follow
                if i + 5 < len(data):
                    fb, flo, fhi = data[i + 3], data[i + 4], data[i + 5]
                    if flo == lo and fhi == hi and (fb == target_bank or fixed_target):
                        prg = base + i
                        _, cpu = prg_to_bank_and_cpu(prg)
                        report.refs.append(
                            Reference(
                                "far call", bank, cpu, prg,
                                detail=f"bank ${fb:02X}",
                                in_data_range=_annotate(labels, prg),
                            )
                        )

        if same_context:
            for i in range(len(data) - 1):
                if data[i] in BRANCH_OPCODES:
                    prg = base + i
                    _, cpu = prg_to_bank_and_cpu(prg)
                    target = cpu + 2 + ((data[i + 1] ^ 0x80) - 0x80)
                    if target == target_cpu:
                        report.refs.append(
                            Reference(
                                BRANCH_OPCODES[data[i]], bank, cpu, prg,
                                detail="relative branch",
                                in_data_range=_annotate(labels, prg),
                            )
                        )

    for ref in report.refs:
        if ref.in_data_range is None:
            ref.aligned = check_alignment(reader, ref.prg, labels)

    report.searched = [
        "JSR / JMP / JMP (ind) absolute",
        "relative branches (displacement-encoded, invisible to a byte search)",
        "ExecuteFarCall inline bank+address",
    ]

    sites, dispatch_refs = _search_dispatch_tables(reader, target_cpu, target_bank, fixed_target, labels)
    report.dispatch_sites_checked = sites
    report.refs.extend(dispatch_refs)
    report.searched.append(f"inline jump tables at all {sites} DispatchInlineJumpTable call sites")
    report.searched.append(
        "instruction-boundary check on each hit, anchored at the nearest code label"
    )

    report.not_covered = [
        "indirect jumps through a runtime pointer (JMP ($22) and friends) - "
        "e.g. every menu choice handler is reached this way and has no static reference",
        "pointer tables read by code that computes an address at run time",
        "self-modifying or stack-manufactured addresses",
    ]
    return report


def _search_dispatch_tables(reader, target_cpu, target_bank, fixed_target, labels):
    """Scan the inline tables of every JSR DispatchInlineJumpTable site."""
    lo, hi = target_cpu & 0xFF, target_cpu >> 8
    dlo, dhi = DISPATCH_INLINE_JUMP_TABLE & 0xFF, DISPATCH_INLINE_JUMP_TABLE >> 8
    sites = 0
    refs: list[Reference] = []
    for bank, base, data in _iter_banks(reader):
        for i in range(len(data) - 2):
            if data[i] != JSR or data[i + 1] != dlo or data[i + 2] != dhi:
                continue
            sites += 1
            if not (fixed_target or bank == target_bank):
                continue
            j = i + 3
            while j + 2 < len(data) and data[j] != 0x00:
                if data[j + 1] == lo and data[j + 2] == hi:
                    prg = base + j
                    _, cpu = prg_to_bank_and_cpu(prg)
                    refs.append(
                        Reference(
                            "dispatch table", bank, cpu, prg,
                            detail=f"key ${data[j]:02X}, table after JSR at ${prg_to_bank_and_cpu(base + i)[1]:04X}",
                            in_data_range=_annotate(labels, prg),
                        )
                    )
                j += 3
    return sites, refs


def find_pointer_references(reader, target_cpu: int, labels=None, bank: int | None = None):
    """Raw little-endian byte pairs matching the address. Noisy by nature."""
    lo, hi = target_cpu & 0xFF, target_cpu >> 8
    hits = []
    for b, base, data in _iter_banks(reader):
        if bank is not None and b != bank:
            continue
        for i in range(len(data) - 1):
            if data[i] == lo and data[i + 1] == hi:
                prg = base + i
                _, cpu = prg_to_bank_and_cpu(prg)
                hits.append(
                    Reference("pointer", b, cpu, prg, in_data_range=_annotate(labels, prg))
                )
    return hits


def find_data_references(reader, target_addr: int, labels=None, reach: int = 0):
    """References to a RAM/register address, plus indexed bases that could reach it.

    `reach` widens the search to bases up to that many bytes *below* the
    target, since `LDA $059C,X` can touch $05BB if X gets large enough. The
    scan cannot know how far an index register actually ranges - that has to
    be read out of the code - so these are candidates to go check, not hits.
    """
    direct: list[Reference] = []
    reaching: dict[int, list[Reference]] = {}
    zero_page = target_addr < 0x100

    for bank, base, data in _iter_banks(reader):
        for i in range(len(data) - 2):
            op = data[i]
            if op in ABS_OPCODES or op in ABS_INDEXED_OPCODES:
                addr = data[i + 1] | (data[i + 2] << 8)
                table = ABS_OPCODES if op in ABS_OPCODES else ABS_INDEXED_OPCODES
                if addr == target_addr:
                    prg = base + i
                    _, cpu = prg_to_bank_and_cpu(prg)
                    direct.append(
                        Reference(table[op], bank, cpu, prg, in_data_range=_annotate(labels, prg))
                    )
                elif (
                    reach
                    and op in ABS_INDEXED_OPCODES
                    and target_addr - reach <= addr < target_addr
                ):
                    prg = base + i
                    _, cpu = prg_to_bank_and_cpu(prg)
                    reaching.setdefault(addr, []).append(
                        Reference(ABS_INDEXED_OPCODES[op], bank, cpu, prg)
                    )
            if zero_page and (op in ZP_OPCODES or op in ZP_INDEXED_OPCODES):
                if data[i + 1] == target_addr:
                    table = ZP_OPCODES if op in ZP_OPCODES else ZP_INDEXED_OPCODES
                    prg = base + i
                    _, cpu = prg_to_bank_and_cpu(prg)
                    direct.append(
                        Reference(table[op], bank, cpu, prg, in_data_range=_annotate(labels, prg))
                    )
    return direct, reaching
