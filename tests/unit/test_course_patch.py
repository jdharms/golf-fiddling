"""Unit tests for the course patch."""

import pytest

from golf.core.patches import (
    ATTR_STREAMING_PATCH,
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    CoursePatch,
    PatchError,
)
from golf.core import rom_utils
from golf.core.patches.course import (
    BANK_TABLE_CPU_ADDR,
    BANK_TABLE_SIZE,
    GREENS_DATA_END,
    TERRAIN_BOUNDS,
    BankAllocation,
    HoleCompressedData,
    allocate_terrain,
    bank_table_bytes,
    compress_holes,
    scorecard_total_writes,
)
from golf.core.rom_writer import BankOverflowError
from golf.formats.hole_data import HoleData


def leaf_patches(patch):
    """A patch's BytePatches, flattening composites."""
    if hasattr(patch, "patches"):
        return [leaf for sub in patch.patches for leaf in leaf_patches(sub)]
    return [patch]


class MockRomWriter:
    """A bare PRG image with every required patch's sites holding original bytes."""

    def __init__(self, size: int = 0x40000):
        self.data = bytearray(size)
        for required in CoursePatch.requires:
            for leaf in leaf_patches(required):
                self.write_prg(leaf.prg_offset, leaf.original)

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset : prg_offset + length])

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset : prg_offset + len(data)] = data

    def annotate(self, description: str) -> "MockRomWriter":
        return self


def rom_with_requirements() -> MockRomWriter:
    rom = MockRomWriter()
    for required in CoursePatch.requires:
        required.apply(rom)
    return rom


class MockHoleData:
    """A hole of a single terrain tile and a single greens tile."""

    def __init__(self, terrain_height: int = 32):
        self.terrain_height = terrain_height
        self.terrain = [[0xA0] * 22 for _ in range(terrain_height)]
        # Attributes need 11 columns (for 22-tile wide terrain with 2x2 supertiles)
        self.attributes = [[0] * 11 for _ in range((terrain_height + 1) // 2)]
        self.greens = [[0x10] * 24 for _ in range(24)]
        self.green_x = 88
        self.green_y = 100
        self.metadata = {"par": 4, "tee": {"x": 88, "y": 500}}


def compressed_holes(count: int, terrain_size: int) -> list[HoleCompressedData]:
    return [
        HoleCompressedData(
            hole_index=i,
            terrain=bytes([0xA0] * terrain_size),
            attributes=bytes(72),
            greens=bytes([0x10] * 100),
        )
        for i in range(count)
    ]


def load_holes(course_dir: str) -> list[HoleData]:
    holes = []
    for number in range(1, 19):
        hole = HoleData()
        hole.load(f"{course_dir}/hole_{number:02d}.json")
        holes.append(hole)
    return holes


@pytest.fixture(scope="module")
def japan() -> list[HoleData]:
    return load_holes("courses/japan")


@pytest.fixture(scope="module")
def japan_with_tall_hole(japan) -> list[HoleData]:
    """Japan with its last hole swapped for a 30-attribute-row JP hole."""
    tall = HoleData()
    tall.load("courses/jp/jp_uk/hole_14.json")
    assert len(tall.attributes) == 30
    return japan[:17] + [tall]


@pytest.fixture(scope="module")
def course(japan) -> CoursePatch:
    return CoursePatch(japan)


class TestConstants:
    def test_terrain_bounds_are_banks_0_and_1(self):
        assert TERRAIN_BOUNDS == {0: (0x8000, 0xA23E), 1: (0x8000, 0xA1E6)}
        assert sum(end - start for start, end in TERRAIN_BOUNDS.values()) == 17444

    def test_bank_table(self):
        assert BANK_TABLE_CPU_ADDR == 0xA700
        assert BANK_TABLE_SIZE == 36
        assert GREENS_DATA_END == BANK_TABLE_CPU_ADDR


class TestAllocateTerrain:
    def test_allocates_to_first_bank_with_space(self):
        allocations = allocate_terrain(compressed_holes(5, 100))
        assert all(alloc.bank == 0 for alloc in allocations)

    def test_allocations_are_contiguous(self):
        allocations = allocate_terrain(compressed_holes(3, 100))
        assert [a.terrain_start for a in allocations] == [0x8000, 0x80AC, 0x8158]
        assert all(a.terrain_end == a.terrain_start + 100 for a in allocations)

    def test_overflows_to_bank_1(self):
        # 18 x 500 bytes = 9,000, more than bank 0's 8,766
        allocations = allocate_terrain(compressed_holes(18, 428))
        assert {a.bank for a in allocations} == {0, 1}

    def test_never_uses_bank_2(self):
        # 18 x 1,072 bytes = 19,296, more than banks 0 and 1 hold together
        with pytest.raises(BankOverflowError):
            allocate_terrain(compressed_holes(18, 1000))


class TestBankTable:
    def test_uses_doubled_indexing(self):
        table = bank_table_bytes(
            [
                BankAllocation(
                    hole_index=0, bank=0, terrain_start=0x8000, terrain_end=0x8100
                ),
                BankAllocation(
                    hole_index=2, bank=1, terrain_start=0x8000, terrain_end=0x8100
                ),
                BankAllocation(
                    hole_index=17, bank=1, terrain_start=0x8100, terrain_end=0x8200
                ),
            ]
        )
        assert len(table) == BANK_TABLE_SIZE
        assert table[0] == 0
        assert table[4] == 1
        assert table[34] == 1


class TestCompressHoles:
    def test_compresses_all_holes(self):
        holes = [MockHoleData(), MockHoleData(terrain_height=60), MockHoleData()]
        compressed = compress_holes(holes)

        assert [c.hole_index for c in compressed] == [0, 1, 2]
        for hole, comp in zip(holes, compressed, strict=True):
            assert len(comp.terrain) > 0
            # Attributes are packed at their real size, not padded to 72 bytes
            assert len(comp.attributes) == ((len(hole.attributes) + 1) // 2) * 6
            assert len(comp.greens) > 0


class TestScorecardTotals:
    @staticmethod
    def by_name(writes) -> dict[str, tuple[int, bytes]]:
        return {write.name: (write.prg_offset, write.data) for write in writes}

    def test_japan(self, japan):
        """Japan's totals are the values vanilla hardcodes for course 0."""
        writes = self.by_name(scorecard_total_writes(japan))
        bank2 = lambda addr: rom_utils.cpu_to_prg_switched(addr, 2)  # noqa: E731
        assert writes == {
            "scorecard total yardage 7037 (thousands tile)": (
                bank2(0xAF33),
                bytes([0x47]),
            ),
            "scorecard total yardage 7037 (hundreds)": (
                bank2(0xAF71),
                bytes([0, 0, 0]),
            ),
            "scorecard total yardage 7037 (tens)": (bank2(0xAF74), bytes([3, 3, 3])),
            "scorecard total yardage 7037 (ones)": (bank2(0xAF77), bytes([7, 7, 7])),
            "scorecard total par 72 (main card)": (bank2(0xB9BF), bytes([0x47, 0x42])),
            "scorecard total par 72 (36-hole match play card)": (
                bank2(0xBAD5),
                bytes([0x47, 0x42]),
            ),
        }

    def test_follows_edited_holes(self):
        holes = [MockHoleData() for _ in range(18)]
        holes[0].metadata = {"par": 5, "distance": 568}
        # 17 x par 4 + 5 = 73; 17 x 400 + 568 = 7,368
        writes = [write.data for write in scorecard_total_writes(holes)]
        assert writes == [
            bytes([0x47]),
            bytes([3, 3, 3]),
            bytes([6, 6, 6]),
            bytes([8, 8, 8]),
            bytes([0x47, 0x43]),
            bytes([0x47, 0x43]),
        ]

    @pytest.mark.parametrize(
        ("metadata", "message"),
        [
            ({"par": 4, "distance": 55}, "Total yardage 990"),
            ({"par": 4, "distance": 556}, "Total yardage 10,008"),
            ({"par": 6, "distance": 400}, "Total par 108"),
        ],
    )
    def test_rejects_totals_that_do_not_fit(self, metadata, message):
        holes = [MockHoleData() for _ in range(18)]
        for hole in holes:
            hole.metadata = metadata
        with pytest.raises(ValueError, match=message):
            scorecard_total_writes(holes)

    def test_course_patch_writes_them(self, course, japan):
        assert course.writes[-6:] == scorecard_total_writes(japan)
        assert (course.stats.total_yards, course.stats.total_par) == (7037, 72)


class TestCoursePatch:
    @pytest.mark.parametrize("count", [0, 17, 19, 36])
    def test_takes_exactly_18_holes(self, count):
        with pytest.raises(ValueError, match="Expected 18 holes"):
            CoursePatch([MockHoleData() for _ in range(count)])

    def test_requires_the_code_that_plays_it(self):
        assert list(CoursePatch.requires) == [
            MULTI_BANK_CODE_PATCH,
            COURSE_MIRRORS_PATCH,
            ATTR_STREAMING_PATCH,
        ]

    def test_building_raises_when_the_course_does_not_fit(self):
        # Single-tile holes compress badly: 18 of them overflow bank 3's greens region
        with pytest.raises(BankOverflowError):
            CoursePatch([MockHoleData() for _ in range(18)])

    def test_stats(self, course):
        stats = course.stats
        assert len(stats.bank_assignments) == 18
        assert set(stats.bank_usage) == {0, 1}
        assert stats.total_terrain_bytes == sum(stats.terrain_bytes_per_hole) + sum(
            stats.attribute_bytes_per_hole
        )

    def test_writes_never_touch_the_requirements(self, course):
        """Code patches are required, not written by the course patch."""
        required = set()
        for patch in CoursePatch.requires:
            for leaf in leaf_patches(patch):
                required |= set(
                    range(leaf.prg_offset, leaf.prg_offset + len(leaf.patched))
                )
        for write in course.writes:
            span = set(range(write.prg_offset, write.prg_offset + len(write.data)))
            assert not (span & required), write.name

    @pytest.mark.parametrize("tall", [False, True])
    def test_apply_then_is_applied(self, japan, japan_with_tall_hole, tall):
        patch = CoursePatch(japan_with_tall_hole if tall else japan)
        rom = rom_with_requirements()

        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)

    def test_apply_is_idempotent(self, course):
        rom = rom_with_requirements()
        course.apply(rom)
        first = bytes(rom.data)
        course.apply(rom)
        assert bytes(rom.data) == first

    def test_refuses_rom_missing_a_requirement(self, course):
        rom = MockRomWriter()
        MULTI_BANK_CODE_PATCH.apply(rom)
        COURSE_MIRRORS_PATCH.apply(rom)

        assert course.missing_requirements(rom) == [ATTR_STREAMING_PATCH]
        with pytest.raises(PatchError, match="requires attr_streaming"):
            course.apply(rom)
        assert not course.is_applied(rom)
