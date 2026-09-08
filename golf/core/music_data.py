"""Extract music tracks from a ROM into a relocatable, JSON-friendly form.

The point of this module is to capture everything an inserter would need to write a
track into a *different* ROM: the order list, every pattern header with its stream
pointer replaced by an index, and the raw stream bytes. Nothing here depends on where
the data happened to live.

It works on both the US ROM and the Japanese release (Mario Open Golf). Their engines
are identical but their note tables are not - see :func:`semitone_offset`.
"""

from __future__ import annotations

import hashlib

from .audio import CPU_HZ, MusicLayout, _prg_image, discover_layout

FIXED_BANK_OFF = 0x3C000
COURSE_NAMES = ("japan", "us", "uk")


def _bank14(rom: bytes):
    prg = _prg_image(rom)
    return lambda cpu: prg[cpu - 0x8000]


def _fixed(rom: bytes) -> bytes:
    if len(rom) >= 16 and rom[:4] == b"NES\x1a":
        rom = rom[16:]
    return rom[FIXED_BANK_OFF:FIXED_BANK_OFF + 0x4000]


# ------------------------------------------------------------------ note tables

def period_words(rom: bytes, layout: MusicLayout) -> list[int]:
    """The 12 chromatic period words (index 0 is unused by the engine)."""
    b = _bank14(rom)
    return [b(layout.period_table + 2 * i) | (b(layout.period_table + 2 * i + 1) << 8)
            for i in range(13)]


def base_note_hz(rom: bytes, layout: MusicLayout) -> float:
    """Pitch of note byte 1, which anchors the whole period table."""
    p = period_words(rom, layout)[1] >> 1
    return CPU_HZ / (16 * (p + 1))


def semitone_offset(rom: bytes, reference: bytes) -> int:
    """How many semitones sharper `rom` plays a given note byte than `reference`.

    The JP ROM's period table is the US one shifted two semitones, so a JP track
    dropped into the US ROM needs +2 added to its transpose byte to sound the same.
    """
    import math
    a = base_note_hz(rom, discover_layout(rom))
    b = base_note_hz(reference, discover_layout(reference))
    return round(12 * math.log2(a / b))


# ---------------------------------------------------------------- course lookup

def discover_course_bgm(rom: bytes) -> dict:
    """Find StartCourseBgm and read the course -> music ID table.

    The table's length is not encoded anywhere, so it is read until a byte stops
    being a playable music ID. That is unambiguous here: the US table is followed by
    `BIT $04F6` ($2C) and the JP table by the same, and $2C is not a valid track.

    The US ROM has three courses; the Japanese release has six slots holding five
    distinct themes (slots 2 and 6 share one).
    """
    fx = _fixed(rom)
    b = _bank14(rom)
    order_table = discover_layout(rom).order_table
    W = None
    pat = [0xA9, 0x00, 0x85, 0xFF, 0xAE, W, W, 0xAD, W, W, 0xF0, 0x09,
           0xBD, W, W, 0xC5, 0xF9, 0xF0, 0x02, 0x85, 0xF4]
    for i in range(len(fx) - len(pat)):
        if not all(p is None or fx[i + k] == p for k, p in enumerate(pat)):
            continue
        table = fx[i + 13] | (fx[i + 14] << 8)
        ids = []
        for k in range(12):
            v = fx[table - 0xC000 + k]
            if not 1 <= v <= 23 or b(order_table + v) == 0xFF:
                break
            ids.append(v)
        names = (list(COURSE_NAMES) if len(ids) == len(COURSE_NAMES)
                 else [f"course_{n + 1}" for n in range(len(ids))])
        return dict(routine=0xC000 + i,
                    curr_course=fx[i + 5] | (fx[i + 6] << 8),
                    bgm_on_flag=fx[i + 8] | (fx[i + 9] << 8),
                    table=table,
                    slots=[{"slot": n, "name": nm, "music_id": v}
                           for n, (nm, v) in enumerate(zip(names, ids))],
                    music_ids=dict(zip(names, ids)),
                    unique_music_ids=sorted(set(ids)))
    raise ValueError("could not locate StartCourseBgm")


# -------------------------------------------------------------------- extraction

def _order(rom, layout, music_id):
    b = _bank14(rom)
    base = b(layout.order_table + music_id)
    if base == 0xFF:
        return None, []
    i = layout.order_table + 1 + base
    loop = b(i)
    i += 1
    seq = []
    while True:
        v = b(i)
        i += 1
        if v == 0:
            break
        seq.append(v)
        if len(seq) > 128:
            raise ValueError(f"runaway order list for music ${music_id:02X}")
    return loop, seq


def _header(rom, addr):
    b = _bank14(rom)
    h = [b(addr + i) for i in range(11)]
    return dict(tempo=h[0], ptr=h[1] | (h[2] << 8), triangle_start=h[3],
                pulse1_start=h[4], noise_start=h[5], dmc_start=h[6],
                pulse2_envelope=h[7], pulse1_envelope=h[8],
                pulse2_vibrato=h[9], pulse1_vibrato=h[10])


def _pattern_frames(rom, layout, h):
    """Section length, which the pulse 2 stream defines by running to its $00.

    Bounding this by `pulse1_start` would be wrong: that offset is 0 on patterns
    where pulse 1 is disabled, and the engine reads to the terminator regardless.
    """
    b = _bank14(rom)
    i = 0
    dur = 0
    total = 0
    while i < 255:
        v = b(h["ptr"] + i)
        i += 1
        if v & 0x80:
            dur = b(layout.duration_table + ((v & 0x1F) + h["tempo"]))
            continue
        if v == 0:
            break
        if v == 1:
            i += 1
            continue
        total += dur
    return total, i


def channel_end(rom, layout, h, channel: str) -> int:
    """Byte index just past the last byte the engine reads for one channel.

    A section ends when the pulse 2 stream hits $00; the other channels simply stop
    being read at that point, and several have no terminator of their own. So the
    bound is the section's frame total, not a marker.
    """
    b = _bank14(rom)
    section, pulse2_end = _pattern_frames(rom, layout, h)
    if channel == "pulse2":
        return pulse2_end
    start = {"pulse1": h["pulse1_start"], "triangle": h["triangle_start"],
             "noise": h["noise_start"], "dmc": h["dmc_start"]}[channel]
    if start == 0:
        return 0                      # channel disabled for this pattern
    i, dur, t = start, 0, 0
    while t < section and i < 255:
        v = b(h["ptr"] + i)
        i += 1
        if v & 0x80:
            dur = b(layout.duration_table + ((v & 0x1F) + h["tempo"]))
            continue
        if v == 0:
            if channel == "pulse1":
                i += 1                # $00 takes a sweep operand, then continues
                continue
            if channel in ("noise", "dmc"):
                break                 # loops back to its own start
        t += dur
    return i


def block_size(rom: bytes, layout: MusicLayout, h: dict) -> int:
    """How many bytes of the pattern's block the engine can actually reach."""
    return max(channel_end(rom, layout, h, c)
               for c in ("pulse2", "pulse1", "triangle", "noise", "dmc"))


def all_patterns(rom: bytes, layout: MusicLayout) -> dict:
    """Every pattern header in the ROM, keyed by header address."""
    out = {}
    for mid in range(24):
        loop, seq = _order(rom, layout, mid)
        if loop is None:
            continue
        for v in seq:
            if v > 2:
                a = layout.header_base(mid) + v
                out.setdefault(a, _header(rom, a))
    return out


def extract_track(rom: bytes, music_id: int, layout: MusicLayout | None = None) -> dict:
    """One track as relocatable data: order list, pattern headers, stream bytes."""
    layout = layout or discover_layout(rom)
    b = _bank14(rom)
    loop, seq = _order(rom, layout, music_id)
    if loop is None:
        raise ValueError(f"music ${music_id:02X} has no track")

    patterns, index_of, entries = [], {}, []
    for v in seq:
        if v < 3:
            entries.append({"type": "flag", "value": v})
            continue
        addr = layout.header_base(music_id) + v
        if addr not in index_of:
            h = _header(rom, addr)
            n = block_size(rom, layout, h)
            section, _ = _pattern_frames(rom, layout, h)
            index_of[addr] = len(patterns)
            patterns.append({
                "tempo": h["tempo"],
                "section_frames": section,
                "pulse1_start": h["pulse1_start"],
                "triangle_start": h["triangle_start"],
                "noise_start": h["noise_start"],
                "dmc_start": h["dmc_start"],
                "pulse2_envelope": h["pulse2_envelope"],
                "pulse1_envelope": h["pulse1_envelope"],
                "pulse2_vibrato": h["pulse2_vibrato"],
                "pulse1_vibrato": h["pulse1_vibrato"],
                "stream": " ".join(f"{b(h['ptr'] + i):02X}" for i in range(n)),
            })
        entries.append({"type": "pattern", "index": index_of[addr]})

    transpose = b(layout.transpose_table + music_id)
    return {
        "music_id": music_id,
        "transpose": transpose - 256 if transpose > 127 else transpose,
        "loop_position": loop,
        "order": entries,
        "patterns": patterns,
        "bytes": sum(len(p["stream"].split()) for p in patterns) + 11 * len(patterns),
    }


def export(rom: bytes, music_ids, *, source: str = "", reference: bytes | None = None) -> dict:
    """A complete, self-describing dump of the given tracks."""
    layout = discover_layout(rom)
    b = _bank14(rom)
    raw = rom[16:] if rom[:4] == b"NES\x1a" else rom

    def tbl(addr, n):
        return " ".join(f"{b(addr + i):02X}" for i in range(n))

    out = {
        "source": source,
        "sha1": hashlib.sha1(raw).hexdigest(),
        "engine": {
            "duration_table": tbl(layout.duration_table, 131),
            "period_table": tbl(layout.period_table, 26),
            "envelope_table": tbl(layout.envelope_table, 142),
            "noise_drum_table": tbl(layout.noise_drum_table, 40),
            "base_note_hz": round(base_note_hz(rom, layout), 2),
        },
        "course_bgm": discover_course_bgm(rom),
        "tracks": [extract_track(rom, i, layout) for i in music_ids],
    }
    if reference is not None:
        out["engine"]["semitones_sharper_than_reference"] = semitone_offset(rom, reference)
    return out
