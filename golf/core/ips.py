"""
IPS patch files: build one from a base file and a patched copy, and apply one.

IPS offsets count from the start of the file, so diff whole `.nes` files -
iNES header included - rather than PRG ROM (which is what `RomWriter`
offsets address).

Format:

    "PATCH"
    records, each one of:
        offset (3 bytes, big-endian), size (2 bytes, big-endian), `size` bytes
        offset (3 bytes), 0x0000, run length (2 bytes, big-endian), value (1 byte)
    "EOF"
    optional truncation length (3 bytes, big-endian) - an extension some
    tools write; `apply` honours it, `diff` never writes it

`diff` is deterministic: the same two files always produce the same patch.
"""

HEADER = b"PATCH"
FOOTER = b"EOF"

#: The largest offset a record can start at (3 bytes).
MAX_OFFSET = 0xFFFFFF
#: The largest payload or run length a record can carry (2 bytes).
MAX_RECORD = 0xFFFF
#: A record starting here would read as the footer, so none may.
EOF_OFFSET = int.from_bytes(FOOTER, "big")

#: A new record costs a 5-byte header, so unchanged gaps shorter than that are
#: cheaper to carry inside one record than to split around.
MERGE_GAP = 5
#: An RLE record costs 8 bytes, plus 5 for the header of the literal record
#: that resumes after it. Runs at least this long are smaller as RLE anywhere.
RLE_MIN_RUN = 14

_BLOCK = 4096


def diff(base: bytes, patched: bytes) -> bytes:
    """The IPS patch that turns `base` into `patched`. Both must be the same size."""
    if len(base) != len(patched):
        raise ValueError(
            f"files differ in size ({len(base)} and {len(patched)} bytes); "
            "diff only supports same-size files"
        )
    if len(patched) > MAX_OFFSET + 1:
        raise ValueError(f"files over {MAX_OFFSET + 1} bytes cannot be addressed by IPS")

    out = bytearray(HEADER)
    for start, end in _changed_spans(base, patched):
        for offset, value, length in _pieces(patched, start, end):
            out += _records(patched, offset, value, length)
    out += FOOTER
    return bytes(out)


def apply(base: bytes, patch: bytes) -> bytes:
    """Apply an IPS patch to `base` and return the result."""
    if not patch.startswith(HEADER):
        raise ValueError("not an IPS patch: missing PATCH header")

    out = bytearray(base)
    pos = len(HEADER)
    while True:
        tag = patch[pos : pos + 3]
        if len(tag) < 3:
            raise ValueError("truncated IPS patch: no EOF marker")
        pos += 3
        if tag == FOOTER:
            break

        offset = int.from_bytes(tag, "big")
        size = _read_int(patch, pos, 2)
        pos += 2
        if size:
            data = patch[pos : pos + size]
            if len(data) < size:
                raise ValueError(f"truncated IPS record at offset 0x{offset:06X}")
            pos += size
        else:
            run = _read_int(patch, pos, 2)
            value = _read_int(patch, pos + 2, 1)
            pos += 3
            data = bytes([value]) * run

        end = offset + len(data)
        if end > len(out):
            out.extend(bytes(end - len(out)))
        out[offset:end] = data

    trailer = patch[pos:]
    if len(trailer) == 3:
        del out[int.from_bytes(trailer, "big") :]
    elif trailer:
        raise ValueError(f"{len(trailer)} unexpected bytes after EOF marker")
    return bytes(out)


def _read_int(patch: bytes, pos: int, length: int) -> int:
    field = patch[pos : pos + length]
    if len(field) < length:
        raise ValueError("truncated IPS record")
    return int.from_bytes(field, "big")


def _changed_spans(base: bytes, patched: bytes) -> list[list[int]]:
    """[start, end) spans of changed bytes, with gaps under MERGE_GAP merged."""
    spans: list[list[int]] = []
    size = len(base)
    block_start = 0
    while block_start < size:
        block_end = min(block_start + _BLOCK, size)
        if base[block_start:block_end] != patched[block_start:block_end]:
            for i in range(block_start, block_end):
                if base[i] != patched[i]:
                    if spans and i - spans[-1][1] < MERGE_GAP:
                        spans[-1][1] = i + 1
                    else:
                        spans.append([i, i + 1])
        block_start = block_end
    return spans


def _pieces(data: bytes, start: int, end: int) -> list[tuple[int, int | None, int]]:
    """
    Cover [start, end) with (offset, value, length) pieces: `value` is the
    repeated byte of an RLE run, or None for literal bytes.
    """
    pieces: list[tuple[int, int | None, int]] = []
    literal_start = start
    i = start
    while i < end:
        value = data[i]
        run_end = i + 1
        while run_end < end and data[run_end] == value:
            run_end += 1
        if run_end - i >= RLE_MIN_RUN:
            if literal_start < i:
                pieces.append((literal_start, None, i - literal_start))
            pieces.append((i, value, run_end - i))
            literal_start = run_end
        i = run_end
    if literal_start < end:
        pieces.append((literal_start, None, end - literal_start))
    return pieces


def _records(data: bytes, offset: int, value: int | None, length: int) -> bytes:
    """One piece as records, split to MAX_RECORD and kept off EOF_OFFSET."""
    out = bytearray()
    while length:
        if offset == EOF_OFFSET:
            # Start one byte early instead; rewriting that byte with its
            # patched value is harmless.
            out += _literal(data, offset - 1, 2)
            offset += 1
            length -= 1
            continue
        count = min(length, MAX_RECORD)
        if value is None:
            out += _literal(data, offset, count)
        else:
            out += offset.to_bytes(3, "big") + b"\x00\x00" + count.to_bytes(2, "big")
            out.append(value)
        offset += count
        length -= count
    return bytes(out)


def _literal(data: bytes, offset: int, count: int) -> bytes:
    return offset.to_bytes(3, "big") + count.to_bytes(2, "big") + data[offset : offset + count]
