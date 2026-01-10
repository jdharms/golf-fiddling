"""
Selection tool for rectangular selection with cut/copy/paste operations.
"""

import pygame
from pygame import Rect

from editor.controllers.view_state import ViewState
from editor.core.constants import (
    CANVAS_OFFSET_X,
    CANVAS_OFFSET_Y,
    GREENS_HEIGHT,
    GREENS_WIDTH,
    STATUS_HEIGHT,
    TERRAIN_WIDTH,
)
from editor.data import ClipboardData

from .base_tool import ToolContext, ToolResult


class SelectionToolState:
    """State for selection drag operation and paste mode."""

    def __init__(self):
        self.is_selecting = False
        self.selection_start: tuple[int, int] | None = None  # (row, col)
        self.selection_end: tuple[int, int] | None = None  # (row, col)
        self.paste_mode = False

    def start_selection(self, tile_pos: tuple[int, int]):
        """Start a new selection."""
        self.is_selecting = True
        self.selection_start = tile_pos
        self.selection_end = tile_pos

    def update_selection(self, tile_pos: tuple[int, int]):
        """Update selection end point."""
        if self.is_selecting:
            self.selection_end = tile_pos

    def finalize_selection(self):
        """Finalize the selection."""
        self.is_selecting = False

    def get_selection_rect(self) -> tuple[int, int, int, int] | None:
        """
        Get selection rectangle as (start_row, start_col, end_row, end_col).

        Returns None if no selection.
        """
        if self.selection_start is None or self.selection_end is None:
            return None

        start_row, start_col = self.selection_start
        end_row, end_col = self.selection_end

        # Ensure correct order
        if start_row > end_row:
            start_row, end_row = end_row, start_row
        if start_col > end_col:
            start_col, end_col = end_col, start_col

        return (start_row, start_col, end_row, end_col)

    def clear_selection(self):
        """Clear the selection."""
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False

    def reset(self):
        """Reset all state."""
        self.clear_selection()
        self.paste_mode = False


class SelectionTool:
    """Selection tool - rectangular selection with cut/copy/paste."""

    def __init__(self):
        self.state = SelectionToolState()

    def handle_mouse_down(self, pos, button, modifiers, context):
        # Right click: Clear selection/paste
        if button == 3:
            return self._clear_selection_or_paste(context)

        if button != 1:  # Only left click
            return ToolResult.not_handled()

        # Create view state for coordinate conversion
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT,
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        mode = context.state.mode

        # If in paste mode, commit paste
        if self.state.paste_mode:
            return self._commit_paste(view_state, pos, context)

        # Otherwise, start new selection
        tile = view_state.screen_to_tile(pos)
        if tile:
            # Clear previous selection
            context.highlight_state.selection_rect = None
            context.highlight_state.selection_mode = None

            self.state.start_selection(tile)
            return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        if button == 1 and self.state.is_selecting:
            # Finalize selection and update highlight state
            self.state.finalize_selection()
            sel_rect = self.state.get_selection_rect()

            if sel_rect:
                start_row, start_col, end_row, end_col = sel_rect
                width = end_col - start_col + 1
                height = end_row - start_row + 1

                context.highlight_state.selection_rect = (
                    start_row,
                    start_col,
                    width,
                    height,
                )
                context.highlight_state.selection_mode = context.state.mode

            return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        # Create view state for coordinate conversion
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT,
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        # Update selection drag
        if self.state.is_selecting:
            tile = view_state.screen_to_tile(pos)
            if tile:
                self.state.update_selection(tile)

                # Update highlight state for preview
                sel_rect = self.state.get_selection_rect()
                if sel_rect:
                    start_row, start_col, end_row, end_col = sel_rect
                    width = end_col - start_col + 1
                    height = end_row - start_row + 1

                    context.highlight_state.selection_rect = (
                        start_row,
                        start_col,
                        width,
                        height,
                    )
                    context.highlight_state.selection_mode = context.state.mode

            return ToolResult.handled()

        # Update paste preview position
        if self.state.paste_mode:
            tile = view_state.screen_to_tile(pos)
            if tile:
                context.highlight_state.paste_preview_pos = tile
            return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        # Ctrl+C: Copy
        if key == pygame.K_c and (modifiers & pygame.KMOD_CTRL):
            return self._copy_selection(context)

        # Ctrl+X: Cut
        if key == pygame.K_x and (modifiers & pygame.KMOD_CTRL):
            return self._cut_selection(context)

        # Ctrl+V: Paste
        if key == pygame.K_v and (modifiers & pygame.KMOD_CTRL):
            return self._start_paste(context)

        # Delete: Delete selection
        if key == pygame.K_DELETE:
            return self._delete_selection(context)

        # Esc: Clear selection or cancel paste
        if key == pygame.K_ESCAPE:
            return self._clear_selection_or_paste(context)

        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        self.reset()
        # Clear highlight state
        context.highlight_state.selection_rect = None
        context.highlight_state.selection_mode = None
        context.highlight_state.paste_preview_pos = None
        context.state.paste_preview_active = False

    def reset(self):
        self.state.reset()

    def get_hotkey(self) -> int | None:
        """Return 'S' key for Selection tool."""
        return pygame.K_s

    def _copy_selection(self, context: ToolContext) -> ToolResult:
        """Copy selected region to clipboard."""
        sel_rect = self.state.get_selection_rect()

        if not sel_rect:
            return ToolResult(handled=True, message="No selection to copy")

        # Create clipboard if it doesn't exist
        if context.state.clipboard is None:
            context.state.clipboard = ClipboardData()

        # Copy region to clipboard
        success = context.state.clipboard.copy_region(
            context.hole_data, sel_rect, context.state.mode
        )

        if success:
            width = context.state.clipboard.width
            height = context.state.clipboard.height
            return ToolResult(
                handled=True, message=f"Copied {width}x{height} region to clipboard"
            )
        else:
            return ToolResult(handled=True, message="Failed to copy region")

    def _cut_selection(self, context: ToolContext) -> ToolResult:
        """Copy selected region to clipboard and fill with default tile."""
        # First, copy
        copy_result = self._copy_selection(context)

        if not copy_result.handled or "Failed" in copy_result.message:
            return copy_result

        # Then, delete (fill with default tile)
        sel_rect = self.state.get_selection_rect()
        if not sel_rect:
            return ToolResult(handled=True, message="No selection to cut")

        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Fill selection with default tile
        start_row, start_col, end_row, end_col = sel_rect
        default_tile = 0x100 if context.state.mode == "terrain" else 0xB0

        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                if context.state.mode == "terrain":
                    if 0 <= row < len(context.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                        context.hole_data.set_terrain_tile(row, col, default_tile)
                else:  # greens
                    if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                        context.hole_data.set_greens_tile(row, col, default_tile)

        width = context.state.clipboard.width if context.state.clipboard else 0
        height = context.state.clipboard.height if context.state.clipboard else 0
        return ToolResult.modified(
            terrain=(context.state.mode == "terrain"),
            message=f"Cut {width}x{height} region to clipboard",
        )

    def _delete_selection(self, context: ToolContext) -> ToolResult:
        """Fill selected region with default tile."""
        sel_rect = self.state.get_selection_rect()

        if not sel_rect:
            return ToolResult(handled=True, message="No selection to delete")

        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Fill selection with default tile
        start_row, start_col, end_row, end_col = sel_rect
        default_tile = 0x100 if context.state.mode == "terrain" else 0x29

        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                if context.state.mode == "terrain":
                    if 0 <= row < len(context.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                        context.hole_data.set_terrain_tile(row, col, default_tile)
                else:  # greens
                    if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                        context.hole_data.set_greens_tile(row, col, default_tile)

        width = end_col - start_col + 1
        height = end_row - start_row + 1
        return ToolResult.modified(
            terrain=(context.state.mode == "terrain"),
            message=f"Deleted {width}x{height} region",
        )

    def _start_paste(self, context: ToolContext) -> ToolResult:
        """Enter paste preview mode."""
        if context.state.clipboard is None or context.state.clipboard.is_empty():
            return ToolResult(handled=True, message="Clipboard is empty")

        # Check mode compatibility
        if context.state.clipboard.mode != context.state.mode:
            return ToolResult(
                handled=True,
                message=f"Cannot paste {context.state.clipboard.mode} clipboard into {context.state.mode} mode",
            )

        # Enter paste mode
        self.state.paste_mode = True
        context.state.paste_preview_active = True

        # Clear selection
        self.state.clear_selection()
        context.highlight_state.selection_rect = None

        width = context.state.clipboard.width
        height = context.state.clipboard.height
        return ToolResult(
            handled=True, message=f"Paste {width}x{height} region (click to place, Esc to cancel)"
        )

    def _commit_paste(
        self, view_state: ViewState, pos: tuple[int, int], context: ToolContext
    ) -> ToolResult:
        """Commit paste at cursor position."""
        if context.state.clipboard is None or context.state.clipboard.is_empty():
            self.state.paste_mode = False
            context.state.paste_preview_active = False
            return ToolResult(handled=True, message="Clipboard is empty")

        tile = view_state.screen_to_tile(pos)
        if not tile:
            return ToolResult.handled()

        paste_row, paste_col = tile

        # Push undo state before modification
        context.state.undo_manager.push_state(context.hole_data)

        # Apply clipboard tiles
        tiles_pasted = 0
        for row_offset in range(context.state.clipboard.height):
            for col_offset in range(context.state.clipboard.width):
                target_row = paste_row + row_offset
                target_col = paste_col + col_offset

                tile_value = context.state.clipboard.get_tile(row_offset, col_offset)

                # Skip transparent tiles (None values)
                if tile_value is None:
                    continue

                # Paste based on mode
                if context.state.mode == "terrain":
                    if 0 <= target_row < len(context.hole_data.terrain) and 0 <= target_col < TERRAIN_WIDTH:
                        context.hole_data.set_terrain_tile(
                            target_row, target_col, tile_value
                        )
                        tiles_pasted += 1
                else:  # greens
                    if 0 <= target_row < GREENS_HEIGHT and 0 <= target_col < GREENS_WIDTH:
                        context.hole_data.set_greens_tile(
                            target_row, target_col, tile_value
                        )
                        tiles_pasted += 1

        # Stay in paste mode for multiple pastes
        # User can press Esc or right-click to exit paste mode

        return ToolResult.modified(
            terrain=(context.state.mode == "terrain"),
            message=f"Pasted {tiles_pasted} tiles (click to paste again, Esc/right-click to cancel)",
        )

    def _cancel_paste(self, context: ToolContext):
        """Cancel paste mode."""
        self.state.paste_mode = False
        context.state.paste_preview_active = False
        context.highlight_state.paste_preview_pos = None

    def _clear_selection_or_paste(self, context: ToolContext) -> ToolResult:
        """Clear selection or cancel paste mode."""
        if self.state.paste_mode:
            self._cancel_paste(context)
            return ToolResult(handled=True, message="Paste cancelled")
        else:
            self.state.clear_selection()
            context.highlight_state.selection_rect = None
            context.highlight_state.selection_mode = None
            return ToolResult(handled=True, message="Selection cleared")
