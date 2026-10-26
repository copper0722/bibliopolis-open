"""The coast: the outline of the land. The land grows with the houses and has no bound.

The land is a buffer of COAST_BUFFER cells around every surface lot, empty lot and road, with the holes filled. It is rasterised on a
grid of one cell, traced and simplified in pure Python (no geometry library), so the same city gives the same polygons on any machine.
The coast is a picture of the city: nothing is placed by it, and it is derived again whenever the city changes.
"""

from __future__ import annotations

import math

COAST_BUFFER = 4.0  # the land reaches this far beyond the nearest lot or road
COAST_TOLERANCE = 1.0  # the simplified outline stays within this many cells of the traced one


def road_samples(roads: dict[str, dict], step: float = 1.0):
    """Points along every road, about one per `step` cells (the ends of a polyline included)."""
    for r in roads.values():
        pts = r["points"]
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            n = max(1, math.ceil(math.hypot(bx - ax, bz - az) / step))
            for k in range(n + 1):
                yield ax + (bx - ax) * k / n, az + (bz - az) * k / n


def coast_of(layout: dict, buffer: float = COAST_BUFFER, tolerance: float = COAST_TOLERANCE) -> dict:
    """The coast: the outline of the land, a buffer of `buffer` cells around every lot and road, holes filled, simplified.

    Rasterised on a grid of 1 cell, so the result is deterministic and needs no geometry library: `polygons` are lists of
    [x, z] corners of the outer boundary of each piece of land (counter-clockwise on screen, z south). The houses of the ring road count like any."""
    places, roads, plaza = layout["places"], layout["roads"], layout["centre"]["radius"]
    pts = [(p["position"]["x"], p["position"]["z"]) for p in places.values() if p["kind"] in ("lot", "reserved")]
    pts += list(road_samples(roads))
    pts.append((0.0, 0.0))
    reach = math.ceil(max(max(math.hypot(x, z) for x, z in pts), plaza) + buffer + 2)  # a city of day one has the plaza and nothing else
    size = 2 * reach + 1
    land = bytearray(size * size)
    r = int(math.ceil(buffer))
    disc = [(dx, dz) for dx in range(-r, r + 1) for dz in range(-r, r + 1) if dx * dx + dz * dz <= buffer * buffer]
    for x, z in pts:
        cx, cz = int(math.floor(x + 0.5)) + reach, int(math.floor(z + 0.5)) + reach
        for dx, dz in disc:
            land[(cz + dz) * size + cx + dx] = 1
    for x in range(int(plaza + buffer) + 1):  # the plaza itself
        for z in range(int(plaza + buffer) + 1):
            if x * x + z * z <= (plaza + buffer) ** 2:
                for sx, sz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    land[(sz * z + reach) * size + sx * x + reach] = 1
    # fill the holes: sea is what a flood from the border reaches
    sea = bytearray(size * size)
    stack = [(0, 0)]
    sea[0] = 1
    while stack:
        cx, cz = stack.pop()
        for nx, nz in ((cx + 1, cz), (cx - 1, cz), (cx, cz + 1), (cx, cz - 1)):
            if 0 <= nx < size and 0 <= nz < size and not land[nz * size + nx] and not sea[nz * size + nx]:
                sea[nz * size + nx] = 1
                stack.append((nx, nz))
    solid = bytearray(0 if sea[i] else 1 for i in range(size * size))
    polygons = [simplify_ring(ring, tolerance) for ring in trace_outlines(solid, size)]
    polygons = [[[round(x - reach, 1), round(z - reach, 1)] for x, z in ring] for ring in polygons]
    return {"buffer": buffer, "tolerance": tolerance, "polygons": polygons}


def trace_outlines(solid: bytearray, size: int) -> list[list[tuple[int, int]]]:
    """Outer boundaries of the 4-connected pieces of a bitmap, as closed lists of grid corners, in a fixed order."""
    # directed unit edges with the land on the left; the corners are the cell corners (x, z)
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for z in range(size):
        row = z * size
        for x in range(size):
            if not solid[row + x]:
                continue
            if z == 0 or not solid[row - size + x]:
                nxt.setdefault((x, z), []).append((x + 1, z))
            if x == size - 1 or not solid[row + x + 1]:
                nxt.setdefault((x + 1, z), []).append((x + 1, z + 1))
            if z == size - 1 or not solid[row + size + x]:
                nxt.setdefault((x + 1, z + 1), []).append((x, z + 1))
            if x == 0 or not solid[row + x - 1]:
                nxt.setdefault((x, z + 1), []).append((x, z))
    rings: list[list[tuple[int, int]]] = []
    for start in sorted(nxt):
        while nxt.get(start):
            ring = [start]
            cur = nxt[start].pop()
            while cur != start:
                ring.append(cur)
                outs = nxt[cur]
                cur = outs.pop(0) if len(outs) == 1 else _turn_left(ring[-2], cur, outs)
            rings.append(ring)
    return sorted(rings, key=lambda ring: (-len(ring), ring[0]))


def _turn_left(prev: tuple[int, int], cur: tuple[int, int], outs: list[tuple[int, int]]) -> tuple[int, int]:
    """At a pinch point (two edges leave a corner) take the sharpest left turn, which keeps pieces apart; remove it from `outs`."""
    dx, dz = cur[0] - prev[0], cur[1] - prev[1]
    best = max(outs, key=lambda o: dx * (o[1] - cur[1]) - dz * (o[0] - cur[0]))  # cross product: largest = leftmost
    outs.remove(best)
    return best


def simplify_ring(ring: list[tuple[int, int]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on a closed ring (split at its two farthest corners so the closing edge is simplified too)."""
    pts = [(float(x), float(z)) for x, z in ring]
    if len(pts) < 4:
        return pts
    a = 0
    b = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[a][0]) ** 2 + (pts[i][1] - pts[a][1]) ** 2)
    first = _dp(pts[a:b + 1], tol)
    second = _dp(pts[b:] + pts[:a + 1], tol)
    return first[:-1] + second[:-1]


def _dp(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    (ax, az), (bx, bz) = pts[0], pts[-1]
    length = math.hypot(bx - ax, bz - az) or 1e-9
    far, worst = -1, -1.0
    for i in range(1, len(pts) - 1):
        d = abs((bx - ax) * (az - pts[i][1]) - (ax - pts[i][0]) * (bz - az)) / length
        if d > worst:
            far, worst = i, d
    if worst <= tol:
        return [pts[0], pts[-1]]
    return _dp(pts[:far + 1], tol)[:-1] + _dp(pts[far:], tol)


def polygon_area(poly: list[list[float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2
