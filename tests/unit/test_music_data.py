"""Tests for ROM layout discovery and relocatable track extraction."""

import json

import pytest

from golf.core import music_data as md
from golf.core.audio import build_nsf, discover_layout

US = "nes_open_us.nes"
JP = "mario_open_jp.nes"


def _load(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        pytest.skip(f"{path} not present")


@pytest.fixture(scope="module")
def us():
    return _load(US)


@pytest.fixture(scope="module")
def jp():
    return _load(JP)


# ------------------------------------------------------------------- discovery

def test_layout_matches_known_us_addresses(us):
    """The US addresses were derived by hand in docs/music_format.md."""
    L = discover_layout(us)
    assert L.order_table == 0x8E9E
    assert L.duration_table == 0x8107
    assert L.period_table == 0x818A
    assert L.envelope_table == 0x81A4
    assert L.transpose_table == 0x884F
    assert L.noise_drum_table == 0x8232
    assert L.dmc_duration_table == 0x8DCB
    assert L.dmc_rate_table == 0x8DD5
    assert L.dmc_ptr_table == 0x8DDF
    assert L.header_base(1) == 0x8F2A
    assert L.header_base(5) == 0x900A
    assert L.header_base(0x11) == 0x90C5


def test_layout_differs_for_the_japanese_rom(jp, us):
    """Mario Open Golf runs the same engine assembled at shifted addresses."""
    j, u = discover_layout(jp), discover_layout(us)
    assert j.order_table == u.order_table == 0x8E9E     # this one did not move
    assert j.duration_table != u.duration_table
    assert j.transpose_table != u.transpose_table
    assert j.header_base(1) != u.header_base(1)
    assert len(j.header_bases) == 4                     # JP has one more than the US
    for f in ("duration_table", "period_table", "envelope_table", "transpose_table"):
        assert 0x8000 <= getattr(j, f) < 0xC000


def test_duration_table_is_identical_across_regions(jp, us):
    """Tempos and note lengths port unchanged; pitch does not."""
    j, u = discover_layout(jp), discover_layout(us)
    jb, ub = md._bank14(jp), md._bank14(us)
    assert [jb(j.duration_table + i) for i in range(131)] == \
           [ub(u.duration_table + i) for i in range(131)]


def test_japanese_rom_is_two_semitones_sharp(jp, us):
    assert md.semitone_offset(jp, us) == 2
    assert md.semitone_offset(us, jp) == -2
    assert md.semitone_offset(us, us) == 0


# ---------------------------------------------------------------- course lookup

def test_us_course_bgm_table(us):
    u = md.discover_course_bgm(us)
    assert u["music_ids"] == {"japan": 3, "us": 2, "uk": 4}
    assert u["unique_music_ids"] == [2, 3, 4]
    assert u["bgm_on_flag"] == 0x6F98


def test_jp_course_bgm_table_has_six_slots_and_five_themes(jp, us):
    """The JP release has more courses than the US one, so the table is longer.

    Its length is not stored anywhere - it is read until a byte stops being a
    playable music ID.
    """
    j = md.discover_course_bgm(jp)
    assert [s["music_id"] for s in j["slots"]] == [4, 3, 0x0B, 2, 0x0C, 3]
    assert j["unique_music_ids"] == [2, 3, 4, 0x0B, 0x0C]
    assert len(j["slots"]) == 6 and len(j["unique_music_ids"]) == 5
    assert j["bgm_on_flag"] == 0x6BE1
    assert j["bgm_on_flag"] != md.discover_course_bgm(us)["bgm_on_flag"]


def test_course_table_stops_before_code(us, jp):
    """The byte after each table is $2C (BIT abs), which is not a valid track."""
    for rom in (us, jp):
        cb = md.discover_course_bgm(rom)
        fx = md._fixed(rom)
        after = fx[cb["table"] - 0xC000 + len(cb["slots"])]
        assert after == 0x2C


def test_jp_course_themes_are_distinct(jp):
    ids = md.discover_course_bgm(jp)["unique_music_ids"]
    sigs = {tuple(sorted(p["stream"] for p in md.extract_track(jp, i)["patterns"]))
            for i in ids}
    assert len(sigs) == len(ids) == 5


# ------------------------------------------------------------------- extraction

@pytest.mark.parametrize("path", [US, JP])
def test_every_pattern_block_is_valid(path):
    rom = _load(path)
    L = discover_layout(rom)
    pats = md.all_patterns(rom, L)
    assert pats
    for addr, h in pats.items():
        n = md.block_size(rom, L, h)
        assert 0 < n <= 255, f"${addr:04X} block of {n} bytes"


@pytest.mark.parametrize("path", [US, JP])
def test_extracted_track_round_trips(path):
    """Rebuilding the order list from the dump must reproduce the ROM's bytes."""
    rom = _load(path)
    L = discover_layout(rom)
    for mid in sorted(set(md.discover_course_bgm(rom)["music_ids"].values())):
        t = md.extract_track(rom, mid, L)
        loop, seq = md._order(rom, L, mid)
        assert t["loop_position"] == loop
        assert len(t["order"]) == len(seq)

        # Each order entry must map back to the byte it came from, and a given
        # pattern index must always correspond to the same order byte.
        rebuilt, seen = [], {}
        for entry, original in zip(t["order"], seq):
            if entry["type"] == "flag":
                assert entry["value"] == original < 3
                rebuilt.append(entry["value"])
                continue
            assert seen.setdefault(entry["index"], original) == original
            rebuilt.append(original)
        assert rebuilt == seq

        # Every pattern's captured stream must be exactly the bytes the engine reads.
        b = md._bank14(rom)
        for index, order_byte in seen.items():
            h = md._header(rom, L.header_base(mid) + order_byte)
            stream = bytes(int(x, 16) for x in t["patterns"][index]["stream"].split())
            expected = bytes(b(h["ptr"] + i) for i in range(md.block_size(rom, L, h)))
            assert stream == expected
            assert t["patterns"][index]["tempo"] == h["tempo"]
            assert t["patterns"][index]["pulse1_start"] == h["pulse1_start"]
            assert t["patterns"][index]["dmc_start"] == h["dmc_start"]


@pytest.mark.parametrize("path", [US, JP])
def test_export_is_json_serialisable_and_complete(path):
    rom = _load(path)
    ids = sorted(set(md.discover_course_bgm(rom)["music_ids"].values()))
    data = md.export(rom, ids, source=path)
    text = json.dumps(data)
    assert json.loads(text) == data
    assert len(data["tracks"]) == len(ids)
    assert data["sha1"] and data["engine"]["duration_table"]
    for t in data["tracks"]:
        assert t["patterns"] and t["order"]
        assert -128 <= t["transpose"] <= 127
        for p in t["patterns"]:
            assert p["stream"]
            assert p["section_frames"] > 0
            # channel start offsets must lie inside the block
            n = len(p["stream"].split())
            for k in ("pulse1_start", "triangle_start", "noise_start", "dmc_start"):
                assert p[k] < n, f"{k}={p[k]} outside a {n}-byte block"


def test_export_records_tuning_against_a_reference(jp, us):
    data = md.export(jp, [3], source=JP, reference=us)
    assert data["engine"]["semitones_sharper_than_reference"] == 2


# --------------------------------------------------------------------- JP NSF

def test_japanese_rom_exports_a_working_nsf(jp):
    """The stub is ROM-agnostic: same RAM map, same AudioEngineMain entry."""
    from py65.devices.mpu6502 import MPU

    from golf.core import audio

    nsf = build_nsf(jp)
    init, play = struct_unpack(nsf)
    body = nsf[0x80:]
    pages = [body[i * 0x1000:(i + 1) * 0x1000] for i in range(len(body) // 0x1000)]
    prg = bytearray(b"".join(pages[b] for b in nsf[112:120]))

    bus = audio._Bus(prg)
    mpu = MPU(memory=bus)
    mpu.sp = 0xFD
    mpu.a, mpu.x = 0, 0
    audio._call(mpu, init)
    for f in range(180):
        bus.frame = f
        audio._call(mpu, play)
    assert len(bus.writes) > 500
    assert {a for _, a, _ in bus.writes} >= {0x4000, 0x4004, 0x400A, 0x4015}


def struct_unpack(nsf):
    import struct
    return struct.unpack_from("<HH", nsf, 10)
