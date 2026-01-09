"""
NES Open Tournament Golf - Editor Application

Main application class that orchestrates all editor components.
"""

from pathlib import Path

import pygame
from pygame import Rect

from golf.core.compressor import load_compression_tables
from golf.formats.hole_data import HoleData

from .controllers.better_forest_fill import BetterForestFiller
from .controllers.editor_state import EditorState
from .controllers.event_handler import EventHandler
from .controllers.highlight_state import HighlightState
from .controllers.stamp_library import StampLibrary
from .controllers.transform_logic import TransformLogic
from .controllers.view_state import ViewState
from .core.constants import *
from .core.pygame_rendering import Sprite, Tileset
from .rendering.greens_renderer import GreensRenderer
from .rendering.render_context import RenderContext
from .rendering.terrain_renderer import TerrainRenderer
from .tools.add_row_tool import AddRowTool
from .tools.cycle_tool import CycleTool
from .tools.eyedropper_tool import EyedropperTool
from .tools.forest_fill_tool import ForestFillTool
from .tools.measure_tool import MeasureTool
from .tools.metadata_editor_tool import MetadataEditorTool
from .tools.paint_tool import PaintTool
from .tools.palette_tool import PaletteTool
from .tools.position_tool import PositionTool
from .tools.remove_row_tool import RemoveRowTool
from .tools.row_operations_tool import RowOperationsTool
from .tools.selection_tool import SelectionTool
from .tools.stamp_tool import StampTool
from .tools.tool_manager import ToolManager
from .tools.transform_tool import TransformTool
from .ui.dialogs import open_file_dialog, save_file_dialog
from .ui.pickers import GreensTilePicker, TilePicker, ToolPicker
from .ui.stamp_browser import StampBrowser
from .ui.toolbar import Toolbar, ToolbarCallbacks


class EditorApplication:
    """Main editor application."""

    def __init__(self, terrain_chr: str, greens_chr: str):
        pygame.init()

        self.screen_width = 1280
        self.screen_height = 1200
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height), pygame.RESIZABLE
        )
        pygame.display.set_caption("NES Open Golf Course Editor")

        self.font = pygame.font.SysFont("monospace", 14)
        self.font_small = pygame.font.SysFont("monospace", 12)

        # Track previous tool for revert behavior (used by dialog tools)
        self.previous_tool_name: str | None = None

        # Load tilesets
        self.terrain_tileset = Tileset(terrain_chr)
        self.greens_tileset = Tileset(greens_chr)

        # Load sprites
        self.sprites: dict[str, Sprite | None] = {}
        sprite_files = {
            "flag": "data/sprites/flag.json",
            "tee": "data/sprites/tee-block.json",
            "ball": "data/sprites/ball.json",
            "green-cup": "data/sprites/green-cup.json",
            "green-flag": "data/sprites/green-flag.json",
        }

        for sprite_name, sprite_path in sprite_files.items():
            try:
                self.sprites[sprite_name] = Sprite(sprite_path)
            except FileNotFoundError:
                print(f"Warning: Sprite file not found: {sprite_path}")
                self.sprites[sprite_name] = None
            except Exception as e:
                print(f"Warning: Failed to load sprite {sprite_name}: {e}")
                self.sprites[sprite_name] = None

        # Load compression tables for transform drag feature
        self.compression_tables = load_compression_tables()
        self.transform_logic = TransformLogic(self.compression_tables)

        # Load terrain neighbor validator
        try:
            from golf.core.neighbor_validator import TerrainNeighborValidator

            self.terrain_neighbor_validator = TerrainNeighborValidator()
        except FileNotFoundError:
            print(
                "Warning: terrain_neighbors.json not found, neighbor validation disabled"
            )
            self.terrain_neighbor_validator = None
        except Exception as e:
            print(f"Warning: Failed to load neighbor validator: {e}")
            self.terrain_neighbor_validator = None


        # Load Forest Filler algorithm
        self.forest_filler = BetterForestFiller()

        # Cache for invalid tiles (performance optimization)
        self.cached_invalid_terrain_tiles = None

        # Create application state
        self.state = EditorState()
        self.hole_data = HoleData()

        # Create highlight state (for visual feedback)
        self.highlight_state = HighlightState()

        # Create pickers first (needed by event handler)
        picker_rect = Rect(
            0,
            TOOLBAR_HEIGHT,
            PICKER_WIDTH,
            self.screen_height - TOOLBAR_HEIGHT - STATUS_HEIGHT,
        )
        self.terrain_picker = TilePicker(
            self.terrain_tileset,
            picker_rect,
            on_hover_change=self._on_terrain_hover_change,
            on_tile_selected=self._on_terrain_tile_selected,
        )
        self.greens_picker = GreensTilePicker(
            self.greens_tileset,
            picker_rect,
            on_hover_change=self._on_greens_hover_change,
            on_tile_selected=self._on_greens_tile_selected,
        )

        # Create tool picker (right sidebar)
        tool_picker_rect = Rect(
            self.screen_width - TOOL_PICKER_WIDTH,
            TOOLBAR_HEIGHT,
            TOOL_PICKER_WIDTH,
            self.screen_height - TOOLBAR_HEIGHT - STATUS_HEIGHT,
        )
        self.tool_picker = ToolPicker(
            tool_picker_rect,
            on_tool_change=self._on_tool_change,
        )
        self.tool_picker.register_tool("paint", "Paint", "🖌")
        self.tool_picker.register_tool("palette", "Palette", "🎨")
        self.tool_picker.register_tool("selection", "Select", "✂")
        self.tool_picker.register_tool("stamp", "Stamp", "📋")
        self.tool_picker.register_tool("transform", "Transform", "↔")
        self.tool_picker.register_tool("forest_fill", "Forest Fill", "🌲")
        self.tool_picker.register_tool("cycle", "Cycle", "🔄")
        self.tool_picker.register_tool("measure", "Measure", "📏")
        self.tool_picker.register_tool("metadata_editor", "Metadata", "📝")
        self.tool_picker.register_tool("position", "Position", "🎯")
        self.tool_picker.register_tool("add_row", "Add Row", "➕", is_action=True)
        self.tool_picker.register_tool("remove_row", "Remove Row", "➖", is_action=True)

        # Create stamp library and browser
        self.stamp_library = StampLibrary()
        self.stamp_library.load_stamps()

        self.stamp_browser = StampBrowser(
            picker_rect,
            self.stamp_library,
            self.font,
            self.terrain_tileset,  # Use terrain tileset for stamp previews
            on_stamp_selected=self._on_stamp_selected,
        )

        # Create tool manager and register tools
        self.tool_manager = ToolManager()
        self.tool_manager.register_tool("paint", PaintTool())
        self.tool_manager.register_tool("selection", SelectionTool())
        self.tool_manager.register_tool("stamp", StampTool())
        self.tool_manager.register_tool("palette", PaletteTool())
        self.tool_manager.register_tool("transform", TransformTool())
        self.tool_manager.register_tool("eyedropper", EyedropperTool())
        self.tool_manager.register_tool("forest_fill", ForestFillTool())
        self.tool_manager.register_tool("cycle", CycleTool())
        self.tool_manager.register_tool("measure", MeasureTool())
        self.tool_manager.register_tool("row_operations", RowOperationsTool())
        self.tool_manager.register_tool("metadata_editor", MetadataEditorTool())
        self.tool_manager.register_tool("position", PositionTool())
        self.tool_manager.register_tool("add_row", AddRowTool())
        self.tool_manager.register_tool("remove_row", RemoveRowTool())

        # Create event handler early (buttons will reference its methods)
        self.event_handler = EventHandler(
            self.state,
            self.hole_data,
            self.terrain_picker,
            self.greens_picker,
            [],  # Empty buttons list initially
            self.screen_width,
            self.screen_height,
            self.tool_manager,
            self.tool_picker,
            self.stamp_browser,
            on_load=self._on_load,
            on_save=self._on_save,
            on_mode_change=self._update_mode_buttons,
            on_flag_change=self._update_flag_buttons,
            on_resize=self._on_resize,
            on_tool_change=self._on_tool_change,
            on_create_stamp=self._on_create_stamp,
            on_terrain_modified=self.invalidate_terrain_validation_cache,
        )

        # Set transform_logic, forest_filler, tool_manager, highlight_state, stamp_library, and revert callback on tool_context (needed by tools)
        self.event_handler.tool_context.transform_logic = self.transform_logic
        self.event_handler.tool_context.forest_filler = self.forest_filler
        self.event_handler.tool_context.tool_manager = self.tool_manager
        self.event_handler.tool_context.highlight_state = self.highlight_state
        self.event_handler.tool_context.stamp_library = self.stamp_library
        self.event_handler.tool_context._on_revert_to_previous_tool = self._revert_to_previous_tool

        # Activate paint tool now that we have context
        self.tool_manager.set_active_tool("paint", self.event_handler.tool_context)

        # Create toolbar with callbacks
        toolbar_callbacks = ToolbarCallbacks(
            on_load=self._on_load,
            on_save=self._on_save,
            on_set_mode=self._set_mode,
            on_toggle_grid=self.state.toggle_grid,
            on_select_flag=self._select_flag,
            on_set_palette=self._set_palette,
            on_toggle_sprites=self.state.toggle_sprites,
        )
        self.toolbar = Toolbar(self.screen_width, toolbar_callbacks)

        # Update event handler with toolbar buttons
        self.event_handler.buttons = self.toolbar.buttons

        self.running = True
        self.clock = pygame.time.Clock()

        # Update button states
        self._update_mode_buttons()
        self._update_flag_buttons()
        self._update_palette_buttons()

    def _set_mode(self, mode: str):
        """Set editing mode."""
        self.state.set_mode(mode)
        self._update_mode_buttons()

    def _on_tool_change(self, tool_name: str | None = None):
        """Handle tool selection change from picker or hotkey."""
        if tool_name is None:
            # Called from hotkey - sync picker selection
            tool_name = self.tool_manager.get_active_tool_name()
            if tool_name:
                self.tool_picker.selected_tool = tool_name
        else:
            # Called from picker or hotkey - activate tool
            current_tool = self.tool_manager.active_tool_name
            self.tool_manager.set_active_tool(tool_name, self.event_handler.tool_context)

            # Check if this was an action tool (active tool didn't change)
            if self.tool_manager.active_tool_name == current_tool:
                # Action tool executed - invalidate cache for terrain modifications
                self.invalidate_terrain_validation_cache()
            else:
                # Normal tool switch - track previous tool for revert
                self.previous_tool_name = current_tool

    def _revert_to_previous_tool(self):
        """Revert to the previously active tool.

        Called by dialog tools (like Metadata Editor) when their dialog closes
        to automatically switch back to the tool that was active before.
        """
        if self.previous_tool_name:
            self.tool_manager.set_active_tool(
                self.previous_tool_name, self.event_handler.tool_context
            )
            # Update picker selection to match
            self.tool_picker.selected_tool = self.previous_tool_name
            # Don't update previous_tool_name here - keep the chain for nested reverts

    def _update_mode_buttons(self):
        """Update mode button active states."""
        mode_buttons = self.toolbar.get_mode_buttons()
        mode_buttons[0].active = self.state.mode == "terrain"
        mode_buttons[1].active = self.state.mode == "greens"
        self._update_flag_buttons()
        self._update_palette_buttons()

    def _select_flag(self, index: int):
        """Select which flag position to display."""
        self.state.select_flag(index)
        self._update_flag_buttons()

    def _update_flag_buttons(self):
        """Update flag button active states."""
        flag_buttons = self.toolbar.get_flag_buttons()
        for i, btn in enumerate(flag_buttons):
            btn.active = i == self.state.selected_flag_index

    def _set_palette(self, palette: int):
        """Set the selected palette."""
        self.state.selected_palette = palette
        self._update_palette_buttons()

    def _update_palette_buttons(self):
        """Update palette button active states."""
        palette_buttons = self.toolbar.get_palette_buttons()
        for i, btn in enumerate(palette_buttons, start=1):
            btn.active = i == self.state.selected_palette


    def _process_tool_result(self, result):
        """Process a tool result (same logic as EventHandler._process_tool_result)."""
        if result.terrain_modified:
            self.invalidate_terrain_validation_cache()
        if result.message:
            print(result.message)

    def invalidate_terrain_validation_cache(self):
        """Invalidate cached invalid tiles (call when terrain is modified)."""
        self.cached_invalid_terrain_tiles = None

    def get_invalid_terrain_tiles(self):
        """Get invalid terrain tiles (cached, recomputes only when needed)."""
        if self.terrain_neighbor_validator is None:
            return set()

        if self.cached_invalid_terrain_tiles is None:
            # Cache miss - recompute
            self.cached_invalid_terrain_tiles = (
                self.terrain_neighbor_validator.get_invalid_tiles(
                    self.hole_data.terrain
                )
            )

        return self.cached_invalid_terrain_tiles

    def _on_load(self):
        """Load a hole file."""
        path = open_file_dialog(
            "Load Hole", [("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            self.hole_data.load(path)
            self.state.reset_canvas_position()
            # Clear undo history when loading new file
            self.state.undo_manager.set_initial_state(self.hole_data)
            # Invalidate cache when loading new hole
            self.invalidate_terrain_validation_cache()

    def _on_save(self):
        """Save the current hole."""
        if self.hole_data.filepath:
            self.hole_data.save()
        else:
            path = save_file_dialog(
                "Save Hole", ".json", [("JSON files", "*.json"), ("All files", "*.*")]
            )
            if path:
                self.hole_data.save(path)

    def _on_resize(self, width: int, height: int):
        """Handle window resize."""
        self.screen_width = width
        self.screen_height = height
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height), pygame.RESIZABLE
        )
        self.toolbar.resize(width)

        # Resize tool picker (right sidebar)
        self.tool_picker.rect = Rect(
            width - TOOL_PICKER_WIDTH,
            TOOLBAR_HEIGHT,
            TOOL_PICKER_WIDTH,
            height - TOOLBAR_HEIGHT - STATUS_HEIGHT,
        )

        self.event_handler.update_screen_size(width, height)

    def _on_terrain_hover_change(self, tile_value: int | None):
        """Called when terrain picker hover changes."""
        if self.state.mode == "terrain":
            if tile_value:
                self.highlight_state.set_picker_hover(tile_value)
            else:
                self.highlight_state.clear_picker_hover()

    def _on_terrain_tile_selected(self, tile_value: int):
        """Called when a tile is selected in terrain picker - auto-switch to paint tool."""
        self.tool_manager.set_active_tool("paint", self.event_handler.tool_context)
        self.tool_picker.selected_tool = "paint"

    def _on_greens_hover_change(self, tile_value: int | None):
        """Called when greens picker hover changes."""
        shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
        if shift_held and self.state.mode == "greens":
            self.highlight_state.set_picker_hover(tile_value)
        else:
            self.highlight_state.clear_picker_hover()

    def _on_greens_tile_selected(self, tile_value: int):
        """Called when a tile is selected in greens picker - auto-switch to paint tool."""
        self.tool_manager.set_active_tool("paint", self.event_handler.tool_context)
        self.tool_picker.selected_tool = "paint"

    def _on_stamp_selected(self, stamp):
        """Called when a stamp is selected in stamp browser - set on stamp tool."""
        # Get stamp tool and set the selected stamp
        stamp_tool = self.tool_manager.get_tool("stamp")
        if stamp_tool:
            stamp_tool.set_stamp(stamp)

        # Ensure stamp tool is active
        if self.tool_manager.get_active_tool_name() != "stamp":
            self.tool_manager.set_active_tool("stamp", self.event_handler.tool_context)
            self.tool_picker.selected_tool = "stamp"

    def _on_create_stamp(self):
        """Called when user presses Ctrl+Shift+S to create stamp from selection."""
        from editor.data import ClipboardData
        from editor.ui.stamp_creation_dialog import StampCreationDialog

        # Check for active selection first (preferred)
        clipboard_data = None
        if self.highlight_state.selection_rect and self.highlight_state.selection_mode == self.state.mode:
            # Create ClipboardData from active selection
            # Convert from (row, col, width, height) to (start_row, start_col, end_row, end_col)
            row, col, width, height = self.highlight_state.selection_rect
            rect_for_copy = (row, col, row + height - 1, col + width - 1)

            clipboard_data = ClipboardData()
            clipboard_data.copy_region(
                self.hole_data,
                rect_for_copy,
                self.state.mode,
            )
        elif self.state.clipboard and not self.state.clipboard.is_empty():
            # Fall back to clipboard if no active selection
            clipboard_data = self.state.clipboard
        else:
            print("No selection to create stamp from - use Selection tool to select a region first")
            return

        # Get appropriate tileset based on mode
        tileset = self.greens_tileset if self.state.mode == "greens" else self.terrain_tileset

        # Create and show dialog
        dialog = StampCreationDialog(
            self.screen_width,
            self.screen_height,
            clipboard_data,
            tileset,
            self.font,
        )

        stamp_data = dialog.show(self.screen, self.clock)

        if stamp_data:
            # Save stamp to library
            save_path = self.stamp_library.save_stamp(stamp_data)
            print(f"Stamp saved to {save_path}")

            # Reload stamps to update browser
            self.stamp_library.load_stamps()

    def _get_canvas_rect(self) -> Rect:
        """Get the canvas drawing area."""
        return Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            self.screen_width - CANVAS_OFFSET_X - TOOL_PICKER_WIDTH,
            self.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT,
        )

    def _screen_to_tile(self, screen_pos: tuple[int, int]) -> tuple[int, int] | None:
        """Convert screen position to tile coordinates."""
        canvas_rect = self._get_canvas_rect()
        if not canvas_rect.collidepoint(screen_pos):
            return None

        local_x = screen_pos[0] - canvas_rect.x + self.state.canvas_offset_x
        local_y = screen_pos[1] - canvas_rect.y + self.state.canvas_offset_y

        tile_size = TILE_SIZE * self.state.canvas_scale
        tile_col = local_x // tile_size
        tile_row = local_y // tile_size

        return (tile_row, tile_col)

    def run(self):
        """Main loop."""
        while self.running:
            events = pygame.event.get()
            self.running = self.event_handler.handle_events(events)

            # Update active tool (for time-based behavior like key repeat)
            active_tool = self.tool_manager.get_active_tool()
            if active_tool and hasattr(active_tool, 'update'):
                result = active_tool.update(self.event_handler.tool_context)
                self._process_tool_result(result)

            self._render()
            self.clock.tick(60)

        pygame.quit()

    def _render(self):
        """Render the editor."""
        self.screen.fill(COLOR_BG)

        # Left sidebar - stamp browser or tile picker
        active_tool = self.tool_manager.get_active_tool_name()
        if active_tool == "stamp":
            # Show stamp browser when stamp tool is active
            self.stamp_browser.render(self.screen, self.state.selected_palette)
        else:
            # Show tile picker for other tools
            if self.state.mode == "greens":
                self.greens_picker.render(self.screen)
            else:
                palette_for_picker = (
                    self.state.selected_palette if self.state.selected_palette > 0 else 1
                )
                self.terrain_picker.render(self.screen, palette_for_picker)

        # Tool picker (right sidebar)
        self.tool_picker.render(self.screen, self.font)

        # Canvas
        self._render_canvas()

        # Toolbar after Canvas so scrolling the Canvas
        # won't cause it to clip into the Toolbar
        self._render_toolbar()

        # Status bar
        self._render_status()

        # Tool overlays (metadata dialog, etc.)
        active_tool = self.tool_manager.get_active_tool()
        if active_tool and hasattr(active_tool, "render_overlay"):
            active_tool.render_overlay(self.screen)

        pygame.display.flip()

    def _render_toolbar(self):
        """Render toolbar with buttons and palette selector."""
        self.toolbar.render(self.screen, self.font, self.font_small)

    def _render_canvas(self):
        """Render the main editing canvas."""
        canvas_rect = self._get_canvas_rect()
        pygame.draw.rect(self.screen, (0, 0, 0), canvas_rect)

        if not self.hole_data.terrain:
            text = self.font.render(
                "No hole loaded. Press Ctrl+O to open.", True, COLOR_TEXT
            )
            self.screen.blit(
                text, (canvas_rect.centerx - text.get_width() // 2, canvas_rect.centery)
            )
            return

        # Create view state
        view_state = ViewState(
            canvas_rect,
            self.state.canvas_offset_x,
            self.state.canvas_offset_y,
            self.state.canvas_scale,
        )

        # Update highlight state
        self.highlight_state.show_invalid_tiles = self.state.show_invalid_tiles
        if self.state.mode == "terrain":
            self.highlight_state.invalid_terrain_tiles = (
                self.get_invalid_terrain_tiles()
            )
        else:
            self.highlight_state.invalid_terrain_tiles = None

        # Get transform state from transform tool
        transform_tool = self.tool_manager.get_tool("transform")
        if transform_tool:
            self.highlight_state.transform_state = transform_tool.state

        # Get measure points from measure tool
        measure_tool = self.tool_manager.get_tool("measure")
        # Only measure in terrain mode
        if measure_tool:
            self.highlight_state.measure_points = (
                measure_tool.points if measure_tool.points and self.state.mode == "terrain" else None
            )

        # Render based on mode
        if self.state.mode == "greens":
            render_ctx = RenderContext(
                self.greens_tileset,
                self.sprites,
                self.state.mode,
                self.state.show_grid,
                self.state.show_sprites,
                self.state.selected_flag_index,
                self.state,  # Add state for clipboard/paste preview access
            )
            GreensRenderer.render(
                self.screen,
                view_state,
                self.hole_data,
                render_ctx,
                self.highlight_state,
            )
        else:
            render_ctx = RenderContext(
                self.terrain_tileset,
                self.sprites,
                self.state.mode,
                self.state.show_grid,
                self.state.show_sprites,
                self.state.selected_flag_index,
                self.state,  # Add state for clipboard/paste preview access
            )
            active_tool_name = self.tool_manager.get_active_tool_name()
            TerrainRenderer.render(
                self.screen,
                view_state,
                self.hole_data,
                render_ctx,
                self.highlight_state,
                active_tool_name,
            )

    def _render_status(self):
        """Render status bar."""
        status_rect = Rect(
            0, self.screen_height - STATUS_HEIGHT, self.screen_width, STATUS_HEIGHT
        )
        pygame.draw.rect(self.screen, COLOR_STATUS, status_rect)

        # Mouse position
        mouse_pos = pygame.mouse.get_pos()

        status_parts = [f"Mode: {self.state.mode.title()}"]

        if self.state.mode == "terrain":
            status_parts.append(
                f"Sprites: {'ON' if self.state.show_sprites else 'OFF'}"
            )
            if self.state.show_sprites and self.hole_data.metadata:
                status_parts.append(f"Flag: {self.state.selected_flag_index + 1}/4")

        # Check picker hover first (priority over canvas)
        picker_hover_tile = None
        if self.state.mode == "greens":
            picker_hover_tile = self.greens_picker.get_hovered_tile()
        else:
            picker_hover_tile = self.terrain_picker.get_hovered_tile()

        if picker_hover_tile is not None:
            # Show picker tile value
            status_parts.append(f"Picker Tile: ${picker_hover_tile:02X}")
        else:
            # Existing canvas hover logic
            tile = self._screen_to_tile(mouse_pos)

            if tile:
                row, col = tile
                status_parts.append(f"Tile: ({col}, {row})")

                if (
                    self.state.mode == "terrain"
                    and 0 <= row < len(self.hole_data.terrain)
                    and 0 <= col < TERRAIN_WIDTH
                ):
                    tile_val = self.hole_data.terrain[row][col]
                    attr_val = self.hole_data.get_attribute(row, col)
                    status_parts.append(f"Value: ${tile_val:02X}")
                    status_parts.append(f"Palette: {attr_val}")

                elif (
                    self.state.mode == "greens"
                    and 0 <= row < len(self.hole_data.greens)
                    and 0 <= col < GREENS_WIDTH
                ):
                    tile_val = self.hole_data.greens[row][col]
                    status_parts.append(f"Value: ${tile_val:02X}")

        if self.hole_data.filepath:
            name = Path(self.hole_data.filepath).name
            modified = "*" if self.hole_data.modified else ""
            status_parts.append(f"File: {name}{modified}")

        # Show tool message (e.g., from Position Tool)
        if self.state.tool_message:
            status_parts.append(self.state.tool_message)

        # Show undo/redo availability
        if self.state.undo_manager.can_undo():
            status_parts.append("Undo:Ctrl+Z")
        if self.state.undo_manager.can_redo():
            status_parts.append("Redo:Ctrl+Y")

        status_text = "  |  ".join(status_parts)
        text_surf = self.font.render(status_text, True, COLOR_TEXT)
        self.screen.blit(text_surf, (10, self.screen_height - STATUS_HEIGHT + 8))

    def load_hole(self, path: str):
        """Load a hole from file path."""
        self.hole_data.load(path)
        self.state.reset_canvas_position()
        # Clear undo history when loading new file
        self.state.undo_manager.set_initial_state(self.hole_data)
