"""Shared pytest fixtures for compression tests."""

import json
from pathlib import Path

import pytest

from golf.core.decompressor import TerrainDecompressor, GreensDecompressor
from golf.formats.hole_data import HoleData


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
def hole_04_data():
    """Load hole 4 (simple 30-row hole)."""
    hole = HoleData()
    hole.load(Path(__file__).parent.parent / "courses" / "japan" / "hole_04.json")
    return hole


@pytest.fixture
def hole_01_data():
    """Load hole 1 (complex 38-row hole)."""
    hole = HoleData()
    hole.load(Path(__file__).parent.parent / "courses" / "japan" / "hole_01.json")
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
    decompressor = TerrainDecompressor(rom_reader=rom_reader)
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
    decompressor = GreensDecompressor(rom_reader=rom_reader)
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
