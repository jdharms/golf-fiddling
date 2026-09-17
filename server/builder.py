"""What the site's routes call to build: a manifest from settings, its unfinished IPS, and a finished IPS.

The builder holds the catalog, curation and hole store the site generates from, and reads
the server's vanilla US ROM on first use. Builds run behind a semaphore, so a burst of
requests queues instead of building side by side. `create_app` takes a builder so tests
can stand one in that never reads a ROM.
"""

import hashlib
import threading
from pathlib import Path

from golf.core.patches import QrCredentials
from golf.randomizer.build import PlayerOptions, build_unfinished, finish
from golf.randomizer.catalog import DEFAULT_INDEX, US_ROM, Catalog, HoleStore
from golf.randomizer.curation import DEFAULT_CURATION, CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import Manifest, Settings
from golf.randomizer.roms import vanilla_rom

from .config import Config


class BuilderUnavailableError(Exception):
    """The server cannot build seeds: its vanilla ROM is missing or not the vanilla ROM."""


class SeedBuilder:
    def __init__(
        self,
        catalog: Catalog,
        curation: CurationSnapshot,
        store: HoleStore,
        rom_path: Path,
        concurrency: int = 1,
    ):
        self.catalog = catalog
        self.curation = curation
        self.store = store
        self.rom_path = Path(rom_path)
        self._builds = threading.Semaphore(concurrency)
        self._rom_lock = threading.Lock()
        self._vanilla: bytes | None = None

    @classmethod
    def from_config(cls, config: Config) -> "SeedBuilder":
        return cls(
            catalog=Catalog.load(DEFAULT_INDEX),
            curation=CurationSnapshot.load(DEFAULT_CURATION),
            store=HoleStore(config.holes_dir),
            rom_path=Path(config.rom_dir) / vanilla_rom(US_ROM).filename,
        )

    def vanilla(self) -> bytes:
        """The server's vanilla US ROM, read and checked once."""
        with self._rom_lock:
            if self._vanilla is None:
                try:
                    data = self.rom_path.read_bytes()
                except OSError as problem:
                    raise BuilderUnavailableError(f"cannot read the vanilla ROM at {self.rom_path}: {problem}") from None
                expected = vanilla_rom(US_ROM).sha1
                if hashlib.sha1(data).hexdigest() != expected:
                    raise BuilderUnavailableError(f"{self.rom_path} is not the vanilla US ROM (SHA-1 {expected})")
                self._vanilla = data
            return self._vanilla

    def generate(self, settings: Settings) -> Manifest:
        return generate(self.catalog, self.curation, settings)

    def build(self, manifest: Manifest) -> bytes:
        """The seed's unfinished IPS, what the seed row stores."""
        vanilla = self.vanilla()
        with self._builds:
            return build_unfinished(manifest, self.catalog, self.store, vanilla).ips

    def finish(
        self,
        manifest: Manifest,
        unfinished_ips: bytes,
        options: PlayerOptions,
        credentials: QrCredentials | None = None,
    ) -> bytes:
        """A player's finished IPS for a stored seed: signed in with credentials, a guest without.

        Finishing takes milliseconds, so it skips the semaphore.
        """
        return finish(manifest, self.vanilla(), unfinished_ips, options, credentials).ips
