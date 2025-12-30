"""
NES Open Tournament Golf - Undo Manager

Manages undo/redo history for hole data modifications.
"""
from typing import Optional
import copy

from golf.formats.hole_data import HoleData


class UndoManager:
    """Manages undo/redo stacks for hole data modifications."""

    def __init__(self, max_undo_levels: int = 50):
        """
        Initialize undo manager.

        Args:
            max_undo_levels: Maximum number of undo levels to keep (default: 50)
        """
        self.undo_stack: list[HoleData] = []
        self.redo_stack: list[HoleData] = []
        self.max_undo_levels = max_undo_levels
        self._current_data: Optional[HoleData] = None

    def set_initial_state(self, hole_data: HoleData):
        """Set the initial state (called when loading a file)."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._current_data = hole_data

    def push_state(self, hole_data: HoleData):
        """
        Push current state onto undo stack before making changes.
        Clears redo stack when new action is taken.

        Args:
            hole_data: Current hole data to save
        """
        # Create deep copy of current state
        snapshot = self._create_snapshot(hole_data)
        self.undo_stack.append(snapshot)

        # Limit stack size
        if len(self.undo_stack) > self.max_undo_levels:
            self.undo_stack.pop(0)

        # Clear redo stack on new action
        self.redo_stack.clear()

        self._current_data = hole_data

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self.redo_stack) > 0

    def undo(self, current_data: HoleData) -> Optional[HoleData]:
        """
        Undo last action.

        Args:
            current_data: Current hole data to save to redo stack

        Returns:
            Previous state, or None if no undo available
        """
        if not self.can_undo():
            return None

        # Save current state to redo stack
        current_snapshot = self._create_snapshot(current_data)
        self.redo_stack.append(current_snapshot)

        # Pop previous state from undo stack
        previous_state = self.undo_stack.pop()
        return previous_state

    def redo(self, current_data: HoleData) -> Optional[HoleData]:
        """
        Redo last undone action.

        Args:
            current_data: Current hole data to save to undo stack

        Returns:
            Next state, or None if no redo available
        """
        if not self.can_redo():
            return None

        # Save current state to undo stack
        current_snapshot = self._create_snapshot(current_data)
        self.undo_stack.append(current_snapshot)

        # Pop next state from redo stack
        next_state = self.redo_stack.pop()
        return next_state

    def _create_snapshot(self, hole_data: HoleData) -> HoleData:
        """
        Create a deep copy snapshot of hole data.

        Args:
            hole_data: Hole data to snapshot

        Returns:
            Deep copy of hole data
        """
        snapshot = HoleData()
        snapshot.terrain = copy.deepcopy(hole_data.terrain)
        snapshot.attributes = copy.deepcopy(hole_data.attributes)
        snapshot.greens = copy.deepcopy(hole_data.greens)
        snapshot.green_x = hole_data.green_x
        snapshot.green_y = hole_data.green_y
        snapshot.metadata = copy.deepcopy(hole_data.metadata)
        snapshot.filepath = hole_data.filepath
        snapshot.modified = hole_data.modified
        return snapshot

    def clear(self):
        """Clear all undo/redo history."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._current_data = None
