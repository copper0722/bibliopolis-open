"""The world on a plan: houses arrive one at a time and the city grows outward.

    assign(plan, tree, placed, arrivals) -> {placements, places, roads, delta, stats}   new houses; placed houses keep their lot
    apply_delta(doc, delta)                                                            fold a result into the world

Pure functions. `placed` is the world document (places, roads, lines: the layout v4 shapes, so the geometry checks and
`bibliopolis.document.world_layout` work on it) and is never changed. A call returns a delta: the records it wrote. A delta can be applied,
stored and replayed; the world is the fold of its deltas. `tree` is the topic tree (a TreeView, or a tree document).

Model. The plan (bibliopolis.plan) fixes directions only; nothing has a radius until a house needs it. A LINE is a trunk of the plan and its
heavy chain: one axis, one frontier, one set of bands. A side child of a trunk starts a line of its own.

  member    a trunk opens at the frontier of its line when the first house of its subtree arrives (a ring-1 trunk at the rim of the plaza);
            a heavy child continues the spoke straight. A member with side children in the plan draws its branch circle at once, one cell
            beyond the frontier: the circles of the members of a line grow outward from the one above, so an arc never meets a deeper spoke.
  branch    one arc per side along that circle, from the spoke to the axis of each side child that has opened; a later side child joins the
            arc at the bearing of its axis, whatever the order of arrival. Beyond the circle the sector of the member is its central wedge
            (`inner`): bands of its line stop short of the side wedges, and a side child's line starts at the circle.
  street    the first house of a road opens a rib on the line of its carrier trunk: lots on both sides of a lane. A rib is a stretch of a
            BAND (an arc round the plaza across the line): first fit by radius: the open end of a band side that has room, else a new band
            at the smallest free radius that fits the wedge. Where a band would end clearly farther out (a narrow sector) the rib lies along
            the SPOKE instead, lots on both sides of the axis. The land grows outward without bound.

Determinism: same plan, tree, world and arrivals give the same bytes (sorted iteration, integer angles, coordinates rounded to 3 decimals).

Roads (the district rule `plan["params"]["districts"]` = {max, min, extract: "largest", count: "direct"}). What the plan pins is the
directions (the ring-1 wedges, the trunks and their sides); which topics are roads is world state:

  root zone  the one street `place:root` (label 根區) lies UNDER the town hall: `{shape: "underground", underground: true, parent: plaza}`, no
             road and no rib on the surface. Its lots carry `underground: true` and stand on a compact grid of whole cells round the centre
             of the plaza, nearest cell first, in arrival order (the first 89 lie inside the plaza), so that a renderer that ignores the flag
             draws nothing outside it. It takes every house no open road takes: the first houses, a topic too thin for a road, an item
             without a topic.
  road       a street record with a key (`tag`) and the chain of topics collapsed into it (`collapsed`). A house stands on the NEAREST OPEN
             ANCESTOR-OR-SELF of its topic (`road_for_tag`): a road covers its key's subtree, and exactly the topics of its chain.
  split      a road holds `max` houses directly (alleys and their houses do not count). The house that would be one more is decided BEFORE
             it is placed: the road's direct houses are grouped by the child topic of its key on their path, and the largest group of at least
             `min` (ties: code-point order of the child key) opens a road of its own below it (collapsed: down to the deepest topic whose
             subtree still holds the whole group). The group moves there; the houses that stay are packed again onto the first lots of the
             road in arrival order (`seq`); the new road is checked in turn. No group reaches `min`: the street record says `over`. Ring 1 is
             the plan's: the root zone opens the plan's ring-1 street of a root topic (the wedges are pinned; its record's `parent` stays
             the plaza), and collapse works below it.
  rib        a rib is sized to the houses its road holds when it opens plus headroom, `min(max, even(n + max(4, ceil(n / 2))))`, n counting
             the arrivals of the call (a split group, the survivors, or 1). A full road opens a CONTINUATION rib sized the same way on its
             current count (while the road is not over its ribs hold at most `max` lots together): a lane record that adds `continued: true`
             and has the road's own label, level and address: one road everywhere. `over` is independent of it. A house takes the lowest
             free lot.
  chronicle  every split and every road that became over is an entry of the document's `world.chronicle`, in the order it happened:
             `{n, event_id, seq, trigger, from, to, label, houses, count_before, count_after}` or `{n, event_id, seq, trigger, over, count}`.
  no merge   a road that falls under `min` (the survivors of a split) stays open.

In a `mirror` plan every topic of `plan["roads"]` is a road from the start and there is no split: a road that holds more than `max` houses is
`over`, and the chronicle says when.
"""

from __future__ import annotations

import copy
import functools
import math
from dataclasses import dataclass, field

from . import layout as lay
from .plan import MIRROR, MODES, check_districts
from .tree import TreeView, major_tag

WORLD_VERSION = "world/1"
PLAZA_PLACE, PLAZA_RADIUS, PLAZA_LABEL = lay.PLAZA_PLACE, lay.PLAZA_RADIUS, lay.PLAZA_LABEL
BAND, LEAD, TRUNK_LANE, ITEM_GAP = lay.BAND, lay.LEAD, lay.TRUNK_LANE, lay.ITEM_GAP
GROWTH_REACH = 80.0  # a band reaches this far off its axis at most (a ring road, not a circle)
JOIN = lay.JOIN
EPS = 1e-9
BRANCH_CLEAR = 1.0  # the branch circle of a member is drawn this far beyond the frontier, and keeps this clear of every lot
SPOKE_MARGIN = 4.0  # a street goes along the spoke (lots on both sides of the axis) when that ends this many cells nearer than a band would
ROOT_PLACE = "place:root"  # the root zone: the one street under the town hall that takes every house no open road takes
ROOT_ZONE_LABEL = "根區"
HEADROOM_MIN, HEADROOM_DIV = 4, 2  # a rib is sized to the houses its road holds plus max(4, ceil(n / 2)) lots of headroom


def district_rib_size(n: int, max_houses: int) -> int:
    """Lots of a rib that opens for a road which holds `n` houses with the arrivals of the call: the houses and headroom, in whole cells
    (two lots to a cell), never above `max`. A rib of `max` lots at the first house made the roads of narrow wedges long and empty."""
    want = n + max(HEADROOM_MIN, math.ceil(n / HEADROOM_DIV))
    return min(max_houses, want + want % 2)


@functools.cache
def _cells_within(r: int) -> tuple[tuple[int, int], ...]:
    """The whole cells (i, j) with i*i + j*j <= r*r, nearest the centre first, ties round the circle: a prefix of the same list for a larger r."""
    pts = ((i, j) for i in range(-r, r + 1) for j in range(-r, r + 1) if i * i + j * j <= r * r)
    return tuple(sorted(pts, key=lambda p: (p[0] * p[0] + p[1] * p[1], math.atan2(p[1], p[0]), p)))


def underground_cell(slot: int) -> tuple[float, float]:
    """(x, z) of the centre of the cell of the underground lot `slot`: whole cells round the centre of the plaza, nearest first. The first 89 cells
    lie wholly inside the plaza (radius 6.0); a root zone larger than that goes on outward."""
    r = 7
    while len(_cells_within(r)) <= slot:
        r += 8
    i, j = _cells_within(r)[slot]
    return float(i), float(j)


def ceil3(v: float) -> float:
    """`v` rounded up to a millimetre: a band radius is stored with three decimals, and must still satisfy the bound it was computed from."""
    return math.ceil(v * 1000 - 1e-7) / 1000


def rib_block_key(street_key: str, ordinal: int) -> str:
    """Block key of the reserved ids of a rib: the topic id for the road itself, `lane:<key>:<k>` for rib k >= 2."""
    return street_key if ordinal == 1 else f"lane:{street_key}:{ordinal}"


# ------------------------------------------------------------------------------------------ views ----
class PlanView:
    """The plan document with the wedges as integer angle units."""

    def __init__(self, plan: dict):
        self.trunks: dict[str, dict] = plan["trunks"]
        self.streets: dict[str, dict] = plan["streets"]
        self.sites: dict[str, str] = plan["sites"]
        self.centre_tag: str | None = plan["params"].get("centre_tag")  # a tree with ONE root: the root is the town hall, its children are ring 1
        self.districts: dict = plan["params"]["districts"]
        check_districts(self.districts)
        self.mode: str = plan.get("mode", "grow")
        if self.mode not in MODES:
            raise ValueError(f"the plan has a mode {self.mode!r}; the engine knows {MODES}")
        self.roads: list[str] = list(plan.get("roads", []))  # mirror: the topics that are roads from the start
        self._wedge: dict[str, tuple[int, int]] = {}

    def wedge(self, trunk: str) -> tuple[int, int]:
        if trunk not in self._wedge:
            lo, hi = self.trunks[trunk]["wedge"]
            self._wedge[trunk] = (round(lo * lay.UNIT), round(hi * lay.UNIT))
        return self._wedge[trunk]

    def inner(self, trunk: str) -> tuple[int, int]:
        lo, hi = self.trunks[trunk]["inner"]
        return round(lo * lay.UNIT), round(hi * lay.UNIT)

    def half(self, wedge: tuple[int, int]) -> float:
        return (wedge[1] - wedge[0]) / (2 * lay.UNIT)

    def axis(self, trunk: str) -> float:
        lo, hi = self.wedge(trunk)
        return (lo + hi) / (2 * lay.UNIT)


class Overlay:
    """Writes over a read-only dict. `new` holds what was written (None: deleted).

    An object in `new` belongs to this overlay, so it may be changed in place; an object of the base never is (`mut` copies it first)."""

    def __init__(self, base: dict):
        self.base, self.new = base, {}

    def get(self, key):
        if key in self.new:
            return self.new[key]
        return self.base.get(key)

    def put(self, key, value) -> None:
        self.new[key] = value

    def delete(self, key) -> None:
        if self.get(key) is not None:  # nothing to take away: nothing is recorded
            self.put(key, None)

    def items(self):
        """(key, value) of every record that stands now: the base minus what was deleted or written over, then what was written."""
        for key, value in self.base.items():
            if key not in self.new:
                yield key, value
        for key, value in self.new.items():
            if value is not None:
                yield key, value

    def mut(self, key):
        """The record of `key` as an object this overlay owns (copied from the base on first use)."""
        if key in self.new and self.new[key] is not None:
            return self.new[key]
        value = copy.deepcopy(self.base[key])
        self.put(key, value)
        return value


@dataclass
class StreetSpec:
    """A road as the plan and the roads above it make it: where it hangs, which trunk carries it. Not stored; derived on demand."""

    place: str
    key: str  # the id of the topic the road is named by
    label: str
    ring: int
    address: list[str]
    parent: str | None  # the road it hangs on (None: a child of the plaza)
    carrier: str  # the trunk whose line carries its ribs
    weight: int = 0
    collapsed: list[str] = field(default_factory=list)
    trunk: bool = False
    order: int = 10**6
    tag: str | None = None


# --------------------------------------------------------------------------------------- documents ----
def new_world(plan: dict) -> dict:
    """The world of day one: the town hall plaza and nothing else."""
    pv = PlanView(plan)
    ring1 = []
    for r in plan["ring1"]:
        lo, hi = r["wedge"]
        ring1.append({"place": r["place"], "label": r["label"], "weight": r["weight"], "from": lo, "to": hi, "span": round(hi - lo, 3)})
    return {
        "schema_version": WORLD_VERSION, "layout_version": "world", "zoning_version": plan["zoning_version"], "mode": pv.mode, "seq": 0,
        "centre": {"place": PLAZA_PLACE, "tag": pv.centre_tag, "radius": PLAZA_RADIUS, "label": PLAZA_LABEL},
        "composition": {"home_max": plan["params"]["home_max"], "trunk_min": plan["params"]["trunk_min"],
                        "articles": 0, "buildings": 0, "reserved_lots": 0, "ring1": ring1},
        "places": {PLAZA_PLACE: {"kind": "plaza", "label": PLAZA_LABEL, "position": {"x": 0.0, "z": 0.0}, "radius": PLAZA_RADIUS,
                                 **({"tag": pv.centre_tag} if pv.centre_tag else {})}},
        "roads": {}, "lines": {},
        "districts": {k: pv.districts[k] for k in ("max", "min", "extract", "count")},
        "chronicle": [],
    }


def apply_delta(doc: dict, delta: dict) -> dict:
    """The world with a delta applied (a new document: the old one is left as it was)."""
    out = {**doc, "places": dict(doc["places"]), "roads": dict(doc["roads"]), "lines": dict(doc["lines"]), "seq": delta["seq"]}
    for name in ("places", "roads", "lines"):
        for key, value in delta[name].items():
            if value is None:
                out[name].pop(key, None)
            else:
                out[name][key] = value
    out["chronicle"] = list(delta["chronicle"])  # the whole chronicle after the delta
    return out


def houses(doc: dict) -> dict[str, dict]:
    """item id -> its lot record."""
    return {p["article"]: p for p in doc["places"].values() if p["kind"] == "lot"}


# ------------------------------------------------------------------------------------------ the world ----
class World:
    """One call's working copy of the world: reads the document, writes into overlays, resolves roads from the plan and the tree."""

    def __init__(self, plan: PlanView, tree: TreeView, doc: dict, *, event_id: int | None = None):
        self.plan, self.tree, self.doc = plan, tree, doc
        self.places, self.roads, self.lines = Overlay(doc["places"]), Overlay(doc["roads"]), Overlay(doc.get("lines", {}))
        self.seq = doc.get("seq", 0)
        self.specs: dict[str, StreetSpec] = {}
        self.placements: dict[str, dict] = {}
        self.stats = {"houses": 0, "ribs": 0, "members": 0, "bands": 0, "spoke_ribs": 0, "splits": 0, "overs": 0, "blocked": 0, "continuations": 0}
        self.max, self.min = plan.districts["max"], plan.districts["min"]
        self.mirror = plan.mode == MIRROR
        self.event_id = event_id  # the event whose house causes what this call writes to the chronicle (None: no events)
        self.chronicle: list[dict] = list(doc.get("chronicle", []))
        self.road_def: dict[str, tuple[str, tuple[str, ...]]] = {}  # road place -> (key, chain top first)
        self.road_key: dict[str, str] = {}  # topic -> the road it is the key of (the road covers the subtree)
        self.road_chain: dict[str, str] = {}  # topic -> the road it is collapsed into (the road covers that topic alone)
        self.arrival_ids: set[str] = set()  # the houses this call brings: the rest are houses put again
        self.hold: dict[str, int] = {}  # road place -> the houses it holds with the batch being put on it: a rib that opens is sized to it
        self._by_road: dict[str, list[dict]] | None = None  # road place -> its lots; None: not built (or stale)
        self.index_roads()
        if self.mirror:  # every topic that holds a house is a road from the start
            for tag in plan.roads:
                place = lay.tag_place(tag)
                if place not in self.road_def:
                    self.register_road(place, tag, ())

    # ---- the root zone: underground, under the town hall
    def ensure_root(self) -> dict:
        """The street record of the root zone, made on first use: no road, no rib, nothing on the surface."""
        rec = self.places.get(ROOT_PLACE)
        if rec is None:
            rec = {"kind": "street", "shape": "underground", "underground": True, "label": ROOT_ZONE_LABEL, "address": [ROOT_ZONE_LABEL],
                   "parent": PLAZA_PLACE, "lots": 0, "reserved": 0}
            self.places.put(ROOT_PLACE, rec)
        return rec

    def put_underground(self, article_id: str, tag: str | None, seq: int, track: bool = True) -> dict:
        """Put a house in the root zone: the lowest free cell of the grid under the plaza (the cell of the lot is a function of its slot, so the houses
        that stay after a split are packed again onto the first cells in arrival order). The lot is flagged `underground`."""
        self.ensure_root()
        used = {p["slot"] for p in self.by_road().get(ROOT_PLACE, ())}
        slot = next(s for s in range(len(used) + 1) if s not in used)
        lot = lay.lot_record(article_id, ROOT_PLACE, slot, slot, underground_cell(slot), 0.0)
        lot.update({"street": ROOT_PLACE, "tag": tag, "seq": seq, "underground": True})
        self.places.mut(ROOT_PLACE)["lots"] += 1
        self.places.put(lay.article_place(article_id), lot)
        if track:
            if article_id not in self.placements:
                self.stats["houses"] += 1
            self.placements[article_id] = lot
        self.by_road().setdefault(ROOT_PLACE, []).append(lot)
        return lot

    # ---- roads: the open roads are world state
    def index_roads(self) -> None:
        """Read the open roads from the street records of the world: a street with a key (`tag`). The root zone has none and a lane is no street."""
        for pid, rec in self.doc["places"].items():
            if rec["kind"] == "street" and "lane_of" not in rec and rec.get("tag") is not None:
                self.register_road(pid, rec["tag"], tuple(rec.get("collapsed", ())))

    def register_road(self, place: str, key: str, chain: tuple[str, ...] | list[str]) -> None:
        """A road is open: `key` covers its subtree and each topic of `chain` (collapsed into it, top first) covers itself."""
        self.road_def[place] = (key, tuple(chain))
        self.road_key[key] = place
        for topic in chain:
            self.road_chain[topic] = place

    def ring1_ok(self, place: str) -> bool:
        """Whether a street can stand with no road above it: a ring-1 street of the plan (its wedge is pinned). The root zone is no road."""
        trunk = self.plan.trunks.get(place)
        return trunk is not None and trunk["role"] == "ring1"

    def road_above(self, top: str) -> str | None:
        """The nearest open road above a topic: the first ancestor that is the key of an open road."""
        cur = self.tree.parent(top)
        while cur is not None:
            place = self.road_key.get(cur)
            if place is not None:
                return place
            cur = self.tree.parent(cur)
        return None

    def claimed(self, topic: str) -> bool:
        """Whether an open road holds the topic, as its key or in its chain."""
        return (self.road_key.get(topic) or self.road_chain.get(topic)) is not None

    def is_below(self, tag: str, ancestor: str) -> bool:
        cur = self.tree.parent(tag)
        while cur is not None:
            if cur == ancestor:
                return True
            cur = self.tree.parent(cur)
        return False

    def road_below(self, topic: str) -> bool:
        """Whether an open road has its key strictly below the topic. A road opened at the topic would then have to become the road above it
        (its level, address and perhaps its carrier would change): the engine does not do that, a group that needs it stays where it is."""
        return any(key != topic and self.is_below(key, topic) for key in self.road_key)

    def road_for_tag(self, tag: str | None) -> str:
        """The road a house of this topic stands on: the nearest open road at or above it. A road covers the subtree of its key and, alone, each
        topic of its chain (a chain topic has no road below it: the houses of its other children stand on the road above). The root zone when there is none."""
        cur, own = tag, True
        while cur is not None:
            place = self.road_key.get(cur)
            if place is None and own:
                place = self.road_chain.get(cur)
            if place is not None:
                return place
            cur, own = self.tree.parent(cur), False
        return ROOT_PLACE

    def spec(self, place: str) -> StreetSpec:
        if place in self.specs:
            return self.specs[place]
        if place not in self.road_def:  # (the root zone is no street to lay out: it is underground, see `put_underground`)
            raise KeyError(f"no road {place}")
        s = self.road_spec(place)
        self.specs[place] = s
        return s

    def road_spec(self, place: str) -> StreetSpec:
        """A road as the plan and the roads above it make it: where it hangs, which trunk carries its ribs. A street of the plan keeps the plan's
        trunk, wedge and carrier while the road above it is the planned one; any other topic is a rib on the line of the road above."""
        key, chain = self.road_def[place]
        chain = list(chain)
        parent = self.road_above(chain[0] if chain else key)
        label = JOIN.join(self.tree.label(t) for t in [*chain, key])
        rec = self.plan.streets.get(place)
        trunk = bool(rec is not None and place in self.plan.trunks and parent == rec["parent"] and (parent is None or self.spec(parent).trunk))
        assert trunk or parent is not None, f"{place} hangs on no road and is no ring-1 street of the plan"
        ring, address = 1, [label]
        if parent is not None:
            ps = self.spec(parent)
            ring, address = ps.ring + 1, ps.address + [label]
        carrier = place if trunk else self.spec(parent).carrier  # type: ignore[arg-type]
        return StreetSpec(place, key, label, ring, address, parent, carrier, rec["weight"] if rec else 0, chain, trunk, rec["order"] if rec else 10**6, key)

    def by_road(self) -> dict[str, list[dict]]:
        """road place -> its lots (the houses standing on the road itself); built on first use and kept up to date by the writers."""
        if self._by_road is None:
            index: dict[str, list[dict]] = {}
            for _pid, p in self.places.items():
                if p["kind"] == "lot":
                    index.setdefault(p["street"], []).append(p)
            self._by_road = index
        return self._by_road

    def lots_on(self, road: str) -> list[dict]:
        """The houses that stand on the road itself (not on its alleys), in arrival order: the count that the rule holds to `max`."""
        return sorted(self.by_road().get(road, ()), key=lambda p: p["seq"])

    def child_on_path(self, key: str | None, tag: str) -> str | None:
        """The child of `key` that lies on the path from `tag` up (None as key: the root of the path); None when `tag` is the key or not below it.
        (The groups of the root zone are the children of the centre when the tree has one root, else the roots.)"""
        prev, cur = None, tag
        while cur is not None:
            if cur == key:
                return prev
            prev, cur = cur, self.tree.parent(cur)
        return prev if key is None else None

    def covered_by(self, tag: str | None, key: str, chain: tuple[str, ...]) -> bool:
        return tag is not None and (tag == key or tag in chain or self.child_on_path(key, tag) is not None)

    def find_split(self, road: str, houses: list[dict]) -> dict | None:
        """The group of `houses` (the houses on the road, with the one about to be put) that opens a road, or None: group by the child topic of the
        road's key on each house's path (a house tagged the key itself, or a topic of the chain, is no group's); the largest group of at least `min`
        wins (ties: code-point order of the child key). A group that cannot open a road (see `candidate`) is passed over."""
        key = self.plan.centre_tag if road == ROOT_PLACE else self.road_def[road][0]  # (the root zone's key is the centre, else the tree's roots are its children)
        groups: dict[str, list[dict]] = {}
        for h in houses:
            tag = h["tag"]
            if tag is None or tag not in self.tree:
                continue
            child = self.child_on_path(key, tag)
            if child is not None:
                groups.setdefault(child, []).append(h)
        for child, group in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            if len(group) < self.min:
                break
            found = self.candidate(road, child, group, houses)
            if found is not None:
                return found
            self.stats["blocked"] += 1
        return None

    def candidate(self, road: str, child: str, group: list[dict], houses: list[dict]) -> dict | None:
        """The road the group of `child` would open: {place, topic, chain, moved}, or None when no road can stand for it.

        From the root zone the road is the plan's ring-1 street of the root topic (the wedges are pinned): its key and its chain are the plan's.
        Below a road it is collapsed: the deepest topic whose subtree holds the whole group, joined with the topics above it down from
        `child`. One topic belongs to one road: topics another road holds are not taken into the chain. A road is never opened ABOVE a road that is
        open already (the key itself held in another road's chain, or an open road with its key below the key): the group stays where it is and
        the road may stay over, which is what the curator is told (`over`)."""
        if road == ROOT_PLACE:
            site = self.plan.sites.get(child)
            if site is None or not self.ring1_ok(site):
                return None
            key, chain = self.plan.streets[site]["name"], tuple(self.plan.streets[site]["collapsed"])
            if any(self.claimed(t) for t in (key, *chain)) or self.road_below(key):
                return None
            moved = [h for h in houses if self.covered_by(h["tag"], key, chain)]
            return {"place": site, "topic": key, "chain": chain, "moved": moved} if len(moved) >= self.min else None
        end, path = child, [child]
        while not any(h["tag"] == end for h in group):
            below = {self.child_on_path(end, h["tag"]) for h in group}
            if len(below) != 1:
                break
            end = next(iter(below))
            path.append(end)
        place = lay.tag_place(end)
        if self.claimed(end) or self.road_below(end) or self.places.get(place) is not None:
            return None
        last = max((i for i, t in enumerate(path[:-1]) if self.claimed(t)), default=-1)
        return {"place": place, "topic": end, "chain": tuple(path[last + 1:-1]), "moved": group}

    def place_lot(self, road: str, h: dict) -> dict:
        """Put a house (a lot record, or the dict of an arrival) on a road. A house of `arrival_ids` is a house of the call, any other is put again."""
        track = h["article"] in self.arrival_ids
        if road == ROOT_PLACE:
            return self.put_underground(h["article"], h["tag"], h["seq"], track=track)
        return self.put_house(h["article"], self.spec(road), h["tag"], h["seq"], track=track)

    def free_lot(self, lot: dict) -> None:
        """Take a house out of its lot; the lot stays where it is, empty (an underground lot leaves nothing: the cell is a function of the slot)."""
        self.places.delete(lay.article_place(lot["article"]))
        carrier = self.places.mut(lot["parent"])
        carrier["lots"] -= 1
        if lot.get("underground"):
            self._by_road = None
            return
        carrier["reserved"] += 1
        self.places.put(lay.reserved_place(carrier["rib"]["block"], lot["slot"]),
                        lay.reserved_record(lot["parent"], lot["slot"], "tail", (lot["position"]["x"], lot["position"]["z"]), lot["facing"]))
        self._by_road = None

    def clear_over(self, road: str) -> None:
        rec = self.places.get(road)
        if rec is not None and rec.get("over"):
            self.places.mut(road).pop("over")

    def mark_over(self, road: str, count: int, trigger: str) -> None:
        """The road holds more than `max` and no group can open a road: it is over (once; the chronicle says when)."""
        if self.places.get(road).get("over"):
            return
        self.places.mut(road)["over"] = True
        self.stats["overs"] += 1
        self.chronicle.append({"n": len(self.chronicle) + 1, "event_id": self.event_id, "seq": self.seq, "trigger": trigger, "over": road, "count": count})

    def add_houses(self, road: str, pending: list[dict], trigger: str) -> None:
        """Put houses on a road, deciding BEFORE they are placed whether the road holds them: when it would hold more than `max`, the group that
        opens a road (if any) is split off first, so that no rib opens for houses a split moves away. A rib that opens while they are placed is sized
        to the `total` the road holds with them (`hold`). In a `mirror` city nothing splits: the road is over."""
        existing = self.lots_on(road)
        total = len(existing) + len(pending)
        if total <= self.max:
            self.hold[road] = total
            for h in pending:
                self.place_lot(road, h)
            self.hold.pop(road, None)
            self.clear_over(road)
            return
        found = None if self.mirror else self.find_split(road, existing + pending)
        if found is None:
            self.hold[road] = total
            for h in pending:
                self.place_lot(road, h)
            self.hold.pop(road, None)
            self.mark_over(road, total, trigger)
            return
        self.split(road, found, pending, trigger)

    def split(self, road: str, found: dict, pending: list[dict], trigger: str) -> None:
        """Open the road of `found`, move the group onto it and pack the houses that stay onto the first lots of the road in arrival order.
        `pending` are houses about to be put on the road: they take part. The group arrives on the new, empty road as any houses arrive (a group larger
        than `max` splits again at once, before any of it is placed: no continuation rib opens on a road that is not over), and then the houses that stay arrive
        on the emptied road, which may split again; the chronicle has the entries in that order."""
        existing = self.lots_on(road)
        everyone = sorted(existing + pending, key=lambda h: h["seq"])
        go_ids = {h["article"] for h in found["moved"]}
        stay = [h for h in everyone if h["article"] not in go_ids]
        go = [h for h in everyone if h["article"] in go_ids]
        for lot in existing:
            self.free_lot(lot)
        self.register_road(found["place"], found["topic"], found["chain"])
        self.stats["splits"] += 1
        self.chronicle.append({"n": len(self.chronicle) + 1, "event_id": self.event_id, "seq": self.seq, "trigger": trigger, "from": road,
                               "to": found["place"], "label": self.spec(found["place"]).label, "houses": [h["article"] for h in go],
                               "count_before": len(everyone), "count_after": len(stay)})
        self.add_houses(found["place"], go, trigger)
        self.add_houses(road, stay, trigger)

    def ensure_roads(self) -> None:
        """Mirror: make the street record of every road that has none, in code-point order of the place: a road that no house stands on or below
        (a topic an item is filed under whose address is elsewhere) has a record only from here on."""
        for place in sorted(self.road_def):
            self.ensure_street(place)

    # ---- records
    def fresh_road(self, base: str) -> str:
        """A road id not used before."""
        rid, n = base, 0
        while self.roads.get(rid) is not None:
            n += 1
            rid = f"{base}@{n}"
        return rid

    def put_road(self, rid: str, street: str, kind: str, ring: int, parent: str | None, at: float, points: list, length: float, **extra) -> dict:
        rec = lay.road_record(street, kind, ring, parent, at, points, length, **extra)
        self.roads.put(rid, rec)
        return rec

    def ensure_street(self, place: str) -> dict:
        """The record of a street, with those of the streets above it, created on first use."""
        rec = self.places.get(place)
        if rec is not None:
            return rec
        spec = self.spec(place)
        if spec.trunk:
            self.open_member(place)
            return self.places.get(place)
        if spec.parent is not None:
            self.ensure_street(spec.parent)
        # a road is a rib until a road opens below it (then a group): the shape tells what stands, not what the plan expected
        rec = {"kind": "street", "shape": "rib", "level": spec.ring, "class": lay.class_of(spec.ring),
               "parent": spec.parent or PLAZA_PLACE, "order": spec.order}
        self.finish_street_record(rec, spec)
        self.places.put(place, rec)
        if spec.parent is not None and self.places.get(spec.parent)["shape"] == "rib":
            self.places.mut(spec.parent)["shape"] = "group"
        return rec

    def finish_street_record(self, rec: dict, spec: StreetSpec) -> None:
        rec["tag"] = spec.tag
        if spec.collapsed or spec.place not in self.plan.streets:  # a topic street of the plan is named by the tree (its address says it)
            rec["label"] = spec.label
        rec["address"] = spec.address
        if spec.collapsed:
            rec["collapsed"] = spec.collapsed
        if spec.carrier != spec.place:
            rec["carrier"] = spec.carrier
        rec["lots"], rec["reserved"], rec["weight"] = 0, 0, spec.weight

    # ---- lines, members, branches
    def frontier(self, line: dict) -> float:
        """The radius from which a line is free: beyond its last band, branch circle and member."""
        f = 0.0
        for m in line["members"]:
            f = max(f, m["s0"] + LEAD, (m["r1"] + BRANCH_CLEAR) if m["r1"] is not None else 0.0)
        for b in line["bands"]:
            f = max(f, b["s"] + BAND / 2)
        for lo, hi in line["spokes"]:
            f = max(f, hi)
        return f

    def covering(self, line: dict, s: float) -> dict:
        """The member of a line whose spoke carries radius `s`: the last one that started at or before it."""
        best = line["members"][0]
        for m in line["members"]:
            if m["s0"] <= s + EPS:
                best = m
        return best

    def extend_line(self, line: dict, s_end: float) -> None:
        """Draw the spoke of a line at least as far as `s_end`: the road of its last member, the only one that is open at the end (the roads of
        the members above end where the next one starts, and together they carry every radius up to the frontier)."""
        self.spoke_to(line["members"][-1]["road"], s_end)

    def spoke_to(self, rid: str, s_end: float, opened: bool | None = None) -> None:
        """Draw a spoke road at least as far as `s_end` (a road is only ever drawn longer)."""
        road = self.roads.mut(rid)
        if s_end > road["s_end"] + EPS:
            road["s_end"] = lay.r3(s_end)
            road["length"] = lay.r3(s_end - road["s0"])
            road["points"] = [road["points"][0], lay.pt(lay.polar_xz(s_end, road["axis"]))]
        if opened is not None:
            road["open"] = opened

    def open_member(self, place: str) -> dict:
        """Open a trunk of the plan as a member of its line (with the members above it): its spoke, its street record, its line. A member that
        stands already is returned as it is."""
        t = self.plan.trunks[place]
        line = self.lines.get(t["line"])
        member = next((m for m in line["members"] if m["place"] == place), None) if line is not None else None
        if member is None:
            member = self.create_member(place, t)
        if self.places.get(place) is None:
            self.put_trunk_record(place, t, member)
        return member

    def create_member(self, place: str, t: dict) -> dict:
        line_id, spec = t["line"], self.spec(place)
        axis, wedge = self.plan.axis(place), self.plan.wedge(place)
        if spec.parent is not None:
            self.ensure_street(spec.parent)
        if t["role"] == "ring1":
            s0, parent_road, at = PLAZA_RADIUS, None, 0.0
            self.lines.put(line_id, {"root": place, "axis": lay.r3(axis), "parent": None, "members": [], "bands": [], "spokes": []})
        elif t["role"] == "heavy":
            self.open_member(t["parent"])
            line = self.lines.mut(line_id)
            last = line["members"][-1]
            s0 = self.frontier(line)
            self.spoke_to(last["road"], s0, opened=False)
            parent_road, at = last["road"], s0 - last["s0"]
        else:  # a side child: it joins the branch circle of its parent member and starts a line of its own
            pline_id = self.plan.trunks[t["parent"]]["line"]
            self.open_member(t["parent"])
            r1, arc, at = self.branch_for(pline_id, t["parent"], place, t["side"], axis)
            s0, parent_road = r1, arc
            self.lines.put(line_id, {"root": place, "axis": lay.r3(axis), "parent": {"line": pline_id, "member": t["parent"], "side": t["side"]},
                                     "members": [], "bands": [], "spokes": []})
        rid = self.fresh_road(f"road:{place}")
        s_end = s0 + LEAD
        pts = [lay.pt(lay.polar_xz(s0, axis)), lay.pt(lay.polar_xz(s_end, axis))]
        self.put_road(rid, place, "spoke", spec.ring, parent_road, at, pts, s_end - s0, axis=lay.r3(axis), s0=lay.r3(s0), s_end=lay.r3(s_end),
                      open=True, wedge=[lay.r3(wedge[0] / lay.UNIT), lay.r3(wedge[1] / lay.UNIT)])
        member = {"place": place, "s0": lay.r3(s0), "r1": None, "road": rid, "arcs": {"L": None, "R": None},
                  "wedge": [lay.r3(wedge[0] / lay.UNIT), lay.r3(wedge[1] / lay.UNIT)],
                  "inner": [lay.r3(v / lay.UNIT) for v in self.plan.inner(place)]}
        line = self.lines.mut(line_id)
        line["members"].append(member)
        if t["left"] or t["right"]:  # side children are planned: the branch circle is drawn now, so that the circles of the members of a line
            member["r1"] = lay.r3(self.frontier(line) + BRANCH_CLEAR)  # grow outward from the one above (an arc then never meets a deeper spoke)
            self.spoke_to(rid, member["r1"])
        self.stats["members"] += 1
        return member

    def put_trunk_record(self, place: str, t: dict, member: dict) -> None:
        spec = self.spec(place)
        wedge = self.plan.wedge(place)
        if spec.parent is not None:
            self.ensure_street(spec.parent)
        rec = {"kind": "street", "shape": "trunk", "level": spec.ring, "class": lay.class_of(spec.ring),
               "parent": spec.parent or PLAZA_PLACE, "order": spec.order}
        self.finish_street_record(rec, spec)
        rec.update({"wedge": [lay.r3(wedge[0] / lay.UNIT), lay.r3(wedge[1] / lay.UNIT)], "axis": lay.r3(self.plan.axis(place)),
                    "inner": [lay.r3(v / lay.UNIT) for v in self.plan.inner(place)], "s0": member["s0"], "road": member["road"], "line": t["line"],
                    "role": t["role"]})
        if t["role"] == "side":
            rec["side"] = t["side"]
        self.places.put(place, rec)

    def branch_for(self, line_id: str, member_place: str, child: str, side: int, child_axis: float) -> tuple[float, str, float]:
        """Join `child` to the branch circle of `member_place` (drawn first if no side child has opened): (radius, arc road, distance along the arc)."""
        line = self.lines.mut(line_id)
        member = next(m for m in line["members"] if m["place"] == member_place)
        axis = line["axis"]
        r1 = member["r1"]
        assert r1 is not None, f"{member_place} has side children in the plan but no branch circle"
        key = "L" if side < 0 else "R"
        offset = abs(((child_axis - axis + 180.0) % 360.0) - 180.0)
        arc = member["arcs"][key]
        if arc is None:
            parent = self.covering(line, r1)
            self.extend_line(line, r1)
            rid = self.fresh_road(f"road:{member_place}:arc{key}")
            ring = self.spec(member_place).ring + 1
            arc = {"road": rid, "reach": 0.0}
            self.put_road(rid, member_place, "arc", ring, parent["road"], r1 - parent["s0"], [lay.pt(lay.polar_xz(r1, axis))], 0.0, side=side)
            member["arcs"][key] = arc
        if offset > arc["reach"] + EPS:
            arc["reach"] = lay.r3(offset)
            road = self.roads.mut(arc["road"])
            angles = [axis + side * a for a in self.arc_grid(offset)]
            road["points"] = [lay.pt(lay.polar_xz(r1, a)) for a in angles]
            road["length"] = lay.r3(math.radians(offset) * r1)
        return r1, arc["road"], math.radians(offset) * r1

    @staticmethod
    def arc_grid(offset: float) -> list[float]:
        """Offsets (degrees from the axis) of the points of an arc that reaches `offset`: every 5 degrees, so a longer arc keeps its first points."""
        n = int(offset // 5.0)
        out = [5.0 * k for k in range(n + 1)]
        if offset - out[-1] > 1e-6:
            out.append(offset)
        return out

    # ---- bands
    def carve_half(self, line: dict, s: float) -> float | None:
        """Half angle of the central wedge from which radius `s` is cut off by the branch circle of the deepest member that has one."""
        half = None
        for m in line["members"]:
            if m["r1"] is not None and s > m["r1"]:
                half = self.plan.half(self.plan.inner(m["place"]))
        return half

    def half_at(self, line: dict, carrier: str, s: float) -> float:
        h = self.plan.half(self.plan.wedge(carrier))
        c = self.carve_half(line, s)
        return h if c is None else min(h, c)

    def reach_at(self, line: dict, carrier: str, s: float, width: int) -> float:
        return min(lay.band_reach(s, self.half_at(line, carrier, s)), TRUNK_LANE + max(GROWTH_REACH, width))

    def spans(self, line: dict) -> list[tuple[float, float]]:
        """The radial intervals of a line that something stands in: its bands, the branch circles of its members (with their clearance) and
        its spoke ribs (with the gap after them). A band or a rib goes only where it overlaps none of them."""
        out = [(b["s"] - BAND / 2, b["s"] + BAND / 2) for b in line["bands"]]
        out += [(m["r1"] - BRANCH_CLEAR, m["r1"] + BRANCH_CLEAR) for m in line["members"] if m["r1"] is not None]
        out += [(lo, hi) for lo, hi in line["spokes"]]
        return sorted(out)

    def free_start(self, line: dict, a: float, length: float) -> float:
        """The smallest radius from `a` outward at which an interval `length` long overlaps none of the spans of the line."""
        spans = self.spans(line)
        moved = True
        while moved:
            moved = False
            for lo, hi in spans:
                if a < hi - EPS and a + length > lo + EPS:
                    a, moved = hi, True
        return a

    def band_room(self, line: dict, carrier: str, width: int) -> dict:
        """Where a street `width` cells long goes on a band: the open end of the band side with the smallest radius that has room, else a
        new band at the smallest free radius at which it fits the wedge. Returns the stretch: band index, side, radius, x0, x1, start, reach."""
        best = None
        for k, b in enumerate(line["bands"]):
            s = b["s"]
            reach = self.reach_at(line, carrier, s, width)
            for i in sorted((0, 1), key=lambda i: (b["used"][i], i)):
                used = b["used"][i]
                gap = ITEM_GAP if used > TRUNK_LANE + EPS else 0
                x0 = used + gap
                if x0 + width <= reach + EPS:
                    if best is None or s < best["s"] - EPS:
                        best = {"mode": "band", "band": k, "side": -1 if i == 0 else +1, "s": s, "x0": x0, "x1": x0 + width,
                                "start": used if gap else 0.0, "reach": reach, "new": False}
                    break
        s = line["members"][0]["s0"] + LEAD + BAND / 2
        for _ in range(64):
            half = self.half_at(line, carrier, s)
            nxt = ceil3(self.free_start(line, max(s, lay.fit_centre(TRUNK_LANE + width, half)) - BAND / 2, BAND) + BAND / 2)
            if abs(nxt - s) < EPS:
                break
            s = nxt
        if best is not None and best["s"] <= s + EPS:
            return best
        return {"mode": "band", "band": len(line["bands"]), "side": -1, "s": s, "x0": TRUNK_LANE, "x1": TRUNK_LANE + width, "start": 0.0,
                "reach": self.reach_at(line, carrier, s, width), "new": True}

    def spoke_room(self, line: dict, carrier: str, width: int) -> dict:
        """Where a street `width` cells long goes along the spoke (its lots on both sides of the axis): the smallest radius from which the lots fit
        the wedge and the interval is free."""
        a = line["members"][0]["s0"] + LEAD
        for _ in range(64):
            half = min(self.half_at(line, carrier, a), 85.0)
            nxt = ceil3(self.free_start(line, max(a, (1.5 + lay.FIT_MARGIN) / math.tan(math.radians(half))), width + ITEM_GAP))
            if abs(nxt - a) < EPS:
                break
            a = nxt
        return {"mode": "spoke", "s": a, "x0": a, "x1": a + width}

    def find_room(self, line: dict, carrier: str, width: int) -> dict:
        """The place of a street: a stretch of a band, or a stretch of the spoke where that ends clearly nearer the plaza (a narrow sector)."""
        band = self.band_room(line, carrier, width)
        spoke = self.spoke_room(line, carrier, width)
        return spoke if spoke["x1"] + SPOKE_MARGIN < band["s"] + BAND / 2 else band

    def rib_slots(self, spec: StreetSpec, ordinal: int) -> int:
        """The lots of rib `ordinal` of a road. A rib is sized to the houses the road holds when it opens, with the arrivals of the call (`hold`: a
        split group, the survivors, or 1), plus headroom. A continuation rib (`ordinal` >= 2) is sized the same way on the road's current count, and
        while the road is not over (it holds `max` or fewer) the ribs of the road hold at most `max` lots together."""
        n = self.hold.get(spec.place)
        if n is None:  # (no batch is being put on the road: the next house)
            n = len(self.lots_on(spec.place)) + 1
        size = district_rib_size(n, self.max)
        if ordinal > 1 and n <= self.max:
            rec = self.places.get(spec.place)
            held = sum(self.places.get(c)["rib"]["slots"] for c in ([spec.place] if "rib" in rec else []) + list(rec.get("lanes", [])))
            size = min(size, max(self.max - held, 1))
        return size

    def open_rib(self, spec: StreetSpec, ordinal: int) -> str:
        """Give a road its first rib (ordinal 1) or its next one: a stretch of a band of the line of its carrier, or of its spoke.
        Returns the place that carries the rib (the road itself, or the continuation)."""
        self.ensure_street(spec.place)
        self.open_member(spec.carrier)
        line_id = self.plan.trunks[spec.carrier]["line"]
        line = self.lines.mut(line_id)
        slots = self.rib_slots(spec, ordinal)
        width = math.ceil(slots / 2)
        st = self.find_room(line, spec.carrier, width)
        axis, s, mode = line["axis"], st["s"], st["mode"]
        rib_place = spec.place if ordinal == 1 else lay.lane_place(spec.key, ordinal)
        ring = spec.ring  # (a continuation is the road itself: its road has the class of the road)
        parent_member = self.covering(line, s)
        wedge = self.plan.wedge(spec.carrier)
        rib = {"trunk": spec.carrier, "line": line_id, "mode": mode, "x0": lay.r3(st["x0"]), "x1": lay.r3(st["x1"]), "s": lay.r3(s), "slots": slots,
               "next": 0, "block": rib_block_key(spec.key, ordinal), "wedge": [lay.r3(wedge[0] / lay.UNIT), lay.r3(wedge[1] / lay.UNIT)]}
        if mode == "spoke":  # the lane of the street is the spoke itself; the rib stands in its own stretch of radii
            line["spokes"].append([lay.r3(s), lay.r3(st["x1"] + ITEM_GAP)])
            self.extend_line(line, st["x1"])
            rib.update({"band": None, "side": 0})
            rid = parent_member["road"]
            self.stats["spoke_ribs"] += 1
        else:
            side = st["side"]
            i = 0 if side < 0 else 1
            if st["new"]:
                line["bands"].append({"s": lay.r3(s), "used": [TRUNK_LANE, TRUNK_LANE], "last": [None, None]})
                self.stats["bands"] += 1
            band = line["bands"][st["band"]]
            if band["last"][i] is None:
                parent, at = parent_member["road"], s - parent_member["s0"]
                self.extend_line(line, s + BAND / 2)
            else:
                parent = band["last"][i]
                at = self.roads.get(parent)["length"]
            a0 = axis + side * math.degrees(st["start"] / s)
            a1 = axis + side * math.degrees(st["x1"] / s)
            rid = self.fresh_road(f"road:{rib_place}" + (":lane" if spec.trunk and ordinal == 1 else ""))
            self.put_road(rid, rib_place, "lane", ring, parent, at, lay.arc_points(s, a0, a1), st["x1"] - st["start"], trunk=line_id,
                          band=st["band"], side=side, off=lay.r3(st["start"]), radius=lay.r3(s), bearings=[lay.r3(a0), lay.r3(a1)])
            band["used"][i] = lay.r3(st["x1"])
            band["last"][i] = rid
            rib.update({"band": st["band"], "side": side, "reach": lay.r3(st["reach"])})
        if ordinal == 1:
            street = self.places.mut(spec.place)
            street["rib"] = rib
            street["lane" if spec.trunk else "road"] = rid
            street["reserved"] = slots
        else:  # a CONTINUATION rib: one road everywhere, so the record has the road's own label, level, class and address
            lane = {"kind": "street", "shape": "rib", "lane_of": spec.place, "ordinal": ordinal, "continued": True, "level": spec.ring,
                    "class": lay.class_of(spec.ring), "parent": spec.place, "label": spec.label, "address": list(spec.address),
                    "carrier": spec.carrier, "lots": 0, "reserved": slots, "road": rid, "rib": rib}
            self.places.put(rib_place, lane)
            self.places.mut(spec.place).setdefault("lanes", []).append(rib_place)
            self.stats["continuations"] += 1
        for slot in range(slots):
            xz, facing = self.cell(rib, axis, slot)
            self.places.put(lay.reserved_place(rib["block"], slot), lay.reserved_record(rib_place, slot, "tail", xz, facing))
        self.stats["ribs"] += 1
        return rib_place

    @staticmethod
    def cell(rib: dict, axis: float, slot: int) -> tuple[tuple[float, float], float]:
        """(x, z) and facing of a slot of a rib. On a band: the inner row on even slots, the outer row on odd ones, two lots to a cell along
        the lane. Along the spoke: the left side on even slots, the right side on odd ones, one cell either side of the axis."""
        if rib["mode"] == "spoke":
            sign = -1.0 if slot % 2 == 0 else 1.0
            return lay.frame_xz(axis, rib["x0"] + slot // 2 + 0.5, sign * 1.0), axis + (90.0 if slot % 2 == 0 else -90.0)
        s, side = rib["s"], rib["side"]
        bearing = axis + side * math.degrees((rib["x0"] + slot // 2 + 0.5) / s)
        return lay.polar_xz(s - 1.0 if slot % 2 == 0 else s + 1.0, bearing), bearing + (0.0 if slot % 2 == 0 else 180.0)

    # ---- houses
    def active_rib(self, spec: StreetSpec) -> str:
        """The rib that takes the next house of a road: the first one that has an empty lot (a split leaves empty lots in front of the cursor),
        else the next continuation (opened here)."""
        rec = self.ensure_street(spec.place)
        carriers = ([spec.place] if "rib" in rec else []) + list(rec.get("lanes", []))
        for carrier in carriers:
            held = self.places.get(carrier)
            if held["lots"] < held["rib"]["slots"]:
                return carrier
        return self.open_rib(spec, len(carriers) + 1)

    def free_slot(self, rib: dict) -> int:
        """The lowest empty lot of a rib."""
        for slot in range(rib["slots"]):
            held = self.places.get(lay.reserved_place(rib["block"], slot))
            if held is not None and held["kind"] == "reserved":
                return slot
        raise AssertionError(f"rib {rib['block']} has no empty lot")

    def put_house(self, article_id: str, spec: StreetSpec, tag: str | None, seq: int, track: bool = True) -> dict:
        """Put a house on the lowest empty lot of its road (opening a rib first when the road has none). The record is the lot record of a layout
        plus what the world keeps: the road, the address `tag` (None: no topic), and the arrival number `seq`. `track=False` is a house that stood in
        the world already and is put again (a split): it is no arrival."""
        rib_place = self.active_rib(spec)
        carrier = self.places.mut(rib_place)
        rib = carrier["rib"]
        slot = self.free_slot(rib)
        rib["next"] = max(rib["next"], slot + 1)
        carrier["lots"] += 1
        carrier["reserved"] -= 1
        free = lay.reserved_place(rib["block"], slot)
        old = self.places.get(free)
        assert old is not None and old["kind"] == "reserved", f"slot {slot} of {rib_place} is not free"
        self.places.delete(free)
        lot = lay.lot_record(article_id, rib_place, slot, slot, (old["position"]["x"], old["position"]["z"]), old["facing"])
        lot.update({"street": spec.place, "tag": tag, "seq": seq})
        self.places.put(lay.article_place(article_id), lot)
        if track:
            if article_id not in self.placements:  # (a house a split puts again in the same call is still one house of the call)
                self.stats["houses"] += 1
            self.placements[article_id] = lot
        if self._by_road is not None:
            self._by_road.setdefault(spec.place, []).append(lot)
        return lot

    def delta(self) -> dict:
        return {"places": self.places.new, "roads": self.roads.new, "lines": self.lines.new, "seq": self.seq, "chronicle": self.chronicle}

    def result(self, **extra) -> dict:
        """What a call returns: the records that are new or changed (`places`, `roads`), the delta that carries them and some counts."""
        d = self.delta()
        return {**extra, "places": {k: v for k, v in d["places"].items() if v is not None}, "roads": {k: v for k, v in d["roads"].items() if v is not None},
                "delta": d, "stats": self.stats}


# ---------------------------------------------------------------------------------------------- assign ----
def assign(plan: dict | PlanView, tree: dict | TreeView, placed: dict, arrivals: list[dict], *, event_id: int | None = None) -> dict:
    """Place the arrivals, in the order given, in the world `placed`; return what to add (see the module docstring).

    An arrival is `{"id", "topics"}`: its address is its deepest topic of the tree (`bibliopolis.tree.major_tag`), None when it has none (the root
    zone). The arrivals are resolved, placed and checked one at a time, in this order, because the road of the next house depends on the splits the
    houses before it caused. `event_id` is the event the call belongs to: the chronicle entries it causes carry it (None: no events)."""
    pv = plan if isinstance(plan, PlanView) else PlanView(plan)
    tv = tree if isinstance(tree, TreeView) else TreeView(tree)
    w = World(pv, tv, placed, event_id=event_id)
    by_id = {a["id"]: a for a in arrivals}
    if len(by_id) != len(arrivals):
        raise ValueError("an item arrives twice")
    clash = [aid for aid in sorted(by_id) if placed["places"].get(lay.article_place(aid)) is not None]
    if clash:
        raise ValueError(f"already placed: {clash[:3]}")
    for a in arrivals:
        tag = major_tag(tv, a)
        w.seq += 1
        house = {"article": a["id"], "tag": tag, "seq": w.seq}
        w.arrival_ids.add(a["id"])
        w.add_houses(w.road_for_tag(tag), [house], "arrival")
    for aid in w.placements:  # (a house a later split moved is where it stands now)
        w.placements[aid] = w.places.get(lay.article_place(aid))
    return w.result(placements=w.placements)


def complete(plan: dict | PlanView, tree: dict | TreeView, placed: dict, *, event_id: int | None = None) -> dict:
    """What a world needs after its last arrival. In a `mirror` plan every topic of `plan["roads"]` is a road, but a road that no house stands on or
    below (a topic an item is filed under whose address is elsewhere) has no street record until the world is completed; this writes it. Nothing else
    changes, and a `grow` plan has nothing to complete (the delta is empty).

    It is a separate call, not part of `assign`, so that a world does not depend on how its arrivals were cut into calls: the records of a road
    that a later arrival is going to need would otherwise be made early, at the end of the first call."""
    pv = plan if isinstance(plan, PlanView) else PlanView(plan)
    tv = tree if isinstance(tree, TreeView) else TreeView(tree)
    w = World(pv, tv, placed, event_id=event_id)
    if w.mirror:
        w.ensure_roads()
    return w.result()
