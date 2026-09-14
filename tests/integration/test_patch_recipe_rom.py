"""Integration tests: recipes and the golf-patch CLI against the real ROM."""

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from golf.core import ips
from golf.core.patches import (
    ATTR_STREAMING_PATCH,
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    CoursePatch,
    PatchStack,
    QrCredentials,
    Recipe,
    StackError,
    load_credentials,
    seeded_wind_patch,
)
from golf.formats.hole_data import HoleData

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"
ART = ROOT / "renders/prehole_signpost/signpost_us_hole01_course_only.aseprite"

pytestmark = pytest.mark.skipif(not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present")


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return ROM_PATH.read_bytes()


@pytest.fixture
def credentials(tmp_path) -> Path:
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(QrCredentials.random(random.Random(8)).manifest()))
    return path


def full_recipe(credentials: Path) -> dict:
    return {
        "steps": [
            {"patch": "wram_expansion"},
            {"patch": "multi_bank_lookup"},
            {"patch": "course_mirrors"},
            {"patch": "attr_streaming"},
            {"patch": "course", "course": "courses/jp/jp_uk"},
            {"patch": "menu_trim", "words": ["RANDO", "GOLF", "0001"]},
            {"patch": "signpost_random_banner", "art": str(ART.relative_to(ROOT))},
            {"patch": "mercy_tap_in", "mercy_point": 9},
            {"patch": "seeded_wind", "seed": "recipe"},
            {"patch": "practice_swing"},
            {"patch": "scorecard_qr", "credentials": str(credentials)},
            {"patch": "music_import", "dump": "data/music/music_jp_courses.json"},
        ]
    }


def run(*args: str | Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", *map(str, args)], cwd=ROOT, capture_output=True, text=True
    )


@pytest.mark.skipif(not ART.exists(), reason=f"{ART.name} not present")
def test_a_recipe_of_every_compatible_patch_builds(vanilla, credentials):
    recipe = Recipe.from_dict(full_recipe(credentials), ROOT)
    result = recipe.stack(vanilla).build(vanilla)
    assert [name for name, regions in result.regions.items() if regions] == [
        step.patch for step in recipe.steps
    ]


def test_a_recipe_builds_the_same_rom_as_the_stack_it_describes(vanilla):
    recipe = Recipe.from_dict(
        {
            "steps": [
                {"patch": "multi_bank_lookup"},
                {"patch": "course_mirrors"},
                {"patch": "attr_streaming"},
                {"patch": "course", "course": "courses/japan"},
                {"patch": "seeded_wind", "seed": "same"},
            ]
        },
        ROOT,
    )
    holes = []
    for number in range(1, 19):
        hole = HoleData()
        hole.load(str(ROOT / f"courses/japan/hole_{number:02d}.json"))
        holes.append(hole)
    direct = PatchStack(
        [MULTI_BANK_CODE_PATCH, COURSE_MIRRORS_PATCH, ATTR_STREAMING_PATCH, CoursePatch(holes), seeded_wind_patch("same")]
    )
    assert recipe.stack(vanilla).build(vanilla).rom == direct.build(vanilla).rom


@pytest.mark.skipif(not ART.exists(), reason=f"{ART.name} not present")
def test_banner_removal_and_new_banner_art_do_not_stack(vanilla):
    """Both rewrite the banner selection at $AC5D; whichever comes second finds
    the other's bytes where it expects vanilla ones."""
    recipe = Recipe.from_dict(
        {"steps": [{"patch": "signpost_random_banner", "art": str(ART)}, {"patch": "remove_course_banner"}]},
        ROOT,
    )
    with pytest.raises(StackError, match="step 'remove_course_banner'.*unexpected state"):
        recipe.stack(vanilla).build(vanilla)


def test_cli_builds_a_rom_and_its_ips_from_a_recipe(vanilla, tmp_path, credentials):
    recipe = full_recipe(credentials)
    recipe["steps"] = [s for s in recipe["steps"] if s["patch"] != "signpost_random_banner"]
    recipe_path = tmp_path / "recipe.json"
    Recipe.from_dict(recipe, ROOT).save(recipe_path)

    out, patch = tmp_path / "out.nes", tmp_path / "out.ips"
    completed = run("tools.patch", ROM_PATH, recipe_path, "-o", out, "--ips", patch, "-v")

    assert completed.returncode == 0, completed.stderr
    assert ips.apply(vanilla, patch.read_bytes()) == out.read_bytes()
    assert "bank 0:" in completed.stdout  # the course report
    assert "(key withheld)" in completed.stdout
    assert load_credentials(credentials).keys[0].hex() not in completed.stdout


def test_cli_inline_steps_match_their_saved_recipe(tmp_path):
    saved, first, second = tmp_path / "saved.json", tmp_path / "first.nes", tmp_path / "second.nes"
    inline = run(
        "tools.patch", ROM_PATH,
        "-p", "multi_bank_lookup", "-p", "course_mirrors", "-p", "attr_streaming",
        "-p", "course:course=courses/japan", "-p", "mercy_tap_in:mercy_point=9",
        "--save-recipe", saved, "-o", first,
    )
    assert inline.returncode == 0, inline.stderr
    from_recipe = run("tools.patch", ROM_PATH, saved, "-o", second)
    assert from_recipe.returncode == 0, from_recipe.stderr
    assert first.read_bytes() == second.read_bytes()


def test_cli_reports_a_missing_requirement(tmp_path):
    completed = run("tools.patch", ROM_PATH, "-p", "seeded_wind:seed=abc", "--validate-only")
    assert completed.returncode == 1
    assert "'seeded_wind' requires course_mirrors (not in the stack)" in completed.stderr


def test_cli_lists_every_patch_type():
    completed = run("tools.patch", "--list")
    assert completed.returncode == 0
    for spec_id in ("course", "seeded_wind", "scorecard_qr", "signpost_random_banner"):
        assert f"\n{spec_id}\n" in f"\n{completed.stdout}"


def test_credentials_cli_is_reproducible_with_a_seed(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert run("tools.qr.credentials", "-o", first, "--rng-seed", "5").returncode == 0
    assert run("tools.qr.credentials", "-o", second, "--rng-seed", "5").returncode == 0
    assert first.read_text() == second.read_text()
    assert load_credentials(first) == QrCredentials.random(random.Random(5))
