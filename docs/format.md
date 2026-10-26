# Formats

Two JSON files go in, one comes out.

```
python -m bibliopolis build --library library.json --tree tree.json --mode grow --out city.json
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
  {"id": "networks", "label": "Networks", "parent": "systems"}
]}
```

| field | type | meaning |
|---|---|---|
| `id` | string, not empty | unique in the tree; no control characters; not of the form `lane:<anything>:<number>` (it would share ids with a continuation rib). |
| `label` | string, not empty | the name of the road. |
| `parent` | string or null | the id of the parent node; null for a root. |

A tree may have several roots. A tree with exactly one root has that root as its centre: the root is the town hall, its children are the
ring-1 roads, and a house whose address is the root itself stands in the root zone.

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

The text is stable: header fields pretty-printed, then one road, one place per line. The same input gives the same bytes on every run (the angles are
integers of 1/100 degree, the coordinates are rounded to three decimals, everything is written in sorted order). The tests build the sample in separate
processes with different hash seeds and compare the bytes.

Coordinates: cells, `x` east, `z` south, the centre of the town hall plaza is the origin. Angles: degrees clockwise from north.

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
(empty lots in the document: always 0 here), `ring1` (every ring-1 sector: `{place, label, weight, from, to, span}`, degrees), `streets`
(`{total, containers, leaves, trunks, groups, spokes, lanes, continuations, underground}`: a road with continuation ribs is counted once) and `measure`
(`lots`, `land_area`, `max_radius`, the walk from the plaza to the doors, `streets_by_class`, `underground_lots`, ...). The measures count the surface only.

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
- **`lot`**: one house. `{article, parent, order, slot, position, facing, seq}` and `underground: true` for a house in the root zone. `article` is the
  item id, `parent` the rib it stands in (its road, or a continuation of it), `slot` its number in the rib (the lowest empty one is used first), `seq`
  the arrival number, `facing` a bearing in degrees.
- **`reserved`**: an empty lot (only in a document made with reserved lots; `build` does not).
- **`street`**: a road, in one of these `shape`s:
  - `trunk`: a road with a spoke of its own (every ring-1 road, and below it a heavy container road): `wedge`, `axis`, `s0`, `s_end`, `open`, `bands`, `road`, `lane`, `heavy`.
  - `group`: a road with roads below it; its own houses (if any) stand on the bands of its carrier trunk.
  - `rib`: a road with no road below it, a stretch of a band of its carrier trunk (`carrier`), or of the spoke.
  - `underground`: the root zone `place:root` (label `根區`): no road, no rib, nothing on the surface. It is in the document once it exists, empty or not.

  A street has `tag` (the topic id; the root zone has none), `address` (the labels from ring 1 down to this road), `level` (1 for ring 1),
  `class` (`大道` ring 1 = avenue, `路` ring 2 = road, `巷` ring 3 = lane, `弄` ring 4 and deeper = alley), `parent` (the street above, or the plaza),
  `lots` (houses standing on it directly) and `reserved` (empty lots it holds). `label` is there when it differs from the tree's label (a road with a collapsed
  chain: `"Humanities・History"`), else `address[-1]` is the name. `collapsed` lists the topics collapsed into the road, top first. `over: true` marks a road
  that holds more than `max` houses and cannot split. `rib` is `{trunk, band, side, x0, x1, s, slots}` (`band` is null when the rib lies along the spoke).
  A road that holds more than its first rib has `lanes`: continuation ribs, records with `lane_of`, `ordinal`, `continued: true` and the same label,
  level, class and address as the road.

### `roads`

Each road has `street`, `kind`, `class`, `parent` (the road it hangs on), `at` (where, as a distance along the parent), `length` and `points` (a polyline).

- `spoke`: a straight road through the plaza along the bisector of a wedge (`axis`, `s0`, `s_end`, `open`, `wedge`);
- `arc`: a connector from a trunk to the axis of a side wedge (`side`);
- `lane`: an arc around the plaza across a trunk, one stretch per street (`trunk`, `band`, `side`, `off`, `radius`, `bearings`).

The walk from the plaza to a door is the sum of the `at` of its road and its ancestors, and the distance along its own lane.

## Two modes

`grow` builds the city the way a collection grows: the roads open as the houses arrive. `mirror` builds the street plan of the tree you give it: a road for
every topic an item is filed under (every entry of its `topics`) and for every topic above one, while each house still stands once, at its address. Both read
the same two files and write the same kind of document; `world.mode` says which. The rules are in [engine.md](engine.md).
