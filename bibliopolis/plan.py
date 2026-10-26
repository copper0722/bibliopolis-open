"""The zoning plan: the directions of the city, fixed before the first house arrives.

The cut (bibliopolis.cut) reads the whole library once. The plan keeps what must be stable before any house exists, and nothing else:

  ring 1       the sectors of the circle, one per root street, in proportion to their weight (a minimum each), centred on north.
  trunks       for every trunk (a ring-1 street, and below it a container street heavy enough to have a sector of its own): which child
               continues it straight (the heavy path), which children branch to the left or right, and the sub-wedge of each.
  streets      the streets of the cut with their addresses and what is collapsed into them; `sites` maps every topic to the street that
               holds it.
  districts    the rule the roads open by: {max, min, extract, count}.

There is no radius, no band and no coordinate in a plan: a street opens at the frontier of its trunk's line when its first house arrives
(bibliopolis.world). The plan is plain JSON-able data built from sorted inputs with integer angles (units of 1/100 degree).

Two modes share it:

  grow     the roads are decided by the houses that stand: a crowded road opens a road for its largest group. The plan pins the directions
           and the ring-1 streets the root zone may open.
  mirror   every topic an item is filed under (any of its topics), and every topic above one, is a road from the start (`plan["roads"]`), and
           the plan has a street for each of them: the topic tree is the street plan.
"""

from __future__ import annotations

from types import SimpleNamespace

from . import cut
from . import layout as lay
from .tree import TreeView

ZONING_VERSION = "districts-1"
SCHEMA_VERSION = "1"
GROW, MIRROR = "grow", "mirror"
MODES = (GROW, MIRROR)  # the modes `build` knows
HAND = "hand"  # the mode of a world built by hand (bibliopolis.hand): no library to plan from, so it is not one of the modes of `build`
MAX_HOUSES, MIN_HOUSES = 40, 10  # a road holds 10 to 40 houses
DISTRICT_EXTRACT, DISTRICT_COUNT = "largest", "direct"  # the only rules the engine knows: the largest group is opened, the houses on the road itself are counted


def check_districts(districts: dict) -> None:
    """ValueError unless `params.districts` is a rule the engine implements: whole numbers 1 <= min <= max, and the two named rules."""
    mx, mn = districts.get("max"), districts.get("min")
    if not (isinstance(mx, int) and isinstance(mn, int) and not isinstance(mx, bool) and not isinstance(mn, bool) and 1 <= mn <= mx):
        raise ValueError(f"the district rule needs whole numbers 1 <= min <= max, got max={mx!r} min={mn!r}")
    if districts.get("extract") != DISTRICT_EXTRACT or districts.get("count") != DISTRICT_COUNT:
        raise ValueError(f"the district rule knows extract={DISTRICT_EXTRACT!r} and count={DISTRICT_COUNT!r} only")


def deg(units: int) -> float:
    """A wedge edge in degrees: angles are integers of 1/100 degree, so two decimals are exact."""
    return round(units / lay.UNIT, 2) + 0.0


# ------------------------------------------------------------------------------------------ directions ----
def ring1_wedges(ring1: list[cut.Street], min_ring1: int) -> list[lay.Wedge]:
    """The wedges of ring 1: the circle in proportion to weight, none below `min_ring1`, centred on north."""
    angles = lay.allocate(lay.FULL, [s.weight for s in ring1], [min_ring1] * len(ring1))
    edge, out = -(sum(angles) // 2), []
    for a in angles:
        out.append(lay.Wedge(edge, edge + a))
        edge += a
    return out


def mark_lines(ring1: list[cut.Street], trunk_min: int) -> None:
    """Which streets are trunks: every ring-1 street, and below them a container street of weight >= `trunk_min` under a trunk.

    A ring-1 leaf street is a trunk with one rib. `carrier` is the trunk a street hangs on."""

    def visit(s: cut.Street, parent: cut.Street | None) -> None:
        s.trunk = True if parent is None else (s.kind == "container" and parent.trunk and s.weight >= trunk_min)
        s.carrier = s if s.trunk else parent.carrier  # type: ignore[union-attr]
        for c in s.leaves + s.containers:
            visit(c, s)

    for s in ring1:
        visit(s, None)


class _Directions:
    """Walks the trunks of the cut and records their wedges, heavy child and sides."""

    def __init__(self) -> None:
        self.trunks: dict[str, dict] = {}

    def trunk(self, street: cut.Street, wedge: lay.Wedge, parent: cut.Street | None, role: str, side: int, line: str, index: int) -> None:
        rec: dict = {"name": street.key, "label": street.label, "ring": street.ring, "role": role, "side": side,
                     "parent": parent.place if parent is not None else None, "line": line, "index": index,
                     "wedge": [deg(wedge.lo), deg(wedge.hi)], "inner": [deg(wedge.lo), deg(wedge.hi)], "heavy": None, "left": [], "right": []}
        self.trunks[street.place] = rec
        real = [c for c in street.containers if c.trunk]
        if not real:
            return
        ranked = sorted(real, key=lambda c: (-c.weight, c.key))
        heavy = ranked[0]
        left: list[cut.Street] = []
        right: list[cut.Street] = []
        weights = {-1: 0, +1: 0}
        for c in ranked[1:]:  # each next child goes to the lighter side (the left one on a tie)
            side_ = -1 if weights[-1] <= weights[+1] else +1
            weights[side_] += c.weight
            (left if side_ < 0 else right).append(c)
        # the central wedge carries the heavy child and every street that hangs on this trunk's own bands, not the heavy child alone: those
        # streets keep arriving after the side wedges are cut off
        central_load = SimpleNamespace(weight=street.weight - sum(c.weight for c in left + right))
        central, lwedges, rwedges = lay.split_wedge(wedge, central_load, left, right)
        rec["inner"] = [deg(central.lo), deg(central.hi)]
        rec["heavy"] = heavy.place
        rec["left"] = [{"place": c.place, "wedge": [deg(w.lo), deg(w.hi)]} for c, w in zip(left, lwedges)]
        rec["right"] = [{"place": c.place, "wedge": [deg(w.lo), deg(w.hi)]} for c, w in zip(right, rwedges)]
        self.trunk(heavy, central, street, "heavy", 0, line, index + 1)
        for sd, kids, wedges in ((-1, left, lwedges), (+1, right, rwedges)):
            for c, w in zip(kids, wedges):
                self.trunk(c, w, street, "side", sd, c.place, 0)


# ----------------------------------------------------------------------------------------------- plan ----
def build_plan(tree: TreeView, items: list[dict], *, mode: str = GROW, max_houses: int = MAX_HOUSES, min_houses: int = MIN_HOUSES,
               home_max: int = lay.HOME_MAX, trunk_min: int = lay.TRUNK_MIN, min_ring1: int = lay.MIN_RING1) -> dict:
    """The plan for a topic tree and the items of a library (each `{"id", "topics"}`; the order does not matter).

    `max_houses` and `min_houses` are the district rule: a road holds `max_houses` houses directly, and a group of at least `min_houses`
    opens a road of its own (in `mirror` the rule only marks a road `over`). `home_max` and `trunk_min` shape the cut and the trunks."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    districts = {"max": max_houses, "min": min_houses, "extract": DISTRICT_EXTRACT, "count": DISTRICT_COUNT}
    check_districts(districts)
    if not isinstance(home_max, int) or isinstance(home_max, bool) or home_max < 1:
        raise ValueError(f"home_max must be a whole number >= 1, got {home_max!r}")
    comp = cut.compose(tree, items, home_max, whole_tree=(mode == MIRROR))
    mark_lines(comp.ring1, trunk_min)
    wedges = ring1_wedges(comp.ring1, min_ring1)
    directions = _Directions()
    for s, w in zip(comp.ring1, wedges):
        directions.trunk(s, w, None, "ring1", 0, s.place, 0)

    streets: dict[str, dict] = {}
    sites: dict[str, str] = {}

    def walk(s: cut.Street) -> None:
        streets[s.place] = {"name": s.key, "kind": s.kind, "ring": s.ring, "label": s.label, "address": s.address,
                            "parent": s.parent.place if s.parent is not None else None, "carrier": s.carrier.place,  # type: ignore[union-attr]
                            "collapsed": s.collapsed, "absorbed": s.absorbed, "ribs": [len(r.lots) for r in s.ribs], "weight": s.weight,
                            "order": s.order}
        sites.setdefault(s.key, s.place)
        for t in s.collapsed + s.absorbed:
            sites.setdefault(t, s.place)
        for c in s.leaves + s.containers:
            walk(c)

    for s in comp.ring1:
        walk(s)
    ring1 = [{"place": s.place, "name": s.key, "label": s.label, "weight": s.weight, "wedge": [deg(w.lo), deg(w.hi)]}
             for s, w in zip(comp.ring1, wedges)]
    plan = {
        "schema_version": SCHEMA_VERSION,
        "zoning_version": ZONING_VERSION,
        "mode": mode,
        "params": {"home_max": home_max, "trunk_min": trunk_min, "min_ring1": deg(min_ring1), "centre_tag": comp.centre_tag,
                   "districts": districts},
        "ring1": ring1,
        "trunks": dict(sorted(directions.trunks.items())),
        "streets": dict(sorted(streets.items())),
        "sites": dict(sorted(sites.items())),
    }
    if mode == MIRROR:
        plan["roads"] = comp.filed_topics()
    return plan
