"""The ring road: the root of the road tree, a closed circular road round the town hall.

The ring is a street like any other: a name (`Knowledge`), the plaza as its parent, houses on both sides of its lane. It stands from day one, empty, and every
house that no open road takes lives on it. This module is its geometry, pure functions of numbers: the cells of a lap, what a lap holds, the radius a plan asks
for, where a slot stands and the two records of a lap. `bibliopolis.world` puts the houses on it and `bibliopolis.plan` writes its radius into the plan.

  lane      the circle of radius R round the plaza. A house stands on either side: the inner lot at R - 1 (facing outward), the outer lot at R + 1 (facing inward),
            as on a band. A cell is one long along the lane and holds two lots: slot s is in cell s // 2, the inner lot when s is even.
  gates     every direction an avenue can take leaves the ring through a gap, so a later avenue never moves a house of the ring. G1 is the axes of the plan's
            ring-1 trunks, each `r3(axis % 360)`, sorted, without repeats; G2 adds the axes of the trunks of role `side` (a lap beyond the first can lie across
            the spoke of a side line). A gate is cut in both rows: outward it is where the avenue leaves, inward it is how the town hall reaches the ring.
  cells     from north clockwise, each cell starting where the one before ended, skipping the open interval (centre - TRUNK_LANE, centre + TRUNK_LANE) round every
            gate (`ring_cells`): a cell never stands within TRUNK_LANE of a gate axis, as the first lot of a band never stands within it of its trunk.
  fill      the n slots of a lap, listed by angle from north clockwise (slot s in cell s // 2: even s its inner lot, odd s its outer lot), are taken in the order of the scaled radical inverse
            (`ring_fill_order`): for j = 0 .. 2^m - 1, 2^m the least power of two that is at least n, the slot floor(rev_m(j) * n / 2^m), rev_m reading the m bits of j
            backwards, the first time a slot comes up. The first house stands at north, the second half way round, the next two at the quarters, then the eighths, and so on,
            so that the houses of the ring spread round the whole circle whatever their number and whatever n is. A house takes the first free slot of that fixed order, a
            slot that is freed is taken again in the same order, and every lap alike.
  radius    R(N) = RING_MIN + k for the least whole k >= 0 such that BOTH hold (`ring_radius_for`): lap 1 holds `districts.max` houses between the gates, and the
            narrowest LAND of the plan's N ring-1 sectors has at the ring's outer edge an arc, (R + BAND / 2) * radians(w_min), of at least RING_AVENUE_ARC (an
            avenue's spoke lane and one lot on each side). An avenue builds in its land: for a grown city the whole wedge of its trunk (the spoke is its middle),
            for a world built by hand the part of its sector within the narrower side of its spoke (`land_of`). RING_MIN = PLAZA_RADIUS + LEAD + BAND / 2: the lane
            lies where the first band of a ring-1 trunk lay in a city with no ring, one bare cell between the plaza rim and the inner row. A plan may pin a larger
            radius; a smaller one is refused.
  laps      a ring that is full goes on as a concentric lap outside the first, the same road: street `place:root:lap:<k>` (lane_of the root, `continued`), road
            `road:place:root:lap:<k>`. `bibliopolis.world` decides where a lap lies.

Other implementations of the engine copy these functions number for number: the order of the operations matters to the last bit.
"""

from __future__ import annotations

import functools
import math

from . import layout as lay

ROOT_PLACE = "place:root"  # the ring road is the root street: lap 1 is `place:root` itself
RING_LABEL = "Knowledge"  # the default name of the ring road
RING_MIN = lay.PLAZA_RADIUS + lay.LEAD + lay.BAND / 2  # the least lane radius: 8.5
RING_AVENUE_ARC = 2 * (lay.TRUNK_LANE + 1.0)  # the arc one avenue needs at the ring's outer edge: its spoke lane (TRUNK_LANE each side of the axis) and a lot (1) on each side: 3
RING_CLASS_RING = 1  # the ring road and its laps are ring 1 (display class 大道)
EPS = 1e-9
RING_SAGITTA = lay.ARC_SAGITTA  # the most a chord of a ring road's polyline lies inside its circle (cells, 0.05, as on every arc): the road drawn stays on its lane at any radius
RING_CHORD_STEP = 72  # a ring road's polyline has a whole multiple of 72 chords: 73 points (5 degrees a chord) wherever that is fine enough


def lap_place(k: int) -> str:
    """The street of lap `k` of the ring road: the root itself for lap 1, `place:root:lap:<k>` beyond."""
    return ROOT_PLACE if k == 1 else f"{ROOT_PLACE}:lap:{k}"


def lap_road(k: int) -> str:
    """The road of lap `k`: `road:<its street>`."""
    return f"road:{lap_place(k)}"


# ----------------------------------------------------------------------------------------------- directions ----
def wedge_units(trunk: dict) -> tuple[int, int]:
    """The wedge (lo, hi) of a trunk record of the plan in whole units of 1/100 degree."""
    lo, hi = trunk["wedge"]
    return round(lo * lay.UNIT), round(hi * lay.UNIT)


def axis_of(lo: int, hi: int) -> float:
    """The bearing of the middle of the wedge (lo, hi), in whole units of 1/100 degree: `r3(axis % 360)`."""
    return lay.r3(((lo + hi) / (2 * lay.UNIT)) % 360)


def gates_of(trunks: dict[str, dict], sides: bool = False) -> tuple[float, ...]:
    """G1 (`sides` False): the axes of the trunks of role `ring1`, each `r3(axis % 360)`, sorted, without repeats - every direction a ring-1 road can ever take,
    open or not. G2 (`sides` True): G1 plus the axes of the trunks of role `side`, in the same form. The axis of a trunk is the middle of its wedge."""
    roles = ("ring1", "side") if sides else ("ring1",)
    return tuple(sorted({axis_of(*wedge_units(rec)) for rec in trunks.values() if rec["role"] in roles}))


def sectors_of(trunks: dict[str, dict]) -> tuple[tuple[int, int], ...]:
    """The sectors the avenues leave the ring through: the wedges (lo, hi), in whole units of 1/100 degree, of the trunks of role `ring1`, sorted. N is their count."""
    return tuple(sorted(wedge_units(rec) for rec in trunks.values() if rec["role"] == "ring1"))


def gate_of(axis: int) -> float:
    """The gate bearing of a spoke axis given in whole units of 1/100 degree: `r3(axis % 360)` (the same number `axis_of` gives for a wedge centred on the axis)."""
    return lay.r3((axis / lay.UNIT) % 360)


def axis_gates(axes: tuple[int, ...] | list[int]) -> tuple[float, ...]:
    """The gate bearings of the spoke axes `axes` (whole units of 1/100 degree): sorted, without repeats. A plan that names the axes of all its N sectors outright
    (`params.ring.axes`: a world built by hand, whose trunks come with its roads) has these gates from day one, so that no avenue that opens later moves a house of the ring."""
    return tuple(sorted({gate_of(a) for a in axes}))


def sector_min(sectors: tuple[tuple[int, int], ...] | list[tuple[int, int]]) -> float | None:
    """w_min: the width of the narrowest wedge in degrees; None when there is no wedge (N = 0). For the wedges of the ring-1 trunks of a grown city, whose spoke is the middle of
    the wedge and whose land is the whole wedge, this is the narrowest land."""
    return min(hi - lo for lo, hi in sectors) / lay.UNIT if sectors else None


def land_of(lo: int, hi: int, axis: int) -> tuple[int, int]:
    """The wedge, in units of 1/100 degree, that an avenue of the sector `(lo, hi)` with its spoke on `axis` may build in. The engine lays lots the same distance either side
    of a spoke, so the land is the part of the sector within the narrower side of the axis: `axis` plus and minus `min(axis - lo, hi - axis)`. The one place that decides how the
    sector of a direction becomes the wedge of its trunk, and the width of the narrowest land (twice the narrower side) is what the radius of the ring must give an arc to."""
    side = min(axis - lo, hi - axis)
    return axis - side, axis + side


def land_min(ring: dict) -> float | None:
    """w_min of a plan that names its sectors and spoke axes (`params.ring.sectors`, `axes`: wedges in degrees and bearings in degrees, one for each direction): the width in degrees of
    the narrowest land, `2 * min(axis - lo, hi - axis)` of the direction with the least of it; None when there is no direction."""
    sectors, axes = sectors_in_order(ring), axes_units(ring)
    return min(hi - lo for lo, hi in (land_of(lo, hi, axis) for (lo, hi), axis in zip(sectors, axes))) / lay.UNIT if sectors else None


# ----------------------------------------------------------------------------------------------- the lane ----
@functools.cache
def _cells(radius: float, gates: tuple[float, ...]) -> tuple[float, ...]:
    length = 2 * math.pi * radius
    blocked = []
    for b in gates:
        for k in (-1, 0, 1):
            centre = radius * math.radians(b) + k * length
            blocked.append((centre - lay.TRUNK_LANE, centre + lay.TRUNK_LANE))
    blocked.sort()
    u, out = 0.0, []
    while u + 1 <= length + EPS:
        hit = next((hi for lo, hi in blocked if lo < u + 1 - EPS and hi > u + EPS), None)
        if hit is not None:
            u = hit
        else:
            out.append(u + 0.5)
            u = u + 1
    return tuple(out)


def ring_cells(radius: float, gates: tuple[float, ...] | list[float]) -> tuple[float, ...]:
    """The centres of the cells of a lap of lane radius `radius` with gate bearings `gates`, as the arc length `u` along the lane from north, clockwise.

    u starts at 0. While one more cell fits (u + 1 <= L + EPS, L = 2 * pi * radius): if the cell [u, u + 1] meets a blocked interval - the open interval
    (R * radians(b) + k * L - TRUNK_LANE, R * radians(b) + k * L + TRUNK_LANE) for each gate b and k in (-1, 0, 1), sorted by lower end, the first one that
    meets it - u jumps to the upper end of that interval and the walk looks at all of them again from the first; else the cell's centre u + 0.5 is a cell and u
    moves on by 1. Pure, cached."""
    return _cells(radius, tuple(gates))


def ring_capacity(radius: float, gates: tuple[float, ...] | list[float]) -> int:
    """Houses a lap holds: two lots to a cell."""
    return 2 * len(ring_cells(radius, gates))


def ring_sector_arc(radius: float, w_min: float) -> float:
    """The arc, in cells, of a sector `w_min` degrees wide at the outer edge of a ring road of lane radius `radius`: (radius + BAND / 2) * radians(w_min)."""
    return (radius + lay.BAND / 2) * math.radians(w_min)


def ring_radius_for(gates: tuple[float, ...] | list[float], max_houses: int, w_min: float | None = None) -> float:
    """R(N): RING_MIN + k for the least whole k >= 0 such that lap 1 (gates G1) holds at least `max_houses` AND the narrowest land of the N ring-1 sectors, `w_min`
    degrees wide, has at the ring's outer edge the arc one avenue needs: (R + BAND / 2) * radians(w_min) >= RING_AVENUE_ARC - EPS. `w_min` None: there is no
    sector (N = 0), only the first condition applies. Pure.

    The walk from RING_MIN upward starts where it can: a lap holds at most two lots to each of floor(2 * pi * R) cells, and the sector's arc grows with R, so no radius
    below the least that satisfies either bound satisfies both. The answer is the one the walk from RING_MIN gives; a `max` of thousands is not a loop of thousands."""
    if w_min is not None and not (isinstance(w_min, (int, float)) and not isinstance(w_min, bool) and w_min > 0 and math.isfinite(w_min)):
        raise ValueError(f"the narrowest land must be a number of degrees above 0, got {w_min!r}")
    cells = math.ceil(max_houses / 2)  # two lots to a cell: at least this many cells are needed, so 2 * pi * R + EPS >= cells
    k = max(0, math.ceil((cells - EPS) / (2 * math.pi) - RING_MIN) - 1)
    if w_min is not None:
        k = max(k, math.ceil((RING_AVENUE_ARC - EPS) / math.radians(w_min) - lay.BAND / 2 - RING_MIN) - 1)
    while not ((w_min is None or ring_sector_arc(RING_MIN + k, w_min) >= RING_AVENUE_ARC - EPS) and ring_capacity(RING_MIN + k, gates) >= max_houses):
        k += 1
    return RING_MIN + k


@functools.cache
def ring_fill_order(slots: int) -> tuple[int, ...]:
    """The order in which the slots of a lap of n = `slots` slots take houses: the scaled radical inverse. For j = 0 .. 2^m - 1, 2^m the least power of two that is at least n, the
    slot is floor(rev_m(j) * n / 2^m), `rev_m` reading the m bits of j backwards, and a slot counts the first time it comes up (the map is onto 0 .. n - 1, so the order holds every
    slot once). The slots are listed by angle from north clockwise (slot s in cell s // 2: even s its inner lot, odd s its outer lot; a numbering only, the order takes both rows from the start), so the first house stands at north, the second at slot n // 2,
    half way round whatever n is, then the quarters, the eighths, and so on: every prefix of the order is spread round the whole ring. A house takes the first free slot in this
    order. Pure, cached."""
    m = 0
    while (1 << m) < slots:
        m += 1
    seen, out = set(), []
    for j in range(1 << m):
        rev = 0
        for b in range(m):
            if (j >> b) & 1:
                rev |= 1 << (m - 1 - b)
        slot = (rev * slots) >> m
        if slot not in seen:
            seen.add(slot)
            out.append(slot)
    return tuple(out)


def ring_slot(radius: float, gates: tuple[float, ...] | list[float], slot: int) -> tuple[tuple[float, float], float]:
    """((x, z), facing) of slot `slot` of a lap: cell slot // 2, the inner lot (even slot, radius R - 1, facing outward) or the outer lot (odd slot, radius R + 1,
    facing inward), as `World.cell` lays a band."""
    cells = ring_cells(radius, gates)
    theta = math.degrees(cells[slot // 2] / radius)
    if slot % 2 == 0:
        return lay.polar_xz(radius - 1.0, theta), theta
    return lay.polar_xz(radius + 1.0, theta), theta + 180.0


# ----------------------------------------------------------------------------------------------- the records ----
def ring_street_record(k: int, label: str, radius: float, gates: tuple[float, ...] | list[float]) -> dict:
    """The street record of lap `k` (1: `place:root`, whose parent is the plaza; beyond: a lap, a street of shape ring that continues the root)."""
    rec = {"kind": "street", "shape": "ring"}
    if k > 1:
        rec.update({"lane_of": ROOT_PLACE, "ordinal": k, "continued": True})
    rec.update({"level": RING_CLASS_RING, "class": lay.class_of(RING_CLASS_RING), "label": label, "address": [label],
                "parent": lay.PLAZA_PLACE if k == 1 else ROOT_PLACE, "lots": 0, "reserved": 0, "road": lap_road(k),
                "ring": {"lap": k, "radius": radius, "slots": ring_capacity(radius, gates), "gaps": list(gates)}})
    return rec


def ring_chords(radius: float) -> int:
    """The number of chords of the polyline of a ring road of lane radius `radius`: the least whole multiple of RING_CHORD_STEP (72: 5 degrees a chord) that is at least
    ceil(pi / acos(1 - RING_SAGITTA / radius)), so that a chord lies at most RING_SAGITTA inside the circle (its sagitta, radius * (1 - cos(pi / n))). 72 chords (73 points) up to
    radius 52.5; beyond, 144, 216, ... (288 at radius 800)."""
    need = math.ceil(math.pi / math.acos(1.0 - RING_SAGITTA / radius))
    return RING_CHORD_STEP * max(1, math.ceil(need / RING_CHORD_STEP))


def ring_points(radius: float) -> list[list[float]]:
    """The closed polyline of a ring road: `ring_chords(radius)` chords from north clockwise, the last point the first. With 72 chords these are the very points of
    `lay.arc_points(radius, 0.0, 360.0)` (the same arithmetic: a + (b - a) * k / n)."""
    n = ring_chords(radius)
    return [lay.pt(lay.polar_xz(radius, 0.0 + (360.0 - 0.0) * k / n)) for k in range(n + 1)]


def ring_road_record(k: int, radius: float) -> dict:
    """The road of lap `k`: a closed circle of radius `radius` from north clockwise (`ring_points`: 73 points up to radius 52.5, more beyond, the last is the first), with no
    parent."""
    return lay.road_record(lap_place(k), "ring", RING_CLASS_RING, None, 0.0, ring_points(radius), 2 * math.pi * radius, radius=radius)


def sectors_units(ring: dict) -> tuple[tuple[int, int], ...]:
    """The sectors that a plan names outright in `params.ring.sectors` (wedges [lo, hi] in degrees, as the plan writes a wedge), in whole units of 1/100 degree, sorted."""
    return tuple(sorted(sectors_in_order(ring)))


def sectors_in_order(ring: dict) -> tuple[tuple[int, int], ...]:
    """The same sectors in the order of the direction numbers (the order of `params.ring.axes`), in whole units of 1/100 degree."""
    return tuple((round(lo * lay.UNIT), round(hi * lay.UNIT)) for lo, hi in ring["sectors"])


def axes_units(ring: dict) -> tuple[int, ...]:
    """The spoke axes that a plan names outright in `params.ring.axes` (degrees), in whole units of 1/100 degree, in the order of the sectors (the number of the direction)."""
    return tuple(round(a * lay.UNIT) for a in ring["axes"])


def check_ring(ring: object, districts: dict, gates: tuple[float, ...], w_min: float | None = None) -> None:
    """ValueError unless `params.ring` is a ring the engine can build: a non-empty label, a lane radius of RING_MIN or more, a lap 1 (gates G1) that holds
    `districts.max` houses, and (`w_min`, the narrowest land of the ring-1 sectors in degrees; None: no sector) an arc of that land at the ring's outer edge of at least
    RING_AVENUE_ARC (with the EPS of `ring_radius_for`). A radius larger than the formula gives is allowed: the plan is the authority."""
    if not isinstance(ring, dict):
        raise ValueError("params.ring must be an object {label, radius}")
    label, radius = ring.get("label"), ring.get("radius")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"params.ring.label must be a non-empty string, got {label!r}")
    sectors, axes = ring.get("sectors"), ring.get("axes")
    if ("sectors" in ring) != ("axes" in ring):
        raise ValueError("params.ring has sectors and axes together or neither: the sectors say where the avenues may stand, the axes which way their spokes run")
    if "sectors" in ring:
        if not (isinstance(sectors, list) and sectors and all(isinstance(w, list) and len(w) == 2 and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in w) and w[0] < w[1] for w in sectors)):
            raise ValueError(f"params.ring.sectors must be a list of wedges [lo, hi] with lo below hi, got {sectors!r}")
        if not (isinstance(axes, list) and len(axes) == len(sectors) and all(
                isinstance(a, (int, float)) and not isinstance(a, bool) and math.isfinite(a) and w[0] <= a <= w[1] for a, w in zip(axes, sectors))):
            raise ValueError(f"params.ring.axes must be one bearing in degrees for each sector, inside it, got {axes!r}")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius < RING_MIN:
        raise ValueError(f"params.ring.radius must be a number of at least RING_MIN = {RING_MIN}, got {radius!r}")
    if ring_capacity(radius, gates) < districts["max"]:
        raise ValueError(f"params.ring.radius {radius} gives a lap that holds {ring_capacity(radius, gates)} houses, fewer than districts.max = {districts['max']}")
    if w_min is not None and ring_sector_arc(radius, w_min) < RING_AVENUE_ARC - EPS:
        raise ValueError(f"params.ring.radius {radius} gives the narrowest land ({w_min} degrees) an arc of {ring_sector_arc(radius, w_min):.3f} at the ring's outer "
                         f"edge, less than the {RING_AVENUE_ARC} one avenue needs")
