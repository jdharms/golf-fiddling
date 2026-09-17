"""tools/ holds thin CLIs: nothing imports from it, and archived scripts stay retired."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imports_tools(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        if any(name == "tools" or name.startswith("tools.") for name in names):
            return True
    return False


def test_nothing_imports_from_tools():
    offenders = [
        str(path.relative_to(ROOT))
        for package in ("golf", "editor", "server", "tests")
        for path in sorted((ROOT / package).rglob("*.py"))
        if _imports_tools(path)
    ]
    assert not offenders, (
        "logic that other code imports belongs in golf/, not tools/: " f"{offenders}"
    )


def test_archived_tools_have_no_entry_points():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    archived = [name for name, target in scripts.items() if target.startswith("tools.archive")]
    assert not archived, f"tools/archive/ scripts should not have entry points: {archived}"
