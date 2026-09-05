"""
Parsing and writing for Mesen ".mlb" label files.

Each line is one entry: "<Type>:<Start>[-<End>]:<Name>[:<Comment>]"

Addresses are uppercase hex, zero-padded to at least 4 digits, no "$" prefix.
Comments may embed literal two-character "\\n" escapes (Mesen keeps every
label on one physical text line, even ones with a multi-line comment).

Address meaning is type-dependent:
- NesPrgRom: raw PRG ROM offset, same numbering as
  golf.core.rom_utils.prg_to_bank_and_cpu / cpu_to_prg_fixed / cpu_to_prg_switched.
- NesInternalRam / NesMemory: CPU address as seen by the 6502 ($0000-$1FFF
  system RAM, $2000-$4017 memory-mapped registers).
- NesSaveRam: offset into the cartridge's battery-backed SRAM chip (commonly
  mapped at CPU $6000-$7FFF, mapper-dependent).
"""

import os
from dataclasses import dataclass
from pathlib import Path

LABEL_TYPES = ("NesMemory", "NesPrgRom", "NesInternalRam", "NesSaveRam")

TYPE_ALIASES = {
    "prg": "NesPrgRom",
    "ram": "NesInternalRam",
    "sram": "NesSaveRam",
    "mem": "NesMemory",
}

_TYPE_ORDER = {t: i for i, t in enumerate(LABEL_TYPES)}


@dataclass
class Label:
    type: str
    start: int
    end: int | None  # None means a single-address label, not a range
    name: str
    comment: str | None = None

    @property
    def address_str(self) -> str:
        if self.end is not None and self.end != self.start:
            return f"{self.start:04X}-{self.end:04X}"
        return f"{self.start:04X}"

    def contains(self, addr: int) -> bool:
        end = self.end if self.end is not None else self.start
        return self.start <= addr <= end

    def to_line(self) -> str:
        parts = [self.type, self.address_str, self.name]
        if self.comment:
            parts.append(self.comment)
        return ":".join(parts)


def describe(label: Label, addr: int) -> str:
    """Format a label for display, with a "+offset" suffix if addr isn't the start."""
    text = label.name
    if addr != label.start:
        text += f"+{addr - label.start}"
    if label.comment:
        first_line = label.comment.split("\\n", 1)[0]
        text += f"  ({first_line})"
    return text


def parse_line(line: str) -> Label | None:
    line = line.rstrip("\n").rstrip("\r")
    if not line:
        return None
    parts = line.split(":", 3)
    if len(parts) < 3:
        return None
    type_, addr_str, name = parts[0], parts[1], parts[2]
    comment = parts[3] if len(parts) > 3 else None
    if "-" in addr_str:
        lo, hi = addr_str.split("-", 1)
        start, end = int(lo, 16), int(hi, 16)
    else:
        start, end = int(addr_str, 16), None
    return Label(type_, start, end, name, comment)


def load_labels(path) -> list[Label]:
    labels = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            label = parse_line(line)
            if label is not None:
                labels.append(label)
    return labels


def save_labels(path, labels: list[Label]) -> None:
    ordered = sorted(labels, key=lambda l: (_TYPE_ORDER.get(l.type, len(LABEL_TYPES)), l.start))
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        for label in ordered:
            f.write(label.to_line() + "\n")


class LabelIndex:
    """In-memory view of a .mlb file, with lookup/mutation helpers."""

    def __init__(self, labels: list[Label]):
        self.labels = labels

    @classmethod
    def load(cls, path) -> "LabelIndex":
        return cls(load_labels(path))

    def save(self, path) -> None:
        save_labels(path, self.labels)

    def lookup(self, type_: str, addr: int) -> Label | None:
        for label in self.labels:
            if label.type == type_ and label.contains(addr):
                return label
        return None

    def find_exact(self, type_: str, start: int) -> Label | None:
        for label in self.labels:
            if label.type == type_ and label.start == start:
                return label
        return None

    def search_name(self, substring: str) -> list[Label]:
        needle = substring.lower()
        return [l for l in self.labels if needle in l.name.lower()]

    def add(self, label: Label) -> None:
        existing = self.find_exact(label.type, label.start)
        if existing is not None:
            self.labels.remove(existing)
        self.labels.append(label)

    def remove(self, type_: str, start: int) -> Label | None:
        existing = self.find_exact(type_, start)
        if existing is not None:
            self.labels.remove(existing)
        return existing


def default_sidecar_path(base_path) -> str:
    """The conventional sidecar path for a base .mlb file: "<name>.sidecar.mlb"."""
    p = Path(base_path)
    return str(p.with_name(f"{p.stem}.sidecar{p.suffix}"))


class LabelStore:
    """A curated base label set plus an optional writable sidecar overlay.

    The base file is treated as human-approved and is never written to by
    normal `add`/`edit`/`remove` operations - agents doing research add
    labels to the sidecar instead, so a human can review and merge sidecar
    entries into the base file later without hunting for what changed.

    Lookups (`lookup`, `search_name`) see the merged view, with a sidecar
    entry at a given type+address shadowing a base entry at the same spot.
    """

    def __init__(
        self,
        base: LabelIndex,
        sidecar: LabelIndex,
        base_path: str | None = None,
        sidecar_path: str | None = None,
    ):
        self.base = base
        self.sidecar = sidecar
        self.base_path = base_path
        self.sidecar_path = sidecar_path

    @classmethod
    def load(cls, base_path: str | None, sidecar_path: str | None = None) -> "LabelStore":
        if sidecar_path is None and base_path is not None:
            sidecar_path = default_sidecar_path(base_path)
        base = LabelIndex.load(base_path) if base_path else LabelIndex([])
        if sidecar_path and os.path.exists(sidecar_path):
            sidecar = LabelIndex.load(sidecar_path)
        else:
            sidecar = LabelIndex([])
        return cls(base, sidecar, base_path, sidecar_path)

    def lookup(self, type_: str, addr: int) -> Label | None:
        return self.sidecar.lookup(type_, addr) or self.base.lookup(type_, addr)

    def search_name(self, substring: str) -> list[Label]:
        seen = set()
        results = []
        for label in list(self.sidecar.labels) + list(self.base.labels):
            key = (label.type, label.start)
            if key in seen:
                continue
            seen.add(key)
            if substring.lower() in label.name.lower():
                results.append(label)
        return results

    def iter_merged(self):
        """Yield (label, source) pairs; a sidecar entry shadows a base entry at the same address."""
        seen = set()
        for label in self.sidecar.labels:
            seen.add((label.type, label.start))
            yield label, "sidecar"
        for label in self.base.labels:
            if (label.type, label.start) not in seen:
                yield label, "base"

    def index_for(self, target: str) -> LabelIndex:
        return self.base if target == "base" else self.sidecar

    def path_for(self, target: str) -> str | None:
        return self.base_path if target == "base" else self.sidecar_path

    def save(self, target: str) -> None:
        path = self.path_for(target)
        if not path:
            raise ValueError(f"no path configured for target '{target}'")
        self.index_for(target).save(path)
