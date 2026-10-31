"""A world built by hand: the fold of an event log (bibliopolis.events) into a city.

    fold(events, rule) -> State      the world after the standing events, in log order; same log, same bytes
    State.apply(event)               one more event; `Refusal` (and no change) when the world does not take it
    State.city()                     the layout v4 document of the world (bibliopolis.document), the shape `build` writes

There is no library to plan from, so the plan grows with the world and never changes what it has given:

  the ring road   the root of the player's tree, `Knowledge` until `rename_road` names it (`road` null), a closed circular road round the town hall (bibliopolis.ring).
                  The world starts with it, empty, and a house starts on it (`add_item`) on the first free slot of its lap in the fill order, as in a grown city: north, half way
                  round, the quarters, the eighths, ..., so the houses spread round the whole ring. Its radius is `ring_radius(rule)`: it follows the rule.
  a road          a named category the player opens (`open_road`) with a chosen set of houses. It is a topic node of the player's tree. Below the ring road it is a
                  ring-1 road and takes the next direction of the golden angle (below); below a road it is laid out as the engine lays out a topic the plan does
                  not hold: a rib on the line of its ring-1 road. No trunk is promoted and no heavy path changes (a stated limitation).
  directions      the k-th direction (k = 0, 1, 2, ...) has the bearing k * 137.50776405003785 degrees, clockwise from north, in whole units of 1/100 degree, whatever the
                  number of directions is. With N = `rule.branches` directions the spoke of an avenue runs ON its bearing and its sector is the nearest-bearing cell among the
                  N bearings, cut to 20 degrees either side (`sector_table`); a larger N only narrows the sectors and moves no bearing. An avenue holds one direction number and
                  gives it up when it is no avenue any more: when it moves below another road, or is merged. A new avenue takes the lowest number that no avenue holds.
  branches        a road holds at most N roads directly, at every level (the ring road: N avenues). The event that would pass it is refused (`branches_full`, and the remedy
                  `merge_roads`): the next category goes below one of the roads, or similar roads are merged first. Under `auto` a split that would pass N merges the best
                  suggestion first (`bibliopolis.suggest.suggest_merge`), then splits.
  merging         `merge_roads` groups roads that stand directly below one road (the ring road: avenues) upward under a new road that takes their place there. A new avenue takes the
                  direction (sector and bearing) of the member whose sector is the widest (widths are compared in whole tenths of a degree, rounded half up; of two as wide, the one
                  with the most houses on it and below it, then the lower number), the others' numbers are free again and the next avenues take them, the lowest number first. The
                  members stand below the new road one ring down, as after a move of a road: only the houses of their subtrees are put again.
  stability       a house stays on its lot unless an event moves it: opening a road moves the houses chosen, filing a house moves that house, moving a road moves
                  the houses of its subtree. The houses that stay keep their lots, whatever holes the others leave. (`undo` may re-place what came after the event
                  it takes back: the fold of the log without that event.)
  a node          a road may stand for one OpenAlex node (`open_road` `topic`, `{id, level, name}`): the houses chosen are under it, and no other road stands for it.
  the rule        `max` and `min` are the limits of the player's district rule (`open_road` needs `min` houses; `crowded` lists what is above `max`), `branches` is N. The world
                  marks nothing over and splits nothing by itself, except under `auto` (bibliopolis.suggest): an arriving house stands on the deepest road whose node
                  it is under (the ring road when there is none), and a place that then holds more than `max` houses opens a road for its largest group, one level of
                  OpenAlex below the place, with the same mechanics as `open_road`, so even then the houses that stay keep their lots. A road so opened is split in
                  turn while it holds more than `max`.
  a new radius    the ring road holds `max` houses between the gates of its N bearings, so a rule with another N, or a `max` that asks for another radius (`ring_radius`), lays the
                  whole world out again on the new ring: every house stays on its road and in its place along its street, every avenue keeps its bearing. The houses of the ring keep
                  their order round it (the laps in turn, each from the north) and take the first slots of the fill order of the new laps, matched by rank (`put_ring_again`).
  the chronicle   one entry for each road opened (the shape of a split), house filed, road renamed or moved, undo and change of rule, in log order; `event_id` is the
                  `seq` of the event and `at` its `at`.
  an annex        an item that exists for another item (`annex_of` and `annex_form` of an item, or the event `annex`) is no house: it has no lot and no road, and stands beside its
                  house as a wing or a mailbox (bibliopolis.world: `put_annex`). An item whose house stands is an annex at once; one whose house has not arrived is an ordinary
                  house that waits (its item says `annex_of`), and when the house arrives every house that waited for it is ABSORBED: it leaves its lot (a lot of a road stays
                  reserved, a lot of the ring leaves nothing) and becomes an annex, and every other house keeps its lot. The event `annex` does the same for a link learned later.
                  The annexes are `State.annexes`; `State.items` and `State.road_of` are the houses that stand on a lot, so a count of `max` and `min` never has them. An annex stands
                  where its house stands: a move, a merge, a split or a new radius needs nothing for it, and an undo is the fold of the log without the event, as for every event.
"""

from __future__ import annotations

import copy
import functools

from . import document
from . import layout as lay
from . import plan as plan_mod
from . import ring as ring_mod
from . import world as zw
from .events import AUTO_PREFIX, BRANCHES_LEAST, DEFAULT_RULE, RING_LIMIT, RULE_KEYS, Refusal, house_is_annex, standing
from .suggest import descends, landing, roads_by_node, suggest_merge, suggest_road

ZONING_VERSION = "hand-1"
FULL = 360 * lay.UNIT
HALF_WEDGE = 20 * lay.UNIT  # a ring-1 road takes 20 degrees either side of its bearing at most
GOLDEN = 13750776405003785  # the golden angle, 137.50776405003785 degrees, in units of 1/100 degree times 10**12: whole numbers only, so a port matches to the unit
PLAZA = lay.PLAZA_PLACE
REMEDY = "merge_roads"  # what the refusal `branches_full` names: group similar roads under a new one, which makes room


# ------------------------------------------------------------------------------------------------ directions ----
def bearing(k: int) -> int:
    """The bearing of the k-th direction (k = 0 for the first), in units of 1/100 degree clockwise from north, from 0 up to a full circle. The golden angle times k, rounded half
    up, in whole numbers. It never depends on how many directions there are: raising `branches` adds bearings and moves none."""
    return ((k * GOLDEN + 5 * 10**11) // 10**12) % FULL


@functools.cache
def sector_table(n: int) -> tuple[tuple[int, int, int], ...]:
    """The sectors of the ring road when a road holds `n` branches: for each direction number k, 0 to n-1, `(lo, hi, axis)` in units of 1/100 degree. The spoke of the direction
    runs ON its bearing (`axis`); its sector is the NEAREST-BEARING CELL among the n bearings: from the midpoint with the bearing before it to the midpoint with the one after it
    (a midpoint of an odd gap is rounded up, so that two cells share it), cut to at most `HALF_WEDGE` either side of the bearing. The cell may be wider on one side of the
    bearing than on the other. The cells of n directions tile the circle (as far as the cut leaves them) and a larger n only narrows them. The axis is kept between -180
    and 180 degrees, and `lo <= axis <= hi`."""
    bearings = [bearing(k) for k in range(n)]
    assert len(set(bearings)) == n, f"{n} directions: two of them have the same bearing"  # (they are distinct for every n a rule allows, up to BRANCHES_LIMIT)
    order = sorted(range(n), key=bearings.__getitem__)
    out: list[tuple[int, int, int] | None] = [None] * n
    for at, k in enumerate(order):
        b = bearings[k]
        before = (b - bearings[order[at - 1]]) % FULL or FULL  # to the bearing before it (the whole circle when it is alone)
        after = (bearings[order[(at + 1) % n]] - b) % FULL or FULL
        lo, hi = b - min(HALF_WEDGE, before // 2), b + min(HALF_WEDGE, (after + 1) // 2)
        turn = FULL if b > FULL // 2 else 0  # the axis is past 180 degrees: the same sector, one turn back
        out[k] = (lo - turn, hi - turn, b - turn)
    return tuple(out)  # type: ignore[arg-type]


land_of = ring_mod.land_of  # the part of a sector an avenue builds in (the engine decides it, bibliopolis.ring: the radius of the ring gives the narrowest land its arc)


def tenths(span: int) -> int:
    """A width given in units of 1/100 degree, in whole tenths of a degree, rounded half up. Sectors that tile the circle differ in the hundredths by no real difference: in tenths
    the widths of the sectors of one table are compared."""
    return (span + 5) // 10


def ring_radius(rule: dict) -> float:
    """The lane radius of the first lap of the ring road for the rule: the least that holds `max` houses between the gates (the bearings of all `branches` directions, so
    that an avenue that opens later never moves a house of the ring) and gives the narrowest LAND the arc of an avenue at the ring's outer edge
    (`bibliopolis.ring.ring_radius_for`; the land of a direction is the part of its sector within the narrower side of its spoke, `land_of`). This is the one place the radius comes
    from: a change of rule that changes it lays the world out again."""
    return _radius(rule["branches"], rule["max"])


@functools.cache
def _radius(branches: int, top: int) -> float:
    table = sector_table(branches)
    return ring_mod.ring_radius_for(ring_mod.axis_gates([axis for _, _, axis in table]), top, ring_mod.sector_min([land_of(lo, hi, axis) for lo, hi, axis in table]))


def ordinal(n: int) -> str:
    return f"{n}{'th' if n % 100 in (11, 12, 13) else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def branches_full(road: str | None, limit: int, number: int) -> Refusal:
    """The refusal when `road` (a road id, or None for the ring road) holds `limit` roads directly already, and the `number`-th is asked for: it names the remedy."""
    holder, what = ("the ring road", "avenues") if road is None else (f"the road {road!r}", "roads")
    return Refusal(f"{holder} holds {limit} {what} directly, the most the rule allows (branches {limit}), so the {ordinal(number)} category goes below one of them, "
                   f"or similar {what} are merged under a new one ({REMEDY}) to make room", "branches_full", road=road, limit=limit, number=number, remedy=REMEDY)


def too_deep(road: str, ring: int) -> Refusal:
    """The refusal when an event would put a road in a ring deeper than `RING_LIMIT`: `road` is the road the event is about, `ring` the deepest ring that any road would stand in."""
    return Refusal(f"the road {road!r} would put a road in ring {ring}; the most the engine takes is ring {RING_LIMIT}", "too_deep", road=road, ring=ring, limit=RING_LIMIT)


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


def ring_params(rule: dict) -> dict:
    """`params.ring` for the rule: the label, the radius, and the sectors and spoke axes of all N directions (degrees, in the order of the direction numbers), so that the
    gates of the ring are all there from day one."""
    table = sector_table(rule["branches"])
    return {"label": ring_mod.RING_LABEL, "radius": ring_radius(rule), "sectors": [[plan_mod.deg(lo), plan_mod.deg(hi)] for lo, hi, _ in table],
            "axes": [plan_mod.deg(axis) for _, _, axis in table]}


def new_plan(rule: dict) -> dict:
    """The plan of a world with nothing in it: the ring road with the sectors and axes of its directions (`params.ring`), no trunk, no street. The trunks and streets are
    added as the ring-1 roads open."""
    return {"schema_version": plan_mod.SCHEMA_VERSION, "zoning_version": ZONING_VERSION, "mode": plan_mod.HAND,
            "params": {"home_max": lay.HOME_MAX, "trunk_min": lay.TRUNK_MIN, "centre_tag": None, "districts": districts_of(rule), "ring": ring_params(rule)},
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

    def absorb(self, house: str, parent: str, form: str, trigger: str) -> None:
        """A house that stands on a lot becomes an annex of the house `parent` (a `form`: wing or mailbox): its lot is freed (a lot of a road stays reserved, a lot of the ring leaves
        nothing), its record is the annex record (it keeps its arrival number) and one entry `absorbed` of the chronicle says where it was."""
        lot = self.places.get(lay.article_place(house))
        self.free_lot(lot)
        self.put_annex(house, parent, form, lot["seq"])
        self.note(trigger, absorbed=house, parent=parent, form=form, left=lot["street"])

    def file_house(self, house: str, key: str, trigger: str) -> None:
        """Move one house onto the road `key`; its lot stays empty behind it."""
        lot = self.places.get(lay.article_place(house))
        place = lay.tag_place(key)
        self.free_lot(lot)
        self.add_houses(place, [{"article": house, "tag": key, "seq": lot["seq"]}], trigger)
        self.note(trigger, filed=house, left=lot["street"], joined=place)

    def put_ring_again(self, lots: list[dict]) -> None:
        """Put the houses of the ring road again, on the new ring: `lots` are their old lots in the order round the ring (the laps in turn, each from the north clockwise). The m
        houses take the first m slots of the fill orders of the laps, the first lap's slots before the second's, and are matched to them by rank, the slots in the order round the
        ring: nobody passes another, a hole closes, and the slots they take are the ones a ring of m houses that never lost one holds (a lap opens when the laps that stand
        are too few)."""
        need = len(lots)
        while sum(self.places.get(lap)["ring"]["slots"] for lap in self.laps()) < need:
            self.open_lap()
        laps = self.laps()
        fill = [(k, slot) for k, lap in enumerate(laps) for slot in ring_mod.ring_fill_order(self.places.get(lap)["ring"]["slots"])][:need]
        for lot, (k, slot) in zip(lots, sorted(fill)):
            self.put_ring(lot["article"], lot["tag"], lot["seq"], track=False, at=(laps[k], slot))

    def put_again(self, keys: list[str], trigger: str) -> list[str]:
        """The roads `keys` (in the order they were opened) have moved: they stand below their new parents in the tree already. Their street records, ribs and lots go
        whole (their roads stay in the world as ghost roads, their ribs in the logs of their lines as ghosts: the ground they claimed stays claimed), and their houses are put
        again, a road at a time and in the order they arrived. Returns the ids of those houses. A house of any other road keeps its lot."""
        places = {lay.tag_place(k) for k in keys}
        lots = sorted((lot for place in sorted(places) for lot in self.by_road().get(place, ())), key=lambda lot: lot["seq"])
        for place in sorted(places):
            rec = self.places.get(place)
            if rec is None:  # a road that never had a house, or lost them all in an earlier move
                continue
            if "rib" in rec:
                rib = rec["rib"]
                self.ghost_rib(place, rib["line"])  # (the rib stays in the log of its line, with its width: the ground it claimed stays claimed)
                for slot in range(rib["slots"]):
                    self.places.delete(lay.reserved_place(rib["block"], slot))
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

    def merge_roads(self, key: str, label: str, members: list[str], took: str, keys: list[str], trigger: str, below: str) -> list[str]:
        """The road `key` (in the tree already, standing below the place `below`: the town hall for a new avenue, which has the direction of `took`) has the roads `members` below
        it: they and the roads below them (`keys`) are put again (see `put_again`), after the lines of the members are taken away when they are avenues (`drop_line`: the
        direction is the new avenue's, or free), and one entry of the chronicle says so."""
        place = lay.tag_place(key)
        if place not in self.road_def:  # (a merge that the rule makes in the middle of an arrival: the road is new to this working copy)
            self.register_road(place, key, ())
        if below == PLAZA:
            for m in members:
                self.drop_line(lay.tag_place(m))
        ids = self.put_again(keys, trigger)
        self.note(trigger, merged=place, label=label, members=[lay.tag_place(m) for m in members], below=below, took=lay.tag_place(took), houses=ids)
        return ids

    def relabel_ring(self, name: str) -> None:
        """Write the name of the ring road, and of every lap of it, again."""
        for lap in self.laps():
            rec = self.places.mut(lap)
            rec["label"], rec["address"] = name, [name]

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


# --------------------------------------------------------------------------------------------------- the state ----
class State:
    """A world built by hand after some events: the rule in force, the roads (the player's tree, in the order they were opened), the houses and the road each stands
    on, and the world document of the engine. `apply` takes the next event; the rest is read from it."""

    def __init__(self, rule: dict):
        self.rule = {**DEFAULT_RULE, **rule}  # (every key: a rule a test or a caller gives without `branches` has the default)
        self.nodes: dict[str, dict] = {}  # road id -> {"key", "name", "parent"}, in the order the roads were opened
        self.items: dict[str, dict] = {}  # house id -> its item, in arrival order: the houses that stand on a lot (an item that waits for its house is one of them)
        self.road_of: dict[str, str | None] = {}  # house id -> the road it stands on; None: the ring road
        self.annexes: dict[str, dict] = {}  # item id -> {"parent": the house it stands beside, "form": wing or mailbox}: the items that have no lot, in the order they became annexes
        self.plan = new_plan(self.rule)
        self.tree = LiveTree(self.nodes)
        self.doc = zw.new_world(self.plan)
        self.held: dict[int, str] = {}  # direction number (0 to N-1, see `sector_table`) -> the avenue that holds it
        self.kinds: dict[int, str] = {}  # seq -> kind of every event seen, standing or not
        self.effects: dict[int, dict] = {}  # seq -> {"houses": placed or moved by the event, "roads": opened by it}: what a later event can depend on

    # ---- all or nothing
    def snapshot(self) -> dict:
        """Everything that an event may change in this State, kept so that `restore` can put it back (`Journal.append` takes one before it applies an event). The dictionaries are copies;
        the records of `nodes` are copied too, since a rename or a move changes them in place, and the plan is copied whole; the document is the same object, since it is never changed
        (a new one takes its place when an event is committed, `zw.apply_delta`). `vars(State)` is this and the live tree, which reads `nodes`: a test holds the two together."""
        return {"rule": dict(self.rule), "nodes": {k: dict(v) for k, v in self.nodes.items()}, "items": dict(self.items), "road_of": dict(self.road_of), "annexes": dict(self.annexes),
                "plan": copy.deepcopy(self.plan), "doc": self.doc, "held": dict(self.held), "kinds": dict(self.kinds), "effects": dict(self.effects)}

    def restore(self, saved: dict) -> None:
        """Put back what `snapshot` kept. The dictionaries `nodes`, `items`, `road_of`, `annexes`, `plan`, `held`, `kinds` and `effects` are emptied and filled again, not replaced, so that whoever holds
        one (the live tree holds `nodes`) still holds the State's. What `snapshot` copied one level down is replaced: the record of each road in `nodes`, and `rule`, and the document, which
        is a new object at every commit; a reference to one of those taken before a failed event is not the State's afterwards."""
        self.rule, self.doc = saved["rule"], saved["doc"]
        for name in ("nodes", "items", "road_of", "annexes", "plan", "held", "kinds", "effects"):
            current = getattr(self, name)
            current.clear()
            current.update(saved[name])

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

    def commit(self, w: HandWorld, event: dict, before: int, base: dict | None = None) -> None:
        """Take the working copy as the world: its delta applied (to `base`, the world a layout again starts from, else to the world as it is), `at` on the entries it
        wrote, the sectors of the ring-1 roads that stand."""
        for entry in w.chronicle[before:]:
            entry["at"] = event["at"]
        doc = zw.apply_delta(self.doc if base is None else base, w.delta())
        self.doc = {**doc, "districts": districts_of(self.rule), "composition": {**doc["composition"], "ring1": self.sectors()}}

    def sectors(self) -> list[dict]:
        """`composition.ring1`: the sector of every road that is a ring-1 road now, in the order the sectors were given."""
        return [{"place": r["place"], "label": r["label"], "weight": r["weight"], "from": r["wedge"][0], "to": r["wedge"][1], "span": round(r["wedge"][1] - r["wedge"][0], 3),
                 "axis": r["axis"]} for r in self.plan["ring1"] if self.nodes[r["name"]]["parent"] is None]

    # ---- roads
    def free_direction(self) -> int:
        """The lowest number of a direction that no avenue holds: the next avenue takes it. A direction that a merge freed has a lower number than any that was never
        used, so freed directions come first, in the golden-angle order. `Refusal` (`branches_full`, with the remedy) when all N of them are held."""
        for k in range(self.rule["branches"]):
            if k not in self.held:
                return k
        raise branches_full(None, self.rule["branches"], self.rule["branches"] + 1)

    def direction_of(self, road: str) -> int | None:
        """The number of the direction that the road holds, None when it holds none."""
        return next((k for k, holder in self.held.items() if holder == road), None)

    def children(self, parent: str | None) -> list[str]:
        """The roads that stand directly below `parent` (None: the avenues), in the order they were opened."""
        return [k for k, node in self.nodes.items() if node["parent"] == parent]

    def room_at(self, parent: str | None) -> None:
        """`Refusal` (`branches_full`) when `parent` (a road id, None for the ring road) holds `branches` roads directly already: one more is not taken."""
        held, limit = len(self.children(parent)), self.rule["branches"]
        if held >= limit:
            raise branches_full(parent, limit, held + 1)

    def least_branches(self) -> tuple[int, str | None]:
        """The least `branches` the world as it stands allows, and the road that asks for it (None: the ring road). The ring road needs one more than the highest direction number
        an avenue holds (the table of fewer directions has no such number); any other road needs as many as it holds roads directly."""
        need, who = max([BRANCHES_LEAST, *(k + 1 for k in self.held)]), None
        for parent in dict.fromkeys(node["parent"] for node in self.nodes.values() if node["parent"] is not None):
            held = len(self.children(parent))
            if held > need:
                need, who = held, parent
        return need, who

    def sector_records(self, direction: int) -> tuple[list[float], float, list[float]]:
        """(the sector, the axis, the land) of a direction for the rule in force, in degrees: the sector `[lo, hi]`, the bearing of the spoke, and the wedge `[lo, hi]` the
        avenue builds in (`land_of`)."""
        lo, hi, axis = sector_table(self.rule["branches"])[direction]
        land = land_of(lo, hi, axis)
        return [plan_mod.deg(lo), plan_mod.deg(hi)], plan_mod.deg(axis), [plan_mod.deg(land[0]), plan_mod.deg(land[1])]

    def add_sector(self, key: str, name: str, direction: int) -> None:
        """Give the avenue `key` the direction `direction`: a trunk of the plan with the land of that direction, and the street that the plan holds for it."""
        place = lay.tag_place(key)
        cell, axis, land = self.sector_records(direction)
        self.held[direction] = key
        self.plan["ring1"].append({"place": place, "name": key, "label": name, "weight": 0, "wedge": cell, "axis": axis})
        self.plan["trunks"][place] = {"name": key, "label": name, "ring": 1, "role": "ring1", "side": 0, "parent": None, "line": place, "index": 0,
                                      "wedge": land, "inner": list(land), "heavy": None, "left": [], "right": []}
        self.plan["streets"][place] = {"name": key, "kind": "leaf", "ring": 1, "label": name, "address": [name], "parent": None, "carrier": place,
                                       "collapsed": [], "absorbed": [], "ribs": [], "weight": 0, "order": len(self.plan["ring1"]) - 1}
        self.plan["sites"][key] = place

    def set_geometry(self) -> None:
        """Write the ring road of the plan again for the rule in force: its radius, the sectors and axes of its N directions, and the sector and land of every avenue that
        holds a direction. The label stays. Nothing of the world changes until it is laid out again (`relay`)."""
        ring, fresh = self.plan["params"]["ring"], ring_params(self.rule)
        for field in ("radius", "sectors", "axes"):
            ring[field] = fresh[field]
        for direction, key in self.held.items():
            cell, axis, land = self.sector_records(direction)
            place = lay.tag_place(key)
            for row in self.plan["ring1"]:
                if row["name"] == key:
                    row["wedge"], row["axis"] = cell, axis
            self.plan["trunks"][place]["wedge"], self.plan["trunks"][place]["inner"] = land, list(land)

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

    def ring(self, road: str) -> int:
        """The ring a road stands in: 1 for an avenue, and one more for each road above it."""
        n = 1
        while self.nodes[road]["parent"] is not None:
            road, n = self.nodes[road]["parent"], n + 1
        return n

    def merge_reach(self, members: list[str]) -> int:
        """The deepest ring that a merge of the avenues `members` would put a road in: the new avenue is ring 1, they are ring 2, and every road below them goes one ring down."""
        return 1 + max(self.ring(k) for m in members for k in self.subtree(m))

    def houses_below(self, road: str) -> list[str]:
        """The houses that stand on the road or on a road below it, in arrival order."""
        roads = set(self.subtree(road))
        return [h for h in self.items if self.road_of[h] in roads]

    def widest_avenue(self, members: list[str]) -> str:
        """The avenue of `members` whose direction has the widest sector (`sector_table`, the widths compared in whole tenths of a degree, `tenths`): a merge gives that sector to the
        new avenue, which carries the houses of all of them and needs the room. Of two with sectors as wide, the one with the most houses on it and below it; then the lower number."""
        table = sector_table(self.rule["branches"])

        def rank(m: str) -> tuple[int, int, int]:
            k = self.direction_of(m)
            return -tenths(table[k][1] - table[k][0]), -len(self.houses_below(m)), k

        return min(members, key=rank)

    def houses_under(self, roads: list[str]) -> list[str]:
        """The houses that stand on any of the roads `roads` or on a road below one of them, in arrival order."""
        below = {k for r in roads for k in self.subtree(r)}
        return [h for h in self.items if self.road_of[h] in below]

    def houses_at(self, road: str | None) -> list[str]:
        """The houses that stand directly on a road (None: the ring road), in arrival order."""
        return [h for h in self.items if self.road_of[h] == road]

    def where(self, road: str | None) -> str:
        return "the ring road" if road is None else f"the road {road!r}"

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
    def annex_of(self, house: str) -> str | None:
        """The house that `house` is an annex of: the one it stands beside, or, for an ordinary house that waits for its house, the one its item says it exists for. None for a house that
        is no annex, and for an id that is none of the world's."""
        if house in self.annexes:
            return self.annexes[house]["parent"]
        return self.items[house].get("annex_of") if house in self.items else None

    def beside(self, house: str, parent: str) -> bool:
        """Whether the new item `house`, which exists for `parent`, stands beside it at once (`parent` stands on a lot) or waits for it. `Refusal` for an item of itself, and for an item of
        an annex (one that stands beside a house, or one that waits for its own house): an item is of a house, never of another annex."""
        if house == parent:
            raise Refusal(f"{house!r} cannot be an annex of itself", "annex_of_itself", house=house)
        above = self.annex_of(parent)
        if above is not None:
            raise Refusal(f"{house!r} cannot be an annex of {parent!r}, which is an annex of {above!r}: an item is of a house, not of another annex", "annex_of_annex",
                          house=house, parent=parent, above=above)
        return parent in self.items

    def absorb_waiting(self, w: HandWorld, house: dict) -> list[str]:
        """The houses that waited for the house `house` (houses whose item says `annex_of` this one) are absorbed, in the order they arrived: each leaves its lot and stands beside it,
        with one entry `absorbed` of the chronicle. A house that is an annex itself takes none (no annex is of an annex): they stay houses. Returns the ids of the houses absorbed."""
        if self.annex_of(house["id"]) is not None:
            return []
        out = []
        for h in [h for h, it in self.items.items() if it.get("annex_of") == house["id"]]:
            form = self.items[h]["annex_form"]
            w.absorb(h, house["id"], form, "add_item")
            del self.items[h], self.road_of[h]
            self.annexes[h] = {"parent": house["id"], "form": form}
            out.append(h)
        return out

    def do_add_item(self, e: dict, p: dict) -> None:
        item = p["item"]
        if item["id"] in self.items or item["id"] in self.annexes:
            raise Refusal(f"{item['id']!r} is a house already", "house_exists", house=item["id"])
        parent = item.get("annex_of")
        if parent is not None and self.beside(item["id"], parent):  # an item that exists for a house that stands: beside it at once, with no lot, no road and no landing
            w, before = self.world(e), len(self.doc["chronicle"])
            w.seq += 1  # the arrival number: log order
            w.place_annex(item["id"], parent, item["annex_form"], w.seq, "add_item")
            self.annexes[item["id"]] = {"parent": parent, "form": item["annex_form"]}
            self.commit(w, e, before)
            self.effects[e["seq"]] = {"houses": [item["id"]], "roads": []}
            return
        land = landing(self, item) if self.rule["auto"] else None  # (a road only under `auto`; otherwise the ring road)
        w, before = self.world(e), len(self.doc["chronicle"])
        w.seq += 1  # the arrival number: log order
        w.arrival_ids.add(item["id"])
        w.add_houses(zw.ROOT_PLACE if land is None else lay.tag_place(land), [{"article": item["id"], "tag": land, "seq": w.seq}], "add_item")
        self.items[item["id"]] = item
        self.road_of[item["id"]] = land
        touched, opened = [item["id"]], []
        touched += self.absorb_waiting(w, item)  # (the houses that waited for this one: an item that has no `annex_of` of its own may have some)
        self.settle(w, e, land, touched, opened)
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": touched, "roads": opened}

    def do_annex(self, e: dict, p: dict) -> None:
        """A link learned later: the house `house` stands beside the house `parent` from here on. Both stand on a lot and differ, the house has no annex of its own and the parent is no annex
        (not one that stands beside a house, and not one that waits for its own house); else a refusal with its own id."""
        house, parent, form = p["house"], p["parent"], p["form"]
        if house == parent:
            raise Refusal(f"{house!r} cannot be an annex of itself", "annex_of_itself", house=house)
        if house in self.annexes:
            raise house_is_annex(house, self.annexes[house]["parent"], self.annexes[house]["form"])
        if house not in self.items:
            raise Refusal(f"{house!r} is not a house", "not_a_house", house=house)
        above = self.annex_of(parent)
        if above is not None:
            raise Refusal(f"{house!r} cannot be an annex of {parent!r}, which is an annex of {above!r}: an item is of a house, not of another annex", "annex_of_annex",
                          house=house, parent=parent, above=above)
        if parent not in self.items:
            raise Refusal(f"{house!r} cannot be an annex of {parent!r}: there is no house {parent!r}", "annex_parent_missing", house=house, parent=parent)
        owned = [a for a, rec in self.annexes.items() if rec["parent"] == house]
        if owned:
            raise Refusal(f"{house!r} has {len(owned)} {'annex' if len(owned) == 1 else 'annexes'} of its own, so it cannot be an annex: an item is of a house, not of another annex",
                          "annex_has_annexes", house=house, count=len(owned))
        w, before = self.world(e), len(self.doc["chronicle"])
        w.absorb(house, parent, form, "annex")
        del self.items[house], self.road_of[house]
        self.annexes[house] = {"parent": parent, "form": form}
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [house], "roads": []}

    def settle(self, w: HandWorld, e: dict, start: str | None, touched: list[str], opened: list[str]) -> None:
        """After an arrival, under the rule `auto`: the place the house stands on (`start`: a road, or None for the ring road) is looked at, and while it holds more than `max`
        houses directly, a road is opened for the largest group of its houses (`bibliopolis.suggest.suggest_road`: one level of OpenAlex below the place) and named after the
        node, with the mechanics of `open_road`: the houses that stay keep their lots. When the place holds `branches` roads already, the best merge of them
        (`bibliopolis.suggest.suggest_merge`) is made first, to make room, and then the road is opened: both are entries of the chronicle. Each road so opened is looked at in
        turn, in the order they were opened, so that one that holds more than `max` houses splits again. The roads are `auto:<seq>`, `auto:<seq>.2`, ... in that order (a merge
        takes a number as a split does), roads like any other afterwards. A place with no suggestion (no group of `min`, or a road for a topic, which is not split, or a road
        in the last ring, `RING_LIMIT`), or with no room and nothing to merge, is left as it is, crowded (`bibliopolis.suggest.crowded` says so). Nothing without `auto`."""
        if not self.rule["auto"]:
            return
        n, queue, seen = 0, [start], set(touched)
        while queue:
            at = queue.pop(0)
            while self.count(at) > self.rule["max"]:
                suggestion = suggest_road(self, at)
                if suggestion is None:
                    break
                n += 1
                key = f"{AUTO_PREFIX}{e['seq']}" + (f".{n}" if n > 1 else "")
                if len(self.children(at)) >= self.rule["branches"]:  # no room at `at`: merge first, then the loop looks again (the merge may change the suggestion)
                    merge = suggest_merge(self, at)
                    if merge is None:
                        break
                    moved = self.merge(w, key, merge["name"], at, merge["members"], "add_item", merge["topic"], e=e)
                    touched.extend(h for h in moved if h not in seen)
                    seen.update(moved)
                    opened.append(key)
                    continue
                direction = self.free_direction() if at is None else None
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
        ring = 1 if parent is None else self.ring(parent) + 1
        if ring > RING_LIMIT:
            raise too_deep(key, ring)
        held = self.houses_at(parent)
        if len(held) < least:
            raise Refusal(f"{self.where(parent)} holds {len(held)} houses directly; a road is opened from a place that holds at least {least}", "too_few_here",
                          road=parent, held=len(held), least=least)
        if len(ids) < least:
            raise Refusal(f"{len(ids)} houses are chosen; a road takes at least {least}", "too_few_chosen", chosen=len(ids), least=least)
        for h in ids:
            if h in self.annexes:
                raise house_is_annex(h, self.annexes[h]["parent"], self.annexes[h]["form"])
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
        if parent is not None:
            self.room_at(parent)
        w, before = self.world(e), len(self.doc["chronicle"])
        self.open(w, key, name, parent, ids, "open_road", direction, node)
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": list(ids), "roads": [key]}

    def do_file(self, e: dict, p: dict) -> None:
        house, key = p["house"], p["road"]
        if house in self.annexes:
            raise house_is_annex(house, self.annexes[house]["parent"], self.annexes[house]["form"])
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
        if key is None:  # the ring road
            was = self.plan["params"]["ring"]["label"]
            if was == name:
                raise Refusal(f"the ring road is called {name!r} already", "same_name", road=None, name=name)
            self.plan["params"]["ring"]["label"] = name
            w, before = self.world(e), len(self.doc["chronicle"])
            w.relabel_ring(name)
            w.note("rename_road", renamed=zw.ROOT_PLACE, was=was, label=name)
            self.commit(w, e, before)
            self.effects[e["seq"]] = {"houses": [], "roads": []}
            return
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
        reach = self.ring(parent) + 1 + max(self.ring(k) for k in below) - self.ring(key)  # the ring of the deepest road of the subtree once it stands below `parent`
        if reach > RING_LIMIT:
            raise too_deep(key, reach)
        self.room_at(parent)
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
        key, name, parent, members, node = p["road"], p["name"], p["parent"], p["members"], p.get("topic")
        if key in self.nodes:
            raise Refusal(f"there is a road {key!r} already", "road_exists", road=key)
        if parent is not None and parent not in self.nodes:
            raise Refusal(f"there is no road {parent!r} to merge roads below", "parent_missing", parent=parent)
        for m in members:
            if m not in self.nodes:
                raise Refusal(f"there is no road {m!r}", "no_road", road=m)
            if self.nodes[m]["parent"] != parent:
                here = "an avenue" if self.nodes[m]["parent"] is None else f"below {self.nodes[m]['parent']!r}"
                raise Refusal(f"the road {m!r} does not stand directly below {self.where(parent)}: it is {here}, and only the roads that stand directly below one road are merged under "
                              "a new one there", "not_a_child", road=m, parent=parent)
        reach = self.merge_reach(members)
        if reach > RING_LIMIT:
            raise too_deep(key, reach)
        moved = self.houses_under(members)
        if node is not None:
            taken = roads_by_node(self).get((node["level"], node["id"]))
            if taken is not None:
                raise Refusal(f"the road {taken!r} stands for the {node['level']} {node['id']!r} already; two roads never stand for one node", "node_taken",
                              level=node["level"], topic=node["id"], road=taken)
            for h in moved:
                if not descends(self.items[h]["openalex"], node["level"], node["id"]):
                    raise Refusal(f"the house {h!r} is not under the {node['level']} {node['id']!r}, which the road stands for", "house_not_under_node",
                                  house=h, level=node["level"], topic=node["id"])
        self.merge(None, key, name, parent, members, "merge_roads", node, e=e)
        self.effects[e["seq"]] = {"houses": moved, "roads": [key]}

    def merge(self, w: HandWorld | None, key: str, name: str, parent: str | None, members: list[str], trigger: str, node: dict | None, *, e: dict) -> list[str]:
        """Group the roads `members` (all directly below `parent`, None: the ring road, so avenues) under the new road `key`, which takes their place there. A new avenue takes the
        direction of the member with the widest sector and the others' are free; below the ring road the new road has no direction and the member that was opened first is the
        one it `took`. The roads of the subtrees of the members and their houses are put again. `w` is the working copy of the event, or None to make it here and commit it
        (a merge that is the event itself). Returns the ids of the houses put again."""
        below = {k for m in members for k in self.subtree(m)}
        keys = [k for k in self.nodes if k in below]  # in the order the roads were opened (before anything moves)
        moved = self.houses_under(members)
        held = {m: self.direction_of(m) for m in members} if parent is None else {}
        opened = list(self.nodes)
        took = self.widest_avenue(members) if parent is None else min(members, key=opened.index)  # the widest sector, then the most houses, then the lower number; below: the first opened
        for m in held:  # the directions of the members are free; the new avenue takes the one of the member with the widest sector
            del self.held[held[m]]
        self.nodes[key] = {"key": key, "name": name, "parent": parent, "topic": node}
        for m in members:
            self.nodes[m]["parent"] = key
        if parent is None:
            self.add_sector(key, name, held[took])
        own = w is None
        if own:
            w = self.world(e)
        before = len(self.doc["chronicle"]) if own else 0
        w.merge_roads(key, name, members, took, keys, trigger, PLAZA if parent is None else lay.tag_place(parent))
        if own:
            self.commit(w, e, before)
        return moved

    def do_undo(self, e: dict, p: dict) -> None:
        w, before = self.world(e), len(self.doc["chronicle"])
        w.note("undo", undone=p["seq"], of=self.kinds.get(p["seq"], "?"))
        self.commit(w, e, before)
        self.effects[e["seq"]] = {"houses": [], "roads": []}

    def do_set_rule(self, e: dict, p: dict) -> None:
        rule = {k: p[k] for k in RULE_KEYS}
        if rule == self.rule:
            raise Refusal("the rule is this already", "rule_unchanged", max=rule["max"], min=rule["min"], auto=rule["auto"], branches=rule["branches"])
        need, who = self.least_branches()
        if rule["branches"] < need:
            where = "an avenue holds the direction number " + str(need - 1) if who is None else f"the road {who!r} holds {need} roads"
            raise Refusal(f"{rule['branches']} branches would leave the world over: {where}, so the rule needs {need} at least (merge or move roads first)",
                          "branches_below_standing", road=who, needs=need, branches=rule["branches"])
        ring = self.plan["params"]["ring"]
        was = {"radius": ring["radius"], "sectors": ring["sectors"], "axes": ring["axes"], "branches": self.rule["branches"]}
        self.rule = rule
        self.plan["params"]["districts"] = districts_of(rule)
        self.set_geometry()
        if (ring["radius"], ring["sectors"], ring["axes"]) == (was["radius"], was["sectors"], was["axes"]):
            w, before = self.world(e), len(self.doc["chronicle"])
            w.note("set_rule", rule=dict(rule))
            self.commit(w, e, before)
        else:  # the ring road is another one (more directions, or a `max` it cannot hold at its radius): the whole world is laid out again on it
            w, base, put = self.relay(e)
            before = len(base["chronicle"])
            w.note("set_rule", rule=dict(rule))
            w.note("set_rule", resized=zw.ROOT_PLACE, was_radius=was["radius"], radius=ring["radius"], was_branches=was["branches"], branches=rule["branches"], houses=put)
            self.commit(w, e, before, base)
        self.effects[e["seq"]] = {"houses": [], "roads": []}

    def layout_order(self) -> list[tuple[str, list[dict]]]:
        """(place, its lots) for the ring road and then each road in the order the roads were opened, the lots of each in the order they stand along it: the laps of the
        ring in turn and the ribs of a road in turn, a slot at a time. A hole between two houses is not part of the order."""
        places, out = self.doc["places"], []
        lots: dict[str, list[dict]] = {}
        for lot in places.values():
            if lot["kind"] == "lot":
                lots.setdefault(lot["street"], []).append(lot)
        for place in (zw.ROOT_PLACE, *(lay.tag_place(k) for k in self.nodes)):
            rec = places.get(place)
            if rec is None or place not in lots:
                continue
            carriers = ([place] if "rib" in rec or place == zw.ROOT_PLACE else []) + list(rec.get("lanes", []))
            out.append((place, sorted(lots[place], key=lambda lot: (carriers.index(lot["parent"]), lot["slot"]))))
        return out

    def relay(self, e: dict) -> tuple[HandWorld, dict, list[str]]:
        """The world laid out again on the plan as it is now: a fresh world (the ring road of the plan, no road, no line, no rib), the chronicle and the arrivals of the
        old one kept, and every house put again, the ring road's first and then each road's, in the order they stood along their streets (on the ring: round it, the laps in
        turn; the houses of the ring take the first slots of the fill order of the new laps, matched by rank, `put_ring_again`). Nothing changes road, no house passes another
        along its street and no avenue changes direction; where a hole stood the next house closes it. Returns the working copy, the fresh world it starts from (for
        `commit`) and the ids of the houses put again, in the order they were put."""
        old = self.doc
        base = {**zw.new_world(self.plan), "seq": old["seq"], "chronicle": [dict(c) for c in old["chronicle"]]}
        base["places"].update({pid: rec for pid, rec in old["places"].items() if rec["kind"] == "annex"})  # (an annex has no lot to put again: it stands where its house stands)
        w, put = HandWorld(zw.PlanView(self.plan), self.tree, base, event_id=e["seq"]), []
        for place, lots in self.layout_order():
            if place == zw.ROOT_PLACE:
                w.put_ring_again(lots)
            else:
                w.add_houses(place, [{"article": lot["article"], "tag": lot["tag"], "seq": lot["seq"]} for lot in lots], "set_rule")
            put.extend(lot["article"] for lot in lots)
        return w, base, put

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
