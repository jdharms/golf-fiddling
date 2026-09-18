#!/usr/bin/env python3
"""Run a pinned Biome (JS/CSS linter and formatter) without any Node tooling.

The first run downloads the release binary for this platform into `.tools/`, checks it
against the SHA-256 pinned below and then runs it; later runs use the cached copy. Every
argument is passed straight to Biome, so `golf-biome --help` is Biome's own help.

To upgrade, change BIOME_VERSION and replace every hash with the `digest` GitHub lists
for that release's assets:

    curl -s "https://api.github.com/repos/biomejs/biome/releases/tags/@biomejs/biome@<version>" \\
        | jq -r '.assets[] | "\\(.name) \\(.digest)"'
"""

import hashlib
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

BIOME_VERSION = "2.5.14"

# Release asset name -> SHA-256 of its contents.
BIOME_SHA256 = {
    "biome-linux-x64": "290c1c85deeaf01310d9187306060b53961574856a7e34f59d9662562e6f19fe",
    "biome-linux-arm64": "50ac7f598985e21b15da57e5d87da0f7ab0c163e6f78eb6d4690309827d77ef8",
    "biome-darwin-x64": "b331448d7afb592cc4674e9bd6905eae5e79f5dd9b34b61b44803a6b7a91b801",
    "biome-darwin-arm64": "3d1194d0a7b720315fb6f8cbafeb5b18ca7100c3e635e8ce82ef46b315de9c0e",
    "biome-win32-x64.exe": "bef8f088617c8364314f55dffdc7b8ddabe12fee9e1e71f45f708a7027579280",
    "biome-win32-arm64.exe": "af61f09b037a6cdf24ed3b37664de83e9b61bf8a4c8dd691ea6b64e808c035c8",
}

RELEASE_URL = "https://github.com/biomejs/biome/releases/download/@biomejs/biome@{version}/{asset}"
CACHE_DIR = Path(__file__).resolve().parents[2] / ".tools" / f"biome-{BIOME_VERSION}"

_OS_NAMES = {"linux": "linux", "darwin": "darwin", "win32": "win32"}
_ARCH_NAMES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def asset_name() -> str:
    """The release asset for this machine, or SystemExit if Biome has none pinned for it."""
    os_name = _OS_NAMES.get(sys.platform)
    arch = _ARCH_NAMES.get(platform.machine().lower())
    name = f"biome-{os_name}-{arch}" + (".exe" if os_name == "win32" else "")
    if name not in BIOME_SHA256:
        raise SystemExit(
            f"golf-biome: no pinned Biome binary for {sys.platform}/{platform.machine()}"
        )
    return name


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_binary() -> Path:
    """Return the verified cached binary, downloading it first if needed."""
    asset = asset_name()
    expected = BIOME_SHA256[asset]
    binary = CACHE_DIR / asset
    if binary.exists():
        if sha256_of(binary) == expected:
            return binary
        print(
            f"golf-biome: cached {binary} fails its hash check, downloading again",
            file=sys.stderr,
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = RELEASE_URL.format(version=BIOME_VERSION, asset=asset)
    print(f"golf-biome: downloading {url}", file=sys.stderr)
    partial = binary.with_name(binary.name + ".part")
    try:
        urllib.request.urlretrieve(url, partial)
        actual = sha256_of(partial)
        if actual != expected:
            raise SystemExit(
                f"golf-biome: {asset} hash mismatch\n  expected {expected}\n  got      {actual}"
            )
        partial.chmod(0o755)
        partial.replace(binary)
    finally:
        partial.unlink(missing_ok=True)
    return binary


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    binary = ensure_binary()
    return subprocess.run([os.fspath(binary), *args]).returncode


if __name__ == "__main__":
    sys.exit(main())
