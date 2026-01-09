"""
Unit tests for PositionTool.

Tests cover:
- Position cycling (Tab, [, ])
- Mode restrictions (terrain vs greens)
- Flag synchronization in greens mode
- Mode change detection and correction
- Out of bounds handling
- Tool activation behavior
"""

import pygame
import pytest
from unittest.mock import Mock, MagicMock

from editor.tools.position_tool import PositionTool
from editor.tools.base_tool import ToolContext


@pytest.fixture
def mock_hole_data():
    """Create mock HoleData with metadata."""
    hole_data = Mock()
    hole_data.metadata = {
        "tee": {"x": 100, "y": 200},
        "flag_positions": [
            {"x_offset": 10, "y_offset": 20},
            {"x_offset": 30, "y_offset": 40},
            {"x_offset": 50, "y_offset": 60},
            {"x_offset": 70, "y_offset": 80},
        ]
    }
    hole_data.green_x = 300
    hole_data.green_y = 400
    hole_data.modified = False
    return hole_data


@pytest.fixture
def mock_state():
    """Create mock EditorState."""
    state = Mock()
    state.mode = "terrain"
    state.undo_manager = Mock()
    state.undo_manager.push_state = Mock()
    return state


@pytest.fixture
def mock_highlight_state():
    """Create mock HighlightState."""
    highlight = Mock()
    highlight.position_tool_selected = None
    return highlight


@pytest.fixture
def mock_context(mock_hole_data, mock_state, mock_highlight_state):
    """Create mock ToolContext."""
    context = Mock(spec=ToolContext)
    context.hole_data = mock_hole_data
    context.state = mock_state
    context.highlight_state = mock_highlight_state
    context.select_flag = Mock()  # Mock the callback
    return context


@pytest.fixture
def position_tool():
    """Create fresh PositionTool instance."""
    return PositionTool()


class TestPositionToolAvailablePositions:
    """Test _get_available_positions method."""

    def test_terrain_mode_returns_tee_and_green(self, position_tool):
        """Terrain mode should only allow tee and green positions."""
        positions = position_tool._get_available_positions("terrain")
        assert positions == ["tee", "green"]

    def test_greens_mode_returns_four_flags(self, position_tool):
        """Greens mode should allow all four flag positions."""
        positions = position_tool._get_available_positions("greens")
        assert positions == ["flag1", "flag2", "flag3", "flag4"]


class TestPositionToolCycling:
    """Test position cycling with Tab, [, and ] keys."""

    def test_tab_cycles_forward_in_terrain_mode(self, position_tool, mock_context):
        """Tab should cycle from tee to green to tee in terrain mode."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Start at position 0 (tee)
        assert position_tool.selected_position_index == 0

        # Tab to position 1 (green)
        result = position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "green"

        # Tab wraps to position 0 (tee)
        result = position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "tee"

    def test_tab_cycles_forward_in_greens_mode(self, position_tool, mock_context):
        """Tab should cycle through all four flags in greens mode."""
        mock_context.state.mode = "greens"
        position_tool.on_activated(mock_context)

        # Cycle through all flags
        expected_positions = ["flag1", "flag2", "flag3", "flag4", "flag1"]
        for i, expected in enumerate(expected_positions[1:], 1):
            result = position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
            assert result.handled
            assert position_tool.selected_position_index == i % 4
            assert mock_context.highlight_state.position_tool_selected == expected

    def test_left_bracket_cycles_backward(self, position_tool, mock_context):
        """[ should cycle backwards through positions."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Start at position 0 (tee)
        assert position_tool.selected_position_index == 0

        # [ wraps to position 1 (green)
        result = position_tool.handle_key_down(pygame.K_LEFTBRACKET, 0, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "green"

        # [ cycles to position 0 (tee)
        result = position_tool.handle_key_down(pygame.K_LEFTBRACKET, 0, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "tee"

    def test_shift_tab_cycles_backward(self, position_tool, mock_context):
        """Shift+Tab should cycle backwards like [."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Shift+Tab wraps backward
        result = position_tool.handle_key_down(pygame.K_TAB, pygame.KMOD_SHIFT, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "green"

    def test_right_bracket_cycles_forward(self, position_tool, mock_context):
        """] should cycle forward like Tab."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # ] cycles forward
        result = position_tool.handle_key_down(pygame.K_RIGHTBRACKET, 0, mock_context)
        assert result.handled
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "green"


class TestPositionToolFlagSync:
    """Test flag synchronization when cycling in greens mode."""

    def test_tab_syncs_flag_in_greens_mode(self, position_tool, mock_context):
        """Tab in greens mode should sync visible flag via callback."""
        mock_context.state.mode = "greens"
        position_tool.on_activated(mock_context)

        # Initial activation should sync to flag1 (index 0)
        mock_context.select_flag.assert_called_with(0)
        mock_context.select_flag.reset_mock()

        # Tab to flag2
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        mock_context.select_flag.assert_called_once_with(1)

        # Tab to flag3
        mock_context.select_flag.reset_mock()
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        mock_context.select_flag.assert_called_once_with(2)

    def test_left_bracket_syncs_flag_in_greens_mode(self, position_tool, mock_context):
        """[ in greens mode should sync visible flag."""
        mock_context.state.mode = "greens"
        position_tool.on_activated(mock_context)
        mock_context.select_flag.reset_mock()

        # [ backward to flag4
        position_tool.handle_key_down(pygame.K_LEFTBRACKET, 0, mock_context)
        mock_context.select_flag.assert_called_once_with(3)

    def test_right_bracket_syncs_flag_in_greens_mode(self, position_tool, mock_context):
        """] in greens mode should sync visible flag."""
        mock_context.state.mode = "greens"
        position_tool.on_activated(mock_context)
        mock_context.select_flag.reset_mock()

        # ] forward to flag2
        position_tool.handle_key_down(pygame.K_RIGHTBRACKET, 0, mock_context)
        mock_context.select_flag.assert_called_once_with(1)

    def test_no_flag_sync_in_terrain_mode(self, position_tool, mock_context):
        """Tab in terrain mode should NOT call select_flag."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)
        mock_context.select_flag.reset_mock()

        # Tab in terrain mode
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)

        # Should not call select_flag for tee/green positions
        mock_context.select_flag.assert_not_called()


class TestPositionToolModeChange:
    """Test mode change detection and position correction."""

    def test_mode_change_from_terrain_to_greens_valid_position(self, position_tool, mock_context):
        """Switching from terrain position 1 (green) to greens should sync flag."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Cycle to position 1 (green)
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        assert position_tool.selected_position_index == 1
        mock_context.select_flag.reset_mock()

        # Switch to greens mode
        mock_context.state.mode = "greens"

        # update() should detect mode change and sync flag
        result = position_tool.update(mock_context)

        # Position 1 is still valid in greens (flag2)
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "flag2"
        # Should sync to flag2 (index 1)
        mock_context.select_flag.assert_called_once_with(1)
        assert result.handled

    def test_mode_change_from_greens_to_terrain_out_of_bounds(self, position_tool, mock_context):
        """Switching from greens flag3 to terrain should reset to position 0."""
        mock_context.state.mode = "greens"
        position_tool.on_activated(mock_context)

        # Cycle to position 2 (flag3)
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)
        assert position_tool.selected_position_index == 2
        mock_context.select_flag.reset_mock()

        # Switch to terrain mode
        mock_context.state.mode = "terrain"

        # update() should detect mode change and reset position
        result = position_tool.update(mock_context)

        # Position 2 is out of bounds in terrain (only 0,1 valid)
        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "tee"
        assert result.handled

    def test_mode_change_from_terrain_to_greens_at_position_zero(self, position_tool, mock_context):
        """Switching from terrain tee to greens should sync to flag1."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # At position 0 (tee)
        assert position_tool.selected_position_index == 0
        mock_context.select_flag.reset_mock()

        # Switch to greens mode
        mock_context.state.mode = "greens"

        # update() should sync to flag1
        result = position_tool.update(mock_context)

        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "flag1"
        mock_context.select_flag.assert_called_once_with(0)

    def test_no_correction_when_mode_unchanged(self, position_tool, mock_context):
        """update() should return early if mode hasn't changed and position is valid."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)
        mock_context.select_flag.reset_mock()

        # Mode stays the same, position is valid
        result = position_tool.update(mock_context)

        # Should return not_handled (fast path)
        assert not result.handled
        mock_context.select_flag.assert_not_called()

    def test_mode_tracker_updated_after_correction(self, position_tool, mock_context):
        """last_validated_mode should be updated after mode change."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        assert position_tool.last_validated_mode == "terrain"

        # Switch mode
        mock_context.state.mode = "greens"
        position_tool.update(mock_context)

        assert position_tool.last_validated_mode == "greens"


class TestPositionToolActivation:
    """Test tool activation behavior."""

    def test_on_activated_resets_to_first_position(self, position_tool, mock_context):
        """Activating tool should reset to position 0."""
        mock_context.state.mode = "terrain"

        # Set to non-zero position
        position_tool.selected_position_index = 1

        position_tool.on_activated(mock_context)

        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "tee"

    def test_on_activated_syncs_flag_in_greens_mode(self, position_tool, mock_context):
        """Activating tool in greens mode should sync to flag1."""
        mock_context.state.mode = "greens"

        position_tool.on_activated(mock_context)

        assert position_tool.selected_position_index == 0
        assert mock_context.highlight_state.position_tool_selected == "flag1"
        mock_context.select_flag.assert_called_once_with(0)

    def test_on_activated_no_flag_sync_in_terrain_mode(self, position_tool, mock_context):
        """Activating tool in terrain mode should NOT sync flag."""
        mock_context.state.mode = "terrain"

        position_tool.on_activated(mock_context)

        mock_context.select_flag.assert_not_called()

    def test_on_activated_initializes_mode_tracker(self, position_tool, mock_context):
        """Activating tool should set last_validated_mode."""
        mock_context.state.mode = "greens"

        position_tool.on_activated(mock_context)

        assert position_tool.last_validated_mode == "greens"

    def test_on_activated_creates_missing_metadata(self, position_tool, mock_context):
        """Activating tool should ensure metadata exists."""
        # Remove metadata
        mock_context.hole_data.metadata = {}

        position_tool.on_activated(mock_context)

        # Should create tee position
        assert "tee" in mock_context.hole_data.metadata
        assert mock_context.hole_data.metadata["tee"] == {"x": 0, "y": 0}

        # Should create flag positions
        assert "flag_positions" in mock_context.hole_data.metadata
        assert len(mock_context.hole_data.metadata["flag_positions"]) == 4

    def test_on_deactivated_clears_highlight(self, position_tool, mock_context):
        """Deactivating tool should clear highlight state."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        position_tool.on_deactivated(mock_context)

        assert mock_context.highlight_state.position_tool_selected is None


class TestPositionToolReset:
    """Test reset() method."""

    def test_reset_clears_all_state(self, position_tool):
        """reset() should clear all tool state."""
        # Set some state
        position_tool.selected_position_index = 2
        position_tool.undo_position_tracker = "flag1"
        position_tool.last_validated_mode = "greens"
        position_tool.held_key = pygame.K_LEFT
        position_tool.key_held_since = 1.5
        position_tool.repeat_active = True

        position_tool.reset()

        assert position_tool.selected_position_index == 0
        assert position_tool.undo_position_tracker is None
        assert position_tool.last_validated_mode is None
        assert position_tool.held_key is None
        assert position_tool.key_held_since is None
        assert not position_tool.repeat_active


class TestPositionToolArrowKeys:
    """Test arrow key handling and position adjustment."""

    def test_arrow_key_adjusts_position(self, position_tool, mock_context):
        """Arrow keys should adjust position coordinates."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # At tee position initially
        initial_x = mock_context.hole_data.metadata["tee"]["x"]

        # Press right arrow
        result = position_tool.handle_key_down(pygame.K_RIGHT, 0, mock_context)

        assert result.needs_render
        assert mock_context.hole_data.metadata["tee"]["x"] == initial_x + 1
        assert mock_context.hole_data.modified

    def test_arrow_key_pushes_undo_once_per_position(self, position_tool, mock_context):
        """Arrow keys should push undo state once per position, not per keystroke."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # First arrow on tee
        position_tool.handle_key_down(pygame.K_RIGHT, 0, mock_context)
        assert mock_context.state.undo_manager.push_state.call_count == 1

        # Second arrow on same position - should not push again
        position_tool.handle_key_down(pygame.K_RIGHT, 0, mock_context)
        assert mock_context.state.undo_manager.push_state.call_count == 1

        # Cycle to green
        position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)

        # Arrow on green - should push new undo state
        position_tool.handle_key_down(pygame.K_RIGHT, 0, mock_context)
        assert mock_context.state.undo_manager.push_state.call_count == 2


class TestPositionToolHandleKeyDown:
    """Test handle_key_down validates position before processing."""

    def test_handle_key_down_validates_position(self, position_tool, mock_context):
        """handle_key_down should validate position as safety check."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Manually put position out of bounds (simulating race condition)
        position_tool.selected_position_index = 5
        position_tool.last_validated_mode = None  # Force validation

        # Tab key will validate (correct to 0) then cycle forward (to 1)
        result = position_tool.handle_key_down(pygame.K_TAB, 0, mock_context)

        # After validation and Tab, should be at position 1 (green)
        assert result.handled
        assert position_tool.selected_position_index == 1
        assert mock_context.highlight_state.position_tool_selected == "green"

    def test_handle_key_down_corrects_out_of_bounds_without_cycling(self, position_tool, mock_context):
        """Validation should correct out of bounds position even with arrow keys."""
        mock_context.state.mode = "terrain"
        position_tool.on_activated(mock_context)

        # Manually put position out of bounds
        position_tool.selected_position_index = 5
        position_tool.last_validated_mode = None  # Force validation

        # Arrow key will validate and correct, then adjust from position 0 (tee)
        initial_x = mock_context.hole_data.metadata["tee"]["x"]
        result = position_tool.handle_key_down(pygame.K_RIGHT, 0, mock_context)

        # Should have corrected to position 0 and moved tee right
        assert result.needs_render
        assert mock_context.hole_data.metadata["tee"]["x"] == initial_x + 1


class TestPositionToolGetHotkey:
    """Test hotkey configuration."""

    def test_get_hotkey_returns_r(self, position_tool):
        """Tool hotkey should be 'R' key."""
        assert position_tool.get_hotkey() == pygame.K_r
