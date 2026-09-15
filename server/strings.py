"""Player-visible English on the site, from a keyed catalog.

`server/strings.toml` holds one entry per string: a `note` saying what it has to get
across and the values it receives, and the `text` itself. Templates and scripts refer to
strings by key only. An entry with empty text renders as a marked placeholder, so a page
shows where text is still to be written. See server/CLAUDE.md, "Player-facing text".
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from markupsafe import Markup

DEFAULT_PATH = Path(__file__).resolve().parent / "strings.toml"
FIELDS = frozenset({"note", "text"})


class StringsError(Exception):
    """A malformed catalog, an unknown key, or text that uses a value the page does not pass."""


@dataclass(frozen=True)
class Entry:
    note: str
    text: str


def _flatten(table: Mapping, prefix: str, out: dict[str, Entry]) -> None:
    for name, value in table.items():
        key = prefix + name
        if not isinstance(value, dict):
            raise StringsError(f"{key}: expected a table with a note and text, got {type(value).__name__}")
        if not value:
            raise StringsError(f"{key}: empty table")
        if not FIELDS & value.keys():
            _flatten(value, key + ".", out)
            continue
        extra = value.keys() - FIELDS
        if extra:
            raise StringsError(f"{key}: an entry holds only note and text, got {sorted(extra)}")
        note, text = value.get("note"), value.get("text", "")
        if not isinstance(note, str) or not note.strip():
            raise StringsError(f"{key}: missing note")
        if not isinstance(text, str):
            raise StringsError(f"{key}: text must be a string")
        out[key] = Entry(note, text)


def _placeholder(key: str, values: Mapping[str, object]) -> str:
    return "⟦" + " ".join([key, *(f"{name}={value}" for name, value in values.items())]) + "⟧"


class Strings:
    def __init__(self, entries: Mapping[str, Entry]):
        self._entries = dict(entries)

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Strings":
        with path.open("rb") as file:
            return cls.from_toml(tomllib.load(file))

    @classmethod
    def from_toml(cls, data: Mapping) -> "Strings":
        entries: dict[str, Entry] = {}
        _flatten(data, "", entries)
        return cls(entries)

    def keys(self) -> list[str]:
        return sorted(self._entries)

    def entry(self, key: str) -> Entry:
        try:
            return self._entries[key]
        except KeyError:
            raise StringsError(f"no string {key!r} in the catalog") from None

    def unwritten(self) -> list[str]:
        return [key for key in self.keys() if not self._entries[key].text]

    def html(self, key: str, **values: object) -> Markup:
        """The string for an HTML body: its text may hold inline HTML, and values are escaped."""
        entry = self.entry(key)
        if not entry.text:
            return Markup('<span class="unwritten" title="{}">{}</span>').format(entry.note, _placeholder(key, values))
        return self._format(key, Markup(entry.text), values)

    def plain(self, key: str, **values: object) -> str:
        """The string for a tab title, an attribute or anything else that takes no HTML."""
        entry = self.entry(key)
        if not entry.text:
            return _placeholder(key, values)
        return self._format(key, entry.text, values)

    def for_script(self, prefix: str) -> dict[str, str | None]:
        """Every entry under `prefix`, for a page to embed as JSON: text, or None while unwritten."""
        start = prefix + "."
        return {key: self._entries[key].text or None for key in self.keys() if key.startswith(start)}

    @staticmethod
    def _format(key: str, text: str, values: Mapping[str, object]) -> str:
        try:
            return text.format(**values)
        except KeyError as problem:
            raise StringsError(f"{key}: the text uses {{{problem.args[0]}}}, but the page passes {sorted(values)}") from None
        except (IndexError, ValueError) as problem:
            raise StringsError(f"{key}: bad braces in the text ({problem}); write {{{{ and }}}} for literal braces") from None
