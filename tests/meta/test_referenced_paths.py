"""File paths quoted in the agent-facing docs exist.

Covers every CLAUDE.md, README.md, docs/README.md and the project skills. A
backticked token counts as a path when it contains a `/` and only path
characters - so `golf/core/rom_reader.py` and `data/qr/` are checked, while
`golf-write <rom>`, `$8000-$BFFF` and `courses/{country}/` are not. A bare
directory name like `art/` is skipped too: layout lists use those for
subdirectories of whatever the bullet is about, so write nested paths out in
full. A path may be relative to the repo root or to the document's own
directory. Gitignored paths (the ROMs) are allowed to be absent.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "build", "dist", "node_modules", "__pycache__"}
PATH_TOKEN = re.compile(r"[A-Za-z0-9_.\-/]+")


def _documents() -> list[Path]:
    claude_files = [
        path
        for path in ROOT.rglob("CLAUDE.md")
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    ]
    return sorted(
        claude_files
        + [ROOT / "README.md", ROOT / "docs" / "README.md"]
        + list((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    )


def _path_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"`([^`\s]+)`", text):
        if "/" not in token or not PATH_TOKEN.fullmatch(token) or token.startswith("/"):
            continue
        segments = [segment for segment in token.split("/") if segment]
        if len(segments) == 1 and token.endswith("/"):
            continue
        # `.org/.byte/.word` is assembler directives, not a path
        if any(s.startswith(".") and s != ".claude" for s in segments):
            continue
        tokens.add(token)
    return tokens


def _gitignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


def test_referenced_paths_exist():
    missing = []
    for document in _documents():
        for token in sorted(_path_tokens(document.read_text())):
            if (ROOT / token).exists() or (document.parent / token).exists():
                continue
            if _gitignored(token):
                continue
            missing.append(f"{document.relative_to(ROOT)}: `{token}`")
    assert not missing, "referenced paths that do not exist:\n" + "\n".join(missing)
