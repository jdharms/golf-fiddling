# Neighbor-Based Editing Features - Brainstorming

This document captures ideas for making terrain tile editing less error-prone by leveraging the `terrain_neighbors.json` dataset of valid neighbor relationships from vanilla courses.

## Context

The editor currently highlights tiles in red when they have neighbor relationships that don't exist in any vanilla course. This is descriptive (what's wrong) but not prescriptive (how to fix it). The challenge: things like trees and slopes span multiple tiles in precise patterns, and floating trees are unacceptable.

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

## Possible Combinations

These options aren't mutually exclusive:
- **Quick workflow**: Options 1 + 4 (cycling for exploration, right-click for problems)
- **Learning workflow**: Options 2 + 5 (palette feedback + preview)
- **Bulk workflow**: Option 3 + 6 (patterns for multi-tile, smart fill for areas)
- **Complete solution**: All of them (different tools for different situations)

---

## Open Questions

- What's the user's typical editing workflow? (placing individual tiles vs. bulk terrain design)
- Should these only work for red-flagged neighbors, or for all editing?
- How much randomness/variation is desired vs. exact pattern matching?
- Would a pattern library be maintained manually or auto-generated?
