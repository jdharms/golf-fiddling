#!/usr/bin/env python3
"""
Scorecard QR Preview

Builds a submission payload, encodes it as the ROM will, and writes a PNG of
the resulting NES screen. Everything renders through the CHR + nametable, so
the image is what the PPU would actually put out rather than an idealised QR.
"""

import argparse
import random
import sys
from pathlib import Path

from golf.qr import encoder, nes, render, sample
from golf.qr.decode import DECODERS
from golf.qr.payload import RoundPayload


def _parse_scores(text: str) -> tuple[tuple[int, int], ...]:
    """Parse `strokes/putts,strokes/putts,...` for 18 holes."""
    holes = []
    for part in text.split(","):
        strokes, _, putts = part.strip().partition("/")
        holes.append((int(strokes), int(putts or 0)))
    if len(holes) != 18:
        raise argparse.ArgumentTypeError(f"expected 18 holes, got {len(holes)}")
    return tuple(holes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("qr_preview.png"),
        help="output PNG (default: qr_preview.png)",
    )
    parser.add_argument("--mask", type=int, default=0, help="QR mask 0-7 (default: 0)")
    parser.add_argument(
        "--seed", type=int, default=0, help="RNG seed for a random round"
    )
    parser.add_argument(
        "--scores",
        type=_parse_scores,
        help="explicit scores, e.g. '4/2,3/1,...' for 18 holes",
    )
    parser.add_argument(
        "--url", help="encode this URL verbatim instead of building a payload"
    )
    parser.add_argument(
        "--scale", type=int, default=3, help="integer pixel scale (default: 3)"
    )
    parser.add_argument(
        "--crop",
        action="store_true",
        help="render only the code plus its quiet zone instead of the whole screen",
    )
    parser.add_argument(
        "--ascii", action="store_true", help="also print the code as text"
    )
    args = parser.parse_args()

    if args.url:
        url = args.url
        payload = None
    else:
        rng = random.Random(args.seed)
        key = sample.random_key(rng)
        if args.scores:
            from golf.qr.payload import HoleRecord

            payload = RoundPayload(
                seed_id=bytes(rng.randrange(256) for _ in range(8)),
                player_id=bytes(rng.randrange(256) for _ in range(4)),
                holes=tuple(HoleRecord(s, p) for s, p in args.scores),
            )
        else:
            payload = sample.random_round(rng)
        url = payload.to_url(key)

    if len(url) > encoder.MAX_CHARS:
        print(
            f"URL is {len(url)} chars, over the version 5-M capacity of {encoder.MAX_CHARS}",
            file=sys.stderr,
        )
        return 1

    matrix = encoder.encode(url, args.mask)

    if payload is not None:
        print(f"seed ID     {payload.seed_id.hex()}")
        print(f"player ID   {payload.player_id.hex()}")
        print(f"slot        {payload.player_slot}")
        print(
            f"score       {payload.total_strokes} strokes, {payload.total_putts} putts"
        )
        if payload.clamped_holes:
            print(f"CLAMPED     holes {payload.clamped_holes}")
    print(f"url         {url}")
    print(f"url length  {len(url)} of {encoder.MAX_CHARS}")
    print(f"mask        {args.mask} (spec would pick {encoder.best_mask(url)})")
    print(f"penalty     {encoder.penalty(matrix)}")

    image = (
        render.render_code(matrix, scale=args.scale)
        if args.crop
        else render.render_screen(matrix, scale=args.scale)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(f"wrote       {args.output} ({image.width}x{image.height})")

    if args.ascii:
        print()
        print(matrix.to_text())

    chr_data = nes.build_chr()
    nametable = nes.build_nametable(matrix.rows())
    assert nes.render_modules(chr_data, nametable) == matrix.rows()
    print(f"chr         {len(chr_data)} bytes, nametable {len(nametable)} bytes")
    print(f"quiet zone  {nes.quiet_zone_margins()} px")

    for name, decoder in DECODERS.items():
        result = decoder(render.render_screen(matrix, scale=3))
        status = "ok" if result == url else f"FAILED ({result!r})"
        print(f"{name:<11} {status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
