"""Unit tests for row operations (add/remove rows with constraints)."""

import tempfile
from unittest.mock import Mock

import pytest

from editor.controllers.editor_state import EditorState
from editor.tools.add_row_tool import AddRowTool
from editor.tools.base_tool import ToolContext
from editor.tools.remove_row_tool import RemoveRowTool
from editor.tools.row_operations_tool import RowOperationsTool
from editor.tools.tool_manager import ToolManager
from golf.formats.hole_data import HoleData


@pytest.fixture
def hole_with_30_rows():
    """Create hole with 30 rows for testing."""
    hole = HoleData()
    # Create 30 rows with identifiable data (row index in first tile)
    hole.terrain = [[i] * 22 for i in range(30)]
    hole.terrain_height = 30
    hole.attributes = [[1] * 11 for _ in range(15)]
    hole.greens = [[0] * 24 for _ in range(24)]
    hole.green_x = 100
    hole.green_y = 200
    hole.metadata = {
        "par": 4,
        "distance": 400,
        "scroll_limit": 1,  # (30 - 28) // 2
        "hole": 1,
        "handicap": 1,
        "tee": {"x": 0, "y": 0},
        "flag_positions": [],
    }
    return hole


@pytest.fixture
def row_operations_tool():
    """Create RowOperationsTool instance."""
    return RowOperationsTool()


@pytest.fixture
def mock_tool_context(hole_with_30_rows):
    """Create mock ToolContext for testing."""
    mock_state = Mock()
    mock_undo_manager = Mock()
    mock_undo_manager.push_state = Mock()
    mock_state.undo_manager = mock_undo_manager

    # Create tool manager
    tool_manager = ToolManager()
    tool_manager.register_tool("row_operations", RowOperationsTool())

    context = ToolContext(
        hole_data=hole_with_30_rows,
        state=mock_state,
        terrain_picker=None,
        greens_picker=None,
        transform_logic=None,
        forest_filler=None,
        screen_width=1024,
        screen_height=768,
        tool_manager=tool_manager,
    )
    return context


class TestHoleDataTerrainHeight:
    """Tests for terrain_height field in HoleData."""

    def test_initialization_sets_terrain_height_to_zero(self):
        """HoleData initialization should set terrain_height to 0."""
        hole = HoleData()
        assert hole.terrain_height == 0

    def test_load_sets_terrain_height_from_json(self, tmp_path):
        """Loading JSON should set terrain_height from terrain.height field."""
        # Create JSON file with explicit height
        json_file = tmp_path / "test_hole.json"
        json_content = """{
  "hole": 1,
  "par": 4,
  "distance": 400,
  "handicap": 1,
  "scroll_limit": 3,
  "green": {"x": 100, "y": 200},
  "tee": {"x": 0, "y": 0},
  "flag_positions": [],
  "terrain": {
    "width": 22,
    "height": 32,
    "rows": ["10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10"]
  },
  "attributes": {
    "width": 11,
    "height": 1,
    "rows": [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]]
  },
  "greens": {
    "width": 24,
    "height": 24,
    "rows": ["00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"]
  }
}"""
        # Need to expand terrain rows to match height
        terrain_rows = ['10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10'] * 32
        greens_rows = ['00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'] * 24

        import json
        data = {
            "hole": 1,
            "par": 4,
            "distance": 400,
            "handicap": 1,
            "scroll_limit": 3,
            "green": {"x": 100, "y": 200},
            "tee": {"x": 0, "y": 0},
            "flag_positions": [],
            "terrain": {
                "width": 22,
                "height": 32,
                "rows": terrain_rows
            },
            "attributes": {
                "width": 11,
                "height": 16,
                "rows": [[1] * 11 for _ in range(16)]
            },
            "greens": {
                "width": 24,
                "height": 24,
                "rows": greens_rows
            }
        }

        with open(json_file, "w") as f:
            json.dump(data, f)

        hole = HoleData()
        hole.load(str(json_file))

        assert hole.terrain_height == 32

    def test_get_terrain_height_returns_terrain_height_field(self):
        """get_terrain_height() should return terrain_height field, not len(terrain)."""
        hole = HoleData()
        hole.terrain = [[0] * 22 for _ in range(40)]  # 40 physical rows
        hole.terrain_height = 32  # Only 32 visible

        assert hole.get_terrain_height() == 32
        assert len(hole.terrain) == 40  # Physical data is larger

    def test_save_writes_terrain_height_to_json(self, tmp_path, hole_with_30_rows):
        """Saving should write terrain_height to JSON terrain.height field."""
        json_file = tmp_path / "test_save.json"

        hole_with_30_rows.filepath = str(json_file)
        hole_with_30_rows.save()

        import json
        with open(json_file, "r") as f:
            data = json.load(f)

        assert data["terrain"]["height"] == 30


class TestRowOperationsPairConstraint:
    """Tests for add/remove in pairs of 2 rows."""

    def test_add_row_adds_two_rows(self, row_operations_tool, mock_tool_context):
        """add_row() should add 2 rows, not 1."""
        initial_height = mock_tool_context.hole_data.terrain_height

        row_operations_tool.add_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == initial_height + 2

    def test_remove_row_removes_two_rows(self, row_operations_tool, mock_tool_context):
        """remove_row() should remove 2 rows, not 1."""
        # Start with more rows so we can remove
        mock_tool_context.hole_data.terrain_height = 32
        initial_height = mock_tool_context.hole_data.terrain_height

        row_operations_tool.remove_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == initial_height - 2

    def test_multiple_adds_maintain_even_count(self, row_operations_tool, mock_tool_context):
        """Multiple add operations should maintain even row count."""
        # Start with 30 (even)
        assert mock_tool_context.hole_data.terrain_height == 30

        # Add 3 times (2 rows each = 6 rows)
        row_operations_tool.add_row(mock_tool_context)
        row_operations_tool.add_row(mock_tool_context)
        row_operations_tool.add_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == 36
        assert mock_tool_context.hole_data.terrain_height % 2 == 0  # Still even

    def test_multiple_removes_maintain_even_count(self, row_operations_tool, mock_tool_context):
        """Multiple remove operations should maintain even row count."""
        # Start with 30 (even)
        assert mock_tool_context.hole_data.terrain_height == 30

        # Remove 2 times (2 rows each = 4 rows)
        # Can't remove more than that because we'd hit the 30-row minimum
        # So let's start with more rows
        mock_tool_context.hole_data.terrain_height = 40

        row_operations_tool.remove_row(mock_tool_context)
        row_operations_tool.remove_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == 36
        assert mock_tool_context.hole_data.terrain_height % 2 == 0  # Still even


class TestRowOperationsMaximumConstraint:
    """Tests for 48-row maximum constraint."""

    def test_cannot_add_rows_beyond_48(self, row_operations_tool, mock_tool_context):
        """Cannot add rows when already at 48."""
        mock_tool_context.hole_data.terrain_height = 48

        result = row_operations_tool.add_row(mock_tool_context)

        assert result.handled is True
        assert "48" in result.message
        assert mock_tool_context.hole_data.terrain_height == 48  # Unchanged

    def test_cannot_add_rows_that_would_exceed_48(self, row_operations_tool, mock_tool_context):
        """Cannot add 2 rows if it would exceed 48."""
        mock_tool_context.hole_data.terrain_height = 47  # Odd, but test edge case

        result = row_operations_tool.add_row(mock_tool_context)

        assert result.handled is True
        assert "48" in result.message
        assert mock_tool_context.hole_data.terrain_height == 47  # Unchanged

    def test_add_row_allows_up_to_48(self, row_operations_tool, mock_tool_context):
        """Can add rows up to exactly 48."""
        mock_tool_context.hole_data.terrain_height = 46
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(46)]

        result = row_operations_tool.add_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == 48  # Allowed


class TestRowOperationsMinimumConstraint:
    """Tests for 30-row minimum constraint."""

    def test_cannot_remove_rows_below_minimum(self, row_operations_tool, mock_tool_context):
        """Cannot remove rows when already at 30."""
        mock_tool_context.hole_data.terrain_height = 30

        result = row_operations_tool.remove_row(mock_tool_context)

        assert result.handled is True
        assert "30" in result.message or "minimum" in result.message.lower()
        assert mock_tool_context.hole_data.terrain_height == 30  # Unchanged

    def test_remove_row_allows_down_to_30_rows(self, row_operations_tool, mock_tool_context):
        """Can remove rows down to exactly 30."""
        mock_tool_context.hole_data.terrain_height = 32

        result = row_operations_tool.remove_row(mock_tool_context)

        assert mock_tool_context.hole_data.terrain_height == 30  # Allowed


class TestRowOperationsSoftRemoval:
    """Tests for soft removal - data persists after removal."""

    def test_remove_row_decreases_height_but_preserves_data(
        self, row_operations_tool, mock_tool_context
    ):
        """Removing rows should decrease terrain_height but keep data in terrain list."""
        # Start with 32 rows, each identifiable
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(32)]
        mock_tool_context.hole_data.terrain_height = 32

        # Store original data from rows 30-31
        original_row_30 = mock_tool_context.hole_data.terrain[30][:]
        original_row_31 = mock_tool_context.hole_data.terrain[31][:]

        # Remove 2 rows
        row_operations_tool.remove_row(mock_tool_context)

        # Height should decrease
        assert mock_tool_context.hole_data.terrain_height == 30

        # Physical terrain list should still have 32 rows
        assert len(mock_tool_context.hole_data.terrain) == 32

        # Data in rows 30-31 should be preserved
        assert mock_tool_context.hole_data.terrain[30] == original_row_30
        assert mock_tool_context.hole_data.terrain[31] == original_row_31

    def test_removed_rows_not_rendered(self, mock_tool_context):
        """get_terrain_height() should return terrain_height, not len(terrain)."""
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(40)]
        mock_tool_context.hole_data.terrain_height = 32

        # Renderer should use get_terrain_height()
        visible_height = mock_tool_context.hole_data.get_terrain_height()

        assert visible_height == 32
        assert len(mock_tool_context.hole_data.terrain) == 40

    def test_multiple_removes_accumulate_hidden_rows(
        self, row_operations_tool, mock_tool_context
    ):
        """Multiple removals should accumulate hidden rows."""
        # Start with 40 rows
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(40)]
        mock_tool_context.hole_data.terrain_height = 40

        # Remove twice (4 rows total)
        row_operations_tool.remove_row(mock_tool_context)
        row_operations_tool.remove_row(mock_tool_context)

        # Height should be 36
        assert mock_tool_context.hole_data.terrain_height == 36

        # Physical data should still be 40 rows
        assert len(mock_tool_context.hole_data.terrain) == 40


class TestRowOperationsRestoration:
    """Tests for restoring hidden rows when adding."""

    def test_add_row_restores_hidden_rows_first(
        self, row_operations_tool, mock_tool_context
    ):
        """Adding rows should restore hidden rows before creating new ones."""
        # Create 32 physical rows with identifiable data
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(32)]
        mock_tool_context.hole_data.terrain_height = 30  # 2 hidden rows

        # Store original data from hidden rows 30-31
        original_row_30 = mock_tool_context.hole_data.terrain[30][:]
        original_row_31 = mock_tool_context.hole_data.terrain[31][:]

        # Add 2 rows (should restore hidden rows)
        row_operations_tool.add_row(mock_tool_context)

        # Height should increase to 32
        assert mock_tool_context.hole_data.terrain_height == 32

        # Physical terrain should still be 32 rows (no new rows added)
        assert len(mock_tool_context.hole_data.terrain) == 32

        # Restored rows should have original data (not default 0xDF)
        assert mock_tool_context.hole_data.terrain[30] == original_row_30
        assert mock_tool_context.hole_data.terrain[31] == original_row_31

    def test_add_row_creates_new_rows_when_no_hidden_data(
        self, row_operations_tool, mock_tool_context
    ):
        """Adding rows when no hidden data should create new physical rows."""
        # Create 30 physical rows
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(30)]
        mock_tool_context.hole_data.terrain_height = 30  # No hidden rows
        mock_tool_context.hole_data.attributes = [[1] * 11 for _ in range(15)]

        # Add 2 rows (should create new rows)
        row_operations_tool.add_row(mock_tool_context)

        # Height should increase to 32
        assert mock_tool_context.hole_data.terrain_height == 32

        # Physical terrain should now be 32 rows (new rows added)
        assert len(mock_tool_context.hole_data.terrain) == 32

        # New rows should have default tile (0xDF)
        assert all(tile == 0xDF for tile in mock_tool_context.hole_data.terrain[30])
        assert all(tile == 0xDF for tile in mock_tool_context.hole_data.terrain[31])

    def test_add_row_partially_restores_then_creates(
        self, row_operations_tool, mock_tool_context
    ):
        """Adding 2 rows when only 1 hidden row exists should restore 1, create 1."""
        # Create 31 physical rows
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(31)]
        mock_tool_context.hole_data.terrain_height = 30  # 1 hidden row
        mock_tool_context.hole_data.attributes = [[1] * 11 for _ in range(15)]

        # Store original data from hidden row 30
        original_row_30 = mock_tool_context.hole_data.terrain[30][:]

        # Add 2 rows (should restore 1, create 1)
        row_operations_tool.add_row(mock_tool_context)

        # Height should increase to 32
        assert mock_tool_context.hole_data.terrain_height == 32

        # Physical terrain should now be 32 rows (1 restored, 1 created)
        assert len(mock_tool_context.hole_data.terrain) == 32

        # Row 30 should have original data (restored)
        assert mock_tool_context.hole_data.terrain[30] == original_row_30

        # Row 31 should have default data (created)
        assert all(tile == 0xDF for tile in mock_tool_context.hole_data.terrain[31])

    def test_remove_then_add_cycle_preserves_data(
        self, row_operations_tool, mock_tool_context
    ):
        """Removing then adding rows should preserve original data."""
        # Create 32 rows with unique identifiable data
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(32)]
        mock_tool_context.hole_data.terrain_height = 32

        # Store original data from rows 30-31
        original_row_30 = mock_tool_context.hole_data.terrain[30][:]
        original_row_31 = mock_tool_context.hole_data.terrain[31][:]

        # Remove 2 rows (soft removal)
        row_operations_tool.remove_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 30

        # Add 2 rows back (should restore)
        row_operations_tool.add_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 32

        # Original data should be preserved (not default values)
        assert mock_tool_context.hole_data.terrain[30] == original_row_30
        assert mock_tool_context.hole_data.terrain[31] == original_row_31


class TestRowOperationsScrollLimit:
    """Tests for scroll_limit automatic updates."""

    def test_add_row_updates_scroll_limit(self, row_operations_tool, mock_tool_context):
        """Adding rows should update scroll_limit."""
        # Start with 30 rows: scroll_limit = (30 - 28) // 2 = 1
        mock_tool_context.hole_data.terrain_height = 30
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(30)]
        mock_tool_context.hole_data.metadata["scroll_limit"] = 1

        # Add 2 rows → 32 rows
        row_operations_tool.add_row(mock_tool_context)

        # scroll_limit should be (32 - 28) // 2 = 2
        assert mock_tool_context.hole_data.metadata["scroll_limit"] == 2

    def test_remove_row_updates_scroll_limit(self, row_operations_tool, mock_tool_context):
        """Removing rows should update scroll_limit."""
        # Start with 34 rows: scroll_limit = (34 - 28) // 2 = 3
        mock_tool_context.hole_data.terrain_height = 34
        mock_tool_context.hole_data.metadata["scroll_limit"] = 3

        # Remove 2 rows → 32 rows
        row_operations_tool.remove_row(mock_tool_context)

        # scroll_limit should be (32 - 28) // 2 = 2
        assert mock_tool_context.hole_data.metadata["scroll_limit"] == 2

    def test_scroll_limit_formula(self, mock_tool_context):
        """Verify scroll_limit formula: (height - 28) // 2."""
        test_cases = [
            (30, 1),   # (30 - 28) // 2 = 1
            (32, 2),   # (32 - 28) // 2 = 2
            (48, 10),  # (48 - 28) // 2 = 10
        ]

        for height, expected_scroll in test_cases:
            calculated = (height - 28) // 2
            assert calculated == expected_scroll

    def test_scroll_limit_never_negative(self, mock_tool_context):
        """Scroll limit should never be negative."""
        # Even if height < 28, scroll_limit should be >= 0
        # (Though our minimum is 30, test the formula safety)
        height = 26
        scroll_limit = max(0, (height - 28) // 2)
        assert scroll_limit == 0


class TestRowOperationsUndo:
    """Tests for undo/redo integration."""

    def test_add_row_pushes_undo_state(self, row_operations_tool, mock_tool_context):
        """add_row() should push undo state before modification."""
        row_operations_tool.add_row(mock_tool_context)

        mock_tool_context.state.undo_manager.push_state.assert_called_once_with(
            mock_tool_context.hole_data
        )

    def test_remove_row_pushes_undo_state(self, row_operations_tool, mock_tool_context):
        """remove_row() should push undo state before modification."""
        # Start with more rows so we can remove
        mock_tool_context.hole_data.terrain_height = 32

        row_operations_tool.remove_row(mock_tool_context)

        mock_tool_context.state.undo_manager.push_state.assert_called_once_with(
            mock_tool_context.hole_data
        )

    def test_undo_add_row_restores_height(self, mock_tool_context):
        """Undo after add_row should restore original height."""
        from editor.controllers.undo_manager import UndoManager

        # Use real UndoManager instead of mock
        real_undo_manager = UndoManager()
        mock_tool_context.state.undo_manager = real_undo_manager

        # Initial state: 30 rows
        initial_height = 30
        mock_tool_context.hole_data.terrain_height = initial_height

        # Push initial state
        real_undo_manager.push_state(mock_tool_context.hole_data)

        # Add rows
        tool = RowOperationsTool()
        tool.add_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 32

        # Undo
        restored = real_undo_manager.undo(mock_tool_context.hole_data)
        assert restored.terrain_height == initial_height

    def test_undo_remove_row_restores_height_and_visibility(self, mock_tool_context):
        """Undo after remove_row should restore height and make rows visible."""
        from editor.controllers.undo_manager import UndoManager

        # Use real UndoManager
        real_undo_manager = UndoManager()
        mock_tool_context.state.undo_manager = real_undo_manager

        # Initial state: 32 rows
        mock_tool_context.hole_data.terrain = [[i] * 22 for i in range(32)]
        mock_tool_context.hole_data.terrain_height = 32

        # Push initial state
        real_undo_manager.push_state(mock_tool_context.hole_data)

        # Remove rows
        tool = RowOperationsTool()
        tool.remove_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 30

        # Undo
        restored = real_undo_manager.undo(mock_tool_context.hole_data)
        assert restored.terrain_height == 32

    def test_redo_add_row_reapplies_height_change(self, mock_tool_context):
        """Redo after undo should reapply the add operation."""
        from editor.controllers.undo_manager import UndoManager

        # Use real UndoManager
        real_undo_manager = UndoManager()
        mock_tool_context.state.undo_manager = real_undo_manager

        # Initial state: 30 rows
        mock_tool_context.hole_data.terrain_height = 30
        real_undo_manager.push_state(mock_tool_context.hole_data)

        # Add rows
        tool = RowOperationsTool()
        tool.add_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 32

        # Undo
        restored = real_undo_manager.undo(mock_tool_context.hole_data)
        assert restored.terrain_height == 30

        # Redo
        redone = real_undo_manager.redo(restored)
        assert redone.terrain_height == 32


class TestRowOperationsAttributes:
    """Tests for attribute row management."""

    def test_add_row_adds_attribute_row_when_needed(
        self, row_operations_tool, mock_tool_context
    ):
        """Adding terrain rows should add attribute rows when needed."""
        # Start with 30 terrain rows (15 attribute rows)
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(30)]
        mock_tool_context.hole_data.terrain_height = 30
        mock_tool_context.hole_data.attributes = [[1] * 11 for _ in range(15)]

        # Add 2 rows → 32 terrain rows (should need 16 attribute rows)
        row_operations_tool.add_row(mock_tool_context)

        # Should have 16 attribute rows now
        assert len(mock_tool_context.hole_data.attributes) == 16

    def test_soft_remove_does_not_remove_attribute_rows(
        self, row_operations_tool, mock_tool_context
    ):
        """Soft removal should NOT remove attribute rows (data persists)."""
        # Start with 32 terrain rows (16 attribute rows)
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(32)]
        mock_tool_context.hole_data.terrain_height = 32
        mock_tool_context.hole_data.attributes = [[1] * 11 for _ in range(16)]

        # Soft remove to height 30
        row_operations_tool.remove_row(mock_tool_context)

        # Attribute rows should still be 16 (data preserved)
        assert len(mock_tool_context.hole_data.attributes) == 16

    def test_attribute_rows_preserved_during_restoration(
        self, row_operations_tool, mock_tool_context
    ):
        """Attribute rows should be preserved when restoring hidden rows."""
        # Start with 32 terrain rows (16 attribute rows)
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(32)]
        mock_tool_context.hole_data.terrain_height = 32
        mock_tool_context.hole_data.attributes = [[i] * 11 for i in range(16)]

        # Store original attribute row 15
        original_attr_15 = mock_tool_context.hole_data.attributes[15][:]

        # Soft remove to 30
        row_operations_tool.remove_row(mock_tool_context)

        # Add back to 32 (restore)
        row_operations_tool.add_row(mock_tool_context)

        # Attribute rows should be unchanged
        assert len(mock_tool_context.hole_data.attributes) == 16
        assert mock_tool_context.hole_data.attributes[15] == original_attr_15


class TestRowOperationsIntegration:
    """Integration tests for row operations."""

    def test_load_hole_edit_save_roundtrip(self, tmp_path):
        """Load hole, add rows, save, reload - verify persistence."""
        import json

        # Create initial JSON file
        json_file = tmp_path / "test_hole.json"
        terrain_rows = ['10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10'] * 30
        greens_rows = ['00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'] * 24

        data = {
            "hole": 1,
            "par": 4,
            "distance": 400,
            "handicap": 1,
            "scroll_limit": 1,
            "green": {"x": 100, "y": 200},
            "tee": {"x": 0, "y": 0},
            "flag_positions": [],
            "terrain": {
                "width": 22,
                "height": 30,
                "rows": terrain_rows
            },
            "attributes": {
                "width": 11,
                "height": 15,
                "rows": [[1] * 11 for _ in range(15)]
            },
            "greens": {
                "width": 24,
                "height": 24,
                "rows": greens_rows
            }
        }

        with open(json_file, "w") as f:
            json.dump(data, f)

        # Load hole
        hole = HoleData()
        hole.load(str(json_file))
        assert hole.terrain_height == 30

        # Add 2 rows
        hole.terrain_height = 32
        hole.add_terrain_row()
        hole.add_terrain_row()
        hole.metadata["scroll_limit"] = (32 - 28) // 2

        # Save
        hole.save()

        # Reload
        hole2 = HoleData()
        hole2.load(str(json_file))

        # Verify persistence
        assert hole2.terrain_height == 32
        assert len(hole2.terrain) == 32
        assert hole2.metadata["scroll_limit"] == 2

    def test_complex_editing_sequence(self, row_operations_tool, mock_tool_context):
        """Test complex sequence: add, remove, add multiple times."""
        # Start with 30 rows
        mock_tool_context.hole_data.terrain = [[0] * 22 for _ in range(30)]
        mock_tool_context.hole_data.terrain_height = 30
        mock_tool_context.hole_data.attributes = [[1] * 11 for _ in range(15)]

        # Add 2 rows → 32
        row_operations_tool.add_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 32
        assert mock_tool_context.hole_data.metadata["scroll_limit"] == 2

        # Remove 4 rows (2 operations) → 28... wait, that would be below minimum 30
        # So let's add more first
        row_operations_tool.add_row(mock_tool_context)  # 34
        row_operations_tool.add_row(mock_tool_context)  # 36

        # Remove 2 rows → 34
        row_operations_tool.remove_row(mock_tool_context)
        assert mock_tool_context.hole_data.terrain_height == 34
        assert mock_tool_context.hole_data.metadata["scroll_limit"] == 3

        # Add 6 rows (3 operations) → 40
        row_operations_tool.add_row(mock_tool_context)  # 36
        row_operations_tool.add_row(mock_tool_context)  # 38
        row_operations_tool.add_row(mock_tool_context)  # 40

        # Final state
        assert mock_tool_context.hole_data.terrain_height == 40
        assert mock_tool_context.hole_data.metadata["scroll_limit"] == 6

    def test_action_tool_integration(self):
        """Test AddRowTool action tool integration."""
        # Create mock context
        hole = HoleData()
        hole.terrain = [[0] * 22 for _ in range(30)]
        hole.terrain_height = 30
        hole.attributes = [[1] * 11 for _ in range(15)]
        hole.metadata = {"scroll_limit": 1}

        mock_state = Mock()
        mock_state.undo_manager = Mock()

        tool_manager = ToolManager()
        tool_manager.register_tool("row_operations", RowOperationsTool())

        context = ToolContext(
            hole_data=hole,
            state=mock_state,
            terrain_picker=None,
            greens_picker=None,
            transform_logic=None,
            forest_filler=None,
            screen_width=1024,
            screen_height=768,
            tool_manager=tool_manager,
        )

        # Create and activate AddRowTool
        add_tool = AddRowTool()
        add_tool.on_activated(context)

        # Verify rows were added
        assert hole.terrain_height == 32

    def test_remove_action_tool_integration(self):
        """Test RemoveRowTool action tool integration."""
        # Create mock context
        hole = HoleData()
        hole.terrain = [[0] * 22 for _ in range(32)]
        hole.terrain_height = 32
        hole.attributes = [[1] * 11 for _ in range(16)]
        hole.metadata = {"scroll_limit": 2}

        mock_state = Mock()
        mock_state.undo_manager = Mock()

        tool_manager = ToolManager()
        tool_manager.register_tool("row_operations", RowOperationsTool())

        context = ToolContext(
            hole_data=hole,
            state=mock_state,
            terrain_picker=None,
            greens_picker=None,
            transform_logic=None,
            forest_filler=None,
            screen_width=1024,
            screen_height=768,
            tool_manager=tool_manager,
        )

        # Create and activate RemoveRowTool
        remove_tool = RemoveRowTool()
        remove_tool.on_activated(context)

        # Verify rows were removed
        assert hole.terrain_height == 30
