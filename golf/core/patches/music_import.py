"""Replace the three US course themes with tracks from a music dump.

**Proof of concept.** This exists to prove out the whole path -
``golf-export-music --dump`` on one ROM, the relocatable JSON it writes, and this
patch inserting those tracks into another - end to end. It is deliberately
narrow: it only replaces music IDs ``$02``, ``$03`` and ``$04`` in the *vanilla
US ROM*, and it only uses the space those three tracks already occupy. Every
region below is a hardcoded US address. A production version would discover the
layout the way :func:`golf.core.audio.discover_layout` does and allocate space
properly.

Replacing exactly the course themes is what makes the PoC small: ``CourseBgmTable``
at ``$DA14`` maps Japan/US/UK to ``$03``/``$02``/``$04``, so keeping the same IDs
means nothing outside the music data has to change.

What gets rewritten
-------------------

  order base table  $8EA0-$8EA2   3    one byte per replaced track
  order data        $8EC6-$8EEC   39   the three freed order lists
  pattern headers   $8F7B-$906C   242  22 freed header slots, 11 bytes each
  stream data       $9379-$9CA3   2347 the freed pattern blocks
  transpose table   $8851-$8853   3    one byte per replaced track
  envelope table    (relocated)        see below

Those four data regions are exactly what music ``$02``/``$03``/``$04`` own in the
vanilla ROM and nothing else references them - the 22 header slots are contiguous
and used by no other track, and no other pattern's stream pointer lands inside
``$9379-$9CA4``. Leftover bytes in each region are left as they are; they become
unreachable.

Header offsets are single bytes added to a base chosen by music ID (``$8F2A`` for
IDs below ``$04``, ``$900A`` above), so a header for track ``$04`` has to sit at
least ``$900D``. That is the one allocation constraint here, and
:func:`_place_headers` enforces it rather than assuming it.

The envelope table
------------------

The only engine table that is *not* portable between the two ROMs. Duration,
period-to-note arithmetic, vibrato, noise drums and the DPCM sample set are all
byte-identical, but ``MusicVolumeEnvelopeTable`` is 142 bytes in the US ROM (rows
``$00``-``$60``) and 190 in the Japanese one, whose course themes use rows up to
``$B0``.

So the patch builds a new table in the freed stream space: the US rows ``$00``-
``$6F`` verbatim, so every track that is *not* being replaced sounds unchanged,
followed by a fresh row for each imported envelope that the US table does not
already contain, taken from the dump's ``envelope_rows``. Imported patterns are
rewritten to point at the new row indices. Two instructions read the table -
``$8B31`` (pulse 2) and ``$8C7F`` (pulse 1) - and both operands are repointed.

Tuning
------

The Japanese period table is the US one shifted up two semitones, so the same
note byte sounds a whole tone sharper there. The dump records the difference as
``engine.semitones_sharper_than_reference``; adding it to each track's transpose
byte makes the track play at its original pitch in the target ROM.

See docs/music_format.md for the format itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PatchError, ROMPatch

if TYPE_CHECKING:
    from golf.core.rom_writer import RomWriter

BANK14_PRG = 0x38000

# --- Vanilla US addresses ----------------------------------------------

ORDER_TABLE = 0x8E9E  # MusicOrderBaseTable, indexed by music ID
ORDER_ORIGIN = 0x8E9F  # a track's order list is at ORDER_ORIGIN + its base byte
TRANSPOSE_TABLE = 0x884F
ENVELOPE_TABLE = 0x81A4
ENVELOPE_OPERANDS = (0x8B31, 0x8C7F)  # the two `LDA MusicVolumeEnvelopeTable,Y`

HEADER_SIZE = 11
ENVELOPE_ROW_LEN = 16

#: Music IDs this patch replaces - the three entries of CourseBgmTable ($DA14).
COURSE_TRACKS = (0x02, 0x03, 0x04)

#: Header base per music ID, the `< $04` / `< $10` split the engine does at $8AF6.
_HEADER_BASES = {0x02: 0x8F2A, 0x03: 0x8F2A, 0x04: 0x900A}

# --- Space the three course themes free up (CPU addresses, end exclusive) ---

FREE_ORDER = (0x8EC6, 0x8EED)  # 39 bytes
FREE_HEADERS = (0x8F7B, 0x906D)  # 22 slots
FREE_STREAMS = (0x9379, 0x9CA4)  # 2347 bytes

# --- Vanilla bytes the patch checks for and builds on -------------------

#: Rows $00-$60 of MusicVolumeEnvelopeTable. Copied into the relocated table so
#: the tracks that are not being replaced keep their exact volume envelopes.
US_ENVELOPE_ROWS = bytes([
    0x94, 0x94, 0x94, 0x94, 0x95, 0x95, 0x95, 0x95,
    0x96, 0x96, 0x96, 0x96, 0x97, 0x98, 0x99, 0x9A,  # $00
    0x92, 0x92, 0x92, 0x92, 0x92, 0x92, 0x92, 0x92,
    0x93, 0x93, 0x94, 0x94, 0x95, 0x95, 0x95, 0x96,  # $10
    0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
    0x90, 0x90, 0x90, 0x90, 0x90, 0x13, 0x96, 0x59,  # $20
    0x94, 0x94, 0x94, 0x94, 0x95, 0x95, 0x95, 0x95,
    0x96, 0x96, 0x96, 0x96, 0x97, 0x98, 0x99, 0x19,  # $30
    0x98, 0x97, 0x97, 0x96, 0x96, 0x95, 0x95, 0x94,
    0x93, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,  # $40
    0x14, 0x14, 0x14, 0x14, 0x15, 0x15, 0x15, 0x15,
    0x16, 0x16, 0x16, 0x16, 0x17, 0x18, 0x99, 0x99,  # $50
    0x94, 0x94, 0x94, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x92, 0x94, 0x95, 0x96, 0x9A, 0x98, 0x9A,  # $60
])

#: The first free envelope row index once US rows $00-$60 are kept.
FIRST_NEW_ENVELOPE = 0x70

_VANILLA_ORDER_BASES = bytes([0x27, 0x34, 0x41])  # $8EA0-$8EA2
_VANILLA_TRANSPOSE = bytes([0xFD, 0x00, 0xF8])  # $8851-$8853, i.e. -3, 0, -8
_ENVELOPE_OPERAND = bytes([ENVELOPE_TABLE & 0xFF, ENVELOPE_TABLE >> 8])


def _prg(cpu_addr: int) -> int:
    """Bank 14 CPU address -> absolute PRG offset."""
    return BANK14_PRG + cpu_addr - 0x8000


def _hexbytes(s: str) -> bytes:
    return bytes(int(v, 16) for v in s.split())


# --------------------------------------------------------------- allocation


def _place_headers(tracks: list[dict]) -> dict[tuple[int, int], int]:
    """Assign a freed header slot to every (music_id, pattern index).

    A slot is only usable by a track whose header base can reach it with a
    single byte, and offsets $00-$02 are order-list commands rather than header
    offsets, so the offset must also be at least 3. Tracks are placed in ID
    order, which puts the low-base tracks in the low slots and leaves the high
    slots for the ones that need them.
    """
    slots = list(range(FREE_HEADERS[0], FREE_HEADERS[1], HEADER_SIZE))
    taken: set[int] = set()
    out: dict[tuple[int, int], int] = {}
    for track in tracks:
        mid = track["music_id"]
        base = _HEADER_BASES[mid]
        for index in range(len(track["patterns"])):
            for addr in slots:
                if addr in taken or not 3 <= addr - base <= 0xFF:
                    continue
                taken.add(addr)
                out[(mid, index)] = addr
                break
            else:
                raise PatchError(
                    f"no free pattern header slot reachable from base "
                    f"${base:04X} for music ${mid:02X} pattern {index}"
                )
    return out


def _build_envelope_table(tracks: list[dict]) -> tuple[bytes, dict[int, dict[int, int]]]:
    """The relocated envelope table, plus a per-track base remap.

    US rows $00-$6F are kept as they are so the surviving tracks are untouched.
    An imported envelope whose bytes already match the row it names is left
    alone; anything else is appended as a new row and the importing patterns are
    repointed at it.
    """
    table = bytearray(US_ENVELOPE_ROWS)
    appended: dict[bytes, int] = {}
    remap: dict[int, dict[int, int]] = {}

    for track in tracks:
        rows = {int(k, 16): _hexbytes(v) for k, v in track["envelope_rows"].items()}
        mapping: dict[int, int] = {}
        for base, row in sorted(rows.items()):
            if len(row) != ENVELOPE_ROW_LEN:
                raise PatchError(
                    f"envelope row ${base:02X} of music ${track['music_id']:02X} is "
                    f"{len(row)} bytes, expected {ENVELOPE_ROW_LEN}"
                )
            if base + ENVELOPE_ROW_LEN <= len(US_ENVELOPE_ROWS) and (
                US_ENVELOPE_ROWS[base:base + ENVELOPE_ROW_LEN] == row
            ):
                mapping[base] = base  # the target ROM already has this envelope
            elif row in appended:
                mapping[base] = appended[row]
            else:
                index = FIRST_NEW_ENVELOPE + len(appended) * ENVELOPE_ROW_LEN
                if index + ENVELOPE_ROW_LEN > 0x100:
                    raise PatchError("out of envelope row indices")
                appended[row] = index
                table.extend(row)
                mapping[base] = index
        remap[track["music_id"]] = mapping

    return bytes(table), remap


# ------------------------------------------------------------------- patch


class MusicImportPatch(ROMPatch):
    """Insert three dumped tracks over the US ROM's course themes."""

    def __init__(self, dump: dict, *, transpose_adjust: int | None = None):
        by_id = {t["music_id"]: t for t in dump.get("tracks", [])}
        missing = [m for m in COURSE_TRACKS if m not in by_id]
        if missing:
            raise PatchError(
                "dump is missing music "
                + ", ".join(f"${m:02X}" for m in missing)
                + f" (has {', '.join(f'${m:02X}' for m in sorted(by_id))})"
            )
        tracks = [by_id[m] for m in COURSE_TRACKS]

        if transpose_adjust is None:
            transpose_adjust = dump.get("engine", {}).get(
                "semitones_sharper_than_reference", 0
            )

        self.name = "music_import"
        self.description = (
            f"replace course themes ${COURSE_TRACKS[0]:02X}/${COURSE_TRACKS[1]:02X}/"
            f"${COURSE_TRACKS[2]:02X} with tracks from {dump.get('source') or 'a dump'}"
        )
        self.source = dump.get("source", "")
        self.transpose_adjust = transpose_adjust
        self.tracks = tracks

        self.envelope_table, remap = _build_envelope_table(tracks)
        self.header_addr = _place_headers(tracks)
        self.writes: list[tuple[str, int, bytes]] = []
        self._layout(tracks, remap)

    # -- construction ---------------------------------------------------

    def _layout(self, tracks: list[dict], remap: dict[int, dict[int, int]]) -> None:
        stream_addr: dict[tuple[int, int], int] = {}

        # Streams first: the pattern headers point at them, and the relocated
        # envelope table goes in whatever is left over.
        cursor = FREE_STREAMS[0]
        for track in tracks:
            for index, pattern in enumerate(track["patterns"]):
                data = _hexbytes(pattern["stream"])
                if len(data) > 0xFF:
                    raise PatchError(
                        f"music ${track['music_id']:02X} pattern {index} is "
                        f"{len(data)} bytes; a pattern block's channel offsets are "
                        f"single bytes, so it cannot exceed 255"
                    )
                stream_addr[(track["music_id"], index)] = cursor
                self.writes.append(
                    (f"stream ${track['music_id']:02X}/{index}", cursor, data)
                )
                cursor += len(data)
        self.envelope_addr = cursor
        self.writes.append(("envelope table", cursor, self.envelope_table))
        cursor += len(self.envelope_table)
        self._check_fit("stream data", cursor, FREE_STREAMS)

        # Pattern headers.
        for track in tracks:
            mid = track["music_id"]
            for index, pattern in enumerate(track["patterns"]):
                ptr = stream_addr[(mid, index)]
                header = bytes([
                    pattern["tempo"],
                    ptr & 0xFF,
                    ptr >> 8,
                    pattern["triangle_start"],
                    pattern["pulse1_start"],
                    pattern["noise_start"],
                    pattern["dmc_start"],
                    remap[mid][pattern["pulse2_envelope"]],
                    remap[mid][pattern["pulse1_envelope"]],
                    pattern["pulse2_vibrato"],
                    pattern["pulse1_vibrato"],
                ])
                self.writes.append(
                    (f"header ${mid:02X}/{index}", self.header_addr[(mid, index)], header)
                )

        # Order lists, then the base table entry that points at each one.
        cursor = FREE_ORDER[0]
        for track in tracks:
            mid = track["music_id"]
            entries = []
            for entry in track["order"]:
                if entry["type"] == "flag":
                    entries.append(entry["value"])
                else:
                    offset = self.header_addr[(mid, entry["index"])] - _HEADER_BASES[mid]
                    entries.append(offset)
            data = bytes([track["loop_position"], *entries, 0x00])
            self.writes.append((f"order list ${mid:02X}", cursor, data))

            base = cursor - ORDER_ORIGIN
            if not 0 <= base <= 0xFF:
                raise PatchError(
                    f"order list for music ${mid:02X} at ${cursor:04X} is out of "
                    f"reach of MusicOrderBaseTable"
                )
            self.writes.append(
                (f"order base ${mid:02X}", ORDER_TABLE + mid, bytes([base]))
            )
            cursor += len(data)
        self._check_fit("order data", cursor, FREE_ORDER)

        # Transpose, adjusted for the target ROM's tuning.
        for track in tracks:
            value = (track["transpose"] + self.transpose_adjust) & 0xFF
            self.writes.append(
                (
                    f"transpose ${track['music_id']:02X}",
                    TRANSPOSE_TABLE + track["music_id"],
                    bytes([value]),
                )
            )

        # Point both envelope readers at the relocated table.
        operand = bytes([self.envelope_addr & 0xFF, self.envelope_addr >> 8])
        for addr in ENVELOPE_OPERANDS:
            self.writes.append((f"envelope operand ${addr:04X}", addr, operand))

    @staticmethod
    def _check_fit(what: str, end: int, region: tuple[int, int]) -> None:
        if end > region[1]:
            raise PatchError(
                f"{what} needs {end - region[0]} bytes but only "
                f"{region[1] - region[0]} are free at ${region[0]:04X}-${region[1] - 1:04X}"
            )

    # -- ROMPatch -------------------------------------------------------

    def can_apply(self, rom_writer: RomWriter) -> bool:
        """True if the ROM still has the vanilla US music data this replaces."""
        read = rom_writer.read_prg
        return (
            read(_prg(ENVELOPE_TABLE), len(US_ENVELOPE_ROWS)) == US_ENVELOPE_ROWS
            and all(read(_prg(a), 2) == _ENVELOPE_OPERAND for a in ENVELOPE_OPERANDS)
            and read(_prg(ORDER_TABLE + COURSE_TRACKS[0]), 3) == _VANILLA_ORDER_BASES
            and read(_prg(TRANSPOSE_TABLE + COURSE_TRACKS[0]), 3) == _VANILLA_TRANSPOSE
        )

    def is_applied(self, rom_writer: RomWriter) -> bool:
        return all(
            rom_writer.read_prg(_prg(addr), len(data)) == data
            for _, addr, data in self.writes
        )

    def apply(self, rom_writer: RomWriter) -> None:
        if self.is_applied(rom_writer):
            return
        if not self.can_apply(rom_writer):
            raise PatchError(
                f"Cannot apply patch '{self.name}': the ROM's music data is neither "
                f"vanilla US nor already carrying this import"
            )
        for _, addr, data in self.writes:
            rom_writer.write_prg(_prg(addr), data)

    # -- reporting ------------------------------------------------------

    def usage(self) -> list[tuple[str, int, int]]:
        """(region name, bytes written, bytes free) for each allocated region."""
        used = {"order data": 0, "pattern headers": 0, "stream data": 0}
        for name, _, data in self.writes:
            if name.startswith("order list"):
                used["order data"] += len(data)
            elif name.startswith("header "):
                used["pattern headers"] += len(data)
            elif name.startswith("stream ") or name == "envelope table":
                used["stream data"] += len(data)
        sizes = {
            "order data": FREE_ORDER[1] - FREE_ORDER[0],
            "pattern headers": FREE_HEADERS[1] - FREE_HEADERS[0],
            "stream data": FREE_STREAMS[1] - FREE_STREAMS[0],
        }
        return [(k, used[k], sizes[k]) for k in sizes]

    def __repr__(self) -> str:
        ids = " ".join(f"${t['music_id']:02X}" for t in self.tracks)
        return (
            f"MusicImportPatch(source={self.source!r}, tracks=[{ids}], "
            f"transpose_adjust={self.transpose_adjust:+d})"
        )


def music_import_patch(dump: dict, *, transpose_adjust: int | None = None) -> MusicImportPatch:
    """Build the patch from a ``golf-export-music --dump`` JSON document."""
    return MusicImportPatch(dump, transpose_adjust=transpose_adjust)
