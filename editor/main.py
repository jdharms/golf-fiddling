"""
NES Open Tournament Golf - Editor Main

Command-line entry point for the editor application.
"""

import sys
from .application import EditorApplication


def main():
    """Main entry point for the editor."""
    if len(sys.argv) < 3:
        print(
            "Usage: python -m editor.main <terrain_chr.bin> <greens_chr.bin> [hole.json]"
        )
        print("")
        print("Example:")
        print("  python -m editor.main data/chr-ram.bin data/green-ram.bin")
        print(
            "  python -m editor.main data/chr-ram.bin data/green-ram.bin courses/japan/hole_01.json"
        )
        sys.exit(1)

    terrain_chr = sys.argv[1]
    greens_chr = sys.argv[2]

    app = EditorApplication(terrain_chr, greens_chr)

    # Load initial hole if specified
    if len(sys.argv) > 3:
        app.load_hole(sys.argv[3])

    app.run()


if __name__ == "__main__":
    main()
