"""Loading, validating, and rendering the site's checked-in Markdown pages."""

from pathlib import Path

import pytest
from markupsafe import Markup

from server.pages import PageCatalog, PageError


def write_page(
    directory: Path, name: str, frontmatter: str, body: str = "Body."
) -> None:
    (directory / name).write_text(f"+++\n{frontmatter}\n+++\n\n{body}\n")


def test_an_empty_directory_is_an_empty_catalog(tmp_path):
    catalog = PageCatalog.load(tmp_path)
    assert catalog.pages == ()
    assert catalog.listed == ()


def test_a_page_uses_its_filename_and_metadata_defaults(tmp_path):
    write_page(tmp_path, "playing-guide.md", 'title = "  Playing Guide  "')
    page = PageCatalog.load(tmp_path).pages[0]
    assert page.slug == "playing-guide"
    assert page.title == "Playing Guide"
    assert page.nav_title == "Playing Guide"
    assert page.order == 100
    assert page.enabled
    assert page.listed
    assert isinstance(page.body_html, Markup)
    assert page.body_html == "<p>Body.</p>\n"


def test_explicit_metadata_and_markdown_features(tmp_path):
    write_page(
        tmp_path,
        "reference.md",
        "\n".join(
            [
                'title = "Reference"',
                'nav_title = "Short"',
                "order = 12",
                "enabled = true",
                "listed = false",
            ]
        ),
        "## Section\n\n| A | B |\n| - | - |\n| 1 | 2 |",
    )
    page = PageCatalog.load(tmp_path).pages[0]
    assert (page.nav_title, page.order, page.enabled, page.listed) == (
        "Short",
        12,
        True,
        False,
    )
    assert "<h2>Section</h2>" in page.body_html
    assert "<table>" in page.body_html


def test_raw_html_is_not_rendered(tmp_path):
    write_page(tmp_path, "safe.md", 'title = "Safe"', '<script>alert("x")</script>')
    html = PageCatalog.load(tmp_path).pages[0].body_html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_listed_pages_are_enabled_and_sorted_for_display(tmp_path):
    write_page(tmp_path, "zulu.md", 'title = "Zulu"\norder = 1')
    write_page(tmp_path, "alpha.md", 'title = "Alpha"\norder = 1')
    write_page(tmp_path, "later.md", 'title = "Later"\norder = 2')
    write_page(tmp_path, "unlisted.md", 'title = "Unlisted"\nlisted = false')
    write_page(
        tmp_path, "disabled.md", 'title = "Disabled"\nenabled = false\nlisted = false'
    )
    catalog = PageCatalog.load(tmp_path)
    assert [page.slug for page in catalog.listed] == ["alpha", "zulu", "later"]
    unlisted = catalog.get("unlisted")
    assert unlisted is not None
    assert unlisted.slug == "unlisted"
    assert catalog.get("disabled") is None
    assert catalog.get("missing") is None


@pytest.mark.parametrize(
    ("name", "source", "problem"),
    [
        ("bad.md", "Body only", "first line"),
        ("bad.md", '+++\ntitle = "Bad"\n', "missing closing"),
        ("bad.md", "+++\ntitle = [\n+++\n", "invalid TOML"),
        ("bad.md", "+++\norder = 1\n+++\n", "title must be a nonempty string"),
        ("bad.md", '+++\ntitle = " "\n+++\n', "title must be a nonempty string"),
        ("bad.md", '+++\ntitle = "Bad"\nunknown = 1\n+++\n', "unknown frontmatter"),
        (
            "bad.md",
            '+++\ntitle = "Bad"\nnav_title = 1\n+++\n',
            "nav_title must be a nonempty string",
        ),
        (
            "bad.md",
            '+++\ntitle = "Bad"\norder = true\n+++\n',
            "order must be an integer",
        ),
        (
            "bad.md",
            '+++\ntitle = "Bad"\nenabled = 1\n+++\n',
            "enabled must be a boolean",
        ),
        ("bad.md", '+++\ntitle = "Bad"\nlisted = 1\n+++\n', "listed must be a boolean"),
        (
            "bad.md",
            '+++\ntitle = "Bad"\nenabled = false\nlisted = true\n+++\n',
            "disabled page cannot be listed",
        ),
    ],
)
def test_malformed_pages_name_the_file(tmp_path, name, source, problem):
    (tmp_path / name).write_text(source)
    with pytest.raises(PageError, match=problem) as caught:
        PageCatalog.load(tmp_path)
    assert name in str(caught.value)


def test_invalid_filename_is_rejected(tmp_path):
    write_page(tmp_path, "Bad_Name.md", 'title = "Bad"')
    with pytest.raises(PageError, match="Bad_Name.md.*filename"):
        PageCatalog.load(tmp_path)


def test_pages_in_subdirectories_are_rejected(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    write_page(nested, "page.md", 'title = "Page"')
    with pytest.raises(PageError, match="nested/page.md.*directly"):
        PageCatalog.load(tmp_path)


def test_missing_directory_is_rejected(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(PageError, match="directory does not exist"):
        PageCatalog.load(missing)
