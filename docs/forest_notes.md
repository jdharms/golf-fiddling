# Forest Fill Algorithm Notes

## Basic concept

### Tile Types

There are three types of tiles used to create "out of bounds forests" in NES
Open Tournament Golf:

1. "Forest Fill" tiles.  These are tiles in the range $A0 to $A3.  They are tiles that have
   dense trees on them that overlap between each other.  They "tile" in a pattern that looks like:
   ```
   A0 A1 A2 A3 A0 A1 A2 A3
   A2 A3 A0 A1 A2 A3 A0 A1
   ```
   (Above is two full horizontal cycles of the tiling)
2. "Forest Border" tiles.  These are tiles that tend to form a 1-tile border around the Forest Fill
   tiles, essentially as a way to "end" the tiling.
3. "Out of Bounds Border" tiles.  These are tiles that have the same ground design as the forest tiles,
   but they have no trees at all on them.  Each tile is partially out of bounds and partially deep rough,
   so a forest is always outlined with a border of these tiles.

### Automatic Forest Creation

If we can fill out the tiles labeled with xx in all 8 tilings of
the forest fill pattern, we should be able to deterministically create borders.

There is a requirement that any tiles above the top xx's, to the
right of the right xx's, etc, must not be either forest fill or forest
border tiles.


So, here is our "template" we need to fill in:

```
-- xx xx xx xx --
xx A0 A1 A2 A3 xx
xx A2 A3 A0 A1 xx
-- xx xx xx xx --


-- xx xx xx xx --
xx A1 A2 A3 A0 xx
xx A3 A0 A1 A2 xx
-- xx xx xx xx --


-- xx xx xx xx --
xx A2 A3 A0 A1 xx
xx A0 A1 A2 A3 xx
-- xx xx xx xx --


-- xx xx xx xx --
xx A3 A0 A1 A2 xx
xx A1 A2 A3 A0 xx
-- xx xx xx xx --
```


And here is my attempt at doing it by hand:

```
-- B1 B6 A8 AD --
BB A0 A1 A2 A3 A7
AF A2 A3 A0 A1 B3
-- A5 AA B4 B9 --


-- B6 A8 AD B1 --
A9 A1 A2 A3 A0 AD
B5 A3 A0 A1 A2 B9
-- AF B4 B9 A5 --


BB A8 AD B1 B6 A7
AF A2 A3 A0 A1 B3
BB A0 A1 A2 A3 A7
AF B4 B9 A5 AA B3


A9 AD B1 B6 A8 AD
B5 A3 A0 A1 A2 B9
A9 A1 A2 A3 A0 AD
B5 B9 A5 AA B4 B9
```

--------

But, this leaves a lot of forest border tiles unused.

Why, and how, is that?

I think it comes down to the fact that patterns 3 and 4 above,
let's call them patterns $A2 and $A3 based on the top-left forest
fill tile, *require* forest border tiles in the "corners" of their
borders.  I think that some of the remaining forest border tiles are
probably used to "cut" those corners, and maybe to "square out" the
corners in the $A0 and $A1 patterns.  Let's check, starting with the
$A3 pattern.

To do that, I think we "cut into" the corner of the fill pattern,
so for example the top right $A1 in the $A2 pattern.  Remove that tile,
find a border tile that fits there instead, and then see where we're at.

Sure enough, I end up with:

```
A9 AD B1 B6 A7 --
B5 A3 A0 A1 B2 --
A9 A1 A2 A3 A0 AD
B5 B9 A5 AA B4 B9
```

This uses $B2 to replace $A2 "inside" the fill pattern, which is
one of the tiles that we didn't use in the "bordering" exercise above.

By inspection also we can use $A4, previously unused, in place of the
$A0 in

```
BB A8 AD B1 B6 A7
AF A2 A3 A0 A1 B3
BB A0 A1 A2 A3 A7
AF B4 B9 A5 AA B3
```

It ends up looking like this:

```
BB A8 AD B1 B6 A7
AF A2 A3 A0 A1 B3
-- A4 A1 A2 A3 A7
-- B5 B9 A5 AA B3
```

---------

## Tile family structure

Somewhere during this process I discovered that the forest border tiles
are actually a lot more regular and systematic than I at first realized.
Every Forest Fill tile has three "unfinished" trees on it, and these are
essentially requirements that they "exert" or impose on their
neighbors to finish the trees they started.  Every Forest Fill tile
exerts requirements in all four directions (and thus, "fulfills" the
corresponding requirement from its neighbor) even though there are only
three unfinished trees, as each forest fill tile has at least one tree
that exerts a requirement in a "corner", or equivalently in two adjacent
directions.

I started to realize that all the forest border tiles look *similar* to
a forest fill tile.  When I realized that there were *exactly* three
unfinished trees on each forest fill tile, *exactly* four forest fill
tiles, and *exactly* 24 forest border tiles, it dawned on me that every
forest border tile is in one of the four forest fill tile "families"
($A0-$A3) and each family has six tiles because there is a tile for each
subset of unfinished trees on the family's fill tile.  For the border
tiles that have two unfinished trees, there are 3c2 (three choose two),
or three, tiles in each family.  3c1 is also three, which rounds out the
family of six tiles.

---------

This adds an interesting constraint to the tile selection that can
probably help us with forest generation quite a bit: every tile
is in a family, and the "fill pattern" extends beyond the "interior"
region of a forest and into the "border" region, it just has to be
fulfilled with a (maybe *certain*) border tile in its family instead
of the fill tile itself.

-------

## Multi-bit exertions

One slight complication is that some of the fill tile edges have two
unfinished trees that exert in the same direction.  An example is $A2,
which has a tree fragment in its top left corner and a tree fragment in
its top right corner.  $A0 above it in the fill pattern continues both
of these trees, and they both continue "out" to the left or right
respectively.  These two trees actually span 4 different fill tiles.

I was initially tempted to just say that we could match tiles that exert
in "opposing" directions and as long as no exerting arrows were unmet we
would be fine, but these tiles with two trees exerting in the same
direction kind of ruin that.  $A2 exerts up with two different trees, as
I mentioned, but the tiles in the $A0 family which have to go above $A2
fulfill either zero, one, or both of them.  Further, "one" could be
either one, so there are really four categories that a tile in $A0
can be in when it comes to its southern border: [0, 0], [1, 0], [0, 1],
or [1, 1], where each of those "bits" is a specific tree that it
exerts/fulfills.

Therefore when I list the four families below, I'll need to list them
with either "bitstrings" or sub-lists for which *trees* they
exert/fulfill in each direction, not just which directions they exert
at all.  I'll keep the bitstrings ordered in absolute tree terms so they
don't need to be translated because they're clockwise or similar.

## Tile exertion data

All tiles are given in

`Tile: [up, right, down, left borders]`

format, where the up field means it *exerts* a requirement upwards and
fulfills a matched requirement in the down direction from the tile above
it.

```
A0: [1, 1, 11, 1]
* $A4: [1, 1, 01, 0]
* $A5: [1, 0, 00, 0]
* $A6: [1, 0, 10, 1]
* $A7: [0, 0, 10, 1]
* $A8: [0, 1, 11, 1]
* $A9: [0, 1, 01, 0]

A1: [11, 1, 1, 1]
* $AA: [11, 1, 0, 0]
* $AB: [10, 0, 0, 0]
* $AC: [10, 0, 1, 1]
* $AD: [00, 0, 1, 1]
* $AE: [01, 1, 1, 1]
* $AF: [01, 1, 0, 0]

A2: [11, 1, 1, 1]
* $B0: [01, 1, 1, 0]
* $B1: [00, 0, 1, 0]
* $B2: [10, 0, 1, 1]
* $B3: [10, 0, 0, 1]
* $B4: [11, 1, 0, 1]
* $B5: [01, 1, 0, 0]

A3: [1, 1, 11, 1]
* $B6: [0, 1, 11, 0]
* $B7: [0, 0, 10, 0]
* $B8: [1, 0, 10, 1]
* $B9: [1, 0, 00, 1]
* $BA: [1, 1, 01, 1]
* $BB: [0, 1, 01, 0]
```

Conclusion: all tiles in a forest region must exert 0s on all
external faces, and all internal faces must match.

---------

## Turning constraints into an algorithm

So the question now becomes: how do we actually *use* all this constraint
information to fill in a region of forest tiles automatically?

The "all internal faces must match" and "all external faces must be zeros"
rules are essentially a constraint satisfaction problem.  Every cell in
the region has a family (determined by its position in the 2x4 repeating
pattern), and within that family there are 7 candidate tiles.  Each
candidate has different exertion patterns, and we need to pick one tile
per cell such that:

1. Adjacent cells exert the same values toward each other
2. Cells on the boundary exert zeros toward non-forest neighbors

I thought about just iterating through cells and greedily picking tiles,
but that seemed fragile.  The problem is that picking a tile for one cell
constrains what tiles are valid for its neighbors, and those constraints
can cascade.  A greedy approach might paint itself into a corner where
no valid tile exists for some cell.

---------

## Arc consistency

After thinking about this for a while, I realized this is basically a
textbook constraint propagation problem.  The technique I ended up using
is called "arc consistency" - the idea is that for each pair of adjacent
cells, we make sure that every value in cell A's candidate set has at
least one compatible value in cell B's candidate set, and vice versa.

Instead of tracking candidate *tiles* directly, I track candidate
*exertion values* for each direction of each cell.  This is because the
matching constraint is really about the exertion values, not the tiles
themselves.  A cell starts out being able to achieve any exertion that
*some* tile in its family can produce, but as we propagate constraints,
these achievable sets shrink.

The algorithm works like this:

1. For each cell, initialize its achievable exertions to everything its
   family can produce
2. Constrain external edges to zeros
3. Use a worklist to propagate: whenever a cell's achievable set shrinks,
   re-examine its neighbors
4. When stable, pick the "best" tile from each cell's remaining valid set

The "best" tile is the one with the most 1-bits in its exertion pattern,
which tends to be the fill tile itself.  This way we prefer fill tiles
in the interior and only use border tiles where necessary.  The fill tiles
compress better in terms of ROM space in the game's compression system.

---------

## The INNER_BORDER fallback

One thing I didn't anticipate was that sometimes the constraints are
just unsatisfiable.  This can happen when a region has an awkward shape,
or when there are pre-existing forest tiles in the region that were
placed with a different orientation.

I needed a fallback, and luckily there's a tile that works: $3F, which
I call INNER_BORDER.  It's not technically a forest tile, but it's
visually compatible.  It's kind of a hybrid between a forest border tile
and an out of bounds border tile.  It shares the same ground color/texture/design
as the forest tiles, and the out of bounds side of the out of bounds border tiles,
but it has no trees on it at all, like the out of bounds border tiles.  Further, it has no
rough on it--no border at all.  It can be used just "inside" any out of bounds border tile and not
look out of place.  The key property for constraint satisfaction
is that it exerts zeros in all directions, so it's universally compatible 
with any neighbor that *also* exerts zero toward it.

When arc consistency leaves a cell with no valid tiles, I mark that cell
as INNER_BORDER and re-run the propagation.  The cell is now effectively
an external boundary, so its neighbors only need to exert zeros toward
it.  This usually resolves the conflict, though in pathological cases
we might need several INNER_BORDER tiles.

---------

## Orientation selection

The fill pattern can be "oriented" four different ways, depending on
which fill tile we consider to be at position (0, 0).  Picking $A0 vs
$A1 vs $A2 vs $A3 as the origin shifts the whole pattern.

Different orientations work better for different region shapes.  A region
that aligns well with one orientation might have lots of constraint
conflicts with another.  So rather than hardcoding an orientation, I
try all four and pick the one that produces:

1. The fewest edge failures (mismatched exertions)
2. The fewest INNER_BORDER tiles
3. The most fill tiles (as a tiebreaker)

This adds a bit of computation but it's worth it for the improved results.

---------

## Edge classification

During implementation I found it helpful to classify each cell's edges
into categories:

* **Internal edges** - neighbor is another cell we're filling
* **External edges** - neighbor is outside our region entirely
* **Screen edges** - neighbor is off the edge of the terrain grid
* **Pre-assigned edges** - neighbor is a forest tile that already exists
* **Inner border edges** - neighbor is a cell we've assigned to INNER_BORDER

Each category has different constraint behavior.  Internal edges need to
match.  External edges need to be zeros (unless the external tile is
another forest tile, in which case we match it).  Screen edges have no
constraint at all (and we'd even prefer them to be unfinished trees when possible,
to give the feeling of the map extending beyond the TV's screen).
Pre-assigned and inner border edges are essentially fixed external constraints.

---------

## Region detection

The algorithm also needs to figure out *what* to fill.  I use a simple
flood fill from placeholder tiles, expanding to include any contiguous
forest tiles.  This way if someone partially fills a region and then
asks to complete it, the existing tiles become pre-assigned constraints
rather than getting overwritten.

---------

## Putting it all together

The final algorithm flow is:

1. Detect contiguous regions of placeholder tiles (plus adjacent forest)
2. For each region, try all four orientations
3. For each orientation:
   a. Assign families to cells based on position
   b. Identify pre-assigned tiles and cells to fill
   c. Classify edges
   d. Initialize achievable exertion sets
   e. Propagate arc consistency
   f. If any cell has no valid tiles, mark it INNER_BORDER and repeat
   g. Assign best remaining tile to each cell
   h. Count failures and INNER_BORDER usage
4. Pick the orientation with best metrics
5. Return the tile assignments

The implementation uses a `CellConstraints` class to track achievable
exertions per cell, with methods for constraining directions and
computing valid tiles.  The worklist propagation re-examines
all affected edges when a cell's achievable set changes.

---------

## Results

The algorithm handles all the cases I've thrown at it so far.  Simple
rectangular regions get filled with mostly fill tiles and clean borders.
Irregular shapes work too, though they need more border tiles.  Regions
with pre-existing forest tiles from different orientations (e.g., a tile
in the A2 family in a spot where the A4 family belongs) tends to produce
mismatches and bad results.  I initially thought the algorithm might still
be able to recover from this and "push" the problem out to the screen edge.
This isn't really the case--to fix these "parity" errors the algorithm
would really need to partition the forest into two forests, one for each
parity constrained upon it.

The constraint propagation is fast enough that trying all four
orientations isn't a problem.  Most of the work happens in the initial
constraint setup; the actual propagation converges quickly because the
families are small (only 7 tiles each) and the exertion values are
simple (at most 2 bits).

## Practical Terms

In terms of practical, real-world usage of this, I've found that I like to
either:

1. Let the Forest Fill do the entire region with no seeded tiles to get a maximally "dense" forest.
2. Seed the middle somewhere with exactly one forest border tile.  This will both pin the
   parity of the tiling, but also give a nice bit of "visual interest" in the part of the forest
   that has to work around the constraint.
3. If *more* variation is desired, putting more parity-compatible forest border tiles
   into the interior should generally work.  An easier approach is to toss an Inner Border
   tile here and there to force a little "forest clearing".
