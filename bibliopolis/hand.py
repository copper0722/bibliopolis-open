"""A world built by hand: the fold of an event log (bibliopolis.events) into a city.

    fold(events, rule) -> State      the world after the standing events, in log order; same log, same bytes
    State.apply(event)               one more event; `Refusal` (and no change) when the world does not take it
    State.city()                     the layout v4 document of the world (bibliopolis.document), the shape `build` writes

There is no library to plan from, so the plan grows with the world and never changes what it has given:

  the root zone   a house starts underground, under the town hall (`add_item`), as in a grown city.
  a road          a named category the player opens (`open_road`) with a chosen set of houses. It is a topic node of the player's tree. Below the root zone it is a
                  ring-1 road and takes the next direction of the golden angle (below); below a road it is laid out as the engine lays out a topic the plan does
                  not hold: a rib on the line of its ring-1 road. No trunk is promoted and no heavy path changes (a stated limitation).
  directions      the k-th direction (k = 0, 1, 2, ...) has the bearing k * 137.50776405003785 degrees, clockwise from north, in whole units of 1/100 degree. Its
                  sector is the free arc around that bearing, at most 20 degrees to either side, never over the sector of an earlier direction (`SECTORS`, a table of
                  13: the 14th bearing lies inside a sector already given, so there are 13 directions and a town has at most 13 avenues, the roads of the first ring,
                  `AVENUES`). A sector never changes. An avenue holds one direction and gives it up when it is no avenue any more: when it moves below another road, or is merged.
                  A new avenue takes the lowest number that no avenue holds; with all 13 held the event is refused (`Refusal` with the id `ring1_full`, and the remedy
                  `merge_roads`): the 14th category goes below an avenue, or similar avenues are merged first.
  merging         `merge_roads` groups avenues upward: the new avenue takes the direction (sector and bearing) of the member whose sector is the widest (it carries all
                  their houses and needs the room; widths are compared in whole tenths of a degree, rounded half up, so that the hundredths that come of the tiling make
                  no difference; of two as wide, the one with the most houses on it and below it, then the lower number), the others are free again and the next avenues
                  take them, the lowest number first (the golden-angle order among the free ones). The members stand below the new avenue as roads of ring 2, as after a
                  move of a road: only the houses of their subtrees are put again.
  stability       a house stays on its lot unless an event moves it: opening a road moves the houses chosen, filing a house moves that house, moving a road moves
                  the houses of its subtree. The houses that stay keep their lots, whatever holes the others leave. (`undo` may re-place what came after the event
                  it takes back: the fold of the log without that event.)
  a node          a road may stand for one OpenAlex node (`open_road` `topic`, `{id, level, name}`): the houses chosen are under it, and no other road stands for it.
  the rule        `max` and `min` are the limits of the player's district rule (`open_road` needs `min` houses; `crowded` lists what is above `max`). The world
                  marks nothing over and splits nothing by itself, except under `auto` (bibliopolis.suggest): an arriving house stands on the deepest road whose node
                  it is under (the root zone when there is none), and a place that then holds more than `max` houses opens a road for its largest group, one level of
                  OpenAlex below the place, with the same mechanics as `open_road`, so even then the houses that stay keep their lots. A road so opened is split in
                  turn while it holds more than `max`.
  the chronicle   one entry for each road opened (the shape of a split), house filed, road renamed or moved, undo and change of rule, in log order; `event_id` is the
                  `seq` of the event and `at` its `at`.
"""

from __future__ import annotations

from . import document
from . import layout as lay
from . import plan as plan_mod
from . import world as zw
from .events import AUTO_PREFIX, Refusal, standing
from .suggest import descends, landing, roads_by_node, suggest_road

ZONING_VERSION = "hand-1"
FULL = 360 * lay.UNIT
HALF_WEDGE = 20 * lay.UNIT  # a ring-1 road takes 20 degrees either side of its bearing at most
GOLDEN = 13750776405003785  # the golden angle, 137.50776405003785 degrees, in units of 1/100 degree times 10**12: whole numbers only, so a port matches to the unit
PLAZA = lay.PLAZA_PLACE


# ------------------------------------------------------------------------------------------------ directions ----
def bearing(k: int) -> int:
    """The bearing of the k-th ring-1 road (k = 0 for the first), in units of 1/100 degree clockwise from north, from 0 up to a full circle. The golden angle
    times k, rounded half up, in whole numbers."""
    return ((k * GOLDEN + 5 * 10**11) // 10**12) % FULL


def _sector(given: list[tuple[int, int]], k: int) -> tuple[int, int] | str:
    """The sector (lo, hi) of the k-th ring-1 road, or the reason there is none: "inside" (the bearing lies inside a sector given) or "border" (it is on the border of
    two sectors, with no room between them)."""
    b = bearing(k)
    for lo, hi in given:
        if 0 < (b - lo) % FULL < hi - lo:
            return "inside"
    right = min([(lo - b) % FULL for lo, hi in given], default=FULL)  # clockwise from the bearing to the next sector
    left = min([(b - hi) % FULL for lo, hi in given], default=FULL)  # anticlockwise, to the sector before it
    lo, hi = b - min(HALF_WEDGE, left), b + min(HALF_WEDGE, right)
    if hi <= lo:
        return "border"
    if lo + hi > FULL:  # the axis is past 180 degrees: the same sector, one turn back
        lo, hi = lo - FULL, hi - FULL
    return lo, hi


def capacity() -> int:
    """How many ring-1 roads the first ring holds: the sectors are asked for, one after the other, until there is none."""
    return len(sector_table())


def sector_table() -> list[tuple[int, int]]:
    """The sectors (lo, hi) of the directions 0, 1, 2, ..., in units of 1/100 degree, each asked for when the ones before it are given, until there is none."""
    given: list[tuple[int, int]] = []
    while True:
        found = _sector(given, len(given))
        if isinstance(found, str):
            return given
        given.append(found)


SECTORS = sector_table()  # the 13 sectors: the 14th bearing (347.60 degrees) lies inside the first
AVENUES = len(SECTORS)  # 13
REMEDY = "merge_roads"  # what the refusal `ring1_full` names: group similar avenues under a new one, which frees their directions


def tenths(span: int) -> int:
    """A width given in units of 1/100 degree, in whole tenths of a degree, rounded half up. The sectors tile the circle, so their widths differ in the hundredths (32.46 and 32.47, 12.52
    and 12.53) by no real difference: in tenths they are 325 and 125, and 400 for the widest."""
    return (span + 5) // 10


def ordinal(n: int) -> str:
    return f"{n}{'th' if n % 100 in (11, 12, 13) else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def ring1_full(number: int) -> Refusal:
    """The refusal when no direction is left for the `number`-th category of the first ring: it names the remedy."""
    return Refusal(f"the first ring has at most {AVENUES} avenues and all {AVENUES} directions are used, so the {ordinal(number)} category goes below an avenue, "
                   f"or similar avenues are merged under a new one ({REMEDY}) to free their directions", "ring1_full", limit=AVENUES, number=number, remedy=REMEDY)


def ring1_wedge(given: list[tuple[int, int]], k: int) -> tuple[int, int]:
    """The sector (lo, hi), in units of 1/100 degree, of the k-th direction when the sectors `given` belong to the earlier ones: the free arc around the bearing
    `bearing(k)`, at most `HALF_WEDGE` to either side of it, ending where the next sector begins on each side. The axis of the sector (the middle of lo and hi, the
    direction of the spoke) is kept between -180 and 180 degrees. `Refusal` with the id `ring1_full` (params `limit`, `number`, `remedy`) when the bearing has no room:
    it lies inside a sector given already, or on the border of two. The bearings and the sectors that come of them are fixed, so there are `AVENUES` = 13 directions,
    a town has at most 13 avenues (the roads of the first ring), and the 14th category goes below an avenue, or similar avenues are merged to free directions."""
    found = _sector(given, k)
    if not isinstance(found, str):
        return found
    if len(given) >= AVENUES:
        raise ring1_full(k + 1)
    where = "lies inside the sector of an earlier road" if found == "inside" else "is on the border of two sectors, with no room between them"
    raise Refusal(f"the first ring has no room for avenue number {k + 1}: its bearing, {bearing(k) / lay.UNIT:g} degrees, {where}", "ring1_full",
                  limit=AVENUES, number=k + 1, remedy=REMEDY)


# ---------------------------------------------------------------------------------------------------- the tree ----
class LiveTree:
    """The player's tree, read from the roads of a State as they are now (the engine asks a tree for the parent and the name of a topic, and whether it has one)."""

    def __init__(self, nodes: dict[str, dict]):
        self.nodes = nodes

    def __contains__(self, key: str) -> bool:
        return key in self.nodes

    def parent(self, key: str) -> str | None:
        node = self.nodes.get(key)
        return node["parent"] if node is not None else None

    def label(self, key: str) -> str:
        node = self.nodes.get(key)
        return node["name"] if node is not None else key


def new_plan(rule: dict) -> dict:
    """The plan of a world with nothing in it: no sector, no trunk, no street. The sectors are added as the ring-1 roads open."""
    return {"schema_version": plan_mod.SCHEMA_VERSION, "zoning_version": ZONING_VERSION, "mode": plan_mod.HAND,
            "params": {"home_max": lay.HOME_MAX, "trunk_min": lay.TRUNK_MIN, "centre_tag": None, "districts": districts_of(rule)},
            "ring1": [], "trunks": {}, "streets": {}, "sites": {}}


def districts_of(rule: dict) -> dict:
    return {"max": rule["max"], "min": rule["min"], "extract": plan_mod.DISTRICT_EXTRACT, "count": plan_mod.DISTRICT_COUNT}


# ------------------------------------------------------------------------------------------------ the engine ----
class HandWorld(zw.World):
    """One event's working copy of a hand-built world: the engine's `World` with the acts of a player. A road is placed where its parent's carrier trunk has room,
    a house on the lowest empty lot of its road, and nothing else moves. There is no limit of its own: a road holds as many houses as the player files on it."""

    def __init__(self, plan: zw.PlanView, tree: LiveTree, doc: dict, *, event_id: int):
        super().__init__(plan, tree, doc, event_id=event_id)
        for key in tree.nodes:  # every road the player has opened is a road, with a house on it yet or not
            place = lay.tag_place(key)
            if place not in self.road_def:
                self.register_road(place, key, ())

    def add_houses(self, road: str, pending: list[dict], trigger: str) -> None:
        """Put houses on a road. No split, no over: whether a road is crowded is a question for the player (`bibliopolis.suggest.crowded`)."""
        self.hold[road] = len(self.lots_on(road)) + len(pending)
        for h in pending:
            self.place_lot(road, h)
        self.hold.pop(road, None)

    def note(self, trigger: str, **entry) -> None:
        """An entry of the chronicle: the next number, the event, the arrivals so far and the kind of event, then what happened."""
        self.chronicle.append({"n": len(self.chronicle) + 1, "event_id": self.event_id, "seq": self.seq, "trigger": trigger, **entry})

    def open_road(self, key: str, label: str, parent_place: str, ids: list[str], trigger: str) -> None:
        """Open the road `key` and move the houses `ids` (all of them on `parent_place`) onto it, in the order they arrived. The houses that stay keep their lots."""
        place = lay.tag_place(key)
        lots = sorted((self.places.get(lay.article_place(h)) for h in ids), key=lambda lot: lot["seq"])
        before = len(self.lots_on(parent_place))
        for lot in lots:
            self.free_lot(lot)
        self.register_road(place, key, ())
        self.stats["splits"] += 1
        self.note(trigger, **{"from": parent_place, "to": place, "label": self.spec(place).label, "houses": [lot["article"] for lot in lots],
                              "count_before": before, "count_after": before - len(lots)})
        self.add_houses(place, [{"article": lot["article"], "tag": key, "seq": lot["seq"]} for lot in lots], trigger)

    def file_house(self, house: str, key: str, trigger: str) -> None:
        """Move one house onto the road `key`; its lot stays empty behind it."""
        lot = self.places.get(lay.article_place(house))
        place = lay.tag_place(key)
        self.free_lot(lot)
        self.add_houses(place, [{"article": house, "tag": key, "seq": lot["seq"]}], trigger)
        self.note(trigger, filed=house, left=lot["street"], joined=place)

    def put_again(self, keys: list[str], trigger: str) -> list[str]:
        """The roads `keys` (in the order they were opened) have moved: they stand below their new parents in the tree already. Their street records, ribs and lots go
        whole (their roads stay in the world as ghost roads, and the ground they claimed stays claimed), and their houses are put again, a road at a time and in the order
        they arrived. Returns the ids of those houses. A house of any other road keeps its lot."""
        places = {lay.tag_place(k) for k in keys}
        lots = sorted((lot for place in sorted(places) for lot in self.by_road().get(place, ())), key=lambda lot: lot["seq"])
        for place in sorted(places):
            rec = self.places.get(place)
            if rec is None:  # a road that never had a house, or lost them all in an earlier move
                continue
            for carrier in ([place] if "rib" in rec else []) + list(rec.get("lanes", [])):
                rib = self.places.get(carrier)["rib"]
                for slot in range(rib["slots"]):
                    self.places.delete(lay.reserved_place(rib["block"], slot))
                if carrier != place:
                    self.places.delete(carrier)
            self.places.delete(place)
        for lot in lots:
            self.places.delete(lay.article_place(lot["article"]))
        self._by_road = None
        for road in keys:
            batch = [{"article": lot["article"], "tag": road, "seq": lot["seq"]} for lot in lots if lot["tag"] == road]
            if batch:
                self.add_houses(lay.tag_place(road), batch, trigger)
        return [lot["article"] for lot in lots]

    def move_subtree(self, key: str, keys: list[str], was_below: str, below: str, trigger: str) -> list[str]:
        """The road `key` has moved: it and the roads below it (`keys`, in the order they were opened) stand again below their new parent (see `put_again`)."""
        ids = self.put_again(keys, trigger)
        self.note(trigger, moved=lay.tag_place(key), below=below, was_below=was_below, houses=ids)
        return ids

    def drop_line(self, place: str) -> None:
        """Take away the line of the avenue `place` with every road it carries (its spoke, its arcs, the roads of the ribs on it). Used when an avenue gives up its direction
        (it is merged, or moves below another road): the line would be a ghost lying over the line that the direction gets next, and nothing stands on it any more."""
        for rid, road in list(self.roads.items()):
            if road.get("trunk") == place or (road["street"] == place and road["kind"] in ("spoke", "arc")):
                self.roads.delete(rid)
        self.lines.delete(place)

    def merge_avenues(self, key: str, label: str, members: list[str], took: str, keys: list[str], trigger: str) -> list[str]:
        """The avenue `key` (in the tree and the plan already, with the direction of `took`) has the avenues `members` below it: they and the roads below them (`keys`)
        are put again (see `put_again`), after the lines of the members are taken away (`drop_line`: the direction is the new avenue's, or free), and one entry of the
        chronicle says so."""
        for m in members:
            self.drop_line(lay.tag_place(m))
        ids = self.put_again(keys, trigger)
        self.note(trigger, merged=lay.tag_place(key), label=label, members=[lay.tag_place(m) for m in members], took=lay.tag_place(took), houses=ids)
        return ids

    def relabel(self, keys: list[str]) -> None:
        """Write the names and addresses of the street records of the roads `keys` (parents first) again, from the tree as it is now."""
        for key in keys:
            place = lay.tag_place(key)
            rec = self.places.get(place)
            if rec is None:
                continue
            spec = self.spec(place)
            rec = self.places.mut(place)
            rec["address"] = list(spec.address)
            if "label" in rec or place not in self.plan.streets:
                rec["label"] = spec.label
            for lane in rec.get("lanes", []):
                lane_rec = self.places.mut(lane)
                lane_rec["address"], lane_rec["label"] = list(spec.address), spec.label


# --------------------------------------------------------------------------------------------------- the state ----
class State:
    """A world built by hand after some events: the rule in force, the roads (the player's tree, in the order they were opened), the houses and the road each stands
    on, and the world document of the engine. `apply` takes the next event; the rest is read from it."""

    def __init__(self, rule: dict):
        self.rule = dict(rule)
        self.nodes: dict[str, dict] = {}  # road id -> {"key", "name", "parent"}, in the order the roads were opened
        self.items: dict[str, dict] = {}  # house id -> its item, in arrival order
        self.road_of: dict[str, str | None] = {}  # house id -> the road it stands on; None: the root zone
        self.plan = new_plan(self.rule)
        self.tree = LiveTree(self.nodes)
        self.doc = zw.new_world(self.plan)
        self.held: dict[int, str] = {}  # direction number (0 to 12, see SECTORS) -> the avenue that holds it: a ring-1 road, or a road that moved away and keeps it
        self.kinds: dict[int, str] = {}  # seq -> kind of every event seen, standing or not
        self.effects: dict[int, dict] = {}  # seq -> {"houses": placed or moved by the event, "roads": opened by it}: what a later event can depend on

    # ---- events
    def apply(self, event: dict) -> None:
        """Take the next standing event. `Refusal`, and no change to the world, when the world does not take it."""
        getattr(self, "do_" + event["kind"])(event, event["payload"])
        self.kinds[event["seq"]] = event["kind"]

    def skip(self, event: dict) -> None:
        """Pass an event that does not count (an undo names it)."""
        self.kinds[event["seq"]] = event["kind"]

    def world(self, event: dict) -> HandWorld:
        return HandWorld(zw.PlanView(self.plan), self.tree, self.doc, event_id=event["seq"])

    def commit(self, w: HandWorld, event: dict, before: int) -> None:
        """Take the working copy as the world: its delta applied, `at` on the entries it wrote, the sectors of the ring-1 roads that stand."""
        for entry in w.chronicle[before:]:
            entry["at"] = event["at"]
        doc = zw.apply_delta(self.doc, w.delta())
        self.doc = {**doc, "districts": districts_of(self.rule), "composition": {**doc["composition"], "ring1": self.sectors()}}

    def sectors(self) -> list[dict]:
        """`composition.ring1`: the sector of every road that is a ring-1 road now, in the order the sectors were given."""
        return [{"place": r["place"], "label": r["label"], "weight": r["weight"], "from": r["wedge"][0], "to": r["wedge"][1], "span": round(r["wedge"][1] - r["wedge"][0], 3)}
                for r in self.plan["ring1"] if self.nodes[r["name"]]["parent"] is None]

    # ---- roads
    def free_direction(self) -> int:
        """The lowest number of a direction that no avenue holds: the next avenue takes it. A direction that a merge freed has a lower number than any that was never
        used, so freed directions come first, in the golden-angle order. `Refusal` (`ring1_full`, with the remedy) when all of them are held."""
        for k in range(AVENUES):
            if k not in self.held:
                return k
        raise ring1_full(AVENUES + 1)

    def direction_of(self, road: str) -> int | None:
        """The number of the direction that the road holds, None when it holds none."""
        return next((k for k, holder in self.held.items() if holder == road), None)

    def add_sector(self, key: str, name: str, direction: int) -> None:
        """Give the avenue `key` the direction `direction`: a trunk of the plan with the sector of that direction, and the street that the plan holds for it."""
        place = lay.tag_place(key)
        wedge = SECTORS[direction]
        lo, hi = plan_mod.deg(wedge[0]), plan_mod.deg(wedge[1])
        self.held[direction] = key
        self.plan["ring1"].append({"place": place, "name": key, "label": name, "weight": 0, "wedge": [lo, hi]})
        self.plan["trunks"][place] = {"name": key, "label": name, "ring": 1, "role": "ring1", "side": 0, "parent": None, "line": place, "index": 0,
                                      "wedge": [lo, hi], "inner": [lo, hi], "heavy": None, "left": [], "right": []}
        self.plan["streets"][place] = {"name": key, "kind": "leaf", "ring": 1, "label": name, "address": [name], "parent": None, "carrier": place,
                                       "collapsed": [], "absorbed": [], "ribs": [], "weight": 0, "order": len(self.plan["ring1"]) - 1}
        self.plan["sites"][key] = place

    def subtree(self, key: str) -> list[str]:
        """The road `key` and every road below it, in the order the roads were opened (a road that moved stays where it was in that order)."""
        below, todo = {key}, [key]
        while todo:
            top = todo.pop()
            for k, node in self.nodes.items():
                if node["parent"] == top and k not in below:
                    below.add(k)
                    todo.append(k)
        return [k for k in self.nodes if k in below]

    def houses_below(self, road: str) -> list[str]:
        """The houses that stand on the road or on a road below it, in arrival order."""
        roads = set(self.subtree(road))
        return [h for h in self.items if self.road_of[h] in roads]

    def widest_avenue(self, members: list[str]) -> str:
        """The avenue of `members` whose direction has the widest sector (`SECTORS`, the widths compared in whole tenths of a degree, `tenths`): a merge gives that sector to the
        new avenue, which carries the houses of all of them and needs the room. Of two with sectors as wide, the one with the most houses on it and below it; then the lower number."""
        def rank(m: str) -> tuple[int, int, int]:
            k = self.direction_of(m)
            return -tenths(SECTORS[k][1] - SECTORS[k][0]), -len(self.houses_below(m)), k

        return min(members, key=rank)

    def houses_at(self, road: str | None) -> list[str]:
        """The houses that stand directly on a road (None: the root zone), in arrival order."""
        return [h for h in self.items if self.road_of[h] == road]

    def where(self, road: str | None) -> str:
        return "the root zone" if road is None else f"the road {road!r}"

    def open(self, w: HandWorld, key: str, name: str, parent: str | None, ids: list[str], trigger: str, direction: int | None, node: dict | None = None) -> None:
        """Open a road: its node in the player's tree (`topic` is the OpenAlex node it stands for, or None), its direction (a number) when it is a ring-1 road, then the
        engine's `open_road`."""
        self.nodes[key] = {"key": key, "name": name, "parent": parent, "topic": node}
        if direction is not None:
            self.add_sector(key, name, direction)
        w.open_road(key, name, zw.ROOT_PLACE if parent is None else lay.tag_place(parent), ids, trigger)
        for h in ids:
            self.road_of[h] = key

    # ---- the events
    def do_add_item(self, e: dict, p: dict) -> None:
        item = p["item"]
        if item["id"] in self.items:
            raise Refusal(f"{item['id']!r} is a house already", "house_exists", house=item["id"])
        land = landing(self, item) if self.rule["auto"] else None  # (a road only under `auto`; otherwise the root zone)
        w, before = self.world(e), len(self.doc["chronicle"])
        w.seq += 1  # the arrival number: log order
        w.arrival_ids.add(item["id"])
        w.add_houses(zw.ROOT_PLACE if land is None else lay.tag_place(land), [{"article": item["id"], "tag": land, "seq": w.seq}], "add_item")
        self.items[item["id"]] = item
        self.road_of[item["id"]] = land
        touched, opened = [item["id"]], []
        self.settle(w, e, land, touched, opened)
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": touched, "roads": opened}

    def settle(self, w: HandWorld, e: dict, start: str | None, touched: list[str], opened: list[str]) -> None:
        """After an arrival, under the rule `auto`: the place the house stands on (`start`: a road, or None for the root zone) is looked at, and while it holds more than `max`
        houses directly, a road is opened for the largest group of its houses (`bibliopolis.suggest.suggest_road`: one level of OpenAlex below the place) and named after the
        node, with the mechanics of `open_road`: the houses that stay keep their lots. Each road so opened is looked at in turn, in the order they were opened, so that one
        that holds more than `max` houses splits again. The roads are `auto:<seq>`, `auto:<seq>.2`, ... in that order, roads like any other afterwards. A place with no
        suggestion (no group of `min`, or a road for a topic, which is not split), or the root zone when all 13 directions of the first ring are used, is left as it is,
        crowded (`bibliopolis.suggest.crowded` says so). Nothing without `auto`."""
        if not self.rule["auto"]:
            return
        n, queue, seen = 0, [start], set(touched)
        while queue:
            at = queue.pop(0)
            while self.count(at) > self.rule["max"]:
                suggestion = suggest_road(self, at)
                if suggestion is None:
                    break
                try:
                    direction = self.free_direction() if at is None else None
                except Refusal:
                    break
                n += 1
                key = f"{AUTO_PREFIX}{e['seq']}" + (f".{n}" if n > 1 else "")
                self.open(w, key, suggestion["name"], at, suggestion["houses"], "add_item", direction, suggestion["topic"])
                touched.extend(h for h in suggestion["houses"] if h not in seen)
                seen.update(suggestion["houses"])
                opened.append(key)
                queue.append(key)

    def do_open_road(self, e: dict, p: dict) -> None:
        key, name, parent, ids, node = p["road"], p["name"], p["parent"], p["houses"], p.get("topic")  # (the event as `append` keeps it has the key; a log made elsewhere may leave it out)
        least = self.rule["min"]
        if key in self.nodes:
            raise Refusal(f"there is a road {key!r} already", "road_exists", road=key)
        if parent is not None and parent not in self.nodes:
            raise Refusal(f"there is no road {parent!r} to open a road below", "parent_missing", parent=parent)
        held = self.houses_at(parent)
        if len(held) < least:
            raise Refusal(f"{self.where(parent)} holds {len(held)} houses directly; a road is opened from a place that holds at least {least}", "too_few_here",
                          road=parent, held=len(held), least=least)
        if len(ids) < least:
            raise Refusal(f"{len(ids)} houses are chosen; a road takes at least {least}", "too_few_chosen", chosen=len(ids), least=least)
        for h in ids:
            if h not in self.items:
                raise Refusal(f"{h!r} is not a house", "not_a_house", house=h)
            if self.road_of[h] != parent:
                raise Refusal(f"the house {h!r} does not stand directly on {self.where(parent)}; it stands on {self.where(self.road_of[h])}", "house_elsewhere",
                              house=h, road=parent, on=self.road_of[h])
        if node is not None:
            taken = roads_by_node(self).get((node["level"], node["id"]))
            if taken is not None:
                raise Refusal(f"the road {taken!r} stands for the {node['level']} {node['id']!r} already; two roads never stand for one node", "node_taken",
                              level=node["level"], topic=node["id"], road=taken)
            for h in ids:
                if not descends(self.items[h]["openalex"], node["level"], node["id"]):
                    raise Refusal(f"the house {h!r} is not under the {node['level']} {node['id']!r}, which the road stands for", "house_not_under_node",
                                  house=h, level=node["level"], topic=node["id"])
        direction = self.free_direction() if parent is None else None  # (may refuse: before anything changes)
        w, before = self.world(e), len(self.doc["chronicle"])
        self.open(w, key, name, parent, ids, "open_road", direction, node)
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": list(ids), "roads": [key]}

    def do_file(self, e: dict, p: dict) -> None:
        house, key = p["house"], p["road"]
        if house not in self.items:
            raise Refusal(f"{house!r} is not a house", "not_a_house", house=house)
        if key not in self.nodes:
            raise Refusal(f"there is no road {key!r}", "no_road", road=key)
        if self.road_of[house] == key:
            raise Refusal(f"the house {house!r} stands on the road {key!r} already", "already_there", house=house, road=key)
        w, before = self.world(e), len(self.doc["chronicle"])
        w.file_house(house, key, "file")
        self.road_of[house] = key
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [house], "roads": []}

    def do_rename_road(self, e: dict, p: dict) -> None:
        key, name = p["road"], p["name"]
        if key not in self.nodes:
            raise Refusal(f"there is no road {key!r}", "no_road", road=key)
        was = self.nodes[key]["name"]
        if was == name:
            raise Refusal(f"the road {key!r} is called {name!r} already", "same_name", road=key, name=name)
        self.nodes[key]["name"] = name
        place = lay.tag_place(key)
        if place in self.plan["streets"]:  # a ring-1 road: the plan holds its name too
            self.plan["trunks"][place]["label"] = name
            self.plan["streets"][place].update(label=name, address=[name])
            for sector in self.plan["ring1"]:
                if sector["place"] == place:
                    sector["label"] = name
        w, before = self.world(e), len(self.doc["chronicle"])
        w.relabel(self.subtree(key))
        w.note("rename_road", renamed=place, was=was, label=name)
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [], "roads": []}

    def do_move_road(self, e: dict, p: dict) -> None:
        key, parent = p["road"], p["parent"]
        if key not in self.nodes:
            raise Refusal(f"there is no road {key!r}", "no_road", road=key)
        if parent not in self.nodes:
            raise Refusal(f"there is no road {parent!r} to move a road below", "move_parent_missing", parent=parent)
        below = self.subtree(key)
        if parent in below:
            raise Refusal(f"the road {key!r} cannot move below {parent!r}, which is itself or one of its own roads", "move_into_itself", road=key, parent=parent)
        old = self.nodes[key]["parent"]
        if old == parent:
            raise Refusal(f"the road {key!r} is below {parent!r} already", "already_below", road=key, parent=parent)
        moved = [h for h in self.items if self.road_of[h] in below]
        self.nodes[key]["parent"] = parent
        if old is None:  # an avenue below another road is no avenue: its direction is free (the next avenue takes the lowest free number)
            del self.held[self.direction_of(key)]
        w, before = self.world(e), len(self.doc["chronicle"])
        if old is None:
            w.drop_line(lay.tag_place(key))  # ... and nothing stands on its line any more: the next avenue of that direction would have its line over it
        w.move_subtree(key, below, PLAZA if old is None else lay.tag_place(old), lay.tag_place(parent), "move_road")
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": moved, "roads": []}

    def do_merge_roads(self, e: dict, p: dict) -> None:
        key, name, members, node = p["road"], p["name"], p["members"], p.get("topic")
        if key in self.nodes:
            raise Refusal(f"there is a road {key!r} already", "road_exists", road=key)
        for m in members:
            if m not in self.nodes:
                raise Refusal(f"there is no road {m!r}", "no_road", road=m)
            if self.nodes[m]["parent"] is not None:
                raise Refusal(f"the road {m!r} is not an avenue: it is below {self.nodes[m]['parent']!r}, and only avenues of the first ring are merged", "not_an_avenue", road=m)
        below = {m: set(self.subtree(m)) for m in members}  # (before anything moves)
        keys = [k for k in self.nodes if any(k in roads for roads in below.values())]  # in the order the roads were opened
        moved = [h for h in self.items if any(self.road_of[h] in roads for roads in below.values())]
        if node is not None:
            taken = roads_by_node(self).get((node["level"], node["id"]))
            if taken is not None:
                raise Refusal(f"the road {taken!r} stands for the {node['level']} {node['id']!r} already; two roads never stand for one node", "node_taken",
                              level=node["level"], topic=node["id"], road=taken)
            for h in moved:
                if not descends(self.items[h]["openalex"], node["level"], node["id"]):
                    raise Refusal(f"the house {h!r} is not under the {node['level']} {node['id']!r}, which the road stands for", "house_not_under_node",
                                  house=h, level=node["level"], topic=node["id"])
        held = {m: self.direction_of(m) for m in members}
        took = self.widest_avenue(members)  # the widest sector; of two as wide, the most houses on it and below it; then the lower number
        for m in members:  # the directions of the members are free; the new avenue takes the one of the member with the widest sector
            del self.held[held[m]]
        self.nodes[key] = {"key": key, "name": name, "parent": None, "topic": node}
        for m in members:
            self.nodes[m]["parent"] = key
        self.add_sector(key, name, held[took])
        w, before = self.world(e), len(self.doc["chronicle"])
        w.merge_avenues(key, name, members, took, keys, "merge_roads")
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": moved, "roads": [key]}

    def do_undo(self, e: dict, p: dict) -> None:
        w, before = self.world(e), len(self.doc["chronicle"])
        w.note("undo", undone=p["seq"], of=self.kinds.get(p["seq"], "?"))
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [], "roads": []}

    def do_set_rule(self, e: dict, p: dict) -> None:
        rule = {"max": p["max"], "min": p["min"], "auto": p["auto"]}
        if rule == self.rule:
            raise Refusal("the rule is this already", "rule_unchanged", max=rule["max"], min=rule["min"], auto=rule["auto"])
        self.rule = rule
        self.plan["params"]["districts"] = districts_of(rule)
        w, before = self.world(e), len(self.doc["chronicle"])
        w.note("set_rule", rule=dict(rule))
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [], "roads": []}

    # ---- what the world holds
    def count(self, road: str | None) -> int:
        return sum(1 for h in self.items if self.road_of[h] == road)

    def lots(self) -> dict[str, dict]:
        """house id -> its lot record in the world document."""
        return zw.houses(self.doc)

    def city(self, with_coast: bool = True) -> dict:
        """The layout v4 document of the world: what `build` writes for a library, for a viewer to read."""
        return document.world_layout(self.doc, with_coast=with_coast)


def fold(events: list[dict], rule: dict) -> State:
    """The world after the events that count (`events.standing`), in log order, from the rule `rule` it started with. `Refusal` naming the event when one cannot apply."""
    keep = standing(events)
    state = State(rule)
    for e in events:
        try:
            if e["seq"] in keep:
                state.apply(e)
            else:
                state.skip(e)
        except Refusal as why:
            raise why.within(e["seq"], e["kind"]) from None
    return state
