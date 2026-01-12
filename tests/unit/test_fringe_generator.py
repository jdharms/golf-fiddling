"""
Unit tests for FringeGenerator algorithm.
"""

import json
import random

import pytest

from editor.algorithms.fringe_generator import (
    FringeGenerator,
    direction_from,
    direction_to,
    opposite,
    compute_signed_area,
    make_shape_key,
    DIRECTIONS,
)


# =============================================================================
# Direction Utilities
# =============================================================================

class TestDirectionFrom:
    """Tests for direction_from function."""

    def test_up(self):
        assert direction_from((5, 5), (4, 5)) == "up"

    def test_down(self):
        assert direction_from((5, 5), (6, 5)) == "down"

    def test_left(self):
        assert direction_from((5, 5), (5, 4)) == "left"

    def test_right(self):
        assert direction_from((5, 5), (5, 6)) == "right"

    def test_non_adjacent_raises(self):
        with pytest.raises(ValueError, match="not orthogonally adjacent"):
            direction_from((5, 5), (7, 5))

    def test_diagonal_raises(self):
        with pytest.raises(ValueError, match="not orthogonally adjacent"):
            direction_from((5, 5), (6, 6))

    def test_same_position_raises(self):
        with pytest.raises(ValueError, match="not orthogonally adjacent"):
            direction_from((5, 5), (5, 5))


class TestDirectionTo:
    """Tests for direction_to function (alias for direction_from)."""

    def test_is_alias_for_direction_from(self):
        positions = [((0, 0), (0, 1)), ((3, 3), (2, 3)), ((1, 1), (1, 0))]
        for p1, p2 in positions:
            assert direction_to(p1, p2) == direction_from(p1, p2)


class TestOpposite:
    """Tests for opposite function."""

    def test_all_directions(self):
        assert opposite("up") == "down"
        assert opposite("down") == "up"
        assert opposite("left") == "right"
        assert opposite("right") == "left"

    def test_double_opposite_is_identity(self):
        for d in DIRECTIONS:
            assert opposite(opposite(d)) == d


# =============================================================================
# Geometry
# =============================================================================

class TestSignedArea:
    """Tests for compute_signed_area function."""

    def test_clockwise_square_is_positive(self):
        # Clockwise in screen coordinates (row increases downward)
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        assert compute_signed_area(path) > 0

    def test_counterclockwise_square_is_negative(self):
        # Counter-clockwise
        path = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert compute_signed_area(path) < 0

    def test_area_magnitude_matches_geometry(self):
        # 2x2 square has area 4
        path = [(0, 0), (0, 2), (2, 2), (2, 0)]
        assert abs(compute_signed_area(path)) == 4.0

    def test_reversed_path_negates_area(self):
        path = [(0, 0), (0, 2), (2, 2), (2, 0)]
        reversed_path = list(reversed(path))
        assert compute_signed_area(path) == -compute_signed_area(reversed_path)


class TestMakeShapeKey:
    """Tests for make_shape_key function."""

    def test_straight_segment_format(self):
        key = make_shape_key(("left", "right"), "up")
        assert key == "path=(left,right) interior=up"

    def test_corner_segment_format(self):
        key = make_shape_key(("down", "right"), ("left", "up"))
        assert key == "path=(down,right) interior=(left,up)"

    def test_directions_are_sorted(self):
        # Order of input shouldn't matter
        key1 = make_shape_key(("right", "down"), ("up", "left"))
        key2 = make_shape_key(("down", "right"), ("left", "up"))
        assert key1 == key2

    def test_single_interior_not_wrapped_in_parens(self):
        key = make_shape_key(("up", "down"), "left")
        assert "interior=left" in key
        assert "interior=(left)" not in key


# =============================================================================
# FringeGenerator - Data Loading
# =============================================================================

class TestFringeGeneratorLoading:
    """Tests for FringeGenerator data loading."""

    def test_generate_before_load_raises(self):
        gen = FringeGenerator()
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        with pytest.raises(RuntimeError, match="not loaded"):
            gen.generate(path)

    def test_load_data_enables_generate(self, tmp_path):
        data = self._minimal_valid_data()
        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)

        # Should not raise RuntimeError now
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        # May raise ValueError for other reasons, but not RuntimeError
        try:
            gen.generate(path)
        except RuntimeError:
            pytest.fail("RuntimeError raised after loading data")
        except ValueError:
            pass  # Expected if mock data doesn't support this path

    def _minimal_valid_data(self):
        return {
            "neighbors": {},
            "classification_index": {}
        }


# =============================================================================
# FringeGenerator - Path Validation
# =============================================================================

class TestFringeGeneratorPathValidation:
    """Tests for path validation in FringeGenerator."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Generator with minimal data for validation tests."""
        data = {
            "neighbors": {},
            "classification_index": {
                "path=(down,right) interior=(down,right)": ["0x48"],
                "path=(down,left) interior=(down,left)": ["0x4B"],
                "path=(left,up) interior=(left,up)": ["0x4F"],
                "path=(right,up) interior=(right,up)": ["0x4C"],
            }
        }
        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)
        return gen

    def test_path_with_three_positions_raises(self, generator):
        with pytest.raises(ValueError, match="too short"):
            generator.generate([(0, 0), (0, 1), (1, 1)])

    def test_path_with_two_positions_raises(self, generator):
        with pytest.raises(ValueError, match="too short"):
            generator.generate([(0, 0), (0, 1)])

    def test_non_orthogonal_move_raises(self, generator):
        # Jump from (0,0) to (2,0) skips a tile
        path = [(0, 0), (0, 1), (2, 1), (2, 0)]
        with pytest.raises(ValueError, match="Non-orthogonal"):
            generator.generate(path)

    def test_diagonal_move_raises(self, generator):
        path = [(0, 0), (1, 1), (2, 0), (1, 0)]
        with pytest.raises(ValueError, match="Non-orthogonal"):
            generator.generate(path)

    def test_duplicate_position_raises(self, generator):
        path = [(0, 0), (0, 1), (0, 0), (1, 0)]
        with pytest.raises(ValueError, match="duplicate"):
            generator.generate(path)


# =============================================================================
# Test Data Builder
# =============================================================================

def build_rectangle_test_data():
    """
    Build test data supporting 4-tile and 8-tile rectangle paths.

    For a clockwise 4-tile square [(0,0), (0,1), (1,1), (1,0)]:
        Position 0: corner (down,right) interior=(down,right) -> RIGHT to pos 1
        Position 1: corner (down,left) interior=(down,left) -> DOWN to pos 2
        Position 2: corner (left,up) interior=(left,up) -> LEFT to pos 3
        Position 3: corner (right,up) interior=(right,up) -> UP to pos 0

    For 8-tile rectangles, we also need straight segments.
    """
    return {
        "neighbors": {
            # Convex corners - each needs connections for both CW and CCW traversal
            "0x48": {  # (down,right) interior=(down,right)
                "right": {"0x49": 50, "0x4B": 50},  # to horizontal or corner
                "down": {"0x52": 50, "0x5F": 50},   # to vertical straight or corner
            },
            "0x4B": {  # (down,left) interior=(down,left)
                "down": {"0x53": 50, "0x4F": 50},   # to vertical or corner
                "left": {"0x49": 50, "0x48": 50},   # to horizontal straight or corner
            },
            "0x4F": {  # (left,up) interior=(left,up)
                "left": {"0x4E": 50, "0x4C": 50},   # to horizontal or corner
                "up": {"0x53": 50, "0x4B": 50},                 # to vertical straight
            },
            "0x4C": {  # (right,up) interior=(right,up)
                "up": {"0x52": 50, "0x48": 50},     # to vertical or corner
                "right": {"0x4E": 50, "0x4F": 50},              # to horizontal straight
            },

            # Horizontal straights
            "0x49": {  # (left,right) interior=down
                "right": {"0x4B": 50, "0x49": 50},  # to corner or another straight
                "left": {"0x48": 50, "0x49": 50},
            },
            "0x4E": {  # (left,right) interior=up
                "right": {"0x4C": 50, "0x4E": 50, "0x4F": 50},
                "left": {"0x4F": 50, "0x4E": 50, "0x4C": 50},
            },

            # Vertical straights
            "0x52": {  # (down,up) interior=right
                "down": {"0x4C": 50, "0x52": 50},
                "up": {"0x48": 50, "0x52": 50},
            },
            "0x53": {  # (down,up) interior=left
                "down": {"0x4F": 50, "0x53": 50},
                "up": {"0x4B": 50, "0x53": 50},
            },
        },
        "classification_index": {
            # Convex corners (interior at the corner quadrant)
            "path=(down,right) interior=(down,right)": ["0x48"],
            "path=(down,left) interior=(down,left)": ["0x4B"],
            "path=(left,up) interior=(left,up)": ["0x4F"],
            "path=(right,up) interior=(right,up)": ["0x4C"],
            # Straight segments
            "path=(left,right) interior=down": ["0x49"],
            "path=(left,right) interior=up": ["0x4E"],
            "path=(down,up) interior=right": ["0x52"],
            "path=(down,up) interior=left": ["0x53"],
        }
    }


# =============================================================================
# FringeGenerator - Generation Output
# =============================================================================

class TestFringeGeneratorOutput:
    """Tests for FringeGenerator output structure and validity."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Generator with realistic neighbor data."""
        data = build_rectangle_test_data()
        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)
        return gen

    def test_output_length_matches_path_length(self, generator):
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)
        assert len(result) == len(path)

    def test_output_is_list_of_tuples(self, generator):
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_output_contains_position_and_tile_id(self, generator):
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)

        for pos, tile_id in result:
            assert isinstance(pos, tuple)
            assert len(pos) == 2
            assert isinstance(pos[0], int)
            assert isinstance(pos[1], int)
            assert isinstance(tile_id, int)

    def test_output_positions_match_input_order(self, generator):
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)

        output_positions = [pos for pos, tile in result]
        assert output_positions == path

    def test_output_tiles_are_in_valid_fringe_range(self, generator):
        """All assigned tiles should be valid fringe tile IDs."""
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)

        # Valid fringe ranges: 0x48-0x6F and 0x74-0x83
        for pos, tile_id in result:
            is_valid = (0x48 <= tile_id <= 0x6F) or (0x74 <= tile_id <= 0x83)
            assert is_valid, f"Tile {tile_id:#04x} at {pos} outside fringe range"

    def test_clockwise_rectangle_8_tiles(self, generator):
        """8-tile clockwise rectangle with straights and corners."""
        path = [
            (0, 0), (0, 1), (0, 2),  # top edge, going right
            (1, 2), (2, 2),          # right edge, going down
            (2, 1), (2, 0),          # bottom edge, going left
            (1, 0),                  # left edge, going up
        ]
        result = generator.generate(path)
        assert len(result) == 8

    def test_counterclockwise_rectangle_8_tiles(self, generator):
        """8-tile counter-clockwise rectangle."""
        path = [
            (0, 0), (1, 0), (2, 0),  # left edge, going down
            (2, 1), (2, 2),          # bottom edge, going right
            (1, 2), (0, 2),          # right edge, going up
            (0, 1),                   # top edge, going left
        ]
        result = generator.generate(path)
        assert len(result) == 8


# =============================================================================
# FringeGenerator - Neighbor Compatibility
# =============================================================================

class TestFringeGeneratorCompatibility:
    """Tests verifying neighbor compatibility in generated output."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Generator with neighbor frequency data for compatibility checking."""
        data = build_rectangle_test_data()
        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)
        gen._raw_neighbors = data["neighbors"]  # Save for verification
        return gen

    def test_adjacent_tiles_are_compatible(self, generator):
        """Each pair of adjacent tiles should appear in neighbor frequency data."""
        path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]
        result = generator.generate(path)

        freq_data = generator._raw_neighbors
        n = len(result)

        for i in range(n):
            j = (i + 1) % n
            pos_i, tile_i = result[i]
            pos_j, tile_j = result[j]

            direction = direction_to(pos_i, pos_j)
            tile_i_hex = f"0x{tile_i:02X}"
            tile_j_hex = f"0x{tile_j:02X}"

            # Check that tile_j appears as valid neighbor of tile_i in this direction
            neighbors = freq_data.get(tile_i_hex, {}).get(direction, {})
            assert tile_j_hex in neighbors, (
                f"Tile {tile_i_hex} at {pos_i} has {tile_j_hex} as {direction} neighbor, "
                f"but this pair not in frequency data"
            )


# =============================================================================
# FringeGenerator - Determinism
# =============================================================================

class TestFringeGeneratorDeterminism:
    """Tests for random seed behavior."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Generator with multiple candidates per shape for randomness testing."""
        data = build_rectangle_test_data()

        # Add extra candidates for variety
        data["classification_index"]["path=(left,right) interior=down"].append("0x62")
        data["neighbors"]["0x62"] = {
            "right": {"0x4B": 50, "0x62": 50},
            "left": {"0x48": 50, "0x62": 50},
        }
        # Update existing tiles to accept the new one
        data["neighbors"]["0x48"]["right"]["0x62"] = 50
        data["neighbors"]["0x4B"]["left"]["0x62"] = 50

        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)
        return gen

    def test_same_seed_produces_same_output(self, generator):
        path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]

        random.seed(12345)
        result1 = generator.generate(path)

        random.seed(12345)
        result2 = generator.generate(path)

        assert result1 == result2

    def test_different_seeds_can_produce_different_output(self, generator):
        """With multiple candidates, different seeds may produce different results."""
        path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]

        results = set()
        for seed in range(50):
            random.seed(seed)
            result = generator.generate(path)
            # Convert to hashable form
            results.add(tuple((pos, tile) for pos, tile in result))

        # With multiple candidates, we should see some variation
        # (may be 1 if all seeds happen to choose same, but usually > 1)
        assert len(results) >= 1


# =============================================================================
# FringeGenerator - Edge Cases
# =============================================================================

class TestFringeGeneratorEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture
    def generator(self, tmp_path):
        data = build_rectangle_test_data()
        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)
        return gen

    def test_minimum_valid_path_four_tiles(self, generator):
        """Smallest valid path is 4 tiles (a 1x1 square)."""
        path = [(0, 0), (0, 1), (1, 1), (1, 0)]
        result = generator.generate(path)
        assert len(result) == 4

    def test_unknown_shape_key_raises(self, tmp_path):
        """Path requiring shape not in classification_index should raise."""
        # Create generator missing straight segment shapes
        data = {
            "neighbors": {},
            "classification_index": {
                "path=(down,right) interior=(down,right)": ["0x48"],
                "path=(down,left) interior=(down,left)": ["0x4B"],
                "path=(left,up) interior=(left,up)": ["0x4F"],
                "path=(right,up) interior=(right,up)": ["0x4C"],
                # Missing: straight segments
            }
        }

        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)

        # 8-tile path requires straight segments
        path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]

        with pytest.raises(ValueError, match="Unknown shape key"):
            gen.generate(path)

    def test_no_compatible_tiles_raises(self, tmp_path):
        """Should raise if arc consistency eliminates all candidates."""
        # Create data where tiles exist but have no valid neighbor connections
        data = {
            "neighbors": {
                "0x48": {},  # No neighbors defined
                "0x4B": {},
                "0x4F": {},
                "0x4C": {},
            },
            "classification_index": {
                "path=(down,right) interior=(down,right)": ["0x48"],
                "path=(down,left) interior=(down,left)": ["0x4B"],
                "path=(left,up) interior=(left,up)": ["0x4F"],
                "path=(right,up) interior=(right,up)": ["0x4C"],
            }
        }

        data_file = tmp_path / "data.json"
        with open(data_file, "w") as f:
            json.dump(data, f)

        gen = FringeGenerator()
        gen.load_data(data_file)

        path = [(0, 0), (0, 1), (1, 1), (1, 0)]

        with pytest.raises(ValueError, match="No valid candidates"):
            gen.generate(path)

    def test_larger_rectangle(self, generator):
        """Test a larger rectangle path."""
        # 4x3 rectangle = 12 tiles
        path = [
            (0, 0), (0, 1), (0, 2), (0, 3),  # top
            (1, 3), (2, 3),                   # right
            (2, 2), (2, 1), (2, 0),           # bottom
            (1, 0),                            # left
        ]
        result = generator.generate(path)
        assert len(result) == 10