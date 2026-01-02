"""
NES Open Tournament Golf - Sprite Renderer

Renders sprite overlays including green overlay, terrain sprites, and greens sprites.
"""

from typing import Dict, Tuple

import pygame
from pygame import Surface, Rect

from editor.core.pygame_rendering import Sprite
from golf.formats.hole_data import HoleData
from editor.core.constants import GREEN_OVERLAY_COLOR
from editor.controllers.view_state import ViewState


class SpriteRenderer:
    """Renders sprite overlays on the canvas."""

    @staticmethod
    def render_green_overlay(
        screen: Surface,
        view_state: ViewState,
        hole_data: HoleData,
    ):
        """
        Render the putting green overlay on terrain view.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            hole_data: Hole data containing greens information
        """
        if not hole_data.greens:
            return

        canvas_rect = view_state.canvas_rect
        canvas_scale = view_state.scale
        canvas_offset_x = view_state.offset_x
        canvas_offset_y = view_state.offset_y

        green_x = hole_data.green_x
        green_y = hole_data.green_y

        for gy, grow in enumerate(hole_data.greens):
            for gx, gval in enumerate(grow):
                if gval >= 0x30:
                    # Calculate pixel position
                    px = green_x + gx
                    py = green_y + gy

                    # Convert to screen coords
                    screen_x = canvas_rect.x + px * canvas_scale - canvas_offset_x
                    screen_y = canvas_rect.y + py * canvas_scale - canvas_offset_y

                    if canvas_rect.collidepoint(screen_x, screen_y):
                        pygame.draw.rect(screen, GREEN_OVERLAY_COLOR,
                                       (screen_x, screen_y, canvas_scale, canvas_scale))

    @staticmethod
    def render_terrain_sprites(
        screen: Surface,
        view_state: ViewState,
        sprites: Dict[str, Sprite],
        hole_data: HoleData,
        selected_flag_index: int,
    ):
        """
        Render flag, tee, and ball sprites on terrain view.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            sprites: Dictionary of loaded sprites
            hole_data: Hole data containing metadata
            selected_flag_index: Which flag position to render (0-3)
        """
        if not hole_data.metadata:
            return

        canvas_rect = view_state.canvas_rect
        canvas_scale = view_state.scale
        canvas_offset_x = view_state.offset_x
        canvas_offset_y = view_state.offset_y

        def to_screen(px: int, py: int) -> Tuple[int, int]:
            """Convert game pixel coords to screen coords."""
            sx = canvas_rect.x + px * canvas_scale - canvas_offset_x
            sy = canvas_rect.y + py * canvas_scale - canvas_offset_y
            return sx, sy

        # Tee blocks
        if sprites.get("tee"):
            tee = hole_data.metadata.get("tee", {})
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)
            sx, sy = to_screen(tee_x, tee_y)
            sprites["tee"].render(screen, sx, sy, canvas_scale)

        # Ball at tee
        if sprites.get("ball"):
            tee = hole_data.metadata.get("tee", {})
            tee_x = tee.get("x", 0)
            tee_y = tee.get("y", 0)

            sx, sy = to_screen(tee_x, tee_y)
            sprites["ball"].render(screen, sx, sy, canvas_scale)

        # Flag
        if sprites.get("flag"):
            flag_positions = hole_data.metadata.get("flag_positions", [])
            if flag_positions and 0 <= selected_flag_index < len(flag_positions):
                flag_pos = flag_positions[selected_flag_index]
                green_flag_x = flag_pos.get("x_offset", 0)
                green_flag_y = flag_pos.get("y_offset", 0)

                flag_x = hole_data.green_x + (green_flag_x // 8)
                flag_y = hole_data.green_y + (green_flag_y // 8)
                sx, sy = to_screen(flag_x, flag_y)
                sprites["flag"].render(screen, sx, sy, canvas_scale)

    @staticmethod
    def render_greens_sprites(
        screen: Surface,
        view_state: ViewState,
        sprites: Dict[str, Sprite],
        hole_data: HoleData,
        selected_flag_index: int,
    ):
        """
        Render flag and cup on greens detail view.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            sprites: Dictionary of loaded sprites
            hole_data: Hole data containing metadata
            selected_flag_index: Which flag position to render (0-3)
        """
        if not sprites.get("green-cup") or not sprites.get("green-flag"):
            return

        canvas_rect = view_state.canvas_rect
        canvas_scale = view_state.scale
        canvas_offset_x = view_state.offset_x
        canvas_offset_y = view_state.offset_y

        flag_positions = hole_data.metadata.get("flag_positions", [])
        if not flag_positions or not (0 <= selected_flag_index < len(flag_positions)):
            return

        flag_pos = flag_positions[selected_flag_index]

        flag_x = flag_pos.get("x_offset", 0)
        flag_y = flag_pos.get("y_offset", 0)

        screen_x = canvas_rect.x + flag_x * canvas_scale - canvas_offset_x
        screen_y = canvas_rect.y + flag_y * canvas_scale - canvas_offset_y

        sprites["green-cup"].render(screen, screen_x, screen_y, canvas_scale)
        sprites["green-flag"].render(screen, screen_x, screen_y, canvas_scale)
