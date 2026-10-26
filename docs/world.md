# A world built by hand

`build` makes a city from a library. A world built by hand is made one act at a time: an item arrives and becomes a house under the town hall, the player opens a road
and moves houses onto it, files a house, renames a road, moves a road, takes an act back. The world is an **append-only log of events**; the city and its chronicle
are the **fold** of the log (same log, same bytes). The log is kept in a SQLite file or in a world file (JSON), and the same content moves between them.

```
python3 -m bibliopolis world new                                      a new, empty world in the home folder (printed)
python3 -m bibliopolis world import city.world.json                   read a world file into a new world
python3 -m bibliopolis world export city.world.json                   write the world as a world file
python3 -m bibliopolis world fold --out city.json                     the city that the log folds to, as `build` writes it
python3 -m bibliopolis picture --city city.json --out city.svg        ... and the picture and the chronicle read it as any city
```

Nothing here touches the network. An item brings its own metadata (and its OpenAlex topics when it has them); fetching them is not part of the engine.

## The log

An event is `{seq, at, kind, payload}`. `seq` runs 1, 2, 3, ... in log order. **Log order is arrival order**: the fold reads `at` (an ISO 8601 date or date and time) from
the event, writes it into the chronicle, and never reads the clock; `at` does not have to grow.

| kind | payload | what it does |
|---|---|---|
| `add_item` | `{item}` | the item becomes a house in the root zone, under the town hall |
| `open_road` | `{road, name, parent, houses, topic}` | the player opens a road, a named category, below a road or (`parent` null) the root zone, and moves the houses chosen onto it. The place it opens from holds at least `min` houses directly, at least `min` houses are chosen, and all of them stand directly there. `topic` is the OpenAlex node the road stands for (see "A road's node"), or null; it may be left out |
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

### A road's node

```json
{"seq": 41, "at": "2026-10-26T09:30:00Z", "kind": "open_road", "payload": {"road": "d1", "name": "Domain 1", "parent": null, "houses": ["item-0001", "item-0002"], "topic": {"id": "ex:d1", "level": "domain", "name": "Domain 1"}}}
```

A road may stand for one node of the OpenAlex tree, which has four levels: domain, field, subfield and topic. `topic` is `{id, level, name}` (the level is one of those four), or null for a category that
the player named, which stands for no node. A suggestion gives its node ready to be the `topic` of `open_road`, and the rule `auto` opens only such roads. The world takes a node on two conditions:
every house chosen is under it (one of its topics has that node at that level), and no other road stands for it. **Two roads never stand for one node.** Renaming or moving a road does not
change its node. Left out, `topic` is null, and the event is kept with it, last in the payload.

### The rule

`{max, min, auto}`: whole numbers 1 <= `min` <= `max`, and a boolean. `min` is the least a new road takes (see `open_road`). `max` is how many houses a road is meant to hold:
the world never refuses a house for it, never marks a road over and never splits a road by itself; `crowded` (below) lists what holds more, and the town hall tells the player.
`auto` is the one rule that acts (see "The rule `auto`"). The rule of a world starts as the file says (40, 10, off by default) and `set_rule` changes it from its place in the log.

## What the fold does

**The root zone.** A house starts underground, under the town hall, on the first free cell of the grid of the root zone (as in a grown city, see [engine.md](engine.md)). The
root zone is no road: nothing of it is on the surface.

**A road** is a node of the player's tree (it may also stand for a node of OpenAlex: see "A road's node"). Below the root zone it is a **ring-1 road**: a trunk of its own, with a sector of the circle and a spoke through the plaza.
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

They cover the whole circle: **a town has at most 13 avenues** (大道, the roads of the first ring), so **the 14th category goes below an avenue**. The 14th bearing lies inside a sector
given already, and `open_road` with `parent` null is refused with the id `ring1_full` (see "Refusals"); a road below an avenue still opens. A road that moves below another road keeps its
sector given: the limit is on the directions given, and the next ring-1 road takes the next direction, not the one it left.

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

An event that an undo takes back writes no entry (it does not count); the undo writes one. `python3 -m bibliopolis chronicle` reads them as sentences.

**The rule `auto`.** The rule follows the OpenAlex tree one level at a time, as a grown city follows its topic tree (nothing here is a model):

1. *An arrival lands.* An item that arrives stands on the deepest road whose node it is under: one of its topics has that node at that level. Of two roads as deep, the one that the topic
   nearer the primary one reaches wins. With no such road the house stays underground, in the root zone. (This is the nearest open ancestor of a grown city, with the nodes of OpenAlex for the tree.)
2. *The place is looked at.* If the place the house landed on, a road or the root zone, holds more than `max` houses directly, a road is opened for the largest group of its houses one level below
   the place (`suggest_road`): the root zone by domain, a domain road by field, a field road by subfield, a subfield road by topic. A road for a topic is not split. The new road stands for the node,
   is named after it, and opens below the place (a domain below the town hall, as a ring-1 road). It uses the mechanics of `open_road`, so the houses that stay keep their lots. The place is looked
   at again while it holds more than `max` houses and a group is left.
3. *The roads it opened are looked at in turn,* in the order they were opened, so a road that holds more than `max` houses splits again in the same event.

The roads are `auto:<seq>`, `auto:<seq>.2`, `auto:<seq>.3`, ... in the order they were opened, roads like any other afterwards. When no group reaches `min`, or all 13 directions of the first ring are used
(the root zone only), nothing happens at that place and it stays crowded (`crowded` says so). Two roads never stand for one node, so the first ring holds the domains and the rest goes below them.
A `set_rule` that switches `auto` on opens nothing by itself, and a place that is over `max` for another reason waits for an arrival that lands on it. On the 600-item sample of this repository
(invented topics) the rule makes 23 roads (domains 6, fields 10, subfields 6, topics 1), and 15 houses stay underground.

**Numbers.** Every document the package writes spells a number as `JSON.stringify` does: an integral value without a fraction (`40`, not `40.0`), any other value as its shortest text
(`bibliopolis.canonical`). The in-memory documents keep their floats. A number that another language would spell differently (an exponent form, a value of 10**15 or more) is refused.
The one line of numbers that is not JSON, the caption of `picture`, prints a measure as the float it is (`55.0`) whichever form the file has, so that a picture drawn from a city file has
the same bytes as the picture of the city.

## Refusals

A world that does not take an event raises `Refusal` (a `ValueError`) and is as it was. A world file or a store that is not a world raises `WorldFileError`. Both carry the English message
and, for a page that translates it, **an id and params**:

- `code`: one of the ids of `bibliopolis.events.CODES`, the one list of them;
- `params`: the values the message is made of, in the names that the list gives, all plain JSON values (a place is a road id, or null for the root zone);
- `event`: `{seq, kind}` when the reason is about an event of a log that was replayed, folded or read, else null;
- `where`: the file, or the place in a file, when the reason is about one, else null;
- `as_dict()` is all of it, with the message, as a JSON object.

A page translates from `code` and `params`, never from the text. **Every** refusal and every error of a world file has an id: a test reads the source for each place that raises one, and
runs a scenario for each id (`tests/refusal_cases.py`); the tables below are checked against those scenarios, so each message is what the program says.

`Refusal.within(seq, kind)` passes a refusal on with the event of the log that it is about (the message gets `event 7 (file): ` in front) and keeps its id and params. A world file or a store
that is read passes the refusal of an event on as a `WorldFileError` with the same id and params, with `event` and `where`. A shape that is wrong has the id `invalid`, whose `problems` are
`{where, code, params}`, each with an id of the table of shapes.

### The world refuses an event

| id | params | when | message |
|---|---|---|---|
| `ring1_full` | `limit`, `number` | `open_road` with `parent` null, when all 13 directions are used (`limit` is 13, `number` the number of the category) | the first ring has at most 13 avenues and all 13 directions are used, so the 14th category goes below an avenue |
| `house_exists` | `house` | `add_item` of an item whose id is a house already | 'h0001' is a house already |
| `not_a_house` | `house` | a house id that is not a house: in `open_road`, `file` and `suggest_file` | 'nobody' is not a house |
| `road_exists` | `road` | `open_road` with the id of a road that is there | there is a road 'a' already |
| `no_road` | `road` | a road id that is not a road: the road of `file`, `rename_road` and `move_road`, and `suggest_road` | there is no road 'nowhere' |
| `parent_missing` | `parent` | `open_road` below a road that is not there | there is no road 'ghost' to open a road below |
| `move_parent_missing` | `parent` | `move_road` below a road that is not there | there is no road 'nowhere' to move a road below |
| `too_few_here` | `road`, `held`, `least` | `open_road` from a place that holds fewer than `least` houses directly (`road` is null for the root zone) | the root zone holds 9 houses directly; a road is opened from a place that holds at least 10 |
| `too_few_chosen` | `chosen`, `least` | `open_road` with fewer than `least` houses chosen | 9 houses are chosen; a road takes at least 10 |
| `house_elsewhere` | `house`, `road`, `on` | `open_road` names a house that does not stand directly on the place it opens from (`road`; `on` is where the house stands; null is the root zone) | the house 'h0001' does not stand directly on the root zone; it stands on the road 'a' |
| `node_taken` | `level`, `topic`, `road` | `open_road` with a `topic` that another road stands for already (`road` is that road): two roads never stand for one node | the road 'a' stands for the domain 'ex:d1' already; two roads never stand for one node |
| `house_not_under_node` | `house`, `level`, `topic` | `open_road` with a `topic` and a chosen house none of whose topics has that node at that level | the house 'h0013' is not under the domain 'ex:d1', which the road stands for |
| `already_there` | `house`, `road` | `file` onto the road the house stands on | the house 'h0001' stands on the road 'a' already |
| `same_name` | `road`, `name` | `rename_road` to the name the road has | the road 'a' is called 'Alpha' already |
| `move_into_itself` | `road`, `parent` | `move_road` below itself, or below a road of its own | the road 'a1' cannot move below 'a1', which is itself or one of its own roads |
| `already_below` | `road`, `parent` | `move_road` below the road it is below | the road 'a1' is below 'a' already |
| `rule_unchanged` | `max`, `min`, `auto` | `set_rule` to the rule that is in force | the rule is this already |

### An undo is refused

| id | params | when | message |
|---|---|---|---|
| `undo_not_earlier` | `target`, `seq` | an undo that names an event that is not earlier than the undo | an undo names an earlier event; event 9 is not earlier than event 4 |
| `undo_not_counting` | `target` | an undo that names an event that does not count (there is none, or it is undone) | event 3 does not count (there is no such event, or it is undone already) |
| `undo_depends` | `target`, `later`, `kind` | an undo of an event on which a later event that counts depends (`later` and `kind` say which) | event 15 cannot be undone: event 16 (rename_road) depends on it; undo that one first |
| `undo_unfoldable` | `target`, `later`, `kind`, `cause`, `cause_params` | an undo after which the log does not fold: `later` and `kind` name the event that no longer applies, `cause` and `cause_params` the refusal it gets (an id of this list and its params) | event 43 cannot be undone: event 44 (open_road): the house 'h0011' does not stand directly on the root zone; it stands on the road 'a' |

### A log or a store is not taken

| id | params | when | message |
|---|---|---|---|
| `event_out_of_place` | `seq`, `place` | replaying a log whose events are not numbered 1, 2, 3, ... in order | event 7 comes in place 6: the events are numbered 1, 2, 3, ... in order |
| `world_exists` | `path` | making a world, or importing one, where a file is already (a world is never overwritten) | <folder>/w.sqlite is there already; a world is not overwritten (choose another file with --world, or move that one away) |
| `not_next_event` | `path`, `held`, `next`, `seq` | appending to a store an event that is not the next number | <folder>/w.sqlite holds 3 events; the next is number 4, not 6 |

### The shape of an event, a rule or a world file is wrong

| id | params | when | message |
|---|---|---|---|
| `invalid` | `problems`, `more` | an event or a rule whose shape is wrong, or a world file with such a part: `problems` lists them (at most 20), each `{where, code, params}` with an id of the next table, and `more` counts those not listed | event.payload.item.id: must be a string, got int |
| `keys_missing` | `keys` | an object lacks keys that it needs | event: missing at, kind, payload |
| `keys_unknown` | `keys`, `allowed` | an object has keys that it may not have | event.payload.item: unknown colour (allowed: id, title, authors, year, doi, type, openalex) |
| `not_an_object` | `got` | a part that must be an object is not (`got` is the name of its type) | event: must be an object, got list |
| `not_a_list` | `got` | a part of a world file that must be a list is not | world.items: must be a list, got dict |
| `not_text` | `got` | a part that must be text is not | event.payload.item.id: must be a string, got int |
| `text_empty` | none | text that must not be empty is (or holds white space only) | event.payload.item.id: must not be empty |
| `text_not_utf8` | none | text with a lone surrogate, which cannot be written as UTF-8 | event.payload.item.title: contains a character that cannot be written as UTF-8 (a lone surrogate) |
| `text_control` | none | an id or a name with a control character | event.payload.item.id: must not contain control characters |
| `authors_not_a_list` | `got` | `authors` of an item is not a list | event.payload.item.authors: must be a list of strings, got str |
| `year_bad` | `limit`, `got` | `year` of an item is not a whole number within the limit, or null | event.payload.item.year: must be a whole number (at most 1000000 either way) or null, got '2020' |
| `topics_not_a_list` | `max`, `got` | `openalex` of an item is not a list | event.payload.item.openalex: must be a list of up to 3 topics, got str |
| `topics_too_many` | `count`, `max` | `openalex` of an item holds more topics than `max` | event.payload.item.openalex: holds 4 topics; the most an item carries is 3 (its primary topic and two more) |
| `topic_not_an_object` | none | a topic of an item is not an object | event.payload.item.openalex[0]: must be an object with domain, field, subfield and topic |
| `level_not_an_object` | none | a level of a topic (domain, field, subfield, topic) is not an object `{id, name}` | event.payload.item.openalex[0].domain: must be an object {id, name} |
| `topic_twice` | `topic`, `first` | an item carries the same topic twice (`first` is the place of the first) | event.payload.item.openalex[2].topic.id: 'ex:d1.f1.s1.t1' is the topic of event.payload.item.openalex[0] already |
| `rule_not_an_object` | `got` | a rule is not an object | world.rule: must be an object {max, min, auto}, got list |
| `rule_number_bad` | `name`, `limit`, `got` | `max` or `min` of a rule is not a whole number from 1 to `limit` (`name` says which) | world.rule.max: must be a whole number from 1 to 100000, got 0 |
| `not_a_boolean` | `got` | `auto` of a rule is not true or false | world.rule.auto: must be true or false, got 'yes' |
| `rule_min_over_max` | `min`, `max` | a rule whose `min` is more than its `max` | world.rule: min (9) is more than max (5) |
| `road_id_lane_like` | `road` | a new road id of the form `lane:<id>:<n>` | event.payload.road: 'lane:x:2' looks like the block key of a continuation rib (lane:<id>:<n>); use another id |
| `road_id_reserved` | `road`, `prefix` | a new road id that starts with `prefix`, which is for the roads that the rule opens | event.payload.road: 'auto:7' starts with 'auto:', which is for the roads that the rule opens by itself |
| `undo_seq_bad` | `got` | `seq` of an undo is not the number of an event | event.payload.seq: must be the number of an event (1 or more), got 0 |
| `houses_empty` | none | `houses` of an `open_road` is not a list, or is empty | event.payload.houses: must be a list of house ids, not empty |
| `house_chosen_twice` | `house` | a house chosen twice in `houses` of an `open_road` | event.payload.houses[1]: 'a' is chosen twice |
| `node_not_an_object` | `got` | `topic` of an `open_road` is not null and not an object | event.payload.topic: must be null or an object {id, level, name}, got str |
| `node_level_bad` | `got`, `levels` | `level` of a `topic` is not one of `levels` (domain, field, subfield, topic) | event.payload.topic.level: must be one of domain, field, subfield, topic, got 'planet' |
| `event_seq_bad` | `got` | `seq` of an event is not a whole number, 1 or more | event.seq: must be a whole number, 1 or more, got 0 |
| `date_bad` | `at` | `at` of an event is not an ISO 8601 date or date and time | event.at: 'yesterday' is not an ISO 8601 date or date and time |
| `kind_unknown` | `kind`, `kinds` | `kind` of an event is not one of `kinds` | event.kind: 'sweep' is not a kind of event (add_item, open_road, file, rename_road, move_road, undo, set_rule) |

### A world file or a store is not a world

| id | params | when | message |
|---|---|---|---|
| `not_a_world_file` | `got` | a world file that is not a JSON object | world: not a world file: it must be a JSON object, got list |
| `file_keys` | `missing`, `unknown`, `expected` | a world file that lacks keys (`missing`) or has others (`unknown`) | world: not a world file: missing rule (it has format, version, rule, items, events) |
| `format_wrong` | `format`, `expected` | `format` of a world file is not `expected` | world.format: must be 'bibliopolis.world', got 'something.else' |
| `version_wrong` | `version`, `expected` | `version` of a world file is not `expected` | world.version: this program reads version 1, got 2 |
| `events_not_numbered` | `index`, `seq`, `expected` | the events of a world file are not numbered 1, 2, 3, ... in order (`index` is the place of the first that is not) | world.events[5].seq: must be 6: the events are numbered 1, 2, 3, ... in order, got 7 |
| `items_differ` | `index`, `derived`, `given` | `items` of a world file are not the items of its add_item events (`index` is the place of the first difference) | world.items[13]: the items are those of the add_item events, in order (14 of them), and the file says otherwise (13) |
| `no_world` | `path` | a store that is not there | <folder>/none.sqlite: there is no world here (make one with `world new`, or read a world file with `world import`) |
| `not_a_world` | `path`, `reason` | a file that is not a SQLite database | <folder>/text.sqlite: not a world of this program (file is not a database) |
| `world_table_wrong` | `path`, `format`, `version` | a store whose `world` table is not one row of this format and version | <folder>/other.sqlite: not a world of this program: its world table must hold one row, 'bibliopolis.world' version 1 |
| `row_not_json` | `path`, `reason` | a row of a store whose JSON text is not JSON | <folder>/w.sqlite: a row does not hold JSON (Expecting value: line 1 column 1 (char 0)) |
| `item_table_differs` | `path` | a store whose `item` table is not the items of its add_item events | <folder>/w.sqlite: the item table is not the items of the add_item events |

## Suggestions

No model and no network: the same world gives the same answer. A house is in the group of each OpenAlex node it carries at a level, once.

- `suggest_road(world, at)`: the road to open at `at` (a road id, or `None` for the root zone). The houses that stand directly there are grouped by the level **one below** the level the place stands
  for: the root zone by domain, a domain road by field, a field road by subfield, a subfield road by topic; a road for a topic is not split (`None`). Only the topics at or below the node of the
  place count, and a node that a road stands for already is left out. The largest group of at least `min` houses wins; of two as large the one with the lower node id. Returns
  `{at, topic: {id, level, name}, name, houses}`: `houses` in arrival order, `topic` the node of the group, ready to be the `topic` of `open_road`, `name` the default name of the road (the name
  of the node as the first house that carries it writes it); or `None`.
- *A category that stands for no node* (a road the player named) stands, for this, for the deepest node that its houses share. Of its houses that carry a topic, a node is shared when all but fewer
  than `min` of them carry it (the few that do not could not make a road of their own). The nodes are taken from the domain down, each below the one before it, the largest first and of two as
  large the one with the lower id. The category is then grouped one level below that node, among the houses under it. With no shared node, not even a domain, it is grouped by domain, as the
  root zone is; with a shared topic there is nothing below it and the answer is `None`. (Read as "the level below the deepest level that `min` houses share", the rule would never give a
  group: below the deepest level at which some node reaches `min` houses, by definition no node reaches `min`.)
- `suggest_file(world, house)`: the road that the house belongs on. A road that stands for a node at or above one of the topics of the house comes first, the deepest one, and of two as deep the
  one that the topic nearer the primary reaches. Returns `{house, road, name, level, shared, confidence}`: `level` is the level of the node, `shared` the houses of the road (the house itself left
  out) that are under the same node, `confidence` one over the number of roads as deep as the winner, in hundredths. A house on such a road gets a suggestion only for a deeper one; a house on
  another road, or underground, for the winner. With no such road, a road scores a count for each level, the topic level first: the topics the house shares with the houses of the road, summed over
  those houses. The best score wins, a road opened earlier winning a tie; `level` is the most specific level at which it shares anything, `shared` the count there, `confidence` that count
  as a part of the same count over every road that could take the house (1.0 when no other road shares a topic at that level). A house on a road gets a suggestion only for a road that scores better than
  its own; `None` when there is nothing to suggest.
- `landing(world, item)`: the road an arriving item stands on under the rule `auto` (the deepest road whose node it is under), or `None`.
- `crowded(world)`: `[{at, name, houses}]` for the places that hold more than `max` houses directly, the root zone (`at` and `name` null) first.

## The files

**A world file** is JSON: `{format, version, rule, items, events}`. `format` is `"bibliopolis.world"` and `version` is 1. `rule` is the rule the world started with. `events` is the log.
`items` is the item of every `add_item` event in log order (an undone one too): written from the events for a reader that does not fold, and checked against them when a file is read. The
text has the header, then one item and one event to a line, and a file that is read and written again is the same bytes.

```json
{"seq": 3, "at": "2026-10-26T09:30:00Z", "kind": "file", "payload": {"house": "item-0001", "road": "r1"}}
```

Reading a file appends every event in turn under the rules of `Journal.append`, and names the first problem with its place (`world.events[14] (file): there is no road 'x'`).

**Its shape** is `schema/world.schema.json` (JSON Schema, 2020-12). A file that the program writes satisfies it, and a file that does not is always refused. A file that does may still be
refused: the schema cannot say what the program checks by reading the whole file (an id used once, events numbered in order, `min` no more than `max`, `items` equal to the items of the
`add_item` events, a topic named twice by one item, text of white space only, and every refusal of the world). A reader of another language can start from the schema and keep to the
program for the rest. `tests/test_world_schema.py` holds the schema to the program, to the files it writes and to the examples of this page.

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

- A town has at most 13 avenues (above): the 14th category goes below an avenue. The sectors are fixed by the rule, not by the weight of a road.
- No trunk is promoted below ring 1 and no heavy path changes; a road below a road is a rib on the line of its ring-1 road.
- A road never becomes a ring-1 road by moving (`parent` is a road).
- A road for a topic is not split, whatever it holds: the OpenAlex tree has no level below a topic (`crowded` lists it).
- The roads of a hand-built city are never marked over and nothing splits by itself, except under `auto`; `crowded` is computed on demand.
- A `set_rule` that lowers `max` or `min` changes nothing in the world; it changes what `crowded` lists and what `open_road` takes.

## Where the tests are

| rule | test file |
|---|---|
| the shape of an item, an event and a rule; which events count | `tests/test_events.py` |
| the sectors, every kind of event and its refusals, undo and undo of an undo, the fold, the documents | `tests/test_hand.py` |
| stability of the lots, and the planted faults that turn it red | `tests/test_stability.py` |
| the journal | `tests/test_journal.py` |
| suggestions, `crowded`, the rule `auto`, the sample | `tests/test_suggest.py` |
| the ids and params of every refusal, and a scenario for each | `tests/test_refusals.py`, `tests/refusal_cases.py` |
| the world file, the SQLite file, the home folder | `tests/test_world_file.py` |
| the schema of the world file (`schema/world.schema.json`) | `tests/test_world_schema.py` |
| the command `world` | `tests/test_world_cli.py` |
| the number form and the pinned hashes | `tests/test_canonical.py`, `tests/test_world_file.py` |
| this page: its examples load through the readers and its numbers are the program's | `tests/test_world_page.py` |
