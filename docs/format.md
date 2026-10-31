# Formats

Two JSON files go in, one comes out.

```
python3 -m bibliopolis build --library library.json --tree tree.json --mode grow --out city.json
```

JSON Schema files for the two inputs are in `schema/`. A schema cannot say everything the program checks; the checks are listed below.
`examples/` holds a sample of each (made by `examples/make_example.py`).

## The library

```json
{"items": [
  {"id": "item-0001", "title": "A survey of adaptive networks", "authors": ["B. Hansen"], "year": 2024, "doi": "10.0000/ex.0001",
   "added_at": "2026-04-06", "type": "article", "tags": ["to-read"], "topics": ["networks"]}
]}
```

| field | type | meaning |
|---|---|---|
| `id` | string | unique in the library; it is the id of the house. No control characters. |
| `title` | string | may be empty. Not read by the engine; kept in your library file. |
| `authors` | list of strings | not read by the engine. |
| `year` | integer or null | the year of publication. Not read by the engine. |
| `doi` | string or null, optional | not read by the engine. A string must not be empty. |
| `added_at` | string | ISO 8601: a date (`2026-04-06`), or a date and time with or without an offset (`2026-04-06T09:30:00+08:00`, `2026-04-06 09:30:00`). A time without an offset is read as UTC. Items arrive in this order, ties by `id` in code-point order. |
| `type` | string, not empty | the kind of document: `article`, `review`, `editorial`, `letter`, `news`, `erratum`, `retraction notice`, and so on. Not read by the engine. |
| `tags` | list of strings | free tags: the residents of the house. Not read by the engine. |
| `topics` | list of strings | ids of nodes of the tree: the topics the item is filed under. The address of the house is the deepest of the topics outside the root bucket of the tree (a root is depth 1; ties: the lower id), and the house stands once, there. In `mirror` mode every topic outside the root bucket that is listed is also a road (see below). With no such topic (the list is empty, or names only nodes of the root bucket, below) the house stands on the ring road, round the town hall. |

| `annex_of` | string, optional | the id of another item of the library that this item exists for (a letter about an article, say): this item is no house of its own, and its `topics` give it no address. That other item is a house: it has no `annex_of` itself. Comes with `annex_form`, or neither. |
| `annex_form` | `wing` or `mailbox`, optional | how this item stands beside the house it exists for: a wing on its side wall, or a mailbox at its gate. The engine reads no `type`: the one who writes the library says which form an item takes. |

The order of the items in the file does not matter: only `added_at` and `id` do. Other keys are ignored.

## The topic tree

```json
{"nodes": [
  {"id": "computing", "label": "Computing", "parent": null},
  {"id": "systems", "label": "Systems", "parent": "computing"},
  {"id": "networks", "label": "Networks", "parent": "systems"}
]}
```

| field | type | meaning |
|---|---|---|
| `id` | string, not empty | unique in the tree; no control characters; not of the form `lane:<anything>:<number>` (a continuation rib of an earlier version had reserved ids of that form; the form stays refused). |
| `label` | string, not empty | the name of the road. |
| `parent` | string or null | the id of the parent node; null for a root. |

A tree may have several roots. A tree with exactly one root has that root as its centre: the root is the town hall, its children are the
ring-1 roads, and a house whose address is the root itself stands on the ring road.

The tree document may also name a **root bucket**, the home of what you have not sorted yet (an inbox, a pile to read, a tag you give to everything new):

```json
{"nodes": [
  {"id": "computing", "label": "Computing", "parent": null},
  {"id": "systems", "label": "Systems", "parent": "computing"},
  {"id": "networks", "label": "Networks", "parent": "systems"},
  {"id": "inbox", "label": "To sort", "parent": null},
  {"id": "maybe-ai", "label": "Maybe AI", "parent": "inbox"}
], "bucket": "inbox"}
```

| key | type | meaning |
|---|---|---|
| `bucket` | string or null, optional | the id of a node that is a root. That node and everything below it are not places of the tree: they get no road, no sector and no mirror road, however many items are filed there, and a tree with one real root plus a bucket still has that root for its centre. They are nodes of the file all the same, so an item may name any of them in `topics`. An item whose only topics are in the bucket stands on the ring road, as an item with no topic does. An item that is also filed under a topic outside the bucket stands at that topic (the deepest one, as always). Null or no key: no bucket. |

The bucket is called what you call it: the engine knows no name for it. Houses of the bucket never form a group that opens a road, so a ring road that holds only them is marked
`over` and goes on as a lap when it is full (see [engine.md](engine.md)); the roads of the topics they are later filed under open as usual.

## What the program checks beyond the schemas

- every `id` of the library is used once, every `id` of the tree is used once;
- every `topics` entry is the id of a node of the tree (a topic the tree does not have is a mistake, not a house placed somewhere; the nodes of the bucket are nodes);
- `annex_of` and `annex_form` come together or not at all; `annex_form` is `wing` or `mailbox`; `annex_of` is the id of another item of the library (not the item itself), and that item has no
  `annex_of` itself: an item is of a house, never of another item that exists for one;
- `bucket`, if it is given, is the id of a node, and that node is a root;
- every `parent` is the id of a node, the parents lead to a root (no cycle), and no branch is deeper than 64 levels;
- `added_at` parses;
- every string can be written as UTF-8.

Every problem found is reported at once (up to 20), each with the place it was found at, for example
`library.items[58] ('item-0059').topics[0]: 'nowhere' is not the id of a node of the tree`. The command exits with status 2 and writes nothing.

## The city

`city.json` is the layout v4 document: the geometry and the structure of the city. It holds no title, author, year, DOI, type or tag: those stay in your
library file, and the house of an item is `place:article:<id>`.

Two commands read it: `python3 -m bibliopolis picture --city city.json --out city.svg` draws it, and `python3 -m bibliopolis chronicle --city city.json`
prints its chronicle as sentences. They refuse a file that is not a city (a library or a tree, say), and a city in which a field they read is missing or of the
wrong type, a street or a house points at a place that is not there, the parents of a street lead round in a circle instead of to the plaza, or a house on the
surface stands under a street that is no sector of ring 1. Each problem is named with its place (`city.places['place:tag:a'].parent: ...`), up to 20 at a time.
The geometry is not re-checked: a city edited by hand can still be wrong in ways the commands do not see.

The text is stable: header fields pretty-printed, then one road, one place per line. The same input gives the same bytes on every run (the angles are
integers of 1/100 degree, the coordinates are rounded to three decimals, everything is written in sorted order). The tests build the sample in separate
processes with different hash seeds and compare the bytes.

Coordinates: cells, `x` east, `z` south, the centre of the town hall plaza is the origin. Angles: degrees clockwise from north.

Numbers are written in one form: an integral value has no fraction (`40`, not `40.0`), any other value is its shortest text (`12.345`). A city that `python3 -m bibliopolis world fold`
writes from a world built by hand is the same document, with `world.mode` `hand` and more kinds of chronicle entry: see [world.md](world.md).

### Top level

| key | holds |
|---|---|
| `schema_version`, `layout_version` | `"4"`, `"v4"` |
| `centre` | `{place, tag, radius, label}`: the town hall plaza (`tag` is the single root of the tree, or null). Its label is `市政廳` (town hall). |
| `generator` | `{tool, version, input}` |
| `composition` | the counts: see below |
| `geometry`, `kinds`, `roads_kinds` | notes in words on the units and on every kind of place and road |
| `counts` | places by kind (`annex` is there only when the city has an annex) |
| `world` | the rule, the mode and the chronicle: see below |
| `roads` | the road network, by road id |
| `coast` | `{buffer, tolerance, polygons}`: the outline of the land. Each polygon is a list of `[x, z]` corners. It is drawn on a grid of one cell, and a city whose grid would hold more than 8388608 cells (its farthest lot or road more than 1441 cells from the town hall) has none: it is refused with the id `city_too_large` ([world.md](world.md), "A city is too large to draw"). |
| `places` | every place, by place id |

### `composition`

`home_max`, `trunk_min` (the numbers the plan was cut with), `articles` = `buildings` (the houses in the document and its annexes: every article is one building), `reserved_lots`
(empty lots in the document: always 0 here), `ring1` (every ring-1 sector: `{place, label, weight, from, to, span}`, degrees; a world built by hand ([world.md](world.md)) adds `axis`, the bearing of the spoke, which lies in the sector and need not be its middle), `streets`
(`{total, containers, leaves, trunks, groups, spokes, lanes, continuations, ring}`: a road is one record, and the ring road counts as one
street, its laps being the only continuations (a document of version 0.3 or before may have more: a continuation rib of a road); `ring` is the number of street records of shape `ring`, laps included) and `measure` (`lots`, `land_area`, `max_radius`, the
walk from the plaza to the doors, `streets_by_class`, `ring_lots`, the houses on the ring road, ...). Every house is on the surface, and the measures count them all. `lots` counts
the houses, which are the lots, and so does `world.houses`: an annex has no lot.

### `world`

| key | holds |
|---|---|
| `format`, `zoning_version`, `mode` | `"world/1"`, the name of the rule set, and `"grow"` or `"mirror"` |
| `seq` | the number of items that arrived (an item that exists for another item arrives too) |
| `houses`, `unbuilt` | the houses in the document (the lots), the empty lots the world holds |
| `districts` | the rule: `{max, min, extract: "largest", count: "direct"}` |
| `chronicle` | what happened, in order: see below |
| `notes` | the meaning of the fields in words |

A **chronicle** entry is a split, an over, or (in a city that has annexes) an annex, numbered `n` = 1, 2, ... in the order they happened:

```json
{"n": 1, "event_id": null, "seq": 41, "trigger": "arrival", "from": "place:root", "to": "place:tag:computing", "label": "Computing",
 "houses": ["item-0123", "..."], "count_before": 41, "count_after": 26, "at": "2019-06-26T19:14:02Z"}
{"n": 19, "event_id": null, "seq": 575, "trigger": "arrival", "over": "place:tag:networks", "count": 41, "at": "2026-06-02"}
```

```json
{"n": 20, "event_id": null, "seq": 601, "trigger": "arrival", "annex": "item-0601", "parent": "item-0042", "form": "wing", "at": "2026-06-03"}
```

`seq` is the arrival number of the item that caused it, `at` its `added_at` as written in the library, `houses` the ids of the items that moved,
`count_before` and `count_after` the houses on the road `from` before the split and after it. `event_id` is always null here and `trigger` always
`"arrival"` (the keys are the ones a city with a record of events fills in). An `annex` entry says that the item `annex` stands beside its house `parent` as a `form`
(see "An item that exists for another item" below). It is caused by the arrival of the item itself when its house has arrived, and else by the arrival of the house, which
the annex waited for.

### `places`

Every place has a `kind`.

- **`plaza`**: `{label, position, radius}`.
- **`lot`**: one house. `{article, parent, order, slot, position, facing, seq}`. `article` is the item id, `parent` the rib it stands in (its road; for a house on the ring road, its lap), `slot` its number in the rib (the lowest empty one is used first; on a lap of the ring road, the first empty one in the fill order of the lap, see [engine.md](engine.md), "The ring road"), `seq` the arrival number,
  `facing` a bearing in degrees.
- **`reserved`**: an empty lot (only in a document made with reserved lots; `build` does not).
- **`annex`**: an item that exists for another item (below). `{article, parent, form, rank, seq}`. It is no house: it has no lot, no position, no slot and no address, and it stands
  where its house stands. `article` is the item id (the place is `place:article:<item id>`, as for a house), `parent` the place of the lot of the house it stands beside, `form` is
  `wing` (against the side wall of the house) or `mailbox` (at its gate), `rank` numbers the annexes of one house and form in the order they arrived, 1 first, and `seq` is its
  arrival number.
- **`street`**: a road, in one of these `shape`s:
  - `trunk`: a road with a spoke of its own (every ring-1 road, and below it a heavy container road): `wedge`, `axis`, `s0`, `s_end`, `open`, `bands`, `road`, `lane`, `heavy`.
  - `group`: a road with roads below it; its own houses (if any) stand on the bands of its carrier trunk.
  - `rib`: a road with no road below it, a stretch of a band of its carrier trunk (`carrier`), or of the spoke.
  - `ring`: the ring road `place:root` (label `Knowledge`), a closed circular road round the plaza, and its laps (below). It is in the document from day one,
    empty or not. It has no rib: its houses are the polar cells of its lane, one on each side. `{ring: {lap, radius, slots, gaps}}`: the number of the lap (1 for
    `place:root`), the radius of its lane (a number of at least 1, as `s` of a rib on a band: a house stands one cell from its lane, and the reader refuses a smaller radius, with which a picture would divide by nothing), how many houses it holds (two to a cell, a cell one long along the lane) and the bearings of the gates its cells keep
    clear (the directions the avenues leave by). A lot of the ring has `slot` s in cell s // 2 of its lap: the inner row at the lane radius less 1 when s is even,
    the outer row at the lane radius plus 1 when odd. When the ring is full it goes on as a **lap**: a street of shape `ring` with `lane_of: "place:root"`,
    `ordinal`, `continued: true` and the ring's label, address and class, outside the lane of the lap before it, in `lanes` of the ring.

  A street has `tag` (the topic id; the ring road has none), `address` (the labels from ring 1 down to this road), `level` (1 for ring 1),
  `class` (`大道` ring 1 = avenue, `路` ring 2 = road, `巷` ring 3 = lane, `弄` ring 4 and deeper = alley), `parent` (the street above, or the plaza),
  `lots` and `reserved`. `label` is there when it differs from the tree's label (a road with a collapsed
  chain: `"Humanities・History"`), else `address[-1]` is the name. `collapsed` lists the topics collapsed into the road, top first. `over: true` marks a road
  that holds more than `max` houses and cannot split. `rib` is `{trunk, band, side, x0, x1, s, slots}` (`band` is null when the rib lies along the spoke).
  A road has one rib, which grows at its end when it is full (engine.md, "Growth in place"); `lanes` is the key of the ring road alone, which lists its laps. (A document made by version 0.3
  or before may give a road `lanes`: continuation ribs, records with `lane_of`, `ordinal`, `continued: true` and the same label, level, class and address as the road. The reader takes them, and
  a road with several records is read as before: the houses standing on it are the `lots` of its record plus the `lots` of every record in its `lanes`.)

  **`lots` and `reserved` count the rib that the record carries**: the houses that stand in, and the empty lots that are left in, it. **The houses standing on a road are the `lots` of its
  record, and not the houses of the roads below it.** In the sample, Ecology is a record with `lots: 35`, `reserved: 5` and a rib of 40 lots: 35 houses.

  **A road with no lots of its own** has `lots: 0`, `reserved: 0` and no `rib`. In `grow` mode it is a road whose houses have all moved to the roads below it, and none has arrived since. In
  `mirror` mode it is also a topic that has roads below it and no house of its own, or a topic an item is filed under while that item's house stands elsewhere.
  It is a road all the same: it has a place, an address, a level and a parent, and a ring-1 road of this kind has its wedge and its spoke.

### `roads`

Each road has `street`, `kind`, `class`, `parent` (the road it hangs on), `at` (where, as a distance along the parent), `length` and `points` (a polyline).

- `spoke`: a straight road through the plaza along the bisector of a wedge (`axis`, `s0`, `s_end`, `open`, `wedge`);
- `arc`: a connector from a trunk to the axis of a side wedge (`side`);
- `lane`: an arc around the plaza across a trunk, one stretch per street (`trunk`, `band`, `side`, `off`, `radius`, `bearings`);
- `ring`: the lane of the ring road or of one of its laps, a closed circle round the plaza from north clockwise (the last point is the first), with no parent (`radius`).

The polyline of an arc (`lane`, `arc`) from bearing `a` to `b` on a circle of radius `R` has `n = max(ceil(|b - a| / 5), ceil(radians(|b - a|) / (2 * acos(1 - 0.05 / R))))` chords of equal angle, the point `k` at the bearing `a + (b - a) * k / n` (`bibliopolis.layout.arc_chords`): a chord every 5 degrees at most, and more where a chord of 5 degrees would lie more than 0.05 cell inside its circle, which is beyond the radius 52.53. A road drawn along a lane stays within 0.05 cell of it at any radius, and a city whose arcs all lie within that radius has the points it always had. The ring road keeps a count of its own, a whole multiple of 72 chords with the same bound.

The walk from the plaza to a door is the sum of the `at` of its road and its ancestors, and the distance along its own lane. The spokes of ring 1 start at the outer
edge of the ring road (`s0`); the walk to a house on the ring goes out through the nearest gate to its lane, then along it.

## An item that exists for another item

Some items exist only for another item: a letter about one article, say. A library says so with `annex_of` and `annex_form`, and the engine does not guess it from `type`.
Such an item is an *annex*. It has an arrival number like any item, but it is no house: no lot, no road, no address, so it takes no room on a road, weighs nothing in the cut and,
in `mirror` mode, makes no road of the topics it is filed under. It stands where its house stands, as a wing against the side wall or as a mailbox at the gate, and the city
document has a place of kind `annex` for it (above). A road that holds 40 houses holds them whatever annexes they have, and the number of articles of a city is its houses and its
annexes. An annex that arrives before its house waits for it, and a replay that stops before the house has no record of the annex. The rules are in [engine.md](engine.md), "Annexes".

## Two modes

`grow` builds the city the way a collection grows: the roads open as the houses arrive. `mirror` builds the street plan of the tree you give it: a road for
every topic an item is filed under (every entry of its `topics`) and for every topic above one, while each house still stands once, at its address. Both read
the same two files and write the same kind of document; `world.mode` says which. The rules are in [engine.md](engine.md).
