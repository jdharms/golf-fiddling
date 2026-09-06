"""Integration tests: menu trim patch against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import PatchError, menu_trim_patch, menu_trim_patches
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

TITLE = "ABCDEFGHIJKLMN"

_BANK12 = 12 * 0x4000


class MenuTables:
    """Decode the bank 12 menu tables straight out of a ROM image."""

    def __init__(self, rom_bytes: bytes):
        self.bank = rom_bytes[0x10 + _BANK12 : 0x10 + _BANK12 + 0x4000]

    def byte(self, cpu: int) -> int:
        return self.bank[cpu - 0x8000]

    def word(self, cpu: int) -> int:
        return self.byte(cpu) | (self.byte(cpu + 1) << 8)

    def text_list(self, ptr: int) -> list[tuple[int, int, str]]:
        """[(x, y, text)] for each entry of a menu text list."""
        if ptr == 0:
            return []
        entries = []
        for i in range(self.byte(ptr)):
            entry = self.word(ptr + 1 + i * 2)
            chars = bytearray()
            j = entry + 2
            while self.byte(j) != 0xFF:
                chars.append(self.byte(j))
                j += 1
            entries.append((self.byte(entry), self.byte(entry + 1), chars.decode("ascii")))
        return entries

    def static_text(self, menu_id: int) -> list[tuple[int, int, str]]:
        return self.text_list(self.word(0x8B35 + menu_id * 4))

    def options(self, menu_id: int) -> list[tuple[int, int, str]]:
        return self.text_list(self.word(0x8B35 + menu_id * 4 + 2))

    def destinations(self, menu_id: int) -> list[int]:
        base = self.word(0x8AA2 + menu_id * 2)
        return [self.byte(base + i) for i in range(len(self.options(menu_id)))]


@pytest.fixture
def patched(tmp_path) -> MenuTables:
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    menu_trim_patch(title_text=TITLE).apply(writer)
    writer.save()
    return MenuTables(out.read_bytes())


def test_vanilla_rom_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    for sub in menu_trim_patches(title_text=TITLE):
        assert sub.can_apply(writer), sub.name


def test_apply_and_reload(tmp_path):
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = menu_trim_patch(title_text=TITLE)
    patch.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)


def test_apply_is_idempotent(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    patch = menu_trim_patch(title_text=TITLE)
    patch.apply(writer)
    before = bytes(writer.rom_data)
    patch.apply(writer)
    assert bytes(writer.rom_data) == before


def test_rejects_an_already_trimmed_rom(tmp_path):
    """A second, differently-titled build must refuse rather than corrupt."""
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    menu_trim_patch(title_text=TITLE).apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    with pytest.raises(PatchError):
        menu_trim_patch(title_text="NOPQRSTUVWXYZ0").apply(reloaded)


def test_main_menu_keeps_only_stroke_play_and_club_house(patched):
    assert [text for _, _, text in patched.options(0x00)] == [
        "STROKE PLAY",
        "CLUB HOUSE",
    ]
    assert patched.destinations(0x00) == [0x01, 0x15]


def test_main_menu_rows_have_no_gap(patched):
    assert [y for _, y, _ in patched.options(0x00)] == [0x0E, 0x10]


def test_main_menu_static_text_is_the_requested_title(patched):
    assert patched.static_text(0x00) == [(0x04, 0x0A, TITLE)]


def test_other_menus_keep_the_shared_please_select_text(patched):
    for menu_id in (0x01, 0x03, 0x09, 0x10):
        assert patched.static_text(menu_id) == [(0x04, 0x0A, "PLEASE SELECT")]


def test_club_house_keeps_only_the_five_retained_entries(patched):
    assert [text for _, _, text in patched.options(0x15)] == [
        "REGISTER NAME",
        "CHOOSE CLUBS",
        "OPTIONS",
        "TRAINING",
        "CLEAR SAVED DATA",
    ]
    assert patched.destinations(0x15) == [0x81, 0x82, 0x83, 0x87, 0x89]


def test_club_house_rows_have_no_gaps(patched):
    assert [y for _, y, _ in patched.options(0x15)] == [0x06, 0x08, 0x0A, 0x0C, 0x0E]


def test_play_mode_guard_only_fires_for_selection_zero(patched):
    # ApplyPlayModeSelection $89AA: CMP #$01, so CLUB HOUSE at index 1 no
    # longer writes GolfGameMode.
    assert patched.byte(0x89AA) == 0xC9
    assert patched.byte(0x89AB) == 0x01


def test_only_bank_12_data_changes(tmp_path):
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    menu_trim_patch(title_text=TITLE).apply(writer)
    writer.save()

    vanilla = Path(ROM_PATH).read_bytes()
    result = out.read_bytes()
    assert len(vanilla) == len(result)
    changed = [i for i in range(len(vanilla)) if vanilla[i] != result[i]]
    assert changed, "patch changed nothing"
    for offset in changed:
        prg = offset - 0x10
        assert _BANK12 <= prg < _BANK12 + 0x4000, f"0x{offset:X} outside bank 12"
