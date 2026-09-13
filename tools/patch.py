#!/usr/bin/env python3
"""
NES Open Tournament Golf - Patch Builder

Builds a ROM, or an IPS patch, from a stack of patches: a JSON recipe, inline
-p steps, or both (inline steps follow the recipe's). The build checks the base
ROM, each patch's requirements, and that no two steps write the same byte.
See docs/patch_stack.md; --list shows every patch type and its parameters.
"""

import argparse
import sys
from pathlib import Path

from golf.core.ips import diff as ips_diff
from golf.core.patches import (
    PATCH_SPECS,
    PatchError,
    PatchStack,
    Recipe,
    RecipeError,
    describe_params,
    parse_step_arg,
)

EXAMPLES = """
examples:
  golf-patch nes_open_us.nes recipe.json -o out.nes
  golf-patch nes_open_us.nes recipe.json --ips out.ips --validate-only -v
  golf-patch nes_open_us.nes -p multi_bank_lookup -p course_mirrors -p attr_streaming \\
      -p course:course=courses/japan -p seeded_wind:seed=abc -o out.nes
  golf-patch nes_open_us.nes -p practice_swing:hold_frames=0x60 --save-recipe practice.json
  golf-patch --list
"""


def list_specs() -> None:
    for spec in PATCH_SPECS.values():
        print(spec.id)
        print(f"    {spec.summary}")
        print(f"    parameters: {describe_params(spec) or 'none'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[2],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    parser.add_argument("rom", nargs="?", help="Base ROM file")
    parser.add_argument("recipe", nargs="?", type=Path, help="JSON recipe")
    parser.add_argument(
        "-p",
        "--patch",
        action="append",
        default=[],
        metavar="ID[:KEY=VALUE,...]",
        help="add a step; paths are relative to the current directory",
    )
    parser.add_argument("-o", "--output", type=Path, help="write the ROM (default: <rom>.patched.nes unless --ips)")
    parser.add_argument("--ips", type=Path, help="write an IPS patch from the base to the build")
    parser.add_argument("--validate-only", action="store_true", help="build in memory; write nothing")
    parser.add_argument("--any-base", action="store_true", help="build on a base other than the vanilla US ROM")
    parser.add_argument("--save-recipe", type=Path, metavar="PATH", help="write the combined steps as a recipe")
    parser.add_argument("-v", "--verbose", action="store_true", help="show each patch type's report")
    parser.add_argument("--list", action="store_true", help="list every patch type and its parameters")
    args = parser.parse_args()

    if args.list:
        list_specs()
        return 0
    if not args.rom:
        parser.error("the base ROM is required (or use --list)")

    try:
        recipe = Recipe.load(args.recipe) if args.recipe else Recipe()
        recipe.steps += [parse_step_arg(text, Path.cwd()) for text in args.patch]
        if not recipe.steps:
            parser.error("no steps: give a recipe, -p steps, or both")
        if args.any_base:
            recipe.base_sha1 = None
        if args.save_recipe:
            recipe.save(args.save_recipe)
            print(f"wrote recipe {args.save_recipe}")

        base = Path(args.rom).read_bytes()
        built = recipe.build_steps(base)
        result = PatchStack([step.patch for step in built], base_sha1=recipe.base_sha1).build(base)
    except (RecipeError, PatchError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for step in built:
        regions = result.regions[step.patch.name]
        size = sum(end - start for start, end in regions)
        print(f"  {step.patch.name:24} {size:6,} bytes in {len(regions)} region(s)")
        if args.verbose:
            for line in step.report():
                print(f"      {line}")

    if args.validate_only:
        print("valid; nothing written")
        return 0

    if args.ips:
        args.ips.write_bytes(ips_diff(base, result.rom))
        print(f"wrote {args.ips}")
    if args.output or not args.ips:
        output = args.output or Path(str(Path(args.rom).with_suffix("")) + ".patched.nes")
        output.write_bytes(result.rom)
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
