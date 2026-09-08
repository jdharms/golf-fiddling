#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Peek Tool

Targeted, scriptable reads of ROM bytes for reverse-engineering work, so
disassembly/patch investigations don't require hand-written one-off Python
each time. Wraps RomReader and golf.core.rom_utils address translation.

Address argument grammar (shared by all subcommands):
  - "$XXXX"  CPU address. Uses the fixed bank ($C000-$FFFF) unless --bank
             is given, in which case it's resolved as a switchable-bank
             address ($8000-$BFFF) in that bank.
  - "0xNNNN" or bare hex digits: a raw PRG ROM offset, used as-is. This
             matches the PRG-offset-style labels (e.g. "3E46D") already
             used in disassembly notes for this project.

Examples:
    golf-rom-peek rom.nes read '$E4F9' --length 10
    golf-rom-peek rom.nes read '$AF14' --bank 2 --length 6
    golf-rom-peek rom.nes read 0x3CA40 --length 192 --format python
    golf-rom-peek rom.nes find '20 84 CE' --follow 2
    golf-rom-peek rom.nes find '20 84 CE' --follow 2 --flag-range '$E4F9-$E516'
    golf-rom-peek rom.nes addr '$E4F9' --bank 2
    golf-rom-peek rom.nes disasm '$AD43' --bank 2 --count 15

    # Annotate output with symbol names from a Mesen .mlb label file.
    # --labels/--sidecar must come before the subcommand (top-level options).
    # Any "notes.sidecar.mlb" next to notes.mlb is loaded automatically and
    # shadows notes.mlb at matching addresses - see golf-labels for adding to it.
    golf-rom-peek rom.nes --labels notes.mlb disasm '$AD43' --bank 2 --count 15
    golf-rom-peek rom.nes --labels notes.mlb label '$AD5D'
    golf-rom-peek rom.nes --labels notes.mlb label '001A' --type ram
    golf-rom-peek rom.nes --labels notes.mlb find-label ScrollX

The `disasm` subcommand decodes opcodes with py65, a project dependency - it is
installed by `uv sync` along with everything else, so `disasm` always works.
"""

import argparse
import re
import sys

from golf.core.mlb_labels import TYPE_ALIASES, Label, LabelStore, describe
from golf.core.rom_analysis import (
    FIXED_BANK,
    disassemble,
    find_code_references,
    find_data_references,
    find_pointer_references,
)
from golf.core.rom_reader import RomReader
from golf.core.rom_utils import (
    FIXED_BANK_PRG_START,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
    parse_cpu_or_prg_address as parse_address,
    prg_to_bank_and_cpu,
)


def format_bytes(data: bytes, fmt: str) -> str:
    if fmt == "python":
        return "bytes([" + ", ".join(f"0x{b:02X}" for b in data) + "])"
    if fmt == "ascii":
        return "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return data.hex(" ").upper()


def cmd_read(reader: RomReader, args, labels: LabelStore | None) -> None:
    prg_offset = parse_address(args.address, args.bank)
    data = reader.read_prg(prg_offset, args.length)
    print(format_bytes(data, args.format))
    if labels is not None:
        label = labels.lookup("NesPrgRom", prg_offset)
        if label is not None:
            print(f"label: {describe(label, prg_offset)}")


def cmd_addr(_reader: RomReader, args, labels: LabelStore | None) -> None:
    if args.address.startswith("$"):
        cpu_addr = int(args.address[1:], 16)
        if args.bank is not None:
            prg_offset = cpu_to_prg_switched(cpu_addr, args.bank)
            bank = args.bank
        else:
            prg_offset = cpu_to_prg_fixed(cpu_addr)
            bank = 15
    else:
        prg_offset = int(args.address, 16)
        bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)
    print(f"bank={bank} cpu=${cpu_addr:04X} prg=0x{prg_offset:X}")
    if labels is not None:
        label = labels.lookup("NesPrgRom", prg_offset)
        if label is not None:
            print(f"label: {describe(label, prg_offset)}")


def _bank_region(bank: int) -> tuple[int, int]:
    if bank == 15:
        return FIXED_BANK_PRG_START, FIXED_BANK_PRG_START + PRG_BANK_SIZE
    return bank * PRG_BANK_SIZE, (bank + 1) * PRG_BANK_SIZE


def cmd_find(reader: RomReader, args, labels: LabelStore | None) -> None:
    pattern = bytes.fromhex(args.pattern.replace(" ", ""))

    flag_low = flag_high = None
    if args.flag_range:
        lo_str, hi_str = args.flag_range.split("-")
        flag_low = int(lo_str.strip().lstrip("$"), 16)
        flag_high = int(hi_str.strip().lstrip("$"), 16)

    if args.bank is not None:
        region_start, region_end = _bank_region(args.bank)
    else:
        region_start, region_end = 0, reader.prg_size

    full = reader.read_prg(region_start, region_end - region_start)

    hits = 0
    search_from = 0
    while True:
        idx = full.find(pattern, search_from)
        if idx == -1:
            break
        hits += 1
        prg_offset = region_start + idx
        bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)
        line = f"bank={bank:2} cpu=${cpu_addr:04X} prg=0x{prg_offset:X}"

        if args.follow:
            follow_start = idx + len(pattern)
            follow_bytes = full[follow_start : follow_start + args.follow]
            if args.follow == 2:
                ptr = follow_bytes[0] | (follow_bytes[1] << 8)
                line += f"  follow=${ptr:04X}"
                if flag_low is not None and flag_low <= ptr <= flag_high:
                    line += "  <-- in flagged range"
            else:
                line += f"  follow={follow_bytes.hex(' ').upper()}"

        if labels is not None:
            label = labels.lookup("NesPrgRom", prg_offset)
            if label is not None:
                line += f"  label={describe(label, prg_offset)}"

        print(line)
        search_from = idx + 1

    if hits == 0:
        print("No matches found.")


_OPERAND_RE = re.compile(r"(?<!#)\$([0-9A-Fa-f]{2,4})\b")


def _operand_label(addr: int, bank: int | None, labels: LabelStore) -> Label | None:
    """Best-effort resolution of a disassembly operand address to a label.

    Zero-page/absolute RAM and PPU/APU register addresses map straight to
    CPU space. $8000-$FFFF operands are resolved against the bank the
    instructions were disassembled in (disasm doesn't track bank switches
    mid-listing, so this assumes the whole run stays in one bank).
    """
    if addr < 0x2000:
        return labels.lookup("NesInternalRam", addr & 0x07FF)
    if 0x2000 <= addr < 0x4020:
        mapped = 0x2000 + ((addr - 0x2000) % 8) if addr < 0x4000 else addr
        return labels.lookup("NesMemory", mapped)
    if 0x6000 <= addr < 0x8000:
        return labels.lookup("NesSaveRam", addr - 0x6000)
    if 0x8000 <= addr <= 0xBFFF and bank is not None:
        return labels.lookup("NesPrgRom", cpu_to_prg_switched(addr, bank))
    if 0xC000 <= addr <= 0xFFFF:
        return labels.lookup("NesPrgRom", cpu_to_prg_fixed(addr))
    return None


def _symbolicate(text: str, bank: int | None, labels: LabelStore) -> str:
    def repl(m: re.Match) -> str:
        addr = int(m.group(1), 16)
        label = _operand_label(addr, bank, labels)
        if label is None:
            return m.group(0)
        return f"{label.name}[{m.group(0)}]"

    return _OPERAND_RE.sub(repl, text)


def cmd_disasm(reader: RomReader, args, labels: LabelStore | None) -> None:
    prg_offset = parse_address(args.address, args.bank)
    listing = disassemble(
        reader,
        prg_offset,
        count=None if args.routine else args.count,
        routine=args.routine,
        max_instructions=args.max,
        labels=labels,
        expand_data=not args.no_data_ranges,
        inline_args=not args.no_inline_args,
    )

    for row in listing.rows:
        if row.label:
            label = labels.lookup("NesPrgRom", row.prg) if labels else None
            print(f"{describe(label, row.prg) if label else row.label}:")
        text = row.text
        if row.kind == "code" and labels is not None:
            text = _symbolicate(text, args.bank, labels)
        elif row.kind == "inline" and row.note:
            text = f"{text}".ljust(44) + f"; inline args for {row.note}"
        raw = row.raw.hex(" ").upper()
        if len(raw) > 8:
            raw = raw[:8] + ".."
        print(f"${row.cpu:04X}  {raw:<10}  {text}")

    if args.routine or not listing.complete:
        print()
        marker = "" if listing.complete else "INCOMPLETE - "
        print(f"[{marker}stopped: {listing.stop_reason}]")
        if not listing.complete:
            print(
                "[the routine may continue past this point; re-run with a larger "
                "--max or an explicit --count]"
            )


def _print_refs(refs, indent="  ") -> None:
    for r in refs:
        line = f"{indent}{r.kind:<15} bank {r.bank:2}  ${r.cpu:04X}  prg 0x{r.prg:05X}"
        if r.detail:
            line += f"  {r.detail}"
        if r.in_data_range:
            line += f"   <-- inside data range {r.in_data_range}, probably a coincidence"
        elif r.aligned is False:
            line += "   <-- lands mid-instruction, byte coincidence"
        elif r.aligned is None:
            line += "   [UNVERIFIED: no nearby code label to check alignment against]"
        print(line)


def cmd_find_refs(reader: RomReader, args, labels: LabelStore | None) -> None:
    if args.type != "prg":
        addr = int(args.address.lstrip("$"), 16)
        direct, reaching = find_data_references(reader, addr, labels, args.reach)
        print(f"${addr:04X} ({args.type})")
        if direct:
            print(f"\n  direct references ({len(direct)}):")
            _print_refs(direct, "    ")
        else:
            print("\n  direct references: NONE FOUND")
        if args.reach:
            if reaching:
                print(
                    f"\n  indexed bases within {args.reach} bytes below, which could reach "
                    "this address if the index register ranges far enough:"
                )
                for base in sorted(reaching):
                    print(f"    ${base:04X},X/Y  ({len(reaching[base])} sites)")
                    _print_refs(reaching[base], "      ")
                print(
                    "\n  [how far X/Y actually range is NOT determined here - read each "
                    "site before concluding this address is safe]"
                )
            else:
                print(f"\n  no indexed bases within {args.reach} bytes below")
        if not direct:
            _print_null_warning(reader, addr, labels, args, code=False)
        return

    prg_offset = parse_address(args.address, args.bank)
    bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)
    report = find_code_references(reader, cpu_addr, bank, labels)

    print(f"{report.target_desc}  prg 0x{prg_offset:05X}")
    if labels is not None:
        label = labels.lookup("NesPrgRom", prg_offset)
        if label is not None:
            print(f"  {describe(label, prg_offset)}")

    confirmed = report.confirmed
    suspect = [r for r in report.refs if r.suspect]
    if confirmed:
        unverified = len(report.unverified)
        suffix = f", {unverified} unverified" if unverified else ""
        print(f"\n  references ({len(confirmed)}{suffix}):")
        _print_refs(confirmed)
    else:
        print("\n  references: NONE FOUND")
    if suspect:
        print(f"\n  discarded as coincidence ({len(suspect)}) - byte matches inside data ranges:")
        _print_refs(suspect)

    print("\n  searched:")
    for item in report.searched:
        print(f"    - {item}")

    if report.empty:
        _print_null_warning(reader, cpu_addr, labels, args, code=True, report=report)


def _print_null_warning(reader, addr, labels, args, code: bool, report=None) -> None:
    print("\n  NOT COVERED by this search - a null result is NOT evidence that this")
    print("  address is unused:")
    items = report.not_covered if report is not None else [
        "any access that computes the address at run time",
        "DMA, the decompressor, and anything the PPU reads directly",
    ]
    for item in items:
        print(f"    - {item}")

    hits = find_pointer_references(reader, addr, labels)
    print(f"\n  escalating: {len(hits)} raw byte-pair(s) matching ${addr:04X} in the ROM.")
    print("  For a pointer search the usual reading is inverted - a hit inside a labelled")
    print("  table is a LIKELY indirect reference, not a coincidence:")
    for hit in hits[:25]:
        where = (
            f"in {hit.in_data_range}  <-- likely a real pointer-table entry"
            if hit.in_data_range
            else "not in any labelled range"
        )
        print(f"    bank {hit.bank:2}  ${hit.cpu:04X}  prg 0x{hit.prg:05X}  {where}")
    if len(hits) > 25:
        print(f"    ... and {len(hits) - 25} more")
    print("\n  [confirm with a Mesen breakpoint before treating this address as dead,")
    print("   then record the result in the .mlb comment or a doc so it isn't re-derived]")


def cmd_label(_reader: RomReader, args, labels: LabelStore | None) -> None:
    if labels is None:
        print("Error: --labels PATH is required for this command", file=sys.stderr)
        sys.exit(1)
    type_ = TYPE_ALIASES[args.type]
    if type_ == "NesPrgRom":
        addr = parse_address(args.address, args.bank)
    else:
        addr = int(args.address.lstrip("$"), 16)
    label = labels.lookup(type_, addr)
    if label is None:
        print("No label found.")
        return
    print(describe(label, addr))


def cmd_find_label(_reader: RomReader, args, labels: LabelStore | None) -> None:
    if labels is None:
        print("Error: --labels PATH is required for this command", file=sys.stderr)
        sys.exit(1)
    matches = labels.search_name(args.name)
    if not matches:
        print("No matches found.")
        return
    for label in matches:
        print(f"{label.type} {label.address_str}: {describe(label, label.start)}")


def main():
    parser = argparse.ArgumentParser(
        description="Targeted reads/searches of ROM bytes for RE work"
    )
    parser.add_argument("rom_file", help="ROM file to read")
    parser.add_argument(
        "--labels",
        help="Path to a Mesen .mlb label file to annotate output with symbol names "
        "(must appear before the subcommand)",
    )
    parser.add_argument(
        "--sidecar",
        help="Path to a sidecar .mlb overlay (defaults to '<labels>.sidecar.mlb' next to "
        "--labels, if it exists); entries here shadow --labels at the same address",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="Read bytes at an address")
    read_parser.add_argument("address", help="'$XXXX' CPU address or raw hex PRG offset")
    read_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14)")
    read_parser.add_argument("--length", type=int, default=1, help="Number of bytes to read")
    read_parser.add_argument(
        "--format",
        choices=["hex", "python", "ascii"],
        default="hex",
        help="Output format (default: hex)",
    )

    find_parser = subparsers.add_parser(
        "find", help="Search for a byte pattern across the ROM"
    )
    find_parser.add_argument("pattern", help="Hex byte pattern, e.g. '20 84 CE'")
    find_parser.add_argument(
        "--bank", type=int, help="Restrict search to one bank (0-14, or 15 for fixed)"
    )
    find_parser.add_argument(
        "--follow",
        type=int,
        help="Also show N bytes following each match (2 decodes as a little-endian pointer)",
    )
    find_parser.add_argument(
        "--flag-range",
        help="Flag matches whose --follow 2 pointer falls in 'LOW-HIGH', e.g. '$E4F9-$E516'",
    )

    addr_parser = subparsers.add_parser(
        "addr", help="Convert between CPU address and PRG offset (no ROM read)"
    )
    addr_parser.add_argument("address", help="'$XXXX' CPU address or raw hex PRG offset")
    addr_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14)")

    disasm_parser = subparsers.add_parser(
        "disasm", help="Disassemble instructions starting at an address"
    )
    disasm_parser.add_argument("address", help="'$XXXX' CPU address or raw hex PRG offset")
    disasm_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14)")
    disasm_parser.add_argument(
        "--count", type=int, default=10, help="Number of instructions to decode (default: 10)"
    )
    disasm_parser.add_argument(
        "--routine",
        action="store_true",
        help="Decode until the routine ends (terminator with no pending forward branch, "
        "or the start of a labelled data range) instead of a fixed --count",
    )
    disasm_parser.add_argument(
        "--max",
        type=int,
        default=200,
        help="Safety cap on rows for --routine (default: 200); output says so if hit",
    )
    disasm_parser.add_argument(
        "--no-inline-args",
        action="store_true",
        help="Decode inline arguments as instructions (the vanilla, desynchronising behaviour)",
    )
    disasm_parser.add_argument(
        "--no-data-ranges",
        action="store_true",
        help="Decode labelled data ranges as instructions instead of .db rows",
    )

    refs_parser = subparsers.add_parser(
        "find-refs",
        help="Find references to an address across every encoding (JSR/JMP/branch/far call/dispatch)",
    )
    refs_parser.add_argument("address", help="'$XXXX' CPU address or raw hex PRG offset")
    refs_parser.add_argument("--bank", type=int, help="Bank the target lives in, for type=prg")
    refs_parser.add_argument(
        "--type",
        choices=list(TYPE_ALIASES),
        default="prg",
        help="What kind of address the target is (default: prg)",
    )
    refs_parser.add_argument(
        "--reach",
        type=int,
        default=0,
        help="For RAM: also list indexed bases up to N bytes below that could reach it",
    )

    label_parser = subparsers.add_parser(
        "label", help="Look up the label at an address (requires --labels)"
    )
    label_parser.add_argument("address", help="'$XXXX' CPU address or raw hex address/offset")
    label_parser.add_argument(
        "--type",
        choices=list(TYPE_ALIASES),
        default="prg",
        help="Label type to search (default: prg)",
    )
    label_parser.add_argument(
        "--bank", type=int, help="Switchable bank number (0-14), used when --type prg"
    )

    find_label_parser = subparsers.add_parser(
        "find-label", help="Search labels by name substring (requires --labels)"
    )
    find_label_parser.add_argument("name", help="Substring to search for (case-insensitive)")

    args = parser.parse_args()
    reader = RomReader(args.rom_file)
    labels = LabelStore.load(args.labels, args.sidecar) if args.labels else None

    commands = {
        "read": cmd_read,
        "find": cmd_find,
        "addr": cmd_addr,
        "disasm": cmd_disasm,
        "label": cmd_label,
        "find-label": cmd_find_label,
        "find-refs": cmd_find_refs,
    }
    try:
        commands[args.command](reader, args, labels)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
