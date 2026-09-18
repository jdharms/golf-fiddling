"""Static files with versioned URLs and the cache headers that go with them.

Templates link static files through `StaticVersions.url`, which adds `?v=` and a hash of
the file's contents, so a deploy that changes a file changes its URL. `CachedStaticFiles`
lets a browser keep a versioned response for good and makes it revalidate anything else:
the rangefinder's module imports and renders, which carry no version, and would otherwise
be cached by heuristic and outlive a deploy.
"""

import hashlib
from pathlib import Path
from urllib.parse import parse_qs

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

#: the query parameter holding a static file's version
VERSION_PARAM = "v"
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


class CachedStaticFiles(StaticFiles):
    """`StaticFiles` answering versioned URLs as immutable and the rest as revalidated."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            versioned = VERSION_PARAM in query
            response.headers["Cache-Control"] = IMMUTABLE if versioned else REVALIDATE
        return response


class StaticVersions:
    """Builds versioned URLs for the files under a static directory.

    A file's version is a hash of its contents, recomputed when its size or modification
    time changes, so an edit during development shows on the next page load.
    """

    def __init__(self, directory: Path, prefix: str = "/static") -> None:
        self.directory = directory
        self.prefix = prefix
        self._versions: dict[str, tuple[int, int, str]] = {}

    def version(self, path: str) -> str:
        file = self.directory / path
        stat = file.stat()
        cached = self._versions.get(path)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]
        digest = hashlib.sha256(file.read_bytes()).hexdigest()[:12]
        self._versions[path] = (stat.st_mtime_ns, stat.st_size, digest)
        return digest

    def url(self, path: str) -> str:
        """The URL of `path`, relative to the directory, with its version."""
        return f"{self.prefix}/{path}?{VERSION_PARAM}={self.version(path)}"
