"""
A minimal reader and writer for Aseprite's `.aseprite` / `.ase` format.

Only what a layered reference export needs: indexed colour, one palette, named
layers with flags, and one compressed cel per layer per frame.  Cel position is
part of the format, which is what lets a layer be *moved* by an artist and read
back as an offset.

`read` is the return leg: a file that has been through Aseprite carries chunks
this module never writes (colour profile, tags, user data, the deprecated
palette chunks), and the artist may have added, hidden or reordered layers.
Unknown chunks are skipped by their length rather than parsed, so the reader
only has to understand the four chunk types that carry pixels.

Format reference: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md
"""

import struct
import zlib
from dataclasses import dataclass, field

ASE_MAGIC = 0xA5E0
FRAME_MAGIC = 0xF1FA

CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_PALETTE = 0x2019

# Layer flags
LAYER_VISIBLE = 1
LAYER_EDITABLE = 2
LAYER_LOCK_MOVEMENT = 4

# Layer types.  A group holds no pixels of its own; its children are listed
# separately at a deeper child level, so compositing just skips it.
LAYER_TYPE_GROUP = 1

CEL_RAW = 0
CEL_LINKED = 1
CEL_COMPRESSED = 2


@dataclass
class Layer:
    name: str
    flags: int = LAYER_VISIBLE | LAYER_EDITABLE
    opacity: int = 255
    layer_type: int = 0

    @property
    def visible(self) -> bool:
        return bool(self.flags & LAYER_VISIBLE)


@dataclass
class Cel:
    """One layer's pixels in one frame.

    `x`/`y` are the cel's position on the canvas.  Aseprite preserves it when
    the artist moves the layer, so a round-trip can recover the offset.
    """

    layer: int
    x: int
    y: int
    width: int
    height: int
    pixels: bytes  # width*height palette indices

    def __post_init__(self) -> None:
        if len(self.pixels) != self.width * self.height:
            raise ValueError(
                f"cel is {self.width}x{self.height} but got {len(self.pixels)} pixels"
            )


@dataclass
class LinkedCel:
    """A cel that shares another frame's image.

    The game reuses metasprite pointers between frames - swing frames 6 and 7
    are literally frames 4 and 3 - and a linked cel says so in a way Aseprite
    honours: editing one edits both.

    A linked cel still carries its own position in the file, so `x`/`y` must
    repeat the source cel's position.  Leaving them at the default drops the
    image in the canvas corner on any reader that does not inherit position
    from the link.
    """

    layer: int
    frame_link: int
    x: int = 0
    y: int = 0


@dataclass
class Frame:
    duration_ms: int = 100
    cels: list = field(default_factory=list)  # Cel | LinkedCel


@dataclass
class AsepriteFile:
    width: int
    height: int
    # (r, g, b, a) or (r, g, b, a, name) - Aseprite shows the name on hover
    palette: list[tuple]
    layers: list[Layer] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    transparent_index: int = 0
    grid: tuple[int, int, int, int] = (0, 0, 16, 16)

    def _chunk(self, chunk_type: int, body: bytes) -> bytes:
        return struct.pack("<IH", len(body) + 6, chunk_type) + body

    def _string(self, text: str) -> bytes:
        raw = text.encode("utf-8")
        return struct.pack("<H", len(raw)) + raw

    def _palette_chunk(self) -> bytes:
        body = struct.pack("<III", len(self.palette), 0, len(self.palette) - 1)
        body += b"\x00" * 8
        for entry in self.palette:
            r, g, b, a = entry[:4]
            name = entry[4] if len(entry) > 4 else None
            if name:
                body += struct.pack("<HBBBB", 1, r, g, b, a) + self._string(name)
            else:
                body += struct.pack("<HBBBB", 0, r, g, b, a)
        return self._chunk(CHUNK_PALETTE, body)

    def _layer_chunk(self, layer: Layer) -> bytes:
        body = struct.pack(
            "<HHHHHHB", layer.flags, layer.layer_type, 0, 0, 0, 0, layer.opacity
        )
        body += b"\x00" * 3
        body += self._string(layer.name)
        return self._chunk(CHUNK_LAYER, body)

    def _cel_chunk(self, cel) -> bytes:
        if isinstance(cel, LinkedCel):
            body = struct.pack("<HhhBHh", cel.layer, cel.x, cel.y, 255, 1, 0)
            body += b"\x00" * 5
            body += struct.pack("<H", cel.frame_link)
            return self._chunk(CHUNK_CEL, body)
        body = struct.pack("<HhhBHh", cel.layer, cel.x, cel.y, 255, 2, 0)
        body += b"\x00" * 5
        body += struct.pack("<HH", cel.width, cel.height)
        body += zlib.compress(bytes(cel.pixels), 9)
        return self._chunk(CHUNK_CEL, body)

    def to_bytes(self) -> bytes:
        frames_data = []
        for index, frame in enumerate(self.frames):
            chunks = []
            if index == 0:
                chunks.append(self._palette_chunk())
                chunks += [self._layer_chunk(layer) for layer in self.layers]
            chunks += [self._cel_chunk(cel) for cel in frame.cels]
            body = b"".join(chunks)
            header = struct.pack(
                "<IHHH2sI",
                len(body) + 16,
                FRAME_MAGIC,
                min(len(chunks), 0xFFFF),
                frame.duration_ms,
                b"\x00\x00",
                len(chunks),
            )
            frames_data.append(header + body)

        payload = b"".join(frames_data)
        gx, gy, gw, gh = self.grid
        header = struct.pack(
            "<IHHHHHIH II B3s HBB hhHH 84s",
            128 + len(payload),
            ASE_MAGIC,
            len(self.frames),
            self.width,
            self.height,
            8,  # indexed
            1,  # layer opacity is valid
            100,  # deprecated speed
            0,
            0,
            self.transparent_index,
            b"\x00\x00\x00",
            len(self.palette) & 0xFFFF,
            1,
            1,
            gx,
            gy,
            gw,
            gh,
            b"\x00" * 84,
        )
        return header + payload

    def write(self, path) -> None:
        with open(path, "wb") as handle:
            handle.write(self.to_bytes())

    # ---- reading ----------------------------------------------------------

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AsepriteFile":
        magic = struct.unpack_from("<H", raw, 4)[0]
        if magic != ASE_MAGIC:
            raise ValueError(f"not an Aseprite file (magic {magic:#06x})")
        frame_count, width, height, depth = struct.unpack_from("<HHHH", raw, 6)
        if depth != 8:
            raise ValueError(f"only indexed (8bpp) files are supported, got {depth}bpp")
        transparent = raw[28]
        grid = struct.unpack_from("<hhHH", raw, 36)

        ase = cls(
            width=width,
            height=height,
            palette=[],
            transparent_index=transparent,
            grid=grid,
        )

        offset = 128
        for _ in range(frame_count):
            frame_size, frame_magic = struct.unpack_from("<IH", raw, offset)
            if frame_magic != FRAME_MAGIC:
                raise ValueError(f"bad frame magic {frame_magic:#06x} at {offset}")
            old_count, duration = struct.unpack_from("<HH", raw, offset + 6)
            new_count = struct.unpack_from("<I", raw, offset + 12)[0]
            frame = Frame(duration_ms=duration)

            pos = offset + 16
            for _ in range(new_count or old_count):
                chunk_size, chunk_type = struct.unpack_from("<IH", raw, pos)
                body = raw[pos + 6 : pos + chunk_size]
                if chunk_type == CHUNK_PALETTE:
                    ase.palette = _parse_palette(body, ase.palette)
                elif chunk_type == CHUNK_LAYER:
                    ase.layers.append(_parse_layer(body))
                elif chunk_type == CHUNK_CEL:
                    frame.cels.append(_parse_cel(body))
                pos += chunk_size

            ase.frames.append(frame)
            offset += frame_size
        return ase

    @classmethod
    def read(cls, path) -> "AsepriteFile":
        with open(path, "rb") as handle:
            return cls.from_bytes(handle.read())

    def composite(self, frame: int = 0) -> bytearray:
        """Flatten one frame to `width*height` palette indices.

        Visible layers are drawn in file order (bottom to top); the transparent
        index does not paint.  Blend modes and per-layer opacity are ignored -
        an indexed reference export has no meaningful notion of either, and a
        file that uses them is not one this pipeline can read back anyway.
        """
        canvas = bytearray([self.transparent_index]) * (self.width * self.height)
        for cel in self.frames[frame].cels:
            layer = self.layers[cel.layer] if cel.layer < len(self.layers) else None
            if layer is not None and not layer.visible:
                continue
            source = cel
            if isinstance(cel, LinkedCel):
                source = self._linked_source(cel)
            for row in range(source.height):
                y = source.y + row
                if not 0 <= y < self.height:
                    continue
                line = source.pixels[row * source.width : (row + 1) * source.width]
                for column, value in enumerate(line):
                    x = source.x + column
                    if value != self.transparent_index and 0 <= x < self.width:
                        canvas[y * self.width + x] = value
        return canvas

    def _linked_source(self, cel: LinkedCel) -> Cel:
        for candidate in self.frames[cel.frame_link].cels:
            if isinstance(candidate, Cel) and candidate.layer == cel.layer:
                return candidate
        raise ValueError(
            f"cel links to frame {cel.frame_link} layer {cel.layer}, which has no image"
        )


def _parse_palette(body: bytes, existing: list) -> list:
    size, first, last = struct.unpack_from("<III", body, 0)
    palette = list(existing) + [(0, 0, 0, 0)] * max(0, size - len(existing))
    pos = 20
    for index in range(first, last + 1):
        flags, r, g, b, a = struct.unpack_from("<HBBBB", body, pos)
        pos += 6
        name = None
        if flags & 1:
            length = struct.unpack_from("<H", body, pos)[0]
            name = body[pos + 2 : pos + 2 + length].decode("utf-8")
            pos += 2 + length
        palette[index] = (r, g, b, a, name) if name else (r, g, b, a)
    return palette


def _parse_layer(body: bytes) -> Layer:
    flags, layer_type = struct.unpack_from("<HH", body, 0)
    opacity = body[12]
    length = struct.unpack_from("<H", body, 16)[0]
    name = body[18 : 18 + length].decode("utf-8")
    return Layer(name=name, flags=flags, opacity=opacity, layer_type=layer_type)


def _parse_cel(body: bytes):
    layer, x, y, _opacity, cel_type = struct.unpack_from("<HhhBH", body, 0)
    if cel_type == CEL_LINKED:
        return LinkedCel(
            layer=layer, frame_link=struct.unpack_from("<H", body, 16)[0], x=x, y=y
        )
    if cel_type not in (CEL_RAW, CEL_COMPRESSED):
        raise ValueError(f"unsupported cel type {cel_type} on layer {layer}")
    width, height = struct.unpack_from("<HH", body, 16)
    pixels = body[20:]
    if cel_type == CEL_COMPRESSED:
        pixels = zlib.decompress(pixels)
    return Cel(layer=layer, x=x, y=y, width=width, height=height, pixels=pixels)
