"""The seed builder: where it finds the vanilla ROM, and refusing to build without it."""

from pathlib import Path

import pytest

from golf.randomizer.catalog import Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.manifest import Settings
from server.builder import BuilderUnavailableError, SeedBuilder
from server.config import Config


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def curation() -> CurationSnapshot:
    return CurationSnapshot.load()


def builder(catalog, curation, rom_path: Path) -> SeedBuilder:
    return SeedBuilder(catalog, curation, HoleStore(), rom_path)


def test_from_config_reads_the_rom_and_holes_directories(tmp_path):
    made = SeedBuilder.from_config(
        Config(rom_dir=tmp_path / "roms", holes_dir=tmp_path / "holes")
    )
    assert made.rom_path == tmp_path / "roms" / "nes_open_us.nes"
    assert made.store.root == tmp_path / "holes"
    assert len(made.catalog) > 0


def test_generate_uses_the_catalog_and_curation(catalog, curation, tmp_path):
    manifest = builder(catalog, curation, tmp_path / "missing.nes").generate(
        Settings(prng_seed="builder")
    )
    assert manifest.catalog_version == catalog.version
    assert manifest.curation_stamp == curation.stamp


def test_a_missing_rom_makes_the_builder_unavailable(catalog, curation, tmp_path):
    seeds = builder(catalog, curation, tmp_path / "missing.nes")
    manifest = seeds.generate(Settings(prng_seed="builder"))
    with pytest.raises(BuilderUnavailableError, match="cannot read"):
        seeds.build(manifest)


def test_a_rom_that_is_not_vanilla_makes_the_builder_unavailable(
    catalog, curation, tmp_path
):
    rom = tmp_path / "nes_open_us.nes"
    rom.write_bytes(b"NES\x1a" + bytes(100))
    seeds = builder(catalog, curation, rom)
    with pytest.raises(BuilderUnavailableError, match="not the vanilla US ROM"):
        seeds.vanilla()
