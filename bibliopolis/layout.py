"""The vocabulary of a city document (layout version 4): constants, place ids, angles and geometry helpers, the records every place and
road is made of, the measures read back from a document, and the stable text a document is written as.

The city is one continent around a town hall plaza at the origin. The plaza is the root of the topic tree; the road network is a tree that
radiates from it. Geometry is a fishbone radial tree laid out in polar frames: bearings in degrees clockwise from north, lengths in cells,
x east, z south.

  wedge   the sector of the plane that a ring-1 road (and, below it, a trunk) may use. The ring-1 roads split the circle in proportion to
          their weight, with a minimum; a trunk splits its wedge again among its children. Nothing of a road leaves its wedge, so the open
          outer end of a wedge is free ground for ever.
  trunk   a ring-1 road, and a container road of weight >= TRUNK_MIN under a trunk: a spoke, a ray through the plaza along the bisector of
          its wedge, open outward.
  band    an arc around the plaza that crosses a trunk: a row of lots, a lane and a row of lots (3 cells). The roads of a trunk are
          consecutive stretches of its bands; the lots of a stretch are one cell long along the lane, two to a cell across it.
  roads   a tree rooted at the plaza: every road record names its parent and where it joins it (kinds spoke, arc, lane), so the walk from
          the centre to any door is the sum of the `at` of its ancestors and the length along its own lane.

Same input, same bytes: inputs are sorted by id, children in code-point order, the angles are integers (units of 1/100 degree),
coordinates are rounded to 3 decimals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import coast
from .canonical import dumps

LAYOUT_VERSION = "v4"
SCHEMA_VERSION = "4"

# ---- the cut
HOME_MAX = 20  # H: the lots a street of the plan holds in one rib, and the size of a leaf street of the plan
JOIN = "・"  # joins the names of the topics collapsed into one road
HEAD_RESERVE = 1  # empty lots before the oldest lot of a rib in the weight of a street of the plan
LANE_FIRST = 2  # the first overflow lane of a street of the plan is lane 2; the street itself is number 1
RESERVE_MIN, RESERVE_DIVISOR = 2, 4  # tail reserve = max(2, ceil(lots / 4))
CLASS_NAMES = ("大道", "路", "巷", "弄")  # display class of ring 1, 2, 3 and 4 (and deeper: it saturates at 弄)

# ---- ids
ARTICLE_PREFIX = "place:article:"
LANE_PREFIX = "place:lane:"
PLAZA_PLACE = "place:plaza"
PLAZA_LABEL = "市政廳"


def tag_place(tag: str) -> str:
    """The place id of the road of a topic (`tag` is the id of a topic of the tree)."""
    return f"place:tag:{tag}"


def article_place(article_id: str) -> str:
    return ARTICLE_PREFIX + article_id


def lane_place(key: str, ordinal: int) -> str:
    return f"{LANE_PREFIX}{key}:{ordinal}"


def reserved_place(block_key: str, n: int) -> str:
    return f"place:reserved:{block_key}:{n}"


# ------------------------------------------------------------------------------------------ the weight of a street ----
def rib_tail(lots: int) -> int:
    """Empty lots after the newest lot of a rib: max(2, ceil(lots / 4))."""
    return max(RESERVE_MIN, math.ceil(lots / RESERVE_DIVISOR))


def rib_slots(lots: int) -> int:
    """Lots plus the head and tail reserves: the number of lots a rib of the plan can hold, and its weight."""
    return HEAD_RESERVE + lots + rib_tail(lots)


# ------------------------------------------------------------------------------------------------------ angles ----
UNIT = 100  # angle units per degree: all the arithmetic of the wedges is on integers
FULL = 360 * UNIT
MIN_RING1, MIN_SIDE, MIN_CENTRAL = 14 * UNIT, 4 * UNIT, 8 * UNIT  # least angle of a ring-1 wedge, a side wedge, a central wedge


def allocate(total: int, weights: list[int], mins: list[int]) -> list[int]:
    """Split `total` units among items in proportion to their weights, none below its minimum; the parts sum to `total`.

    Integer arithmetic only (largest remainder, ties to the lower index), so every implementation agrees to the unit. When the
    minimums alone need more than the total they share it in proportion to themselves."""
    n = len(weights)
    if n == 0:
        return []
    if sum(mins) >= total:
        return _share(total, [max(m, 1) for m in mins], [False] * n, mins)
    fixed = [False] * n
    while True:
        rest = total - sum(m for m, f in zip(mins, fixed) if f)
        wsum = sum(w for w, f in zip(weights, fixed) if not f)
        changed = False
        for i in range(n):
            if not fixed[i] and rest * weights[i] < mins[i] * wsum:
                fixed[i], changed = True, True
        if not changed:
            return _share(rest, weights, fixed, mins)


def _share(rest: int, weights: list[int], fixed: list[bool], mins: list[int]) -> list[int]:
    """The free items take `rest` in proportion to their weights (a fixed item keeps its minimum)."""
    n = len(weights)
    out = [mins[i] if fixed[i] else 0 for i in range(n)]
    free = [i for i in range(n) if not fixed[i]]
    if not free:
        return out
    wsum = sum(max(weights[i], 1) for i in free)
    rem: dict[int, int] = {}
    for i in free:
        out[i], rem[i] = divmod(rest * max(weights[i], 1), wsum)
    for i in sorted(free, key=lambda i: (-rem[i], i))[: rest - sum(out[i] for i in free)]:
        out[i] += 1
    return out


@dataclass(frozen=True)
class Wedge:
    """The sector of the plane between two bearings seen from the plaza, in angle units clockwise from north (may be negative)."""

    lo: int
    hi: int

    @property
    def span(self) -> int:
        return self.hi - self.lo

    @property
    def axis(self) -> float:
        return (self.lo + self.hi) / (2 * UNIT)

    @property
    def half(self) -> float:
        return (self.hi - self.lo) / (2 * UNIT)


def split_wedge(wedge: Wedge, heavy, left: list, right: list) -> tuple[Wedge, list[Wedge], list[Wedge]]:
    """The wedge of the heavy child (centred on the axis of its parent) and the side wedges, heaviest child outermost.

    `heavy`, `left` and `right` are streets (anything with a `weight`); `left` and `right` are the side children heaviest first, and the wedges
    come back in the same order. Each side has the same angle, so the heavy child keeps the axis of its parent."""
    span = wedge.span
    if not left and not right:
        return wedge, [], []
    # a wedge too narrow for the minimums scales them all down together (no part is ever empty)
    crowd = max(len(left), len(right))
    fit = min(1.0, span / (MIN_CENTRAL + 2 * MIN_SIDE * crowd))
    min_side, min_central = max(1, int(MIN_SIDE * fit)), max(1, int(MIN_CENTRAL * fit))
    total = heavy.weight + sum(c.weight for c in left + right)

    def need(side: list) -> int:  # the angle a side asks for: its weight's share, at least the minimum of each child
        return max(min_side * len(side), span * sum(c.weight for c in side) // total) if side else 0

    s = min(max(need(left), need(right)), (span - min_central) // 2)
    central = Wedge(wedge.lo + s, wedge.hi - s)

    def lay(side: list, start: int, sign: int) -> list[Wedge]:
        # allocate from the inside out (lightest child first), then hand the wedges back heaviest first
        inner_out = list(reversed(side))
        parts = allocate(s, [c.weight for c in inner_out], [min_side] * len(inner_out))
        out, edge = [], start
        for part in parts:
            out.append(Wedge(edge - part, edge) if sign < 0 else Wedge(edge, edge + part))
            edge += sign * part
        return list(reversed(out))

    return central, lay(left, central.lo, -1), lay(right, central.hi, +1)


# --------------------------------------------------------------------------------------------------- geometry ----
PLAZA_RADIUS = 6.0  # the town hall plaza: the spokes of ring 1 start at its rim
TRUNK_LANE = 0.5  # half the width of a trunk lane: the first lot of a band stands this far from the axis
LEAD = 1.0  # bare trunk before the first band
BAND = 3.0  # a band: a row of lots, a lane and a row of lots
RIB_GAP = 0.0  # empty cells between two bands (the rows of lots of two bands stand back to back)
ITEM_GAP = 1  # empty cells between two streets of one band
FIT_MARGIN = 0.5  # clear cells between a lot and the border of its wedge
TRUNK_MIN = 300  # weight (lots plus reserved lots of the plan) from which a container street gets a trunk and a wedge of its own
ARC_STEP = 5.0  # degrees: the widest chord of the polyline of an arc (the floor of its chord count, `arc_chords`)
ARC_SAGITTA = 0.05  # cells: the most a chord of the polyline of an arc lies inside its circle, at any radius (the bound of the ring road's polyline too)


def polar_xz(rho: float, deg: float) -> tuple[float, float]:
    """(x, z) of the point at distance `rho` from the plaza on the bearing `deg` (clockwise from north; x east, z south)."""
    r = math.radians(deg)
    return rho * math.sin(r), -rho * math.cos(r)


def frame_xz(axis: float, s: float, t: float) -> tuple[float, float]:
    """(x, z) of the point at `s` along the spoke of bearing `axis` (through the plaza) and `t` to its right (clockwise)."""
    r = math.radians(axis)
    return s * math.sin(r) + t * math.cos(r), -s * math.cos(r) + t * math.sin(r)


def band_reach(s: float, half_deg: float) -> float:
    """Farthest lateral extent (cells along the lane, off the trunk axis) a lot may have on the band of radius `s` inside a wedge
    of half angle `half_deg`: the arc of the inner row, less the clear margin."""
    return (s - 1.5) * math.radians(half_deg) - FIT_MARGIN


def fit_centre(extent: float, half_deg: float) -> float:
    """Smallest band radius at which a street that reaches `extent` cells off the axis stays inside the wedge."""
    return 1.5 + (extent + FIT_MARGIN) / math.radians(half_deg)


def class_of(ring: int) -> str:
    """Display class of a street ring: 大道, 路, 巷, then 弄 for every deeper ring."""
    return CLASS_NAMES[min(ring, len(CLASS_NAMES)) - 1]


def r3(v: float) -> float:
    return round(v, 3) + 0.0  # + 0.0 turns -0.0 into 0.0


def pt(xz: tuple[float, float]) -> list[float]:
    return [r3(xz[0]), r3(xz[1])]


def arc_chords(radius: float, a: float, b: float) -> int:
    """The number of chords of the polyline of the arc of `radius` from bearing `a` to `b`: one every ARC_STEP degrees at most (the count of the first version, the floor), and more where a
    chord would lie deeper than ARC_SAGITTA inside the circle: the least n with radius * (1 - cos(phi / (2 * n))) <= ARC_SAGITTA, phi = radians(|b - a|), that is
    ceil(phi / (2 * acos(1 - ARC_SAGITTA / radius))). Up to radius 52.53 a chord of 5 degrees keeps within the bound, so an arc there keeps its points; beyond it the polyline follows its
    lane at any radius."""
    n = max(1, math.ceil(abs(b - a) / ARC_STEP))
    return max(n, math.ceil(math.radians(abs(b - a)) / (2.0 * math.acos(1.0 - ARC_SAGITTA / radius))))


def arc_points(radius: float, a: float, b: float) -> list[list[float]]:
    """Points of the arc of the given radius from bearing `a` to `b`: `arc_chords` chords of equal angle, point k at the bearing a + (b - a) * k / n."""
    n = arc_chords(radius, a, b)
    return [pt(polar_xz(radius, a + (b - a) * k / n)) for k in range(n + 1)]


# ----------------------------------------------------------------------------------------------- the records ----
def lot_record(article: str, parent: str, order: int, slot: int, xz: tuple[float, float], facing: float) -> dict:
    """The place record of a house: one cell of a rib. `facing` is a bearing in degrees (any number of turns)."""
    return {"kind": "lot", "article": article, "parent": parent, "order": order, "slot": slot, "position": {"x": r3(xz[0]), "z": r3(xz[1])},
            "facing": r3(facing % 360)}


def reserved_record(parent: str, slot: int, end: str, xz: tuple[float, float], facing: float) -> dict:
    """The place record of an empty lot kept for a house that does not exist yet (`end`: head or tail of its rib)."""
    return {"kind": "reserved", "parent": parent, "slot": slot, "end": end, "position": {"x": r3(xz[0]), "z": r3(xz[1])}, "facing": r3(facing % 360)}


ANNEX_RECORD_KEYS = ("kind", "article", "parent", "form", "rank", "seq")  # the keys of an annex record, in the order they are written


def annex_record(article: str, parent: str, form: str, rank: int, seq: int) -> dict:
    """The place record of an item that exists for another item: it has no lot, no position and no slot, and stands where its house stands. `parent` is the place of the lot of
    that house, `rank` the number of the annex among those of that house in the same form (1 is the first to arrive), `seq` its arrival number."""
    return {"kind": "annex", "article": article, "parent": parent, "form": form, "rank": rank, "seq": seq}


def road_record(street: str, kind: str, ring: int, parent: str | None, at: float, points: list[list[float]], length: float, **extra) -> dict:
    """A road: the street it serves, its display class, the road it hangs on and where (`at`: distance along the parent), its polyline."""
    rec = {"street": street, "kind": kind, "class": class_of(ring), "parent": parent, "at": r3(at), "length": r3(length), **extra}
    rec["points"] = points
    return rec


# -------------------------------------------------------------------------------------------- the document ----
KIND_NOTES = {
    "plaza": "the town hall plaza at the origin: the root of the topic tree (a virtual root over the topic roots when the tree has several)",
    "street": "a road of the city: a topic that has houses on it or below it. shape trunk: a spoke with bands of streets and a wedge; rib: a "
              "street that is a stretch of a band on the trunk of `carrier`; group: a road with roads below it, "
              "its roads hang on the bands of `carrier`; ring: the ring road round the plaza (the root of the road tree) or one of its laps, a concentric "
              "ring road outside it, with lots on both sides of its lane",
    "lot": "one item's house: one cell, id place:article:<item id>",
    "reserved": "an empty lot kept for a house that does not exist yet",
}
ROAD_NOTES = {
    "spoke": "a straight road through the plaza along the bisector of a wedge, open outward when `open`",
    "arc": "a connector: an arc around the plaza from a trunk to the axis of a side wedge",
    "lane": "an arc around the plaza across a trunk (a band): one stretch per street, each starting where the previous one ends",
    "ring": "a closed circle round the plaza (the ring road or one of its laps): a polyline from north clockwise whose last point is its first, with no parent",
}
ANNEX_KIND_NOTE = ("an item that exists for another item, with no lot of its own: it stands where its house stands (`parent` is the place of that house's lot), as a `form` "
                   "wing (on its side wall) or mailbox (at its gate); `rank` numbers the annexes of one house and form by arrival, 1 first; id place:article:<item id>")
ANNEX_NOTES = {
    "composition.buildings": "every article is one building, a house or an annex: `articles` and `buildings` count both, while `world.houses` and `measure.lots` count the houses, "
                             "which are the lots",
    "world.chronicle.annex": "an item that exists for another item stands beside its house: `annex` is the item, `parent` its house and `form` how it stands there",
}  # a document has them only when it holds an annex
ANNEX_NOTES_HAND = {
    "world.chronicle.absorbed": "a house that stood on a lot of its own is an annex now, when the house it exists for arrives or by the event `annex`: `absorbed` is the house, `parent` the house "
                                "it stands beside, `form` how, and `left` the place it left (a lot of a road stays reserved, a lot of the ring leaves nothing)",
}  # a document of a world built by hand has it only when it holds an annex
GEOMETRY = {
    "unit": "cell", "x": "east", "z": "south", "angle": "degrees clockwise from north (may be negative or above 360)",
    "origin": "the centre of the town hall plaza", "position": "centre of the cell",
    "band": f"{BAND} cells (a row of lots, a lane, a row of lots) and {RIB_GAP} empty between bands",
    "reserve": "a road has one rib, laid out for the houses its road holds when it opens and max(4, ceil(n / 2)) empty lots after them, in whole cells and "
               "never above the limit of a road; a full rib grows at its end, in place, and what lies beyond it moves outward",
}


def finish_layout(layout: dict, with_coast: bool = True) -> dict:
    """The tail of every document: the coast of the land, then the measures read back from the document."""
    if with_coast:
        layout["coast"] = coast.coast_of(layout)
    layout["composition"]["measure"] = measure(layout)
    return layout


# ----------------------------------------------------------------------------------------------- measures ----
def road_starts(layout: dict) -> dict[str, float]:
    """road id -> length of the road walk from the centre of the plaza to the start of the road.

    A road with no parent starts at its own `s0` when it has one (a spoke: the plaza rim in a city with no ring road, the outer edge of the ring road in a city
    with one), at its `radius` when it is a ring road (the lane of the ring), else at the plaza rim."""
    roads = layout["roads"]
    cum: dict[str, float] = {}

    def start_of(rid: str) -> float:
        if rid not in cum:
            r = roads[rid]
            if r["parent"]:
                cum[rid] = start_of(r["parent"]) + r["at"]
            elif "s0" in r:
                cum[rid] = r["s0"]
            elif r["kind"] == "ring":
                cum[rid] = r["radius"]
            else:
                cum[rid] = layout["centre"]["radius"]
        return cum[rid]

    for rid in roads:
        start_of(rid)
    return cum


def ring_walk(places: dict[str, dict], lot: dict, lap: dict) -> float:
    """The walk from the centre of the plaza to a house on the ring road: straight out through the nearest gate to the lane of its lap, R, then along the lane to
    the house: R + R * radians(d), d the smallest angle between the bearing of the house (atan2(x, -z) of its position, degrees) and a gate of G1 (`ring.gaps` of
    the root of the ring, the gates by which the plaza reaches it; none: the bearing from north)."""
    radius = lap["ring"]["radius"]
    gates = places[lap.get("lane_of", lot["parent"])]["ring"]["gaps"] or [0.0]
    bearing = math.degrees(math.atan2(lot["position"]["x"], -lot["position"]["z"]))
    d = min(abs((bearing - g + 180.0) % 360.0 - 180.0) for g in gates)
    return radius + radius * math.radians(d)


def lot_door_walks(layout: dict) -> dict[str, float]:
    """article id -> length of the road walk from the centre of the plaza to the door of its lot, along the road tree.

    The door of a lot is the point of its lane right in front of it. A house on the ring road walks `ring_walk`."""
    places, roads = layout["places"], layout["roads"]
    starts = road_starts(layout)
    out: dict[str, float] = {}
    for p in places.values():
        if p["kind"] != "lot":
            continue
        owner = places[p["parent"]]
        if owner.get("shape") == "ring":
            out[p["article"]] = ring_walk(places, p, owner)
            continue
        rid = owner.get("lane") or owner["road"]
        road, rib = roads[rid], owner["rib"]
        centre = rib["x0"] + p["slot"] // 2 + 0.5
        along = centre - road["s0"] if road["kind"] == "spoke" else centre - road["off"]
        out[p["article"]] = starts[rid] + along
    return out


def place_root(places: dict[str, dict], pid: str) -> str:
    """The ring-1 street place a place stands under."""
    while True:
        p = places[pid]
        parent = p.get("parent")
        if parent is None or parent == PLAZA_PLACE:
            return pid
        pid = parent


def measure(layout: dict) -> dict:
    """The numbers of a city, read back from the document alone. Every house is on the surface; a lap of the ring road (`continued`) is the ring road it continues.
    `ring_lots` counts the houses on every lap of the ring road, and the ring counts as one 大道 (its laps are continuations)."""
    places, roads = layout["places"], layout["roads"]
    lots = [p for p in places.values() if p["kind"] == "lot"]
    reserved = [p for p in places.values() if p["kind"] == "reserved"]
    radius = max([math.hypot(p["position"]["x"], p["position"]["z"]) + 0.71 for p in lots + reserved] + [0.0])
    walks = lot_door_walks(layout)
    values = sorted(walks.values())
    streets = [p for p in places.values() if p["kind"] == "street"]
    by_class: dict[str, int] = {}
    for p in streets:
        if not p.get("continued"):
            by_class[p["class"]] = by_class.get(p["class"], 0) + 1
    land = sum(coast.polygon_area(poly) for poly in layout.get("coast", {}).get("polygons", []))
    ring1 = layout["composition"]["ring1"]
    out = {
        "lots": len(lots), "reserved_lots": len(reserved), "slots": len(lots) + len(reserved),
        "land_area": round(land, 1), "land_per_lot": round(land / len(lots), 2) if lots and land else None,
        "land_per_slot": round(land / (len(lots) + len(reserved)), 2) if lots and land else None,
        "max_radius": round(radius, 1),
        "walk_mean": round(sum(values) / len(values), 1) if values else 0.0,
        "walk_median": round(values[len(values) // 2], 1) if values else 0.0,
        "walk_longest": round(values[-1], 1) if values else 0.0,
        "streets_by_class": {c: by_class.get(c, 0) for c in CLASS_NAMES},
        "max_ring": max((p["level"] for p in streets), default=0),
        "ring1_wedges": [{"place": r["place"], "label": r["label"], "span": r["span"]} for r in ring1],
        "roads": len(roads), "road_length": round(sum(r["length"] for r in roads.values()), 1),
    }
    out["ring_lots"] = sum(1 for p in lots if places[p["parent"]].get("shape") == "ring")  # (they are in the numbers above)
    return out


# ------------------------------------------------------------------------------------------------ the text ----
def render(layout: dict) -> str:
    """Stable text: header fields pretty-printed, then one road and one place per line. Numbers are written in the canonical form (bibliopolis.canonical)."""
    head = {k: v for k, v in layout.items() if k not in ("roads", "coast", "places")}
    head_text = dumps(head, indent=1)[:-2]

    def lines(d: dict) -> str:
        return ",\n".join(f"  {dumps(k)}: {dumps(v)}" for k, v in d.items())

    parts = [head_text, ',\n "roads": {\n' + lines(layout["roads"]) + "\n }"]
    if "coast" in layout:
        c = layout["coast"]
        polys = ",\n".join("   " + dumps(p) for p in c["polygons"])
        parts.append(',\n "coast": {' + ",".join(f"{dumps(k)}:{dumps(v)}" for k, v in c.items() if k != "polygons")
                     + ',"polygons":[\n' + polys + "\n  ]}")
    parts.append(',\n "places": {\n' + lines(layout["places"]) + "\n }\n}\n")
    return "".join(parts)
