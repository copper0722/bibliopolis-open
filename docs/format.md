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
| `topics` | list of strings | ids of nodes of the tree: the topics the item is filed under. The address of the house is the deepest of them (a root is depth 1; ties: the lower id), and the house stands once, there. In `mirror` mode every topic listed is also a road (see below). Empty: the house stands in the root zone, under the town hall. |

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
| `id` | string, not empty | unique in the tree; no control characters; not of the form `lane:<anything>:<number>` (it would share ids with a continuation rib). |
| `label` | string, not empty | the name of the road. |
| `parent` | string or null | the id of the parent node; null for a root. |

A tree may have several roots. A tree with exactly one root has that root as its centre: the root is the town hall, its children are the
ring-1 roads, and a house whose address is the root itself stands on the ring road.

## What the program checks beyond the schemas

- every `id` of the library is used once, every `id` of the tree is used once;
- every `topics` entry is the id of a node of the tree (a topic the tree does not have is a mistake, not a house placed somewhere);
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
| `counts` | places by kind |
| `world` | the rule, the mode and the chronicle: see below |
| `roads` | the road network, by road id |
| `coast` | `{buffer, tolerance, polygons}`: the outline of the land. Each polygon is a list of `[x, z]` corners. |
| `places` | every place, by place id |

### `composition`

`home_max`, `trunk_min` (the numbers the plan was cut with), `articles` = `buildings` (the houses in the document), `reserved_lots`
(empty lots in the document: always 0 here), `ring1` (every ring-1 sector: `{place, label, weight, from, to, span}`, degrees; a world built by hand ([world.md](world.md)) adds `axis`, the bearing of the spoke, which lies in the sector and need not be its middle), `streets`
(`{total, containers, leaves, trunks, groups, spokes, lanes, continuations, ring}`: a road with continuation ribs is counted once, and the ring road counts as one
street, its laps being continuations; `ring` is the number of street records of shape `ring`, laps included) and `measure` (`lots`, `land_area`, `max_radius`, the
walk from the plaza to the doors, `streets_by_class`, `ring_lots`, the houses on the ring road, ...). Every house is on the surface, and the measures count them all.

### `world`

| key | holds |
|---|---|
| `format`, `zoning_version`, `mode` | `"world/1"`, the name of the rule set, and `"grow"` or `"mirror"` |
| `seq` | the number of items that arrived |
| `houses`, `unbuilt` | the houses in the document, the empty lots the world holds |
| `districts` | the rule: `{max, min, extract: "largest", count: "direct"}` |
| `chronicle` | what happened, in order: see below |
| `notes` | the meaning of the fields in words |

A **chronicle** entry is either a split or an over, numbered `n` = 1, 2, ... in the order they happened:

```json
{"n": 1, "event_id": null, "seq": 41, "trigger": "arrival", "from": "place:root", "to": "place:tag:computing", "label": "Computing",
 "houses": ["item-0123", "..."], "count_before": 41, "count_after": 26, "at": "2019-06-26T19:14:02Z"}
{"n": 19, "event_id": null, "seq": 575, "trigger": "arrival", "over": "place:tag:networks", "count": 41, "at": "2026-06-02"}
```

`seq` is the arrival number of the item that caused it, `at` its `added_at` as written in the library, `houses` the ids of the items that moved,
`count_before` and `count_after` the houses on the road `from` before the split and after it. `event_id` is always null here and `trigger` always
`"arrival"` (the keys are the ones a city with a record of events fills in).

### `places`

Every place has a `kind`.

- **`plaza`**: `{label, position, radius}`.
- **`lot`**: one house. `{article, parent, order, slot, position, facing, seq}`. `article` is the item id, `parent` the rib it stands in (its road, or a
  continuation of it; for a house on the ring road, its lap), `slot` its number in the rib (the lowest empty one is used first), `seq` the arrival number,
  `facing` a bearing in degrees.
- **`reserved`**: an empty lot (only in a document made with reserved lots; `build` does not).
- **`street`**: a road, in one of these `shape`s:
  - `trunk`: a road with a spoke of its own (every ring-1 road, and below it a heavy container road): `wedge`, `axis`, `s0`, `s_end`, `open`, `bands`, `road`, `lane`, `heavy`.
  - `group`: a road with roads below it; its own houses (if any) stand on the bands of its carrier trunk.
  - `rib`: a road with no road below it, a stretch of a band of its carrier trunk (`carrier`), or of the spoke.
  - `ring`: the ring road `place:root` (label `Knowledge`), a closed circular road round the plaza, and its laps (below). It is in the document from day one,
    empty or not. It has no rib: its houses are the polar cells of its lane, one on each side. `{ring: {lap, radius, slots, gaps}}`: the number of the lap (1 for
    `place:root`), the radius of its lane, how many houses it holds (two to a cell, a cell one long along the lane) and the bearings of the gates its cells keep
    clear (the directions the avenues leave by). A lot of the ring has `slot` s in cell s // 2 of its lap: the inner row at the lane radius less 1 when s is even,
    the outer row at the lane radius plus 1 when odd. When the ring is full it goes on as a **lap**: a street of shape `ring` with `lane_of: "place:root"`,
    `ordinal`, `continued: true` and the ring's label, address and class, outside the lane of the lap before it, in `lanes` of the ring.

  A street has `tag` (the topic id; the ring road has none), `address` (the labels from ring 1 down to this road), `level` (1 for ring 1),
  `class` (`大道` ring 1 = avenue, `路` ring 2 = road, `巷` ring 3 = lane, `弄` ring 4 and deeper = alley), `parent` (the street above, or the plaza),
  `lots` and `reserved`. `label` is there when it differs from the tree's label (a road with a collapsed
  chain: `"Humanities・History"`), else `address[-1]` is the name. `collapsed` lists the topics collapsed into the road, top first. `over: true` marks a road
  that holds more than `max` houses and cannot split. `rib` is `{trunk, band, side, x0, x1, s, slots}` (`band` is null when the rib lies along the spoke).
  A road that holds more than its first rib has `lanes`: continuation ribs, records with `lane_of`, `ordinal`, `continued: true` and the same label,
  level, class and address as the road.

  **`lots` and `reserved` count one segment**: the houses that stand in, and the empty lots that are left in, the rib that this record carries. A road with
  continuation ribs is several records, each with its own counts. **The houses standing on a whole road are the `lots` of its record plus the `lots` of every
  record in its `lanes`, and not the houses of the roads below it.** In the sample, Ecology is a record with `lots: 18` and one continuation with `lots: 17`: 35
  houses. `reserved` is read the same way. (A continuation that a split left empty is not in the document, nor in `lanes`.)

  **A road with no lots of its own** has `lots: 0`, `reserved: 0` and no `rib`. In `grow` mode it is a road whose houses have all moved to the roads below it, and none has arrived since. In
  `mirror` mode it is also a topic that has roads below it and no house of its own, or a topic an item is filed under while that item's house stands elsewhere.
  It is a road all the same: it has a place, an address, a level and a parent, and a ring-1 road of this kind has its wedge and its spoke.

### `roads`

Each road has `street`, `kind`, `class`, `parent` (the road it hangs on), `at` (where, as a distance along the parent), `length` and `points` (a polyline).

- `spoke`: a straight road through the plaza along the bisector of a wedge (`axis`, `s0`, `s_end`, `open`, `wedge`);
- `arc`: a connector from a trunk to the axis of a side wedge (`side`);
- `lane`: an arc around the plaza across a trunk, one stretch per street (`trunk`, `band`, `side`, `off`, `radius`, `bearings`);
- `ring`: the lane of the ring road or of one of its laps, a closed circle round the plaza from north clockwise (the last point is the first), with no parent (`radius`).

The walk from the plaza to a door is the sum of the `at` of its road and its ancestors, and the distance along its own lane. The spokes of ring 1 start at the outer
edge of the ring road (`s0`); the walk to a house on the ring goes out through the nearest gate to its lane, then along it.

## Two modes

`grow` builds the city the way a collection grows: the roads open as the houses arrive. `mirror` builds the street plan of the tree you give it: a road for
every topic an item is filed under (every entry of its `topics`) and for every topic above one, while each house still stands once, at its address. Both read
the same two files and write the same kind of document; `world.mode` says which. The rules are in [engine.md](engine.md).
