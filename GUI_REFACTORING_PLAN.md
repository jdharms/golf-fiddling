# GUI Refactoring Plan: NES Golf Editor

## Executive Summary

This plan outlines a comprehensive refactoring to prepare the editor for 3-4x growth in complexity. The refactoring addresses parameter explosion, scattered responsibilities, and inconsistent patterns while maintaining the clean tree-based architecture.

**Key Goals:**
1. Extract tools into separate classes (extensible for new tools)
2. Reduce renderer parameter count from 15 to 5
3. Establish three-layer architecture (Input → Coordination → Execution)
4. Create context objects for better organization
5. Implement hover notifications instead of polling

**Estimated Effort:** ~3 weeks (split into 6 phases)

---

## Design Decisions

The following design decisions were made after architectural review:

1. **State Management**: Create smaller context objects (ViewState, RenderContext, HighlightState)
2. **Hover Updates**: Switch from polling to notification/callbacks
3. **Tool Extraction**: Separate tool classes with Protocol interface
4. **Tool Switching**: Support BOTH toolbar buttons AND keyboard shortcuts
5. **Button Management**: Create Toolbar class to manage button layout
6. **Resize Behavior**: Don't recreate components, just update positions
7. **Transform State**: Move to TransformTool class (tools own their state)
8. **Architecture**: Three-layer pattern (EventHandler=input, Application=coordination, Tools=execution)
9. **Coordinate Conversion**: Put screen_to_tile() method on ViewState object

---

## Target Architecture

### Three-Layer Pattern

```
Layer 1: Input Translation (EventHandler)
  - Receives pygame events
  - Routes to tools/components
  - Emits high-level callbacks
  - ~150 lines (down from 420)

Layer 2: Coordination (Application)
  - Receives callbacks
  - Delegates to tools
  - Updates state
  - Invalidates caches
  - ~300 lines (current 480, but better organized)

Layer 3: Execution (Tools)
  - PaintTool (~50 lines)
  - TransformTool (~100 lines)
  - EyedropperTool (~30 lines)
  - ForestFillTool (~50 lines)
```

### File Structure After Refactoring

```
editor/
├── application.py (coordinator)
├── controllers/
│   ├── editor_state.py (state container)
│   ├── view_state.py (NEW: viewport/camera)
│   ├── highlight_state.py (NEW: visual feedback)
│   ├── event_handler.py (input translator)
│   └── undo_manager.py (unchanged)
├── tools/ (NEW)
│   ├── __init__.py
│   ├── base_tool.py (Protocol, ToolContext, ToolResult)
│   ├── tool_manager.py (registration & switching)
│   ├── paint_tool.py
│   ├── transform_tool.py
│   ├── eyedropper_tool.py
│   └── forest_fill_tool.py
├── rendering/
│   ├── render_context.py (NEW: rendering resources bundle)
│   ├── terrain_renderer.py (MODIFIED: 5 params instead of 15)
│   └── greens_renderer.py (MODIFIED: 5 params instead of 13)
└── ui/
    ├── toolbar.py (NEW: button management)
    ├── pickers/ (MODIFIED: add hover callbacks)
    └── widgets.py (unchanged)
```

---

## Phase 1: Create Context Objects (2-3 hours)

### 1.1 Create ViewState

**File:** `editor/controllers/view_state.py` (NEW)

**Purpose:** Manages viewport camera (offset, scale) and coordinate transformations. This eliminates duplicate `_screen_to_tile()` code.

```python
"""
NES Open Tournament Golf - View State

Manages viewport camera position, zoom, and coordinate transformations.
"""

from typing import Optional, Tuple
from pygame import Rect

from editor.core.constants import TILE_SIZE


class ViewState:
    """Manages viewport camera and coordinate transformations."""

    def __init__(self, canvas_rect: Rect, offset_x: int = 0, offset_y: int = 0, scale: int = 4):
        """
        Initialize view state.

        Args:
            canvas_rect: The canvas drawing area (screen coordinates)
            offset_x: Horizontal scroll offset in pixels
            offset_y: Vertical scroll offset in pixels
            scale: Zoom scale multiplier (1-8)
        """
        self.canvas_rect = canvas_rect
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.scale = scale

    @property
    def tile_size(self) -> int:
        """Get the current tile size in pixels (based on scale)."""
        return TILE_SIZE * self.scale

    def screen_to_tile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        Convert screen position to tile coordinates.

        Args:
            screen_pos: Screen position (x, y) in pixels

        Returns:
            Tile coordinates (row, col), or None if outside canvas
        """
        if not self.canvas_rect.collidepoint(screen_pos):
            return None

        local_x = screen_pos[0] - self.canvas_rect.x + self.offset_x
        local_y = screen_pos[1] - self.canvas_rect.y + self.offset_y

        tile_col = local_x // self.tile_size
        tile_row = local_y // self.tile_size

        return (tile_row, tile_col)

    def screen_to_supertile(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        Convert screen position to supertile (2x2) coordinates.

        Args:
            screen_pos: Screen position (x, y) in pixels

        Returns:
            Supertile coordinates (row, col), or None if outside canvas
        """
        tile = self.screen_to_tile(screen_pos)
        if tile is None:
            return None
        return (tile[0] // 2, tile[1] // 2)

    def tile_to_screen(self, tile_pos: Tuple[int, int]) -> Tuple[int, int]:
        """
        Convert tile coordinates to screen position (top-left corner).

        Args:
            tile_pos: Tile coordinates (row, col)

        Returns:
            Screen position (x, y) in pixels
        """
        row, col = tile_pos
        x = self.canvas_rect.x + col * self.tile_size - self.offset_x
        y = self.canvas_rect.y + row * self.tile_size - self.offset_y
        return (x, y)

    def is_tile_visible(self, tile_pos: Tuple[int, int]) -> bool:
        """
        Check if a tile is visible in the current viewport.

        Args:
            tile_pos: Tile coordinates (row, col)

        Returns:
            True if tile is visible in viewport
        """
        x, y = self.tile_to_screen(tile_pos)
        tile_size = self.tile_size

        return not (
            x + tile_size < self.canvas_rect.x or x > self.canvas_rect.right or
            y + tile_size < self.canvas_rect.y or y > self.canvas_rect.bottom
        )
```

### 1.2 Create RenderContext

**File:** `editor/rendering/render_context.py` (NEW)

**Purpose:** Bundles rendering resources and settings to reduce parameter count.

```python
"""
NES Open Tournament Golf - Render Context

Bundles rendering resources and settings for canvas rendering.
"""

from typing import Dict, Optional
from editor.core.pygame_rendering import Tileset, Sprite


class RenderContext:
    """Bundles rendering resources and settings."""

    def __init__(
        self,
        tileset: Tileset,
        sprites: Dict[str, Optional[Sprite]],
        mode: str,
        show_grid: bool = True,
        show_sprites: bool = True,
        selected_flag_index: int = 0,
    ):
        """
        Initialize render context.

        Args:
            tileset: Tileset to use (terrain or greens)
            sprites: Dictionary of sprite objects
            mode: Current editing mode ("terrain", "palette", "greens")
            show_grid: Whether to show grid overlay
            show_sprites: Whether to show sprite overlays
            selected_flag_index: Which flag position to render (0-3)
        """
        self.tileset = tileset
        self.sprites = sprites
        self.mode = mode
        self.show_grid = show_grid
        self.show_sprites = show_sprites
        self.selected_flag_index = selected_flag_index
```

### 1.3 Create HighlightState

**File:** `editor/controllers/highlight_state.py` (NEW)

**Purpose:** Manages temporary visual highlights (hover, transform preview, invalid tiles).

```python
"""
NES Open Tournament Golf - Highlight State

Manages temporary visual highlights (hover, transform preview, selection).
"""

from typing import Optional
from .transform_drag_state import TransformDragState


class HighlightState:
    """Manages temporary visual highlights and previews."""

    def __init__(self):
        """Initialize with no highlights."""
        self.shift_hover_tile: Optional[int] = None
        self.transform_state: TransformDragState = TransformDragState()
        self.show_invalid_tiles: bool = False
        self.invalid_terrain_tiles: Optional[set] = None

    def set_picker_hover(self, tile_value: Optional[int]):
        """
        Update the shift-hover tile highlight.

        This is called by pickers when hover state changes (callback pattern).

        Args:
            tile_value: Tile value to highlight, or None to clear
        """
        self.shift_hover_tile = tile_value

    def clear_picker_hover(self):
        """Clear shift-hover highlight."""
        self.shift_hover_tile = None
```

**Testing:** After creating these files, verify they import correctly:
```bash
python -c "from editor.controllers.view_state import ViewState; print('ViewState OK')"
python -c "from editor.rendering.render_context import RenderContext; print('RenderContext OK')"
python -c "from editor.controllers.highlight_state import HighlightState; print('HighlightState OK')"
```

---

## Phase 2: Update Renderers (1 hour)

### 2.1 Update TerrainRenderer

**File:** `editor/rendering/terrain_renderer.py`

**Change the signature from:**
```python
def render(
    screen, canvas_rect, hole_data, tileset, sprites,
    canvas_offset_x, canvas_offset_y, canvas_scale,
    show_grid, show_sprites, selected_flag_index,
    transform_state, shift_hover_tile,
    show_invalid_tiles, invalid_terrain_tiles
):  # 15 parameters!
```

**To:**
```python
@staticmethod
def render(
    screen: Surface,
    view_state: ViewState,
    hole_data: HoleData,
    render_ctx: RenderContext,
    highlight_state: HighlightState,
):  # 5 parameters!
```

**Update the implementation:**
- Replace `canvas_rect` with `view_state.canvas_rect`
- Replace `canvas_offset_x/y` with `view_state.offset_x/y`
- Replace `canvas_scale` with `view_state.scale`
- Replace `tileset` with `render_ctx.tileset`
- Replace `sprites` with `render_ctx.sprites`
- Replace `show_grid` with `render_ctx.show_grid`
- Replace `show_sprites` with `render_ctx.show_sprites`
- Replace `selected_flag_index` with `render_ctx.selected_flag_index`
- Replace `transform_state` with `highlight_state.transform_state`
- Replace `shift_hover_tile` with `highlight_state.shift_hover_tile`
- Replace `show_invalid_tiles` with `highlight_state.show_invalid_tiles`
- Replace `invalid_terrain_tiles` with `highlight_state.invalid_terrain_tiles`

**Use ViewState methods:**
- Replace manual `tile_to_screen` calculations with `view_state.tile_to_screen((row, col))`
- Replace manual visibility checks with `view_state.is_tile_visible((row, col))`

### 2.2 Update GreensRenderer

**File:** `editor/rendering/greens_renderer.py`

Apply the same signature and implementation changes as TerrainRenderer.

### 2.3 Update Helper Renderers

**File:** `editor/rendering/sprite_renderer.py`

Update methods to accept `view_state` instead of individual offset/scale parameters:
```python
@staticmethod
def render_green_overlay(screen, view_state, hole_data):
    # ... use view_state.offset_x, view_state.offset_y, view_state.scale ...

@staticmethod
def render_terrain_sprites(screen, view_state, sprites, hole_data, selected_flag_index):
    # ... use view_state methods ...
```

**File:** `editor/rendering/grid_renderer.py`

```python
@staticmethod
def render(screen, view_state, width, height):
    # ... use view_state.tile_size, view_state.offset_x/y ...
```

### 2.4 Update Application._render_canvas()

**File:** `editor/application.py`

**Replace the old rendering code with:**
```python
def _render_canvas(self):
    """Render the main editing canvas."""
    canvas_rect = self._get_canvas_rect()
    pygame.draw.rect(self.screen, (0, 0, 0), canvas_rect)

    if not self.hole_data.terrain:
        text = self.font.render("No hole loaded. Press Ctrl+O to open.", True, COLOR_TEXT)
        self.screen.blit(text, (canvas_rect.centerx - text.get_width() // 2, canvas_rect.centery))
        return

    # Create view state
    view_state = ViewState(
        canvas_rect,
        self.state.canvas_offset_x,
        self.state.canvas_offset_y,
        self.state.canvas_scale
    )

    # Update highlight state
    self.highlight_state.show_invalid_tiles = self.state.show_invalid_tiles
    if self.state.mode == "terrain":
        self.highlight_state.invalid_terrain_tiles = self.get_invalid_terrain_tiles()
    else:
        self.highlight_state.invalid_terrain_tiles = None

    # Get transform state from EditorState (will move to tool later)
    self.highlight_state.transform_state = self.state.transform_state

    # Render based on mode
    if self.state.mode == "greens":
        render_ctx = RenderContext(
            self.greens_tileset,
            self.sprites,
            self.state.mode,
            self.state.show_grid,
            self.state.show_sprites,
            self.state.selected_flag_index,
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
        )
        TerrainRenderer.render(
            self.screen,
            view_state,
            self.hole_data,
            render_ctx,
            self.highlight_state,
        )
```

**Testing:** After this phase, run the editor and verify:
- Rendering still works correctly
- All modes render (terrain, palette, greens)
- Grid toggle works
- Sprite toggle works
- Transform preview shows correctly
- Shift+hover highlights work

---

## Phase 3: Implement Hover Callbacks (1 hour)

### 3.1 Update TilePicker

**File:** `editor/ui/pickers/tile_picker.py`

**Add callback to __init__:**
```python
def __init__(self, tileset: Tileset, rect: Rect, on_hover_change=None):
    # ... existing code ...
    self.hovered_tile = None
    self.on_hover_change = on_hover_change  # NEW
```

**Update handle_event to notify on hover changes:**
```python
def handle_event(self, event: pygame.event.Event) -> bool:
    if event.type == pygame.MOUSEMOTION:
        if self.rect.collidepoint(event.pos):
            new_hover = self._tile_at_position(event.pos)
        else:
            new_hover = None

        # Only notify if hover changed
        if new_hover != self.hovered_tile:
            self.hovered_tile = new_hover
            if self.on_hover_change:
                self.on_hover_change(new_hover)

    # ... rest of event handling ...
```

### 3.2 Update GreensTilePicker

**File:** `editor/ui/pickers/greens_tile_picker.py`

Apply the same changes as TilePicker (same pattern).

### 3.3 Update Application

**File:** `editor/application.py`

**In __init__, create HighlightState:**
```python
def __init__(self, terrain_chr: str, greens_chr: str):
    # ... existing code ...

    # Create highlight state (BEFORE creating pickers)
    self.highlight_state = HighlightState()

    # Create pickers with hover callbacks
    picker_rect = Rect(0, TOOLBAR_HEIGHT, PICKER_WIDTH, self.screen_height - TOOLBAR_HEIGHT - STATUS_HEIGHT)
    self.terrain_picker = TilePicker(
        self.terrain_tileset,
        picker_rect,
        on_hover_change=self._on_terrain_hover_change  # NEW
    )
    self.greens_picker = GreensTilePicker(
        self.greens_tileset,
        picker_rect,
        on_hover_change=self._on_greens_hover_change  # NEW
    )
```

**Add hover callback methods:**
```python
def _on_terrain_hover_change(self, tile_value: Optional[int]):
    """Called when terrain picker hover changes."""
    shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
    if shift_held and self.state.mode in ("terrain", "palette"):
        self.highlight_state.set_picker_hover(tile_value)
    else:
        self.highlight_state.clear_picker_hover()

def _on_greens_hover_change(self, tile_value: Optional[int]):
    """Called when greens picker hover changes."""
    shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
    if shift_held and self.state.mode == "greens":
        self.highlight_state.set_picker_hover(tile_value)
    else:
        self.highlight_state.clear_picker_hover()
```

**Remove the old polling code from _render():**
Delete these lines:
```python
# OLD CODE TO DELETE:
shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
if shift_held:
    if self.state.mode == "greens":
        self.state.shift_hover_tile = self.greens_picker.get_hovered_tile()
    else:
        self.state.shift_hover_tile = self.terrain_picker.get_hovered_tile()
else:
    self.state.shift_hover_tile = None
```

**Note:** You still need to check shift state in callbacks because shift can be pressed/released without mouse movement. The callbacks handle the common case (mouse moves while shift is held).

**Testing:** Verify shift+hover highlighting still works correctly.

---

## Phase 4: Extract Tools (4-5 hours)

This is the biggest change. Extract tool logic from EventHandler into separate classes.

### 4.1 Create Tool Infrastructure

**File:** `editor/tools/__init__.py` (NEW)

```python
"""
NES Open Tournament Golf - Tools

Editor tools for painting, transforming, and modifying hole data.
"""

from .base_tool import Tool, ToolContext, ToolResult
from .tool_manager import ToolManager
from .paint_tool import PaintTool
from .transform_tool import TransformTool
from .eyedropper_tool import EyedropperTool
from .forest_fill_tool import ForestFillTool

__all__ = [
    'Tool',
    'ToolContext',
    'ToolResult',
    'ToolManager',
    'PaintTool',
    'TransformTool',
    'EyedropperTool',
    'ForestFillTool',
]
```

**File:** `editor/tools/base_tool.py` (NEW)

This is a large file. Here's the complete implementation:

```python
"""
Tool protocol and base definitions for editor tools.
"""
from typing import Protocol, Optional, Tuple
import pygame


class Tool(Protocol):
    """Protocol defining the tool interface.

    Tools don't need to inherit from this - they just need to implement these methods.
    This provides duck typing with type checking support.
    """

    def handle_mouse_down(
        self,
        pos: Tuple[int, int],
        button: int,
        modifiers: int,
        context: 'ToolContext'
    ) -> 'ToolResult':
        """Handle mouse button down event."""
        ...

    def handle_mouse_up(
        self,
        pos: Tuple[int, int],
        button: int,
        context: 'ToolContext'
    ) -> 'ToolResult':
        """Handle mouse button up event."""
        ...

    def handle_mouse_motion(
        self,
        pos: Tuple[int, int],
        context: 'ToolContext'
    ) -> 'ToolResult':
        """Handle mouse motion event."""
        ...

    def handle_key_down(
        self,
        key: int,
        modifiers: int,
        context: 'ToolContext'
    ) -> 'ToolResult':
        """Handle key down event (for tool-specific shortcuts)."""
        ...

    def handle_key_up(
        self,
        key: int,
        context: 'ToolContext'
    ) -> 'ToolResult':
        """Handle key up event."""
        ...

    def on_activated(self, context: 'ToolContext') -> None:
        """Called when tool becomes active."""
        ...

    def on_deactivated(self, context: 'ToolContext') -> None:
        """Called when tool is deactivated."""
        ...

    def reset(self) -> None:
        """Reset tool state."""
        ...


class ToolContext:
    """Context object providing tools access to application state.

    This acts as a facade, limiting what tools can access and preventing
    tight coupling to Application internals.
    """

    def __init__(
        self,
        hole_data,
        state,
        terrain_picker,
        greens_picker,
        transform_logic,
        forest_filler,
        screen_width: int,
        screen_height: int,
    ):
        self.hole_data = hole_data
        self.state = state
        self.terrain_picker = terrain_picker
        self.greens_picker = greens_picker
        self.transform_logic = transform_logic
        self.forest_filler = forest_filler
        self.screen_width = screen_width
        self.screen_height = screen_height

    def get_selected_tile(self) -> int:
        """Get currently selected tile based on mode."""
        if self.state.mode == "greens":
            return self.greens_picker.selected_tile
        else:
            return self.terrain_picker.selected_tile

    def set_selected_tile(self, tile: int) -> None:
        """Set selected tile based on mode."""
        if self.state.mode == "greens":
            self.greens_picker.selected_tile = tile
        else:
            self.terrain_picker.selected_tile = tile


class ToolResult:
    """Result of a tool operation."""

    def __init__(
        self,
        handled: bool = False,
        needs_undo_push: bool = False,
        needs_render: bool = False,
        terrain_modified: bool = False,
        message: Optional[str] = None,
    ):
        self.handled = handled
        self.needs_undo_push = needs_undo_push
        self.needs_render = needs_render
        self.terrain_modified = terrain_modified
        self.message = message

    @staticmethod
    def handled() -> 'ToolResult':
        """Event handled but no action needed."""
        return ToolResult(handled=True)

    @staticmethod
    def not_handled() -> 'ToolResult':
        """Event not handled."""
        return ToolResult(handled=False)

    @staticmethod
    def modified(terrain: bool = False, message: Optional[str] = None) -> 'ToolResult':
        """Content was modified."""
        return ToolResult(
            handled=True,
            needs_undo_push=False,  # Tool handles undo timing
            needs_render=True,
            terrain_modified=terrain,
            message=message
        )
```

**File:** `editor/tools/tool_manager.py` (NEW)

```python
"""
Tool manager for registering and switching between editor tools.
"""
from typing import Dict, Optional
from .base_tool import Tool, ToolContext


class ToolManager:
    """Manages tool registration and activation."""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.active_tool: Optional[Tool] = None
        self.active_tool_name: Optional[str] = None

    def register_tool(self, name: str, tool: Tool):
        """Register a tool with a name."""
        self.tools[name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)

    def set_active_tool(self, name: str, context: ToolContext) -> bool:
        """Set the active tool by name."""
        if name not in self.tools:
            return False

        if self.active_tool and self.active_tool_name != name:
            self.active_tool.on_deactivated(context)

        self.active_tool = self.tools[name]
        self.active_tool_name = name
        self.active_tool.on_activated(context)

        return True

    def get_active_tool(self) -> Optional[Tool]:
        """Get the currently active tool."""
        return self.active_tool

    def get_active_tool_name(self) -> Optional[str]:
        """Get the name of the currently active tool."""
        return self.active_tool_name
```

### 4.2 Implement Individual Tools

I'll provide complete implementations for each tool. These are extracted from the current EventHandler logic.

**File:** `editor/tools/paint_tool.py` (NEW)

```python
"""
Paint tool for terrain, palette, and greens editing.
"""
from typing import Optional, Tuple
from .base_tool import Tool, ToolContext, ToolResult
from editor.controllers.view_state import ViewState
from editor.core.constants import TERRAIN_WIDTH, GREENS_WIDTH, GREENS_HEIGHT, CANVAS_OFFSET_X, CANVAS_OFFSET_Y, STATUS_HEIGHT
from pygame import Rect


class PaintTool:
    """Paint tool - primary editing tool for all modes."""

    def __init__(self):
        self.is_painting = False
        self.last_paint_pos: Optional[Tuple[int, int]] = None
        self.undo_pushed = False

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button != 1:  # Only left click
            return ToolResult.not_handled()

        # Start paint stroke - push undo state
        if not self.is_painting:
            context.state.undo_manager.push_state(context.hole_data)
            self.undo_pushed = True
            self.is_painting = True

        return self._paint_at(pos, context)

    def handle_mouse_up(self, pos, button, context):
        if button == 1:
            self.is_painting = False
            self.last_paint_pos = None
            self.undo_pushed = False
        return ToolResult.handled()

    def handle_mouse_motion(self, pos, context):
        if self.is_painting:
            return self._paint_at(pos, context)
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        self.reset()

    def reset(self):
        self.is_painting = False
        self.last_paint_pos = None
        self.undo_pushed = False

    def _paint_at(self, pos: Tuple[int, int], context: ToolContext) -> ToolResult:
        """Paint at screen position based on current mode."""
        # Create view state for coordinate conversion
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        mode = context.state.mode

        if mode == "terrain":
            return self._paint_terrain(view_state, pos, context)
        elif mode == "palette":
            return self._paint_palette(view_state, pos, context)
        elif mode == "greens":
            return self._paint_greens(view_state, pos, context)

        return ToolResult.not_handled()

    def _paint_terrain(self, view_state, pos, context) -> ToolResult:
        tile = view_state.screen_to_tile(pos)
        if tile and tile != self.last_paint_pos:
            row, col = tile
            if 0 <= row < len(context.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                selected_tile = context.terrain_picker.selected_tile
                context.hole_data.set_terrain_tile(row, col, selected_tile)
                self.last_paint_pos = tile
                return ToolResult.modified(terrain=True)
        return ToolResult.handled()

    def _paint_palette(self, view_state, pos, context) -> ToolResult:
        supertile = view_state.screen_to_supertile(pos)
        if supertile and supertile != self.last_paint_pos:
            row, col = supertile
            context.hole_data.set_attribute(row, col, context.state.selected_palette)
            self.last_paint_pos = supertile
            return ToolResult.modified(terrain=False)
        return ToolResult.handled()

    def _paint_greens(self, view_state, pos, context) -> ToolResult:
        tile = view_state.screen_to_tile(pos)
        if tile and tile != self.last_paint_pos:
            row, col = tile
            if 0 <= row < GREENS_HEIGHT and 0 <= col < GREENS_WIDTH:
                selected_tile = context.greens_picker.selected_tile
                context.hole_data.set_greens_tile(row, col, selected_tile)
                self.last_paint_pos = tile
                return ToolResult.modified(terrain=False)
        return ToolResult.handled()
```

**File:** `editor/tools/eyedropper_tool.py` (NEW)

```python
"""
Eyedropper tool for sampling tiles from the canvas.
"""
from .base_tool import Tool, ToolContext, ToolResult
from editor.controllers.view_state import ViewState
from editor.core.constants import TERRAIN_WIDTH, GREENS_WIDTH, CANVAS_OFFSET_X, CANVAS_OFFSET_Y, STATUS_HEIGHT
from pygame import Rect


class EyedropperTool:
    """Eyedropper tool - samples tiles/palettes from canvas."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button == 3:  # Right click
            return self._sample_at(pos, context)
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def _sample_at(self, pos, context) -> ToolResult:
        """Sample tile/palette at position."""
        # Create view state for coordinate conversion
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        mode = context.state.mode

        if mode == "terrain":
            tile = view_state.screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(context.hole_data.terrain) and 0 <= col < TERRAIN_WIDTH:
                    context.terrain_picker.selected_tile = context.hole_data.terrain[row][col]
                    return ToolResult.handled()

        elif mode == "palette":
            supertile = view_state.screen_to_supertile(pos)
            if supertile:
                row, col = supertile
                if (0 <= row < len(context.hole_data.attributes) and
                    0 <= col < len(context.hole_data.attributes[row])):
                    context.state.selected_palette = context.hole_data.attributes[row][col]
                    return ToolResult.handled()

        elif mode == "greens":
            tile = view_state.screen_to_tile(pos)
            if tile:
                row, col = tile
                if 0 <= row < len(context.hole_data.greens) and 0 <= col < GREENS_WIDTH:
                    context.greens_picker.selected_tile = context.hole_data.greens[row][col]
                    return ToolResult.handled()

        return ToolResult.not_handled()
```

**File:** `editor/tools/transform_tool.py` (NEW)

This is the most complex tool. It replaces `TransformDragState` and owns its state machine.

```python
"""
Transform tool for applying compression table transformations via shift+drag.
"""
import pygame
from typing import Optional, Tuple, Dict
from .base_tool import Tool, ToolContext, ToolResult
from editor.controllers.view_state import ViewState
from editor.core.constants import TILE_SIZE, TERRAIN_WIDTH, GREENS_WIDTH, GREENS_HEIGHT, CANVAS_OFFSET_X, CANVAS_OFFSET_Y, STATUS_HEIGHT
from pygame import Rect


class TransformToolState:
    """State for an active transform drag operation."""

    def __init__(self):
        self.is_active = False
        self.drag_start_pos: Optional[Tuple[int, int]] = None
        self.origin_tile: Optional[Tuple[int, int]] = None
        self.preview_changes: Dict[Tuple[int, int], int] = {}
        self.direction: Optional[str] = None
        self.blocked = False

    def start(self, mouse_pos: Tuple[int, int], tile_pos: Tuple[int, int]):
        self.is_active = True
        self.drag_start_pos = mouse_pos
        self.origin_tile = tile_pos
        self.preview_changes = {}
        self.direction = None
        self.blocked = False

    def reset(self):
        self.__init__()


class TransformTool:
    """Transform tool - shift+drag to apply compression transformations."""

    def __init__(self):
        self.state = TransformToolState()

    def handle_mouse_down(self, pos, button, modifiers, context):
        if button != 1:
            return ToolResult.not_handled()

        # Only activate if Shift is held
        if not (modifiers & pygame.KMOD_SHIFT):
            return ToolResult.not_handled()

        # Only in terrain or greens mode
        if context.state.mode not in ("terrain", "greens"):
            return ToolResult.not_handled()

        # Create view state
        canvas_rect = Rect(
            CANVAS_OFFSET_X,
            CANVAS_OFFSET_Y,
            context.screen_width - CANVAS_OFFSET_X,
            context.screen_height - CANVAS_OFFSET_Y - STATUS_HEIGHT
        )
        view_state = ViewState(
            canvas_rect,
            context.state.canvas_offset_x,
            context.state.canvas_offset_y,
            context.state.canvas_scale,
        )

        tile = view_state.screen_to_tile(pos)
        if tile:
            self.state.start(pos, tile)
            return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        if button == 1 and self.state.is_active:
            # Commit transform
            if not self.state.blocked and self.state.preview_changes:
                context.state.undo_manager.push_state(context.hole_data)
                self._commit_transform(context)
                self.state.reset()
                return ToolResult.modified(terrain=(context.state.mode == "terrain"))
            else:
                self.state.reset()
                return ToolResult.handled()

        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        if self.state.is_active:
            self._update_transform_preview(pos, context)
            return ToolResult.handled()
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        # Cancel on Shift release
        if key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            if self.state.is_active:
                self.state.reset()
                return ToolResult.handled()
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        self.reset()

    def reset(self):
        self.state.reset()

    def _update_transform_preview(self, pos, context):
        """Update transform preview based on drag movement."""
        dx = pos[0] - self.state.drag_start_pos[0]
        dy = pos[1] - self.state.drag_start_pos[1]

        # Determine direction
        if self.state.direction is None and (abs(dx) > 5 or abs(dy) > 5):
            if dx < -2 or dy < -2:
                self.state.blocked = True
                return
            self.state.direction = "horizontal" if abs(dx) > abs(dy) else "vertical"

        if self.state.direction is None:
            return

        # Get source tile
        origin_row, origin_col = self.state.origin_tile
        if context.state.mode == "terrain":
            source_value = context.hole_data.terrain[origin_row][origin_col]
            max_col = TERRAIN_WIDTH
            max_row = len(context.hole_data.terrain)
        else:
            source_value = context.hole_data.greens[origin_row][origin_col]
            max_col = GREENS_WIDTH
            max_row = GREENS_HEIGHT

        tile_size = TILE_SIZE * context.state.canvas_scale

        if self.state.direction == "horizontal":
            if dx < 0:
                self.state.preview_changes.clear()
                return

            steps = max(0, (dx + tile_size - 1) // tile_size)
            if steps == 0:
                self.state.preview_changes.clear()
                return

            self.state.preview_changes.clear()
            current_value = source_value
            for step in range(1, steps + 1):
                current_value = context.transform_logic.apply_horizontal(
                    current_value, context.state.mode
                )
                tile_col = origin_col + step
                if 0 <= tile_col < max_col:
                    self.state.preview_changes[(origin_row, tile_col)] = current_value

        else:  # vertical
            if dy < 0:
                self.state.preview_changes.clear()
                return

            steps = max(0, (dy + tile_size - 1) // tile_size)
            if steps == 0:
                self.state.preview_changes.clear()
                return

            self.state.preview_changes.clear()
            current_value = source_value
            for step in range(1, steps + 1):
                current_value = context.transform_logic.apply_vertical(
                    current_value, context.state.mode
                )
                tile_row = origin_row + step
                if 0 <= tile_row < max_row:
                    self.state.preview_changes[(tile_row, origin_col)] = current_value

    def _commit_transform(self, context):
        """Apply preview changes to hole data."""
        for (row, col), tile_value in self.state.preview_changes.items():
            if context.state.mode == "terrain":
                context.hole_data.set_terrain_tile(row, col, tile_value)
            else:
                context.hole_data.set_greens_tile(row, col, tile_value)
```

**File:** `editor/tools/forest_fill_tool.py` (NEW)

```python
"""
Forest fill tool - intelligent WFC-based forest region filling.
"""
import pygame
from .base_tool import Tool, ToolContext, ToolResult


class ForestFillTool:
    """Forest fill tool - fills placeholder regions with forest tiles."""

    def handle_mouse_down(self, pos, button, modifiers, context):
        return ToolResult.not_handled()

    def handle_mouse_up(self, pos, button, context):
        return ToolResult.not_handled()

    def handle_mouse_motion(self, pos, context):
        return ToolResult.not_handled()

    def handle_key_down(self, key, modifiers, context):
        # Ctrl+F activates forest fill
        if key == pygame.K_f and (modifiers & pygame.KMOD_CTRL):
            return self._trigger_forest_fill(context)
        return ToolResult.not_handled()

    def handle_key_up(self, key, context):
        return ToolResult.not_handled()

    def on_activated(self, context):
        pass

    def on_deactivated(self, context):
        pass

    def reset(self):
        pass

    def _trigger_forest_fill(self, context) -> ToolResult:
        """Execute forest fill on detected regions."""
        if context.state.mode != "terrain":
            return ToolResult(
                handled=True,
                message="Forest Fill: Only available in terrain mode"
            )

        if not context.forest_filler:
            return ToolResult(
                handled=True,
                message="Forest fill not available (neighbor data missing)"
            )

        # Detect regions
        regions = context.forest_filler.detect_regions(context.hole_data.terrain)

        if not regions:
            return ToolResult(
                handled=True,
                message="Forest Fill: No placeholder regions detected"
            )

        # Fill all regions
        all_changes = {}
        for region in regions:
            changes = context.forest_filler.fill_region(context.hole_data.terrain, region)
            all_changes.update(changes)

        if not all_changes:
            return ToolResult(
                handled=True,
                message="Forest Fill: No fillable cells found"
            )

        # Push undo state before applying
        context.state.undo_manager.push_state(context.hole_data)

        # Apply changes
        for (row, col), tile in all_changes.items():
            context.hole_data.set_terrain_tile(row, col, tile)

        message = f"Forest Fill: Filled {len(all_changes)} tiles in {len(regions)} region(s)"
        return ToolResult.modified(terrain=True, message=message)
```

### 4.3 Update EventHandler

**File:** `editor/controllers/event_handler.py`

This requires substantial changes. The key is to:
1. Accept ToolManager instead of individual tool logic
2. Create ToolContext
3. Delete all tool implementation methods
4. Delegate to tools

**Replace the constructor:**
```python
def __init__(
    self,
    state: EditorState,
    hole_data: HoleData,
    terrain_picker: TilePicker,
    greens_picker: GreensTilePicker,
    buttons: List[Button],
    screen_width: int,
    screen_height: int,
    tool_manager,  # NEW: ToolManager instead of transform_logic/forest_filler
    on_load: Callable[[], None],
    on_save: Callable[[], None],
    on_mode_change: Callable[[], None],
    on_flag_change: Callable[[], None],
    on_resize: Callable[[int, int], None],
    on_terrain_modified: Callable[[], None] = None,
):
    self.state = state
    self.hole_data = hole_data
    self.terrain_picker = terrain_picker
    self.greens_picker = greens_picker
    self.buttons = buttons
    self.screen_width = screen_width
    self.screen_height = screen_height
    self.tool_manager = tool_manager  # NEW
    self.on_load = on_load
    self.on_save = on_save
    self.on_mode_change = on_mode_change
    self.on_flag_change = on_flag_change
    self.on_resize = on_resize
    self.on_terrain_modified = on_terrain_modified

    # Create tool context (NEW)
    from editor.tools.base_tool import ToolContext
    self.tool_context = ToolContext(
        hole_data=hole_data,
        state=state,
        terrain_picker=terrain_picker,
        greens_picker=greens_picker,
        transform_logic=None,  # Will be set by Application
        forest_filler=None,  # Will be set by Application
        screen_width=screen_width,
        screen_height=screen_height,
    )
```

**Delete these methods** (they're now in tools):
- `_paint_at()`
- `_transform_at()`
- `_commit_transform()`
- `_sample_at()` (eyedropper)
- Everything related to forest fill

**Replace mouse handling:**
```python
def _handle_mouse_down(self, event):
    """Delegate mouse down to tools."""
    modifiers = pygame.key.get_mods()

    # Try transform tool first if shift held
    if modifiers & pygame.KMOD_SHIFT:
        transform_tool = self.tool_manager.get_tool("transform")
        if transform_tool:
            result = transform_tool.handle_mouse_down(
                event.pos, event.button, modifiers, self.tool_context
            )
            if result.handled:
                self._process_tool_result(result)
                return

    # Try eyedropper on right click
    if event.button == 3:
        eyedropper_tool = self.tool_manager.get_tool("eyedropper")
        if eyedropper_tool:
            result = eyedropper_tool.handle_mouse_down(
                event.pos, event.button, modifiers, self.tool_context
            )
            if result.handled:
                self._process_tool_result(result)
                return

    # Handle scrolling
    if event.button == 4:  # Scroll up
        self.state.canvas_offset_y = max(0, self.state.canvas_offset_y - 20)
        return
    elif event.button == 5:  # Scroll down
        self.state.canvas_offset_y += 20
        return

    # Default to active tool (paint)
    tool = self.tool_manager.get_active_tool()
    if tool:
        result = tool.handle_mouse_down(
            event.pos, event.button, modifiers, self.tool_context
        )
        self._process_tool_result(result)

def _handle_mouse_up(self, event):
    """Delegate mouse up to tools."""
    # Check transform first (might be active)
    transform_tool = self.tool_manager.get_tool("transform")
    if transform_tool and hasattr(transform_tool, 'state') and transform_tool.state.is_active:
        result = transform_tool.handle_mouse_up(event.pos, event.button, self.tool_context)
        self._process_tool_result(result)
        return

    # Otherwise delegate to active tool
    tool = self.tool_manager.get_active_tool()
    if tool:
        result = tool.handle_mouse_up(event.pos, event.button, self.tool_context)
        self._process_tool_result(result)

def _handle_mouse_motion(self, event):
    """Delegate mouse motion to active tool."""
    # Check if transform is active
    transform_tool = self.tool_manager.get_tool("transform")
    if transform_tool and hasattr(transform_tool, 'state') and transform_tool.state.is_active:
        result = transform_tool.handle_mouse_motion(event.pos, self.tool_context)
        self._process_tool_result(result)
        return

    # Otherwise delegate to active tool
    tool = self.tool_manager.get_active_tool()
    if tool:
        result = tool.handle_mouse_motion(event.pos, self.tool_context)
        self._process_tool_result(result)

def _process_tool_result(self, result):
    """Process a tool result and trigger necessary callbacks."""
    if result.terrain_modified and self.on_terrain_modified:
        self.on_terrain_modified()

    if result.message:
        print(result.message)  # TODO: Better status display
```

**Update handle_events to delegate key events to tools:**
```python
def handle_events(self, events: List[pygame.event.Event]) -> bool:
    for event in events:
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if not self._handle_global_keys(event):
                # Let active tool handle if global handler didn't
                tool = self.tool_manager.get_active_tool()
                if tool:
                    modifiers = pygame.key.get_mods()
                    result = tool.handle_key_down(event.key, modifiers, self.tool_context)
                    self._process_tool_result(result)

        elif event.type == pygame.KEYUP:
            tool = self.tool_manager.get_active_tool()
            if tool:
                result = tool.handle_key_up(event.key, self.tool_context)
                self._process_tool_result(result)

        # ... rest of event handling (buttons, pickers, mouse, resize) ...
```

### 4.4 Update Application

**File:** `editor/application.py`

**Import ToolManager:**
```python
from editor.tools.tool_manager import ToolManager
from editor.tools import PaintTool, TransformTool, EyedropperTool, ForestFillTool
```

**Create and register tools in __init__:**
```python
def __init__(self, terrain_chr: str, greens_chr: str):
    # ... existing initialization ...

    # Create tool manager (AFTER loading transform_logic and forest_filler)
    self.tool_manager = ToolManager()
    self.tool_manager.register_tool("paint", PaintTool())
    self.tool_manager.register_tool("transform", TransformTool())
    self.tool_manager.register_tool("eyedropper", EyedropperTool())
    self.tool_manager.register_tool("forest_fill", ForestFillTool())

    # Set paint as default active tool
    from editor.tools.base_tool import ToolContext
    tool_context = ToolContext(
        self.hole_data, self.state, self.terrain_picker, self.greens_picker,
        self.transform_logic, self.forest_filler,
        self.screen_width, self.screen_height
    )
    self.tool_manager.set_active_tool("paint", tool_context)

    # Create event handler with tool manager
    self.event_handler = EventHandler(
        self.state,
        self.hole_data,
        self.terrain_picker,
        self.greens_picker,
        [],  # buttons list
        self.screen_width,
        self.screen_height,
        self.tool_manager,  # Pass tool manager instead of transform_logic/forest_filler
        on_load=self._on_load,
        on_save=self._on_save,
        on_mode_change=self._update_mode_buttons,
        on_flag_change=self._update_flag_buttons,
        on_resize=self._on_resize,
        on_terrain_modified=self.invalidate_terrain_validation_cache,
    )

    # Update tool context with transform_logic and forest_filler
    self.event_handler.tool_context.transform_logic = self.transform_logic
    self.event_handler.tool_context.forest_filler = self.forest_filler
```

**Update _render_canvas to get transform state from tool:**
```python
def _render_canvas(self):
    # ... existing code ...

    # Get transform state from transform tool (not EditorState)
    transform_tool = self.tool_manager.get_tool("transform")
    if transform_tool and hasattr(transform_tool, 'state'):
        self.highlight_state.transform_state = transform_tool.state
    else:
        # Create empty state for renderer
        from editor.controllers.transform_drag_state import TransformDragState
        self.highlight_state.transform_state = TransformDragState()

    # ... rest of rendering ...
```

### 4.5 Delete Old File

**Delete:** `editor/controllers/transform_drag_state.py`

The TransformToolState class inside transform_tool.py replaces this.

**Testing:** After Phase 4, thoroughly test:
- All tools work (paint, transform, eyedropper, forest fill)
- Undo/redo works for each tool
- Tool state is properly reset when switching modes
- Transform preview renders correctly

---

## Phase 5: Create Toolbar Class (2 hours)

*This phase is optional for initial refactoring. You can defer it if you want to ship Phase 1-4 first.*

The Toolbar class will manage button layout and prevent recreation on resize.

**File:** `editor/ui/toolbar.py` (NEW)

```python
"""
Toolbar for editor buttons.
"""
from typing import List, Callable
import pygame
from pygame import Rect
from .widgets import Button
from editor.core.constants import COLOR_TOOLBAR, TOOLBAR_HEIGHT, PALETTES


class ToolbarCallbacks:
    """Container for toolbar callbacks."""
    def __init__(self, **callbacks):
        for name, callback in callbacks.items():
            setattr(self, name, callback)


class Toolbar:
    """Manages toolbar buttons and layout."""

    def __init__(self, screen_width: int, callbacks: ToolbarCallbacks):
        self.screen_width = screen_width
        self.callbacks = callbacks

        # Button groups
        self.file_buttons: List[Button] = []
        self.mode_buttons: List[Button] = []
        self.tool_buttons: List[Button] = []
        self.flag_buttons: List[Button] = []
        self.palette_buttons: List[Button] = []

        self._create_buttons()

        # All buttons
        self.buttons = (
            self.file_buttons +
            self.mode_buttons +
            self.tool_buttons +
            self.flag_buttons +
            self.palette_buttons
        )

    def _create_buttons(self):
        """Create all toolbar buttons with automatic layout."""
        x = 10

        # File buttons
        btn_load = Button(Rect(x, 5, 60, 30), "Load", self.callbacks.on_load)
        self.file_buttons.append(btn_load)
        x += 70

        btn_save = Button(Rect(x, 5, 60, 30), "Save", self.callbacks.on_save)
        self.file_buttons.append(btn_save)
        x += 80

        # Mode buttons
        btn_terrain = Button(Rect(x, 5, 70, 30), "Terrain", lambda: self.callbacks.on_set_mode("terrain"))
        self.mode_buttons.append(btn_terrain)
        x += 80

        btn_palette = Button(Rect(x, 5, 70, 30), "Palette", lambda: self.callbacks.on_set_mode("palette"))
        self.mode_buttons.append(btn_palette)
        x += 80

        btn_greens = Button(Rect(x, 5, 70, 30), "Greens", lambda: self.callbacks.on_set_mode("greens"))
        self.mode_buttons.append(btn_greens)
        x += 90

        # Utility buttons
        btn_grid = Button(Rect(x, 5, 50, 30), "Grid", self.callbacks.on_toggle_grid)
        self.tool_buttons.append(btn_grid)
        x += 60

        btn_add_row = Button(Rect(x, 5, 70, 30), "+Row", lambda: self.callbacks.on_add_row(False))
        self.tool_buttons.append(btn_add_row)
        x += 80

        btn_del_row = Button(Rect(x, 5, 70, 30), "-Row", lambda: self.callbacks.on_remove_row(False))
        self.tool_buttons.append(btn_del_row)
        x += 100

        # Flag position buttons
        for i in range(4):
            btn = Button(
                Rect(x + (i * 35), 5, 30, 30),
                f"F{i+1}",
                lambda idx=i: self.callbacks.on_select_flag(idx)
            )
            self.flag_buttons.append(btn)
        x += 150

        # Palette selector buttons
        for i in range(1, 4):
            btn = Button(
                Rect(x + ((i-1) * 30), 8, 24, 24),
                str(i),
                lambda idx=i: self.callbacks.on_set_palette(idx),
                background_color=PALETTES[i][3]
            )
            self.palette_buttons.append(btn)
        x += 100

        # Sprite toggle
        btn_sprites = Button(Rect(x, 5, 70, 30), "Sprites", self.callbacks.on_toggle_sprites)
        self.tool_buttons.append(btn_sprites)

    def handle_events(self, events):
        """Delegate events to all buttons."""
        for button in self.buttons:
            for event in events:
                button.handle_event(event)

    def render(self, screen, font, font_small):
        """Render toolbar background and all buttons."""
        pygame.draw.rect(screen, COLOR_TOOLBAR, (0, 0, self.screen_width, TOOLBAR_HEIGHT))
        for button in self.buttons:
            button.render(screen, font_small if button in self.palette_buttons else font)

    def resize(self, screen_width: int):
        """Update button positions for new screen width without recreating."""
        self.screen_width = screen_width
        # For now, positions are absolute. In future could make dynamic.
        # Buttons maintain their positions since they're fixed layout.

    def get_mode_buttons(self):
        """Get mode buttons for updating active state."""
        return self.mode_buttons
```

**Update Application to use Toolbar** - replace `_create_ui()` and button management.

---

## Phase 6: Testing & Polish (ongoing)

### Testing Checklist

After each phase, verify:

- [ ] Load a hole file
- [ ] Paint terrain tiles (left drag)
- [ ] Paint greens tiles (switch mode, paint)
- [ ] Paint palette (switch mode, select palette, paint)
- [ ] Transform drag (shift+drag right/down)
- [ ] Transform cancel (shift+drag left/up, or release shift)
- [ ] Eyedropper (right-click)
- [ ] Forest fill (Ctrl+F)
- [ ] Undo/redo (Ctrl+Z, Ctrl+Y)
- [ ] Mode switching (Tab)
- [ ] Grid toggle (G)
- [ ] Sprite toggle (V)
- [ ] Shift+hover highlights
- [ ] Window resize (verify picker scroll preserved after Phase 5)
- [ ] Save file

---

## Success Criteria

You'll know the refactoring succeeded when:

1. ✅ EventHandler is under 200 lines (down from 420)
2. ✅ Renderer signatures have 5 parameters (down from 15)
3. ✅ Adding a new tool requires creating one file, not modifying EventHandler
4. ✅ Coordinate conversion exists in one place (ViewState)
5. ✅ Window resize doesn't reset picker scroll position (after Phase 5)
6. ✅ All existing functionality still works
7. ✅ Undo/redo works correctly for all tools

---

## Files Summary

### To Create:
- `editor/controllers/view_state.py`
- `editor/controllers/highlight_state.py`
- `editor/rendering/render_context.py`
- `editor/tools/__init__.py`
- `editor/tools/base_tool.py`
- `editor/tools/tool_manager.py`
- `editor/tools/paint_tool.py`
- `editor/tools/transform_tool.py`
- `editor/tools/eyedropper_tool.py`
- `editor/tools/forest_fill_tool.py`
- `editor/ui/toolbar.py` (optional, Phase 5)

### To Modify:
- `editor/application.py` (create contexts, use ToolManager, simpler rendering)
- `editor/controllers/event_handler.py` (delegate to tools, ~270 lines removed)
- `editor/rendering/terrain_renderer.py` (new signature: 5 params)
- `editor/rendering/greens_renderer.py` (new signature: 5 params)
- `editor/rendering/sprite_renderer.py` (accept ViewState)
- `editor/rendering/grid_renderer.py` (accept ViewState)
- `editor/ui/pickers/tile_picker.py` (add on_hover_change callback)
- `editor/ui/pickers/greens_tile_picker.py` (add on_hover_change callback)

### To Delete:
- `editor/controllers/transform_drag_state.py` (replaced by TransformTool.state)

---

## Notes

- **Commit after each phase** - This makes it easy to bisect if something breaks
- **Test between phases** - Don't move to the next phase until the current one works
- **Preserve existing behavior** - No user-facing changes (except resize preserving state in Phase 5)
- **Reference the original plan** - The full plan at `~/.claude/plans/structured-foraging-lighthouse.md` has additional details and examples

Good luck with the refactoring! The architecture will be much cleaner and extensible after these changes.
