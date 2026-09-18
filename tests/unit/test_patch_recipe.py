"""Unit tests for the patch registry and recipes."""

import json
import random
from pathlib import Path

import pytest

from golf.core import rom_utils
from golf.core.patches import (
    PATCH_SPECS,
    QrCredentials,
    Recipe,
    RecipeError,
    RecipeStep,
    describe_params,
    load_credentials,
    parse_step_arg,
)
from tests.synthetic_holes import write_courses

ROOT = Path(__file__).resolve().parents[2]


def step(data: dict, base_dir: Path = ROOT) -> RecipeStep:
    return RecipeStep.from_dict(data, base_dir)


@pytest.fixture
def credentials_file(tmp_path) -> Path:
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(QrCredentials.random(random.Random(3)).manifest()))
    return path


class TestRegistry:
    def test_every_patch_type_builds_a_patch_of_its_own_name(
        self, credentials_file, tmp_path
    ):
        courses = write_courses(tmp_path / "courses", "japan")
        params = {
            "course": {"course": str(courses / "japan")},
            "course_theme": {"music": 2},
            "menu_trim": {"words": "ABCD EFGH IJKL"},
            "mercy_tap_in": {"mercy_point": 9},
            "seeded_wind": {"seed": "x"},
            "qr_credentials": {"credentials": str(credentials_file)},
            "music_import": {"dump": "data/music/music_jp_courses.json"},
        }
        for spec_id in PATCH_SPECS:
            if spec_id == "signpost_random_banner":
                continue  # reads the ROM; covered by the integration tests
            (built,) = Recipe(
                [step({"patch": spec_id, **params.get(spec_id, {})})]
            ).build_steps(b"")
            assert built.patch.name == spec_id
            assert all(isinstance(line, str) for line in built.report())

    def test_describe_params(self):
        assert describe_params(PATCH_SPECS["wram_expansion"]) == ""
        assert describe_params(PATCH_SPECS["seeded_wind"]) == "seed (string, required)"
        assert (
            describe_params(PATCH_SPECS["practice_swing"])
            == "hold_frames (integer, default 120)"
        )
        assert "mercy_result (integer or null)" in describe_params(
            PATCH_SPECS["mercy_tap_in"]
        )
        assert "name (string, default 'RANDOM')" in describe_params(
            PATCH_SPECS["scorecard_course_name"]
        )
        assert "title (string or null)" in describe_params(
            PATCH_SPECS["scorecard_course_name"]
        )
        assert "clubs (list of string or null)" in describe_params(
            PATCH_SPECS["sram_defaults"]
        )


class TestParams:
    def test_integers_accept_numbers_and_strings_in_any_base(self):
        assert step({"patch": "mercy_tap_in", "mercy_point": 9}).params.mercy_point == 9
        assert (
            step({"patch": "practice_swing", "hold_frames": "0x60"}).params.hold_frames
            == 0x60
        )

    @pytest.mark.parametrize("value", [True, "nine", 9.5])
    def test_integers_reject_other_values(self, value):
        with pytest.raises(RecipeError, match=r"mercy_point: expected integer"):
            step({"patch": "mercy_tap_in", "mercy_point": value})

    def test_strings_are_not_coerced(self):
        with pytest.raises(RecipeError, match="seed: expected string"):
            step({"patch": "seeded_wind", "seed": 5})

    def test_optional_values_take_null(self):
        assert (
            step(
                {"patch": "mercy_tap_in", "mercy_point": 9, "mercy_result": None}
            ).params.mercy_result
            is None
        )

    def test_paths_are_relative_to_the_base_dir(self, tmp_path):
        assert (
            step({"patch": "course", "course": "japan"}, tmp_path).params.course
            == tmp_path / "japan"
        )
        absolute = step(
            {"patch": "course", "course": str(tmp_path)}, ROOT
        ).params.course
        assert absolute == tmp_path

    def test_path_lists(self, tmp_path):
        params = step(
            {"patch": "course", "holes": ["a.json", "b.json"]}, tmp_path
        ).params
        assert params.holes == [tmp_path / "a.json", tmp_path / "b.json"]

    def test_string_lists_also_take_a_whitespace_separated_string(self):
        assert step({"patch": "sram_defaults", "clubs": " 1W 3W  PW"}).params.clubs == [
            "1W",
            "3W",
            "PW",
        ]
        params = parse_step_arg("sram_defaults:clubs=1W 3W PW,bgm=false", ROOT).params
        assert (params.clubs, params.bgm) == (["1W", "3W", "PW"], False)

    def test_path_lists_do_not_take_a_string(self, tmp_path):
        with pytest.raises(RecipeError, match="holes: expected list of path,"):
            step({"patch": "course", "holes": "a.json b.json"}, tmp_path)

    def test_unknown_parameters_are_named(self):
        with pytest.raises(
            RecipeError, match=r"unknown parameter\(s\) sed; seeded_wind takes seed"
        ):
            step({"patch": "seeded_wind", "sed": "x"})

    def test_missing_required_parameters(self):
        with pytest.raises(RecipeError, match="missing required parameter 'seed'"):
            step({"patch": "seeded_wind"})

    def test_unknown_patch_types_list_the_known_ones(self):
        with pytest.raises(
            RecipeError, match="unknown patch type 'wind'; known types: wram_expansion"
        ):
            step({"patch": "wind"})

    def test_a_step_needs_a_patch_key(self):
        with pytest.raises(RecipeError, match="'patch' key"):
            step({"seed": "x"})


class TestRecipe:
    def test_the_base_defaults_to_vanilla(self):
        assert Recipe.from_dict({"steps": []}, ROOT).base_sha1 == rom_utils.US_ROM_SHA1
        assert (
            Recipe.from_dict({"steps": [], "base_sha1": None}, ROOT).base_sha1 is None
        )

    def test_unknown_keys_are_rejected(self):
        with pytest.raises(RecipeError, match="unknown recipe key"):
            Recipe.from_dict({"steps": [], "version": 1}, ROOT)

    def test_steps_must_be_a_list(self):
        with pytest.raises(RecipeError, match="'steps' list"):
            Recipe.from_dict({"steps": {"patch": "wram_expansion"}}, ROOT)

    @pytest.mark.parametrize("base_sha1", [rom_utils.US_ROM_SHA1, None])
    def test_round_trip(self, tmp_path, base_sha1):
        data = {
            "steps": [
                {"patch": "multi_bank_lookup"},
                {"patch": "course", "course": "courses/japan"},
                {"patch": "course", "holes": ["a/hole_01.json", "b/hole_07.json"]},
                {"patch": "mercy_tap_in", "mercy_point": 9, "mercy_result": 12},
                {"patch": "practice_swing"},
            ]
        }
        if base_sha1 is None:
            data = {"base_sha1": None, **data}
        assert Recipe.from_dict(data, tmp_path).to_dict(tmp_path) == data

    def test_saving_elsewhere_keeps_paths_pointing_at_the_same_files(self, tmp_path):
        here, there = tmp_path / "here", tmp_path / "there"
        here.mkdir()
        there.mkdir()
        recipe = Recipe.from_dict(
            {"steps": [{"patch": "course", "course": "courses/japan"}]}, here
        )
        recipe.save(there / "recipe.json")

        saved = json.loads((there / "recipe.json").read_text())
        assert saved["steps"][0]["course"] == "../here/courses/japan"
        reloaded = Recipe.load(there / "recipe.json")
        assert (
            reloaded.steps[0].params.course.resolve()
            == (here / "courses/japan").resolve()
        )

    def test_course_takes_a_directory_or_holes_not_both(self, tmp_path):
        recipe = Recipe(
            [step({"patch": "course", "course": "x", "holes": ["y"]}, tmp_path)]
        )
        with pytest.raises(
            RecipeError, match=r"steps\[0\] \(course\): course takes exactly one"
        ):
            recipe.build_steps(b"")

    def test_build_errors_name_the_step(self):
        recipe = Recipe(
            [
                step({"patch": "practice_swing"}),
                step({"patch": "menu_trim", "words": "TWO WORDS"}),
            ]
        )
        with pytest.raises(
            RecipeError,
            match=r"steps\[1\] \(menu_trim\): words must be exactly 3 words",
        ):
            recipe.build_steps(b"")

    def test_malformed_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{")
        with pytest.raises(RecipeError, match="bad.json"):
            Recipe.load(path)


class TestInlineSteps:
    def test_no_parameters(self):
        assert parse_step_arg("practice_swing", ROOT).patch == "practice_swing"

    def test_parameters(self):
        parsed = parse_step_arg("mercy_tap_in:mercy_point=9,mercy_result=0x0C", ROOT)
        assert (parsed.params.mercy_point, parsed.params.mercy_result) == (9, 12)

    def test_paths_are_relative_to_the_given_directory(self, tmp_path):
        assert (
            parse_step_arg("course:course=japan", tmp_path).params.course
            == tmp_path / "japan"
        )

    def test_malformed_parameters(self):
        with pytest.raises(RecipeError, match="key=value pairs"):
            parse_step_arg("seeded_wind:abc", ROOT)


class TestCredentials:
    def test_round_trip(self, credentials_file):
        credentials = QrCredentials.random(random.Random(3))
        assert load_credentials(credentials_file) == credentials

    def test_malformed_file(self, tmp_path):
        path = tmp_path / "keys.json"
        path.write_text(json.dumps({"seed_id": "00"}))
        with pytest.raises(ValueError, match="not a credentials file"):
            load_credentials(path)
