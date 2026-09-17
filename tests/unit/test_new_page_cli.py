"""The new-page CLI creates valid Markdown page stubs without overwriting files."""

import subprocess
import sys
import tomllib
from pathlib import Path

from server.pages import PageCatalog

ROOT = Path(__file__).resolve().parents[2]


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.new_page", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def frontmatter(path: Path) -> dict:
    source = path.read_text()
    return tomllib.loads(source.split("+++", maxsplit=2)[1])


def test_creates_a_valid_page_with_explicit_defaults(tmp_path):
    result = run("How to Play", "--dir", tmp_path)
    path = tmp_path / "how-to-play.md"
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"created {path}\n"
    assert frontmatter(path) == {
        "title": "How to Play",
        "nav_title": "How to Play",
        "order": 100,
        "enabled": True,
        "listed": True,
    }
    assert path.read_text().endswith("+++\n\n")
    assert PageCatalog.load(tmp_path).get("how-to-play") is not None


def test_an_explicit_slug_controls_the_filename(tmp_path):
    result = run("Frequently Asked Questions", "--slug", "faq", "--dir", tmp_path)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "faq.md"
    assert path.is_file()
    assert frontmatter(path)["title"] == "Frequently Asked Questions"


def test_quotes_and_non_ascii_titles_as_valid_toml(tmp_path):
    result = run('Café "Rules"', "--dir", tmp_path)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "cafe-rules.md"
    assert frontmatter(path)["title"] == 'Café "Rules"'
    assert PageCatalog.load(tmp_path).get("cafe-rules") is not None


def test_refuses_to_overwrite_an_existing_page(tmp_path):
    path = tmp_path / "rules.md"
    path.write_text("keep me")
    result = run("Rules", "--dir", tmp_path)
    assert result.returncode == 2
    assert "already exists" in result.stderr
    assert path.read_text() == "keep me"


def test_rejects_a_title_that_cannot_form_a_slug(tmp_path):
    result = run("!!!", "--dir", tmp_path)
    assert result.returncode == 2
    assert "slug must" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_rejects_an_invalid_explicit_slug(tmp_path):
    result = run("Rules", "--slug", "Bad_Slug", "--dir", tmp_path)
    assert result.returncode == 2
    assert "slug must" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_rejects_a_missing_page_directory(tmp_path):
    missing = tmp_path / "missing"
    result = run("Rules", "--dir", missing)
    assert result.returncode == 2
    assert "directory does not exist" in result.stderr
    assert not missing.exists()
