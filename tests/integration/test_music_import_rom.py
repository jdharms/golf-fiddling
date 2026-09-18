"""Integration tests: importing JP course themes into the vanilla US ROM.

The decisive test is :func:`test_imported_tracks_sound_exactly_like_the_source`:
it runs the game's own 6502 engine over both ROMs and compares every APU
register write. Anything the patch got wrong - a stream byte, a channel offset,
an envelope row, the transpose adjustment - shows up there.
"""

import json
from pathlib import Path

import pytest

from golf.core import music_data as md
from golf.core.audio import discover_layout, run_engine
from golf.core.patches import PatchError, music_import_patch
from golf.core.patches.music_import import (
    COURSE_BGM_TABLE_PRG,
    COURSE_TRACKS,
    FREE_HEADERS,
    SCENE_MUSIC_OPERAND_PRG,
    SINGLE_TRACK_ID,
    US_ENVELOPE_ROWS,
    _build_envelope_table,
    _place_headers,
)
from golf.core.rom_writer import RomWriter

US_ROM = "nes_open_us.nes"
JP_ROM = "mario_open_jp.nes"
DUMP = "data/music/music_jp_courses.json"

pytestmark = pytest.mark.skipif(
    not all(Path(p).exists() for p in (US_ROM, JP_ROM, DUMP)),
    reason="ROMs or the JP music dump are not present",
)

UNTOUCHED_TRACKS = [0x01, *range(0x05, 0x18)]
JP_COURSE_THEMES = [0x02, 0x03, 0x04, 0x0B, 0x0C]

#: The one-track import under test: a JP theme with no US counterpart ID
SINGLE = 0x0C


@pytest.fixture(scope="module")
def dump():
    return json.loads(Path(DUMP).read_text())


@pytest.fixture(scope="module")
def patched(tmp_path_factory, dump):
    """The vanilla US ROM with the three JP course themes imported."""
    out = tmp_path_factory.mktemp("music") / "jpmusic.nes"
    writer = RomWriter(US_ROM, str(out))
    music_import_patch(dump).apply(writer)
    writer.save()
    return out.read_bytes()


@pytest.fixture(scope="module")
def single_path(tmp_path_factory, dump):
    """The vanilla US ROM with JP music $0C as its only course theme."""
    out = tmp_path_factory.mktemp("music") / "single.nes"
    writer = RomWriter(US_ROM, str(out))
    music_import_patch(dump, track=SINGLE).apply(writer)
    writer.save()
    return out


@pytest.fixture(scope="module")
def single(single_path):
    return single_path.read_bytes()


@pytest.fixture(scope="module")
def vanilla():
    return Path(US_ROM).read_bytes()


@pytest.fixture(scope="module")
def jp():
    return Path(JP_ROM).read_bytes()


# ------------------------------------------------------------------ applying


def test_vanilla_rom_is_applicable(tmp_path, dump):
    writer = RomWriter(US_ROM, str(tmp_path / "out.nes"))
    patch = music_import_patch(dump)
    assert patch.can_apply(writer)
    assert not patch.is_applied(writer)


def test_apply_is_idempotent(tmp_path, dump):
    out = str(tmp_path / "out.nes")
    patch = music_import_patch(dump)
    writer = RomWriter(US_ROM, out)
    patch.apply(writer)
    writer.save()

    again = RomWriter(out, str(tmp_path / "twice.nes"))
    assert patch.is_applied(again)
    patch.apply(again)
    again.save()
    assert Path(out).read_bytes() == Path(tmp_path / "twice.nes").read_bytes()


def test_dump_without_the_course_tracks_is_rejected(dump):
    partial = dict(dump, tracks=[t for t in dump["tracks"] if t["music_id"] != 0x04])
    with pytest.raises(PatchError, match=r"\$04"):
        music_import_patch(partial)


def test_only_bank_14_is_touched(patched, vanilla):
    assert len(patched) == len(vanilla)
    changed = [i for i in range(len(vanilla)) if vanilla[i] != patched[i]]
    assert changed
    assert all(0x38000 <= i - 16 < 0x3C000 for i in changed)


# ------------------------------------------------------------------ allocation


def test_header_slots_are_reachable_from_each_track_s_base(dump):
    """A header offset is one byte added to a base picked by music ID."""
    from golf.core.patches.music_import import _HEADER_BASES

    tracks = [t for t in dump["tracks"] if t["music_id"] in COURSE_TRACKS]
    placed = _place_headers(tracks)
    assert len(set(placed.values())) == len(placed)  # no slot reused
    for (mid, _), addr in placed.items():
        assert 3 <= addr - _HEADER_BASES[mid] <= 0xFF
        assert FREE_HEADERS[0] <= addr < FREE_HEADERS[1]
        assert (addr - FREE_HEADERS[0]) % 11 == 0


def test_envelope_table_keeps_the_us_rows_and_appends_the_rest(dump):
    tracks = [t for t in dump["tracks"] if t["music_id"] in COURSE_TRACKS]
    table, remap = _build_envelope_table(tracks)
    assert table[: len(US_ENVELOPE_ROWS)] == US_ENVELOPE_ROWS
    for track in tracks:
        rows = track["envelope_rows"]
        for base, new_base in remap[track["music_id"]].items():
            want = bytes(int(v, 16) for v in rows[f"{base:02X}"].split())
            assert table[new_base : new_base + 16] == want


# ------------------------------------------------------------------ the result


@pytest.mark.parametrize("music_id", COURSE_TRACKS)
def test_imported_track_round_trips_out_of_the_patched_rom(patched, jp, music_id):
    got = md.extract_track(patched, music_id)
    want = md.extract_track(jp, music_id)
    assert [p["stream"] for p in got["patterns"]] == [
        p["stream"] for p in want["patterns"]
    ]
    assert got["order"] == want["order"]
    assert got["loop_position"] == want["loop_position"]
    assert got["transpose"] == want["transpose"] + 2  # JP plays two semitones sharp


@pytest.mark.parametrize("music_id", COURSE_TRACKS)
def test_imported_tracks_sound_exactly_like_the_source(patched, jp, music_id):
    """30 seconds of APU writes, long enough for every track to loop."""
    assert run_engine(patched, music_id, 1800) == run_engine(jp, music_id, 1800)


@pytest.mark.parametrize("music_id", UNTOUCHED_TRACKS)
def test_every_other_track_is_unchanged(patched, vanilla, music_id):
    assert run_engine(patched, music_id, 600) == run_engine(vanilla, music_id, 600)


def test_the_relocated_envelope_table_is_still_discoverable(patched):
    """Both readers were repointed, so discover_layout finds the new address."""
    layout = discover_layout(patched)
    assert layout.envelope_table != 0x81A4
    assert 0x8000 <= layout.envelope_table < 0xC000


# ------------------------------------------------------------------ one track


@pytest.mark.parametrize("music_id", JP_COURSE_THEMES)
def test_every_jp_course_theme_fits_as_the_one_track(dump, music_id):
    patch = music_import_patch(dump, track=music_id)
    assert [t["music_id"] for t in patch.tracks] == [SINGLE_TRACK_ID]
    assert sorted(t["music_id"] for t in dump["tracks"]) == JP_COURSE_THEMES


def test_a_track_the_dump_lacks_is_rejected(dump):
    with pytest.raises(PatchError, match=r"no music \$17"):
        music_import_patch(dump, track=0x17)


def test_one_track_is_applicable_and_idempotent(tmp_path, dump, single_path):
    patch = music_import_patch(dump, track=SINGLE)
    fresh = RomWriter(US_ROM, str(tmp_path / "fresh.nes"))
    assert patch.can_apply(fresh)
    assert not patch.is_applied(fresh)

    again = RomWriter(str(single_path), str(tmp_path / "twice.nes"))
    assert patch.is_applied(again)
    patch.apply(again)
    again.save()
    assert (tmp_path / "twice.nes").read_bytes() == single_path.read_bytes()


def test_one_track_touches_bank_14_and_the_two_redirects(single, vanilla):
    changed = [i - 16 for i in range(len(vanilla)) if vanilla[i] != single[i]]
    outside = {i for i in changed if not 0x38000 <= i < 0x3C000}
    # CourseBgmTable's first entry is already $03
    assert outside == {
        COURSE_BGM_TABLE_PRG + 1,
        COURSE_BGM_TABLE_PRG + 2,
        SCENE_MUSIC_OPERAND_PRG,
    }


def test_every_course_and_the_scene_request_play_the_one_track(single):
    assert (
        single[16 + COURSE_BGM_TABLE_PRG : 16 + COURSE_BGM_TABLE_PRG + 3]
        == b"\x03\x03\x03"
    )
    assert (
        single[16 + SCENE_MUSIC_OPERAND_PRG - 1 : 16 + SCENE_MUSIC_OPERAND_PRG + 1]
        == b"\xa9\x03"
    )


def test_the_one_track_round_trips_out_of_the_patched_rom(single, jp):
    got = md.extract_track(single, SINGLE_TRACK_ID)
    want = md.extract_track(jp, SINGLE)
    assert [p["stream"] for p in got["patterns"]] == [
        p["stream"] for p in want["patterns"]
    ]
    assert got["order"] == want["order"]
    assert got["loop_position"] == want["loop_position"]
    assert got["transpose"] == want["transpose"] + 2


def test_the_one_track_sounds_exactly_like_the_source(single, jp):
    assert run_engine(single, SINGLE_TRACK_ID, 1800) == run_engine(jp, SINGLE, 1800)


@pytest.mark.parametrize("music_id", UNTOUCHED_TRACKS)
def test_one_track_leaves_every_other_track_unchanged(single, vanilla, music_id):
    assert run_engine(single, music_id, 600) == run_engine(vanilla, music_id, 600)
