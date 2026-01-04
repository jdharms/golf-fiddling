# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a toolset for reverse engineering and editing NES Open Tournament Golf ROM data. The project includes:
- ROM reading and decompression tools
- Course data extraction and visualization
- A graphical course editor built with Pygame

## Development Commands

### Setup
```bash
# Install dependencies (uses uv for package management)
uv sync
```

### Running Tools
The project provides several command-line tools via entry points (defined in `pyproject.toml`):

```bash
# Extract all course data from ROM to JSON files with compression statistics
golf-dump <rom_file.nes> <output_dir>

# Analyze ROM structure and show technical details
golf-analyze <rom_file.nes> [hole_number]

# Visualize a hole as PNG (renders terrain + greens with sprites)
golf-visualize <tileset.bin> <hole.json> [output.png]

# Visualize an entire course directory
golf-visualize <tileset.bin> <course_dir> [output_dir]

# Convert hex string to binary file
golf-hex2bin

# Expand dictionary codes into their complete horizontal transition sequences
golf-expand-dict <meta.json> [terrain|greens]

# Launch the course editor (requires CHR binary files)
golf-editor <terrain_chr.bin> <greens_chr.bin> [hole.json]
```

### Example Workflow
```bash
# Extract all courses from ROM
golf-dump nes_open_us.nes courses/

# Visualize a specific hole
golf-visualize data/chr-ram.bin courses/japan/hole_01.json output.png

# Or visualize an entire course
golf-visualize data/chr-ram.bin courses/japan/ renders/japan/

# Edit a hole in the visual editor
golf-editor data/chr-ram.bin data/green-ram.bin courses/japan/hole_01.json
```

### JSON Inspection

When inspecting JSON files in `courses/` and `data/`, prefer using `jq` over `python -c` one-liners for readability and convenience.

## Code Architecture

### Package Structure

The codebase is organized into three main packages:

**`golf/`** - Shared library for ROM reading and data formats
- `core/` - ROM reading, decompression, NES graphics (CHR tiles, palettes)
- `formats/` - Hole data model, JSON serialization, hex utilities
- `rendering/` - PIL-based rendering for visualization

**`editor/`** - Interactive Pygame-based course editor
- `core/` - Pygame rendering primitives (tilesets, sprites)
- `ui/` - Widgets, dialogs, tile pickers, toolbar
- `controllers/` - Editor state, event handling, view state, undo management
- `rendering/` - Specialized renderers (terrain, greens, grid, sprites)
- `tools/` - Editor tools (paint, transform, eyedropper, forest fill, etc.)

**`tools/`** - Command-line utilities
- `dump.py` - Extract course data from ROM to JSON
- `analyze.py` - ROM structure analysis
- `visualize.py` - Static rendering of holes to PNG
- `hex2bin.py` - Hex string converter

### Key Architecture Concepts

**ROM Memory Model**: NES ROMs use bank switching. The game has a fixed bank ($C000-$FFFF, bank 15) containing pointer tables and lookup data, plus switchable banks ($8000-$BFFF) containing compressed course data. The `RomReader` class handles CPU address translation to PRG ROM offsets.

**Decompression**: Course terrain and greens use a custom compression scheme with three stages:
1. RLE + dictionary expansion (codes $E0+ expand to multiple bytes)
2. Horizontal transitions (low byte values trigger table lookups)
3. Vertical fill (0 bytes copy from row above with transformation)

Separate decompression tables exist for terrain (in fixed bank) and greens (in switchable banks).

**Data Model**: `HoleData` is the central model for hole information. It stores:
- Terrain tiles (22 columns wide, variable height)
- Greens tiles (24x24 grid)
- Attributes (palette indices for 2x2 supertiles)
- Metadata (par, distance, tee/green positions, flag positions)

**JSON Format**: Holes are stored as JSON with hex-encoded tile rows (e.g., "A2 A3 A0 A1"). This compact format is human-readable and can be directly edited.

**CHR Graphics**: NES graphics use 8x8 tiles stored in CHR format. The codebase requires extracted CHR binaries for terrain and greens tilesets. `Tileset` class handles loading and rendering CHR tiles with NES palettes.

**Sprite Rendering**: Sprite definitions in `data/sprites/*.json` define NES sprite-based objects (ball, flag, tee markers) with tile data and palette information.

### Course Data Organization

- **3 courses**: Japan, US, UK (in that order - Japan was developed first)
- **18 holes per course** (54 total holes)
- **Course files**: `courses/{country}/hole_{01-18}.json` and `courses/{country}/course.json`
- **Coordinates**: All positions use pixel coordinates (x, y)

### Important Coordinate Systems

- **Terrain tiles**: 22 tiles wide, variable height (typically 30-40 rows)
- **Supertiles**: 2x2 tile blocks used for attribute (palette) mapping
- **Attributes**: 11 columns wide (12 supertiles minus 1 HUD column)
- **Greens tiles**: Fixed 24x24 grid centered at green position
- **Screen coordinates**: Editor uses scrollable viewport with zoom

### NES-Specific Details

- **Palettes**: 4 palettes of 4 colors each for terrain; separate palettes for greens
- **Attributes**: Packed as 4 2-bit values per byte covering 4x4 tile areas
- **BCD encoding**: Distances stored as Binary-Coded Decimal
- **Bank numbers**: Course data bank determined by `TABLE_COURSE_BANK_TERRAIN`

### Editor Architecture (THREE-LAYER PATTERN)

The editor uses a **strict three-layer architecture**. Violating these boundaries causes architectural drift and should be avoided:

#### Layer 1: Input Translation (EventHandler)
**Purpose:** Translate pygame events into high-level actions
**Location:** `editor/controllers/event_handler.py`

**MUST:**
- Route events to appropriate handlers (tools, pickers, toolbar)
- Call Application callbacks for state-changing operations
- Delegate tool operations to ToolManager

**MUST NOT:**
- Modify EditorState, HoleData, or any application state directly
- Implement tool logic (that belongs in tools)
- Make decisions about what state to change

**Example:**
```python
# GOOD: Delegate to callback
if key == pygame.K_TAB:
    self.on_mode_change()

# BAD: Change state directly
if key == pygame.K_TAB:
    self.state.mode = "terrain"  # WRONG LAYER!
```

#### Layer 2: Coordination (Application)
**Purpose:** Coordinate between components and manage state
**Location:** `editor/application.py`

**MUST:**
- Handle callbacks from EventHandler
- Update EditorState and HoleData
- Delegate operations to tools via ToolManager
- Invalidate caches when state changes
- Create context objects (ViewState, RenderContext, HighlightState) for rendering

**MUST NOT:**
- Directly handle pygame events (EventHandler does this)
- Implement tool logic (tools do this)

**Example:**
```python
# GOOD: Coordination
def _set_mode(self, mode: str):
    self.state.mode = mode
    self.invalidate_terrain_validation_cache()
    self._update_mode_buttons()

# BAD: Tool implementation
def _paint_tile(self, pos):
    tile = self._screen_to_tile(pos)  # Tool logic doesn't belong here
```

#### Layer 3: Execution (Tools)
**Purpose:** Execute specific editing operations
**Location:** `editor/tools/*.py`

**MUST:**
- Receive ToolContext with access to state
- Execute the specific operation (paint, transform, sample, etc.)
- Return ToolResult to signal what changed
- Own their own state (e.g., TransformTool owns TransformToolState)

**MUST NOT:**
- Directly access Application or EventHandler
- Handle raw pygame events (EventHandler routes them)

**Example:**
```python
# GOOD: Tool execution
def handle_mouse_down(self, pos, button, modifiers, context):
    tile = view_state.screen_to_tile(pos)
    if tile:
        context.hole_data.set_terrain_tile(row, col, value)
        return ToolResult.modified(terrain=True)
```

#### Context Objects

The refactored architecture uses three context objects to reduce parameter passing:

**ViewState** (`editor/controllers/view_state.py`)
- Manages viewport camera (offset_x, offset_y, scale)
- Provides coordinate conversions: `screen_to_tile()`, `tile_to_screen()`, etc.
- **Always use ViewState methods for coordinate conversion** - don't duplicate this logic

**RenderContext** (`editor/rendering/render_context.py`)
- Bundles rendering resources: tileset, sprites, mode
- Bundles rendering settings: show_grid, show_sprites, selected_flag_index

**HighlightState** (`editor/controllers/highlight_state.py`)
- Manages temporary visual highlights: hover, transform preview, invalid tiles
- Updated via callbacks (event-driven, not polled)

#### State Management

**EditorState** (`editor/controllers/editor_state.py`)
- Application-level state: mode, canvas offset, zoom, selected palette, flags
- Managed by Application, never by EventHandler or Tools

**HoleData** (`golf/formats/hole_data.py`)
- Course data model: terrain tiles, greens tiles, attributes, metadata
- Modified by Tools via ToolContext
- Supports undo/redo via UndoManager

**UndoManager** (`editor/controllers/undo_manager.py`)
- Manages undo/redo stack via snapshots
- Tools call `context.state.undo_manager.push_state()` before modifications

### Common Pitfalls to Avoid

**❌ DON'T: Put state changes in EventHandler**
```python
# BAD - EventHandler should not modify state
def _handle_key_down(self, event):
    if event.key == pygame.K_g:
        self.state.show_grid = not self.state.show_grid  # WRONG!
```

```python
# GOOD - EventHandler calls callback, Application changes state
def _handle_key_down(self, event):
    if event.key == pygame.K_g:
        self.on_toggle_grid()  # Application handles it
```

**❌ DON'T: Duplicate coordinate conversion logic**
```python
# BAD - Reimplementing screen_to_tile
local_x = pos[0] - canvas_rect.x + offset_x
local_y = pos[1] - canvas_rect.y + offset_y
tile_col = local_x // tile_size
```

```python
# GOOD - Use ViewState
tile = view_state.screen_to_tile(pos)
```

**❌ DON'T: Bypass ToolManager**
```python
# BAD - Directly calling tool methods
if shift_held:
    transform_tool.handle_mouse_down(pos, button, mods, ctx)
```

```python
# GOOD - Let ToolManager route
tool = self.tool_manager.get_active_tool()
if tool:
    result = tool.handle_mouse_down(pos, button, mods, ctx)
```

**❌ DON'T: Recreate UI components on resize**
```python
# BAD - Creates new buttons every resize
def on_resize(self, width, height):
    self.buttons = self._create_buttons()  # Memory leak!
```

```python
# GOOD - Update existing components
def on_resize(self, width, height):
    self.toolbar.resize(width)  # Updates positions only
```

**❌ DON'T: Poll for state in render loop**
```python
# BAD - Checking state every frame
def render(self):
    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
        hover = self.picker.get_hovered_tile()  # Inefficient!
```

```python
# GOOD - Use callbacks
def __init__(self):
    self.picker = TilePicker(..., on_hover_change=self._on_hover)

def _on_hover(self, tile):
    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
        self.highlight_state.set_picker_hover(tile)  # Event-driven
```

## Development Notes

### Adding New Tools

To add a new command-line tool:
1. Create the tool as a Python module in `tools/` with a `main()` function
2. Add an entry point in `pyproject.toml` under `[project.scripts]`
3. Tools become available as `golf-<tool-name>` after running `uv sync`

Example: `golf-expand-dict = "tools.expand_dict:main"` makes `golf-expand-dict` available as a command.

### Adding Editor Tools

Editor tools are separate classes that handle specific editing operations (paint, transform, eyedropper, etc.).

**To add a new editor tool:**

1. Create tool class in `editor/tools/your_tool.py` implementing the Tool protocol:
```python
class YourTool:
    def handle_mouse_down(self, pos, button, modifiers, context):
        # Handle mouse press
        return ToolResult.handled()

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
```

2. Register tool in `editor/application.py` `__init__`:
```python
self.tool_manager.register_tool("your_tool", YourTool())
```

3. Activate tool via ToolManager or keyboard shortcut in EventHandler

**Tool Best Practices:**
- Return `ToolResult.modified()` when data changes (triggers re-render)
- Return `ToolResult.handled()` when event is consumed but no change
- Return `ToolResult.not_handled()` to let other handlers process event
- Push undo state BEFORE modifying data: `context.state.undo_manager.push_state(context.hole_data)`
- Use `context.get_selected_tile()` / `context.set_selected_tile()` for mode-agnostic tile access
- Store tool-specific state as instance variables (e.g., `self.is_painting`)

## Testing

### Running Tests

A comprehensive test suite for the compression system is located in the `tests/` directory. Tests are written using pytest and cover both unit and integration testing.

Tests must be executed and must pass after all changes.  There are no "ok failures".  Ever.

```bash
# Run all tests with coverage
pytest

# Run only unit tests (tests individual compression functions)
pytest tests/unit/

# Run only integration tests (round-trip compression/decompression)
pytest tests/integration/

# Run specific test file
pytest tests/unit/test_vertical_fill.py -v

# Run with verbose output and see print statements
pytest -v -s

# Generate coverage report
pytest --cov=golf --cov-report=html
```

### Test Structure

- **Unit Tests** (`tests/unit/`)
- **Integration Tests** (`tests/integration/`)
- **Test Fixtures** (`tests/fixtures/` and `tests/conftest.py`):
  - Real compression tables from `data/tables/compression_tables.json`
  - Mock minimal tables for unit testing
  - Real hole data from `courses/japan/`
  - Hand-crafted test fixtures (simple terrain/greens)

## Claude Code Preferences

- **Commit messages**: Please do not author commit messages. I prefer to write them myself to capture the specific context and rationale.
- **Updating this file**: When planning changes that would contradict or obsolete information in this CLAUDE.md file, include a step in your plan to update CLAUDE.md accordingly. This ensures architectural documentation stays current with the codebase.
