# Course Editor

Pygame-based course editor (`golf-editor`). The data it edits is described in
`docs/course_data.md`.

- `core/` - Pygame rendering primitives (tilesets, sprites)
- `ui/` - widgets, dialogs, tile pickers, toolbar
- `controllers/` - editor state, event handling, view state, undo management
- `rendering/` - specialized renderers (terrain, greens, grid, sprites)
- `tools/` - editor tools (paint, transform, eyedropper, forest fill, etc.)
- `algorithms/` - fringe generation and similar

A standalone executable is built with PyInstaller from the repo root:
`uv run pyinstaller run_editor.spec`.

## Three-layer architecture

The editor uses a **strict three-layer architecture**. Violating these boundaries causes
architectural drift and should be avoided.

### Layer 1: Input translation (EventHandler)

`editor/controllers/event_handler.py` translates pygame events into high-level actions.

- MUST route events to the right handler (tools, pickers, toolbar), call Application
  callbacks for state-changing operations, and delegate tool operations to ToolManager.
- MUST NOT modify EditorState, HoleData or any application state directly, implement tool
  logic, or decide what state to change.

```python
# GOOD: delegate to callback
if key == pygame.K_TAB:
    self.on_mode_change()

# BAD: change state directly
if key == pygame.K_TAB:
    self.state.mode = "terrain"  # WRONG LAYER!
```

### Layer 2: Coordination (Application)

`editor/application.py` coordinates components and manages state.

- MUST handle EventHandler callbacks, update EditorState and HoleData, delegate operations
  to tools via ToolManager, invalidate caches when state changes, and create the context
  objects (ViewState, RenderContext, HighlightState) used for rendering.
- MUST NOT handle pygame events directly or implement tool logic.

```python
# GOOD: coordination
def _set_mode(self, mode: str):
    self.state.mode = mode
    self.invalidate_terrain_validation_cache()
    self._update_mode_buttons()

# BAD: tool implementation
def _paint_tile(self, pos):
    tile = self._screen_to_tile(pos)  # Tool logic doesn't belong here
```

### Layer 3: Execution (Tools)

`editor/tools/*.py` execute specific editing operations.

- MUST receive a ToolContext, execute the operation, return a ToolResult saying what
  changed, and own their own state (e.g. TransformTool owns TransformToolState).
- MUST NOT access Application or EventHandler, or handle raw pygame events.

```python
# GOOD: tool execution
def handle_mouse_down(self, pos, button, modifiers, context):
    tile = view_state.screen_to_tile(pos)
    if tile:
        context.hole_data.set_terrain_tile(row, col, value)
        return ToolResult.modified(terrain=True)
```

## Context objects

- **ViewState** (`controllers/view_state.py`) - viewport camera (offset_x, offset_y,
  scale) and coordinate conversions (`screen_to_tile()`, `tile_to_screen()`, ...).
  **Always use these for coordinate conversion**; never re-derive the math.
- **RenderContext** (`rendering/render_context.py`) - rendering resources (tileset,
  sprites, mode) and settings (show_grid, show_sprites, selected_flag_index).
- **HighlightState** (`controllers/highlight_state.py`) - temporary highlights (hover,
  transform preview, invalid tiles), updated via callbacks rather than polled.

## State

- **EditorState** (`controllers/editor_state.py`) - mode, canvas offset, zoom, selected
  palette, flags. Managed by Application, never by EventHandler or tools.
- **HoleData** (`golf/formats/hole_data.py`) - the course data. Modified by tools via
  ToolContext.
- **UndoManager** (`controllers/undo_manager.py`) - snapshot undo/redo. Tools call
  `context.state.undo_manager.push_state(context.hole_data)` *before* modifying data.

## Common pitfalls

- **State changes in EventHandler.** `self.state.show_grid = not self.state.show_grid` in
  a key handler is wrong; call `self.on_toggle_grid()` and let Application change it.
- **Duplicated coordinate math.** Don't compute `(pos[0] - canvas_rect.x + offset_x) //
  tile_size`; use `view_state.screen_to_tile(pos)`.
- **Bypassing ToolManager.** Don't call a specific tool's `handle_mouse_down` directly;
  get `self.tool_manager.get_active_tool()` and route through it.
- **Recreating UI components on resize.** Update positions (`self.toolbar.resize(width)`)
  instead of rebuilding buttons, which leaks.
- **Polling in the render loop.** Don't query key state or picker hover every frame; use
  callbacks such as `TilePicker(..., on_hover_change=self._on_hover)`.

## Adding editor tools

Every tool implements the Tool protocol in `tools/base_tool.py`: `handle_mouse_down`,
`handle_mouse_up`, `handle_mouse_motion`, `handle_key_down`, `handle_key_up`,
`on_activated`, `on_deactivated`, `reset`, `get_hotkey`. Copy the closest existing tool
of the same kind rather than starting from scratch:

| Kind | Behavior | Example to copy |
|------|----------|-----------------|
| Modal | Persistent mode shown in the picker; stays active until another tool is chosen | `paint_tool.py`, `forest_fill_tool.py` |
| Service | Not in the picker; used by other tools via `context.get_eyedropper_tool()` | `eyedropper_tool.py` |
| Action | Picker button that runs immediately in `on_activated()` and leaves the previous tool active; `is_action_tool()` returns `True` | `add_row_tool.py`, `remove_row_tool.py` |
| Dialog | Opens a modal dialog in `on_activated()`, shows as active while open, then calls `context.request_revert_to_previous_tool()` on close; draws via `render_overlay()` | `metadata_editor_tool.py` |

Register the tool in `Application.__init__`:

```python
self.tool_manager.register_tool("your_tool", YourTool())
self.tool_picker.register_tool("your_tool", "Your Tool", "🔧")            # modal / dialog
self.tool_picker.register_tool("your_action", "Your Action", "⚡", is_action=True)  # action
```

`is_action=True` makes the picker execute the tool on every click without changing the
selected tool, so an action can be repeated.

Best practices:

- Return `ToolResult.modified()` when data changes (triggers re-render),
  `ToolResult.handled()` when the event is consumed without a change, and
  `ToolResult.not_handled()` to let other handlers see it.
- Push undo state **before** modifying data.
- Use `context.get_selected_tile()` / `context.set_selected_tile()` for mode-agnostic tile
  access.
- Keep tool-specific state as instance variables (e.g. `self.is_painting`).

## Keys

ToolManager validates hotkey uniqueness on registration and raises `ValueError` on a
conflict. Tool hotkeys currently in use: A, C, D, F, K, M, P, R, S, T, U, V, `=` (add row),
`-` (remove row); `grep -n -A2 'def get_hotkey' editor/tools/*.py` is the source of truth.
Also reserved: G (grid), Tab (mode), 1-3 (flags), Ctrl+Z/Y (undo/redo), Ctrl+S (save),
Ctrl+X (invalid tiles).

## Tool-specific behavior

**Forest Fill**: clicking inside a forest placeholder region fills only that region, not
all regions, and the tool stays active for multiple clicks. Algorithm notes:
`docs/forest_notes.md`.
