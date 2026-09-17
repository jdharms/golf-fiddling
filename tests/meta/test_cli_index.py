"""Every command-line entry point is listed in the README's command index."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_entry_point_is_in_readme():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    readme = (ROOT / "README.md").read_text()
    missing = [
        name for name in scripts if not re.search(rf"`{re.escape(name)}[` ]", readme)
    ]
    assert not missing, f"add these commands to the README command index: {missing}"
