"""Geometry and bookkeeping checks of a city, shared by the tests.

Two kinds, each a function that returns the list of violations (empty when the city is sound); the tests assert on it:

  on a document or a world   no overlap between lots, every lot against the lane of its own street, a road tree that starts at the plaza rim,
                              no crossing of roads, no road through a lot, every lot inside the wedge of its trunk
  on a world only            (it needs the `lines` a world keeps) positions are the centres of their slots, the carve-out beyond a branch
                              circle, the registry of bands and members, and the bookkeeping of lots, ribs and streets

Pure Python, no fixtures. The houses of the root zone stand under the plaza and have no rib: every check leaves them out.
"""

import math
from collections import defaultdict

PLAZA_RADIUS = 6.0
EPS = 1e-6
DOCUMENT_CHECKS = ("overlaps", "not_adjacent", "road_tree_problems", "crossings", "roads_through_lots")
WORLD_CHECKS = ("position_problems", "wedge_problems", "branch_circle_problems", "registry_problems", "bookkeeping_problems")


def bearing_of(x, z):
    return math.degrees(math.atan2(x, -z))


def lot_cells(layout):
    """[(id, kind, rho, bearing, rho_lane, band_cell)]: every lot and reserved lot as a polar cell (the lane radius is its band's)."""
    places = layout["places"]
    out = []
    for pid, p in places.items():
        if p["kind"] not in ("lot", "reserved") or p.get("underground"):
            continue
        rib = places[p["parent"]]["rib"]
        pos = p["position"]
        out.append((pid, p["kind"], math.hypot(pos["x"], pos["z"]), bearing_of(pos["x"], pos["z"]), rib["s"], rib["band"] is not None))
    return out


def overlaps(layout):
    """Pairs of cells that overlap. A band cell is one cell along its lane and one across it, in polar coordinates; a cell of a
    street laid along its spoke is a unit square, compared by its centre."""
    cells = lot_cells(layout)
    grid = defaultdict(list)
    for c in cells:
        x, z = c[2] * math.sin(math.radians(c[3])), -c[2] * math.cos(math.radians(c[3]))
        grid[(int(x // 3), int(z // 3))].append((c, x, z))
    bad = []
    for (gx, gz), items in grid.items():
        near = [t for dx in (-1, 0, 1) for dz in (-1, 0, 1) for t in grid.get((gx + dx, gz + dz), [])]
        for a, ax, az in items:
            for b, bx, bz in near:
                if a[0] >= b[0]:
                    continue
                d = math.hypot(ax - bx, az - bz)
                if d > 1.6:
                    continue
                if a[5] and b[5]:
                    dphi = abs((a[3] - b[3] + 180) % 360 - 180)
                    # positions are rounded to a millimetre-ish: neighbours in a row touch exactly, so allow the rounding
                    if abs(a[2] - b[2]) < 1 - 0.01 and dphi < math.degrees(0.5 / a[4] + 0.5 / b[4]) - 0.02:
                        bad.append((a[0], b[0]))
                elif d < 0.99:
                    bad.append((a[0], b[0]))
    return bad


def not_adjacent(layout):
    """Lots that do not stand against the lane of their own street: one cell off the lane, inside its stretch."""
    places = layout["places"]
    bad = []
    for pid, p in places.items():
        if p["kind"] not in ("lot", "reserved") or p.get("underground"):
            continue
        owner = places[p["parent"]]
        rib = owner["rib"]
        pos = p["position"]
        rho = math.hypot(pos["x"], pos["z"])
        if rib["band"] is None:
            continue  # a street along its own spoke
        if abs(abs(rho - rib["s"]) - 1.0) > 0.01:
            bad.append((pid, "not one cell from the lane radius"))
            continue
        trunk = places[rib["trunk"]]
        lateral = math.radians((bearing_of(pos["x"], pos["z"]) - trunk["axis"] + 180) % 360 - 180) * rib["s"]
        if lateral * rib["side"] <= 0 or not (rib["x0"] - 5e-3 <= abs(lateral) - 0.5 <= rib["x1"] + 5e-3):  # positions are rounded to 1e-3
            bad.append((pid, f"lateral {lateral:.2f} outside the stretch {rib['x0']}..{rib['x1']}"))
    return bad


def point_along(points, dist):
    """The point at arc length `dist` along a polyline (clamped to its end)."""
    left = dist
    for (ax, az), (bx, bz) in zip(points, points[1:]):
        seg = math.hypot(bx - ax, bz - az)
        if left <= seg or seg == 0:
            t = left / seg if seg else 0.0
            return ax + (bx - ax) * t, az + (bz - az) * t
        left -= seg
    return points[-1]


def road_tree_problems(layout):
    """Every road reaches a ring-1 spoke through its parents, attaches inside its parent, and starts at the point it attaches to."""
    roads = layout["roads"]
    bad = []
    for rid, r in roads.items():
        seen, cur = set(), rid
        while roads[cur]["parent"] is not None:
            if cur in seen:
                bad.append((rid, "cycle"))
                break
            seen.add(cur)
            if roads[cur]["parent"] not in roads:
                bad.append((rid, "parent is not a road"))
                break
            cur = roads[cur]["parent"]
        else:
            root = roads[cur]
            if abs(math.hypot(*root["points"][0]) - PLAZA_RADIUS) > 0.01:
                bad.append((rid, f"root {cur} does not start at the plaza rim"))
        if r["parent"] is not None:
            par = roads[r["parent"]]
            if r["at"] > par["length"] + 1e-6 or r["at"] < -1e-6:
                bad.append((rid, f"attaches at {r['at']} of a parent {par['length']} long"))
            else:
                end = point_along(par["points"], r["at"])
                if math.hypot(end[0] - r["points"][0][0], end[1] - r["points"][0][1]) > 0.4:
                    bad.append((rid, f"starts {math.hypot(end[0] - r['points'][0][0], end[1] - r['points'][0][1]):.2f} away from its junction"))
    return bad


def segments(layout):
    for rid, r in layout["roads"].items():
        for a, b in zip(r["points"], r["points"][1:]):
            yield rid, a, b


def seg_hit(p, p2, q, q2):
    """The intersection point of two segments, or None; a shared end counts."""
    d1 = (p2[0] - p[0], p2[1] - p[1])
    d2 = (q2[0] - q[0], q2[1] - q[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None  # parallel: lanes on one radius never share a point except through their junction
    t = ((q[0] - p[0]) * d2[1] - (q[1] - p[1]) * d2[0]) / den
    u = ((q[0] - p[0]) * d1[1] - (q[1] - p[1]) * d1[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return p[0] + d1[0] * t, p[1] + d1[1] * t
    return None


def is_junction(roads, r1, r2, hit):
    """A touch is a junction when it is at an end of one road (its start on the other, or the shared start of siblings)."""
    for a, b in ((r1, r2), (r2, r1)):
        pts = roads[a]["points"]
        if math.hypot(hit[0] - pts[0][0], hit[1] - pts[0][1]) < 0.5 or math.hypot(hit[0] - pts[-1][0], hit[1] - pts[-1][1]) < 0.5:
            return True
    return False


def crossings(layout):
    """Pairs of roads that cross or touch other than at a junction of the road tree (the start of one on the other)."""
    roads = layout["roads"]
    grid = defaultdict(list)
    segs = list(segments(layout))
    for i, (rid, a, b) in enumerate(segs):
        for gx in range(int(min(a[0], b[0]) // 8), int(max(a[0], b[0]) // 8) + 1):
            for gz in range(int(min(a[1], b[1]) // 8), int(max(a[1], b[1]) // 8) + 1):
                grid[(gx, gz)].append(i)
    seen, bad = set(), []
    for idx in grid.values():
        for i in idx:
            for j in idx:
                if i >= j or (i, j) in seen:
                    continue
                seen.add((i, j))
                (r1, a1, b1), (r2, a2, b2) = segs[i], segs[j]
                if r1 == r2:
                    continue
                hit = seg_hit(a1, b1, a2, b2)
                if hit is None:
                    continue
                if is_junction(roads, r1, r2, hit):
                    continue
                bad.append((r1, r2, hit))
    return bad


def road_samples(layout, step=0.5):
    for rid, r in layout["roads"].items():
        for (ax, az), (bx, bz) in zip(r["points"], r["points"][1:]):
            n = max(1, math.ceil(math.hypot(bx - ax, bz - az) / step))
            for k in range(n + 1):
                yield rid, ax + (bx - ax) * k / n, az + (bz - az) * k / n


def roads_through_lots(layout):
    """Points of a road that lie inside the cell of a lot (the road of a street runs beside its lots, never through one)."""
    cells = lot_cells(layout)
    grid = defaultdict(list)
    for c in cells:
        x, z = c[2] * math.sin(math.radians(c[3])), -c[2] * math.cos(math.radians(c[3]))
        grid[(int(x // 3), int(z // 3))].append((c, x, z))
    bad = []
    for rid, x, z in road_samples(layout):
        gx, gz = int(x // 3), int(z // 3)
        rho, bear = math.hypot(x, z), bearing_of(x, z)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for c, cx, cz in grid.get((gx + dx, gz + dz), []):
                    if math.hypot(x - cx, z - cz) > 1.2:
                        continue
                    if c[5]:
                        dphi = abs((bear - c[3] + 180) % 360 - 180)
                        if abs(rho - c[2]) < 0.45 and dphi < math.degrees(0.5 / c[4]) - 0.02:
                            bad.append((rid, c[0]))
                    elif math.hypot(x - cx, z - cz) < 0.45:
                        bad.append((rid, c[0]))
    return bad


def document_wedge_problems(layout):
    """Wedges that leave the wedge of their parent trunk (a document of a city)."""
    places = layout["places"]
    bad = []
    for pid, p in places.items():
        if p["kind"] != "street" or "wedge" not in p or p["parent"] == "place:plaza":
            continue
        cur, at = places[p["parent"]], p["parent"]
        while "wedge" not in cur:
            at = cur["parent"]
            cur = places[at]
        lo, hi = p["wedge"]
        plo, phi = places[at]["wedge"]
        if lo < plo - 1e-6 or hi > phi + 1e-6:
            bad.append((pid, "wedge leaves its parent's"))
    return bad


# ----------------------------------------------------------------------------------------- a world only ----
def frame(axis, s, t):
    """(x, z) of the point `s` along the spoke of bearing `axis` and `t` to its right."""
    r = math.radians(axis)
    return s * math.sin(r) + t * math.cos(r), -s * math.cos(r) + t * math.sin(r)


def polar(rho, deg):
    r = math.radians(deg)
    return rho * math.sin(r), -rho * math.cos(r)


def cell_corners(places, p, axis):
    """The four corners (x, z) of the cell of a lot or reserved lot, from its rib: a polar cell on a band, a square along the spoke."""
    rib = places[p["parent"]]["rib"]
    slot, c = p["slot"], p["slot"] // 2
    if rib["mode"] == "spoke":
        t0, t1 = (-1.5, -0.5) if slot % 2 == 0 else (0.5, 1.5)
        return [frame(axis, rib["x0"] + c + u, t) for u in (0, 1) for t in (t0, t1)]
    s, side = rib["s"], rib["side"]
    rho = s - 1.0 if slot % 2 == 0 else s + 1.0
    a0, a1 = axis + side * math.degrees((rib["x0"] + c) / s), axis + side * math.degrees((rib["x0"] + c + 1) / s)
    return [polar(r, a) for r in (rho - 0.5, rho + 0.5) for a in (a0, a1)]


def bearing_in(wedge, deg):
    lo, hi = wedge
    d = (deg - lo) % 360.0
    return d <= (hi - lo) + 1e-4 or (360.0 - d) <= 1e-4


def cells_of(doc):
    """(place id, record, axis, rib) of every lot and reserved lot of a world."""
    places, lines = doc["places"], doc["lines"]
    for pid, p in places.items():
        if p["kind"] in ("lot", "reserved") and not p.get("underground"):
            rib = places[p["parent"]]["rib"]
            yield pid, p, lines[rib["line"]]["axis"], rib


def center_of(rib, axis, slot):
    """(x, z) of the centre of a slot of a rib, from the rib alone (an independent statement of the geometry the engine writes)."""
    c = slot // 2
    if rib["mode"] == "spoke":
        return frame(axis, rib["x0"] + c + 0.5, -1.0 if slot % 2 == 0 else 1.0)
    return polar(rib["s"] - 1.0 if slot % 2 == 0 else rib["s"] + 1.0, axis + rib["side"] * math.degrees((rib["x0"] + c + 0.5) / rib["s"]))


def position_problems(doc):
    """The position of every lot and reserved lot is the centre of its slot in its rib."""
    bad = []
    for pid, p, axis, rib in cells_of(doc):
        x, z = center_of(rib, axis, p["slot"])
        if abs(x - p["position"]["x"]) > 2e-3 or abs(z - p["position"]["z"]) > 2e-3:
            bad.append((pid, "position is not the centre of its slot"))
    return bad


def wedge_problems(doc):
    """Every corner of every cell lies in the wedge of its rib's carrier trunk, and in the central wedge from the branch circle outward."""
    places, lines = doc["places"], doc["lines"]
    bad = []
    for pid, p, axis, rib in cells_of(doc):
        corners = cell_corners(places, p, axis)
        for x, z in corners:
            if not bearing_in(rib["wedge"], bearing_of(x, z)):
                bad.append((pid, "corner outside the wedge of its trunk"))
                break
        line = lines[rib["line"]]
        rmin = min(math.hypot(x, z) for x, z in corners)
        for m in line["members"]:
            if m["r1"] is not None and rmin >= m["r1"] + 1.0 - EPS:
                if not all(bearing_in(m["inner"], bearing_of(x, z)) for x, z in corners):
                    bad.append((pid, f"beyond the branch circle of {m['place']} but outside its central wedge"))
                    break
    return bad


def branch_circle_problems(doc):
    """No lot or reserved lot of the line stands within one cell of the branch circle of a member (the arcs run clear of lots)."""
    places, lines = doc["places"], doc["lines"]
    bad = []
    for pid, p, axis, rib in cells_of(doc):
        rho = [math.hypot(x, z) for x, z in cell_corners(places, p, axis)]
        for m in lines[rib["line"]]["members"]:
            if m["r1"] is not None and min(rho) < m["r1"] + 1.0 - EPS and max(rho) > m["r1"] - 1.0 + EPS:
                bad.append((pid, f"within a cell of the branch circle of {m['place']}"))
    return bad


def registry_problems(doc):
    """The registry of every line (bands, spans, members) agrees with the ribs and roads in the world."""
    places, roads, lines = doc["places"], doc["roads"], doc["lines"]
    bad = []
    for pid, p in places.items():
        if p["kind"] != "street" or "rib" not in p:
            continue
        rib, line = p["rib"], lines.get(p["rib"]["line"])
        if line is None:
            bad.append((pid, "rib on a line the registry lacks"))
            continue
        if rib["mode"] == "spoke":
            if not any(abs(lo - rib["s"]) < 2e-3 and hi >= rib["x1"] - 2e-3 for lo, hi in line["spokes"]):
                bad.append((pid, "spoke rib without its span"))
        elif rib["band"] >= len(line["bands"]):
            bad.append((pid, "band the registry lacks"))
        else:
            band = line["bands"][rib["band"]]
            if abs(band["s"] - rib["s"]) > 2e-3 or band["used"][0 if rib["side"] < 0 else 1] < rib["x1"] - 2e-3:
                bad.append((pid, "band rib the registry does not know"))
    for lid, line in lines.items():
        for m in line["members"]:
            if m["road"] not in roads:
                bad.append((lid, f"member {m['place']} has no road"))
        for a, b in zip(line["members"], line["members"][1:]):  # the spokes of the members of a line are one straight road, end to start
            if a["road"] in roads and b["road"] in roads and abs(roads[a["road"]]["s_end"] - roads[b["road"]]["s0"]) > 2e-3:
                bad.append((lid, f"the road of {a['place']} does not end where the road of {b['place']} starts"))
        spans = sorted([(b["s"] - 1.5, b["s"] + 1.5) for b in line["bands"]] + [tuple(sp) for sp in line["spokes"]]
                       + [(m["r1"] - 1.0, m["r1"] + 1.0) for m in line["members"] if m["r1"] is not None])
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            if b0 < a1 - 2e-3:
                bad.append((lid, f"spans overlap: {(a0, a1)} {(b0, b1)}"))
    return bad


def bookkeeping_problems(doc):
    """Slots of every rib are lots plus reserved lots, counters agree, every lot has its rib, street and ancestors in the world."""
    places = doc["places"]
    bad = []
    slots: dict[str, dict[int, str]] = {}
    for pid, p in places.items():
        if p["kind"] in ("lot", "reserved"):
            if p["parent"] not in places:
                bad.append((pid, "parent rib missing"))
                continue
            if p["slot"] in slots.setdefault(p["parent"], {}):
                bad.append((pid, f"slot {p['slot']} taken twice"))
            slots[p["parent"]][p["slot"]] = p["kind"]
            if p["kind"] == "lot" and p["street"] not in places:
                bad.append((pid, "street missing"))
    for pid, p in places.items():
        if p["kind"] != "street":
            continue
        if p["parent"] != "place:plaza" and p["parent"] not in places:
            bad.append((pid, "parent street missing"))
        if "rib" in p:
            held = slots.get(pid, {})
            lots = sum(1 for k in held.values() if k == "lot")
            if sorted(held) != list(range(p["rib"]["slots"])):
                bad.append((pid, "slots are not 0..n-1"))
            if lots != p["lots"] or len(held) - lots != p["reserved"]:
                bad.append((pid, f"counters {p['lots']}/{p['reserved']} but {lots} lots and {len(held) - lots} empty"))
            if p["rib"]["next"] < max((s for s, k in held.items() if k == "lot"), default=-1) + 1:
                bad.append((pid, "next pointer behind a lot"))
    for pid, p in places.items():
        if p["kind"] == "lot" and p["parent"] in places and p["street"] in places:
            owner = places[p["parent"]]
            if owner.get("lane_of", p["parent"]) != p["street"]:
                bad.append((pid, "lot in a rib that is not of its street"))
    return bad


def all_problems(doc):
    """Every check on a world; name -> violations (only the non-empty ones)."""
    out = {}
    for name in DOCUMENT_CHECKS + WORLD_CHECKS:
        found = globals()[name](doc)
        if found:
            out[name] = found
    return out


def document_problems(layout):
    """The checks that need only the document of a city (`world_layout`): the same geometry, and the wedges of the streets."""
    out = {}
    for name in DOCUMENT_CHECKS + ("document_wedge_problems",):
        found = globals()[name](layout)
        if found:
            out[name] = found
    return out
