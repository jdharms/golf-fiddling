# Randomizer Design Document

> **Note**: This document was authored in full by jdharms, no AI assistance

## Randomizers

Randomizers are websites or software that act as patch generators for games, often
retro games, that randomize some aspect(s) of the game.  Some classic examples are
[The ALTTP Randomizer](https://alttpr.com/en) or the Final Fantasy Randomizer.
These randomizers have "logic" as part of their implementation which ensures that
unbeatable games are never generated, primarily by making sure that the ability
to get to a place or "do a thing" is never gated *behind* getting to that place or
doing that thing.

There are other randomizers that don't need to have this concept of logic built-in,
or at least not as strong of a concept.  Randomizers for platformers like Super
Mario Bros. 3, Kirby's Adventure, Donkey Kong Country, etc. primarily randomize
things like:

* Level order
* Power-ups in blocks
* Enemies in various stages

Generally platformers don't have hard requirements on maintaining power ups, as
that can lead to softlock situations, so these randomizers can mostly get away with
either "no logic" or minimal, targeted hardcoding here and there to make sure that
"there is always a [whatever] in stage [wherever]" or "there is never an [enemy] in
level [whatever]."  These randomizers are still fun and interesting and can provide
a similar feeling of "a different game every time".

### Randomizer Racing

Competitive or semi-competitive communities have popped up around quite a few games
focused around racing (either simultaneously or asynchronously) to beat randomizer
seeds.  This is done by having one person generate the seed, all participants
patch their game with the seed's output, and then race to complete the game in the
quickest time.

Somewhat paradoxically, sometimes randomizers *un*-randomize aspects of the game
if doing so would lead to a more pleasant racing experience.  An example of this
is that The ALTTP Randomizer "seeds" the RNG patterns of various bosses and
mini-games so that all players in a given seed will encounter the same situation.
The broad point here is that competitive aspects of the game can inform the
design and feature set of a randomizer.

## NES Open Tournament Golf "League"

Between December 2025 and February 2026 I organized and ran a "League" for 12
players including myself.  We used the vanilla, unaltered US game and had six
"weeks", or rounds, of competition.  The course breakdown was two weeks on the
U.S. course, one week on the U.K. course, and three weeks on the Japan course.
The way the scoring/standings worked is that each player started the league with
$100 in "Fun Bucks", and each week players were paired against another player
for a match that would result in some money changing hands.  Players could always
play their rounds at whatever time best suited them, because there's not a lot
of advantage (though there is admittedly *some*) in knowing the result of your
opponent's round while playing.  Players streamed their rounds on Twitch,
uploaded a screenshot of the end-of-round scorecard to Discord, and I kept track
of results in a spreadsheet.  We used various classic formats, like skins game,
match play, pairs play using best ball, etc.

Overall the league was a success, and we had a lot of fun.  It was designed to
be a low-stakes, low-stress, and just generally "fun" experience, and I think it
delivered on that.  Players encountered different wind values on the same holes
than their opponents did, and that certainly affected things.  The difference
between playing with and against the wind on a long par 5 can be the difference
between an easy birdie and chasing par. Since we largely didn't take it too
seriously, this was fine and I don't think it was a real issue.

## NES Open Tournament Golf Randomizer

### Background Work

During my "holiday break" in December 2025/January 2026 I started working on a
course editor for NES Open.  It was my first "AI-driven" software development
project.  Many people had similar projects right around this time, as this was
also approximately "the moment" that Claude Code and Codex became "good enough".
I was impressed with how well it went, considering that my past experiences with
things like GitHub Copilot and similar AI tools was... not very good.  It was
certainly not perfect by any stretch, and at some point I may write up more
thoughts.  But I did manage to release version 1.0 of the course editor "to users"
on January 27th, nearly exactly one month after my initial commit.

I took a break from my NES Open reverse-engineering and development work after
for a few months, and then picked up what I'd consider two parallel workstreams.

#### QOL/Balance Patches

One of the pieces of feedback, that I heard both directly and in passing, for
season one of our golf League was that seeding the wind's behavior for all
players would be nice.  I had done some investigation into how the wind values
were calculated and stored already, so this mostly came down to figuring out
the best way to keep the wind sequences stable such that each player would get
the same wind for the same shot on each hole.

There are a few other small tweaks like this that I explored as well.  One of the
Famicom Disk System (FDS) golf titles includes the ability to press Select when
lined up for a swing to move Mario "back" off the ball about 8 or 10 pixels so
you can take a practice swing.  This feature would be very nice for NES Open,
as something you often have to do is switch between slow/medium/fast swings
for purposes of manipulating the distance curve of the clubs.  I found that this
was surprisingly not that difficult to implement.

A rough edge that NES Open has is no concept of a mercy rule or tap-in feature.
You **will** get the ball in the hole before you move on to the next one, no
matter if that takes you one shot or four hundred.  The game stops *counting*
your strokes for a given hole past 50, and I think the reason for this is to keep
the theoretical maximum score for a round of golf to three digits.
(18 holes * 50 strokes = 900 strokes). I've implemented a patch to change this,
making it to where if you don't get the ball in the hole on the 9th stroke, you
get an automatic one-stroke "tap-in" from anywhere on the course, leaving you
with a score of 10 for the hole.  The implementation is a little janky and could
possibly use some refining later.  I hooked into the "after the ball finishes
rolling" routine for my custom code, so if you "miss" the ball (i.e., you never
finish your stroke button inputs) the ball rolling routine never runs, the mercy
hook never runs, and you can be required to swing again.  This probably never
matters in practice, but it would be good to clean up at some point.

#### Bringing in Additional Content

A version of NES Open was released in Japan titled "Mario Open Golf", presumably
because in Japan the console wasn't called the NES.  Mario Open has five courses,
compared to NES Open's three courses, as well as a sixth "remix course" that
is essentially just pointers to 18 holes that exist in the other five courses.
Each of the five courses in Mario Open has its own unique course gameplay music,
just like each of the three courses in NES Open.  Surprisingly, all of the songs
are unique across *both games*, giving us a total of 8 songs.  Inside the five
courses in Mario Open, some of the holes are either present in NES Open or adapted
from holes in NES Open.  A lot more detail about this is in a blog post
that I've found to be incredibly useful, here:
[Nintendo's 8-bit Obsession with Golf](https://nerdlypleasures.blogspot.com/2019/10/nintendos-8-bit-obsession-with-golf.html)

Since I'd created a course editor for NES Open, I already had code written to dump
courses from a rom file into a "readable" format.  Luckily, Mario Open uses the
same tileset and compression algorithm/encoding format to store the course data
in the program ROM.  I was able to open Mario Open in an emulator, note down some
memory addresses that changed when I panned the map or loaded a hole, and pretty
quickly got all five courses dumped to disk.

I used my existing pipeline to write one of the Mario Open courses to the NES Open
rom, booted up the game, started a round, and instantly crashed the system.

It turns out that Mario Open allows for holes to be quite a bit longer/"taller"
than NES Open.  This resulted in some problems:

* The buffers in RAM/WRAM the hole data was decompressed to were too small to
hold the largest Mario Open holes.  The decompression routines run until they're
out of data to unpack, so without fixes they just clobber the memory immediately
following the buffer if the data is too large.
* The "camera math" for knowing where to put the camera for each shot, how to
follow the ball and such, uses lookup tables and those lookup tables are
right-sized for the length of the NES Open holes.  The lookups aren't bounded
(why would they be?) so junk values are read and sprites can be drawn in the wrong
places or not at all.
* There's no room to expand either of these to fix the problems.

It ended up being quite a process to support longer holes.  I ended up getting rid
of the "career stats" feature to free up SRAM to hold the uncompressed terrain
buffer and relocating the various offset tables and fixing all callers to use
the relocated tables.

----

I'm not especially familiar with NES sound/music programming, but Claude is.  I
asked Claude to create a tool to disassemble sections of a rom file and to inline
annotations when present from my "personal" collection of memory address labels
that I'd collected from my reverse-engineering work.  I also gave it the ability to
have its "own" collection of memory address labels that it could add to as it
"figured things out".  With these tools I was essentially able to say "Hey Claude,
go figure out how the sound/music engine works for this game." and it was perfectly
able to do so.  I also gave it the Mario Open rom and it was able to repeat the
exercise, and "translate" the music between the two to account for the *slight*
differences in the engines' implementations.  Now we have access to all 8 course
themes.

### Future

With all of this work done, I feel like an almost "obvious" next step is to
implement a randomizer.  I'm hoping to have version 1.0 of the randomizer released
in time for "Season Two" of "Golf League", and to run the event using randomized
roms.

In the next few sections I'm going to try and jot down the different ideas/goals/
non-goals I have for the randomizer.  It'll be a combination of user/feature-level
design alongside architectural decisions.

## Randomizer Design/Architecture

### Features, Requirements, Constraints, etc.

The mission statement in a paragraph for the randomizer would be something like: 

"Allow users to patch their NES Open Tournament Golf rom to get back a game
that supports Stroke Play mode for One or Two Players on a single course
composed of 18 holes, randomly chosen from a pool of holes provided by the game,
possibly with some constraint or filter used.  The generated game should be
suitable for competitive play, and users should be able to easily and legally share
or coordinate access to a generated game for distributed multiplayer purposes."

Some explicit non-goals:

* Support for the game's Tournament modes, or even the single player Match Play
mode. We exclusively use the result of playing through a course in Stroke Play
mode for our league, so that will be the use-case we support first.
* Multiple courses on a single randomized rom.  At the point that users are
generating randomized roms, they can generate multiple randomized roms if something
like a "two course competition" is desired.  This allows us to essentially not
worry about space when it comes to inserting course data into the rom. It does
leave us with a possible question of how could you generate a two course
competition where no holes are shared between the two courses.  That's something
I'll figure out for version 2.0. (Also, see Appendix B)

Constraints:

* Use must be locked behind having access to a legally-obtained vanilla rom file.

### Base ROM vs. Vanilla ROM

There's a common concept referred to as a randomizer base rom.  Essentially the
"base rom" is the rom after QOL/randomizer scaffolding patches have been applied.
You can think of it as the set of patches that makes things randomizable.  Once
you have a base rom, you should be able to fairly easily take a human-readable
seed "manifest", usually a json or yaml file, that contains the output of the
randomization process, and create the final rom.  As an example, the ALTTPR base
rom would include the patch required to make bosses drop something other than a
full heart container, a seed's manifest would include what Moldorm drops as
part of a large yaml dict or similar, and the "final patcher" would take the
base rom and produce a rom where Moldorm drops the appropriate item.

My current thoughts for the NES Open Base ROM:

* Balance/RNG Control: Wind seeding patch, printing the seed hash on the main menu
and on the scorecard, for quick verification.
* WRAM Expansion: All the constituent changes required to support Mario Open courses
* Menu trimming: Take away access to unnecessary/removed features like career
earnings, statistics, tournament modes, etc.
This also reclaims a bunch of rom space!

There are other patches that are generally quality of life that probably *shouldn't*
be applied by default, at least not without some "community discussion".  In this
bucket I'd put the practice swing functionality and the mercy tap-in rule.

### Seed Generation

The primary randomization that happens as part of generating a seeded rom is 
the creation of an 18 hole randomized course.  I've spent some time thinking of
a mental model of this and landed on the following:

There is a hole `catalog`, which is the collection of all holes in the "universe".
This includes at least the holes from the courses in NES Open and Mario Open,
but also potentially "blessed" community holes as well.  There's precedent for this
from the Zelda II randomizer, which at this point includes hundreds of
community-designed rooms that can be placed into dungeons.

From the `catalog`, a hole `pool` is created, from which the 18 holes will be
selected.  There might be *filters* applied between the catalog and the pool,
like an option to remove "hard" or "expert" holes.  Some of the holes in Mario
Open are *very difficult*.  Less obviously, though, there might be other *maps*
or *transformations* applied between the catalog and the pool.  One idea I received
that I've grown to really like is the idea of adding mirrored versions of holes
to the pool.  Some holes are already symmetrical and adding a mirrored version won't
make sense.  Any hole that's a dogleg or has asymmetric obstacles will be a great
candidate for mirroring, though. (See appendix for mirroring.)  So, the `pool`
is not just a filter *down* from the `catalog`, but possibly also an expansion.

After we have a `pool` for a seed, we need the course `layout`, which I'm defining
as the sequence of par values for holes 1 to 18.  There are some constraints that
we (probably) want to adhere to:

* courses typically have four par 3s and four par 5s in a par 72 course.
* courses typically have two par 3s and two par 5s in both the front and back nine.
* it's rare to have consecutive holes that are par 3
* it's rare to have consecutive holes that are par 5
* sometimes courses are par 70 or 71, but 72 is the most common

This last one should probably be a generation time setting and default should
always be 72.

I originally envisioned using a "gap-filling" algorithm to generate `layouts`.
This would be done by putting the 4s for the front nine in a sequence,
choosing two *different* gaps, placing the 3s there, now again choose two
*different* gaps from the new sequence, place the 5s there.  Repeat for the
back nine.

After a review pass of the first verison of this document with Claude, though,
I've decided that generating all distinct permutations and then filtering
out any that fail our constraints above is the best way to go.  For my
reference later, the permutations can be computed with an algorithm like this:

```
def distinct_permutations(counts):
    n = sum(counts.values())
    current = []
    result = []

    def backtrack():
        if len(current) == n:
            result.append(tuple(current))
            return
        for val in counts:
            if counts[val] > 0:
                counts[val] -= 1
                current.append(val)
                backtrack()
                current.pop()
                counts[val] += 1

    backtrack()
    return result

perms = distinct_permutations({4: 5, 3: 2, 5: 2})
```

At this point it's a matter of defining predicates that return true/false
based on the constraints above, and then running the permutation set
through the predicates.

This will generate a uniform distribution over the possibility space, which
is a nice bonus.

For par 70/71 variants, we change how many of each par value is in our `counts`
map.

Once we have our course `layout`, we fill each slot with a randomly chosen hole
from the `pool`.

I think this is enough to give us good results.  At some point we might also want to
"tag" holes as straight, dogleg, etc to prevent having too many of any type
back-to-back-to-back, but that doesn't feel necessary for version 1.0, and I'd
probably want to receive this as feedback before assuming it will be desired.

-----

The output of the randomization process is a `manifest`, which is structured
data, either json or yaml (distinction unimportant), that fully defines the
"important" properties of the final rom.  This includes the list of what each hole
is, but also other generation-time options like "Are players allowed to apply
the practice swing patch?", "Should the mercy tap-in patch be applied?",
"what constraints are placed on players' club bags?" as
well as what song is assigned to the course, and a seed value for the seeded wind
patch.

The next step in the process is taking the `manifest` and producing either a
`patch` or collection of some sort (list? tree?) of `patch` objects.

There's currently patches in the ./golf/core/patches directory of this repo,
and the *idea* is sound but I think some changes need to be made to the
exact architecture.  In short, I think that patches need to have a way to
"accept" ROM space allocation, and "provide" free space.  I will likely revisit
this in more detail in the coming days and expand in this section.

Either way, there should be code to take a `manifest` and generate a `patch`.
Worth noting, the `manifest` *alone* is **not** enough to generate a `patch`,
at least typically.  There will also be settings at "download" time for
players to specify their Player Name, to select what golf clubs they want
in their bag, to enable the practice swing patch, select their golfer sprite,
etc.  All of these decisions need to make their way into the `patch`.

The final step is to send this `patch` to the user, and the user's client,
which is likely a browser window, can apply the `patch` to a rom file.

The `patch` entities in the codebase now are Python classes.  The `patch` that
I think we should actually send the clients is either an .IPS patch file, or
a json document that contains the "instructions" needed to patch a vanilla rom.
(e.g., write bytes [whatever] to location wherever, repeat however many times).
In development/testing my tools for executing patches have applied the patches
to vanilla rom files and produced an output rom file.  Our "production" `patch`
processor should be able to do that, but also should be able to apply patches
in memory, keeping track of the changes requested, and then outputting a combined
.IPS or json document that consolidates all the byte changes from applying
all the patches.  Then this .IPS or json document gets sent down to the client,
and a small bit of WASM code does the mechanical patching of the user's rom file,
and triggers a download dialog to place the patched rom on the user's computer.

There is prior art here--this is how ALTTPR enables the player to "download" a rom.

------

The process of opening a manifest's page on the randomizer site and downloading
a patched rom will be gated behind the user providing vanilla rom file(s)
for NES Open Tournament Golf and optionally Mario Open Golf.  If the rom for
Mario Open is not provided, the user will be unable to generate roms that
contain the Mario Open holes.

Also in the spirit of respecting copyright, the vanilla course data will be
removed (and completely stripped) from this repository, and replaced with
a pushbutton, single-script command to rehydrate all of it from the vanilla
rom files.

We're going to work under the assumption that it is acceptable for the server
to have access to vanilla roms (my personal backups of the game cartridges
I own) as long as 1) the user's roms are verified and 2) a minimal amount
of vanilla code/data is transmitted across the wire.

**Note**: While we will attempt to keep the amount of vanilla data transmitted
to the players as small as possible, I am *not* planning on eliminating it
entirely.  This could be done by never sending *any* vanilla hole data
down as part of a patch and *only* sending "grab these bytes from rom A/B
then apply this transformation to them and put them at [location]."  However,
this is a significantly more complicated architecture, and I believe that
gating access to this data behind a user-supplied rom check is sufficient.

------

When a seed is generated, we should store the `manifest` in a database,
alongside an `id` of some format.  This `id` will be what's used to share
seeds with other players.  ALTTPR uses URLs of the form `https://alttpr.com/h/5yoAlr2rMm`.  We should do something similar.

The `manifest` should be the only thing persisted in the database, at least for now.
It should contain the outputs mentioned above as well as all the settings/decisions
that were specified at seed generation time.  They should be generally stable
across version releases of the randomizer.  At some point we might even want to
start maintaining "old" versions of patches to ensure that old seeds can always
be downloaded. (See Appendix C)

-----

One quality of this approach that I really feel is worth calling out:
storing the `manifest` in the database means that the generation process
can change freely between versions.  *Only the manifest-to-rom part
of the pipeline needs to be stable*.

## Appendix A: Mirroring & Transforms

Every tile in the tileset for NES Open (and therefore Mario Open) has its
mirror present as well.  Therefore, mirroring a hole is a fairly straightforward
operation.  It's possible that the game's compression algorithm is "tuned"
to the vanilla orientations, and that mirrored courses will compress *slightly*
worse, but this is a non-issue when generating only one course on a rom.

Mirroring is a specific case of the general concept of applying a "transform"
to a hole.  I can see more of these existing in the future, like randomizing
the sand traps/water hazards, or even procedurally generating the putting
surface slopes.

I still need to do more thinking about how this would be implemented in
a reproducible manner, but my current thought is to version all transforms
and have them all be deterministic based on inputs.  Then, if "Randomize
Putting Surfaces" is turned on, the manifest can include something like:
`{transforms: RandomizePuttingSurfaces@1:{seed: 12345}}`.

Maybe transforms are only applied at the hole level, and the above would be
attached to every hole, or maybe we could also have the concept of a
course-level transform which... just applies the transform to every hole.

## Appendix B: Stateful constraints, feasibility

Two approaches to solving the "Multi-round" or "League" seed problem (restated:
generate more than one course from the pool in a way that constrains duplicates)
are 1) Have the generation process take previous manifest IDs as inputs to be
aware of and 2) Give the generation process the ability to generate multiple
courses at the same time.

I'm leaning toward the second option, as I think it generalizes better, and
makes the "feasibility problem" more tractable.  The feasibility problem is
"what happens if the user selects enough filters to make the hole selection
process impossible?"  If we generate all the courses at the same time, the
randomizer can fail immediately and surface an error message rather than
failing on the nth course generation.  It also lets the generator potentially
swap holes around between the courses to make things fit in ways that a greedy
approach would not.

Either way, this work is specifically not in scope for v1.0.

## Appendix C: Catalog Immutability

In order to ensure that old manifests remain downloadable, the catalog's
contents should be considered immutable.  If a custom hole is in the
catalog and a tweak is made to it by the author that we want to 
incorporate, we leave the old version in the catalog, mark it as
"deprecated" so the generator never puts it in a new manifest, and
add the new version of the hole with a new ID.

As mentioned in Appendix A, `transform`s need to be versioned as well,
so really they can be considered part of the `catalog`, to some extent.