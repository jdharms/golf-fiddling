"""Unit tests for the .aseprite writer.

The tests parse the bytes back with an independent reader rather than trusting
the writer's own structures, because the failure mode that matters is a file
Aseprite refuses to open - a wrong field offset or a size that does not add up.
"""

import struct
import zlib

import pytest

from golf.core.aseprite import (
    LAYER_EDITABLE,
    LAYER_LOCK_MOVEMENT,
    LAYER_VISIBLE,
    AsepriteFile,
    Cel,
    Frame,
    Layer,
    LinkedCel,
)


def parse(data):
    """A deliberately literal reader, offsets taken from the format spec."""
    size, magic, frames, width, height, depth = struct.unpack("<IHHHHH", data[:14])
    assert magic == 0xA5E0
    assert size == len(data), "header size field must match the real length"
    transparent = data[28]
    ncolors = struct.unpack("<H", data[32:34])[0]
    grid = struct.unpack("<hhHH", data[36:44])

    pos = 128
    palette, layers, all_frames = {}, [], []
    for _ in range(frames):
        frame_size, frame_magic, _, duration = struct.unpack(
            "<IHHH", data[pos : pos + 10]
        )
        chunk_count = struct.unpack("<I", data[pos + 12 : pos + 16])[0]
        assert frame_magic == 0xF1FA
        p, end = pos + 16, pos + frame_size
        cels = []
        for _ in range(chunk_count):
            chunk_size, chunk_type = struct.unpack("<IH", data[p : p + 6])
            body = data[p + 6 : p + chunk_size]
            if chunk_type == 0x2019:
                count, first, last = struct.unpack("<III", body[:12])
                q = 20
                for i in range(first, last + 1):
                    flags, r, g, b, a = struct.unpack("<HBBBB", body[q : q + 6])
                    q += 6
                    name = None
                    if flags & 1:
                        length = struct.unpack("<H", body[q : q + 2])[0]
                        name = body[q + 2 : q + 2 + length].decode()
                        q += 2 + length
                    palette[i] = (r, g, b, a, name)
            elif chunk_type == 0x2004:
                flags = struct.unpack("<H", body[:2])[0]
                name_len = struct.unpack("<H", body[16:18])[0]
                layers.append((body[18 : 18 + name_len].decode(), flags))
            elif chunk_type == 0x2005:
                layer, x, y, _, cel_type, _ = struct.unpack("<HhhBHh", body[:11])
                rest = body[16:]
                if cel_type == 2:
                    cw, ch = struct.unpack("<HH", rest[:4])
                    pixels = zlib.decompress(rest[4:])
                    cels.append(("image", layer, x, y, cw, ch, pixels))
                elif cel_type == 1:
                    cels.append(
                        ("linked", layer, struct.unpack("<H", rest[:2])[0], x, y)
                    )
            p += chunk_size
        assert p == end, "chunk sizes must exactly fill the frame"
        pos = end
        all_frames.append((duration, cels))
    assert pos == len(data)
    return dict(
        width=width,
        height=height,
        depth=depth,
        frames=frames,
        transparent=transparent,
        ncolors=ncolors,
        grid=grid,
        palette=palette,
        layers=layers,
        cels=all_frames,
    )


@pytest.fixture
def sample():
    ase = AsepriteFile(
        width=8,
        height=4,
        palette=[(0, 0, 0, 0), (255, 0, 0, 255), (0, 128, 255, 255)],
        grid=(2, 3, 8, 8),
    )
    ase.layers = [
        Layer("body", LAYER_VISIBLE | LAYER_EDITABLE),
        Layer("guides", LAYER_VISIBLE | LAYER_LOCK_MOVEMENT),
    ]
    ase.frames = [
        Frame(120, [Cel(0, 1, 2, 2, 1, bytes([1, 2]))]),
        Frame(120, [LinkedCel(0, 0, 1, 2)]),
    ]
    return ase


class TestStructure:
    def test_header_is_128_bytes_and_indexed(self, sample):
        parsed = parse(sample.to_bytes())
        assert parsed["depth"] == 8
        assert parsed["width"] == 8 and parsed["height"] == 4
        assert parsed["frames"] == 2

    def test_palette_round_trips(self, sample):
        parsed = parse(sample.to_bytes())
        assert parsed["ncolors"] == 3
        assert parsed["palette"][1][:4] == (255, 0, 0, 255)
        assert parsed["palette"][2][:4] == (0, 128, 255, 255)

    def test_index_zero_is_transparent(self, sample):
        assert parse(sample.to_bytes())["transparent"] == 0

    def test_named_entries_round_trip_and_keep_later_ones_aligned(self):
        ase = AsepriteFile(
            width=1,
            height=1,
            palette=[
                (0, 0, 0, 0),
                (1, 2, 3, 255, "$16 - body 1"),
                (4, 5, 6, 255),
                (7, 8, 9, 255, "guide"),
            ],
        )
        ase.layers = [Layer("l")]
        ase.frames = [Frame(cels=[Cel(0, 0, 0, 1, 1, bytes([1]))])]
        parsed = parse(ase.to_bytes())["palette"]
        assert parsed[1] == (1, 2, 3, 255, "$16 - body 1")
        assert parsed[2] == (4, 5, 6, 255, None)
        assert parsed[3] == (7, 8, 9, 255, "guide")

    def test_grid_is_written_where_the_spec_puts_it(self, sample):
        assert parse(sample.to_bytes())["grid"] == (2, 3, 8, 8)

    def test_layers_keep_their_names_and_flags(self, sample):
        layers = parse(sample.to_bytes())["layers"]
        assert layers[0] == ("body", LAYER_VISIBLE | LAYER_EDITABLE)
        assert layers[1] == ("guides", LAYER_VISIBLE | LAYER_LOCK_MOVEMENT)
        assert not layers[1][1] & LAYER_EDITABLE


class TestCels:
    def test_image_cel_keeps_position_and_pixels(self, sample):
        kind, layer, x, y, w, h, pixels = parse(sample.to_bytes())["cels"][0][1][0]
        assert kind == "image"
        assert (layer, x, y, w, h) == (0, 1, 2, 2, 1)
        assert pixels == bytes([1, 2])

    def test_linked_cel_points_at_the_source_frame(self, sample):
        cel = parse(sample.to_bytes())["cels"][1][1][0]
        assert cel[:3] == ("linked", 0, 0)

    def test_linked_cel_carries_its_own_position(self, sample):
        # A linked cel shares the image but not the position field, so leaving
        # x/y at zero drops the image in the canvas corner.
        _, _, _, x, y = parse(sample.to_bytes())["cels"][1][1][0]
        assert (x, y) == (1, 2)

    def test_layer_chunks_only_appear_in_the_first_frame(self, sample):
        data = sample.to_bytes()
        assert len(parse(data)["layers"]) == 2

    def test_mismatched_pixel_count_is_rejected(self):
        with pytest.raises(ValueError):
            Cel(0, 0, 0, 4, 4, bytes(3))


class TestReader:
    """The return leg: a file that has been through Aseprite and back.

    Round-tripping the writer is the cheap half.  The half that matters is
    tolerating what a real editor adds - chunks this module never writes, and
    layers the artist created, hid or reordered.
    """

    def test_round_trip_preserves_canvas_palette_and_grid(self, sample):
        back = AsepriteFile.from_bytes(sample.to_bytes())
        assert (back.width, back.height) == (sample.width, sample.height)
        assert back.transparent_index == sample.transparent_index
        assert back.grid == sample.grid
        assert len(back.palette) == len(sample.palette)
        assert back.palette[1][:4] == sample.palette[1][:4]

    def test_round_trip_preserves_layers_and_cels(self, sample):
        back = AsepriteFile.from_bytes(sample.to_bytes())
        assert [layer.name for layer in back.layers] == [
            layer.name for layer in sample.layers
        ]
        cel = back.frames[0].cels[0]
        assert (cel.layer, cel.x, cel.y, cel.width, cel.height) == (0, 1, 2, 2, 1)
        assert cel.pixels == bytes([1, 2])

    def test_palette_entry_names_survive(self):
        ase = AsepriteFile(
            width=1,
            height=1,
            palette=[(0, 0, 0, 0, "transparent"), (255, 0, 0, 255, "$16 - red")],
            layers=[Layer("art")],
            frames=[Frame(cels=[Cel(0, 0, 0, 1, 1, bytes([1]))])],
        )
        assert AsepriteFile.from_bytes(ase.to_bytes()).palette[1][4] == "$16 - red"

    def test_unknown_chunks_are_skipped_not_parsed(self, sample):
        """Aseprite writes a colour-profile chunk this module knows nothing of."""
        data = bytearray(sample.to_bytes())
        extra = struct.pack("<IH", 6 + 16, 0x2007) + bytes(16)
        insert = 128 + 16
        data[insert:insert] = extra
        # Grow the frame's size and chunk counts to match the injected chunk.
        frame_size = struct.unpack_from("<I", data, 128)[0] + len(extra)
        struct.pack_into("<I", data, 128, frame_size)
        struct.pack_into(
            "<H", data, 128 + 6, struct.unpack_from("<H", data, 128 + 6)[0] + 1
        )
        struct.pack_into(
            "<I", data, 128 + 12, struct.unpack_from("<I", data, 128 + 12)[0] + 1
        )
        struct.pack_into("<I", data, 0, len(data))

        back = AsepriteFile.from_bytes(bytes(data))
        assert [layer.name for layer in back.layers] == [
            layer.name for layer in sample.layers
        ]
        assert back.frames[0].cels[0].pixels == bytes([1, 2])

    def test_composite_paints_later_layers_over_earlier_ones(self):
        ase = AsepriteFile(
            width=2,
            height=1,
            palette=[(0, 0, 0, 0), (1, 1, 1, 255), (2, 2, 2, 255)],
            layers=[Layer("under"), Layer("over")],
            frames=[
                Frame(
                    cels=[
                        Cel(0, 0, 0, 2, 1, bytes([1, 1])),
                        Cel(1, 1, 0, 1, 1, bytes([2])),
                    ]
                )
            ],
        )
        assert AsepriteFile.from_bytes(ase.to_bytes()).composite() == bytearray([1, 2])

    def test_composite_skips_hidden_layers(self):
        ase = AsepriteFile(
            width=1,
            height=1,
            palette=[(0, 0, 0, 0), (1, 1, 1, 255), (2, 2, 2, 255)],
            layers=[Layer("under"), Layer("hidden", flags=LAYER_EDITABLE)],
            frames=[
                Frame(
                    cels=[
                        Cel(0, 0, 0, 1, 1, bytes([1])),
                        Cel(1, 0, 0, 1, 1, bytes([2])),
                    ]
                )
            ],
        )
        assert AsepriteFile.from_bytes(ase.to_bytes()).composite() == bytearray([1])

    def test_composite_resolves_a_linked_cel_to_its_source_image(self, sample):
        back = AsepriteFile.from_bytes(sample.to_bytes())
        assert back.composite(1) == back.composite(0)

    def test_a_non_indexed_file_is_refused(self, sample):
        data = bytearray(sample.to_bytes())
        struct.pack_into("<H", data, 12, 32)  # RGBA
        with pytest.raises(ValueError, match="indexed"):
            AsepriteFile.from_bytes(bytes(data))
