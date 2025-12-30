"""Unit tests for UndoManager functionality."""

import pytest

from editor.controllers.undo_manager import UndoManager
from golf.formats.hole_data import HoleData


@pytest.fixture
def undo_manager():
    """Create a fresh UndoManager instance."""
    return UndoManager(max_undo_levels=10)


@pytest.fixture
def simple_hole_data():
    """Create simple hole data for testing."""
    hole = HoleData()
    hole.terrain = [[1, 2, 3] for _ in range(5)]
    hole.attributes = [[1, 2] for _ in range(3)]
    hole.greens = [[4, 5, 6] for _ in range(4)]
    hole.green_x = 100
    hole.green_y = 200
    hole.metadata = {"par": 4, "distance": 350}
    hole.filepath = "/test/hole.json"
    hole.modified = False
    return hole


class TestUndoManagerInitialization:
    """Tests for UndoManager initialization."""

    def test_initialize_with_default_max_levels(self):
        """UndoManager should initialize with default max levels."""
        manager = UndoManager()
        assert manager.max_undo_levels == 50
        assert manager.can_undo() is False
        assert manager.can_redo() is False

    def test_initialize_with_custom_max_levels(self):
        """UndoManager should accept custom max undo levels."""
        manager = UndoManager(max_undo_levels=25)
        assert manager.max_undo_levels == 25

    def test_stacks_start_empty(self, undo_manager):
        """Undo and redo stacks should start empty."""
        assert len(undo_manager.undo_stack) == 0
        assert len(undo_manager.redo_stack) == 0


class TestPushState:
    """Tests for pushing states to undo stack."""

    def test_push_state_creates_snapshot(self, undo_manager, simple_hole_data):
        """push_state should create a snapshot."""
        undo_manager.push_state(simple_hole_data)
        assert undo_manager.can_undo()
        assert len(undo_manager.undo_stack) == 1

    def test_push_state_clears_redo_stack(self, undo_manager, simple_hole_data):
        """push_state should clear redo stack."""
        undo_manager.push_state(simple_hole_data)

        # Undo to populate redo stack
        simple_hole_data.terrain[0][0] = 99
        undo_manager.undo(simple_hole_data)
        assert undo_manager.can_redo()

        # Push new state should clear redo stack
        simple_hole_data.terrain[0][0] = 77
        undo_manager.push_state(simple_hole_data)
        assert undo_manager.can_redo() is False

    def test_push_state_respects_max_levels(self, undo_manager, simple_hole_data):
        """push_state should limit undo stack to max_undo_levels."""
        # Create manager with max 3 levels
        manager = UndoManager(max_undo_levels=3)

        # Push 5 states
        for i in range(5):
            simple_hole_data.terrain[0][0] = i
            manager.push_state(simple_hole_data)

        # Should only keep 3 most recent states
        assert len(manager.undo_stack) == 3

    def test_push_snapshot_is_deep_copy(self, undo_manager, simple_hole_data):
        """Snapshots should be independent deep copies."""
        undo_manager.push_state(simple_hole_data)

        # Modify original after pushing
        simple_hole_data.terrain[0][0] = 999
        simple_hole_data.green_x = 500
        simple_hole_data.metadata["par"] = 5

        # Snapshot should be unchanged
        snapshot = undo_manager.undo_stack[0]
        assert snapshot.terrain[0][0] == 1
        assert snapshot.green_x == 100
        assert snapshot.metadata["par"] == 4


class TestUndo:
    """Tests for undo functionality."""

    def test_undo_returns_previous_state(self, undo_manager, simple_hole_data):
        """undo should return the previous state."""
        undo_manager.push_state(simple_hole_data)

        # Modify hole data
        simple_hole_data.terrain[0][0] = 99

        # Undo should return original
        restored = undo_manager.undo(simple_hole_data)
        assert restored is not None
        assert restored.terrain[0][0] == 1

    def test_undo_saves_current_to_redo_stack(self, undo_manager, simple_hole_data):
        """undo should save current state to redo stack."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.terrain[0][0] = 99
        undo_manager.undo(simple_hole_data)

        assert undo_manager.can_redo()
        assert len(undo_manager.redo_stack) == 1

    def test_undo_returns_none_when_empty(self, undo_manager, simple_hole_data):
        """undo should return None when stack is empty."""
        result = undo_manager.undo(simple_hole_data)
        assert result is None

    def test_can_undo_reflects_stack_state(self, undo_manager, simple_hole_data):
        """can_undo should accurately reflect stack state."""
        assert undo_manager.can_undo() is False

        undo_manager.push_state(simple_hole_data)
        assert undo_manager.can_undo() is True

        simple_hole_data.terrain[0][0] = 99
        undo_manager.undo(simple_hole_data)
        assert undo_manager.can_undo() is False

    def test_multiple_undos(self, undo_manager, simple_hole_data):
        """Should be able to undo multiple actions in sequence."""
        # Push 3 states
        undo_manager.push_state(simple_hole_data)
        undo_manager.push_state(simple_hole_data)
        undo_manager.push_state(simple_hole_data)

        # Should have 3 undo levels
        assert len(undo_manager.undo_stack) == 3

        # Undo 3 times
        state1 = undo_manager.undo(simple_hole_data)
        assert state1 is not None
        assert len(undo_manager.undo_stack) == 2

        state2 = undo_manager.undo(state1)
        assert state2 is not None
        assert len(undo_manager.undo_stack) == 1

        state3 = undo_manager.undo(state2)
        assert state3 is not None
        assert len(undo_manager.undo_stack) == 0  # Stack now empty

        # Fourth undo should return None
        state4 = undo_manager.undo(state3)
        assert state4 is None


class TestRedo:
    """Tests for redo functionality."""

    def test_redo_returns_next_state(self, undo_manager, simple_hole_data):
        """redo should return the next state from redo stack."""
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 99

        undo_manager.undo(simple_hole_data)

        # Redo should return the modified state
        redone = undo_manager.redo(simple_hole_data)
        assert redone is not None
        assert redone.terrain[0][0] == 99

    def test_redo_saves_current_to_undo_stack(self, undo_manager, simple_hole_data):
        """redo should save current state to undo stack."""
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 99

        undo_manager.undo(simple_hole_data)
        undo_manager.redo(simple_hole_data)

        assert undo_manager.can_undo()
        # After push, undo, redo: undo_stack should have the redo'ed state
        assert len(undo_manager.undo_stack) >= 1

    def test_redo_returns_none_when_empty(self, undo_manager, simple_hole_data):
        """redo should return None when redo stack is empty."""
        result = undo_manager.redo(simple_hole_data)
        assert result is None

    def test_can_redo_reflects_stack_state(self, undo_manager, simple_hole_data):
        """can_redo should accurately reflect stack state."""
        assert undo_manager.can_redo() is False

        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 99
        assert undo_manager.can_redo() is False

        undo_manager.undo(simple_hole_data)
        assert undo_manager.can_redo() is True

    def test_multiple_redos(self, undo_manager, simple_hole_data):
        """Should be able to redo multiple actions in sequence."""
        # Build up undo stack
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 1
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][1] = 2

        # Undo twice
        state1 = undo_manager.undo(simple_hole_data)
        state2 = undo_manager.undo(state1)

        # Redo twice
        redo1 = undo_manager.redo(state2)
        redo2 = undo_manager.redo(redo1)

        assert redo1 is not None
        assert redo2 is not None


class TestSetInitialState:
    """Tests for clearing undo/redo on file load."""

    def test_set_initial_state_clears_stacks(self, undo_manager, simple_hole_data):
        """set_initial_state should clear both stacks."""
        # Build up stacks with multiple push/undo operations
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 99
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.terrain[0][1] = 88
        restored = undo_manager.undo(simple_hole_data)

        assert undo_manager.can_undo()
        assert undo_manager.can_redo()

        # Reset
        new_hole = HoleData()
        undo_manager.set_initial_state(new_hole)

        assert undo_manager.can_undo() is False
        assert undo_manager.can_redo() is False

    def test_set_initial_state_stores_reference(self, undo_manager, simple_hole_data):
        """set_initial_state should store reference to hole data."""
        undo_manager.set_initial_state(simple_hole_data)
        assert undo_manager._current_data is simple_hole_data


class TestClear:
    """Tests for clearing all history."""

    def test_clear_empties_both_stacks(self, undo_manager, simple_hole_data):
        """clear should empty both undo and redo stacks."""
        # Build up stacks with multiple operations
        undo_manager.push_state(simple_hole_data)
        simple_hole_data.terrain[0][0] = 99
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.terrain[0][1] = 88
        undo_manager.undo(simple_hole_data)

        assert undo_manager.can_undo()
        assert undo_manager.can_redo()

        # Clear
        undo_manager.clear()

        assert len(undo_manager.undo_stack) == 0
        assert len(undo_manager.redo_stack) == 0
        assert undo_manager.can_undo() is False
        assert undo_manager.can_redo() is False


class TestSnapshotPreservation:
    """Tests for verifying snapshot data preservation."""

    def test_terrain_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Terrain data should be fully preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.terrain = [[99] * 3 for _ in range(5)]
        restored = undo_manager.undo(simple_hole_data)

        assert restored.terrain == [[1, 2, 3] for _ in range(5)]

    def test_attributes_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Attributes should be fully preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.attributes = [[99] * 2 for _ in range(3)]
        restored = undo_manager.undo(simple_hole_data)

        assert restored.attributes == [[1, 2] for _ in range(3)]

    def test_greens_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Greens data should be fully preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.greens = [[99] * 3 for _ in range(4)]
        restored = undo_manager.undo(simple_hole_data)

        assert restored.greens == [[4, 5, 6] for _ in range(4)]

    def test_coordinates_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Green coordinates should be preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.green_x = 999
        simple_hole_data.green_y = 888
        restored = undo_manager.undo(simple_hole_data)

        assert restored.green_x == 100
        assert restored.green_y == 200

    def test_metadata_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Metadata should be fully preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.metadata = {"par": 5, "distance": 400, "other": "data"}
        restored = undo_manager.undo(simple_hole_data)

        assert restored.metadata == {"par": 4, "distance": 350}

    def test_filepath_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Filepath should be preserved in snapshots."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.filepath = "/different/path.json"
        restored = undo_manager.undo(simple_hole_data)

        assert restored.filepath == "/test/hole.json"

    def test_modified_flag_preserved_in_snapshot(self, undo_manager, simple_hole_data):
        """Modified flag should be preserved in snapshots."""
        simple_hole_data.modified = True
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.modified = False
        restored = undo_manager.undo(simple_hole_data)

        assert restored.modified is True


class TestUndoRedoSequences:
    """Tests for complex undo/redo sequences."""

    def test_undo_redo_undo_sequence(self, undo_manager, simple_hole_data):
        """Should handle undo->redo->undo sequences correctly."""
        # Build up undo stack
        undo_manager.push_state(simple_hole_data)
        undo_manager.push_state(simple_hole_data)

        # Undo
        state1 = undo_manager.undo(simple_hole_data)
        assert state1 is not None
        assert undo_manager.can_redo()

        # Redo
        state2 = undo_manager.redo(state1)
        assert state2 is not None

        # Undo again
        state3 = undo_manager.undo(state2)
        assert state3 is not None

    def test_new_action_after_undo_clears_redo(self, undo_manager, simple_hole_data):
        """New push_state after undo should clear redo stack."""
        undo_manager.push_state(simple_hole_data)

        simple_hole_data.terrain[0][0] = 99
        undo_manager.undo(simple_hole_data)
        assert undo_manager.can_redo()

        # New push should clear redo
        simple_hole_data.terrain[0][1] = 88
        undo_manager.push_state(simple_hole_data)
        assert undo_manager.can_redo() is False

    def test_alternating_undo_redo(self, undo_manager, simple_hole_data):
        """Should handle alternating undo/redo operations."""
        # Build up undo/redo states
        undo_manager.push_state(simple_hole_data)
        undo_manager.push_state(simple_hole_data)

        # Undo
        s1 = undo_manager.undo(simple_hole_data)
        assert s1 is not None
        assert undo_manager.can_redo()

        # Redo
        s2 = undo_manager.redo(s1)
        assert s2 is not None

        # Undo again
        s3 = undo_manager.undo(s2)
        assert s3 is not None
        assert undo_manager.can_redo()

        # Redo again
        s4 = undo_manager.redo(s3)
        assert s4 is not None
