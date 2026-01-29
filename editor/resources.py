"""Resource path utilities for PyInstaller bundling."""

import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to a bundled resource.

    When running as a PyInstaller bundle, resources are extracted to
    a temporary directory referenced by sys._MEIPASS. When running
    as a script, resources are relative to the project root.

    Args:
        relative_path: Path relative to project root (e.g., "data/sprites/flag.json")

    Returns:
        Absolute Path to the resource
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as bundled exe - resources in temp dir
        base_path = Path(sys._MEIPASS) # pyright: ignore[reportAttributeAccessIssue]
    else:
        # Running as script - project root is parent of editor/
        base_path = Path(__file__).parent.parent

    return base_path / relative_path
