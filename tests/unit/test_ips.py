"""Unit tests for IPS patch creation and application."""

import random

import pytest

from golf.core import ips
from golf.core.ips import EOF_OFFSET, MAX_RECORD, MERGE_GAP, RLE_MIN_RUN


def records(patch: bytes) -> list[tuple[int, str, int]]:
    """(offset, 'literal' | 'rle', length) for each record in a patch."""
    assert patch.startswith(b"PATCH") and patch.endswith(b"EOF")
    out = []
    pos = 5
    while patch[pos : pos + 3] != b"EOF" or pos + 3 != len(patch):
        offset = int.from_bytes(patch[pos : pos + 3], "big")
        size = int.from_bytes(patch[pos + 3 : pos + 5], "big")
        if size:
            out.append((offset, "literal", size))
            pos += 5 + size
        else:
            out.append((offset, "rle", int.from_bytes(patch[pos + 5 : pos + 7], "big")))
            pos += 8
    return out


def roundtrip(base: bytes, patched: bytes) -> bytes:
    patch = ips.diff(base, patched)
    assert ips.apply(base, patch) == patched
    return patch


class TestDiff:
    def test_identical_files_give_an_empty_patch(self):
        assert ips.diff(bytes(64), bytes(64)) == b"PATCHEOF"

    def test_single_byte(self):
        patched = bytearray(32)
        patched[5] = 0xAB
        assert (
            ips.diff(bytes(32), bytes(patched))
            == b"PATCH" + bytes([0, 0, 5, 0, 1, 0xAB]) + b"EOF"
        )

    def test_offsets_count_from_the_start_of_the_file(self):
        patched = bytearray(0x20000)
        patched[0x10203] = 1
        assert records(roundtrip(bytes(0x20000), bytes(patched))) == [
            (0x10203, "literal", 1)
        ]

    def test_short_gaps_merge_into_one_record(self):
        patched = bytearray(64)
        patched[10] = 1
        patched[10 + MERGE_GAP] = 1  # MERGE_GAP - 1 unchanged bytes between
        assert records(roundtrip(bytes(64), bytes(patched))) == [
            (10, "literal", MERGE_GAP + 1)
        ]

    def test_longer_gaps_split_records(self):
        patched = bytearray(64)
        patched[10] = 1
        patched[11 + MERGE_GAP] = 1  # MERGE_GAP unchanged bytes between
        assert records(roundtrip(bytes(64), bytes(patched))) == [
            (10, "literal", 1),
            (11 + MERGE_GAP, "literal", 1),
        ]

    def test_long_runs_become_rle(self):
        patched = bytearray(100)
        patched[10:40] = b"\xff" * 30
        patch = roundtrip(bytes(100), bytes(patched))
        assert patch == b"PATCH" + bytes([0, 0, 10, 0, 0, 0, 30, 0xFF]) + b"EOF"

    def test_short_runs_stay_literal(self):
        patched = bytearray(100)
        patched[10 : 10 + RLE_MIN_RUN - 1] = b"\xff" * (RLE_MIN_RUN - 1)
        assert records(roundtrip(bytes(100), bytes(patched))) == [
            (10, "literal", RLE_MIN_RUN - 1)
        ]

    def test_run_inside_a_span_splits_it(self):
        patched = bytearray(100)
        patched[10:13] = b"\x01\x02\x03"
        patched[13:33] = b"\x07" * 20
        patched[33:35] = b"\x04\x05"
        assert records(roundtrip(bytes(100), bytes(patched))) == [
            (10, "literal", 3),
            (13, "rle", 20),
            (33, "literal", 2),
        ]

    def test_records_split_at_max_size(self):
        rng = random.Random(1)
        size = MAX_RECORD + 6
        patched = bytes(rng.randrange(1, 256) for _ in range(size))
        # no byte repeats 14 times in a row, so the span stays literal
        assert records(roundtrip(bytes(size), patched)) == [
            (0, "literal", MAX_RECORD),
            (MAX_RECORD, "literal", 6),
        ]

    @pytest.mark.parametrize("run", [1, 20])
    def test_no_record_starts_at_the_eof_offset(self, run):
        size = EOF_OFFSET + 64
        base = bytes(size)
        patched = bytearray(size)
        patched[EOF_OFFSET : EOF_OFFSET + run] = b"\x55" * run
        patch = roundtrip(base, bytes(patched))
        offsets = [offset for offset, _, _ in records(patch)]
        assert EOF_OFFSET not in offsets
        assert offsets[0] == EOF_OFFSET - 1

    def test_different_sizes_are_rejected(self):
        with pytest.raises(ValueError, match="differ in size"):
            ips.diff(bytes(10), bytes(11))

    def test_is_deterministic(self):
        rng = random.Random(7)
        base = bytes(rng.randrange(256) for _ in range(4096))
        patched = bytearray(base)
        for _ in range(50):
            patched[rng.randrange(4096)] = rng.randrange(256)
        assert ips.diff(base, bytes(patched)) == ips.diff(base, bytes(patched))

    @pytest.mark.parametrize("seed", range(5))
    def test_random_edits_roundtrip(self, seed):
        rng = random.Random(seed)
        size = 262_160
        base = bytes(rng.randrange(256) for _ in range(size))
        patched = bytearray(base)
        for _ in range(200):
            start = rng.randrange(size)
            length = rng.choice([1, 3, 20, 300])
            fill = rng.choice([None, rng.randrange(256)])
            for i in range(start, min(start + length, size)):
                patched[i] = rng.randrange(256) if fill is None else fill
        roundtrip(base, bytes(patched))


class TestApply:
    def test_rejects_missing_header(self):
        with pytest.raises(ValueError, match="PATCH header"):
            ips.apply(bytes(8), b"NOTAPATCH")

    def test_rejects_missing_eof(self):
        with pytest.raises(ValueError, match="no EOF"):
            ips.apply(bytes(8), b"PATCH" + bytes([0, 0, 1, 0, 1, 0xAA]))

    def test_rejects_truncated_record(self):
        with pytest.raises(ValueError, match="truncated"):
            ips.apply(bytes(8), b"PATCH" + bytes([0, 0, 1, 0, 4, 0xAA]) + b"EOF")

    def test_rejects_trailing_garbage(self):
        with pytest.raises(ValueError, match="after EOF"):
            ips.apply(bytes(8), b"PATCHEOF\x00")

    def test_rle_record(self):
        patch = b"PATCH" + bytes([0, 0, 2, 0, 0, 0, 3, 0x7E]) + b"EOF"
        assert ips.apply(bytes(8), patch) == bytes([0, 0, 0x7E, 0x7E, 0x7E, 0, 0, 0])

    def test_records_past_the_end_grow_the_file(self):
        patch = b"PATCH" + bytes([0, 0, 10, 0, 1, 0xAA]) + b"EOF"
        assert ips.apply(bytes(8), patch) == bytes(10) + b"\xaa"

    def test_truncation_extension(self):
        assert ips.apply(bytes(8), b"PATCHEOF" + bytes([0, 0, 5])) == bytes(5)
