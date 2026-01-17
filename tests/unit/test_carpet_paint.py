"""
Unit tests for CarpetPaintTool constraint logic.
"""

import pytest

from editor.tools.carpet_paint_tool import (
    PAINTABLE_TILES,
    PROTECTED_TILES,
    CarpetPaintTool,
)


# =============================================================================
# Tile Category Tests
# =============================================================================


class TestTileCategories:
    """Tests for tile category constants."""

    def test_placeholder_is_paintable(self):
        """Placeholder tile (0x100) should be paintable."""
        assert 0x100 in PAINTABLE_TILES

    def test_flat_is_paintable(self):
        """Flat tile (0xB0) should be paintable."""
        assert 0xB0 in PAINTABLE_TILES

    def test_dark_slopes_are_paintable(self):
        """Dark slope tiles (0x30-0x47) should be paintable."""
        for tile in range(0x30, 0x48):
            assert tile in PAINTABLE_TILES, f"Tile 0x{tile:02X} should be paintable"

    def test_light_slopes_are_paintable(self):
        """Light slope tiles (0x88-0xA7) should be paintable."""
        for tile in range(0x88, 0xA8):
            assert tile in PAINTABLE_TILES, f"Tile 0x{tile:02X} should be paintable"

    def test_fringe_lower_range_is_protected(self):
        """Fringe tiles (0x48-0x6F) should be protected."""
        for tile in range(0x48, 0x70):
            assert tile in PROTECTED_TILES, f"Tile 0x{tile:02X} should be protected"

    def test_fringe_upper_range_is_protected(self):
        """Fringe tiles (0x74-0x83) should be protected."""
        for tile in range(0x74, 0x84):
            assert tile in PROTECTED_TILES, f"Tile 0x{tile:02X} should be protected"

    def test_rough_base_tiles_are_protected(self):
        """Rough base tiles (0x29, 0x2C) should be protected."""
        assert 0x29 in PROTECTED_TILES
        assert 0x2C in PROTECTED_TILES

    def test_rough_edge_variants_are_protected(self):
        """Rough edge variants should be protected."""
        # Edge variants 0x70-0x73
        for tile in [0x70, 0x71, 0x72, 0x73]:
            assert tile in PROTECTED_TILES, f"Tile 0x{tile:02X} should be protected"
        # Edge variants 0x84-0x87
        for tile in [0x84, 0x85, 0x86, 0x87]:
            assert tile in PROTECTED_TILES, f"Tile 0x{tile:02X} should be protected"

    def test_no_overlap_between_paintable_and_protected(self):
        """Paintable and protected sets should have no overlap."""
        overlap = PAINTABLE_TILES & PROTECTED_TILES
        assert len(overlap) == 0, f"Found overlapping tiles: {[hex(t) for t in overlap]}"

    def test_paintable_tile_count(self):
        """Verify expected number of paintable tiles."""
        # 1 placeholder + 1 flat + 24 dark slopes + 32 light slopes = 58
        expected_count = 1 + 1 + (0x48 - 0x30) + (0xA8 - 0x88)
        assert len(PAINTABLE_TILES) == expected_count

    def test_protected_tile_count(self):
        """Verify expected number of protected tiles."""
        # (0x70 - 0x48) + (0x84 - 0x74) + 2 rough base + 8 edge variants = 40 + 16 + 2 + 8 = 66
        # Actually:
        # 0x48-0x6F = 0x70 - 0x48 = 40 tiles
        # 0x74-0x83 = 0x84 - 0x74 = 16 tiles
        # 0x29, 0x2C = 2 tiles
        # 0x70-0x73 = 4 tiles
        # 0x84-0x87 = 4 tiles
        # Total = 40 + 16 + 2 + 4 + 4 = 66
        expected_count = (0x70 - 0x48) + (0x84 - 0x74) + 2 + 4 + 4
        assert len(PROTECTED_TILES) == expected_count


# =============================================================================
# Tool Behavior Tests
# =============================================================================


class TestCarpetPaintTool:
    """Tests for CarpetPaintTool behavior."""

    @pytest.fixture
    def tool(self):
        return CarpetPaintTool()

    def test_hotkey_is_v(self, tool):
        """Carpet paint tool hotkey should be 'V'."""
        import pygame

        assert tool.get_hotkey() == pygame.K_v

    def test_reset_clears_state(self, tool):
        """Reset should clear painting state."""
        tool.is_painting = True
        tool.last_paint_pos = (5, 5)
        tool.undo_pushed = True

        tool.reset()

        assert tool.is_painting is False
        assert tool.last_paint_pos is None
        assert tool.undo_pushed is False

    def test_initial_state(self, tool):
        """Tool should start with clean state."""
        assert tool.is_painting is False
        assert tool.last_paint_pos is None
        assert tool.undo_pushed is False


# =============================================================================
# Tile Category Logic Tests
# =============================================================================


class TestTileCategoryLogic:
    """Tests for the paintability check logic."""

    def test_paintable_tiles_include_putting_surface(self):
        """Paintable tiles should include all putting surface tiles."""
        putting_surface_tiles = [
            0x100,  # Placeholder
            0xB0,   # Flat
            0x30,   # First dark slope
            0x47,   # Last dark slope
            0x88,   # First light slope
            0xA7,   # Last light slope
        ]
        for tile in putting_surface_tiles:
            assert tile in PAINTABLE_TILES, f"0x{tile:02X} should be paintable"

    def test_protected_tiles_include_boundary(self):
        """Protected tiles should include all boundary tiles."""
        boundary_tiles = [
            0x48,  # First fringe lower range
            0x6F,  # Last fringe lower range
            0x74,  # First fringe upper range
            0x83,  # Last fringe upper range
            0x29,  # Rough base 1
            0x2C,  # Rough base 2
            0x70,  # Rough edge
            0x87,  # Rough edge
        ]
        for tile in boundary_tiles:
            assert tile in PROTECTED_TILES, f"0x{tile:02X} should be protected"

    def test_known_fringe_tiles_protected(self):
        """Specific known fringe tiles should be protected."""
        known_fringe = [
            0x64,  # FRINGE_UP
            0x65,  # FRINGE_DOWN
            0x66,  # FRINGE_LEFT
            0x67,  # FRINGE_RIGHT
        ]
        for tile in known_fringe:
            assert tile in PROTECTED_TILES, f"Fringe tile 0x{tile:02X} should be protected"
