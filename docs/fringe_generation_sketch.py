def generate_fringe_tiles(path, classification_index, neighbor_freq, freq_threshold=5):
    """
    path: list of (row, col) in trace order, forming closed loop
    """
    n = len(path)

    # Step 1: For each position, determine shape family and candidate set
    candidates = []
    for i in range(n):
        prev_pos = path[(i - 1) % n]
        curr_pos = path[i]
        next_pos = path[(i + 1) % n]

        incoming_dir = direction_from(prev_pos, curr_pos)
        outgoing_dir = direction_to(curr_pos, next_pos)
        interior_side = compute_interior_side_from_winding(path, i)

        shape_key = make_shape_key(incoming_dir, outgoing_dir, interior_side)
        candidates.append(set(classification_index[shape_key]))

    # Step 2: Filter by pairwise edge compatibility
    # For each adjacent pair, remove candidates that have no valid neighbor
    changed = True
    while changed:
        changed = False
        for i in range(n):
            j = (i + 1) % n
            dir_i_to_j = direction_to(path[i], path[j])
            dir_j_to_i = opposite(dir_i_to_j)

            # Filter candidates[i]: keep only tiles that have a compatible neighbor in candidates[j]
            valid_i = set()
            for tile_i in candidates[i]:
                for tile_j in candidates[j]:
                    if is_compatible(tile_i, dir_i_to_j, tile_j, neighbor_freq, freq_threshold):
                        valid_i.add(tile_i)
                        break

            if valid_i < candidates[i]:
                candidates[i] = valid_i
                changed = True

            # Same for candidates[j]
            valid_j = set()
            for tile_j in candidates[j]:
                for tile_i in candidates[i]:
                    if is_compatible(tile_i, dir_i_to_j, tile_j, neighbor_freq, freq_threshold):
                        valid_j.add(tile_j)
                        break

            if valid_j < candidates[j]:
                candidates[j] = valid_j
                changed = True

    # Step 3: Assign tiles (greedy or random from remaining valid sets)
    assignment = []
    for i in range(n):
        j = (i + 1) % n
        dir_i_to_j = direction_to(path[i], path[j])

        if i == 0:
            tile = random.choice(list(candidates[0]))
        else:
            # Pick a tile compatible with previous assignment
            prev_tile = assignment[-1]
            prev_dir = direction_to(path[i-1], path[i])
            valid = [t for t in candidates[i]
                     if is_compatible(prev_tile, prev_dir, t, neighbor_freq, freq_threshold)]
            tile = random.choice(valid)

        assignment.append(tile)

    # Verify closure: last tile compatible with first
    # (Should be guaranteed by arc consistency, but worth checking)

    return list(zip(path, assignment))

def is_compatible(tile_a, direction, tile_b, neighbor_freq, threshold):
    """Check if tile_a can have tile_b as neighbor in given direction."""
    neighbors = neighbor_freq.get(tile_a, {}).get(direction, {})
    return neighbors.get(tile_b, 0) >= threshold