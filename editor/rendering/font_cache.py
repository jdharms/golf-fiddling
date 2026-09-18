import pygame

_fonts: dict[tuple[str | None, int], pygame.font.Font] = {}


def get_font(name: str | None, size: int) -> pygame.font.Font:
    key = (name, size)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont(name, size)
    return _fonts[key]
