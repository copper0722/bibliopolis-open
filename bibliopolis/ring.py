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
  radius    R(N) = RING_MIN + k for the least whole k >= 0 such that BOTH hold (`ring_radius_for`): lap 1 holds `districts.max` houses between the gates, and the
            narrowest of the plan's N ring-1 sectors has at the ring's outer edge an arc, (R + BAND / 2) * radians(w_min), of at least RING_AVENUE_ARC (an
            avenue's spoke lane and one lot on each side). RING_MIN = PLAZA_RADIUS + LEAD + BAND / 2: the lane lies where the first band of a ring-1 trunk
            lay in a city with no ring, one bare cell between the plaza rim and the inner row. A plan may pin a larger radius; a smaller one is refused.
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


def gates_of(trunks: dict[str, dict], sides: bool = False) -> tuple[float, ...]:
    """G1 (`sides` False): the axes of the trunks of role `ring1`, each `r3(axis % 360)`, sorted, without repeats - every direction a ring-1 road can ever take,
    open or not. G2 (`sides` True): G1 plus the axes of the trunks of role `side`, in the same form. The axis of a trunk is the middle of its wedge."""
    roles = ("ring1", "side") if sides else ("ring1",)
    found = set()
    for rec in trunks.values():
        if rec["role"] in roles:
            lo, hi = wedge_units(rec)
            found.add(lay.r3(((lo + hi) / (2 * lay.UNIT)) % 360))
    return tuple(sorted(found))


def sectors_of(trunks: dict[str, dict]) -> tuple[tuple[int, int], ...]:
    """The sectors the avenues leave the ring through: the wedges (lo, hi), in whole units of 1/100 degree, of the trunks of role `ring1`, sorted. N is their count."""
    return tuple(sorted(wedge_units(rec) for rec in trunks.values() if rec["role"] == "ring1"))


def sector_min(sectors: tuple[tuple[int, int], ...] | list[tuple[int, int]]) -> float | None:
    """w_min: the width of the narrowest sector in degrees; None when there is no sector (N = 0)."""
    return min(hi - lo for lo, hi in sectors) / lay.UNIT if sectors else None


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
    """R(N): RING_MIN + k for the least whole k >= 0 such that lap 1 (gates G1) holds at least `max_houses` AND the narrowest of the N ring-1 sectors, `w_min`
    degrees wide, has at the ring's outer edge the arc one avenue needs: (R + BAND / 2) * radians(w_min) >= RING_AVENUE_ARC - EPS. `w_min` None: there is no
    sector (N = 0), only the first condition applies. Pure."""
    if w_min is not None and not (isinstance(w_min, (int, float)) and not isinstance(w_min, bool) and w_min > 0 and math.isfinite(w_min)):
        raise ValueError(f"the narrowest sector must be a number of degrees above 0, got {w_min!r}")
    k = 0
    while not ((w_min is None or ring_sector_arc(RING_MIN + k, w_min) >= RING_AVENUE_ARC - EPS) and ring_capacity(RING_MIN + k, gates) >= max_houses):
        k += 1
    return RING_MIN + k


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


def ring_road_record(k: int, radius: float) -> dict:
    """The road of lap `k`: a closed circle of radius `radius` from north clockwise (73 points, the last is the first), with no parent."""
    return lay.road_record(lap_place(k), "ring", RING_CLASS_RING, None, 0.0, lay.arc_points(radius, 0.0, 360.0), 2 * math.pi * radius, radius=radius)


def check_ring(ring: object, districts: dict, gates: tuple[float, ...], w_min: float | None = None) -> None:
    """ValueError unless `params.ring` is a ring the engine can build: a non-empty label, a lane radius of RING_MIN or more, a lap 1 (gates G1) that holds
    `districts.max` houses, and (`w_min`, the narrowest ring-1 sector in degrees; None: no sector) an arc of that sector at the ring's outer edge of at least
    RING_AVENUE_ARC (with the EPS of `ring_radius_for`). A radius larger than the formula gives is allowed: the plan is the authority."""
    if not isinstance(ring, dict):
        raise ValueError("params.ring must be an object {label, radius}")
    label, radius = ring.get("label"), ring.get("radius")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"params.ring.label must be a non-empty string, got {label!r}")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius < RING_MIN:
        raise ValueError(f"params.ring.radius must be a number of at least RING_MIN = {RING_MIN}, got {radius!r}")
    if ring_capacity(radius, gates) < districts["max"]:
        raise ValueError(f"params.ring.radius {radius} gives a lap that holds {ring_capacity(radius, gates)} houses, fewer than districts.max = {districts['max']}")
    if w_min is not None and ring_sector_arc(radius, w_min) < RING_AVENUE_ARC - EPS:
        raise ValueError(f"params.ring.radius {radius} gives the narrowest sector ({w_min} degrees) an arc of {ring_sector_arc(radius, w_min):.3f} at the ring's outer "
                         f"edge, less than the {RING_AVENUE_ARC} one avenue needs")
