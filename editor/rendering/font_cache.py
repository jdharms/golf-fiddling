from typing import Optional

import pygame

_fonts: dict[tuple[Optional[str], int], pygame.font.Font] = {}

def get_font(name: Optional[str], size: int) -> pygame.font.Font:
    key = (name, size)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont(name, size)
    return _fonts[key]