"""Every [project.scripts] target imports and names a callable.

A module moved without updating pyproject.toml would otherwise only fail the
first time someone runs the command.
"""

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_entry_point_resolves():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    broken = []
    for name, target in scripts.items():
        module_name, _, attr = target.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as error:
            broken.append(f"{name}: {error}")
            continue
        if not callable(getattr(module, attr, None)):
            broken.append(f"{name}: {module_name} has no callable {attr!r}")
    assert not broken, "\n".join(broken)
