# The engine

How a library and a topic tree become a city. Formats are in [format.md](format.md).

```
inputs ──> plan (directions, from the whole library) ──> world (the arrivals, one house at a time) ──> document (city.json) ──> picture (city.svg)
```

| step | module | what it does |
|---|---|---|
| check | `bibliopolis.inputs` | reads the two files, checks them, puts the items in arrival order |
| cut | `bibliopolis.cut` | decides which topics are streets, from the house counts of the whole library |
| plan | `bibliopolis.plan` | pins the directions: ring-1 sectors, trunks, heavy paths, sides; the rule `max` / `min`; and the radius of the ring road |
| ring | `bibliopolis.ring` | the geometry of the ring road: gates, cells, radius, the position of a slot, the records of a lap |
| world | `bibliopolis.world` | folds the arrivals into a world, one house at a time: the ring road, the roads, the splits, the ribs, the chronicle |
| document | `bibliopolis.document`, `bibliopolis.layout`, `bibliopolis.coast` | writes the world as the layout v4 document: records, measures, the coast, the stable text |
| glue | `bibliopolis.city`, `bibliopolis.cli` | `build_city()`, `chronicle_lines()` and the commands `python3 -m bibliopolis build`, `picture` and `chronicle` |
| picture | `bibliopolis.picture` | draws a city document as SVG: one city, or several on one sheet (see "The pictures") |
| by hand | `bibliopolis.events`, `hand`, `journal`, `suggest`, `store` | a world made one act at a time from a log of events, through the same world and document steps: see [world.md](world.md) |
| numbers | `bibliopolis.canonical` | the one number form of every document the package writes: an integral value without a fraction |

## Arrival and address

Items arrive in `added_at` order, ties by `id`. The n-th item to arrive has `seq` = n. The address of an item is its deepest topic (a root is depth 1,
ties go to the lower id); an item with no topic has none.

**Replay.** `build_city(..., first=n)` and `build --first n` stop the build after the first `n` items of the arrival order. The plan is still cut from the whole
library, so the sectors of ring 1 do not move: the document is the city that the whole library makes, at an earlier moment, and its chronicle is the start of
the full chronicle. `first=0` is the town hall and the empty ring road; a number above the count of items places them all.

The last step of a build, `complete` (see "The world: mirror"), runs only when every item is placed. A `mirror` replay therefore shows the roads that the first
`n` items reached and the roads above them, and no other: a road that no house stands on or below is not there yet, and a road that is reached later opens, when
its first house arrives, where the full build opens it. Had a replay taken the last step as well, such a road would start nearer the plaza than it does in the
full city, because it would open at the frontier of its trunk before the houses that push the frontier outward have arrived.

What keeps its place, in both modes: the bearing of every road, and the point where each spoke starts. What does not: a spoke grows longer as houses arrive, and
a later split re-packs the houses of the road that split (not those of the ring road, whose houses stay), so a lot can stand elsewhere in the full city. A continuation rib that a later split empties is in the
earlier document and not in the later one.

## The plan

The plan reads the whole library once, before any house stands, and pins what must be stable while the city grows: where the roads of the first ring go.
It has no coordinate, and no radius but the ring road's; a road opens at the frontier of its trunk when its first house arrives.

**The cut.** Count the houses of each topic and below it (`H` = 20).

- a topic with `H` houses or fewer below it is a *leaf* street: everything below it is folded into it;
- a topic with more is a *container* street, which also owns the houses whose address is the topic itself;
- a container with no house of its own and exactly one child that has houses is a *chain*: it is collapsed into the address of its child, and its name
  is joined to the child's (`Humanities・History`);
- a topic with no house at or below it is empty and has no street;
- a street with more than `H` lots of its own gets overflow lanes of `H` lots (the plan only counts them: they give the street its weight);
- the weight of a street is the lots and reserved lots of it and below it: `1 + n + max(2, ceil(n / 4))` for a rib of `n` lots.

**Ring 1** is the topic roots (the children of the root when the tree has exactly one root). The circle is shared among them in proportion to their weight,
centred on north, in whole units of 1/100 degree. No sector is narrower than 14 degrees as long as the minimums fit in the circle, which they do for up to 25
ring-1 streets (25 x 14 = 350 degrees). With 26 or more they do not fit: the circle is then shared in proportion to the minimums, which are equal, so every
sector gets the same angle (360 / n degrees, less than 14) whatever its weight.

**Trunks.** Every ring-1 street is a trunk (a spoke through the plaza along the bisector of its wedge). Below it, a container street of weight 300 or more
under a trunk is a trunk too. Of the trunk children, the heaviest continues the spoke straight (the heavy path); the others take side wedges, alternately
on the lighter side (the left on a tie), the heaviest outermost. A side wedge is not narrower than 4 degrees and the central wedge not narrower than 8; when the
wedge of a trunk is too narrow for them, both minimums are scaled down together by the same factor. Every other street hangs on the bands of the nearest trunk
above it (its *carrier*).

**The rule.** `max` (40) and `min` (10), two whole numbers with `1 <= min <= max <= 10000` (the range of a world built by hand too: a larger number is refused before the radius of the ring road is computed, and no valid rule asks for a city too large to draw its coast).

**The ring.** `params.ring` = `{label, radius}`: the name of the ring road (`Knowledge`) and the lane radius `R` of its first lap. `R` is the least `8.5 + k`
(a whole `k >= 0`, 8.5 being the plaza radius, one bare cell and half a band) such that two things hold: the first lap holds `max` houses between its gates, and
the narrowest land of the `N` ring-1 sectors (a grown city: the whole wedge of a trunk, its spoke being its middle), `w` degrees wide, has at the ring's outer edge an arc of at least 3 cells, `(R + 1.5) * radians(w) >= 3`: one avenue's spoke
lane and a lot on each side. The gates are the axes of the ring-1 trunks: see "The ring road" below. A plan may pin a larger radius; a smaller one is refused when the
plan is read. A plan for a world built by hand ([world.md](world.md)) has no trunk at first, since the avenues open one at a time; it adds `sectors` (the `N` wedges `[lo, hi]` in degrees,
the sector of each direction) and `axes` (the bearing of each spoke, inside its sector, which need not be the middle of it): the gates are then the axes of all `N` directions from day
one, and `w` is the narrowest of the lands: twice the narrower side of a spoke inside its sector (`ring.land_of`).

## The world: grow

A world starts as the town hall plaza and the ring road round it, with no house. The arrivals are placed one at a time, in order; each is resolved, placed and
checked before the next, because the road of a house depends on the splits the houses before it caused.

1. **The ring road.** One street, `place:root` (label `Knowledge`), a closed circular road round the town hall, on the surface, with a lot on each side of its lane
   (see "The ring road" below). It takes every house no open road takes: the first houses, the houses of topics too thin for a road, the items with no topic.
2. **Roads.** A house stands on the nearest open road at or above its address; none: the ring road. A road covers the subtree of its key and, alone, each
   topic collapsed into it.
3. **The count.** A road's count is the houses standing on the road itself. The houses of the roads below it do not count (counting them would keep a
   parent over for ever).
4. **The split.** Before a house is placed on a road, the road's count is decided: if it would be more than `max`, the road's houses and the arriving one
   are grouped by the child topic of the road's key on each house's path (a house whose address is the key itself, or a collapsed topic, is in no group).
   The largest group of at least `min` houses (ties: the lower child id) opens a road of its own, below this one, and moves there. Then the houses
   that stay are packed again onto the first lots of the road in arrival order (on the ring road they stay where they are: only the lots of the group that leaves
   are freed, and the houses of the call that stay take the first free slots of the fill order), and the new road is checked in turn (a group larger than `max` splits
   again at once). `seq` never changes.
5. **Where a road opens.** From the ring road only a ring-1 road of the plan can open (the wedges are pinned): the plan's street of the root topic, with
   the chain the plan pins. Below a road, the new road is the deepest topic whose subtree still holds the whole group, and the topics between are its
   chain. One topic belongs to one road. A road is never opened above a road that is open already: that group stays where it is.
6. **Over.** If no group of `min` exists (or none can open), the road stays as it is and is marked `over: true`; the chronicle records the moment once. The mark
   goes when the road holds `max` or fewer houses again (a later split took some away).
7. **No merge back.** A road that holds fewer than `min` houses (the survivors of a split) stays open.
8. **Ribs.** A road's first rib is sized to the houses the road holds when it opens plus headroom: `min(max, even(n + max(4, ceil(n / 2))))`, `n` counting the
   arrivals of the call (the group that moved, the survivors, or 1). A road that has no empty lot opens a *continuation* rib, sized the same way on its
   current count (while the road is not over, its ribs hold at most `max` lots together). A continuation is the same road: the same label, level, class and
   address, and the street counts count the road once. A house takes the lowest empty lot of the first rib that has one.
9. **The chronicle.** Every split and every road that became over is an entry of `world.chronicle`, in order, with the arrival that caused it (see
   [format.md](format.md)).

## The ring road

The root of the road tree is a street like any other, round the town hall: shape `ring`, level 1, class 大道, `Knowledge`, the plaza as its parent. It stands from
day one, with its road (a closed circle from north, clockwise), and a house on it is a surface lot like any, counted, in the coast and in the measures. The
geometry is `bibliopolis.ring` (pure functions of numbers; the order of the operations matters to the last bit).

- **Gates.** Every direction an avenue can take leaves the ring through a gap, so that a later avenue never moves a house of the ring. G1 is the axes of the plan's
  ring-1 trunks (each the middle of its wedge, mod 360, to three decimals, sorted, without repeats; a plan that names the spoke axes of all its directions, `params.ring.axes`, has
  those instead, and no ring-1 trunk adds to them: one that a road left behind is no gate); G2 is G1 and the axes of the side trunks (a lap beyond the first can lie across the spoke of a side line). A gate is cut in both rows: outward it is where the avenue leaves, inward it is how the town hall reaches the ring.
- **Cells and slots.** The lane is cut into cells one long, from north clockwise, each starting where the one before ended, skipping a stretch of one round every
  gate. A cell holds two lots: slot `s` is in cell `s // 2`, the inner lot (radius `R - 1`, facing out) when `s` is even, the outer lot (radius `R + 1`, facing
  in) when it is odd. So the slots of a lap are listed by angle from north clockwise, the two lots of a cell sharing an angle (slot `2c` the inner lot of cell `c`, slot `2c + 1` its outer lot: a numbering only, the fill order below takes both rows from the start). There are no
  empty-lot records on the ring: the cell of a slot is a function of the slot.
- **Fill order.** The `n = 2C` slots of a lap are taken in the order of the scaled radical inverse (`ring_fill_order(n)`): for `j = 0 .. 2^m - 1`, `2^m` the least power of two
  that is at least `n`, the slot `floor(rev_m(j) * n / 2^m)` (integer arithmetic: `(rev_m(j) * n) >> m`), `rev_m` reading the `m` bits of `j` backwards, and a slot counts the first
  time it comes up (the map is onto `0 .. n - 1`, so every slot is taken once). The first house stands at north, the second half way round (slot `n // 2`, whatever `n` is), the next
  two at the quarters, then the eighths, and so on (a lap of 122 slots: 0, 61, 30, 91, 15, 76, 45, 106, 7, ...; of 58: 0, 29, 14, 43, 7, 36, ...): the first `2^i` slots of the order cut the
  lap into `2^i` stretches of `floor(n / 2^i)` or `ceil(n / 2^i)` slots, so the houses stand spread round the whole ring whatever their number. A house that comes to the ring takes the **first free slot in that fixed order** of the lowest lap that has one; a slot that a split or a move
  freed is taken again in the same order; survivors keep their slots. Every lap alike, each with its own `n`. The spread, as tested: after `k` houses the largest gap between
  neighbouring slots round the lap is at most `2 * n / k + 1` slots, so at most `n / k + 1` cells (the cell index, the gates left out); `tests/test_ring.py` takes it for every lap
  size up to 400 slots and for the laps of the sample plans.
- **Avenues.** A ring-1 spoke starts at the outer edge of the ring, `R + 0.5`; its first band lies at `R + 3` or farther (back to back with the outer row of the
  ring where its wedge allows it), and a street along its spoke starts at `R + 1.5` or later.
- **Laps.** When every slot of the laps that stand is taken and one more house comes to the ring, a lap opens: a street `place:root:lap:<k>` that continues the ring
  (`lane_of`, `continued`, the same label and address), with its own road. Its radius is `ceil3(max(R_k + 3, F + 1.5))`, `F` the largest frontier of the lines (0
  when none is open): back to back with the lap before while no avenue is open, beyond everything that stands when one is. Every lap is a span of every line, so
  no band, no street along a spoke and no branch circle lies across a lap; a road crosses a lap at its gates. A lap no house stands on any more stays in the
  world and takes houses before another lap opens; the document leaves it out.
- **The road.** The road of a lap is a closed polyline from north, clockwise, whose last point is its first: `n` chords, `n` the least whole multiple of 72 with
  `R * (1 - cos(pi / n)) <= 0.05` (a chord lies at most 0.05 cell inside the lane), the point `k` at the bearing `360 * k / n`. So 73 points up to `R = 52.5`, 289 at `R = 800`; the
  road of a far lap does not cut across its inner row of lots. Every other arc has the same bound with its own count (`arc_chords`, [format.md](format.md)).
- **The walk** from the plaza to a house on the ring goes out through the nearest gate of G1 to the lane, then along the lane: `R + R * radians(d)`, `d` the angle
  between the house and that gate.
- **Stability.** A split from the ring frees the lots of the group that leaves and nothing else: the houses that stay keep their lots. Every other road packs its
  survivors onto its first lots, as before.

## The world: mirror

The topic tree is the street plan.

- Every topic an item is filed under (any entry of its `topics`, not only the one that is its address), and every topic above one, is a road from the start.
  The centre (the single root of a tree with one root) is not a road. An item still stands once, at its address, its deepest topic.
- Nothing is folded and nothing is collapsed: the plan has a street for each of those topics. A road with no lots of its own is a road with `lots: 0`: a topic
  with roads below it and no house of its own, or a topic an item is filed under while the house stands elsewhere. It has a place, an address and a level, and a
  ring-1 road of this kind has its wedge and its spoke. A topic that nothing is filed under, directly or below, is no road.
- There is no split: `min` has no effect (it stays in `world.districts`). A road that holds more than `max` houses is marked `over`, and the chronicle records
  when it became so. Over is a hint that a collection is crowded.
- An item with no topic, and an item whose address is the centre, stand on the ring road.
- Houses are placed exactly as in `grow`: arrival order, the lowest empty lot, continuation ribs.
- A mirror road that no house stands on or below (a topic an item is filed under while the house stands elsewhere) has no street record until the world is
  completed (`bibliopolis.world.complete`): it appears in the document only then. `build_city`, and so the command line, completes the world after the last
  arrival, and a replay (`first`, see above) stops before that; code that calls `assign` by itself gets the world without those roads. `complete` is a step of
  its own, so that a world does not depend on how its arrivals were cut into calls: a record made early would open the trunks of the plan before their first
  house, nearer the plaza.

## The pictures

`bibliopolis.picture` draws a city document, and nothing else: it never reads the library. Units are cells, north is up.

- **One city** (`render`, the command `picture`): the coast, the houses, the roads in four classes (大道 avenue, 路 road, 巷 lane, 弄 alley), the plaza with its
  name, a title, a line of numbers and a legend.
- **The ring road is drawn like any road,** a closed circle of class 大道 (every lap of it), and its houses like any house, as the polar cells of the lane of their lap
  on both sides, in a colour of their own (the ring is no sector of ring 1). Its name stands at its north point.
- **A sector is named once it has a road.** The plan pins every sector of ring 1 before the first house, but a picture shows only those with a road, so a
  city of 40 houses is the town hall and the ring road. Each name stands just beyond the farthest house of its sector, and farther out, with a line, where it
  would sit on another name.
- **One sheet** (`sheet`): several cities on the same frame at the same scale, so that growth shows as growth. The frame leaves room for every name of every
  city. A road is never drawn thicker than at 3.5 pixels to the cell, so a small city is not made of fat lines. Coordinates have one decimal on a sheet and two
  in a single picture, which keeps a sheet small (the sheets of the README are under 100 KB, and a test says so).
- The same document gives the same bytes. A character that XML 1.0 cannot carry (a control character) in a name is replaced, so a picture is always valid XML.

The pictures of the README (`docs/images/`) are made by `examples/make_pictures.py`: `growth.svg` is the sample in `grow` mode after 40, 41, 150 and 600 items
(`first=n`), `modes.svg` is the sample in both modes, `concept.svg` is a tiny invented city with labels laid over it at places the document gives. A test makes
them again and compares them with the committed files byte for byte.

## Limits and known quirks

- **A tree with one root and houses on the root itself.** The plan gives such houses a ring-1 sector of their own, but no road ever opens there: a house whose
  address is the root stands on the ring road. The sector stays empty. (The engine of the private project this one was extracted from does the same.)
- **Time.** The work per house is small, except on the ring road and on a road that stays over: each arrival there looks at all the houses of the road.
  9,000 houses that all stay on the ring road (1,000 topics of 9) take about 12 seconds; a library whose topics open roads takes a fraction of a second
  per 1,000 items.
- **Depth.** A tree deeper than 64 levels is refused.
- **Words in the document.** The label of the plaza (`市政廳`, the town hall) and the road classes (`大道`, `路`, `巷`, `弄`) are zh-TW names that a viewer reads
  as constants; `format.md` gives their meaning. (The ring road is named `Knowledge`, a name of the plan.)

## Where the tests are

| rule | test file |
|---|---|
| the 41st house, packing, a split in the middle of a call, again at once, ribs, continuation, over, no merge back, chains, ring 1 | `tests/test_districts.py` |
| the ring road: the radius, the gates, the cells of a lap, the fill order and its spread, day one, the first forty houses, the survivors of a split, the avenues, the laps, the walks | `tests/test_ring.py` |
| mirror, items filed under several topics, `complete` | `tests/test_mirror.py` |
| the cut and the plan: leaf and container streets, chains, the sectors of ring 1, the heavy path and the sides | `tests/test_plan.py` |
| angles, geometry, records, measures, the stable text, the coast | `tests/test_layout.py` |
| the budget of the grid of the coast, the range of the rule that keeps a valid rule drawable, a city too large to draw, the flood of the sea (its order, and its memory in a child process under a limit) | `tests/test_budget.py` |
| the geometry checks of the tests themselves: an overlap and a road through a lot are found at every radius, and a far arc is drawn through lots by one chord and not by the chord rule | `tests/test_checks.py` |
| the two input files and their checks | `tests/test_inputs.py`, `tests/test_schema.py` |
| reading a city file: what is accepted, what is refused and where, and that no single wrong field gets past the reader to crash or loop `picture` or `chronicle` | `tests/test_cityfile.py`, `tests/test_cli.py` |
| the pipeline, its summary (the streets that are over now), the basics of the replay with `first`, the chronicle as sentences | `tests/test_city.py` |
| a replay: what keeps its place and what does not, what a mirror replay leaves out, a case that crosses `trunk_min` | `tests/test_replay.py` |
| the command line (`build`, `picture`, `chronicle`), the same bytes in separate processes | `tests/test_cli.py` |
| the picture: what is drawn and left out, the frame of a sheet, valid XML | `tests/test_picture.py` |
| the pictures of the README are what the script makes, byte for byte | `tests/test_images.py` |
| the sample and what it shows; what the format page says about the sample | `tests/test_example.py`, `tests/test_format_page.py` |
| empty library, one root, many roots, a long chain | `tests/test_edges.py` |
| the README does not drift from the program: its commands run, the lines and pictures it shows are real | `tests/test_readme.py` |
| standard library only, Python 3.11 syntax (also the f-strings that only 3.12 can read) | `tests/test_package.py` |
| the world built by hand, its files and its command | the table at the end of [world.md](world.md) |
| the number form, and the sha256 of the sample cities | `tests/test_canonical.py` |

`tests/checks.py` holds the geometry checks (no overlap, every lot beside the lane of its own street, a road tree that starts at the plaza rim, no road
through a lot, every lot inside the wedge of its trunk, and for the ring road its cells re-derived apart from the engine) that the random worlds of
`tests/support.py` run after every step.
