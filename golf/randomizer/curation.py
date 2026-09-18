"""
Curation: the editable judgments that steer generation, kept apart from the frozen catalog.

A record is keyed by lineage (`nes_uk/01`, never `nes_uk/01@2`), so it carries forward when
a new version is published. Generation reads a `CurationSnapshot`, a point-in-time view the
caller builds: the CLI from `data/catalog/curation.json`, the site from that file plus its
own database. Nothing here reaches a ROM. See docs/catalog.md.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import LINEAGE_PATTERN, REPO_ROOT, Catalog, CatalogError, HoleId

DEFAULT_CURATION = REPO_ROOT / "data" / "catalog" / "curation.json"

FAMILY_PATTERN = re.compile(r"[a-z0-9_]+")
_FIELDS = {"tags", "drawable", "family", "display_name"}


class CurationError(CatalogError):
    """A malformed curation file."""


@dataclass(frozen=True)
class HoleCuration:
    """What generation may know about a lineage beyond its catalog entry.

    `family` groups holes a person has judged to be the same hole in different releases or
    tee setups, such as a vanilla hole and its Mario Open twin. Every hole with the same
    label is in the same family; a hole is in at most one.
    """

    tags: frozenset[str] = frozenset()
    drawable: bool = True
    family: str | None = None
    display_name: str | None = None

    def to_json(self) -> dict:
        data: dict = {}
        if self.tags:
            data["tags"] = sorted(self.tags)
        if not self.drawable:
            data["drawable"] = False
        if self.family is not None:
            data["family"] = self.family
        if self.display_name is not None:
            data["display_name"] = self.display_name
        return data


def _record_from_json(lineage: str, data: dict) -> HoleCuration:
    if not isinstance(data, dict):
        raise CurationError(f"{lineage}: expected an object, got {data!r}")
    unknown = set(data) - _FIELDS
    if unknown:
        raise CurationError(f"{lineage}: unknown fields {sorted(unknown)}")
    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(
        isinstance(tag, str) and tag for tag in tags
    ):
        raise CurationError(f"{lineage}: tags must be a list of non-empty strings")
    drawable = data.get("drawable", True)
    if not isinstance(drawable, bool):
        raise CurationError(f"{lineage}: drawable must be true or false")
    family = data.get("family")
    if family is not None and not (
        isinstance(family, str) and FAMILY_PATTERN.fullmatch(family)
    ):
        raise CurationError(f"{lineage}: family must match {FAMILY_PATTERN.pattern}")
    display_name = data.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        raise CurationError(f"{lineage}: display_name must be a string")
    return HoleCuration(frozenset(tags), drawable, family, display_name)


@dataclass(frozen=True)
class CurationSnapshot:
    """Curation for every lineage at one moment, with a stamp identifying that moment."""

    holes: Mapping[str, HoleCuration] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_CURATION) -> "CurationSnapshot":
        return cls.from_json(json.loads(Path(path).read_text()))

    @classmethod
    def from_json(cls, data: dict) -> "CurationSnapshot":
        if not isinstance(data, dict):
            raise CurationError("curation file must be an object keyed by lineage")
        holes = {}
        for key, value in data.items():
            if not LINEAGE_PATTERN.fullmatch(key):
                raise CurationError(
                    f"curation key {key!r} must be a lineage such as nes_uk/01, with no @version"
                )
            holes[key] = _record_from_json(key, value)
        return cls(holes)

    def to_json(self) -> dict:
        return {
            lineage: self.holes[lineage].to_json() for lineage in sorted(self.holes)
        }

    @property
    def stamp(self) -> str:
        """SHA-256 of the canonical form: equal curation always has an equal stamp."""
        encoded = json.dumps(self.to_json(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def for_hole(self, hole_id: HoleId | str) -> HoleCuration:
        """The record for a hole's lineage, or the default when nobody has curated it."""
        return self.holes.get(HoleId.parse(hole_id).lineage, HoleCuration())

    def unknown_lineages(self, catalog: Catalog) -> list[str]:
        """Curated lineages the catalog has no entry for, which are almost always typos."""
        return sorted(set(self.holes) - catalog.lineages())

    def families(self) -> dict[str, list[str]]:
        """Family label to its member lineages."""
        members: dict[str, list[str]] = {}
        for lineage in sorted(self.holes):
            family = self.holes[lineage].family
            if family is not None:
                members.setdefault(family, []).append(lineage)
        return members
