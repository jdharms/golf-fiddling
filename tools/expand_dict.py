#!/usr/bin/env python3
"""
Dictionary Code Expander

Reads meta.json statistics and expands all dictionary codes into their
complete horizontal transition sequences.
"""

import json
import sys
from pathlib import Path


def build_transition_map(transitions_list):
    """
    Build a mapping of prev_byte -> next_byte from transition data.

    Args:
        transitions_list: List of {"prev_byte": "0xXX", "next_byte": "0xXX", "count": N} dicts

    Returns:
        Dictionary mapping prev_byte (int) -> next_byte (int)
    """
    mapping = {}
    for trans in transitions_list:
        prev = int(trans["prev_byte"], 16)
        next_byte = int(trans["next_byte"], 16)

        # In case of conflicts, prefer the more frequently used transition
        if prev not in mapping:
            mapping[prev] = next_byte
        # If we see a different mapping for the same prev_byte, note it but keep the first
        elif mapping[prev] != next_byte:
            print(f"Warning: Conflicting transitions for 0x{prev:02X}: 0x{mapping[prev]:02X} vs 0x{next_byte:02X}",
                  file=sys.stderr)

    return mapping


def expand_dict_code(code_hex, first_byte_hex, repeat_count, transition_map):
    """
    Expand a dictionary code into its complete sequence.

    Args:
        code_hex: Dictionary code as hex string (e.g., "0xE0")
        first_byte_hex: First byte as hex string (e.g., "0xA2")
        repeat_count: Number of times to apply horizontal transition
        transition_map: Mapping of prev_byte -> next_byte

    Returns:
        List of bytes representing the expanded sequence
    """
    sequence = []
    current = int(first_byte_hex, 16)
    sequence.append(current)

    for _ in range(repeat_count):
        if current in transition_map:
            current = transition_map[current]
            sequence.append(current)
        else:
            # If we don't have a transition, assume identity (shouldn't happen in real data)
            sequence.append(current)

    return sequence


def main():
    if len(sys.argv) < 2:
        print("Usage: python expand_dict.py <meta.json> [terrain|greens]")
        print("\nExpands all dictionary codes into their complete horizontal sequences.")
        sys.exit(1)

    meta_path = Path(sys.argv[1])
    data_type = sys.argv[2].lower() if len(sys.argv) > 2 else "terrain"

    if data_type not in ["terrain", "greens"]:
        print("Error: data_type must be 'terrain' or 'greens'")
        sys.exit(1)

    if not meta_path.exists():
        print(f"Error: {meta_path} not found")
        sys.exit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    stats = meta["statistics"][data_type]

    # Build transition map from horizontal transitions
    transition_map = build_transition_map(stats["horizontal_transitions"]["top_transitions"])

    # Also add any transitions from greens if we have them
    if "horizontal_transitions" in stats:
        transition_map.update(build_transition_map(stats["horizontal_transitions"]["top_transitions"]))

    print(f"=== Dictionary Code Expansions ({data_type.upper()}) ===\n")
    print(f"Horizontal transition map has {len(transition_map)} unique transitions")
    print()

    dict_codes = stats["dictionary_codes"]

    # Sort by code number
    sorted_codes = sorted(dict_codes.items(), key=lambda x: int(x[0], 16))

    for code_hex, info in sorted_codes:
        code_int = int(code_hex, 16)
        first_byte_hex = info["first_byte"]
        repeat_count = info["repeat_count"]
        usage_count = info["usage_count"]
        holes_count = len(info["holes"])

        # Expand the sequence
        sequence = expand_dict_code(code_hex, first_byte_hex, repeat_count, transition_map)

        # Format output
        seq_hex = " ".join(f"{b:02X}" for b in sequence)
        seq_hex_compact = "".join(f"{b:02X}" for b in sequence)

        print(f"{code_hex} (#{code_int - 0xE0:2d}): {seq_hex_compact:>20}  ({len(sequence):2d} bytes) | {usage_count:5d} uses in {holes_count:2d} holes")
        print(f"         Bytes: {seq_hex}")
        print(f"         Expanded: {repeat_count} transitions from 0x{sequence[0]:02X}")
        print()


if __name__ == "__main__":
    main()
