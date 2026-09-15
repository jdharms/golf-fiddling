"""The site's strings catalog: loading, rendering, and that pages and catalog agree on keys."""

import re
import tomllib
from pathlib import Path

import pytest
from markupsafe import Markup, escape

from server.app import ROM_SCRIPT_STRINGS
from server.strings import Entry, Strings, StringsError

SERVER = Path(__file__).resolve().parents[2] / "server"
TEMPLATE_USE = re.compile(r"""\bt(?:_plain)?\(\s*["']([^"']+)["']""")
SCRIPT_USE = re.compile(r"""\bt\(\s*["']([^"']+)["']""")


def catalog(text: str) -> Strings:
    return Strings.from_toml(tomllib.loads(text))


def used(pattern: re.Pattern, paths) -> set[str]:
    return {key for path in paths for key in pattern.findall(path.read_text())}


def template_keys() -> set[str]:
    return used(TEMPLATE_USE, (SERVER / "templates").glob("*.html"))


def script_keys() -> set[str]:
    return used(SCRIPT_USE, (SERVER / "static").glob("*.js"))


# -- The checked-in catalog ---------------------------------------------------------------


def test_the_catalog_loads_and_every_entry_has_a_note():
    strings = Strings.load()
    assert strings.keys()
    for key in strings.keys():  # noqa: SIM118 (Strings, not a dict)
        assert strings.entry(key).note.strip(), key


def test_the_scans_find_keys():
    assert "rom.heading" in template_keys()
    assert "rom.status.stored" in script_keys()


def test_every_key_a_page_uses_is_in_the_catalog():
    missing = (template_keys() | script_keys()) - set(Strings.load().keys())
    assert not missing, f"add these to server/strings.toml: {sorted(missing)}"


def test_every_catalog_entry_is_used():
    unused = set(Strings.load().keys()) - template_keys() - script_keys()
    assert not unused, f"no template or script uses these entries: {sorted(unused)}"


def test_script_keys_are_embedded_for_the_script():
    embedded = Strings.load().for_script(ROM_SCRIPT_STRINGS)
    missing = script_keys() - embedded.keys()
    assert not missing, f"rom.js uses keys outside {ROM_SCRIPT_STRINGS!r}: {sorted(missing)}"


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
