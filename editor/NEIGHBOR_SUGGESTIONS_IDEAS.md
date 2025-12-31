# Neighbor-Based Editing Features - Brainstorming

This document captures ideas for making terrain tile editing less error-prone by leveraging the `terrain_neighbors.json` dataset of valid neighbor relationships from vanilla courses.

## Context

The editor currently highlights tiles in red when they have neighbor relationships that don't exist in any vanilla course. This is descriptive (what's wrong) but not prescriptive (how to fix it). The challenge: things like trees and slopes span multiple tiles in precise patterns, and floating trees are unacceptable.

## Current Pain Points

**Biggest challenge: Forest boundaries** are by far the most painful editing experience. The typical forest structure requires precise transitions:

```
Out of Bounds Border ($80-$9B)
    ↓
Inner Border ($3F) - rough/OOB boundary, no trees
    ↓
Forest Border ($A4-$BB) - 24 complex transition tiles
    ↓
Forest Fill ($A0-$A3) - 4-tile horizontal repeating pattern
```

**What works today:**
- Forest fill ($A0-$A3) is already handled by the drag-and-transform system in `editor/controllers/transform_logic.py`
- Individual tree placement is tedious but manageable
- Feature borders (water/sand) are workable, though tile palette organization would help

**Dream workflow:**
1. User manually draws the rough/OOB border
2. User places Inner Border ($3F) tiles where desired
3. System automatically fills the forest region with:
   - Forest Border tiles ($A4-$BB) near edges
   - Forest Fill tiles ($A0-$A3) in interior
   - Perfect neighbor-constraint satisfaction throughout
   - Seamless transitions from Border → Forest Border → Forest Fill

**Why this is hard:**
- Forest borders have 24 different tiles ($A4-$BB) - the most complex part of forest drawing
- Transitions must respect strict neighbor constraints
- Multi-tile depth borders require careful tile selection
- Pattern alignment must be maintained for the fill region

---

## Option 1: Smart Tile Cycling (Middle-Click)

**Concept**: Middle-click a tile to cycle through alternative tiles that would satisfy its current neighbors.

**Details**:
- Show only tiles that are compatible with all 4 current neighbors
- Rank suggestions by frequency (most common compatible tile first)
- Could show frequency stats: "This pattern seen 47 times in vanilla courses"
- Shift+middle-click cycles backwards through suggestions
- Visual indicator (text or highlight) showing which option you're on

**Pros**:
- Lightweight to implement
- Quick one-click fixes
- Natural exploration of alternatives

**Cons**:
- Doesn't help if no compatible tile exists
- Requires trial-and-error for multi-tile objects

---

## Option 2: Contextual Tile Palette

**Concept**: When a terrain tile is selected/active, filter or recolor the palette to show compatibility.

**Details**:
- Green/bright: tiles compatible with current neighbors
- Yellow/muted: tiles that work in some directions but not all
- Red/grayed: tiles incompatible with any current neighbor
- Hover shows specific incompatibilities: "Would break up-neighbor relationship"
- Could also show frequency stats: "Appears 156 times above tile X"

**Pros**:
- Educational - user learns patterns naturally
- No random cycling - user can make informed choice
- Works even when incompatible tiles exist

**Cons**:
- Requires more UI space
- Might feel information-heavy

---

## Option 3: Pattern Stamping

**Concept**: Extract common multi-tile patterns from vanilla courses and allow stamping them.

**Details**:
- Analyze vanilla courses to find common clusters (2x2 trees, slope sequences, etc.)
- Create a pattern library/palette with visual thumbnails
- Shift+click to stamp entire pattern instead of single tile
- Patterns could be smart: "Forest edge pattern" adapts to surrounding context
- Could categorize: forest, grass, rougher, slopes, trees, etc.

**Pros**:
- Solves multi-tile floating object problem at root
- Natural gameplay feeling from real patterns
- Educational - shows how vanilla levels work

**Cons**:
- More complex to implement and maintain
- Pattern library needs curation

---

## Option 4: "Did You Mean?" Suggestions

**Concept**: Right-click a red-outlined tile to see smart suggestions.

**Details**:
- Shows top 3-5 alternative tiles ranked by how common that exact neighbor context is
- Display as popup menu or panel showing: tile preview, frequency count, and diff ("fixing N red neighbors")
- One-click to swap and immediately see the result
- Could also suggest: "Try tile X to the left instead" (multi-tile reasoning)

**Pros**:
- Direct problem → solution flow
- Minimal cognitive load
- Helps without forcing anything

**Cons**:
- Only works on red tiles
- Doesn't help in undiscovered problematic areas

---

## Option 5: Neighbor Preview Mode

**Concept**: When hovering over a tile in the palette, show where it would be compatible.

**Details**:
- Highlight or outline compatible locations in the terrain
- Show frequency stats: "This tile works here in X vanilla contexts"
- Inverse mode: select a tile in terrain, highlight compatible neighbors in palette
- Could have a toggle for "show only compatible" in the palette

**Pros**:
- Visual learning tool
- Helps place new tiles strategically
- No accidents - see compatibility before clicking

**Cons**:
- Requires careful UI design to avoid clutter
- Slower workflow (more hovering/checking)

---

## Option 6: Smart Fill Tool

**Concept**: Like flood fill but respects neighbor constraints and adds variation.

**Details**:
- Select a region (e.g., forest area) and a "base tile" to fill with
- Tool picks compatible tiles randomly from vanilla patterns
- Respects all 4-neighbor constraints throughout
- Could have options: "Dense forest" vs "Sparse trees" (frequency threshold)
- Prevents uniform repetitive look while staying valid

**Pros**:
- Great for rapid prototyping
- Feels natural from real patterns
- Can fill large areas with confidence

**Cons**:
- Less control than manual placement
- Randomness might need tweaking for right feel
- Needs good default parameters

---

## Option 7: Intelligent Forest Fill (Meta-Tile Based)

**Concept**: Specialized smart fill specifically for forests, using "meta-tiles" (forest regions) rather than individual tiles.

**Details**:
- User draws the boundary (Out of Bounds Border $80-$9B tiles) to define
  forest region
- User triggers forest fill (e.g., keyboard shortcut, context menu)
- System analyzes the bounded region and fills it intelligently:
  - **Constraint solving**: Uses `terrain_neighbors.json` to ensure all tiles have valid neighbors
  - **Distance field**: Calculates distance from each cell to nearest boundary
  - **Edge heuristics**: Places Forest Border tiles ($A4-$BB) near boundaries
  - **Interior fill**: Places Forest Fill pattern ($A0-$A3) in center, maintaining horizontal repeat alignment
  - **Frequency scoring**: Among valid options, prefers tiles common in vanilla courses
- Could work inward from boundary (flood fill approach) or use wave function collapse
- Unlike Option 6, this doesn't ask user to pick a "base tile" - the system knows it's making a forest

**Pros**:
- Solves the #1 pain point directly
- Leverages existing neighbor data comprehensively
- Maintains pattern integrity automatically
- Reduces forest creation from painful to instant
- No manual tile selection needed - system understands "forest" as a concept

**Cons**:
- Forest-specific (not general purpose)
- Requires sophisticated constraint solving algorithm
- May need backtracking if painted into corners
- Heuristics for border depth need tuning
- Edge cases: what if user-drawn boundary is irregular?

**Implementation notes**:
- Likely uses a priority queue to fill tiles in order (boundary-first)
- Each tile queries neighbor data for valid options given what's already placed
- Scoring function combines: distance from edge, neighbor compatibility, vanilla frequency
- May need fallback strategies if no valid tile exists (rare, but possible)

**Relationship to Option 6**:
This is essentially Option 6.1 or Option 6.B - a specialized variant that:
- Uses "forest region" as the meta-tile concept instead of base tile selection
- Focuses on a single high-value use case rather than general filling
- Deeply integrates knowledge of forest structure ($3F → $A4-$BB → $A0-$A3)

---

## Possible Combinations

These options aren't mutually exclusive:
- **Quick workflow**: Options 1 + 4 (cycling for exploration, right-click for problems)
- **Learning workflow**: Options 2 + 5 (palette feedback + preview)
- **Bulk workflow**: Option 3 + 6 (patterns for multi-tile, smart fill for areas)
- **Forest-focused workflow**: Option 7 + 1 (intelligent forest fill for bulk, cycling for touch-ups)
- **Complete solution**: All of them (different tools for different situations)

**Priority recommendation based on pain points:**
Start with Option 7 (Intelligent Forest Fill) to address the #1 editing pain point, then add Options 1 & 4 for general tile fixing and exploration.

---

## Open Questions

- What's the user's typical editing workflow? (placing individual tiles vs. bulk terrain design)
- Should these only work for red-flagged neighbors, or for all editing?
- How much randomness/variation is desired vs. exact pattern matching?
- Would a pattern library be maintained manually or auto-generated?

---

## Analysis & Feasibility (Option 7: Forest Fill)

**Analysis Tool**: Created `tools/analyze_forest.py` to assess feasibility of intelligent forest fill using `terrain_neighbors.json`.

### Key Findings: 🟢 HIGHLY FEASIBLE

**Coverage - Perfect:**
- ✓ All 4 forest fill tiles ($A0-$A3) have comprehensive neighbor data
- ✓ All 24 forest border tiles ($A4-$BB) have comprehensive neighbor data
- ✓ Inner Border ($3F) has extensive neighbor data (127 relationships)
- ✓ 140 unique tiles total, 6750 total neighbor relationships in dataset

**Pattern Validation:**
- ✓ Forest fill horizontal repeat pattern confirmed: $A0 → $A1 → $A2 → $A3 → $A0
- ✓ Each fill tile correctly knows its expected left/right neighbors
- ✓ Pattern can be maintained during automated fill

**Transition Paths:**
- ✓ 22/24 forest border tiles appear adjacent to Inner Border ($3F)
- ✓ 23/24 forest border tiles appear adjacent to forest fill
- ✓ Clear paths exist from boundary → border → fill
- ✓ Inner Border can sometimes directly neighbor forest fill ($A1, $A3)

**Border Depth Support:**
- ✓ All 24 forest border tiles can neighbor other forest border tiles
- ✓ Multi-tile-deep borders are well-supported in the data
- ✓ System can determine appropriate border depth dynamically

**No Blockers Detected:**
The neighbor dataset is comprehensive enough to support constraint-based forest fill without hitting dead ends or missing data.

### Recommended Implementation Approach

1. **Flood fill from boundary inward**
   - Start at Inner Border ($3F) tiles
   - Work inward using breadth-first search

2. **Distance field calculation**
   - Calculate each cell's distance to nearest boundary
   - Use distance to determine border vs. fill regions

3. **Priority queue filling**
   - Fill tiles in order: boundary tiles first, interior last
   - Ensures sufficient neighbor context exists when placing each tile

4. **Constraint satisfaction for each tile**:
   - Query `terrain_neighbors.json` for tiles compatible with already-placed neighbors
   - Filter candidates by category (prefer border near edges, fill in interior)
   - Score by frequency in vanilla courses (prefer common patterns)
   - Select highest-scoring valid option

5. **Pattern alignment** (for fill region):
   - Maintain $A0-$A3 horizontal repeat pattern
   - Track pattern phase to ensure continuity

6. **Backtracking strategy** (if needed):
   - If no valid tile exists, backtrack and try different earlier choices
   - Should be rare given data coverage

### Estimated Complexity

- **Data access**: Simple (JSON lookups)
- **Algorithm**: Moderate (distance field + constraint solving + scoring)
- **Edge cases**: Some (irregular boundaries, deep borders)
- **Overall**: Tractable for a skilled developer, 1-2 weeks implementation + testing

---

## Next Steps for Discussion

### Implementation Decisions

1. **Algorithm Choice**:
   - Simple distance field + greedy selection (faster, simpler)
   - Wave function collapse (fancier, more robust, slower)
   - Hybrid approach?

2. **Border Depth Heuristic**:
   - Fixed depth (e.g., always 2-3 tiles deep)?
   - Dynamic based on region size?
   - Learn from vanilla course patterns?
   - User-configurable?

3. **UI/UX Trigger**:
   - Keyboard shortcut after selecting region?
   - Context menu when right-clicking bounded area?
   - Special "forest fill mode" tool?
   - How does user "undo" if result is unsatisfactory?

4. **Frequency Data**:
   - Do we need to count tile frequencies in vanilla courses?
   - Or is existence in neighbor data sufficient?
   - Should rare tiles be deprioritized or excluded?

5. **Edge Cases**:
   - What if boundary is irregular or has gaps?
   - What if region is very small (< 4 tiles)?
   - What if Inner Border tiles form disconnected regions?
   - How to handle pre-existing tiles inside boundary?

### Prototyping Plan

1. **Phase 1**: Simple proof-of-concept
   - Rectangular forest regions only
   - Fixed border depth (2 tiles)
   - Greedy tile selection

2. **Phase 2**: Refinement
   - Support irregular boundaries
   - Dynamic border depth
   - Frequency-based scoring

3. **Phase 3**: Polish
   - Undo/redo support
   - Preview mode before committing
   - Performance optimization for large regions

### Open Questions

- Should this be a separate "tool mode" or integrated into existing workflow?
- Do we want preview/confirmation before applying fill?
- Should the system highlight which tiles it's uncertain about?
- Can this technique generalize to other meta-tiles (water hazards, sand traps)?

---

## Appendix: Terrain Tile Details

### Definitions:
"Feature": anything that is not rough or out of bounds is a feature drawn with a shared pool of tiles and distinctions are drawn by changing palettes.  The three feature types are 1. Fairway 2. Sand traps 3. Water hazards.

### Tile usage:

#### Fill:
- Shallow rough: $25
- Feature: $27
- Deep rough: $DF

#### Teebox: $35-$3C

#### Rough:
- Small tree: $3E (single tile)
- Large Treetop: $9C
- Large Treebase: $9D
- Medium Treetop: $9E
- Medium Treebase: $9F

Large and medium treetop/treebases are interchangeable!

#### Features: (borders are always partially feature and partially rough)
- borders With Depth: $40-$53
- borders, Flat (fairway, also south side of all features): $54-$7F
- W/ Large Treetop: $BC
- w/ Large Treebase: $BD
- w/ Medium Treetop: $BE
- w/ Medium Treebase: $BF

#### Out of bounds:
- Border: $80-$9B
- "Inner" Border: $3F (This is used to set the trees back a full tile from the rough/OOB border)
- Forest fill:  $A0-$A3 (this is a pattern that is repeated horizontally and tiled vertically to fill most forests)
- Forest border: $A4-$BB (This seems like the most complex part of forest drawing)
