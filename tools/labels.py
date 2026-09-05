#!/usr/bin/env python3
"""
NES Open Tournament Golf - Mesen Label Editor

Add/edit/remove/list entries in a Mesen ".mlb" label file from the command
line, so labels discovered during reverse-engineering (with golf-rom-peek,
disassembly notes, etc.) can be recorded without hand-editing the raw file.

Base file + sidecar overlay:
  The base .mlb file (positional `mlb_file`) is treated as human-curated.
  `add`/`edit`/`remove` default to a writable sidecar file instead -
  "<mlb_file stem>.sidecar.mlb" next to it, unless --sidecar names a
  different path - so an agent doing research can freely record labels
  without touching the approved base file. Pass --target base to write
  straight to the base file once you're happy with an entry; a future
  merge tool will handle folding sidecar entries into base interactively.
  `list` shows the merged view, tagging each row's source.

Label types (see golf.core.mlb_labels for the full address semantics):
  prg  - NesPrgRom:    raw PRG ROM offset (same numbering as golf-rom-peek's
                        raw hex address form / --bank-resolved "$XXXX")
  ram  - NesInternalRam: CPU-space system RAM address ($0000-$1FFF)
  sram - NesSaveRam:    offset into cartridge battery-backed SRAM
  mem  - NesMemory:     CPU-space memory-mapped register address

Examples:
    golf-labels notes.mlb list --filter Scorecard
    golf-labels notes.mlb list --source sidecar
    golf-labels notes.mlb add prg '$AD5D' --bank 2 CourseSelectHandler
    golf-labels notes.mlb add ram 001A ScrollX --comment "current scroll X"
    golf-labels notes.mlb edit prg '$AD5D' --bank 2 --comment "confirmed via trace"
    golf-labels notes.mlb remove ram 001A
    golf-labels notes.mlb add prg '$AD5D' --bank 2 CourseSelectHandler --target base
"""

import argparse
import sys

from golf.core.mlb_labels import TYPE_ALIASES, Label, LabelStore
from golf.core.rom_utils import parse_cpu_or_prg_address


def _parse_prg_address_or_range(address: str, bank: int | None) -> tuple[int, int | None]:
    if "-" in address:
        lo, hi = address.split("-", 1)
        return parse_cpu_or_prg_address(lo, bank), parse_cpu_or_prg_address(hi, bank)
    return parse_cpu_or_prg_address(address, bank), None


def _parse_plain_address_or_range(address: str) -> tuple[int, int | None]:
    address = address.strip()
    if "-" in address:
        lo, hi = address.split("-", 1)
        return int(lo.strip().lstrip("$"), 16), int(hi.strip().lstrip("$"), 16)
    return int(address.lstrip("$"), 16), None


def _address_range(args) -> tuple[str, int, int | None]:
    type_ = TYPE_ALIASES[args.type]
    if type_ == "NesPrgRom":
        start, end = _parse_prg_address_or_range(args.address, args.bank)
    else:
        start, end = _parse_plain_address_or_range(args.address)
    return type_, start, end


def cmd_list(store: LabelStore, args) -> None:
    type_filter = TYPE_ALIASES[args.type] if args.type else None
    needle = args.filter.lower() if args.filter else None
    for label, source in store.iter_merged():
        if args.source != "all" and source != args.source:
            continue
        if type_filter and label.type != type_filter:
            continue
        if needle:
            haystack = label.name.lower() + " " + (label.comment or "").lower()
            if needle not in haystack:
                continue
        print(f"[{source}] {label.to_line()}")


def cmd_add(store: LabelStore, args) -> None:
    type_, start, end = _address_range(args)
    target = store.index_for(args.target)

    existing = target.find_exact(type_, start)
    if existing is not None and not args.force:
        print(
            f"Error: a label already exists at {type_}:{existing.address_str} "
            f"({existing.name}) in {args.target}. Use --force to overwrite, or `edit`.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.target == "sidecar":
        shadowed = store.base.find_exact(type_, start)
        if shadowed is not None and existing is None:
            print(
                f"Note: base already has a label at {type_}:{shadowed.address_str} "
                f"({shadowed.name}) - this sidecar entry will shadow it until merged.",
                file=sys.stderr,
            )

    label = Label(type_, start, end, args.name, args.comment)
    target.add(label)
    store.save(args.target)
    print(f"Added to {args.target} ({store.path_for(args.target)}): {label.to_line()}")


def cmd_edit(store: LabelStore, args) -> None:
    type_, start, _end = _address_range(args)
    target = store.index_for(args.target)
    label = target.find_exact(type_, start)
    if label is None:
        other = "base" if args.target == "sidecar" else "sidecar"
        hint = ""
        if store.index_for(other).find_exact(type_, start) is not None:
            hint = f" (found in {other} instead - pass --target {other} if that's the one to edit)"
        print(f"Error: no label found at {type_}:{start:04X} in {args.target}{hint}", file=sys.stderr)
        sys.exit(1)
    if not args.name and args.comment is None:
        print("Error: nothing to change (pass --name and/or --comment)", file=sys.stderr)
        sys.exit(1)
    if args.name:
        label.name = args.name
    if args.comment is not None:
        label.comment = args.comment or None
    store.save(args.target)
    print(f"Updated in {args.target}: {label.to_line()}")


def cmd_remove(store: LabelStore, args) -> None:
    type_, start, _end = _address_range(args)
    target = store.index_for(args.target)
    removed = target.remove(type_, start)
    if removed is None:
        other = "base" if args.target == "sidecar" else "sidecar"
        hint = ""
        if store.index_for(other).find_exact(type_, start) is not None:
            hint = f" (found in {other} instead - pass --target {other} if that's the one to remove)"
        print(f"Error: no label found at {type_}:{start:04X} in {args.target}{hint}", file=sys.stderr)
        sys.exit(1)
    store.save(args.target)
    print(f"Removed from {args.target}: {removed.to_line()}")


def main():
    parser = argparse.ArgumentParser(
        description="Add/edit/remove/list labels in a Mesen .mlb label file"
    )
    parser.add_argument("mlb_file", help="Path to the base .mlb label file")
    parser.add_argument(
        "--sidecar",
        help="Path to the writable sidecar overlay (default: '<mlb_file stem>.sidecar.mlb')",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List labels (merged base + sidecar view)")
    list_parser.add_argument("--type", choices=list(TYPE_ALIASES), help="Restrict to one type")
    list_parser.add_argument("--filter", help="Case-insensitive substring to match name/comment")
    list_parser.add_argument(
        "--source", choices=["all", "base", "sidecar"], default="all", help="Restrict to one source"
    )

    add_parser = subparsers.add_parser("add", help="Add a new label (sidecar by default)")
    add_parser.add_argument("type", choices=list(TYPE_ALIASES))
    add_parser.add_argument(
        "address", help="'$XXXX' (prg, needs --bank for switchable) or raw hex; 'START-END' for a range"
    )
    add_parser.add_argument("name")
    add_parser.add_argument("--comment")
    add_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14), for type=prg")
    add_parser.add_argument(
        "--target", choices=["sidecar", "base"], default="sidecar", help="Which file to write to"
    )
    add_parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing label at this address"
    )

    edit_parser = subparsers.add_parser("edit", help="Rename/re-comment an existing label")
    edit_parser.add_argument("type", choices=list(TYPE_ALIASES))
    edit_parser.add_argument("address")
    edit_parser.add_argument("--name")
    edit_parser.add_argument("--comment")
    edit_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14), for type=prg")
    edit_parser.add_argument(
        "--target", choices=["sidecar", "base"], default="sidecar", help="Which file to edit"
    )

    remove_parser = subparsers.add_parser("remove", help="Remove a label")
    remove_parser.add_argument("type", choices=list(TYPE_ALIASES))
    remove_parser.add_argument("address")
    remove_parser.add_argument("--bank", type=int, help="Switchable bank number (0-14), for type=prg")
    remove_parser.add_argument(
        "--target", choices=["sidecar", "base"], default="sidecar", help="Which file to remove from"
    )

    args = parser.parse_args()
    store = LabelStore.load(args.mlb_file, args.sidecar)

    commands = {"list": cmd_list, "add": cmd_add, "edit": cmd_edit, "remove": cmd_remove}
    try:
        commands[args.command](store, args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
