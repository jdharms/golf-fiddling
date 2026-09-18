"""The catalog index is append-only across its whole git history.

Every entry ever committed to data/catalog/holes.json is still in the working tree with
the same fields; the one permitted change is `withdrawn` going from absent to true. The
index version never decreases. See docs/catalog.md.
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = "data/catalog/holes.json"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def _committed_indexes() -> list[tuple[str, dict]]:
    try:
        commits = _git("log", "--format=%H", "--", INDEX).split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git history unavailable")
    return [
        (commit[:10], json.loads(_git("show", f"{commit}:{INDEX}")))
        for commit in commits
    ]


def test_no_committed_entry_was_removed_or_changed():
    current = json.loads((ROOT / INDEX).read_text())
    problems = []
    for commit, past in _committed_indexes():
        if current["version"] < past["version"]:
            problems.append(
                f"{commit}: version went from {past['version']} to {current['version']}"
            )
        for hole_id, fields in past["holes"].items():
            now = current["holes"].get(hole_id)
            if now is None:
                problems.append(f"{commit}: {hole_id} was removed")
                continue
            if fields.get("withdrawn") and not now.get("withdrawn"):
                problems.append(f"{commit}: {hole_id} was un-withdrawn")
            if {k: v for k, v in now.items() if k != "withdrawn"} != {
                k: v for k, v in fields.items() if k != "withdrawn"
            }:
                problems.append(
                    f"{commit}: {hole_id} changed; publish a new version instead"
                )
    assert not problems, "\n".join(problems)
