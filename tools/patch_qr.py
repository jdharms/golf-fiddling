#!/usr/bin/env python3
"""
NES Open Tournament Golf - Scorecard QR Patch Tool

Installs the end-of-round QR submission screen (docs/scorecard_qr.md): the
tables and routine go into bank 2's reclaimed region, and the wait that follows
the post-round scorecard is repointed through a trampoline in bank 13 padding.

Each build gets its own seed ID, one player ID per slot, and one MAC key per
slot. The keys are secret — they are what stops a player submitting a scorecard
as somebody else — so `--manifest` writes them out for the server and nothing
else prints them in full.

The region this writes into is the vacated UK course. Apply it to a randomizer
ROM, where course mirroring and menu trimming have already made course 3
unreachable; on a vanilla ROM the other two courses still play normally, but the
UK course's terrain is gone.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from golf.core.patches import PatchError, QrCredentials, ScorecardQrPatch
from golf.core.rom_writer import RomWriter
from golf.qr import payload
from golf.qr.port import layout


def _hex_bytes(text: str, length: int, label: str) -> bytes:
    try:
        data = bytes.fromhex(text.replace("-", "").replace(" ", ""))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{label} must be hex") from None
    if len(data) != length:
        raise argparse.ArgumentTypeError(
            f"{label} must be {length} bytes ({length * 2} hex digits)"
        )
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom_file", help="Source ROM file")
    parser.add_argument("-o", "--output", help="Output ROM (default: <rom>.qr.nes)")
    parser.add_argument(
        "--seed-id",
        help=f"{payload.SEED_ID_LEN}-byte seed ID as hex (default: random)",
    )
    parser.add_argument(
        "--player-id",
        action="append",
        default=[],
        metavar="HEX",
        help=f"{payload.PLAYER_ID_LEN}-byte player ID, once per slot (default: random)",
    )
    parser.add_argument(
        "--key",
        action="append",
        default=[],
        metavar="HEX",
        help=f"{payload.KEY_LEN}-byte MAC key, once per slot (default: random)",
    )
    parser.add_argument(
        "--rng-seed",
        type=int,
        help="seed the credential RNG, for a reproducible build",
    )
    parser.add_argument(
        "--manifest", type=Path, help="write the seed, player IDs and keys here as JSON"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="report whether the patch can apply, without writing a ROM",
    )
    args = parser.parse_args()

    rng = random.Random(args.rng_seed) if args.rng_seed is not None else None
    credentials = QrCredentials.random(rng)
    if args.seed_id:
        credentials = QrCredentials(
            seed_id=_hex_bytes(args.seed_id, payload.SEED_ID_LEN, "--seed-id"),
            player_ids=credentials.player_ids,
            keys=credentials.keys,
        )
    for slot, value in enumerate(args.player_id[:2]):
        ids = list(credentials.player_ids)
        ids[slot] = _hex_bytes(value, payload.PLAYER_ID_LEN, "--player-id")
        credentials = QrCredentials(
            seed_id=credentials.seed_id,
            player_ids=(ids[0], ids[1]),
            keys=credentials.keys,
        )
    for slot, value in enumerate(args.key[:2]):
        keys = list(credentials.keys)
        keys[slot] = _hex_bytes(value, payload.KEY_LEN, "--key")
        credentials = QrCredentials(
            seed_id=credentials.seed_id,
            player_ids=credentials.player_ids,
            keys=(keys[0], keys[1]),
        )

    try:
        patch = ScorecardQrPatch(credentials)
    except PatchError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    output = args.output or str(Path(args.rom_file).with_suffix("")) + ".qr.nes"
    writer = RomWriter(args.rom_file, output)

    print(f"{patch.name}: {patch.description}")
    print(
        f"  image       {len(patch.image)} bytes at bank 2 "
        f"${layout.TABLE_ORIGIN:04X} (prg 0x{patch.image_offset:05X})"
    )
    print(
        f"  entry       ${patch.entry:04X} QrShowCodes, far-called from the "
        f"bank 13 trampoline at ${0xBF83:04X}"
    )
    print(f"  hook        bank 13 $852D, JSR operand -> ${0xBF83:04X}")
    print(f"  seed ID     {credentials.seed_id.hex()}")
    for slot, player_id in enumerate(credentials.player_ids):
        print(f"  player {slot + 1}    {player_id.hex()}  (key withheld)")

    if patch.is_applied(writer):
        state = "already applied (will be rewritten with these credentials)"
    elif patch.can_apply(writer):
        state = "pending"
    else:
        state = "CONFLICT: the hook site is not vanilla"
    print(f"  status      {state}")

    if args.validate_only:
        return 0 if "CONFLICT" not in state else 1

    try:
        patch.apply(writer)
    except PatchError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    writer.save()

    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(credentials.manifest(), indent=2) + "\n")
        print(f"  manifest    {args.manifest} (contains the secret MAC keys)")
    else:
        print("  note        no --manifest given, so the MAC keys are not recoverable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
