"""The golf-randomize CLI's generate and show subcommands, which need no ROM."""

import json
import subprocess
import sys
from pathlib import Path

from golf.core.patches.sram_defaults import Club
from golf.randomizer.catalog import US_ROM, Catalog
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import ClubRules, Manifest, Settings

ROOT = Path(__file__).resolve().parents[2]


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.randomize", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def load(path: Path) -> Manifest:
    return Manifest.from_json(json.loads(path.read_text()))


def test_generate_writes_the_manifest_the_library_generates(tmp_path):
    path = tmp_path / "seed.json"
    completed = run("generate", "--seed", "cli-unit", "-o", path)
    assert completed.returncode == 0, completed.stderr
    expected = generate(
        Catalog.load(), CurationSnapshot.load(), Settings(prng_seed="cli-unit")
    )
    assert load(path) == expected
    assert f"wrote {path}" in completed.stdout


def test_generate_draws_a_seed_when_none_is_given(tmp_path):
    path = tmp_path / "seed.json"
    assert run("generate", "-o", path).returncode == 0
    assert load(path).settings.prng_seed


def test_every_generate_flag_lands_in_the_settings(tmp_path):
    path = tmp_path / "seed.json"
    completed = run(
        "generate",
        "-o",
        path,
        "--seed",
        "flags",
        "--par",
        "70",
        "--sources",
        US_ROM,
        "--exclude-tags",
        "long,scenic",
        "--allow-family-repeats",
        "--music",
        "nes_uk",
        "--mercy-point",
        "none",
        "--clubs-max",
        "10",
        "--banned",
        "1W",
        "--required-bag",
        "3W,PW",
    )
    assert completed.returncode == 0, completed.stderr
    settings = load(path).settings
    assert settings == Settings(
        prng_seed="flags",
        par=70,
        sources=frozenset({US_ROM}),
        exclude_tags=frozenset({"long", "scenic"}),
        allow_family_repeats=True,
        music="nes_uk",
        mercy_point=None,
        clubs=ClubRules(
            max=10,
            banned=frozenset({Club.W1}),
            required_bag=frozenset({Club.W3, Club.PW}),
        ),
    )
    assert load(path).course.par == 70


def test_show_prints_the_course(tmp_path):
    path = tmp_path / "seed.json"
    assert run("generate", "--seed", "show", "-o", path).returncode == 0
    completed = run("show", path)
    assert completed.returncode == 0, completed.stderr
    manifest = load(path)
    for slot in manifest.course.holes:
        assert str(slot.id) in completed.stdout
    assert " ".join(manifest.course.magic_words) in completed.stdout
    assert f"music: {manifest.course.music}" in completed.stdout


def test_generate_refuses_settings_the_model_refuses(tmp_path):
    path = tmp_path / "seed.json"
    for args, message in [
        (["--music", "bogus"], "music must be"),
        (["--banned", "PT"], "putter cannot be banned"),
        (["--clubs-max", "2", "--required-bag", "1W,3W"], "over the max"),
        (["--banned", "5W"], "unknown club"),
    ]:
        completed = run("generate", "-o", path, *args)
        assert completed.returncode == 1, args
        assert completed.stderr.startswith("error:") and message in completed.stderr, (
            completed.stderr
        )
    assert not path.exists()


def test_argparse_refuses_an_unsupported_par(tmp_path):
    completed = run("generate", "-o", tmp_path / "seed.json", "--par", "69")
    assert completed.returncode == 2
    assert "invalid choice" in completed.stderr


def test_show_refuses_a_malformed_manifest(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": 1}))
    completed = run("show", path)
    assert completed.returncode == 1
    assert completed.stderr.startswith("error:")
