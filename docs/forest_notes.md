Basic concept:

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

A9 AD B1 B6 A7 --
B5 A3 A0 A1 B2 --
A9 A1 A2 A3 A0 AD
B5 B9 A5 AA B4 B9

This uses $B2 to replace $A2 "inside" the fill pattern, which is
one of the tiles that we didn't use in the "bordering" exercise above.

By inspection also we can use $A4, previously unused, in place of the
$A0 in

BB A8 AD B1 B6 A7
AF A2 A3 A0 A1 B3
BB A0 A1 A2 A3 A7
AF B4 B9 A5 AA B3

It ends up looking like this:

BB A8 AD B1 B6 A7
AF A2 A3 A0 A1 B3
-- A4 A1 A2 A3 A7
-- B5 B9 A5 AA B3

---------

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

All tiles are given in

`Tile: [up, right, down, left borders]`

format, where the up field means it *exerts* a requirement upwards and
fulfills a matched requirement in the down direction from the tile above
it.

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

Conclusion: all tiles in a forest region must exert 0s on all
external faces, and all internal faces must match.