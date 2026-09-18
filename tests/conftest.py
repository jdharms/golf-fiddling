"""Shared pytest fixtures.

Vanilla course data is not checked in: `golf-rehydrate` dumps it from the ROMs into
`courses/` and renders the rangefinder from it. A test that reads it asks for
`vanilla_courses` (NES Open), `vanilla_jp_courses` (Mario Open) or `rangefinder_assets`,
each of which skips when its ROM is absent and fails, naming `golf-rehydrate`, when the ROM
is present but the data is missing or stale. Such tests carry the `vanilla_data` marker.
"""

import json
from pathlib import Path

import pytest

from golf.core.decompressor import GreensDecompressor, TerrainDecompressor
from golf.formats.hole_data import HoleData
from golf.randomizer.catalog import DEFAULT_COURSES, JP_ROM, US_ROM, Catalog
from golf.randomizer.rehydrate import (
    RehydrateError,
    check_rangefinder,
    check_rehydrated,
)
from golf.randomizer.roms import vanilla_rom
from golf.rendering.rangefinder import DEFAULT_OUTPUT

ROOT = Path(__file__).resolve().parents[1]
VANILLA_DATA_FIXTURES = frozenset(
    {"vanilla_courses", "vanilla_jp_courses", "rangefinder_assets"}
)


def pytest_collection_modifyitems(items):
    for item in items:
        if VANILLA_DATA_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.vanilla_data)


def _rehydrated(rom_id: str) -> Path:
    rom = vanilla_rom(rom_id)
    if not (ROOT / rom.filename).exists():
        pytest.skip(f"{rom.filename} not present")
    try:
        check_rehydrated(Catalog.load(), DEFAULT_COURSES, [rom_id])
    except RehydrateError as error:
        pytest.fail(
            f"{rom.filename} is present but its courses are not rehydrated; "
            f"run `uv run golf-rehydrate`\n{error}"
        )
    return DEFAULT_COURSES


@pytest.fixture(scope="session")
def vanilla_courses() -> Path:
    """The courses root, holding the NES Open courses verified against the catalog."""
    return _rehydrated(US_ROM)


@pytest.fixture(scope="session")
def vanilla_jp_courses() -> Path:
    """The courses root, holding the Mario Open courses under jp/, verified."""
    return _rehydrated(JP_ROM)


@pytest.fixture(scope="session")
def rangefinder_assets(vanilla_courses) -> Path:
    """The rangefinder's static directory, rendered from the rehydrated courses."""
    try:
        check_rangefinder(vanilla_courses, DEFAULT_OUTPUT)
    except RehydrateError as error:
        pytest.fail(f"run `uv run golf-rehydrate`\n{error}")
    return DEFAULT_OUTPUT


@pytest.fixture
def compression_tables_path():
    """Path to real compression tables."""
    return Path(__file__).parent.parent / "data" / "tables" / "compression_tables.json"


@pytest.fixture
def compression_tables(compression_tables_path):
    """Load real compression tables."""
    with open(compression_tables_path) as f:
        return json.load(f)


@pytest.fixture
def terrain_tables(compression_tables):
    """Extract terrain-specific tables."""
    return compression_tables["terrain"]


@pytest.fixture
def greens_tables(compression_tables):
    """Extract greens-specific tables."""
    return compression_tables["greens"]


@pytest.fixture
def mock_minimal_tables():
    """Load minimal mock tables for unit tests."""
    path = Path(__file__).parent / "fixtures" / "minimal_tables.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def mock_minimal_terrain_tables(mock_minimal_tables):
    """Extract minimal terrain tables for unit testing."""
    return mock_minimal_tables["terrain"]


@pytest.fixture
def mock_minimal_greens_tables(mock_minimal_tables):
    """Extract minimal greens tables for unit testing."""
    return mock_minimal_tables["greens"]


@pytest.fixture
def hole_04_data(vanilla_courses):
    """Load Japan hole 4 (simple 30-row hole)."""
    hole = HoleData()
    hole.load(vanilla_courses / "japan" / "hole_04.json")
    return hole


@pytest.fixture
def hole_01_data(vanilla_courses):
    """Load Japan hole 1 (complex 38-row hole)."""
    hole = HoleData()
    hole.load(vanilla_courses / "japan" / "hole_01.json")
    return hole


@pytest.fixture
def simple_terrain_fixture():
    """Load simple hand-crafted terrain fixture."""
    path = Path(__file__).parent / "fixtures" / "simple_terrain.json"
    with open(path) as f:
        data = json.load(f)
    return data


@pytest.fixture
def simple_greens_fixture():
    """Load simple hand-crafted greens fixture."""
    path = Path(__file__).parent / "fixtures" / "simple_greens.json"
    with open(path) as f:
        data = json.load(f)
    return data


@pytest.fixture
def terrain_decompressor(terrain_tables):
    """Create a terrain decompressor with real tables."""
    rom_reader = None  # Not needed for decompressor initialization
    decompressor = TerrainDecompressor(rom=rom_reader)
    # Manually set tables since we're providing them
    decompressor.horiz_table = terrain_tables["horizontal_table"]
    decompressor.vert_table = terrain_tables["vertical_table"]
    dict_table = terrain_tables["dictionary_codes"]
    # Build dict_table as expected by decompressor (flat byte array)
    decompressor.dict_table = []
    for code in sorted(dict_table.keys(), key=lambda x: int(x, 16)):
        decompressor.dict_table.append(dict_table[code]["first_byte"])
        decompressor.dict_table.append(dict_table[code]["repeat_count"])
    return decompressor


@pytest.fixture
def greens_decompressor(greens_tables):
    """Create a greens decompressor with real tables."""
    rom_reader = None  # Not needed for decompressor initialization
    decompressor = GreensDecompressor(rom=rom_reader)
    # Manually set tables since we're providing them
    decompressor.horiz_table = greens_tables["horizontal_table"]
    decompressor.vert_table = greens_tables["vertical_table"]
    dict_table = greens_tables["dictionary_codes"]
    # Build dict_table as expected by decompressor (flat byte array)
    decompressor.dict_table = []
    for code in sorted(dict_table.keys(), key=lambda x: int(x, 16)):
        decompressor.dict_table.append(dict_table[code]["first_byte"])
        decompressor.dict_table.append(dict_table[code]["repeat_count"])
    return decompressor
