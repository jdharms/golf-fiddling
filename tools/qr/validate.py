#!/usr/bin/env python3
"""
Scorecard QR Validation Sweep

Decides whether the ROM can get away with a fixed QR mask, and which one.

For every mask, encodes a batch of random rounds, renders each as an NES
screen, puts each render through a set of simulated capture conditions, and
tries to decode the result with two independent decoders. Reports per-mask
decode rates, which conditions fail, and how the fixed mask compares to the
one the spec's penalty scoring would have chosen.
"""

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

from golf.qr import capture, encoder, render, sample
from golf.qr.decode import DECODERS


def _parse_masks(text: str) -> tuple[int, ...]:
    if text == "all":
        return tuple(range(8))
    masks = tuple(int(part) for part in text.split(","))
    for mask in masks:
        if not 0 <= mask <= 7:
            raise argparse.ArgumentTypeError(f"mask must be 0-7, got {mask}")
    return masks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--rounds",
        type=int,
        default=25,
        help="random rounds per mask (default: 25)",
    )
    parser.add_argument(
        "--masks", type=_parse_masks, default=tuple(range(8)), help="masks to test"
    )
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (default: 0)")
    parser.add_argument(
        "--degradations",
        help="comma-separated subset of capture conditions (default: all)",
    )
    parser.add_argument(
        "--decoders", help="comma-separated subset of decoders (default: all)"
    )
    parser.add_argument(
        "--crop",
        action="store_true",
        help="feed decoders the code plus quiet zone instead of the whole screen",
    )
    parser.add_argument(
        "--failures-to",
        type=Path,
        help="directory to write the clean render of any payload that failed to decode",
    )
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    args = parser.parse_args()

    degradations = capture.DEGRADATIONS
    if args.degradations:
        try:
            degradations = tuple(
                capture.DEGRADATIONS_BY_NAME[name]
                for name in args.degradations.split(",")
            )
        except KeyError as exc:
            print(f"unknown degradation {exc}", file=sys.stderr)
            return 1

    decoders = DECODERS
    if args.decoders:
        try:
            decoders = {name: DECODERS[name] for name in args.decoders.split(",")}
        except KeyError as exc:
            print(f"unknown decoder {exc}", file=sys.stderr)
            return 1

    # The same rounds for every mask, so masks are compared on equal footing.
    rng = random.Random(args.seed)
    key = sample.random_key(rng)
    urls = [sample.random_round(rng).to_url(key) for _ in range(args.rounds)]

    # (mask, degradation, decoder) -> [successes, attempts]
    tally: dict[tuple[int, str, str], list[int]] = defaultdict(lambda: [0, 0])
    penalties: dict[int, list[int]] = defaultdict(list)
    spec_choice: dict[int, int] = defaultdict(int)
    failures: list[tuple[int, str, str, str]] = []

    for url in urls:
        spec_choice[encoder.best_mask(url)] += 1

    total = len(args.masks) * len(urls)
    done = 0
    for mask in args.masks:
        for url in urls:
            matrix = encoder.encode(url, mask)
            penalties[mask].append(encoder.penalty(matrix))
            clean = (
                render.render_code(matrix, scale=1)
                if args.crop
                else render.render_screen(matrix, scale=1)
            )
            for degradation in degradations:
                image = degradation.apply(clean)
                for name, decoder in decoders.items():
                    result = decoder(image)
                    entry = tally[(mask, degradation.name, name)]
                    entry[1] += 1
                    if result == url:
                        entry[0] += 1
                    else:
                        failures.append((mask, degradation.name, name, url))
                        if args.failures_to:
                            args.failures_to.mkdir(parents=True, exist_ok=True)
                            stem = f"mask{mask}_{degradation.name}_{name}_{url[-12:]}"
                            clean.save(args.failures_to / f"{stem}.png")
            done += 1
            print(f"\r{done}/{total} rounds", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)

    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line)

    emit(f"# QR mask validation: {len(urls)} rounds x {len(args.masks)} masks")
    emit()
    emit(
        f"Decoders: {', '.join(decoders)}. "
        f"Image: {'code + quiet zone' if args.crop else 'full 256x240 screen'}."
    )
    emit()

    header = "| mask | " + " | ".join(d.name for d in degradations) + " | overall |"
    emit(header)
    emit("|---" * (len(degradations) + 2) + "|")
    for mask in args.masks:
        cells = []
        mask_ok = mask_total = 0
        for degradation in degradations:
            ok = sum(tally[(mask, degradation.name, name)][0] for name in decoders)
            attempts = sum(
                tally[(mask, degradation.name, name)][1] for name in decoders
            )
            mask_ok += ok
            mask_total += attempts
            cells.append("100%" if ok == attempts else f"{ok * 100 / attempts:.0f}%")
        overall = f"{mask_ok * 100 / mask_total:.1f}%"
        emit(f"| {mask} | " + " | ".join(cells) + f" | **{overall}** |")
    emit()

    emit("## Spec penalty (lower is better)")
    emit()
    emit("| mask | min | mean | max | times spec would pick it |")
    emit("|---|---|---|---|---|")
    for mask in args.masks:
        values = penalties[mask]
        emit(
            f"| {mask} | {min(values)} | {sum(values) / len(values):.0f} | "
            f"{max(values)} | {spec_choice.get(mask, 0)} |"
        )
    emit()

    if failures:
        emit(f"## {len(failures)} failures")
        emit()
        by_bucket: dict[tuple[int, str, str], int] = defaultdict(int)
        for mask, degradation, decoder, _url in failures:
            by_bucket[(mask, degradation, decoder)] += 1
        emit("| mask | condition | decoder | failures |")
        emit("|---|---|---|---|")
        for (mask, degradation, decoder), count in sorted(
            by_bucket.items(), key=lambda item: -item[1]
        ):
            emit(f"| {mask} | {degradation} | {decoder} | {count} |")
    else:
        emit("No failures.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n")
        print(f"\nwrote {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
