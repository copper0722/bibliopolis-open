# A world built by hand

`build` makes a city from a library. A world built by hand is made one act at a time: an item arrives and becomes a house under the town hall, the player opens a road
and moves houses onto it, files a house, renames a road, moves a road, takes an act back. The world is an **append-only log of events**; the city and its chronicle
are the **fold** of the log (same log, same bytes). The log is kept in a SQLite file or in a world file (JSON), and the same content moves between them.

```
python -m bibliopolis world new                                      a new, empty world in the home folder (printed)
python -m bibliopolis world import city.world.json                   read a world file into a new world
python -m bibliopolis world export city.world.json                   write the world as a world file
python -m bibliopolis world fold --out city.json                     the city that the log folds to, as `build` writes it
python -m bibliopolis picture --city city.json --out city.svg        ... and the picture and the chronicle read it as any city
```

Nothing here touches the network. An item brings its own metadata (and its OpenAlex topics when it has them); fetching them is not part of the engine.

## The log

An event is `{seq, at, kind, payload}`. `seq` runs 1, 2, 3, ... in log order. **Log order is arrival order**: the fold reads `at` (an ISO 8601 date or date and time) from
the event, writes it into the chronicle, and never reads the clock; `at` does not have to grow.

| kind | payload | what it does |
|---|---|---|
| `add_item` | `{item}` | the item becomes a house in the root zone, under the town hall |
| `open_road` | `{road, name, parent, houses}` | the player opens a road, a named category, below a road or (`parent` null) the root zone, and moves the houses chosen onto it. The place it opens from holds at least `min` houses directly, at least `min` houses are chosen, and all of them stand directly there |
| `file` | `{house, road}` | a house moves, from the root zone or another road, onto a road |
| `rename_road` | `{road, name}` | |
| `move_road` | `{road, parent}` | a road, with the roads and the houses below it, stands again below another road |
| `undo` | `{seq}` | the named event no longer counts; an undo of an undo gives it back |
| `set_rule` | `{max, min, auto}` | the rule from here on |

A road id is text chosen by whoever appends the event (not empty, no control characters, not of the form `lane:<id>:<n>`, not starting with `auto:`); it names one road, so a road
is not opened twice under one id while it stands. A house id is the id of its item, and likewise names one house. (An event that an undo takes back leaves its ids free.) Road ids and
house ids are two kinds of name.

### An item

```json
{"id": "item-0001", "title": "A survey of adaptive networks", "authors": ["B. Hansen"], "year": 2024, "doi": "10.0000/ex.0001", "type": "article",
 "openalex": [{"domain": {"id": "ex:d1", "name": "Domain 1"}, "field": {"id": "ex:d1.f1", "name": "Field 1.1"},
               "subfield": {"id": "ex:d1.f1.s1", "name": "Subfield 1.1.1"}, "topic": {"id": "ex:d1.f1.s1.t1", "name": "Topic 1.1.1.1"}}]}
```

`id`, `title` (may be empty), `authors`, `year` (a whole number or null) and `type` are there; `doi` (null when there is none) and `openalex` (the empty list when no topic is
known) may be left out. `openalex` holds up to three topics, the primary one first, each with all four levels (domain, field, subfield, topic) as `{id, name}`; an id is any
text, the ids of OpenAlex when the topics come from there. Any other key is refused, so that nothing is dropped in silence. The samples and the tests of this repository use
invented topics (`ex:d1.f1.s1.t1`).

### The rule

`{max, min, auto}`: whole numbers 1 <= `min` <= `max`, and a boolean. `min` is the least a new road takes (see `open_road`). `max` is how many houses a road is meant to hold:
the world never refuses a house for it, never marks a road over and never splits a road by itself; `crowded` (below) lists what holds more, and the town hall tells the player.
`auto` is the one rule that acts (see "The rule `auto`"). The rule of a world starts as the file says (40, 10, off by default) and `set_rule` changes it from its place in the log.

## What the fold does

**The root zone.** A house starts underground, under the town hall, on the first free cell of the grid of the root zone (as in a grown city, see [engine.md](engine.md)). The
root zone is no road: nothing of it is on the surface.

**A road** is a topic node of the player's tree. Below the root zone it is a **ring-1 road**: a trunk of its own, with a sector of the circle and a spoke through the plaza.
Below a road it is laid out as the engine lays out a topic that the plan does not hold: a rib on the line of its ring-1 road (a road of ring 3 is a rib on the same line). No
trunk is promoted and no heavy path changes. A road with more houses than a rib holds opens continuation ribs, as in a grown city.

**Directions.** There is no library to plan from, so the sector of a ring-1 road is decided when it opens, from the golden angle. The k-th ring-1 road (k = 0 for the first)
has the bearing k * 137.50776405003785 degrees, clockwise from north, in whole units of 1/100 degree and in exact integer arithmetic:
`bearing(k) = (k * 13750776405003785 + 500000000000) // 10**12 % 36000`. Its sector is **the free arc around that bearing, at most 20 degrees to either side**: it stops where
the next sector begins on each side, and it never overlaps a sector given already. A sector once given never changes, not when its road moves away. The spoke runs along the middle
of the sector, which is kept between -180 and 180 degrees. These are the thirteen sectors that there are:

| k | bearing | sector | k | bearing | sector |
|---|---|---|---|---|---|
| 0 | 0.00 | -20.00 .. 20.00 | 7 | 242.55 | -137.45 .. -104.98 |
| 1 | 137.51 | 117.51 .. 157.51 | 8 | 20.06 | 20.00 .. 32.52 |
| 2 | 275.02 | -104.98 .. -64.98 | 9 | 157.57 | 157.51 .. 170.03 |
| 3 | 52.52 | 32.52 .. 72.52 | 10 | 295.08 | -64.98 .. -52.46 |
| 4 | 190.03 | -189.97 .. -149.97 | 11 | 72.59 | 72.52 .. 85.05 |
| 5 | 327.54 | -52.46 .. -20.00 | 12 | 210.09 | -149.97 .. -137.45 |
| 6 | 105.05 | 85.05 .. 117.51 | 13 | 347.60 | none: inside the sector of k = 0 |

They cover the whole circle, so **the first ring holds 13 roads**. The 14th bearing lies inside a sector given already, and `open_road` from the root zone is refused with the reason
(a road below a road can still open). A road that moves below another road keeps its sector given: the next ring-1 road takes the next direction, not the one it left.

**Stability.** A house keeps its lot unless an event moves it. `open_road` moves the houses chosen, `file` moves that house, `move_road` moves the houses of the road and of the roads
below it; nothing else moves a house, and the houses that stay keep their lots whatever holes the others leave (a lot that a house leaves stays empty, and the next house on that road
takes the lowest empty lot). The one exception is `undo`, which is the fold of the log without the event it takes back, so it may place again what came after that event. The tests
replay logs one event at a time and check this (`tests/test_stability.py`), with planted faults that must turn the check red.

**Moving a road.** The road and the roads below it are put again below the new parent, a road at a time in the order the roads were opened, and their houses in the order they arrived;
their old ribs go and the ground they claimed stays claimed. A road may not move below itself or below a road of its own, nor below the road it is below already. A ring-1 road may move
below a road (it is then laid out like any road of ring 2). A road below a road cannot move to the town hall: `parent` is a road, and a move never makes a ring-1 road.

**Undo.** `undo` names an earlier event that counts. It is refused when a later event that counts depends on the named one: it names a road that the event opened, or a house that the
event placed or moved. So the player undoes from the end backwards. It is also refused when the log without that event does not fold (every later event that counts is taken again; for
example giving back a filing whose house a later event took from the root zone). Appending is all or nothing.

**The chronicle.** One entry for each road opened, house filed, road renamed or moved, undo and change of rule, in log order. Every entry has `n` (1, 2, ...), `event_id` (the `seq` of the
event), `seq` (the houses that have arrived), `trigger` (the kind of the event) and, last, `at` (the `at` of the event); then:

| entry | keys |
|---|---|
| a road opened (`open_road`, and the rule `auto`) | `from`, `to`, `label`, `houses`, `count_before`, `count_after` (the shape of a split in a grown city) |
| a house filed | `filed`, `left`, `joined` (the house id and two place ids) |
| a road renamed | `renamed`, `was`, `label` |
| a road moved | `moved`, `below`, `was_below`, `houses` (the houses put again) |
| an undo | `undone`, `of` (the number and the kind of the event) |
| a change of rule | `rule` |

An event that an undo takes back writes no entry (it does not count); the undo writes one. `python -m bibliopolis chronicle` reads them as sentences.

**The rule `auto`.** After an arrival (`add_item`) that leaves the root zone above `max`, the rule opens a road for the largest group of houses of the root zone that share an OpenAlex topic
at the most specific level that gives a group of at least `min` (see `suggest_road`), named after that topic, below the town hall: `auto:<seq>` (`auto:<seq>.2` for a second road of the
same arrival), a road like any other afterwards. It uses the mechanics of `open_road`, so the houses that stay keep their lots. It repeats while the root zone is above `max` and a group is
left. When no group reaches `min`, or the first ring has no direction left, nothing happens. An arrival still becomes a house in the root zone, and the rule does not file it onto a road that
is there: the houses of a topic that a road took gather in the root zone again, and a second road of the same name can open. (On the 600-item sample of this repository, with invented topics,
the first ring is full by the 180th arrival.) A `set_rule` that switches `auto` on opens nothing by itself.

**Numbers.** Every document the package writes spells a number as `JSON.stringify` does: an integral value without a fraction (`40`, not `40.0`), any other value as its shortest text
(`bibliopolis.canonical`). The in-memory documents keep their floats. A number that another language would spell differently (an exponent form, a value of 10**15 or more) is refused.

## Suggestions

No model and no network: the same world gives the same answer. A house is in the group of each OpenAlex topic it carries, once.

- `suggest_road(world, at)`: the road to open at `at` (a road id, or `None` for the root zone). The largest group of the houses standing directly there that share a topic at the most specific
  level (topic, then subfield, field, domain) that still gives a group of at least `min`; at one level the largest group wins, and of two as large the one with the lower topic id. Returns
  `{at, level, topic: {id, name}, name, houses}`, `name` being the default name of the road (the name of that topic), or `None`.
- `suggest_file(world, house)`: the road that the house belongs on. A road scores a count for each level, the topic level first: the topics the house shares with the houses of the road, summed
  over those houses. The best score wins, a road opened earlier winning a tie. Returns `{house, road, name, level, shared, confidence}`: `level` is the most specific level at which the
  winner shares anything, `shared` the count there, `confidence` that count as a part of the same count over every road that could take the house (1.0 when no other road shares a topic
  at that level), in hundredths. A house on a road gets a suggestion only for a road that scores better than its own; `None` when there is nothing to suggest.
- `crowded(world)`: `[{at, name, houses}]` for the places that hold more than `max` houses directly, the root zone (`at` and `name` null) first.

## The files

**A world file** is JSON: `{format, version, rule, items, events}`. `format` is `"bibliopolis.world"` and `version` is 1. `rule` is the rule the world started with. `events` is the log.
`items` is the item of every `add_item` event in log order (an undone one too): written from the events for a reader that does not fold, and checked against them when a file is read. The
text has the header, then one item and one event to a line, and a file that is read and written again is the same bytes.

```json
{"seq": 3, "at": "2026-10-26T09:30:00Z", "kind": "file", "payload": {"house": "item-0001", "road": "r1"}}
```

Reading a file appends every event in turn under the rules of `Journal.append`, and names the first problem with its place (`world.events[14] (file): there is no road 'x'`).

**A SQLite file** (standard library `sqlite3`) holds the same content in three tables: `world` (one row: format, version, the starting rule as JSON text), `event` (`seq`, `at`, `kind`,
`payload` as JSON text) and `item` (`seq`, `id`, `json`: the item of each `add_item` event). The log is append-only: the file refuses an update or a delete of a row. Importing a world file and
exporting it again gives the same bytes, and so does exporting a store and importing the file.

**The home folder** is `$BIBLIOPOLIS_HOME`, else `~/Bibliopolis`; it is made on first use and printed. The world of a command without `--world` is `world.sqlite` in it. A world is never
overwritten: `world new` and `world import` refuse a file that is there.

## In Python

```python
from bibliopolis.journal import Journal, dumps_world, read_world, world_document
from bibliopolis.suggest import suggest_road, suggest_file, crowded

journal = Journal()                                              # or Journal({"max": 30, "min": 8, "auto": True})
journal.append("add_item", {"item": item}, "2026-10-26T09:30:00Z")   # the event, or Refusal and no change
journal.state.city()                                             # the layout v4 document
suggest_road(journal.state, None)
```

`Journal.append` is the one way an event enters a world. `bibliopolis.hand.fold(events, rule)` folds a whole log. `bibliopolis.store.Store` reads and writes the SQLite file.

## Limits of this version

- The first ring holds 13 roads (above). The sectors are fixed by the rule, not by the weight of a road.
- No trunk is promoted below ring 1 and no heavy path changes; a road below a road is a rib on the line of its ring-1 road.
- A road never becomes a ring-1 road by moving (`parent` is a road).
- Under `auto` an arrival is not filed onto a road that is there (above).
- The roads of a hand-built city are never marked over and nothing splits by itself; `crowded` is computed on demand.
- A `set_rule` that lowers `max` or `min` changes nothing in the world; it changes what `crowded` lists and what `open_road` takes.

## Where the tests are

| rule | test file |
|---|---|
| the shape of an item, an event and a rule; which events count | `tests/test_events.py` |
| the sectors, every kind of event and its refusals, undo and undo of an undo, the fold, the documents | `tests/test_hand.py` |
| stability of the lots, and the planted faults that turn it red | `tests/test_stability.py` |
| the journal | `tests/test_journal.py` |
| suggestions, `crowded`, the rule `auto`, the sample | `tests/test_suggest.py` |
| the world file, the SQLite file, the home folder | `tests/test_world_file.py` |
| the command `world` | `tests/test_world_cli.py` |
| the number form and the pinned hashes | `tests/test_canonical.py`, `tests/test_world_file.py` |
| this page: its examples load through the readers and its numbers are the program's | `tests/test_world_page.py` |
