#!/usr/bin/env python3
"""
Scorecard QR Table Export

Emits the ROM tables the 6502 QR generator carries — the static matrix, the
GF(256) log/antilog pair, the Reed-Solomon generator polynomial, the 16 CHR
tiles, the base64url alphabet and the constant code word head — as a flat
blob, one binary per table, an assembler include and a JSON manifest.

Everything is derived from `golf/qr/`, the reference implementation, so the
exported bytes cannot drift from the oracle the 6502 port is tested against.
"""

import argparse
import hashlib
import sys
from pathlib import Path

from golf.qr import tables
from golf.qr.payload import URL_LEN, URL_PREFIX
from golf.qr.submission import FIXED_MASK


def _parse_address(text: str) -> int:
    """Accept `$8400`, `0x8400` or `33792`."""
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
        "out_dir",
        type=Path,
        nargs="?",
        help="directory to write the tables into (omit to only print the summary)",
    )
    parser.add_argument(
        "--mask",
        type=int,
        default=FIXED_MASK,
        help=f"QR mask baked into the static matrix (default: {FIXED_MASK})",
    )
    parser.add_argument(
        "--origin",
        type=_parse_address,
        help="CPU address the blob is loaded at, e.g. $8400; adds per-table addresses",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="write only the combined blob, not one binary per table",
    )
    parser.add_argument(
        "--asm", action="store_true", help="print the assembler include to stdout"
    )
    args = parser.parse_args()

    if not 0 <= args.mask <= 7:
        print(f"mask must be 0-7, got {args.mask}", file=sys.stderr)
        return 1

    built = tables.build_tables(args.mask)
    blob = tables.blob(built)

    print(f"mask        {args.mask}")
    print(f"url prefix  {URL_PREFIX} ({URL_LEN} chars)")
    if args.origin is not None:
        print(f"origin      ${args.origin:04X}")
    print()

    header = f"{'table':<16} {'size':>6} {'offset':>7}"
    if args.origin is not None:
        header += f" {'addr':>6} {'page':>5}"
    print(header)
    print("-" * len(header))
    for placement in tables.layout(built, args.origin):
        line = (
            f"{placement.table.label:<16} {placement.table.size:>6} "
            f"${placement.offset:04X}  "
        )
        if placement.address_hex is not None:
            aligned = "yes" if placement.page_aligned else "-"
            line += f" {placement.address_hex:>6} {aligned:>5}"
        print(line)
    print("-" * len(header))
    print(f"{'total':<16} {len(blob):>6}")
    print()
    print(f"sha256      {hashlib.sha256(blob).hexdigest()}")
    print(
        f"budget      {len(blob)} of {tables.REGION_BYTES} bytes in bank 2, "
        f"{tables.REGION_BYTES - len(blob)} left for code"
    )

    if args.asm:
        print()
        print(tables.to_asm(built, args.mask, args.origin), end="")

    if args.out_dir is None:
        print()
        print("no output directory given, nothing written")
        return 0

    written = tables.write_tables(
        args.out_dir, built, args.mask, args.origin, split=not args.no_split
    )
    print()
    for path in written:
        print(f"wrote       {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
