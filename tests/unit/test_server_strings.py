"""The site's strings catalog: loading, rendering, and that pages and catalog agree on keys."""

import re
import tomllib
from pathlib import Path

import pytest
from markupsafe import Markup, escape

from server.app import (
    DOWNLOAD_SCRIPT_STRINGS,
    RANGEFINDER_SCRIPT_STRINGS,
    ROM_SCRIPT_STRINGS,
)
from server.strings import CATALOG_DIR, Entry, Strings, StringsError

SERVER = Path(__file__).resolve().parents[2] / "server"
TEMPLATE_USE = re.compile(r"""\bt(?:_plain)?\(\s*["']([^"']+)["']""")
SCRIPT_USE = re.compile(r"""\bt\(\s*["']([^"']+)["']""")


def catalog(text: str) -> Strings:
    return Strings.from_toml(tomllib.loads(text))


def used(pattern: re.Pattern, paths) -> set[str]:
    return {key for path in paths for key in pattern.findall(path.read_text())}


#: admin pages are for admins only and hold their English themselves (server/CLAUDE.md)
ADMIN_TEMPLATES = SERVER / "templates" / "admin"


def template_keys() -> set[str]:
    """The keys the player-facing templates use: every template outside `ADMIN_TEMPLATES`."""
    paths = (SERVER / "templates").rglob("*.html")
    return used(TEMPLATE_USE, (path for path in paths if ADMIN_TEMPLATES not in path.parents))


def script_keys() -> set[str]:
    return used(SCRIPT_USE, (SERVER / "static").rglob("*.js"))


# -- The checked-in catalog ---------------------------------------------------------------


def test_the_catalog_loads_and_every_entry_has_a_note():
    strings = Strings.load()
    assert strings.keys()
    for key in strings.keys():  # noqa: SIM118 (Strings, not a dict)
        assert strings.entry(key).note.strip(), key


def test_the_scans_find_keys():
    assert "rom.heading" in template_keys()
    assert "rom.status.stored" in script_keys()


def test_admin_templates_use_no_strings():
    """The carve-out runs one way: an admin page's text is its own, never half in the catalog."""
    paths = list(ADMIN_TEMPLATES.rglob("*.html"))
    assert paths
    assert not used(TEMPLATE_USE, paths)


def test_every_key_a_page_uses_is_in_the_catalog():
    missing = (template_keys() | script_keys()) - set(Strings.load().keys())
    assert not missing, f"add these to server/strings/: {sorted(missing)}"


def test_every_catalog_entry_is_used():
    unused = set(Strings.load().keys()) - template_keys() - script_keys()
    assert not unused, f"no template or script uses these entries: {sorted(unused)}"


#: each page script, and the catalog prefix its page embeds for it
SCRIPT_PREFIXES = {
    "download.js": DOWNLOAD_SCRIPT_STRINGS,
    "rom.js": ROM_SCRIPT_STRINGS,
    "romstore.js": None,
    "rangefinder/app.js": RANGEFINDER_SCRIPT_STRINGS,
    "rangefinder/green-modal.js": None,
    "rangefinder/measure.js": None,
    "rangefinder/renderer.js": None,
    "rangefinder/strings.js": None,
    "rangefinder/ui.js": None,
}


def page_scripts() -> dict[str, Path]:
    return {
        path.relative_to(SERVER / "static").as_posix(): path
        for path in (SERVER / "static").rglob("*.js")
    }


def test_every_script_is_listed_with_its_prefix():
    assert page_scripts().keys() == SCRIPT_PREFIXES.keys()


@pytest.mark.parametrize("script, prefix", SCRIPT_PREFIXES.items())
def test_script_keys_are_embedded_for_the_script(script, prefix):
    keys = used(SCRIPT_USE, [page_scripts()[script]])
    if prefix is None:
        assert not keys, f"{script} is shared and uses no strings of its own: {sorted(keys)}"
        return
    missing = keys - Strings.load().for_script(prefix).keys()
    assert keys and not missing, f"{script} uses keys outside {prefix!r}: {sorted(missing)}"


def test_each_namespace_lives_in_exactly_one_file():
    """A page's strings sit together, so there is one place to look for `generate.*`."""
    seen: dict[str, str] = {}
    for file in sorted(CATALOG_DIR.rglob("*.toml")):
        keys = Strings.from_toml(tomllib.loads(file.read_text())).keys()
        for namespace in sorted({key.split(".")[0] for key in keys}):
            assert namespace not in seen, f"{namespace}.* is in both {seen[namespace]} and {file.name}"
            seen[namespace] = file.name


# -- The catalog directory ----------------------------------------------------------------


def write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text)


def test_every_file_in_the_directory_is_merged(tmp_path):
    write(tmp_path, "a.toml", '[a.one]\nnote = "n"\ntext = "t"\n')
    write(tmp_path, "b.toml", '[b.two]\nnote = "n"\n')
    assert Strings.load(tmp_path).keys() == ["a.one", "b.two"]


def test_files_in_subdirectories_are_merged_too(tmp_path):
    (tmp_path / "pages").mkdir()
    write(tmp_path, "a.toml", '[a.one]\nnote = "n"\n')
    write(tmp_path / "pages", "b.toml", '[b.two]\nnote = "n"\n')
    assert Strings.load(tmp_path).keys() == ["a.one", "b.two"]


def test_each_file_loads_as_a_catalog_of_its_own(tmp_path):
    (tmp_path / "pages").mkdir()
    write(tmp_path, "b.toml", '[b.two]\nnote = "n"\n[b.three]\nnote = "n"\ntext = "t"\n')
    write(tmp_path / "pages", "a.toml", '[a.one]\nnote = "n"\n')
    catalogs = Strings.load_files(tmp_path)
    assert list(catalogs) == [tmp_path / "b.toml", tmp_path / "pages" / "a.toml"]
    assert catalogs[tmp_path / "b.toml"].keys() == ["b.three", "b.two"]
    assert catalogs[tmp_path / "b.toml"].unwritten() == ["b.two"]
    assert catalogs[tmp_path / "pages" / "a.toml"].keys() == ["a.one"]


def test_a_key_in_two_files_is_an_error(tmp_path):
    write(tmp_path, "a.toml", '[dup.key]\nnote = "n"\n')
    write(tmp_path, "b.toml", '[dup.key]\nnote = "n"\n')
    with pytest.raises(StringsError, match="defined in both a.toml and b.toml"):
        Strings.load(tmp_path)


def test_a_malformed_file_is_named_in_the_error(tmp_path):
    write(tmp_path, "bad.toml", '[a]\ntext = "t"\n')
    with pytest.raises(StringsError, match="bad.toml: a: missing note"):
        Strings.load(tmp_path)


def test_unparsable_toml_is_named_in_the_error(tmp_path):
    write(tmp_path, "broken.toml", "[a\n")
    with pytest.raises(StringsError, match="broken.toml"):
        Strings.load(tmp_path)


def test_a_directory_with_no_catalog_files_is_an_error(tmp_path):
    with pytest.raises(StringsError, match="no strings in"):
        Strings.load(tmp_path)


# -- Loading ------------------------------------------------------------------------------


def test_nested_tables_flatten_to_dotted_keys():
    strings = catalog(
        """
        [a.b]
        note = "n1"
        text = "t1"
        [a.c.d]
        note = "n2"
        """
    )
    assert strings.keys() == ["a.b", "a.c.d"]
    assert strings.entry("a.b") == Entry("n1", "t1")
    assert strings.entry("a.c.d") == Entry("n2", "")


@pytest.mark.parametrize(
    "text, problem",
    [
        ('[a]\nnote = "n"\nsize = 3', "only note and text"),
        ('[a]\ntext = "t"', "missing note"),
        ('[a]\nnote = ""', "missing note"),
        ('[a]\nnote = "n"\ntext = 3', "text must be a string"),
        ('a = "loose"', "expected a table"),
        ("[a]", "empty table"),
        ('[a]\nnote = "n"\n[a.b]\nnote = "n"', "only note and text"),
    ],
)
def test_malformed_catalogs_are_refused(text, problem):
    with pytest.raises(StringsError, match=problem):
        catalog(text)


def test_an_unknown_key_is_an_error():
    with pytest.raises(StringsError, match="no string"):
        catalog('[a]\nnote = "n"').html("b")


# -- Rendering ----------------------------------------------------------------------------

WRITTEN = catalog(
    """
    [hash]
    note = "hash line"
    text = "Hash <code>{sha1}</code>"
    [braces]
    note = "literal braces"
    text = "{{sha1}} is {sha1}"
    [empty]
    note = "a note with <angle> & 'quotes'"
    [script.one]
    note = "n"
    text = "one"
    [script.two]
    note = "n"
    [scripts.other]
    note = "n"
    text = "other"
    """
)


def test_written_html_keeps_its_markup_and_escapes_values():
    rendered = WRITTEN.html("hash", sha1="<x>")
    assert isinstance(rendered, Markup)
    assert rendered == "Hash <code>&lt;x&gt;</code>"


def test_written_plain_text_is_formatted_unescaped():
    assert WRITTEN.plain("hash", sha1="abc") == "Hash <code>abc</code>"
    assert WRITTEN.plain("braces", sha1="abc") == "{sha1} is abc"


def test_unwritten_html_is_a_placeholder_carrying_its_note():
    rendered = WRITTEN.html("empty", file="<f>")
    assert rendered == Markup(
        f'<span class="unwritten" title="{escape("a note with <angle> & \'quotes\'")}">⟦empty file=&lt;f&gt;⟧</span>'
    )


def test_unwritten_plain_is_the_bare_placeholder():
    assert WRITTEN.plain("empty") == "⟦empty⟧"
    assert WRITTEN.plain("empty", a=1, b="two") == "⟦empty a=1 b=two⟧"


def test_text_using_a_value_the_page_does_not_pass_is_an_error():
    with pytest.raises(StringsError, match=r"uses \{sha1\}"):
        WRITTEN.html("hash")


def test_stray_braces_are_an_error():
    with pytest.raises(StringsError, match="bad braces"):
        catalog('[a]\nnote = "n"\ntext = "oops {"').plain("a")


def test_for_script_holds_one_prefix_with_none_for_unwritten():
    assert WRITTEN.for_script("script") == {"script.one": "one", "script.two": None}


def test_unwritten_lists_entries_without_text():
    assert WRITTEN.unwritten() == ["empty", "script.two"]
