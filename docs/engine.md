# The engine

How a library and a topic tree become a city. Formats are in [format.md](format.md).

```
inputs ──> plan (directions, from the whole library) ──> world (the arrivals, one house at a time) ──> document (city.json)
```

| step | module | what it does |
|---|---|---|
| check | `bibliopolis.inputs` | reads the two files, checks them, puts the items in arrival order |
| cut | `bibliopolis.cut` | decides which topics are streets, from the house counts of the whole library |
| plan | `bibliopolis.plan` | pins the directions: ring-1 sectors, trunks, heavy paths, sides; and the rule `max` / `min` |
| world | `bibliopolis.world` | folds the arrivals into a world, one house at a time: the root zone, the roads, the splits, the ribs, the chronicle |
| document | `bibliopolis.document`, `bibliopolis.layout`, `bibliopolis.coast` | writes the world as the layout v4 document: records, measures, the coast, the stable text |
| glue | `bibliopolis.city`, `bibliopolis.cli` | `build_city()` and `python -m bibliopolis build` |

## Arrival and address

Items arrive in `added_at` order, ties by `id`. The n-th item to arrive has `seq` = n. The address of an item is its deepest topic (a root is depth 1,
ties go to the lower id); an item with no topic has none.

## The plan

The plan reads the whole library once, before any house stands, and pins what must be stable while the city grows: where the roads of the first ring go.
It has no radius and no coordinate; a road opens at the frontier of its trunk when its first house arrives.

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

**The rule.** `max` (40) and `min` (10), two whole numbers with `1 <= min <= max`.

## The world: grow

A world starts as the town hall plaza and nothing else. The arrivals are placed one at a time, in order; each is resolved, placed and checked before the
next, because the road of a house depends on the splits the houses before it caused.

1. **The root zone.** One street, `place:root` (label 根區), lies under the town hall: no road, no rib, nothing on the surface. Its houses stand on a grid of whole
   cells round the centre of the plaza, nearest cell first, in arrival order (the first 89 lie inside the plaza), and are marked `underground`. It takes
   every house no open road takes: the first houses, the houses of topics too thin for a road, the items with no topic.
2. **Roads.** A house stands on the nearest open road at or above its address; none: the root zone. A road covers the subtree of its key and, alone, each
   topic collapsed into it.
3. **The count.** A road's count is the houses standing on the road itself. The houses of the roads below it do not count (counting them would keep a
   parent over for ever).
4. **The split.** Before a house is placed on a road, the road's count is decided: if it would be more than `max`, the road's houses and the arriving one
   are grouped by the child topic of the road's key on each house's path (a house whose address is the key itself, or a collapsed topic, is in no group).
   The largest group of at least `min` houses (ties: the lower child id) opens a road of its own, below this one, and moves there. Then the houses
   that stay are packed again onto the first lots of the road in arrival order, and the new road is checked in turn (a group larger than `max` splits
   again at once). `seq` never changes.
5. **Where a road opens.** From the root zone only a ring-1 road of the plan can open (the wedges are pinned): the plan's street of the root topic, with
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

## The world: mirror

The topic tree is the street plan.

- Every topic an item is filed under (any entry of its `topics`, not only the one that is its address), and every topic above one, is a road from the start.
  The centre (the single root of a tree with one root) is not a road. An item still stands once, at its address, its deepest topic.
- Nothing is folded and nothing is collapsed: the plan has a street for each of those topics. A road with no lots of its own is a road with `lots: 0`: a topic
  with roads below it and no house of its own, or a topic an item is filed under while the house stands elsewhere. It has a place, an address and a level, and a
  ring-1 road of this kind has its wedge and its spoke. A topic that nothing is filed under, directly or below, is no road.
- There is no split: `min` has no effect (it stays in `world.districts`). A road that holds more than `max` houses is marked `over`, and the chronicle records
  when it became so. Over is a hint that a collection is crowded.
- An item with no topic, and an item whose address is the centre, stand in the root zone.
- Houses are placed exactly as in `grow`: arrival order, the lowest empty lot, continuation ribs.
- The roads that no house stands on or below get their street record when the world is completed (`bibliopolis.world.complete`, which `build_city` calls after the
  last arrival). `assign` alone never makes them, so that a world does not depend on how its arrivals were cut into calls: a record made early would open the
  trunks of the plan before their first house, nearer the plaza.

## Limits and known quirks

- **A tree with one root and houses on the root itself.** The plan gives such houses a ring-1 sector of their own, but no road ever opens there: a house whose
  address is the root stands in the root zone. The sector stays empty. (The engine of the private project this one was extracted from does the same.)
- **Time.** The work per house is small, except in the root zone and on a road that stays over: each arrival there looks at all the houses of the zone.
  9,000 houses that all stay under the town hall (1,000 topics of 9) take about 12 seconds; a library whose topics open roads takes a fraction of a second
  per 1,000 items.
- **Depth.** A tree deeper than 64 levels is refused.
- **Words in the document.** The labels of the plaza (`市政廳`, the town hall), the root zone (`根區`) and the road classes (`大道`, `路`, `巷`, `弄`) are
  zh-TW names that a viewer reads as constants; `format.md` gives their meaning.

## Where the tests are

| rule | test file |
|---|---|
| the root zone, the 41st house, packing, a split in the middle of a call, again at once, ribs, continuation, over, no merge back, chains, ring 1 | `tests/test_districts.py` |
| mirror, items filed under several topics, `complete` | `tests/test_mirror.py` |
| the cut and the plan: leaf and container streets, chains, the sectors of ring 1, the heavy path and the sides | `tests/test_plan.py` |
| angles, geometry, records, measures, the stable text, the coast | `tests/test_layout.py` |
| the two input files and their checks | `tests/test_inputs.py`, `tests/test_schema.py` |
| the pipeline and its summary (the streets that are over now) | `tests/test_city.py` |
| the command line, the same bytes in separate processes | `tests/test_cli.py` |
| the sample and what it shows; what the format page says about the sample | `tests/test_example.py`, `tests/test_format_page.py` |
| empty library, one root, many roots, a long chain | `tests/test_edges.py` |
| the README does not drift from the program | `tests/test_readme.py` |
| standard library only, Python 3.11 syntax | `tests/test_package.py` |

`tests/checks.py` holds the geometry checks (no overlap, every lot beside the lane of its own street, a road tree that starts at the plaza rim, no road
through a lot, every lot inside the wedge of its trunk) that the random worlds of `tests/support.py` run after every step.
