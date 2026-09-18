"""Player-visible English on the site, from a keyed catalog.

`server/strings/` holds the catalog as TOML files: `common.toml` for the elements on every
page, and one file per page beside it. Each entry is a `note` saying what it has to get
across and the values it receives, and the `text` itself. Every file under the directory is
loaded and merged, and entries carry their full dotted key, so a file name is organization
only. Templates and scripts refer to strings by key only. An entry with empty text renders
as a marked placeholder, so a page shows where text is still to be written. See
server/CLAUDE.md, "Player-facing text".
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, overload

from markupsafe import Markup

#: the catalog: every *.toml beside this module
CATALOG_DIR = Path(__file__).resolve().parent
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
            raise StringsError(
                f"{key}: expected a table with a note and text, got {type(value).__name__}"
            )
        if not value:
            raise StringsError(f"{key}: empty table")
        if not FIELDS & value.keys():
            _flatten(value, key + ".", out)
            continue
        extra = value.keys() - FIELDS
        if extra:
            raise StringsError(
                f"{key}: an entry holds only note and text, got {sorted(extra)}"
            )
        note, text = value.get("note"), value.get("text", "")
        if not isinstance(note, str) or not note.strip():
            raise StringsError(f"{key}: missing note")
        if not isinstance(text, str):
            raise StringsError(f"{key}: text must be a string")
        out[key] = Entry(note, text)


def _placeholder(key: str, values: Mapping[str, object]) -> str:
    return (
        "⟦"
        + " ".join([key, *(f"{name}={value}" for name, value in values.items())])
        + "⟧"
    )


class Strings:
    def __init__(self, entries: Mapping[str, Entry]):
        self._entries = dict(entries)

    @classmethod
    def load_files(cls, directory: Path = CATALOG_DIR) -> dict[Path, "Strings"]:
        """Every `*.toml` under `directory` as a catalog of its own, keyed by path, in path order."""
        catalogs: dict[Path, Strings] = {}
        for file in sorted(directory.rglob("*.toml")):
            try:
                with file.open("rb") as handle:
                    data = tomllib.load(handle)
            except tomllib.TOMLDecodeError as problem:
                raise StringsError(f"{file.name}: {problem}") from None
            found: dict[str, Entry] = {}
            try:
                _flatten(data, "", found)
            except StringsError as problem:
                raise StringsError(f"{file.name}: {problem}") from None
            catalogs[file] = cls(found)
        return catalogs

    @classmethod
    def load(cls, directory: Path = CATALOG_DIR) -> "Strings":
        """Every `*.toml` under `directory`, merged into one catalog."""
        entries: dict[str, Entry] = {}
        source: dict[str, Path] = {}
        for file, strings in cls.load_files(directory).items():
            for key in strings.keys():  # noqa: SIM118 (Strings, not a dict)
                if key in source:
                    raise StringsError(
                        f"{key}: defined in both {source[key].name} and {file.name}"
                    )
                source[key], entries[key] = file, strings.entry(key)
        if not entries:
            raise StringsError(f"no strings in {directory}")
        return cls(entries)

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
            return Markup('<span class="unwritten" title="{}">{}</span>').format(
                entry.note, _placeholder(key, values)
            )
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
        return {
            key: self._entries[key].text or None
            for key in self.keys()
            if key.startswith(start)
        }

    @overload
    @staticmethod
    def _format(key: str, text: Markup, values: Mapping[str, object]) -> Markup: ...

    @overload
    @staticmethod
    def _format(key: str, text: str, values: Mapping[str, object]) -> str: ...

    @staticmethod
    def _format(key: str, text: str, values: Mapping[str, object]) -> Any:
        """Insert the values, handing back the same kind of string it was given.

        `Markup.format` escapes what it inserts and returns `Markup`; `str.format` does
        neither. The overloads keep that difference, so `html` stays typed `Markup`.
        """
        try:
            return text.format(**values)
        except KeyError as problem:
            raise StringsError(
                f"{key}: the text uses {{{problem.args[0]}}}, but the page passes {sorted(values)}"
            ) from None
        except (IndexError, ValueError) as problem:
            raise StringsError(
                f"{key}: bad braces in the text ({problem}); write {{{{ and }}}} for literal braces"
            ) from None
