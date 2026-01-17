"""Integration tests for undo/redo with editor components."""

import pytest
from pygame import Rect

from unittest.mock import Mock

from editor.controllers.editor_state import EditorState
from editor.controllers.event_handler import EventHandler
from editor.controllers.transform_logic import TransformLogic
from editor.core.pygame_rendering import Tileset
from editor.tools.tool_manager import ToolManager
from editor.tools.row_operations_tool import RowOperationsTool
from editor.ui.pickers import GreensTilePicker, TilePicker
from golf.core.compressor import load_compression_tables
from golf.formats.hole_data import HoleData


@pytest.fixture
def editor_setup():
    """Set up editor components for testing."""
    state = EditorState()
    hole_data = HoleData()

    # Initialize hole with realistic data
    hole_data.terrain = [[0xA0 + i] * 22 for i in range(30)]
    hole_data.terrain_height = 30  # Set terrain height
    hole_data.attributes = [[1] * 11 for _ in range(15)]
    hole_data.greens = [[0xC0] * 24 for _ in range(24)]
    hole_data.green_x = 100
    hole_data.green_y = 200
    hole_data.metadata = {"par": 4, "distance": 350, "flag_positions": [(100, 100)]}
    hole_data.filepath = "/test/hole.json"

    # Create tilesets and pickers
    terrain_ts = Tileset("data/chr-ram.bin")
    greens_ts = Tileset("data/chr-ram.bin")
    picker_rect = Rect(0, 50, 100, 100)
    terrain_picker = TilePicker(terrain_ts, picker_rect)
    greens_picker = GreensTilePicker(greens_ts, picker_rect)

    # Create tool manager and register tools
    tool_manager = ToolManager()
    row_operations_tool = RowOperationsTool()
    tool_manager.register_tool("row_operations", row_operations_tool)

    # Create event handler
    transform_logic = TransformLogic(load_compression_tables())
    mock_tool_picker = Mock()
    mock_stamp_browser = Mock()
    event_handler = EventHandler(
        state,
        hole_data,
        terrain_picker,
        greens_picker,
        [],
        800,
        600,
        tool_manager,
        mock_tool_picker,
        mock_stamp_browser,
        on_load=lambda: None,
        on_load_file=lambda path: None,
        on_save=lambda: None,
        on_mode_change=lambda: None,
        on_flag_change=lambda: None,
        on_resize=lambda w, h: None,
        on_tool_change=lambda: None,
    )

    # Set transform_logic and forest_filler on tool_context
    event_handler.tool_context.transform_logic = transform_logic
    event_handler.tool_context.forest_filler = None

    return {
        "state": state,
        "hole_data": hole_data,
        "event_handler": event_handler,
        "terrain_picker": terrain_picker,
        "greens_picker": greens_picker,
        "row_operations_tool": row_operations_tool,
    }


class TestPaintStrokeUndo:
    """Tests for undo/redo of paint strokes."""

    def test_paint_stroke_groups_into_single_undo(self, editor_setup):
        """Multiple paint operations should group into single undo action."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]

        # Simulate start of paint stroke
        state.undo_manager.push_state(hole_data)
        state.painting = True

        # Paint multiple tiles
        hole_data.set_terrain_tile(5, 5, 0xB0)
        hole_data.set_terrain_tile(5, 6, 0xB1)
        hole_data.set_terrain_tile(5, 7, 0xB2)

        # End paint stroke
        state.painting = False

        # Undo should restore all tiles
        assert state.undo_manager.can_undo()
        restored = state.undo_manager.undo(hole_data)

        assert restored.terrain[5][5] == 0xA5
        assert restored.terrain[5][6] == 0xA5
        assert restored.terrain[5][7] == 0xA5

    def test_multiple_paint_strokes_separate_undos(self, editor_setup):
        """Each paint stroke should be separate undo action."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]

        # First stroke
        state.undo_manager.push_state(hole_data)
        state.painting = True
        hole_data.set_terrain_tile(5, 5, 0xB0)
        hole_data.set_terrain_tile(5, 6, 0xB1)
        state.painting = False

        # Second stroke
        state.undo_manager.push_state(hole_data)
        state.painting = True
        hole_data.set_terrain_tile(6, 5, 0xC0)
        hole_data.set_terrain_tile(6, 6, 0xC1)
        state.painting = False

        # Should have 2 undo levels
        assert len(state.undo_manager.undo_stack) == 2

        # First undo reverses second stroke
        restored1 = state.undo_manager.undo(hole_data)
        assert restored1.terrain[6][5] == 0xA6
        assert restored1.terrain[6][6] == 0xA6

    def test_terrain_mode_paint_undo(self, editor_setup):
        """Terrain mode painting should be undoable."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        terrain_picker = editor_setup["terrain_picker"]

        state.mode = "terrain"
        terrain_picker.selected_tile = 0xA5

        # Simulate paint
        state.undo_manager.push_state(hole_data)
        original_val = hole_data.terrain[5][5]
        hole_data.set_terrain_tile(5, 5, 0xA5)

        # Undo
        restored = state.undo_manager.undo(hole_data)
        assert restored.terrain[5][5] == original_val

    def test_greens_mode_paint_undo(self, editor_setup):
        """Greens mode painting should be undoable."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        greens_picker = editor_setup["greens_picker"]

        state.mode = "greens"
        greens_picker.selected_tile = 0xD5

        # Simulate paint
        state.undo_manager.push_state(hole_data)
        original_val = hole_data.greens[5][5]
        hole_data.set_greens_tile(5, 5, 0xD5)

        # Undo
        restored = state.undo_manager.undo(hole_data)
        assert restored.greens[5][5] == original_val

    def test_palette_mode_paint_undo(self, editor_setup):
        """Palette mode painting should be undoable."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]

        state.mode = "palette"
        state.selected_palette = 2

        # Simulate paint
        state.undo_manager.push_state(hole_data)
        original_val = hole_data.attributes[5][5]
        hole_data.set_attribute(5, 5, 2)

        # Undo
        restored = state.undo_manager.undo(hole_data)
        assert restored.attributes[5][5] == original_val


class TestRowOperationUndo:
    """Tests for undo/redo of row add/remove operations."""

    def test_add_row_undo(self, editor_setup):
        """Adding rows should be undoable (adds 2 rows at a time)."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        initial_height = hole_data.terrain_height

        # Add row (this pushes undo state internally, adds 2 rows)
        row_operations_tool.add_row(event_handler.tool_context, False)

        assert hole_data.terrain_height == initial_height + 2
        assert state.undo_manager.can_undo()

        # Undo
        restored = state.undo_manager.undo(hole_data)
        assert restored.terrain_height == initial_height

    def test_remove_row_undo(self, editor_setup):
        """Removing rows should be undoable (removes 2 rows at a time, soft removal)."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        # Start with more rows so we can remove (minimum is 30)
        hole_data.terrain_height = 34
        initial_height = hole_data.terrain_height

        # Remove row (soft removal: decreases height by 2, keeps data)
        row_operations_tool.remove_row(event_handler.tool_context, False)

        assert hole_data.terrain_height == initial_height - 2
        assert state.undo_manager.can_undo()

        # Undo
        restored = state.undo_manager.undo(hole_data)
        assert restored.terrain_height == initial_height

    def test_add_multiple_rows_separate_undos(self, editor_setup):
        """Each row add should be separate undo action (adds 2 rows each time)."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        initial_height = hole_data.terrain_height

        # Add 3 times (2 rows each = 6 rows total)
        row_operations_tool.add_row(event_handler.tool_context, False)
        row_operations_tool.add_row(event_handler.tool_context, False)
        row_operations_tool.add_row(event_handler.tool_context, False)

        assert hole_data.terrain_height == initial_height + 6
        assert len(state.undo_manager.undo_stack) == 3

        # Undo each one
        s1 = state.undo_manager.undo(hole_data)
        assert s1.terrain_height == initial_height + 4

        s2 = state.undo_manager.undo(s1)
        assert s2.terrain_height == initial_height + 2

        s3 = state.undo_manager.undo(s2)
        assert s3.terrain_height == initial_height

    def test_add_undo_redo_row_sequence(self, editor_setup):
        """Should handle add/undo/redo sequences for rows (adds 2 rows at a time)."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        initial_height = hole_data.terrain_height

        # Add row (adds 2 rows)
        row_operations_tool.add_row(event_handler.tool_context, False)
        assert hole_data.terrain_height == initial_height + 2

        # Undo
        s1 = state.undo_manager.undo(hole_data)
        assert s1.terrain_height == initial_height

        # Redo
        s2 = state.undo_manager.redo(s1)
        assert s2.terrain_height == initial_height + 2


class TestFileLoadClearsUndoHistory:
    """Tests that loading a file clears undo/redo history."""

    def test_set_initial_state_clears_history(self, editor_setup):
        """set_initial_state should clear undo/redo on file load."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        # Build up undo stack
        row_operations_tool.add_row(event_handler.tool_context, False)
        row_operations_tool.add_row(event_handler.tool_context, False)

        assert len(state.undo_manager.undo_stack) == 2

        # Load new file (simulated)
        new_hole = HoleData()
        state.undo_manager.set_initial_state(new_hole)

        assert len(state.undo_manager.undo_stack) == 0
        assert len(state.undo_manager.redo_stack) == 0

    def test_undo_redo_after_load(self, editor_setup):
        """Should be able to undo/redo after file load."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        # Build up history
        row_operations_tool.add_row(event_handler.tool_context, False)

        # Load new file
        new_hole = HoleData()
        new_hole.terrain = [[0xA0] * 22 for _ in range(30)]
        state.undo_manager.set_initial_state(new_hole)

        # Old history should be gone
        assert state.undo_manager.can_undo() is False
        assert state.undo_manager.can_redo() is False

        # New operations should work
        event_handler.hole_data = new_hole
        event_handler.tool_context.hole_data = new_hole
        row_operations_tool.add_row(event_handler.tool_context, False)
        assert state.undo_manager.can_undo()


class TestComplexUndoRedoSequences:
    """Tests for complex sequences of undo/redo operations."""

    def test_paint_then_row_then_undo(self, editor_setup):
        """Should handle paint, row op, then undo in sequence."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        initial_height = hole_data.terrain_height

        # Paint stroke
        state.undo_manager.push_state(hole_data)
        state.painting = True
        hole_data.set_terrain_tile(5, 5, 0xB5)
        state.painting = False

        # Add row (adds 2 rows)
        row_operations_tool.add_row(event_handler.tool_context, False)

        # Should have 2 undo states
        assert len(state.undo_manager.undo_stack) == 2

        # Undo row add
        s1 = state.undo_manager.undo(hole_data)
        assert s1.terrain_height == initial_height

        # Undo paint
        s2 = state.undo_manager.undo(s1)
        assert s2.terrain[5][5] == 0xA5

    def test_undo_redo_undo_redo_cycle(self, editor_setup):
        """Should handle undo/redo/undo/redo cycles (adds 2 rows at a time)."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]
        event_handler = editor_setup["event_handler"]
        row_operations_tool = editor_setup["row_operations_tool"]

        initial_height = hole_data.terrain_height

        # Add row (adds 2 rows)
        row_operations_tool.add_row(event_handler.tool_context, False)

        # Undo
        s1 = state.undo_manager.undo(hole_data)
        assert s1.terrain_height == initial_height

        # Redo
        s2 = state.undo_manager.redo(s1)
        assert s2.terrain_height == initial_height + 2

        # Undo again
        s3 = state.undo_manager.undo(s2)
        assert s3.terrain_height == initial_height

        # Redo again
        s4 = state.undo_manager.redo(s3)
        assert s4.terrain_height == initial_height + 2

    def test_paint_undo_new_paint_clears_redo(self, editor_setup):
        """New paint after undo should clear redo stack."""
        state = editor_setup["state"]
        hole_data = editor_setup["hole_data"]

        # Paint and push
        state.undo_manager.push_state(hole_data)
        state.painting = True
        hole_data.set_terrain_tile(5, 5, 0xB5)
        state.painting = False

        # Undo
        s1 = state.undo_manager.undo(hole_data)
        assert state.undo_manager.can_redo()

        # New paint stroke should clear redo
        state.undo_manager.push_state(s1)
        state.painting = True
        s1.set_terrain_tile(6, 6, 0xC6)
        state.painting = False

        assert state.undo_manager.can_redo() is False
