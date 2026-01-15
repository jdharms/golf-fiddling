"""
NES Open Tournament Golf - Greens Renderer

Renders greens editing canvas view.
"""


import math

import pygame
from pygame import Surface

from editor.controllers.highlight_state import HighlightState
from editor.controllers.view_state import ViewState
from editor.core.constants import GREENS_HEIGHT, GREENS_WIDTH, TILE_SIZE
from golf.formats.hole_data import HoleData

from .font_cache import get_font
from .grid_renderer import GridRenderer
from .highlight_utils import draw_tile_border
from .render_context import RenderContext
from .selection_renderer import SelectionRenderer
from .sprite_renderer import SpriteRenderer


class GreensRenderer:
    """Renders greens editing canvas view."""

    @staticmethod
    def render(
        screen: Surface,
        view_state: ViewState,
        hole_data: HoleData,
        render_ctx: RenderContext,
        highlight_state: HighlightState,
    ):
        """
        Render greens editing view.

        Args:
            screen: Pygame surface to draw on
            view_state: Viewport camera and coordinate transformations
            hole_data: Hole data to render
            render_ctx: Rendering resources and settings
            highlight_state: Visual highlights and preview state
        """
        if not hole_data.greens:
            return

        canvas_rect = view_state.canvas_rect
        canvas_offset_x = view_state.offset_x
        canvas_offset_y = view_state.offset_y
        canvas_scale = view_state.scale
        tile_size = view_state.tile_size
        tileset = render_ctx.tileset
        sprites = render_ctx.sprites
        show_grid = render_ctx.show_grid
        selected_flag_index = render_ctx.selected_flag_index
        transform_state = highlight_state.transform_state
        shift_hover_tile = highlight_state.shift_hover_tile

        # Render greens tiles
        for row_idx, row in enumerate(hole_data.greens):
            for col_idx, tile_idx in enumerate(row):
                x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                tile_surf = tileset.render_tile_greens(tile_idx, canvas_scale)
                screen.blit(tile_surf, (x, y))

        # Render shift-hover highlights (AFTER base tiles, BEFORE transform preview)
        if shift_hover_tile is not None:
            GreensRenderer._render_shift_hover_highlights(
                screen,
                canvas_rect,
                hole_data,
                shift_hover_tile,
                canvas_scale,
                canvas_offset_x,
                canvas_offset_y,
            )

        # Render transform preview with gold borders (ON TOP of tiles)
        if transform_state.is_active:
            GreensRenderer._render_transform_preview(
                screen,
                canvas_rect,
                hole_data,
                tileset,
                transform_state.preview_changes,
                transform_state.origin_tile,
                canvas_scale,
                canvas_offset_x,
                canvas_offset_y,
            )

        # Render flag-cup sprite
        SpriteRenderer.render_greens_sprites(
            screen,
            view_state,
            sprites,
            hole_data,
            selected_flag_index,
            highlight_state.position_tool_selected,
        )

        # Render measurement overlay
        if highlight_state.measure_points:
            GreensRenderer._render_measurement_overlay(
                screen,
                view_state.canvas_rect,
                highlight_state.measure_points,
                view_state.scale,
                view_state.offset_x,
                view_state.offset_y,
            )

        # Render selection rectangle
        if highlight_state.selection_rect and highlight_state.selection_mode == "greens":
            SelectionRenderer.render_selection_rect(
                screen,
                highlight_state,
                view_state.offset_x,
                view_state.offset_y,
                view_state.scale,
            )

        # Render paste preview
        if highlight_state.paste_preview_pos and render_ctx.state.paste_preview_active:
            SelectionRenderer.render_paste_preview(
                screen,
                highlight_state,
                render_ctx.state.clipboard,
                hole_data,
                tileset,
                view_state.offset_x,
                view_state.offset_y,
                view_state.scale,
                "greens",
            )

        # Render stamp preview
        if highlight_state.stamp_preview_pos and highlight_state.current_stamp:
            from editor.rendering.stamp_renderer import StampRenderer
            StampRenderer.render_stamp_preview(
                screen,
                highlight_state,
                hole_data,
                tileset,
                view_state.offset_x,
                view_state.offset_y,
                view_state.scale,
                "greens",
            )

        # Render fringe generation path overlay
        if highlight_state.fringe_path:
            GreensRenderer._render_fringe_path_overlay(
                screen,
                canvas_rect,
                view_state,
                highlight_state,
            )

        # Render grid
        if show_grid:
            GridRenderer.render(screen, view_state, GREENS_WIDTH, GREENS_HEIGHT)

    @staticmethod
    def _render_transform_preview(
        screen,
        canvas_rect,
        hole_data,
        tileset,
        preview_changes,
        origin_tile,
        canvas_scale,
        canvas_offset_x,
        canvas_offset_y,
    ):
        """Render preview tiles with their transformed values and gold borders."""
        tile_size = TILE_SIZE * canvas_scale

        # Render preview tiles with their transformed values
        for (row, col), transformed_tile_idx in preview_changes.items():
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Cull off-screen tiles
            if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                continue
            if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                continue

            # Render the transformed tile
            tile_surf = tileset.render_tile_greens(transformed_tile_idx, canvas_scale)
            screen.blit(tile_surf, (x, y))

            # Draw gold border around tile
            draw_tile_border(screen, x, y, tile_size)

        # Render border around origin tile
        if origin_tile:
            row, col = origin_tile
            x = canvas_rect.x + col * tile_size - canvas_offset_x
            y = canvas_rect.y + row * tile_size - canvas_offset_y

            # Only render if on-screen
            if not (
                x + tile_size < canvas_rect.x
                or x > canvas_rect.right
                or y + tile_size < canvas_rect.y
                or y > canvas_rect.bottom
            ):
                draw_tile_border(screen, x, y, tile_size)

    @staticmethod
    def _render_shift_hover_highlights(
        screen,
        canvas_rect,
        hole_data,
        highlight_tile_value,
        canvas_scale,
        canvas_offset_x,
        canvas_offset_y,
    ):
        """Render gold borders around all tiles matching the shift-hovered tile value."""
        if not hole_data.greens:
            return

        tile_size = TILE_SIZE * canvas_scale

        for row_idx, row in enumerate(hole_data.greens):
            for col_idx, tile_idx in enumerate(row):
                # Only highlight if tile matches the hovered value
                if tile_idx != highlight_tile_value:
                    continue

                x = canvas_rect.x + col_idx * tile_size - canvas_offset_x
                y = canvas_rect.y + row_idx * tile_size - canvas_offset_y

                # Cull off-screen tiles
                if x + tile_size < canvas_rect.x or x > canvas_rect.right:
                    continue
                if y + tile_size < canvas_rect.y or y > canvas_rect.bottom:
                    continue

                # Draw gold border
                draw_tile_border(screen, x, y, tile_size)

    @staticmethod
    def _render_measurement_overlay(
        screen,
        canvas_rect,
        measure_points,
        canvas_scale,
        canvas_offset_x,
        canvas_offset_y,
    ):
        """Render measurement lines and distance labels."""
        if not measure_points or len(measure_points) == 0:
            return

        # Line and point colors for visibility
        line_color = (0, 255, 255)  # Cyan
        point_color = (255, 255, 0)  # Yellow

        # Create ViewState for coordinate conversion
        view_state = ViewState(canvas_rect, canvas_offset_x, canvas_offset_y, canvas_scale)

        # Convert game pixel positions to screen positions
        screen_points = []
        for game_pixel_pos in measure_points:
            screen_pos = view_state.game_pixels_to_screen(game_pixel_pos)
            screen_points.append(screen_pos)

        # Draw lines between consecutive pairs
        font = get_font("monospace", 12)

        for i in range(len(screen_points) - 1):
            p1_screen = screen_points[i]
            p2_screen = screen_points[i + 1]
            p1_game = measure_points[i]
            p2_game = measure_points[i + 1]

            # Check if line is visible (either endpoint on screen)
            p1_visible = (
                canvas_rect.left <= p1_screen[0] <= canvas_rect.right
                and canvas_rect.top <= p1_screen[1] <= canvas_rect.bottom
            )
            p2_visible = (
                canvas_rect.left <= p2_screen[0] <= canvas_rect.right
                and canvas_rect.top <= p2_screen[1] <= canvas_rect.bottom
            )

            if not (p1_visible or p2_visible):
                continue  # Skip off-screen lines

            # Draw line
            pygame.draw.line(screen, line_color, p1_screen, p2_screen, 2)

            # Calculate distance in yards
            dx = p2_game[0] - p1_game[0]
            dy = p2_game[1] - p1_game[1]
            distance_yards = math.sqrt(dx * dx + dy * dy) * 2

            # Draw label at midpoint
            mid_x = (p1_screen[0] + p2_screen[0]) // 2
            mid_y = (p1_screen[1] + p2_screen[1]) // 2

            label_text = f"{distance_yards:.1f}y"
            label_surf = font.render(label_text, True, (255, 255, 255))

            # Draw background rectangle for readability
            label_rect = label_surf.get_rect(center=(mid_x, mid_y))
            bg_rect = label_rect.inflate(4, 2)
            pygame.draw.rect(screen, (0, 0, 0), bg_rect)
            pygame.draw.rect(screen, line_color, bg_rect, 1)

            screen.blit(label_surf, label_rect)

        # Draw points (on top of lines)
        for screen_x, screen_y in screen_points:
            # Check if point is visible
            if not (
                canvas_rect.left <= screen_x <= canvas_rect.right
                and canvas_rect.top <= screen_y <= canvas_rect.bottom
            ):
                continue

            # Draw point as filled circle with black outline
            pygame.draw.circle(screen, point_color, (screen_x, screen_y), 4)
            pygame.draw.circle(screen, (0, 0, 0), (screen_x, screen_y), 4, 1)

    @staticmethod
    def _render_fringe_path_overlay(
        screen: Surface,
        canvas_rect,
        view_state: ViewState,
        highlight_state: HighlightState,
    ):
        """Render fringe generation path overlay."""
        if not highlight_state.fringe_path:
            return

        tile_size = int(TILE_SIZE * view_state.scale)

        # Render path tiles with green border
        for row, col in highlight_state.fringe_path:
            screen_pos = view_state.tile_to_screen((row, col))
            if screen_pos is None:
                continue
            rect = pygame.Rect(screen_pos[0], screen_pos[1], tile_size, tile_size)
            pygame.draw.rect(screen, (0, 255, 0), rect, 2)  # Green, 2px border

        # Render initial position with thicker, brighter border
        if highlight_state.fringe_initial_pos:
            row, col = highlight_state.fringe_initial_pos
            screen_pos = view_state.tile_to_screen((row, col))
            if screen_pos is not None:
                rect = pygame.Rect(screen_pos[0], screen_pos[1], tile_size, tile_size)
                pygame.draw.rect(screen, (0, 255, 128), rect, 4)  # Bright green, 4px border

        # Render current position with yellow border
        if highlight_state.fringe_current_pos:
            row, col = highlight_state.fringe_current_pos
            screen_pos = view_state.tile_to_screen((row, col))
            if screen_pos is not None:
                rect = pygame.Rect(screen_pos[0], screen_pos[1], tile_size, tile_size)
                pygame.draw.rect(screen, (255, 255, 0), rect, 3)  # Yellow, 3px border
