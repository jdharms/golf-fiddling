"""The golf-site-strings CLI: unwritten strings listed by catalog file."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.site_strings", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text)


def test_unwritten_strings_are_listed_by_file_with_a_total(tmp_path):
    write(tmp_path, "a.toml", '[a.one]\nnote = "n"\ntext = ""\n[a.two]\nnote = "n"\ntext = "done"\n')
    write(tmp_path, "b.toml", '[b.one]\nnote = "n"\ntext = "done"\n')
    write(tmp_path, "c.toml", '[c.one]\nnote = "n"\n[c.two]\nnote = "n"\ntext = ""\n')
    result = run("--dir", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "a.toml (1)\n  a.one\n\nc.toml (2)\n  c.one\n  c.two\n\n3 unwritten in 2 of 3 files\n"


def test_notes_print_under_their_keys(tmp_path):
    write(tmp_path, "a.toml", '[a.one]\nnote = "h1 of the page"\n')
    result = run("--dir", tmp_path, "--notes")
    assert "  a.one\n      h1 of the page\n" in result.stdout


def test_a_fully_written_catalog_says_so(tmp_path):
    write(tmp_path, "a.toml", '[a.one]\nnote = "n"\ntext = "done"\n')
    result = run("--dir", tmp_path)
    assert result.returncode == 0
    assert result.stdout == "every string is written\n"


def test_a_malformed_catalog_is_an_error(tmp_path):
    write(tmp_path, "bad.toml", '[a]\ntext = "t"\n')
    result = run("--dir", tmp_path)
    assert result.returncode == 2
    assert "bad.toml" in result.stderr


def test_the_real_catalog_lists():
    result = run()
    assert result.returncode == 0, result.stderr
