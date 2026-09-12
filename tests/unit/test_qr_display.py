"""
The display layer, checked through simulated video memory.

`sim.Machine` models enough of the PPU to capture what the routine actually
draws, so these tests read the finished screen out of VRAM rather than trusting
the code that wrote it — including pulling the QR back out of the nametable and
CHR the 6502 uploaded and handing it to a real decoder.

The dismissal gesture is driven by a per-frame callback: the `WaitForVblank`
stub ticks the harness, and the test sets the controller bytes the way the NMI
would have.
"""

import random

import pytest

from golf.qr import encoder, nes, sample, tables
from golf.qr.decode import DECODERS
from golf.qr.payload import RoundPayload
from golf.qr.port import (
    HOLD_CAPTION,
    PLAYER_CAPTION,
    SCAN_CAPTION,
    build,
    caption_address,
    caption_tiles,
    layout,
)
from golf.qr.port.sim import Machine
from golf.qr.render import render_screen

#: Up + Select + A.
DISMISS = layout.DISMISS_MASK

#: Where the stub for `LoadCompressedGraphics` records its inline arguments.
GRAPHICS_CALL = 0x5FF0


@pytest.fixture(scope="module")
def program():
    return build()


@pytest.fixture(scope="module")
def round_and_key() -> tuple[RoundPayload, bytes]:
    rng = random.Random(2024)
    return sample.random_round(rng), sample.random_key(rng)


def staged(program, round_payload: RoundPayload, key: bytes, slot: int = 0) -> Machine:
    machine = Machine(program)
    machine.write(program.symbol("QrSeedId"), round_payload.seed_id)
    ids = [bytes(4), bytes(4)]
    keys = [bytes(8), bytes(8)]
    ids[slot] = round_payload.player_id
    keys[slot] = key
    machine.write(program.symbol("QrPlayerId"), b"".join(ids))
    machine.write(program.symbol("QrMacKey"), b"".join(keys))
    machine.set_round(
        [(hole.strokes, hole.putts) for hole in round_payload.holes],
        player=slot,
        player_count=1 if slot else 0,
    )
    return machine


def drawn(program, round_payload: RoundPayload, key: bytes, slot: int = 0) -> Machine:
    """A machine with one code built and its screen drawn."""
    machine = staged(program, round_payload, key, slot)
    machine.call("QrBuildCode", a=slot)
    machine.poke(layout.DISPLAY_STATE, slot)  # QrDisplaySlot, for the caption
    machine.call("QrDrawScreen")
    return machine


def code_block(nametable: bytes) -> bytes:
    """The 19x19 tile block, read back out of the drawn nametable."""
    return bytes(
        nametable[(layout.SCREEN_TILE_ROW + row) * 32 + layout.SCREEN_TILE_COL + col]
        for row in range(nes.TILE_COUNT)
        for col in range(nes.TILE_COUNT)
    )


def decoded_url(machine: Machine) -> str | None:
    """Read the code out of video memory and put it through a real decoder."""
    rows = nes.render_modules(
        machine.bus.pattern(layout.CHR_DEST, nes.QR_TILE_COUNT),
        code_block(machine.bus.nametable()),
        base_tile=layout.TILE_BASE,
    )
    matrix = encoder.QrMatrix(bytearray(sum(rows, [])), 0)
    return DECODERS["zxing"](render_screen(matrix))


# --------------------------------------------------------------------------
# What lands in video memory
# --------------------------------------------------------------------------


def test_the_chr_tiles_are_uploaded_where_the_nametable_expects_them(
    program, round_and_key
) -> None:
    machine = drawn(program, *round_and_key)
    assert machine.bus.pattern(layout.CHR_DEST, 16) == tables.chr_table()
    assert layout.TILE_BASE == (layout.CHR_DEST - 0x1000) // 16


def test_the_palette_is_white_ground_and_black_ink(program, round_and_key) -> None:
    machine = drawn(program, *round_and_key)
    palette = machine.bus.palette()
    assert palette[0] == 0x30  # universal backdrop: white, so quiet zone is free
    assert set(palette[:16]) == {0x30, 0x0F}
    for index in range(0, 16, 4):
        assert palette[index : index + 4] == bytes([0x30, 0x0F, 0x0F, 0x0F])


def test_the_screen_is_blank_apart_from_the_code_and_captions(
    program, round_and_key
) -> None:
    machine = drawn(program, *round_and_key)
    nametable = machine.bus.nametable()

    caption_cells = set()
    for row, text, extra in (
        (layout.PLAYER_CAPTION_ROW, PLAYER_CAPTION, 1),
        (layout.SCAN_CAPTION_ROW, SCAN_CAPTION, 0),
        (layout.HOLD_CAPTION_ROW, HOLD_CAPTION, 0),
    ):
        width = len(text) + extra
        start = caption_address(row, width) - 0x2000
        caption_cells.update(range(start, start + width))

    code_cells = {
        (layout.SCREEN_TILE_ROW + row) * 32 + layout.SCREEN_TILE_COL + col
        for row in range(nes.TILE_COUNT)
        for col in range(nes.TILE_COUNT)
    }

    for index in range(960):
        if index in caption_cells or index in code_cells:
            continue
        assert nametable[index] == layout.TILE_BASE, f"tile {index} is not blank"

    assert set(nametable[960:1024]) == {0x00}, "attributes must all be palette 0"


def test_the_code_block_matches_the_nametable_in_ram(program, round_and_key) -> None:
    machine = drawn(program, *round_and_key)
    assert code_block(machine.bus.nametable()) == machine.read(layout.NAMETABLE, 361)


def test_the_quiet_zone_is_wider_than_the_spec_asks(program, round_and_key) -> None:
    """Nothing may be drawn within four modules of the code."""
    machine = drawn(program, *round_and_key)
    nametable = machine.bus.nametable()
    top = layout.SCREEN_TILE_ROW
    bottom = top + nes.TILE_COUNT - 1
    for row in range(top - 2, top):
        assert set(nametable[row * 32 : row * 32 + 32]) == {layout.TILE_BASE}
    for row in range(bottom + 1, bottom + 3):
        assert set(nametable[row * 32 : row * 32 + 32]) == {layout.TILE_BASE}
    assert top - 2 > layout.PLAYER_CAPTION_ROW
    assert bottom + 2 < layout.SCAN_CAPTION_ROW


# --------------------------------------------------------------------------
# End to end, out of video memory
# --------------------------------------------------------------------------


def test_the_screen_in_video_memory_decodes_to_the_round(
    program, round_and_key
) -> None:
    round_payload, key = round_and_key
    machine = drawn(program, round_payload, key)
    assert decoded_url(machine) == round_payload.to_url(key)


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------


@pytest.mark.parametrize("slot", [0, 1])
def test_the_player_caption_names_the_slot(program, round_and_key, slot: int) -> None:
    round_payload, key = round_and_key
    machine = drawn(program, round_payload, key, slot=slot)
    nametable = machine.bus.nametable()
    width = len(PLAYER_CAPTION) + 1
    start = caption_address(layout.PLAYER_CAPTION_ROW, width) - 0x2000
    expected = caption_tiles(PLAYER_CAPTION) + [slot + 1]
    assert list(nametable[start : start + width]) == expected


def test_the_fixed_captions_are_drawn(program, round_and_key) -> None:
    machine = drawn(program, *round_and_key)
    nametable = machine.bus.nametable()
    for row, text in (
        (layout.SCAN_CAPTION_ROW, SCAN_CAPTION),
        (layout.HOLD_CAPTION_ROW, HOLD_CAPTION),
    ):
        tiles = caption_tiles(text)
        start = caption_address(row, len(tiles)) - 0x2000
        assert list(nametable[start : start + len(tiles)]) == tiles


def test_every_caption_glyph_exists_in_the_card_font() -> None:
    """The title font is A-Z, 0-9 and space; anything else would draw garbage."""
    for text in (PLAYER_CAPTION, SCAN_CAPTION, HOLD_CAPTION):
        for tile in caption_tiles(text):
            assert tile <= 0x24


# --------------------------------------------------------------------------
# Rendering state
# --------------------------------------------------------------------------


def test_rendering_is_off_while_drawing_and_back_on_afterwards(
    program, round_and_key
) -> None:
    machine = drawn(program, *round_and_key)
    assert machine.bus.ppu_mask == layout.PPU_MASK_VALUE
    assert machine.peek(layout.PPU_MASK_TARGET) == layout.PPU_MASK_VALUE
    assert machine.peek(layout.PPU_CTRL_CACHE) == layout.PPU_CTRL_VALUE
    for address in (
        layout.SCROLL_X,
        layout.SCROLL_Y,
        layout.NAMETABLE_X,
        layout.NAMETABLE_Y,
    ):
        assert machine.peek(address) == 0


def test_the_card_font_is_reloaded_rather_than_assumed(program, round_and_key) -> None:
    machine = drawn(program, *round_and_key)
    assert machine.read(GRAPHICS_CALL, 3) == bytes(
        [
            layout.CARD_FONT_BANK,
            layout.CARD_FONT_TABLE & 0xFF,
            layout.CARD_FONT_TABLE >> 8,
        ]
    )


def test_all_sprites_are_parked_off_screen(program, round_and_key) -> None:
    machine = drawn(program, *round_and_key)
    assert set(machine.read(0x0200, 256)) == {0xF0}


# --------------------------------------------------------------------------
# Dismissal
# --------------------------------------------------------------------------


def run_dismissal(program, inputs, limit_frames: int = 2000) -> int:
    """Run the wait loop with `inputs(frame) -> (pad1, pad2)`; return frames."""
    machine = Machine(program)

    def on_frame(frame: int) -> None:
        if frame > limit_frames:
            raise AssertionError("dismissal never returned")
        pad1, pad2 = inputs(frame)
        machine.poke(layout.CONTROLLER_CURRENT, pad1)
        machine.poke(layout.CONTROLLER_CURRENT + 1, pad2)

    machine.call("QrWaitForDismiss", on_frame=on_frame)
    return machine.bus.frames


def test_the_gesture_must_be_held_for_three_seconds(program) -> None:
    frames = run_dismissal(program, lambda frame: (DISMISS, 0))
    assert frames == layout.HOLD_FRAMES
    assert layout.HOLD_FRAMES == 180


def test_letting_go_resets_the_count(program) -> None:
    def inputs(frame: int) -> tuple[int, int]:
        if frame == 100:
            return 0, 0
        return DISMISS, 0

    frames = run_dismissal(program, inputs)
    assert frames == 100 + layout.HOLD_FRAMES


def test_an_incomplete_gesture_never_dismisses(program) -> None:
    for buttons in (0x80, 0x20, 0x08, 0x88, 0xA0, 0x28, 0x00):
        with pytest.raises(AssertionError, match="never returned"):
            run_dismissal(program, lambda frame, b=buttons: (b, 0), limit_frames=400)


def test_extra_buttons_do_not_break_the_gesture(program) -> None:
    frames = run_dismissal(program, lambda frame: (DISMISS | 0x40 | 0x01, 0))
    assert frames == layout.HOLD_FRAMES


def test_either_controller_can_dismiss(program) -> None:
    frames = run_dismissal(program, lambda frame: (0, DISMISS))
    assert frames == layout.HOLD_FRAMES


# --------------------------------------------------------------------------
# Both players
# --------------------------------------------------------------------------


def test_one_player_gets_one_screen(program, round_and_key) -> None:
    round_payload, key = round_and_key
    machine = staged(program, round_payload, key)
    machine.poke(layout.PLAYER_COUNT, 0)
    machine.call(
        "QrShowCodes",
        on_frame=lambda frame: machine.poke(layout.CONTROLLER_CURRENT, DISMISS),
    )
    assert machine.bus.frames == layout.HOLD_FRAMES
    assert decoded_url(machine) == round_payload.to_url(key)


def test_two_players_get_a_screen_each(program) -> None:
    rng = random.Random(77)
    first = sample.random_round(rng)
    second = sample.random_round(rng)
    keys = [sample.random_key(rng), sample.random_key(rng)]

    machine = Machine(program)
    machine.write(program.symbol("QrSeedId"), first.seed_id)
    machine.write(program.symbol("QrPlayerId"), first.player_id + second.player_id)
    machine.write(program.symbol("QrMacKey"), keys[0] + keys[1])
    machine.set_round(
        [(hole.strokes, hole.putts) for hole in first.holes], player=0, player_count=1
    )
    machine.set_round(
        [(hole.strokes, hole.putts) for hole in second.holes], player=1, player_count=1
    )

    screens: list[str | None] = []

    def on_frame(frame: int) -> None:
        machine.poke(layout.CONTROLLER_CURRENT, DISMISS)
        if frame in (layout.HOLD_FRAMES, layout.HOLD_FRAMES * 2):
            screens.append(decoded_url(machine))

    machine.call("QrShowCodes", on_frame=on_frame)

    expected_second = RoundPayload(
        seed_id=first.seed_id,
        player_id=second.player_id,
        holes=second.holes,
        player_slot=1,
    ).to_url(keys[1])
    assert screens == [first.to_url(keys[0]), expected_second]
    assert machine.bus.frames == layout.HOLD_FRAMES * 2
