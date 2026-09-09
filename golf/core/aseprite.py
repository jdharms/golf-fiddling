"""
A minimal writer for Aseprite's `.aseprite` / `.ase` format.

Only what a layered reference export needs: indexed colour, one palette, named
layers with flags, and one compressed cel per layer per frame.  Cel position is
part of the format, which is what lets a layer be *moved* by an artist and read
back as an offset.

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


@dataclass
class Layer:
    name: str
    flags: int = LAYER_VISIBLE | LAYER_EDITABLE
    opacity: int = 255


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
            "<HHHHHHB", layer.flags, 0, 0, 0, 0, 0, layer.opacity
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
            8,                       # indexed
            1,                       # layer opacity is valid
            100,                     # deprecated speed
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
