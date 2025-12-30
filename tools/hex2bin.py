#!/usr/bin/env python3
"""
NES Open Tournament Golf - Hex to Binary Converter

Simple utility to convert space-separated hexadecimal text files to binary format.
"""

import sys


def hex_to_binary(input_file, output_file):
    with open(input_file, 'r') as f:
        hex_data = f.read()

    # Split on whitespace and convert each hex string to a byte
    bytes_list = bytes(int(b, 16) for b in hex_data.split())

    with open(output_file, 'wb') as f:
        f.write(bytes_list)

    print(f"Wrote {len(bytes_list)} bytes to {output_file}")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.txt> <output.bin>")
        sys.exit(1)

    hex_to_binary(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
