"""
Metadata editor tool for editing hole par and distance.

Opens a modal dialog when activated.
"""

import pygame

from editor.ui.metadata_dialog import MetadataDialog

from .base_tool import ToolContext, ToolResult


class MetadataEditorTool:
    """
    Metadata editor tool - opens dialog for editing par and distance.

    The tool owns a MetadataDialog that provides text entry for numeric metadata.
    Undo state is pushed once when the dialog is opened, so all changes can be
    reverted with a single Undo.
    """

    def __init__(self):
        self.dialog: MetadataDialog | None = None
        self.undo_pushed: bool = False

    def handle_mouse_down(self, pos, button, modifiers, context):
        if self.dialog:
            # Delegate to dialog
            if self.dialog.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)):
                # Dialog wants to close
                return self._close_dialog(context)
        return ToolResult.handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        if self.dialog:
            # Delegate to dialog
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=modifiers, unicode=pygame.key.name(key))
            # Need to set unicode properly for printable keys
            if 32 <= key <= 126:  # Printable ASCII range
                event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=modifiers, unicode=chr(key))

            if self.dialog.handle_event(event):
                # Dialog wants to close
                return self._close_dialog(context)
        return ToolResult.handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        """Called when tool becomes active - create dialog and push undo state."""
        # Push undo state once for entire dialog session
        if not self.undo_pushed:
            context.state.undo_manager.push_state(context.hole_data)
            self.undo_pushed = True

        # Create dialog
        self.dialog = MetadataDialog(
            context.screen_width,
            context.screen_height,
            context.hole_data,
            pygame.font.Font(None, 24),  # Use default font
        )

    def on_deactivated(self, context):
        """Called when tool is deactivated - close dialog."""
        self.dialog = None
        self.undo_pushed = False

    def reset(self):
        """Reset tool state."""
        self.dialog = None
        self.undo_pushed = False

    def get_hotkey(self) -> int | None:
        """Return 'D' key for Data/metadata editing."""
        return pygame.K_d

    def _close_dialog(self, context: ToolContext) -> ToolResult:
        """Close dialog and return appropriate result."""
        if self.dialog:
            if self.dialog.saved:
                # Changes were saved
                message = f"Metadata updated: Par={self.dialog.par_value}, Distance={self.dialog.distance_value}"
                self.dialog = None
                self.undo_pushed = False
                return ToolResult.modified(message=message)
            else:
                # Dialog was cancelled
                self.dialog = None
                self.undo_pushed = False
                return ToolResult(handled=True, message="Metadata edit cancelled")

        return ToolResult.handled()

    def render_overlay(self, screen):
        """Render dialog overlay if active."""
        if self.dialog:
            self.dialog.render(screen)
