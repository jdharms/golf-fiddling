#!/usr/bin/env python3
"""
Scorecard QR 6502 Port

Assembles `golf/qr/port/` and reports what it costs: the size of each routine,
the table blob it sits behind, and how much of bank 2's reclaimed region the
whole feature uses. Optionally writes the image that gets spliced into the ROM,
or the assembly source it was built from.
"""

import argparse
import sys
from pathlib import Path

from golf.qr import port
from golf.qr.port import layout


def _parse_address(text: str) -> int:
    cleaned = text.strip()
    try:
        if cleaned.startswith("$"):
            return int(cleaned[1:], 16)
        if cleaned.lower().startswith("0x"):
            return int(cleaned, 16)
        return int(cleaned, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an address: {text}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write the tables-plus-code image to this file",
    )
    parser.add_argument(
        "--origin",
        type=_parse_address,
        help=f"assemble the code at this address (default: ${layout.CODE_ORIGIN:04X})",
    )
    parser.add_argument(
        "--asm", action="store_true", help="print the assembled source instead"
    )
    parser.add_argument(
        "--symbols", action="store_true", help="list every symbol, not just routines"
    )
    args = parser.parse_args()

    if args.asm:
        print(port.full_source(), end="")
        return 0

    program = port.build(origin=args.origin)
    blob = port.table_blob()
    image = program.end - layout.TABLE_ORIGIN
    region = layout.REGION_END - layout.REGION_START + 1

    print(f"tables      ${layout.TABLE_ORIGIN:04X}  {len(blob):5d} bytes")
    print(f"code        ${program.origin:04X}  {program.size:5d} bytes")
    print(f"image             {image:5d} bytes")
    print(
        f"region      ${layout.REGION_START:04X}-${layout.REGION_END:04X}  "
        f"{region} bytes, {region - image} spare"
    )
    print()

    inside = sorted(
        (address, name)
        for name, address in program.symbols.items()
        if program.origin <= address < program.end and (args.symbols or "@" not in name)
    )
    print(f"{'routine':<24} {'addr':>6} {'size':>6}")
    print("-" * 38)
    for index, (address, name) in enumerate(inside):
        end = inside[index + 1][0] if index + 1 < len(inside) else program.end
        print(f"{name:<24} ${address:04X} {end - address:6d}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(port.rom_bytes())
        print()
        print(f"wrote       {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
