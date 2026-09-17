"""Integration tests: menu trim patch against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import PatchError, menu_trim_patch, menu_trim_patches
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

WORDS = ["ALPHA", "BETA", "GAMMA"]
HEADER = [(0x04, 0x0A, "ALPHA  BETA  "), (0x04, 0x0C, "GAMMA ")]

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

    def course_select_table(self) -> dict[int, int]:
        """ApplyCourseSelection's inline (selection + 1 -> CurrCourse) table."""
        table = {}
        cpu = 0x89EA
        while self.byte(cpu):
            table[self.byte(cpu)] = self.byte(cpu + 1)
            cpu += 2
        return table


@pytest.fixture
def vanilla() -> MenuTables:
    return MenuTables(Path(ROM_PATH).read_bytes())


@pytest.fixture
def patched(tmp_path) -> MenuTables:
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    menu_trim_patch(WORDS).apply(writer)
    writer.save()
    return MenuTables(out.read_bytes())


def test_vanilla_rom_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    for sub in menu_trim_patches(WORDS):
        assert sub.can_apply(writer), sub.name


def test_apply_and_reload(tmp_path):
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = menu_trim_patch(WORDS)
    patch.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)


def test_apply_is_idempotent(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    patch = menu_trim_patch(WORDS)
    patch.apply(writer)
    before = bytes(writer.rom_data)
    patch.apply(writer)
    assert bytes(writer.rom_data) == before


def test_rejects_an_already_trimmed_rom(tmp_path):
    """A second build with different words must refuse rather than corrupt."""
    out = tmp_path / "menu_trim.nes"
    writer = RomWriter(ROM_PATH, str(out))
    menu_trim_patch(WORDS).apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    with pytest.raises(PatchError):
        menu_trim_patch().apply(reloaded)


def test_main_menu_keeps_only_stroke_play_and_club_house(patched):
    assert [text for _, _, text in patched.options(0x00)] == [
        "STROKE PLAY",
        "CLUB HOUSE",
    ]
    assert patched.destinations(0x00) == [0x01, 0x15]


def test_main_menu_rows_have_no_gap(patched):
    assert [y for _, y, _ in patched.options(0x00)] == [0x0E, 0x10]


def test_main_player_and_course_menus_share_the_header(patched):
    for menu_id in (0x00, 0x01, 0x02):
        assert patched.static_text(menu_id) == HEADER, f"menu ${menu_id:02X}"


def test_header_occupies_exactly_vanilla_course_select_span(patched, vanilla):
    """Same positions and widths, so the same attribute cells are coloured."""
    def span(entries):
        return [(x, y, len(text)) for x, y, text in entries]

    assert vanilla.static_text(0x02) == [(0x04, 0x0A, "PLEASE SELECT"), (0x04, 0x0C, "COURSE")]
    assert span(patched.static_text(0x02)) == span(vanilla.static_text(0x02))


def test_other_menus_keep_the_shared_please_select_text(patched):
    for menu_id in (0x03, 0x07, 0x09, 0x10):
        assert patched.static_text(menu_id) == [(0x04, 0x0A, "PLEASE SELECT")]


def test_course_select_offers_only_random_course(patched):
    assert patched.options(0x02) == [(0x0C, 0x0E, "RANDOM COURSE")]
    assert patched.destinations(0x02) == [0x03]


def test_course_select_picks_course_zero(patched, vanilla):
    # selection 0 looks up key 1
    assert vanilla.course_select_table() == {1: 1, 2: 0, 3: 2}
    assert patched.course_select_table() == {1: 0, 2: 0, 3: 2}


def test_player_count_menu_still_leads_to_course_select(patched):
    assert [text for _, _, text in patched.options(0x01)] == ["1 PLAYER", "2 PLAYER"]
    assert patched.destinations(0x01) == [0x02, 0x02]


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
    menu_trim_patch(WORDS).apply(writer)
    writer.save()

    vanilla = Path(ROM_PATH).read_bytes()
    result = out.read_bytes()
    assert len(vanilla) == len(result)
    changed = [i for i in range(len(vanilla)) if vanilla[i] != result[i]]
    assert changed, "patch changed nothing"
    for offset in changed:
        prg = offset - 0x10
        assert _BANK12 <= prg < _BANK12 + 0x4000, f"0x{offset:X} outside bank 12"
