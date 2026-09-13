#!/usr/bin/env python3
"""
Compare read and write traces to find address coverage gaps.

Reports:
- Addresses written but not read (new data not in original dump)
- Addresses read but not written (data from dump not being written back)

Usage:
    golf-compare-traces <read_trace.json> <write_trace.json>
"""

import argparse
import json
from dataclasses import dataclass


@dataclass
class AddressRange:
    """A range of PRG addresses with metadata."""
    start: int
    end: int  # exclusive
    annotation: str
    bank: int
    cpu_addr: str

    @property
    def length(self) -> int:
        return self.end - self.start


def load_trace(path: str) -> list[dict]:
    """Load trace entries from JSON file."""
    with open(path) as f:
        data = json.load(f)
    return data.get("entries", [])


def extract_ranges(entries: list[dict], op_type: str | None = None) -> list[AddressRange]:
    """Extract address ranges from trace entries."""
    ranges = []
    for entry in entries:
        if op_type and entry.get("type") != op_type:
            continue

        prg_offset = entry.get("prg_offset")
        length = entry.get("length", 1)

        if prg_offset is not None:
            ranges.append(AddressRange(
                start=prg_offset,
                end=prg_offset + length,
                annotation=entry.get("annotation", ""),
                bank=entry.get("bank", -1),
                cpu_addr=entry.get("cpu_addr", ""),
            ))

    return ranges


def ranges_overlap(a: AddressRange, b: AddressRange) -> bool:
    """Check if two ranges overlap."""
    return a.start < b.end and b.start < a.end


def find_unread_writes(
    read_ranges: list[AddressRange],
    write_ranges: list[AddressRange],
) -> list[AddressRange]:
    """Find write ranges that don't overlap with any read range."""
    unread = []

    for write in write_ranges:
        has_overlap = any(ranges_overlap(write, read) for read in read_ranges)
        if not has_overlap:
            unread.append(write)

    return unread


def find_unwritten_reads(
    read_ranges: list[AddressRange],
    write_ranges: list[AddressRange],
) -> list[AddressRange]:
    """Find read ranges that don't overlap with any write range."""
    unwritten = []

    for read in read_ranges:
        has_overlap = any(ranges_overlap(read, write) for write in write_ranges)
        if not has_overlap:
            unwritten.append(read)

    return unwritten


def merge_adjacent_ranges(ranges: list[AddressRange]) -> list[AddressRange]:
    """Merge adjacent/overlapping ranges with same bank."""
    if not ranges:
        return []

    # Sort by start address
    sorted_ranges = sorted(ranges, key=lambda r: (r.bank, r.start))

    merged = [sorted_ranges[0]]
    for current in sorted_ranges[1:]:
        last = merged[-1]

        # Merge if same bank and adjacent/overlapping
        if current.bank == last.bank and current.start <= last.end:
            # Extend the range, combine annotations
            annotations = last.annotation
            if current.annotation and current.annotation not in annotations:
                annotations = f"{annotations}; {current.annotation}"

            merged[-1] = AddressRange(
                start=last.start,
                end=max(last.end, current.end),
                annotation=annotations,
                bank=last.bank,
                cpu_addr=last.cpu_addr,
            )
        else:
            merged.append(current)

    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Compare read/write traces to find address coverage gaps"
    )
    parser.add_argument("read_trace", help="Path to read_trace.json")
    parser.add_argument("write_trace", help="Path to write_trace.json")
    parser.add_argument(
        "--merge", "-m",
        action="store_true",
        help="Merge adjacent address ranges",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Show summary statistics only",
    )

    args = parser.parse_args()

    # Load traces
    read_entries = load_trace(args.read_trace)
    write_entries = load_trace(args.write_trace)

    # Extract ranges
    read_ranges = extract_ranges(read_entries, "read")
    write_ranges = extract_ranges(write_entries, "write")

    print(f"Read trace: {len(read_ranges)} read operations")
    print(f"Write trace: {len(write_ranges)} write operations")
    print()

    # Find unread writes and unwritten reads
    unread_writes = find_unread_writes(read_ranges, write_ranges)
    unwritten_reads = find_unwritten_reads(read_ranges, write_ranges)

    if args.merge:
        unread_writes = merge_adjacent_ranges(unread_writes)
        unwritten_reads = merge_adjacent_ranges(unwritten_reads)

    # Calculate totals
    total_unread_bytes = sum(r.length for r in unread_writes)
    total_written_bytes = sum(r.length for r in write_ranges)
    total_unwritten_bytes = sum(r.length for r in unwritten_reads)
    total_read_bytes = sum(r.length for r in read_ranges)

    print(f"Written but not read: {len(unread_writes)} ranges, {total_unread_bytes:,} / {total_written_bytes:,} bytes")
    print(f"Read but not written: {len(unwritten_reads)} ranges, {total_unwritten_bytes:,} / {total_read_bytes:,} bytes")
    print()

    if args.summary:
        # Group by bank for summary
        def summarize_by_bank(ranges: list[AddressRange], label: str):
            by_bank: dict[int, int] = {}
            for r in ranges:
                by_bank[r.bank] = by_bank.get(r.bank, 0) + r.length

            if by_bank:
                print(f"{label} by bank:")
                for bank in sorted(by_bank.keys()):
                    print(f"  Bank {bank}: {by_bank[bank]:,} bytes")
                print()

        summarize_by_bank(unread_writes, "Written but not read")
        summarize_by_bank(unwritten_reads, "Read but not written")
        return

    def print_ranges(ranges: list[AddressRange], title: str):
        if not ranges:
            return

        print(title)
        print("-" * 80)

        for r in ranges:
            cpu_end = int(r.cpu_addr[1:], 16) + r.length - 1 if r.cpu_addr else 0
            print(
                f"  PRG ${r.start:05X}-${r.end - 1:05X} "
                f"(bank {r.bank}, {r.cpu_addr}-${cpu_end:04X}) "
                f"[{r.length:,} bytes]"
            )
            # Truncate long annotations
            annotation = r.annotation
            if len(annotation) > 60:
                annotation = annotation[:57] + "..."
            print(f"    {annotation}")
            print()

    print_ranges(unread_writes, "WRITTEN BUT NOT READ:")
    print_ranges(unwritten_reads, "READ BUT NOT WRITTEN:")


if __name__ == "__main__":
    main()
