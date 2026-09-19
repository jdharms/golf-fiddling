"""golf-site's checks before it starts uvicorn."""

import os
import subprocess
import sys
from pathlib import Path

from server.config import PREFIX

ROOT = Path(__file__).resolve().parents[2]


def launch(environ: dict[str, str]) -> subprocess.CompletedProcess:
    env = {
        name: value for name, value in os.environ.items() if not name.startswith(PREFIX)
    }
    return subprocess.run(
        [sys.executable, "-m", "tools.site"],
        cwd=ROOT,
        env=env | environ,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_refuses_settings_the_config_rejects_in_one_line():
    result = launch(
        {"GOLF_DISCORD_CLIENT_ID": "client", "GOLF_DISCORD_CLIENT_SECRET": "secret"}
    )
    assert result.returncode == 1
    assert result.stderr == (
        "error: Discord sign-in needs a session secret (GOLF_SESSION_SECRET)\n"
    )


def test_refuses_to_start_without_rehydrated_data(tmp_path):
    result = launch(
        {
            "GOLF_ROM_DIR": str(tmp_path),
            "GOLF_HOLES_DIR": str(tmp_path / "courses"),
            "GOLF_RANGEFINDER_DIR": str(tmp_path / "rangefinder"),
        }
    )
    assert result.returncode == 1
    assert "run `golf-rehydrate` first" in result.stderr
