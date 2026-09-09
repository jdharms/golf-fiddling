"""Integration tests: the golfer sprite model against the real vanilla ROM.

The numbers here were each derived twice - once from the metasprite tables in
bank 8 and once from the graphics tables in banks 0-2 - so they are regression
tests for the identification as much as for the code.
"""

import json
import struct
from pathlib import Path

import pytest

from golf.core.golfer_sprites import (
    BODY_IN_FRONT_FRAMES,
    GOLFER_NAMES,
    GolferSprites,
)
from golf.core.graphics_codec import load_graphics_table
from golf.core.rom_reader import RomReader

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


@pytest.fixture(scope="module")
def rom():
    return RomReader(ROM_PATH)


@pytest.fixture(scope="module")
def sprites(rom):
    return GolferSprites(rom)


class TestGraphicsCodec:
    def test_course_intro_nametable_fills_exactly_one_screen(self, rom):
        table, vram = load_graphics_table(rom, 8, 0xB723)
        assert table.dest_ppu_addr == 0x2000
        # 960 tiles + 64 attribute bytes, landing exactly on the next nametable
        assert table.end_ppu_addr == 0x2400
        assert len(vram.touched) == 0x400

    def test_each_golfer_chr_ends_one_tile_past_its_highest_tile_index(
        self, rom, sprites
    ):
        from golf.core.golfer_sprites import GOLFER_CHR_TABLES

        for golfer in range(6):
            used = set()
            for putt in (False, True):
                for frame in sprites.body_frames(golfer, putt):
                    used.update(s.tile for s in frame.sprites)
            bank, addr = GOLFER_CHR_TABLES[golfer]
            table, _ = load_graphics_table(rom, bank, addr)
            assert table.end_ppu_addr == (max(used) + 1) * 16, GOLFER_NAMES[golfer]


class TestFrameInventory:
    def test_thirteen_swing_frames_hold_eleven_distinct_poses(self, sprites):
        for golfer in range(6):
            frames = sprites.body_frames(golfer)
            assert len(frames) == 13
            assert len({f.cpu_addr for f in frames}) == 11

    def test_frames_six_and_seven_replay_four_and_three(self, sprites):
        for golfer in range(6):
            frames = sprites.body_frames(golfer)
            assert frames[6].cpu_addr == frames[4].cpu_addr
            assert frames[7].cpu_addr == frames[3].cpu_addr

    def test_putt_frame_zero_reuses_the_swing_address_pose(self, sprites):
        for golfer in range(6):
            assert (
                sprites.body_frames(golfer, putt=True)[0].cpu_addr
                == sprites.body_frames(golfer)[1].cpu_addr
            )

    def test_no_frame_exceeds_the_eight_sprite_scanline_limit(self, sprites):
        for golfer in range(6):
            for putt in (False, True):
                for frame in sprites.body_frames(golfer, putt):
                    assert frame.peak_per_scanline() <= 8


class TestBuilds:
    def test_two_builds_split_the_six_golfers(self, sprites):
        assert [sprites.body_type(g) for g in range(6)] == [0, 1, 1, 0, 1, 1]

    def test_all_six_share_one_foot_line(self, sprites):
        for golfer in range(6):
            bottom = max(f.bounds()[3] for f in sprites.body_frames(golfer))
            assert bottom == 24, GOLFER_NAMES[golfer]

    def test_short_build_is_eight_pixels_shorter(self, sprites):
        heights = {}
        for golfer in range(6):
            frames = sprites.body_frames(golfer)
            top = min(f.bounds()[1] for f in frames)
            heights[golfer] = 24 - top
        assert heights[0] == heights[3] == 56
        assert all(heights[g] == 64 for g in (1, 2, 4, 5))

    def test_body_offsets_sit_on_the_eight_pixel_grid(self, sprites):
        off_grid = set()
        for golfer in range(6):
            for putt in (False, True):
                for frame in sprites.body_frames(golfer, putt):
                    for s in frame.sprites:
                        if s.dy % 8 or s.dx % 8:
                            off_grid.add((s.dy, s.dx))
        # the tall build's hat is nudged one pixel left on the top row
        assert off_grid == {(-40, -15), (-40, -7)}


class TestPaletteAndPriority:
    def test_each_golfer_gets_one_custom_colour(self, sprites):
        shirts = [sprites.body_palette(g)[1] for g in range(6)]
        assert shirts == [0x25, 0x2B, 0x28, 0x22, 0x26, 0x38]
        assert len(set(shirts)) == 6

    def test_only_billy_overrides_the_skin_tone(self, sprites):
        assert [sprites.body_palette(g)[3] for g in range(6)] == [0x36] * 5 + [0x27]

    def test_colour_zero_is_never_displayed(self, sprites):
        assert sprites.body_palette(0)[0] is None

    def test_body_draws_in_front_on_exactly_two_frames(self):
        assert BODY_IN_FRONT_FRAMES == (5, 11)


class TestClubNudge:
    def test_three_golfers_are_skipped_entirely(self, sprites):
        skipped = [g for g in range(6) if sprites.nudge_slot(g, 0, 0) is None]
        assert skipped == [0, 3, 5]

    def test_the_putter_never_gets_a_nudge(self, sprites):
        for golfer in range(6):
            assert sprites.nudge_slot(golfer, 15, 0) is None
            assert sprites.club_nudge(golfer, 15, 0) == (0, 0)

    def test_every_reachable_slot_lands_inside_the_table(self, sprites):
        slots = set()
        for golfer in range(6):
            for club in range(16):
                for frame in range(13):
                    slot = sprites.nudge_slot(golfer, club, frame)
                    if slot is not None:
                        slots.add(slot)
        # 3 golfers x 2 club classes x 11 frames, exactly filling $96B8-$96F9
        assert slots == set(range(66))

    def test_frames_six_and_seven_share_slots_with_four_and_three(self, sprites):
        for golfer in (1, 2, 4):
            assert sprites.nudge_slot(golfer, 0, 6) == sprites.nudge_slot(golfer, 0, 4)
            assert sprites.nudge_slot(golfer, 0, 7) == sprites.nudge_slot(golfer, 0, 3)


class TestClubAnimationPairing:
    def test_putting_requires_the_putter(self, sprites):
        with pytest.raises(ValueError, match="putting uses club 15"):
            sprites.club_frames(0, 0, putt=True)

    def test_the_putter_has_no_swing_frames(self, sprites):
        with pytest.raises(ValueError, match="no swing frames"):
            sprites.club_frames(0, 15, putt=False)

    def test_the_putter_set_is_the_tail_of_each_club_set(self, sprites):
        # 4 club groups x 13 swing frames + 6 putt frames = 58 per set
        frames = sprites.club_frames(5, 15, putt=True)
        assert len(frames) == 6


def _linked_and_source_positions(data, layer):
    """Walk a .aseprite and pair each linked cel's position with its source's."""
    import zlib

    frames = struct.unpack("<H", data[6:8])[0]
    pos, images, links = 128, {}, []
    for frame in range(frames):
        frame_size = struct.unpack("<I", data[pos : pos + 4])[0]
        count = struct.unpack("<I", data[pos + 12 : pos + 16])[0]
        p = pos + 16
        for _ in range(count):
            chunk_size, chunk_type = struct.unpack("<IH", data[p : p + 6])
            body = data[p + 6 : p + chunk_size]
            if chunk_type == 0x2005:
                li, x, y, _, cel_type, _ = struct.unpack("<HhhBHh", body[:11])
                if li == layer and cel_type == 2:
                    images[frame] = (x, y)
                elif li == layer and cel_type == 1:
                    link = struct.unpack("<H", body[16:18])[0]
                    links.append(((x, y), link))
            p += chunk_size
        pos += frame_size
    return [(xy, images[link]) for xy, link in links]


class TestExporter:
    def test_export_produces_a_readable_file_and_sidecar(self, rom, sprites, tmp_path):
        from tools.golfer_export import canvas_bounds, export_golfer

        bounds = canvas_bounds(sprites)
        path, meta = export_golfer(rom, sprites, 0, False, bounds, str(tmp_path))

        data = Path(path).read_bytes()
        size, magic, frames = struct.unpack("<IHH", data[:8])
        assert magic == 0xA5E0
        assert size == len(data)
        assert frames == 13

        sidecar = json.loads((tmp_path / "mario_swing.json").read_text())
        assert sidecar["name"] == "Mario"
        assert sidecar["body_in_front_frames"] == [5, 11]
        assert sidecar["frames"][6]["body_linked_to"] == 4
        assert sidecar["frames"][7]["body_linked_to"] == 3
        assert sidecar["canvas"]["origin_x"] > 0

    def test_every_swing_club_group_gets_its_own_layer(self, rom, sprites, tmp_path):
        from tools.golfer_export import canvas_bounds, export_golfer

        _, meta = export_golfer(
            rom, sprites, 0, False, canvas_bounds(sprites), str(tmp_path)
        )
        assert meta["clubs"] == [0, 4, 8, 12]
        # body + four club layers + guides
        assert len(meta["layers"]) == 6
        # clubs 4-14 share one nudge class, so three layers cannot move apart
        shared = meta["nudge_classes_shared_by"]
        assert len(shared) == 1 and len(next(iter(shared.values()))) == 3

    def test_palette_offers_every_nes_colour_once(self, rom, sprites, tmp_path):
        from golf.core.palettes import (
            NES_BLACK_ENTRIES,
            NES_CANONICAL_BLACK,
            NES_SYSTEM_PALETTE,
        )
        from tools.golfer_export import PALETTE_SIZE, build_palette, nes_index

        palette = build_palette([0x25, 0x0F, 0x36], [0x17, 0x0F, 0x30])
        assert len(palette) == PALETTE_SIZE
        assert palette[0][3] == 0, "index 0 must stay transparent"
        for value in range(64):
            entry = palette[nes_index(value)]
            expected = NES_SYSTEM_PALETTE[
                NES_CANONICAL_BLACK if value in NES_BLACK_ENTRIES else value
            ]
            assert entry[:3] == expected
        assert "body 1" in palette[nes_index(0x25)][4]
        assert "club 1" in palette[nes_index(0x17)][4]

    def test_the_spare_blacks_collapse_onto_one_entry(self):
        from golf.core.palettes import NES_BLACK_ENTRIES, NES_CANONICAL_BLACK
        from tools.golfer_export import NES_ENTRIES, nes_index

        black = nes_index(NES_CANONICAL_BLACK)
        for value in NES_BLACK_ENTRIES:
            assert nes_index(value) == black, f"${value:02X} should fold onto $0F"
        assert sum(1 for v in NES_ENTRIES if v in NES_BLACK_ENTRIES) == 1
        assert len(NES_ENTRIES) == 55

    def test_no_two_palette_entries_share_a_colour_except_white(self):
        # $20 and $30 are both white in this palette rendering; every other
        # duplicate has been folded away.
        from tools.golfer_export import NES_ENTRIES
        from golf.core.palettes import NES_SYSTEM_PALETTE

        seen = {}
        duplicates = []
        for value in NES_ENTRIES:
            rgb = NES_SYSTEM_PALETTE[value]
            if rgb in seen:
                duplicates.append((seen[rgb], value))
            seen[rgb] = value
        assert duplicates == [(0x20, 0x30)]

    def test_nes_by_index_round_trips(self):
        from tools.golfer_export import NES_ENTRIES, nes_by_index, nes_index

        table = nes_by_index()
        assert table[0] is None, "transparent"
        for value in NES_ENTRIES:
            assert table[nes_index(value)] == value

    def test_body_pixels_use_the_golfer_s_own_nes_indices(self, rom, sprites, tmp_path):
        from tools.golfer_export import canvas_bounds, export_golfer, nes_index

        _, meta = export_golfer(
            rom, sprites, 0, False, canvas_bounds(sprites), str(tmp_path)
        )
        expected = [nes_index(v) for v in meta["body_palette_nes"][1:]]
        assert meta["palette"]["body_indices"] == expected
        table = meta["palette"]["nes_by_index"]
        for index, nes in zip(expected, meta["body_palette_nes"][1:]):
            assert table[index] == nes

    def test_linked_body_cels_repeat_the_source_position(self, rom, sprites, tmp_path):
        from tools.golfer_export import canvas_bounds, export_golfer

        path, _ = export_golfer(
            rom, sprites, 0, False, canvas_bounds(sprites), str(tmp_path)
        )
        data = Path(path).read_bytes()
        positions = _linked_and_source_positions(data, layer=0)
        assert positions, "expected linked body cels"
        for linked_xy, source_xy in positions:
            assert linked_xy == source_xy

    def test_putt_export_uses_the_putter(self, rom, sprites, tmp_path):
        from tools.golfer_export import canvas_bounds, export_golfer

        bounds = canvas_bounds(sprites)
        _, meta = export_golfer(rom, sprites, 5, True, bounds, str(tmp_path))
        assert meta["clubs"] == [15]
        assert len(meta["frames"]) == 6

    def test_canvas_fits_every_golfer_and_both_animations(self, sprites):
        from tools.golfer_export import canvas_bounds

        x0, y0, x1, y1 = canvas_bounds(sprites)
        for golfer in range(6):
            for putt in (False, True):
                for frame in sprites.body_frames(golfer, putt):
                    bx0, by0, bx1, by1 = frame.bounds()
                    assert x0 <= bx0 and bx1 <= x1
                    assert y0 <= by0 and by1 <= y1
