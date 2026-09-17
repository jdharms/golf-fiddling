#!/usr/bin/env python3
"""
NES Open Tournament Golf - Scorecard QR Credentials

Writes the credentials the qr_credentials patch needs - a seed ID, and one player
ID and MAC key per player slot - to a JSON file that a recipe names:

    golf-qr-credentials -o keys.json
    golf-patch rom.nes -p scorecard_qr -p qr_credentials:credentials=keys.json ...

The keys are secret: they are what stops a player submitting a scorecard as
somebody else, and the server needs them to verify submissions. Keep the file
out of anything you share. IDs and keys are random unless given.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from golf.core.patches import QrCredentials
from golf.qr import payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write scorecard QR credentials (secret MAC keys) to a JSON file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="credentials file to write")
    parser.add_argument("--seed-id", help=f"{payload.SEED_ID_LEN}-byte seed ID as hex (default: random)")
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
    parser.add_argument("--rng-seed", type=int, help="seed the RNG, for reproducible credentials")
    args = parser.parse_args()

    def hex_bytes(text: str, length: int, label: str) -> bytes:
        try:
            data = bytes.fromhex(text.replace("-", "").replace(" ", ""))
        except ValueError:
            parser.error(f"{label} must be hex")
        if len(data) != length:
            parser.error(f"{label} must be {length} bytes ({length * 2} hex digits)")
        return data

    rng = random.Random(args.rng_seed) if args.rng_seed is not None else None
    drawn = QrCredentials.random(rng)
    player_ids = list(drawn.player_ids)
    keys = list(drawn.keys)
    for slot, value in enumerate(args.player_id[:2]):
        player_ids[slot] = hex_bytes(value, payload.PLAYER_ID_LEN, "--player-id")
    for slot, value in enumerate(args.key[:2]):
        keys[slot] = hex_bytes(value, payload.KEY_LEN, "--key")
    credentials = QrCredentials(
        seed_id=hex_bytes(args.seed_id, payload.SEED_ID_LEN, "--seed-id") if args.seed_id else drawn.seed_id,
        player_ids=(player_ids[0], player_ids[1]),
        keys=(keys[0], keys[1]),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(credentials.manifest(), indent=2) + "\n")
    print(f"seed ID     {credentials.seed_id.hex()}")
    for slot, player_id in enumerate(credentials.player_ids):
        print(f"player {slot + 1}    {player_id.hex()}  (key withheld)")
    print(f"wrote {args.output} (contains the secret MAC keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
