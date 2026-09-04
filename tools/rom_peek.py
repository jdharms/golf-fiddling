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

The `disasm` subcommand needs py65 (`uv pip install py65`) for opcode decoding -
it's not a hard dependency of the rest of the project, just this one subcommand.
"""

import argparse
import sys

from golf.core.rom_reader import RomReader
from golf.core.rom_utils import (
    FIXED_BANK_PRG_START,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
    prg_to_bank_and_cpu,
)


def parse_address(address: str, bank: int | None) -> int:
    """Parse a "$XXXX" CPU address or raw hex PRG offset into a PRG offset."""
    address = address.strip()
    if address.startswith("$"):
        cpu_addr = int(address[1:], 16)
        if bank is not None:
            return cpu_to_prg_switched(cpu_addr, bank)
        return cpu_to_prg_fixed(cpu_addr)
    return int(address, 16)


def format_bytes(data: bytes, fmt: str) -> str:
    if fmt == "python":
        return "bytes([" + ", ".join(f"0x{b:02X}" for b in data) + "])"
    if fmt == "ascii":
        return "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return data.hex(" ").upper()


def cmd_read(reader: RomReader, args) -> None:
    prg_offset = parse_address(args.address, args.bank)
    data = reader.read_prg(prg_offset, args.length)
    print(format_bytes(data, args.format))


def cmd_addr(_reader: RomReader, args) -> None:
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


def _bank_region(bank: int) -> tuple[int, int]:
    if bank == 15:
        return FIXED_BANK_PRG_START, FIXED_BANK_PRG_START + PRG_BANK_SIZE
    return bank * PRG_BANK_SIZE, (bank + 1) * PRG_BANK_SIZE


def cmd_find(reader: RomReader, args) -> None:
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

        print(line)
        search_from = idx + 1

    if hits == 0:
        print("No matches found.")


def cmd_disasm(reader: RomReader, args) -> None:
    try:
        from py65.devices.mpu6502 import MPU
        from py65.disassembler import Disassembler
    except ImportError:
        print(
            "Error: py65 is required for disasm (uv pip install py65)",
            file=sys.stderr,
        )
        sys.exit(1)

    prg_offset = parse_address(args.address, args.bank)
    bank, cpu_addr = prg_to_bank_and_cpu(prg_offset)

    # Max instruction length is 3 bytes; overshoot the read so the last
    # decoded instruction never runs off the end of the buffer.
    data = reader.read_prg(prg_offset, args.count * 3)

    mpu = MPU()
    region_end = min(cpu_addr + len(data), 0x10000)
    mpu.memory[cpu_addr:region_end] = list(data[: region_end - cpu_addr])
    dis = Disassembler(mpu)

    pc = cpu_addr
    for _ in range(args.count):
        offset = pc - cpu_addr
        if offset >= len(data):
            break
        length, text = dis.instruction_at(pc)
        if length <= 0:
            print(f"${pc:04X}  {data[offset]:02X}        .byte ${data[offset]:02X}  (undecoded)")
            pc += 1
            continue
        raw = data[offset : offset + length]
        print(f"${pc:04X}  {raw.hex(' ').upper():<8}  {text.upper()}")
        pc += length


def main():
    parser = argparse.ArgumentParser(
        description="Targeted reads/searches of ROM bytes for RE work"
    )
    parser.add_argument("rom_file", help="ROM file to read")
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
        "disasm", help="Disassemble instructions starting at an address (needs py65)"
    )
    disasm_parser.add_argument("address", help="'$XXXX' CPU address or raw hex PRG offset")
    disasm_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14)")
    disasm_parser.add_argument(
        "--count", type=int, default=10, help="Number of instructions to decode (default: 10)"
    )

    args = parser.parse_args()
    reader = RomReader(args.rom_file)

    commands = {"read": cmd_read, "find": cmd_find, "addr": cmd_addr, "disasm": cmd_disasm}
    try:
        commands[args.command](reader, args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
