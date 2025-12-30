#!/usr/bin/env python3
"""
Compression Tables Extraction Tool

Extracts decompression tables from NES Open Tournament Golf ROM and stores them
in JSON format optimized for future compression implementation.
"""

import json
import sys
from pathlib import Path

from golf.core.rom_reader import RomReader


def compute_dict_expansions(dict_table, horiz_table):
    """
    Expand all 32 dictionary codes using horizontal transitions.

    Args:
        dict_table: Dictionary table from ROM (64 bytes: 32 pairs)
        horiz_table: Horizontal transition table from ROM

    Returns:
        Dict mapping code hex string to expansion info
    """
    expansions = {}

    for code in range(0xE0, 0x100):  # 0xE0-0xFF
        dict_idx = (code - 0xE0) * 2
        first_byte = dict_table[dict_idx]
        repeat_count = dict_table[dict_idx + 1]

        # Generate sequence by applying horizontal transitions
        sequence = [first_byte]
        current = first_byte
        for _ in range(repeat_count):
            if current < len(horiz_table):
                current = horiz_table[current]
                sequence.append(current)
            else:
                sequence.append(0)
                current = 0

        expansions[f"0x{code:02X}"] = {
            "first_byte": first_byte,
            "repeat_count": repeat_count,
            "sequence": sequence,
            "length": len(sequence)
        }

    return expansions


def build_reverse_dict(dict_codes):
    """
    Build reverse lookup map from sequence to codes, sorted by length (longest first).

    This enables greedy longest-match compression.

    Args:
        dict_codes: Dictionary of code -> expansion info

    Returns:
        Dict mapping hex-encoded sequence string to list of matching codes
    """
    reverse = {}

    for code, info in dict_codes.items():
        seq_hex = "".join(f"{b:02X}" for b in info["sequence"])
        if seq_hex not in reverse:
            reverse[seq_hex] = []
        reverse[seq_hex].append(code)

    # Sort by length (longest first) - critical for greedy matching
    return dict(sorted(reverse.items(), key=lambda x: len(x[0]), reverse=True))


def extract_terrain_tables(rom):
    """
    Extract terrain decompression tables from fixed bank.

    Args:
        rom: RomReader instance

    Returns:
        Dict with terrain tables and metadata
    """
    # Read raw tables
    horiz_prg = rom.cpu_to_prg_fixed(0xE1AC)
    horiz_table = list(rom.read_prg(horiz_prg, 224))

    vert_prg = rom.cpu_to_prg_fixed(0xE28C)
    vert_table = list(rom.read_prg(vert_prg, 224))

    dict_prg = rom.cpu_to_prg_fixed(0xE36C)
    dict_table = list(rom.read_prg(dict_prg, 64))

    # Compute dictionary expansions
    dict_codes = compute_dict_expansions(dict_table, horiz_table)

    # Build reverse dictionary lookup
    reverse_dict = build_reverse_dict(dict_codes)

    return {
        "horizontal_table": horiz_table,
        "vertical_table": vert_table,
        "dictionary_codes": dict_codes,
        "reverse_dict_lookup": reverse_dict,
        "_metadata": {
            "table_addresses": {
                "horiz": "0xE1AC (fixed bank)",
                "vert": "0xE28C (fixed bank)",
                "dict": "0xE36C (fixed bank)"
            },
            "max_dict_sequence_length": max(info["length"] for info in dict_codes.values()),
            "total_dict_codes": len(dict_codes)
        }
    }


def extract_greens_tables(rom, bank=3):
    """
    Extract greens decompression tables from switchable bank.

    Args:
        rom: RomReader instance
        bank: Bank number (default 3 for greens)

    Returns:
        Dict with greens tables and metadata
    """
    # Read raw tables
    horiz_prg = rom.cpu_to_prg_switched(0x8000, bank)
    horiz_table = list(rom.read_prg(horiz_prg, 192))

    vert_prg = rom.cpu_to_prg_switched(0x80C0, bank)
    vert_table = list(rom.read_prg(vert_prg, 192))

    dict_prg = rom.cpu_to_prg_switched(0x8180, bank)
    dict_table = list(rom.read_prg(dict_prg, 64))

    # Compute dictionary expansions
    dict_codes = compute_dict_expansions(dict_table, horiz_table)

    # Build reverse dictionary lookup
    reverse_dict = build_reverse_dict(dict_codes)

    return {
        "horizontal_table": horiz_table,
        "vertical_table": vert_table,
        "dictionary_codes": dict_codes,
        "reverse_dict_lookup": reverse_dict,
        "_metadata": {
            "table_addresses": {
                "horiz": f"0x8000 (bank {bank})",
                "vert": f"0x80C0 (bank {bank})",
                "dict": f"0x8180 (bank {bank})"
            },
            "max_dict_sequence_length": max(info["length"] for info in dict_codes.values()),
            "total_dict_codes": len(dict_codes)
        }
    }


def extract_tables(rom_path, output_path):
    """
    Extract all decompression tables from ROM and save as JSON.

    Args:
        rom_path: Path to ROM file
        output_path: Path to output JSON file
    """
    print(f"Loading ROM: {rom_path}")
    rom = RomReader(rom_path)

    print("Extracting terrain tables...")
    terrain = extract_terrain_tables(rom)
    print(f"  ✓ Terrain: {len(terrain['dictionary_codes'])} dict codes, "
          f"max sequence length: {terrain['_metadata']['max_dict_sequence_length']}")

    print("Extracting greens tables...")
    greens = extract_greens_tables(rom)
    print(f"  ✓ Greens: {len(greens['dictionary_codes'])} dict codes, "
          f"max sequence length: {greens['_metadata']['max_dict_sequence_length']}")

    # Build output structure
    output = {
        "terrain": terrain,
        "greens": greens
    }

    # Write to file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting to: {output_path}")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Successfully extracted {len(output)} table sets")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_tables.py <rom_file> [output_file]")
        print("\nExtracts decompression tables from ROM to JSON format.")
        print("Default output: data/tables/compression_tables.json")
        sys.exit(1)

    rom_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "data/tables/compression_tables.json"

    extract_tables(rom_path, output_path)


if __name__ == "__main__":
    main()
