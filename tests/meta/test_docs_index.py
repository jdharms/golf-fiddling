"""docs/README.md indexes every doc, and every link in it resolves."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
INDEX = DOCS / "README.md"


def _index_links() -> list[str]:
    return re.findall(r"\]\(([^)#\s]+)\)", INDEX.read_text())


def test_every_doc_is_indexed():
    linked = {(DOCS / link).resolve() for link in _index_links()}
    missing = [
        path.name
        for path in sorted(DOCS.glob("*.md"))
        if path != INDEX and path.resolve() not in linked
    ]
    assert not missing, f"add these docs to docs/README.md: {missing}"


def test_every_index_link_resolves():
    broken = [link for link in _index_links() if not (DOCS / link).exists()]
    assert not broken, f"docs/README.md links to missing files: {broken}"
