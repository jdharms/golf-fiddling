"""Unit tests for EventHandler keyboard shortcut handling."""

import pytest
from unittest.mock import Mock, MagicMock, patch

import pygame

from editor.controllers.event_handler import EventHandler
from editor.controllers.editor_state import EditorState
from editor.tools.tool_manager import ToolManager
from editor.tools.paint_tool import PaintTool
from editor.tools.forest_fill_tool import ForestFillTool
from editor.tools.base_tool import ToolResult
from golf.formats.hole_data import HoleData


@pytest.fixture
def mock_pygame():
    """Initialize pygame for tests."""
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def editor_state():
    """Create a fresh EditorState instance."""
    return EditorState()


@pytest.fixture
def hole_data():
    """Create simple hole data for testing."""
    hole = HoleData()
    hole.terrain = [[0x10, 0x11, 0x12] for _ in range(5)]
    hole.attributes = [[1, 1] for _ in range(3)]
    hole.greens = [[0x20, 0x21, 0x22] for _ in range(4)]
    return hole


@pytest.fixture
def tool_manager():
    """Create ToolManager with registered tools."""
    manager = ToolManager()
    manager.register_tool("paint", PaintTool())
    manager.register_tool("forest_fill", ForestFillTool())
    return manager


@pytest.fixture
def event_handler(editor_state, hole_data, tool_manager):
    """Create EventHandler with minimal setup."""
    # Create mock pickers
    mock_terrain_picker = Mock()
    mock_greens_picker = Mock()

    # Create mock callbacks
    mock_on_load = Mock()
    mock_on_save = Mock()
    mock_on_mode_change = Mock()
    mock_on_flag_change = Mock()
    mock_on_resize = Mock()
    mock_on_terrain_modified = Mock()

    handler = EventHandler(
        state=editor_state,
        hole_data=hole_data,
        terrain_picker=mock_terrain_picker,
        greens_picker=mock_greens_picker,
        buttons=[],
        screen_width=1200,
        screen_height=1200,
        tool_manager=tool_manager,
        on_load=mock_on_load,
        on_save=mock_on_save,
        on_mode_change=mock_on_mode_change,
        on_flag_change=mock_on_flag_change,
        on_resize=mock_on_resize,
        on_terrain_modified=mock_on_terrain_modified,
    )

    # Set tool context properties (normally done by Application)
    handler.tool_context.transform_logic = None

    # Mock forest filler with proper return values
    mock_filler = Mock()
    mock_filler.detect_regions.return_value = []  # Default: no regions
    mock_filler.fill_region.return_value = {}  # Default: no changes
    handler.tool_context.forest_filler = mock_filler

    # Activate paint tool
    tool_manager.set_active_tool("paint", handler.tool_context)

    return handler


class MockEvent:
    """Mock pygame event."""

    def __init__(self, type, **kwargs):
        self.type = type
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestForestFillShortcut:
    """Regression tests for Ctrl+F forest fill shortcut."""

    def test_ctrl_f_triggers_forest_fill(
        self, mock_pygame, event_handler, tool_manager
    ):
        """Ctrl+F should trigger the forest fill tool."""
        # Create Ctrl+F event
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        # Mock pygame.key.get_mods to return Ctrl
        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            # Spy on the forest fill tool
            forest_fill_tool = tool_manager.get_tool("forest_fill")
            original_handle_key_down = forest_fill_tool.handle_key_down

            call_count = 0

            def tracked_handle_key_down(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return original_handle_key_down(*args, **kwargs)

            forest_fill_tool.handle_key_down = tracked_handle_key_down

            # Handle the event
            running = event_handler.handle_events([event])

            # Verify forest fill was triggered
            assert call_count == 1, "Forest fill tool should be called once"
            assert running is True, "Event handler should continue running"

    def test_ctrl_f_works_in_terrain_mode(self, mock_pygame, event_handler):
        """Ctrl+F should work in terrain mode."""
        event_handler.state.set_mode("terrain")
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            running = event_handler.handle_events([event])
            assert running is True

    def test_ctrl_f_in_palette_mode_shows_message(self, mock_pygame, event_handler):
        """Ctrl+F in palette mode should show 'only available in terrain mode' message."""
        event_handler.state.set_mode("palette")
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            # Capture print output
            with patch("builtins.print") as mock_print:
                event_handler.handle_events([event])

                # Should have printed message about terrain mode
                assert mock_print.called
                call_args = str(mock_print.call_args)
                assert "terrain mode" in call_args.lower()

    def test_ctrl_f_in_greens_mode_shows_message(self, mock_pygame, event_handler):
        """Ctrl+F in greens mode should show 'only available in terrain mode' message."""
        event_handler.state.set_mode("greens")
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            with patch("builtins.print") as mock_print:
                event_handler.handle_events([event])
                assert mock_print.called
                call_args = str(mock_print.call_args)
                assert "terrain mode" in call_args.lower()

    def test_f_without_ctrl_not_handled_globally(self, mock_pygame, event_handler):
        """F key without Ctrl should not be handled by global handler."""
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        # Mock get_mods to return no modifiers
        with patch("pygame.key.get_mods", return_value=0):
            # Spy on the active tool's handle_key_down
            active_tool = event_handler.tool_manager.get_active_tool()
            call_count = 0
            original = active_tool.handle_key_down

            def tracked(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return original(*args, **kwargs)

            active_tool.handle_key_down = tracked

            event_handler.handle_events([event])

            # Active tool should receive the unhandled key
            assert call_count == 1, "Active tool should receive unhandled F key"

    def test_ctrl_f_calls_on_terrain_modified(self, mock_pygame, event_handler):
        """Ctrl+F should trigger on_terrain_modified callback when terrain is modified."""
        # Set up forest filler to return changes
        mock_filler = event_handler.tool_context.forest_filler
        mock_filler.detect_regions.return_value = [[(0, 0), (0, 1)]]  # Mock region
        mock_filler.fill_region.return_value = {
            (0, 0): 0x50,
            (0, 1): 0x51,
        }  # Mock changes

        event_handler.state.set_mode("terrain")
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_f)

        # Track on_terrain_modified callback
        on_terrain_modified_called = False
        original_callback = event_handler.on_terrain_modified

        def tracked_callback():
            nonlocal on_terrain_modified_called
            on_terrain_modified_called = True
            if original_callback:
                original_callback()

        event_handler.on_terrain_modified = tracked_callback

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            event_handler.handle_events([event])

        # Callback should be triggered because terrain was modified
        assert on_terrain_modified_called, (
            "on_terrain_modified should be called when fill succeeds"
        )


class TestOtherGlobalShortcuts:
    """Tests for other global keyboard shortcuts to ensure they still work."""

    def test_ctrl_s_triggers_save(self, mock_pygame, event_handler):
        """Ctrl+S should trigger save callback."""
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_s)

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            event_handler.handle_events([event])
            event_handler.on_save.assert_called_once()

    def test_ctrl_z_triggers_undo(self, mock_pygame, event_handler, hole_data):
        """Ctrl+Z should trigger undo if available."""
        # Push a state to enable undo
        event_handler.state.undo_manager.push_state(hole_data)

        event = MockEvent(pygame.KEYDOWN, key=pygame.K_z)

        with patch("pygame.key.get_mods", return_value=pygame.KMOD_CTRL):
            assert event_handler.state.undo_manager.can_undo()
            event_handler.handle_events([event])
            # After undo, should not be able to undo again (only had 1 state)
            assert not event_handler.state.undo_manager.can_undo()

    def test_g_toggles_grid(self, mock_pygame, event_handler):
        """G key should toggle grid visibility."""
        initial_grid_state = event_handler.state.show_grid
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_g)

        with patch("pygame.key.get_mods", return_value=0):
            event_handler.handle_events([event])
            assert event_handler.state.show_grid == (not initial_grid_state)

    def test_v_toggles_sprites(self, mock_pygame, event_handler):
        """V key should toggle sprite visibility."""
        initial_sprite_state = event_handler.state.show_sprites
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_v)

        with patch("pygame.key.get_mods", return_value=0):
            event_handler.handle_events([event])
            assert event_handler.state.show_sprites == (not initial_sprite_state)


class TestEventHandlerDelegation:
    """Tests for event handler delegation to tools."""

    def test_active_tool_receives_unhandled_keys(self, mock_pygame, event_handler):
        """Active tool should receive keys not handled by global handler."""
        active_tool = event_handler.tool_manager.get_active_tool()

        # Mock the tool's handle_key_down to track calls
        original = active_tool.handle_key_down
        call_args = []

        def tracked(*args, **kwargs):
            call_args.append((args, kwargs))
            return original(*args, **kwargs)

        active_tool.handle_key_down = tracked

        # Send a key that's not handled globally (e.g., 'A')
        event = MockEvent(pygame.KEYDOWN, key=pygame.K_a)

        with patch("pygame.key.get_mods", return_value=0):
            event_handler.handle_events([event])

        # Tool should have received the key
        assert len(call_args) == 1, "Tool should receive unhandled key event"
        assert call_args[0][0][0] == pygame.K_a, "Tool should receive correct key"

    def test_quit_event_stops_application(self, mock_pygame, event_handler):
        """QUIT event should make handle_events return False."""
        event = MockEvent(pygame.QUIT)
        running = event_handler.handle_events([event])
        assert running is False, "QUIT event should return False to stop application"
