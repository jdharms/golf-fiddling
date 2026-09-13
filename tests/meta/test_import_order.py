"""Every golf module imports cleanly as the first thing a fresh interpreter loads.

Within one pytest process, modules are already imported by the time most tests
run, so a circular import that only bites when one particular module is imported
*first* goes unnoticed (golf.formats.hole_data -> golf.core -> course_validation
-> hole_data did, for the neighbor analyzers). Each module gets its own
subprocess here.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _golf_modules() -> list[str]:
    modules = []
    for path in sorted((ROOT / "golf").rglob("*.py")):
        parts = path.relative_to(ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.append(".".join(parts))
    return modules


def _import_alone(module: str) -> tuple[str, str | None]:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return module, None
    return module, result.stderr.strip().splitlines()[-1]


def test_every_golf_module_imports_first():
    modules = _golf_modules()
    assert modules, "found no modules under golf/"
    with ThreadPoolExecutor(max_workers=8) as pool:
        failures = [(m, err) for m, err in pool.map(_import_alone, modules) if err]
    assert not failures, "\n".join(f"{m}: {err}" for m, err in failures)
