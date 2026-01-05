"""
Stamp creation dialog for creating stamps from selections.

Allows user to:
- Preview selected region
- Mark tiles as transparent by clicking them
- Optionally name the stamp
- Choose category
- Save or cancel
"""

import pygame
from pygame import Rect, Surface

from editor.core.constants import (
    COLOR_BUTTON,
    COLOR_BUTTON_HOVER,
    COLOR_GRID,
    COLOR_PICKER_BG,
    COLOR_SELECTION,
    COLOR_TEXT,
    TILE_SIZE,
)
from editor.core.pygame_rendering import Tileset
from editor.data import ClipboardData, StampData, StampMetadata


class StampCreationDialog:
    """Modal dialog for creating stamps from clipboard data."""

    # Checkered pattern colors for transparent tiles
    TRANSPARENT_COLOR1 = (100, 100, 100)
    TRANSPARENT_COLOR2 = (140, 140, 140)

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        clipboard_data: ClipboardData,
        tileset: Tileset,
        font: pygame.font.Font,
    ):
        """
        Initialize stamp creation dialog.

        Args:
            screen_width: Screen width
            screen_height: Screen height
            clipboard_data: ClipboardData to create stamp from
            tileset: Tileset for rendering tiles
            font: Pygame font for rendering text
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.clipboard_data = clipboard_data
        self.tileset = tileset
        self.font = font

        # Dialog dimensions
        self.dialog_width = min(800, screen_width - 100)
        self.dialog_height = min(600, screen_height - 100)
        self.dialog_rect = Rect(
            (screen_width - self.dialog_width) // 2,
            (screen_height - self.dialog_height) // 2,
            self.dialog_width,
            self.dialog_height,
        )

        # Transparency mask (True = transparent, False = opaque)
        self.transparency_mask = [
            [False for _ in range(clipboard_data.width)]
            for _ in range(clipboard_data.height)
        ]

        # User input
        self.stamp_name = ""
        self.category = "user"
        self.name_input_active = False

        # Categories
        self.categories = ["user", "terrain", "water", "bunker", "green"]

        # Calculate layout
        self._calculate_layout()

        # Result
        self.result: StampData | None = None
        self.cancelled = False

    def _calculate_layout(self):
        """Calculate layout rectangles."""
        margin = 20
        button_height = 40

        # Title
        self.title_y = self.dialog_rect.y + margin

        # Preview area (centered)
        preview_scale = 3
        preview_width = self.clipboard_data.width * TILE_SIZE * preview_scale
        preview_height = self.clipboard_data.height * TILE_SIZE * preview_scale
        self.preview_rect = Rect(
            self.dialog_rect.centerx - preview_width // 2,
            self.title_y + 40,
            preview_width,
            preview_height,
        )
        self.preview_scale = preview_scale

        # Name input
        input_y = self.preview_rect.bottom + margin
        self.name_label_rect = Rect(
            self.dialog_rect.x + margin,
            input_y,
            200,
            30,
        )
        self.name_input_rect = Rect(
            self.name_label_rect.right + 10,
            input_y,
            self.dialog_width - 230 - margin * 2,
            30,
        )

        # Category dropdown
        category_y = input_y + 40
        self.category_label_rect = Rect(
            self.dialog_rect.x + margin,
            category_y,
            200,
            30,
        )
        self.category_button_rect = Rect(
            self.category_label_rect.right + 10,
            category_y,
            200,
            30,
        )

        # Buttons
        button_width = 100
        button_y = self.dialog_rect.bottom - margin - button_height
        self.save_button_rect = Rect(
            self.dialog_rect.centerx - button_width - 10,
            button_y,
            button_width,
            button_height,
        )
        self.cancel_button_rect = Rect(
            self.dialog_rect.centerx + 10,
            button_y,
            button_width,
            button_height,
        )

        # Category dropdown menu (shown when category button clicked)
        self.category_dropdown_visible = False
        self.category_dropdown_rects = []
        dropdown_y = self.category_button_rect.bottom
        for i, cat in enumerate(self.categories):
            self.category_dropdown_rects.append(
                Rect(
                    self.category_button_rect.x,
                    dropdown_y + i * 30,
                    200,
                    30,
                )
            )

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if dialog should close."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check buttons
            if self.save_button_rect.collidepoint(event.pos):
                self._save_stamp()
                return True
            elif self.cancel_button_rect.collidepoint(event.pos):
                self.cancelled = True
                return True

            # Check category dropdown
            if self.category_dropdown_visible:
                for i, rect in enumerate(self.category_dropdown_rects):
                    if rect.collidepoint(event.pos):
                        self.category = self.categories[i]
                        self.category_dropdown_visible = False
                        return False
                # Click outside dropdown closes it
                self.category_dropdown_visible = False
            elif self.category_button_rect.collidepoint(event.pos):
                self.category_dropdown_visible = True
                return False

            # Check name input
            if self.name_input_rect.collidepoint(event.pos):
                self.name_input_active = True
            else:
                self.name_input_active = False

            # Check preview grid (toggle transparency)
            if self.preview_rect.collidepoint(event.pos):
                self._toggle_transparency_at(event.pos)

        elif event.type == pygame.KEYDOWN:
            if self.name_input_active:
                if event.key == pygame.K_BACKSPACE:
                    self.stamp_name = self.stamp_name[:-1]
                elif event.key == pygame.K_RETURN:
                    self.name_input_active = False
                elif event.unicode and event.unicode.isprintable():
                    if len(self.stamp_name) < 50:
                        self.stamp_name += event.unicode
            elif event.key == pygame.K_ESCAPE:
                self.cancelled = True
                return True
            elif event.key == pygame.K_RETURN:
                self._save_stamp()
                return True

        return False

    def _toggle_transparency_at(self, pos: tuple[int, int]):
        """Toggle transparency of tile at screen position."""
        local_x = pos[0] - self.preview_rect.x
        local_y = pos[1] - self.preview_rect.y

        tile_size = TILE_SIZE * self.preview_scale
        col = local_x // tile_size
        row = local_y // tile_size

        if 0 <= row < self.clipboard_data.height and 0 <= col < self.clipboard_data.width:
            self.transparency_mask[row][col] = not self.transparency_mask[row][col]

    def _save_stamp(self):
        """Create StampData from current settings."""
        # Create tiles array with transparency
        tiles = []
        for row in range(self.clipboard_data.height):
            tile_row = []
            for col in range(self.clipboard_data.width):
                if self.transparency_mask[row][col]:
                    tile_row.append(None)  # Transparent
                else:
                    tile_row.append(self.clipboard_data.get_tile(row, col))
            tiles.append(tile_row)

        # Create metadata (ID auto-generated if name is empty)
        metadata = StampMetadata(
            name=self.stamp_name,
            category=self.category,
        )

        # Create StampData
        self.result = StampData()
        self.result.tiles = tiles
        self.result.attributes = self.clipboard_data.attributes
        self.result.width = self.clipboard_data.width
        self.result.height = self.clipboard_data.height
        self.result.mode = self.clipboard_data.mode
        self.result.metadata = metadata

    def render(self, screen: Surface):
        """Render the dialog."""
        # Semi-transparent overlay
        overlay = Surface((self.screen_width, self.screen_height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Dialog background
        pygame.draw.rect(screen, COLOR_PICKER_BG, self.dialog_rect)
        pygame.draw.rect(screen, COLOR_GRID, self.dialog_rect, 2)

        # Title
        title_surf = self.font.render("Create Stamp", True, COLOR_TEXT)
        title_rect = title_surf.get_rect(centerx=self.dialog_rect.centerx, y=self.title_y)
        screen.blit(title_surf, title_rect)

        # Instructions
        instructions = "Click tiles to toggle transparency (checkered = transparent)"
        instr_surf = self.font.render(instructions, True, COLOR_TEXT)
        instr_rect = instr_surf.get_rect(
            centerx=self.dialog_rect.centerx,
            y=self.title_y + 20,
        )
        screen.blit(instr_surf, instr_rect)

        # Preview grid
        self._render_preview(screen)

        # Name input
        name_label_surf = self.font.render("Name (optional):", True, COLOR_TEXT)
        screen.blit(name_label_surf, self.name_label_rect)

        # Name input box
        input_color = COLOR_SELECTION if self.name_input_active else COLOR_GRID
        pygame.draw.rect(screen, COLOR_BUTTON, self.name_input_rect)
        pygame.draw.rect(screen, input_color, self.name_input_rect, 2)

        name_surf = self.font.render(self.stamp_name or "auto-generated", True, COLOR_TEXT)
        name_rect = name_surf.get_rect(
            left=self.name_input_rect.left + 5,
            centery=self.name_input_rect.centery,
        )
        screen.blit(name_surf, name_rect)

        # Category label and button
        cat_label_surf = self.font.render("Category:", True, COLOR_TEXT)
        screen.blit(cat_label_surf, self.category_label_rect)

        pygame.draw.rect(screen, COLOR_BUTTON, self.category_button_rect)
        pygame.draw.rect(screen, COLOR_GRID, self.category_button_rect, 1)

        cat_surf = self.font.render(self.category.capitalize(), True, COLOR_TEXT)
        cat_rect = cat_surf.get_rect(center=self.category_button_rect.center)
        screen.blit(cat_surf, cat_rect)

        # Category dropdown
        if self.category_dropdown_visible:
            for i, (cat, rect) in enumerate(zip(self.categories, self.category_dropdown_rects)):
                pygame.draw.rect(screen, COLOR_BUTTON_HOVER, rect)
                pygame.draw.rect(screen, COLOR_GRID, rect, 1)
                cat_text_surf = self.font.render(cat.capitalize(), True, COLOR_TEXT)
                cat_text_rect = cat_text_surf.get_rect(center=rect.center)
                screen.blit(cat_text_surf, cat_text_rect)

        # Buttons
        self._render_button(screen, self.save_button_rect, "Save")
        self._render_button(screen, self.cancel_button_rect, "Cancel")

    def _render_preview(self, screen: Surface):
        """Render preview grid with transparency overlay."""
        tile_size = TILE_SIZE * self.preview_scale

        for row in range(self.clipboard_data.height):
            for col in range(self.clipboard_data.width):
                x = self.preview_rect.x + col * tile_size
                y = self.preview_rect.y + row * tile_size

                tile_value = self.clipboard_data.get_tile(row, col)
                is_transparent = self.transparency_mask[row][col]

                if is_transparent:
                    # Draw checkered pattern
                    self._draw_checkered_tile(screen, x, y, tile_size)
                elif tile_value is not None:
                    # Render tile
                    # Use palette 1 for terrain (greens always use palette 0)
                    palette_idx = 0 if self.clipboard_data.mode == "greens" else 1
                    tile_surf = self.tileset.render_tile(
                        tile_value, palette_idx, self.preview_scale
                    )
                    screen.blit(tile_surf, (x, y))

                # Draw grid
                rect = Rect(x, y, tile_size, tile_size)
                pygame.draw.rect(screen, COLOR_GRID, rect, 1)

        # Draw preview border
        pygame.draw.rect(screen, COLOR_SELECTION, self.preview_rect, 2)

    def _draw_checkered_tile(self, surface: Surface, x: int, y: int, size: int):
        """Draw checkered pattern to indicate transparent tile."""
        checker_size = max(size // 4, 2)

        for row in range(0, size, checker_size):
            for col in range(0, size, checker_size):
                if (row // checker_size + col // checker_size) % 2 == 0:
                    color = self.TRANSPARENT_COLOR1
                else:
                    color = self.TRANSPARENT_COLOR2

                rect = Rect(x + col, y + row, checker_size, checker_size)
                pygame.draw.rect(surface, color, rect)

    def _render_button(self, screen: Surface, rect: Rect, text: str):
        """Render a button."""
        is_hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = COLOR_BUTTON_HOVER if is_hovered else COLOR_BUTTON

        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, COLOR_GRID, rect, 1)

        text_surf = self.font.render(text, True, COLOR_TEXT)
        text_rect = text_surf.get_rect(center=rect.center)
        screen.blit(text_surf, text_rect)

    def show(self, screen: Surface, clock: pygame.time.Clock) -> StampData | None:
        """
        Show dialog and run event loop until user saves or cancels.

        Args:
            screen: Pygame screen surface
            clock: Pygame clock for frame rate

        Returns:
            StampData if user saved, None if cancelled
        """
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.cancelled = True
                    running = False
                elif self.handle_event(event):
                    running = False

            self.render(screen)
            pygame.display.flip()
            clock.tick(60)

        return self.result if not self.cancelled else None
