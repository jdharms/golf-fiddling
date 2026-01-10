"""
NES Open Tournament Golf - Editor Main

Command-line entry point for the editor application.

Usage:
    golf-editor [terrain_chr greens_chr] [hole.json]

Defaults to data/chr-ram.bin and data/green-ram.bin if CHR files not specified.
"""

import sys

from .application import EditorApplication


def parse_arguments():
    """
    Parse command-line arguments with defaults.

    Returns:
        tuple[str, str, str | None]: (terrain_chr, greens_chr, hole_json)

    Usage patterns:
        golf-editor                              # defaults, no hole
        golf-editor hole.json                    # defaults, with hole
        golf-editor terrain.bin greens.bin       # custom CHR, no hole
        golf-editor terrain.bin greens.bin hole.json  # all explicit
    """
    # Default CHR paths
    DEFAULT_TERRAIN_CHR = "data/chr-ram.bin"
    DEFAULT_GREENS_CHR = "data/green-ram.bin"

    args = sys.argv[1:]  # Exclude program name

    if len(args) == 0:
        # No args: use defaults, no hole
        return DEFAULT_TERRAIN_CHR, DEFAULT_GREENS_CHR, None

    elif len(args) == 1:
        # 1 arg: if JSON, use defaults + hole; otherwise error
        if args[0].endswith(".json"):
            return DEFAULT_TERRAIN_CHR, DEFAULT_GREENS_CHR, args[0]
        else:
            print("Error: Single argument must be a hole JSON file")
            print("")
            show_usage()
            sys.exit(1)

    elif len(args) == 2:
        # 2 args: both should be CHR files
        if args[1].endswith(".json"):
            print("Error: Two arguments provided but second is JSON")
            print("Did you mean: golf-editor <terrain_chr> <greens_chr> <hole.json>?")
            print("")
            show_usage()
            sys.exit(1)
        return args[0], args[1], None

    elif len(args) == 3:
        # 3 args: terrain CHR, greens CHR, hole JSON
        return args[0], args[1], args[2]

    else:
        print(f"Error: Too many arguments ({len(args)} provided)")
        print("")
        show_usage()
        sys.exit(1)


def show_usage():
    """Display usage information."""
    print("Usage: golf-editor [terrain_chr greens_chr] [hole.json]")
    print("")
    print("Arguments:")
    print("  terrain_chr    Path to terrain CHR binary (default: data/chr-ram.bin)")
    print("  greens_chr     Path to greens CHR binary (default: data/green-ram.bin)")
    print("  hole.json      Optional hole file to load on startup")
    print("")
    print("Examples:")
    print("  golf-editor")
    print("  golf-editor hole_01.json")
    print("  golf-editor data/chr-ram.bin data/green-ram.bin")
    print(
        "  golf-editor data/chr-ram.bin data/green-ram.bin courses/japan/hole_01.json"
    )


def validate_chr_file(path: str, label: str):
    """Validate CHR file exists and is readable."""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        print(f"Error: {label} file not found: {path}")
        print("")
        if "CHR" in label:
            print("Using default paths? Run from project root directory.")
        sys.exit(1)

    if not p.is_file():
        print(f"Error: {label} path is not a file: {path}")
        sys.exit(1)


def main():
    """Main entry point for the editor."""
    terrain_chr, greens_chr, hole_json = parse_arguments()

    # Validate files exist before starting pygame
    validate_chr_file(terrain_chr, "Terrain CHR")
    validate_chr_file(greens_chr, "Greens CHR")
    if hole_json:
        validate_chr_file(hole_json, "Hole JSON")

    # Create and run application
    app = EditorApplication(terrain_chr, greens_chr)

    if hole_json:
        app.load_hole(hole_json)

    app.run()


if __name__ == "__main__":
    main()
