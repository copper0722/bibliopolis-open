"""The city document of a world: the layout v4 shape that a viewer reads.

    world_layout(doc, with_reserved=False, with_coast=True) -> dict

A world (bibliopolis.world) keeps its own bookkeeping: lines, ribs with a cursor, the address and the arrival number of every house. It is also
served as the document a layout is: the same top-level keys and records, given their coast and measures by `bibliopolis.layout.finish_layout`
and written by `bibliopolis.layout.render`.

The document is RESTRICTED to what stands: the built houses, the streets they hang on (with the streets above them, up to the plaza, and the
trunk that carries each rib), and the roads those streets need (the road of each street and every road above it, to a spoke that starts at the
plaza rim). Empty lots (`reserved`) are left out unless `with_reserved`. The coast is the buffered outline of the lots and roads that are IN
the document: the land grows with the houses.

Keys:

  top level   schema_version "4", layout_version "v4", centre, generator, composition, geometry, kinds, roads_kinds, counts, world, roads,
              coast, places.
  world       {format "world/1", zoning_version, mode, seq, houses, unbuilt, districts, chronicle, notes}. `seq` is the arrival counter after
              the last house, `houses` the lots in this document, `unbuilt` the empty lots the world holds (in or out of `places`). `districts`
              is the rule (max, min, extract, count) and `chronicle` has one entry per split and one per road that became over, in the order
              they happened (bibliopolis.world, "Roads"); a chronicle entry made by `bibliopolis.city` also says `at`, the `added_at` of the item
              whose arrival caused it. A road has ONE rib, which grows in place when it is full; only a lap of the ring road continues another street (a street record
              with `continued: true`, the road's own label, level, class and address); the counts `composition.streets` count the road once (`continuations` is an extra key,
              the laps). The root is the RING ROAD. The street `place:root` ({shape "ring", level 1, class 大道, label, address [label], parent plaza, lots, reserved 0,
                road "road:place:root", ring {lap 1, radius, slots, gaps}, [lanes]}) is a closed circular road round the plaza and stands from day one, with
                its road (kind "ring", parent null, `radius`, a closed polyline from north clockwise). Its houses are ordinary surface lots on both sides of
                it: lots with parent the lap, `slot` within the lap (even: the inner row, odd: the outer row) and no empty-lot records (the cell of a slot is a
                function of the slot; `ring.gaps` are the gate bearings its cells keep clear). When it is full it goes on as a LAP: a street of shape "ring"
                with `lane_of: place:root`, `ordinal`, `continued: true`, the ring's label, address and class, its own `ring` and its own road
                `road:place:root:lap:<k>`. `measure.ring_lots` counts the houses on every lap; `composition.streets` counts the ring as one street (`ring` = the
                records of shape ring, laps included; the laps are `continuations`).
  composition home_max trunk_min articles buildings reserved_lots ring1 streets measure. `articles` = `buildings` = the houses in this
              document and the annexes (items that exist for another item: below), which are buildings too; `reserved_lots` = the empty lots in this
              document (0 without `with_reserved`); `ring1` is the plan's, every sector of it, built or not (the pinned directions). `world.houses` and
              `measure.lots` count the houses, which are the lots.
  places      plaza {kind label position radius [tag]}; lot {kind article parent order slot position facing seq}; reserved {kind
              parent slot end position facing} (with_reserved only); annex {kind article parent form rank seq}; street, in the shapes
                trunk  address axis bands class kind level lots open order parent reserved road s0 s_end shape wedge weight
                       [carrier collapsed heavy label lane rib tag over]
                group  address carrier class kind level lots order parent reserved shape weight [collapsed label rib road tag over]
                rib    as group; a lap of the ring road is a street of shape ring with lane_of, ordinal, continued, the ring's label and no order, weight or tag
                       (the key `lanes` is the ring road's list of its laps; a city file of version 0.3 or before may give a road `lanes` too: continuation ribs)
              and `rib` {trunk band side x0 x1 s slots} (band null: laid along the spoke of `trunk`, lots on both sides of its axis).
              `lot.seq` is the arrival number (orders the growth). A street's `lots` counts its built lots, `reserved` the lots it holds empty.
              An annex is an item that exists for another item. It is no house: it has no lot, no position, no slot and no address, and `parent` is the place of the lot of the house it
              stands beside, as a `form` wing or mailbox; `rank` numbers the annexes of one house and form by arrival (`seq`), 1 first. A document has the kind `annex` in `counts` and
              `kinds`, and the notes about annexes, only when it holds an annex.
  roads       spoke {at axis class kind length open parent points s0 s_end street wedge}; arc {at class kind length parent points side
              street}; lane {at band bearings class kind length off parent points radius side street trunk}; ring {at class kind length parent (null) points
              radius street}.
  coast       {buffer, tolerance, polygons}.

Determinism: places and roads are sorted by id, street records by key; same world, same options, same bytes.
"""

from __future__ import annotations

from . import layout as lay
from ._version import __version__

GENERATOR = {"tool": "bibliopolis", "version": __version__,
             "input": "a library of items and a topic tree (docs/format.md), folded in arrival order into a world of roads and houses"}
NOTES = {
    "lot.seq": "arrival number of the house: lower numbers arrived first",
    "street.reserved": "empty lots the street holds, whether or not they are listed in places",
    "composition.ring1": "every sector the plan pins, whether a house stands in it or not",
}
NOTES_DISTRICTS = {
    "world.districts": "the rule the roads open by: a road holds `max` houses directly; a crowded road opens a road for its largest group of at least `min`",
    "world.mode": "grow: the roads open by that rule; mirror: every topic that holds a house is a road from the start and nothing splits",
    "world.chronicle": "every split and every road that became over, in the order it happened (the arrival number that caused it and, when the library "
                       "gives one, its date `at`)",
    "street.over": "the road holds more than `max` houses directly and no group of at least `min` can open a road: the topic tree needs sorting",
    "street.continued": "a lap of the ring road, which continues the ring when it is full: the same road (its label, level, class and address), not a road of its own",
    "street.ring": "the ring road round the town hall (the root of the road tree) or one of its laps: a closed circular road with houses on both sides; a lap "
                   "(`lane_of`, `continued`) is the same road, a concentric ring outside the first when it is full; `ring` = {lap, radius, slots, gaps}",
    "road.ring": "a closed circle round the plaza, from north clockwise (the last point is the first), radius `radius`; it has no parent",
    "lot.slot": "on the ring road: slot s stands in cell s // 2 of its lap, the inner row (even s) or the outer row (odd s); the cells keep clear of `ring.gaps`",
}
NOTES_HAND = {
    "world.mode": "hand: the world is the fold of a log of events that the player appended (docs/world.md); a road is a category the player opened or, under the rule `auto`, a road "
                  "that the rule opened for a node of OpenAlex; nothing is marked over, and nothing splits by itself except under `auto`",
    "world.districts": "the rule of the player (docs/world.md): `max` is how many houses a road is meant to hold, `min` is the least a new road takes; the world marks nothing over, "
                       "and only under the rule `auto` does a place that holds more than `max` open a road, for its largest group of at least `min`; the ring road holds `max` houses "
                       "between the gates of its `branches` directions, and a road holds at most `branches` roads",
    "world.chronicle": "every road opened, house filed, road renamed or moved, roads merged, undo, change of rule and new radius of the ring road, in the order of the log "
                       "(`event_id` is the number of the event, `seq` the arrivals so far, `at` the `at` of the event)",
    "composition.ring1": "the avenues that stand: `from` and `to` bound the sector of the direction the avenue holds (the cell nearest its bearing among the bearings of all the "
                         "directions), `axis` is the bearing of its spoke, which need not be the middle of the sector; the street's `wedge` is its land, the part of the sector "
                         "within the narrower side of the spoke",
}
HAND_INPUT = "a log of events (docs/world.md), folded in order into a world of roads and houses"
LOT_KEYS = ("kind", "article", "parent", "order", "slot", "position", "facing")
RESERVED_KEYS = ("kind", "parent", "slot", "end", "position", "facing")
RIB_KEYS = ("trunk", "band", "side", "x0", "x1", "s", "slots")
HIDDEN_STREET_KEYS = frozenset({"line", "role", "side", "inner"})  # what the plan says about a trunk, not what a document shows of it


def needed(doc: dict, with_reserved: bool) -> tuple[set[str], set[str]]:
    """(streets, roads) the document needs: the streets that carry a lot, then whatever those point at - the street above, the street a
    continuation belongs to, the trunk that carries a rib, their roads, the road above each road, and the street of every road.
    The ring road (the root street, lap 1) stands from day one, whatever it holds: the chronicle names it (`from`) after a split that left it empty. A lap beyond
    it stands when a house stands on it.
    In a `mirror` city every road stands once it exists, with a house on it or below it or not."""
    places, roads = doc["places"], doc["roads"]
    streets: set[str] = set()
    out_roads: set[str] = set()
    seeds = {p["parent"] for p in places.values() if p["kind"] == "lot" or (with_reserved and p["kind"] == "reserved")}
    seeds |= {pid for pid, p in places.items() if p["kind"] == "street" and p.get("shape") == "ring" and "lane_of" not in p}
    if doc.get("mode") == "mirror":
        seeds |= {pid for pid, p in places.items() if p["kind"] == "street" and "lane_of" not in p and p.get("tag") is not None}
    street_todo = sorted(seeds)
    road_todo: list[str] = []
    while street_todo or road_todo:
        while street_todo:
            pid = street_todo.pop()
            rec = places.get(pid)
            if pid in streets or rec is None or rec["kind"] != "street":
                continue  # the plaza ends the walk
            streets.add(pid)
            street_todo += [x for x in (rec.get("parent"), rec.get("lane_of"), rec.get("carrier"), (rec.get("rib") or {}).get("trunk")) if x]
            road_todo += [x for x in (rec.get("road"), rec.get("lane")) if x]
        while road_todo:
            rid = road_todo.pop()
            if rid in out_roads:
                continue
            out_roads.add(rid)
            road = roads[rid]
            if road["parent"]:
                road_todo.append(road["parent"])
            street_todo.append(road["street"])
    return streets, out_roads


def street_view(pid: str, rec: dict, roads: dict, streets: set[str], heavy_of: dict[str, str], bands_of: dict[str, set[int]]) -> dict:
    """A street of the world as the document writes it: the plan's bookkeeping and the rib's registry left out, a trunk with the end,
    openness and band count of its spoke (`roads`: the roads of the document)."""
    out = {k: v for k, v in rec.items() if k not in HIDDEN_STREET_KEYS}
    if "rib" in rec:
        out["rib"] = {k: rec["rib"][k] for k in RIB_KEYS}
    if "lanes" in rec:
        lanes = [lane for lane in rec["lanes"] if lane in streets]
        if lanes:
            out["lanes"] = lanes
        else:
            del out["lanes"]
    if rec["shape"] == "trunk":
        spoke = roads[rec["road"]]
        out["s_end"], out["open"] = spoke["s_end"], spoke["open"]
        out["bands"] = len(bands_of.get(pid, ()))
        if heavy_of.get(pid) in streets:
            out["heavy"] = heavy_of[pid]
    return dict(sorted(out.items()))


def street_counts(places: dict[str, dict]) -> dict:
    """The `composition.streets` counts of a document (the streets in it). A road has one rib. The ring road is a street like any: `total` counts it once (a lap is a
    continuation, and the one street that continues another: `continuations`) and `ring` is the number of street records of shape ring, laps included."""
    recs = [p for p in places.values() if p["kind"] == "street"]
    own = [p for p in recs if "lane_of" not in p]
    out = {"total": len(own), "containers": sum(1 for p in own if p["shape"] in ("trunk", "group")), "leaves": sum(1 for p in own if p["shape"] == "rib"),
           "trunks": sum(1 for p in own if p["shape"] == "trunk"), "groups": sum(1 for p in own if p["shape"] == "group"),
           "spokes": sum(1 for p in own if p["shape"] == "spoke"), "lanes": sum(1 for p in recs if "lane_of" in p and not p.get("continued")),
           "continuations": sum(1 for p in recs if p.get("continued")), "ring": sum(1 for p in recs if p.get("shape") == "ring")}
    return out


def world_layout(doc: dict, *, with_reserved: bool = False, with_coast: bool = True) -> dict:
    """The layout v4 document of the world `doc` (see the module docstring). Never changes `doc`."""
    places, roads = doc["places"], doc["roads"]
    streets, road_ids = needed(doc, with_reserved)
    out_roads = {rid: dict(roads[rid]) for rid in sorted(road_ids)}
    heavy_of: dict[str, str] = {}
    for line in doc.get("lines", {}).values():
        for here, there in zip(line["members"], line["members"][1:]):
            heavy_of[here["place"]] = there["place"]  # a line is a trunk and its heavy chain, members in the order they opened
    bands_of: dict[str, set[int]] = {}
    for pid in streets:
        rib = places[pid].get("rib")
        if rib is not None and rib["band"] is not None:
            bands_of.setdefault(rib["trunk"], set()).add(rib["band"])
    out: dict[str, dict] = {lay.PLAZA_PLACE: dict(places[lay.PLAZA_PLACE])}
    for pid in streets:
        out[pid] = street_view(pid, places[pid], out_roads, streets, heavy_of, bands_of)
    n_lots = n_reserved = n_annex = 0
    for pid, p in places.items():
        if p["kind"] == "lot":
            rec = {k: p[k] for k in LOT_KEYS}
            rec["position"] = dict(p["position"])
            rec["seq"] = p["seq"]
            out[pid] = rec
            n_lots += 1
        elif p["kind"] == "annex":  # an item that exists for another item: no lot, no position; it stands where its house stands
            out[pid] = {k: p[k] for k in lay.ANNEX_RECORD_KEYS}
            n_annex += 1
        elif p["kind"] == "reserved" and with_reserved:
            rec = {k: p[k] for k in RESERVED_KEYS}
            rec["position"] = dict(p["position"])
            out[pid] = rec
            n_reserved += 1
    out = dict(sorted(out.items()))
    kinds: dict[str, int] = {}
    for p in out.values():
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    c = doc["composition"]
    by_hand = doc.get("mode") == "hand"
    world = {"format": doc["schema_version"], "zoning_version": doc.get("zoning_version"), "mode": doc.get("mode"), "seq": doc.get("seq", 0),
             "houses": n_lots, "unbuilt": sum(1 for p in places.values() if p["kind"] == "reserved"),
             "districts": dict(doc["districts"]), "chronicle": [dict(e) for e in doc["chronicle"]],
             "notes": {**NOTES, **NOTES_DISTRICTS, **(NOTES_HAND if by_hand else {}), **(lay.ANNEX_NOTES if n_annex else {})}}
    layout = {
        "schema_version": lay.SCHEMA_VERSION, "layout_version": lay.LAYOUT_VERSION,
        "centre": dict(doc["centre"]),
        "generator": {**GENERATOR, **({"input": HAND_INPUT} if by_hand else {})},
        "composition": {
            "home_max": c.get("home_max", lay.HOME_MAX), "trunk_min": c.get("trunk_min", lay.TRUNK_MIN),
            "articles": n_lots + n_annex, "buildings": n_lots + n_annex, "reserved_lots": n_reserved,
            "ring1": [dict(r) for r in c["ring1"]], "streets": street_counts(out),
        },
        "geometry": dict(lay.GEOMETRY), "kinds": {**lay.KIND_NOTES, **({"annex": lay.ANNEX_KIND_NOTE} if n_annex else {})}, "roads_kinds": dict(lay.ROAD_NOTES),
        "counts": dict(sorted(kinds.items())),
        "world": world,
        "roads": out_roads, "places": out,
    }
    return lay.finish_layout(layout, with_coast)
