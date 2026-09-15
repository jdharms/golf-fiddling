"""The vanilla ROMs a randomizer seed can be built from, with the hash that identifies each.

The ids are the catalog's source ROM ids (`US_ROM`, `JP_ROM`), which `required_roms`
returns for a manifest. A hash covers the whole file, iNES header included. The site's ROM
setup page checks a player's files against these in the browser (docs/randomizer_devplan.md).
"""

from dataclasses import dataclass

from golf.core.jp_rom_utils import JP_ROM_SHA1
from golf.core.rom_utils import US_ROM_SHA1

from .catalog import JP_ROM, US_ROM


@dataclass(frozen=True)
class VanillaRom:
    id: str
    title: str
    #: lowercase hex SHA-1 of the whole file
    sha1: str


VANILLA_ROMS: tuple[VanillaRom, ...] = (
    VanillaRom(US_ROM, "NES Open Tournament Golf (USA)", US_ROM_SHA1),
    VanillaRom(JP_ROM, "Mario Open Golf (Japan)", JP_ROM_SHA1),
)


def vanilla_rom(rom_id: str) -> VanillaRom:
    """The vanilla ROM with this id. Raises KeyError for an unknown id."""
    for rom in VANILLA_ROMS:
        if rom.id == rom_id:
            return rom
    raise KeyError(rom_id)
