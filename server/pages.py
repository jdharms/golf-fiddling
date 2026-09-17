"""Checked-in Markdown pages served by the randomizer website."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from markupsafe import Markup

HERE = Path(__file__).resolve().parent
PAGES_DIR = HERE / "content" / "pages"
FRONTMATTER_DELIMITER = "+++"
FIELDS = frozenset({"title", "nav_title", "order", "enabled", "listed"})
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class PageError(ValueError):
    """A malformed page or page catalog."""


@dataclass(frozen=True)
class ContentPage:
    slug: str
    title: str
    nav_title: str
    order: int
    enabled: bool
    listed: bool
    body_html: Markup


@dataclass(frozen=True)
class PageCatalog:
    """The Markdown pages known to the site, including disabled ones."""

    pages: tuple[ContentPage, ...]

    @classmethod
    def load(cls, directory: Path = PAGES_DIR) -> "PageCatalog":
        """Load and validate every Markdown file directly under ``directory``."""
        if not directory.is_dir():
            raise PageError(f"page directory does not exist: {directory}")

        pages: list[ContentPage] = []
        for path in sorted(directory.rglob("*.md")):
            if path.parent != directory:
                relative = path.relative_to(directory)
                raise PageError(f"{relative}: pages must live directly in {directory}")
            pages.append(_load_page(path))
        return cls(tuple(pages))

    def get(self, slug: str) -> ContentPage | None:
        """Return an enabled page by slug; disabled and unknown pages are absent."""
        return next(
            (page for page in self.pages if page.slug == slug and page.enabled), None
        )

    @property
    def listed(self) -> tuple[ContentPage, ...]:
        """Enabled pages that should appear in navigation, in display order."""
        return tuple(
            sorted(
                (page for page in self.pages if page.enabled and page.listed),
                key=lambda page: (page.order, page.nav_title.casefold(), page.slug),
            )
        )


def _split_frontmatter(path: Path, source: str) -> tuple[str, str]:
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        raise PageError(f"{path.name}: first line must be {FRONTMATTER_DELIMITER!r}")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise PageError(f"{path.name}: missing closing {FRONTMATTER_DELIMITER!r}")


def _string_field(
    path: Path, metadata: dict, name: str, default: str | None = None
) -> str:
    value = metadata.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise PageError(f"{path.name}: {name} must be a nonempty string")
    return value.strip()


def _load_page(path: Path) -> ContentPage:
    if not SLUG.fullmatch(path.stem):
        raise PageError(
            f"{path.name}: filename must contain only lowercase letters, digits, and hyphens"
        )

    frontmatter, body = _split_frontmatter(path, path.read_text(encoding="utf-8"))
    try:
        metadata = tomllib.loads(frontmatter)
    except tomllib.TOMLDecodeError as problem:
        raise PageError(f"{path.name}: invalid TOML frontmatter: {problem}") from None

    extra = metadata.keys() - FIELDS
    if extra:
        raise PageError(f"{path.name}: unknown frontmatter fields: {sorted(extra)}")

    title = _string_field(path, metadata, "title")
    nav_title = _string_field(path, metadata, "nav_title", title)
    order = metadata.get("order", 100)
    enabled = metadata.get("enabled", True)
    listed = metadata.get("listed", True)
    if type(order) is not int:
        raise PageError(f"{path.name}: order must be an integer")
    if type(enabled) is not bool:
        raise PageError(f"{path.name}: enabled must be a boolean")
    if type(listed) is not bool:
        raise PageError(f"{path.name}: listed must be a boolean")
    if listed and not enabled:
        raise PageError(f"{path.name}: a disabled page cannot be listed")

    renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    return ContentPage(
        slug=path.stem,
        title=title,
        nav_title=nav_title,
        order=order,
        enabled=enabled,
        listed=listed,
        body_html=Markup(renderer.render(body)),
    )
