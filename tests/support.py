"""Worlds for the tests: small synthetic topic trees with items, a world with districts that checks itself after every step, the invariants
of the rule (`district_problems`) and the measure of waste (`land_waste`, land laid beyond need) with random simulations of a world.

Not collected by pytest (the name has no test_ prefix)."""

import itertools
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

import checks

from bibliopolis import coast
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import ring
from bibliopolis import world as zw
from bibliopolis.document import world_layout
from bibliopolis.tree import TreeView

ROOT = zw.ROOT_PLACE
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def sample():
    """(tree, library) of examples/: the synthetic sample of the README."""
    return (json.loads((EXAMPLES / "tree.json").read_text(encoding="utf-8")), json.loads((EXAMPLES / "library.json").read_text(encoding="utf-8")))


def stamp(i):
    """An `added_at` that grows with `i`: one second apart."""
    return (START + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")


def T(n=0, **kids):
    """A topic with `n` items whose only topic it is, and the given child topics."""
    return (n, kids)


def art(i, topics=(), **extra):
    """A library item (arrival order = `i`); `extra` replaces or adds fields."""
    item = {"id": f"a{i:05d}", "title": f"Title {i}", "authors": ["A. Author"], "year": 2020, "doi": f"10.0000/t.{i:05d}", "added_at": stamp(i),
            "type": "article", "tags": [], "topics": list(topics)}
    item.update(extra)
    return item


def make_tree(spec):
    """(tree document, items) from {"root": T(5, child=T(8))}: n items per topic, arriving in the order of the walk. Several roots are allowed.
    The label of a topic is its id with a capital."""
    nodes, items = [], []
    counter = itertools.count(1)

    def walk(name, node, parent):
        n, kids = node
        nodes.append({"id": name, "label": name.capitalize(), "parent": parent})
        for _ in range(n):
            items.append(art(next(counter), [name]))
        for child, grand in kids.items():
            walk(child, grand, name)

    for root, node in spec.items():
        walk(root, node, None)
    return {"nodes": nodes}, items


def random_world(seed):
    """A random topic tree (two or three roots, depth up to 6) with random counts, and some items with no topic."""
    rng = random.Random(seed)
    counter = itertools.count(1)

    def sub(depth):
        kids = {}
        if depth < 6:
            for _ in range(rng.choice([0, 0, 1, 2, 3, 4])):
                kids[f"n{next(counter)}"] = sub(depth + 1)
        return (rng.choice([0, 0, 1, 3, 8, 19, 22, 40]), kids)

    spec = {f"root{i}": sub(1) for i in range(rng.choice([2, 3]))}
    tree, items = make_tree(spec)
    every = [n["id"] for n in tree["nodes"]]
    for a in items:  # one item in ten is filed under a second topic, anywhere in the tree: its house still stands once, at the deepest of the two
        if rng.random() < 0.1:
            a["topics"].append(rng.choice(every))
    n = len(items)
    for _ in range(rng.randint(0, 40)):
        n += 1
        items.append(art(n, []))
    return tree, items


# ------------------------------------------------------------------------------------------------ helpers ----
def by_tag(items, *tags):
    return [a for a in items if a["topics"] and a["topics"][0] in tags]


def lot_of(doc, item):
    return doc["places"][lay.article_place(item["id"] if isinstance(item, dict) else item)]


def road_of(doc, item):
    return lot_of(doc, item)["street"]


def roads_of(doc):
    """{road place: street record} of the roads (the street records with a key); the ring road and the continuation ribs are not roads."""
    return {pid: p for pid, p in doc["places"].items() if p["kind"] == "street" and "lane_of" not in p and p.get("tag") is not None}


def direct_counts(doc):
    """{road or ring road place: houses standing on it directly} - on its ribs, never on a road below it."""
    counts = Counter()
    for p in doc["places"].values():
        if p["kind"] == "lot":
            counts[p["street"]] += 1
    return counts


def count(doc, road):
    return direct_counts(doc).get(road, 0)


def tag_street(tag):
    return lay.tag_place(tag)


def ribs_of(doc, road):
    """The slots of the ribs of a road, the first rib first."""
    rec = doc["places"][road]
    return [doc["places"][c]["rib"]["slots"] for c in ([road] if "rib" in rec else []) + list(rec.get("lanes", []))]


def on_ring(doc):
    """The houses on the ring road (any lap), by arrival."""
    return sorted((p for p in doc["places"].values() if p["kind"] == "lot" and p["street"] == ROOT), key=lambda p: p["seq"])


def laps_of(doc):
    """The streets of the laps of the ring road that stand, lap 1 first."""
    return [ROOT, *doc["places"][ROOT].get("lanes", [])]


def gates_of(plan, sides=False):
    """G1 (G2 with `sides`) stated from the plan file alone: the axis of a trunk is the middle of its wedge, in whole hundredths of a degree, mod 360, to 3
    decimals. A plan that names the spoke axes of its sectors (`params.ring.axes`: a world built by hand) has the gates of all of them, whichever roads are open."""
    out = set()
    for axis_deg in plan["params"]["ring"].get("axes", []):
        out.add(round((round(axis_deg * 100) / 100) % 360, 3) + 0.0)
    for rec in plan["trunks"].values():
        if ("axes" not in plan["params"]["ring"] and rec["role"] == "ring1") or (sides and rec["role"] == "side"):
            lo, hi = (round(v * 100) for v in rec["wedge"])
            out.add(round(((lo + hi) / 200) % 360, 3) + 0.0)
    return sorted(out)


GOLDEN = 13750776405003785  # the golden angle in units of 1/100 degree times 10**12 (docs/world.md, "The sectors")


def bearing_of_direction(k):
    return ((k * GOLDEN + 5 * 10**11) // 10**12) % 36000


def cells_table(n):
    """The sectors of n directions stated apart from the engine (docs/world.md): for k in range(n), (lo, hi, axis) in units of 1/100 degree. The spoke is ON the bearing; the sector is
    the cell that is nearest to it among the n bearings - to the midpoint with the nearest bearing on either side - cut to 20 degrees each side, a midpoint of an odd gap rounded up;
    the axis is kept between -180 and 180 degrees. Found by looking at every other bearing, not by sorting them as the engine does."""
    bearings = [bearing_of_direction(k) for k in range(n)]
    out = []
    for k, b in enumerate(bearings):
        others = [x for j, x in enumerate(bearings) if j != k]
        clockwise = min(((x - b) % 36000 for x in others), default=36000)
        anticlockwise = min(((b - x) % 36000 for x in others), default=36000)
        turn = 36000 if b > 18000 else 0
        out.append((b - min(2000, anticlockwise // 2) - turn, b + min(2000, (clockwise + 1) // 2) - turn, b - turn))
    return out


def capacity(radius, gates):
    """What a lap holds, from the independent cells of tests/checks.py."""
    return 2 * len(checks.free_cells(radius, gates))


def radical_inverse(j):
    """The radical inverse of j in base 2 as an exact fraction: the binary digits of j read backwards after the point (j = 6 = 110 gives 0.011 = 3/8)."""
    x, scale = Fraction(0), Fraction(1, 2)
    while j:
        if j & 1:
            x += scale
        j >>= 1
        scale /= 2
    return x


def fill_order_of(slots):
    """The order in which the slots of a lap fill, stated apart from the engine (docs/engine.md, "The ring road"): the slots listed by angle from north, clockwise (slot 2c the inner lot of cell c, 2c + 1 its outer lot) are numbered
    0 .. slots - 1, and the j-th point of the van der Corput sequence, `radical_inverse(j)` in [0, 1), falls in the slot floor(point * slots); the order is the order
    in which the slots are first hit, j = 0, 1, 2, ... (exact fractions; the engine reverses the bits of j below 2**m and scales by integers)."""
    seen, out, j = set(), [], 0
    while len(out) < slots:
        slot = math.floor(radical_inverse(j) * slots)
        if slot not in seen:
            seen.add(slot)
            out.append(slot)
        j += 1
    return out


def first_free(laps, taken):
    """(lap index from 0, slot) where the next house goes: the first free slot, in fill order, of the lowest lap that has one. `laps` is the number of slots of each lap that stands, `taken`
    the set of (lap index, slot) that hold a house. (len(laps), 0) when every slot of every lap is taken: a lap opens, and its first slot is 0."""
    for k, slots in enumerate(laps):
        for s in fill_order_of(slots):
            if (k, s) not in taken:
                return k, s
    return len(laps), 0


def radius_for(gates, max_houses, w_min=None):
    """R(N) stated apart from the engine, with the independent cells: the least 8.5 + k such that lap 1 holds `max_houses` between the gates AND the narrowest land
    holds an avenue at the ring's outer edge (`w_min` None: no sector, only the first)."""
    k = 0
    while not (capacity(8.5 + k, gates) >= max_houses and (w_min is None or (8.5 + k + 1.5) * math.radians(w_min) >= 3.0 - 1e-9)):
        k += 1
    return 8.5 + k


def walk_radius_for(gates, max_houses, w_min=None):
    """The radius as v0.2.0 found it, kept as the oracle of the bisection that `ring.ring_radius_for` is now: the walk upward, one whole step at a time, from the lower
    bound that the houses and the sector give (no radius below it holds either condition), each step a lap of the engine's cells."""
    k = max(0, math.ceil((math.ceil(max_houses / 2) - ring.EPS) / (2 * math.pi) - ring.RING_MIN) - 1)
    if w_min is not None:
        k = max(k, math.ceil((ring.RING_AVENUE_ARC - ring.EPS) / math.radians(w_min) - lay.BAND / 2 - ring.RING_MIN) - 1)
    while not ((w_min is None or ring.ring_sector_arc(ring.RING_MIN + k, w_min) >= ring.RING_AVENUE_ARC - ring.EPS)
               and ring.ring_capacity(ring.RING_MIN + k, gates) >= max_houses):
        k += 1
    return ring.RING_MIN + k


def sea_with_tuple_stack(land, size, order=None):
    """The flood of the sea of `bibliopolis.coast.sea_of` as it was until the stack held cell indices: the stack a list of (x, z) tuples. `order`, a list, collects the cells in the order they
    are taken from the stack."""
    sea = bytearray(size * size)
    stack = [(0, 0)]
    sea[0] = 1
    while stack:
        cx, cz = stack.pop()
        if order is not None:
            order.append((cx, cz))
        for nx, nz in ((cx + 1, cz), (cx - 1, cz), (cx, cz + 1), (cx, cz - 1)):
            if 0 <= nx < size and 0 <= nz < size and not land[nz * size + nx] and not sea[nz * size + nx]:
                sea[nz * size + nx] = 1
                stack.append((nx, nz))
    return sea


def coast_with_tuple_stack(layout, buffer=coast.COAST_BUFFER, tolerance=coast.COAST_TOLERANCE, budget=None):
    """`bibliopolis.coast.coast_of` as it was until its flood of the sea went by a stack of indices: the same steps and the same budget, the stack of the flood a list of (x, z) tuples
    (over a hundred bytes a cell, so that a sparse city inside the budget needed more memory than the grid). The control of the tests of the memory, and the reference for the equality
    of the output."""
    places, roads, plaza = layout["places"], layout["roads"], layout["centre"]["radius"]
    lots = [(p["position"]["x"], p["position"]["z"]) for p in places.values() if p["kind"] in ("lot", "reserved")]
    ends = [(x, z) for r in roads.values() if len(r["points"]) >= 2 for x, z in r["points"]]
    farthest = max([math.hypot(x, z) for x, z in lots + ends] + [0.0, plaza])
    reach = math.ceil(farthest + buffer + 2)
    size = 2 * reach + 1
    limit = coast.COAST_GRID_BUDGET if budget is None else budget
    if size * size > limit:
        raise coast.CityTooLarge(f"the city is too large to draw its coast: the grid would hold {size * size} cells ({size} by {size}) and the most is {limit}", "city_too_large",
                                 cells=size * size, budget=limit)
    pts = lots + list(coast.road_samples(roads))
    pts.append((0.0, 0.0))
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
    sea = sea_with_tuple_stack(land, size)
    solid = bytearray(0 if sea[i] else 1 for i in range(size * size))
    polygons = [coast.simplify_ring(ring, tolerance) for ring in coast.trace_outlines(solid, size)]
    polygons = [[[round(x - reach, 1), round(z - reach, 1)] for x, z in ring] for ring in polygons]
    return {"buffer": buffer, "tolerance": tolerance, "polygons": polygons}


def five_degree_arc(radius, a, b):
    """The polyline of an arc as the engine drew it before the chord rule: a chord every 5 degrees at most, at any radius. The control of the tests that show a far arc drawn that way
    leaving its lane."""
    n = max(1, math.ceil(abs(b - a) / 5.0))
    return [lay.pt(lay.polar_xz(radius, a + (b - a) * k / n)) for k in range(n + 1)]


def slot_cell(radius, gates, slot):
    """((x, z), facing) of a slot of a lap, from the independent cells: the inner lot (even slot) at radius - 1 facing outward, the outer lot (odd) at radius + 1
    facing inward."""
    theta = math.degrees(checks.free_cells(radius, gates)[slot // 2] / radius)
    if slot % 2 == 0:
        return checks.polar(radius - 1.0, theta), theta % 360
    return checks.polar(radius + 1.0, theta), (theta + 180.0) % 360


def as_text(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------- the world ----
def world_of(spec, *, max_houses=40, min_houses=10, trunk_min=20, mode="grow"):
    """(tree, items, plan, empty world) for a tree spec; `trunk_min` is small so that the small worlds of a test have trunks too."""
    tree, items = make_tree(spec)
    plan = plan_mod.build_plan(TreeView(tree), items, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    return tree, items, plan, zw.new_world(plan)


def send(plan, tree, doc, arrivals, event_id=None):
    """Send arrivals as one call: (the world after, the result). Checks the world on the way: the geometry and the rule."""
    res = zw.assign(plan, tree, doc, arrivals, event_id=event_id)
    after = zw.apply_delta(doc, res["delta"])
    sound(after, plan, tree)
    assert step_problems(doc, after, may_change_after(plan, doc, after)) == []
    return after, res


def lay_problems(doc, plan, tree, *, full=True, world=None):
    """Idempotence of the laying (invariant 8): a fresh `World` over the document lays every line from its log (`World.lay_all`) and writes nothing. Returns what it wrote
    that differs from the document, as (store, record, {field: (was, now)}), empty when the document is what its log lays. `world` is a working copy of a kind other than
    `zw.World` (a world built by hand: `HandWorld`), made over the same document."""
    w = world if world is not None else zw.World(zw.PlanView(plan), tree if isinstance(tree, TreeView) else TreeView(tree), doc)
    w.lay_all(full=full)
    bad = []
    for name, store in (("places", w.places), ("roads", w.roads), ("lines", w.lines)):
        for key, now in store.new.items():
            was = doc[name].get(key)
            if now is None or was is None:
                bad.append((name, key, "deleted" if now is None else "made"))
            elif now != was:
                bad.append((name, key, {k: (was.get(k), v) if not isinstance(v, (list, dict)) else "differs" for k, v in now.items() if was.get(k) != v}))
    return bad


def sound(doc, plan, tree):
    assert checks.all_problems(doc) == {}
    assert district_problems(doc, plan, tree) == []
    assert lay_problems(doc, plan, tree) == []


class Town:
    """A world with districts and its tree: `send` checks the world after every step (the geometry and the rule)."""

    def __init__(self, spec, **kw):
        self.tree, self.items, self.plan, self.doc = world_of(spec, **kw)
        self.tv = TreeView(self.tree)

    def check(self):
        sound(self.doc, self.plan, self.tv)

    def send(self, arrivals, event_id=None, check=True):
        before = self.doc
        res = zw.assign(self.plan, self.tv, self.doc, arrivals, event_id=event_id)
        self.doc = zw.apply_delta(self.doc, res["delta"])
        if check:
            self.check()
            assert step_problems(before, self.doc, may_change_after(self.plan, before, self.doc)) == []
        return res

    def one_by_one(self, arrivals, check=True):
        """The arrivals as one call each (a call the world is only checked after, when `check`): the world does not depend on how a batch is cut, except for the
        size of a rib that opens for it."""
        for a in arrivals[:-1]:
            self.send([a], check=False)
        if arrivals:
            self.send(arrivals[-1:], check=check)

    def finish(self):
        """Complete the world after its last arrival (a mirror city: the roads no house stands on or below) and check it."""
        self.doc = zw.apply_delta(self.doc, zw.complete(self.plan, self.tv, self.doc)["delta"])
        self.check()

    def tagged(self, *tags):
        return by_tag(self.items, *tags)

    def road(self, item):
        return road_of(self.doc, item)

    def count(self, road):
        return count(self.doc, road)

    def shown(self):
        return world_layout(self.doc, with_coast=False)


# --------------------------------------------------------------------------------- the rule, as a checker ----
def ring_root_problems(places, plan):
    """The root of a world on a plan with the ring road: it stands from day one, with the plan's label, the plan's radius for lap 1 and the gates G1 (G2 beyond), the gates read from the
    plan file by `gates_of` and not asked of the engine."""
    root = zw.ROOT_PLACE
    rec = places.get(root)
    if rec is None:
        return [(root, "a world with the ring road has the ring from day one")]
    ring = plan["params"]["ring"]
    want = {"kind": "street", "shape": "ring", "label": ring["label"], "address": [ring["label"]], "parent": lay.PLAZA_PLACE, "level": 1, "class": "大道", "road": f"road:{root}"}
    bad = [(root, f"{k} is {rec.get(k)!r}") for k, v in want.items() if rec.get(k) != v]
    if rec["ring"]["radius"] != ring["radius"] or rec["ring"]["gaps"] != gates_of(plan) or rec["ring"]["lap"] != 1:
        bad.append((root, "lap 1 is not the plan's radius with the gates G1"))
    if any(places[lap]["ring"]["gaps"] != gates_of(plan, sides=True) for lap in rec.get("lanes", [])):
        bad.append((root, "a lap beyond the first does not have the gates G2"))
    return bad


def district_problems(doc, plan, tree):
    """Violations of the rule in a world with districts (empty: sound), read from the world document alone and from a fresh `World` (the lookup
    of the road of a topic is asked again, not remembered)."""
    pv = zw.PlanView(plan)
    tv = tree if isinstance(tree, TreeView) else TreeView(tree)
    rule = pv.districts
    mx, mn = rule["max"], rule["min"]
    bad = []
    places, root = doc["places"], zw.ROOT_PLACE
    counts = direct_counts(doc)
    roads = roads_of(doc)
    fresh = zw.World(pv, tv, doc)
    # every house stands where the rule says: the nearest open road at or above its topic, the ring road when there is none
    for pid, p in places.items():
        if p["kind"] != "lot":
            continue
        want = fresh.road_for_tag(p["tag"]) if p["tag"] is not None else root
        if p["street"] != want:
            bad.append((pid, f"stands on {p['street']} but its topic belongs to {want}"))
        if p["street"] not in places or places[p["street"]]["kind"] != "street":
            bad.append((pid, "its road is not a street of the world"))
        elif places[p["parent"]].get("lane_of", p["parent"]) != p["street"]:
            bad.append((pid, "stands in a rib that is not of its road"))
        if "underground" in p:
            bad.append((pid, "a house of a world with the ring road is not underground"))
    bad += ring_root_problems(places, plan)
    # no street of any other kind, and the topics a road holds are held once
    held = Counter()
    for pid, r in roads.items():
        held[r["tag"]] += 1
        for t in r.get("collapsed", []):
            held[t] += 1
        if r["parent"] != lay.PLAZA_PLACE:
            parent = places.get(r["parent"])
            if parent is None or r["level"] != parent["level"] + 1 or r["address"][:-1] != parent["address"]:
                bad.append((pid, "level or address do not follow the road above"))
            elif parent["shape"] == "rib":
                bad.append((pid, "a road below a rib: the road above should be a group"))
        elif r["level"] != 1:
            bad.append((pid, "a road with no road above is not ring 1"))
    bad += [(t, "a topic is held by two roads") for t, n in held.items() if n > 1]
    # the count and the over flag
    mirror = pv.mode == plan_mod.MIRROR
    for pid in sorted(set(counts) | set(roads)):
        n = counts.get(pid, 0)
        rec = places.get(pid)
        if rec is None:
            continue
        over = bool(rec.get("over"))
        if n > mx and not over:
            bad.append((pid, f"{n} houses but not over"))
        if over and n <= mx:
            bad.append((pid, f"over with {n} houses"))
        if over and not mirror and fresh.find_split(pid, fresh.lots_on(pid)) is not None:
            bad.append((pid, "over although a group could open a road"))
    # one stretch (invariant 3): a road has one rib and no street continues another but the laps of the ring road; a road that was never over holds `max` lots at most
    ever_over = {e["over"] for e in doc["chronicle"] if "over" in e}
    for pid, p in places.items():
        if p["kind"] == "street" and ("lane_of" in p or "continued" in p or "lanes" in p) and not (p.get("shape") == "ring" and (pid == root or pid.startswith(f"{root}:lap:"))):
            bad.append((pid, "a street that continues another, or has a second rib: a road is one stretch"))
    for pid, road in roads.items():
        if pid not in ever_over and road.get("rib", {}).get("slots", 0) > mx:
            bad.append((pid, f"a rib of {road['rib']['slots']} lots on a road that was never over"))
    # the chronicle: one numbered line per event, the numbers of a split add up
    chron = doc["chronicle"]
    if [e["n"] for e in chron] != list(range(1, len(chron) + 1)):
        bad.append(("chronicle", "numbers are not 1..n"))
    for e in chron:
        if "from" in e:
            if mirror or len(e["houses"]) < mn or e["count_before"] != e["count_after"] + len(e["houses"]) or e["from"] == e["to"] or e["count_before"] <= mx:
                bad.append(("chronicle", f"entry {e['n']} does not add up"))
        elif "over" not in e or e["count"] <= mx:
            bad.append(("chronicle", f"entry {e['n']} is neither a split nor an over"))
    return bad


# ------------------------------------------------------------------------------------------ the measure of waste ----
# Land is laid for the houses that need it. A snapshot cannot tell a rib laid too long from the lots that a split freed afterwards (the houses that stay are
# packed onto the first lots and the rib keeps its length), so these checks are read one step at a time, at the moment the land is laid.
def rib_need(n, max_houses):
    """The lots a road of `n` houses needs, stated apart from the engine: its houses and the headroom (4 lots, or half the houses rounded up if that is more), in
    whole cells (an even number of lots), at most `max_houses` while the road is not over (n <= max)."""
    want = n + max(4, -(-n // 2))
    want += want % 2
    return min(max_houses, want) if n <= max_houses else want


def frontage(doc, road):
    """The ribs of a road: its one rib, when it has one."""
    return [road] if "rib" in doc["places"][road] else []


def on_the_ring(doc):
    """The ids of the houses that stand on a lap of the ring road."""
    return {p["article"] for p in doc["places"].values() if p["kind"] == "lot" and doc["places"].get(p["parent"], {}).get("shape") == "ring"}


def land_waste(before, after, max_houses):
    """The land that one step of a world laid beyond need, as a list of (what, place, detail): empty when there is none. `before` and `after` are the world on either
    side of one call.
      rib  a rib laid or grown in this step (a street record with a rib that is new, or whose lots changed) leaves its road holding more lots than rib_need(n). n is the
           houses of the road after the step. A call of one arrival is read exactly: the arrival is the last thing that happens to its road, so a rib that it lays or grows (also
           for the survivors of a split, or for the group of a split that splits again at once) is laid for the houses the road holds after the step. A call of several arrivals
           is read leniently, since a rib may have been laid before a split of the same call: n then counts the houses that a split of this step took from the road too;
      grow a rib grows only when it is full: the houses that came to its road in this step outnumber the empty lots it had before the step; and it grows by
           max(rib_need(n) - held, 1) lots (read exactly for a call of one arrival). A step in which a split took houses from the road is excused (it frees lots as it goes);
      lap  a lap of the ring opened in this step although the laps that stood had free slots that the houses this step put on the ring did not fill: the step put fewer
           houses on the ring than the free slots plus the one that opened the lap. The houses that came to the ring and left it again in a split of the same call count;
      lot  a house placed in this step (it came, or a split put it on another lot) stands farther along its road than a lot the step left free: farther than its
           road's houses need (a house takes the lowest free lot, and a split packs the houses that stay onto the first lots). The ring road keeps its own fill order
           and is no such road."""
    bad = []
    places, prev = after["places"], before["places"]
    new = after["chronicle"][len(before["chronicle"]):]  # what happened in this step
    left = Counter()
    for e in new:
        if "from" in e:
            left[e["from"]] += len(e["houses"])
    held = Counter(p["street"] for p in places.values() if p["kind"] == "lot")
    was_lots = {p["article"] for p in prev.values() if p["kind"] == "lot"}
    came = Counter(p["street"] for p in places.values() if p["kind"] == "lot" and p["article"] not in was_lots)  # houses new to the world, by the road they stand on
    arrivals = sum(came.values())
    laid = {}  # road -> the ribs laid or grown for it in this step
    for pid, rec in places.items():
        if rec["kind"] == "street" and "rib" in rec:
            old = prev.get(pid)
            if old is None or "rib" not in old or old["rib"]["slots"] != rec["rib"]["slots"]:
                laid.setdefault(rec.get("lane_of", pid), []).append(pid)
    on_rib = Counter(p["parent"] for p in prev.values() if p["kind"] == "lot")
    for road, ribs in laid.items():
        lots = sum(places[r]["rib"]["slots"] for r in frontage(after, road))
        n = held[road] + (left[road] if arrivals > 1 else 0)
        if lots > rib_need(n, max_houses):
            bad.append(("rib", road, f"{lots} lots for {n} houses, need {rib_need(n, max_houses)} (laid: {', '.join(sorted(ribs))})"))
        if left[road]:
            continue
        for pid in ribs:
            old = prev.get(pid)
            if old is None or "rib" not in old:
                continue  # (a rib that opened in this step is sized by the check above)
            slots, free = old["rib"]["slots"], old["rib"]["slots"] - on_rib[pid]
            if came[road] <= free:
                bad.append(("grow", road, f"{pid} grew from {slots} lots with {free} empty, and {came[road]} house(s) came to the road"))
            want = slots + max(rib_need(held[road], max_houses) - slots, 1)
            if arrivals == 1 and places[pid]["rib"]["slots"] != want:
                bad.append(("grow", road, f"{pid} grew from {slots} to {places[pid]['rib']['slots']} lots, not to {want} (max(need - held, 1) for {held[road]} houses)"))
    if ROOT in prev and prev[ROOT].get("shape") == "ring":
        laps = [ROOT, *prev[ROOT].get("lanes", [])]
        opened = [k for k in places[ROOT].get("lanes", []) if k not in laps]
        if opened:
            free = sum(prev[k]["ring"]["slots"] - prev[k]["lots"] for k in laps)
            gone = {h for e in new if e.get("from") == ROOT for h in e["houses"]}  # came to the ring in this call and left it again in a split
            ring_came = len((on_the_ring(after) | gone) - on_the_ring(before))
            if ring_came < free + 1:
                bad += [("lap", k, f"opened with {free} free slots on the laps before it, {ring_came} house(s) came to the ring") for k in opened]
    was = {p["article"]: (p["parent"], p["slot"]) for p in prev.values() if p["kind"] == "lot"}
    placed, taken = {}, {}
    for p in places.values():
        if p["kind"] == "lot":
            taken.setdefault(p["street"], set()).add((p["parent"], p["slot"]))
            if was.get(p["article"]) != (p["parent"], p["slot"]):
                placed.setdefault(p["street"], set()).add((p["parent"], p["slot"]))
    for road, now in placed.items():
        rec = places.get(road, {})
        if rec.get("shape") == "ring" or "rib" not in rec:
            continue
        order = [(r, s) for r in frontage(after, road) for s in range(places[r]["rib"]["slots"])]
        first_free = next((i for i, lot in enumerate(order) if lot not in taken[road]), len(order))
        beyond = sorted(i for i, lot in enumerate(order) if lot in now and i > first_free)
        if beyond:
            bad.append(("lot", road, f"{len(beyond)} house(s) placed beyond lot {first_free}, which the step left free"))
    return bad


# ---------------------------------------------------------------------------------------- one step, between two worlds ----
# What a step of a world may change, and what it may not. A rib that grows moves what lies beyond it and nothing else: no house changes its address or its lot, a rib keeps
# its mode, its row and its side, the spans of a line keep their order and none of them moves inward. Each check reads two worlds, the one before a step and the one after.
def lot_key(p):
    """What a house is to its street: the road, the topic, the rib and the slot, and where it came in the order of arrival. Not where the rib stands: that is derived."""
    return (p["street"], p["tag"], p["parent"], p["slot"], p["order"], p["seq"])


def row_and_side(doc, p):
    """(row, side) of a house, read from where it stands: on a band the row (inner, nearer the plaza than the lane of the band, or outer) and the side of the axis of its line;
    along the spoke the side of the axis."""
    rib = doc["places"][p["parent"]]["rib"]
    axis = doc["lines"][rib["line"]]["axis"]
    x, z = p["position"]["x"], p["position"]["z"]
    if rib["mode"] == "spoke":
        return "spoke", "left" if x * math.cos(math.radians(axis)) + z * math.sin(math.radians(axis)) < 0 else "right"
    turn = (math.degrees(math.atan2(x, -z)) - axis + 180.0) % 360.0 - 180.0
    return "inner" if math.hypot(x, z) < rib["s"] else "outer", "left" if turn < 0 else "right"


def spans_of(line):
    """The spans of a line in radial order, as (lo, kind, key): bands, branch circles and ribs along the spoke."""
    out = [(b["s"] - 1.5, "band", k) for k, b in enumerate(line["bands"])] + [(sp[0], "spoke", k) for k, sp in enumerate(line["spokes"])]
    out += [(m["r1"] - 1.0, "branch", m["place"]) for m in line["members"] if m["r1"] is not None]
    return [(kind, key) for _lo, kind, key in sorted(out)]


def streets_along(doc, lid, band, side):
    """The streets of the ribs along one side of a band, nearest the axis first, ghosts too: read from the roads, which a move leaves where they are."""
    lanes = [r for r in doc["roads"].values() if r["kind"] == "lane" and r.get("trunk") == lid and r["band"] == band and r["side"] == side]
    return [r["street"] for r in sorted(lanes, key=lambda r: r["off"])]


def step_problems(before, after, may_change=lambda lot_before, lot_after: False, *, re_ribbed=frozenset(), laid_out_again=False):
    """What one step did that it may not (empty: nothing), as (invariant, what, detail). `may_change(lot_before, lot_after)` is True for a house that the step may put on
    another road or lot (a split, a move, a merge, a filing). `re_ribbed`: the streets of roads that the step moved, whose rib is a new one (the old rib stays in the line as a
    ghost). `laid_out_again`: the step laid the whole world out afresh (a new ring road), so that only the first two hold.
      1 address  every house keeps its road and its topic;
      2 lot      every house keeps its rib and its slot;
      4 row      a rib keeps its mode, its band and its side; a house keeps its row (inner or outer) and its side of the axis, read from where it stands;
      6 order    the spans of a line keep their radial order (new ones are put among them), and the streets along a side of a band keep theirs (new ones come last);
      7 monotone no span of a line, no road of a band and no rib moves inward or gets fewer lots."""
    bad = []
    was, now = {p["article"]: p for p in before["places"].values() if p["kind"] == "lot"}, {p["article"]: p for p in after["places"].values() if p["kind"] == "lot"}
    for aid, lot in was.items():
        if aid not in now:
            bad.append((1, "a house is gone", aid))
        elif lot_key(lot) != lot_key(now[aid]) and not may_change(lot, now[aid]):
            what = (1, "a house changed its road or topic") if lot["street"] != now[aid]["street"] or lot["tag"] != now[aid]["tag"] else (2, "a house changed its lot")
            bad.append((*what, f"{aid}: {lot_key(lot)} -> {lot_key(now[aid])}"))
    if laid_out_again:
        return bad
    for pid, rec in before["places"].items():
        later = after["places"].get(pid)
        if rec["kind"] != "street" or "rib" not in rec or later is None or "rib" not in later:
            continue
        if pid in re_ribbed:
            continue
        old, new = rec["rib"], later["rib"]
        for key in ("mode", "line", "band", "side", "trunk"):
            if old[key] != new[key]:
                bad.append((4, f"a rib changed its {key}", f"{pid}: {old[key]!r} -> {new[key]!r}"))
        if new["slots"] < old["slots"]:
            bad.append((7, "a rib lost lots", f"{pid}: {old['slots']} -> {new['slots']}"))
    for aid, lot in was.items():
        later = now.get(aid)
        if later is None or (lot["parent"], lot["slot"]) != (later["parent"], later["slot"]) or "rib" not in after["places"][lot["parent"]] or lot["street"] in re_ribbed:
            continue  # (gone, or put on another lot: said above; a house of the ring road has no rib)
        if row_and_side(before, lot) != row_and_side(after, later):
            bad.append((4, "a house changed its row or its side", f"{aid}: {row_and_side(before, lot)} -> {row_and_side(after, later)}"))
    for lid, line in before["lines"].items():
        later = after["lines"].get(lid)
        if later is None:
            continue
        order_before, order_after = spans_of(line), spans_of(later)
        if [x for x in order_after if x in set(order_before)] != order_before:
            bad.append((6, "the spans of a line changed their order", f"{lid}: {order_before} -> {order_after}"))
        for k, band in enumerate(line["bands"]):
            for side in (-1, 1):
                a, b = streets_along(before, lid, k, side), streets_along(after, lid, k, side)
                if b[:len(a)] != a:
                    bad.append((6, "the streets along a side of a band changed their order", f"{lid} band {k} side {side}: {a} -> {b}"))
            if later["bands"][k]["s"] < band["s"] - 1e-9 or any(y < x - 1e-9 for x, y in zip(band["used"], later["bands"][k]["used"])):
                bad.append((7, "a band moved inward or got shorter", f"{lid} band {k}: {band['s']} {band['used']} -> {later['bands'][k]['s']} {later['bands'][k]['used']}"))
        for k, span in enumerate(line["spokes"]):
            if later["spokes"][k][0] < span[0] - 1e-9 or later["spokes"][k][1] < span[1] - 1e-9:
                bad.append((7, "a rib along the spoke moved inward or got shorter", f"{lid} spoke {k}: {span} -> {later['spokes'][k]}"))
        for m, n in zip(line["members"], later["members"]):
            if n["s0"] < m["s0"] - 1e-9 or (m["r1"] is not None and n["r1"] < m["r1"] - 1e-9):
                bad.append((7, "a member or a branch circle moved inward", f"{lid} {m['place']}: {m['s0']} {m['r1']} -> {n['s0']} {n['r1']}"))
    for rid, road in before["roads"].items():
        later = after["roads"].get(rid)
        if later is not None and road["kind"] == "lane" and later.get("trunk") == road["trunk"] and road["trunk"] in after["lines"] and (
                later["radius"] < road["radius"] - 1e-9 or later["off"] < road["off"] - 1e-9 or later["length"] < road["length"] - 1e-9):
            bad.append((7, "a road of a band moved inward or got shorter", f"{rid}: {road['radius']} {road['off']} {road['length']} -> {later['radius']} {later['off']} {later['length']}"))
    return bad


def grow_by(more_of):
    """A planted fault: a rib that grows by `more_of(need, held, max)` lots instead of max(need - held, 1)."""
    def grow(self, spec):
        n = self.hold.get(spec.place)
        if n is None:
            n = len(self.lots_on(spec.place)) + 1
        street = self.places.mut(spec.place)
        more = more_of(zw.district_road_need(n, self.max), street["rib"]["slots"], self.max)
        street["rib"]["slots"] += more
        street["reserved"] += more
        line = self.lines.mut(street["rib"]["line"])
        for e in line["log"]:
            for entry in (e["rib"],) if e["kind"] == "spoke" else [r for side in e["ribs"] for r in side] if e["kind"] == "band" else ():
                if entry["place"] == spec.place:
                    entry["width"] = math.ceil(street["rib"]["slots"] / 2)
        self.lay_line(street["rib"]["line"], grown=spec.place)
        return spec.place
    return grow


def may_change_after(plan, before, after):
    """Which houses a call may put on another road or lot: those of a road that split in it, except the survivors of the ring road, which stand."""
    splitting = {e["from"] for e in after["chronicle"][len(before["chronicle"]):] if "from" in e}
    ring = plan["params"].get("ring")
    return lambda lot, now: lot["street"] in splitting and not (ring and lot["street"] == zw.ROOT_PLACE == now["street"])


def simulate_districts(seed, *, max_houses=12, min_houses=4, trunk_min=40, batch_max=15, order="shuffle", check_every=1, mode="grow"):
    """A random world on a plan with districts: its items in random batches (a batch is one call), every invariant checked after every step.
    Returns (problems, the final world, the number of steps, the plan, the tree view).

    `problems` is a list of (seed, step, what, detail): empty when the world was sound after every step. A call changes the lot of a house only
    when the road of the house split in it - and not even then on the ring road: a house that is on the ring before and after the call stands."""
    tree, items = random_world(seed)
    tv = TreeView(tree)
    plan = plan_mod.build_plan(tv, items, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    doc = zw.new_world(plan)
    rng = random.Random(seed * 7919 + 3)
    seq = list(items)
    rng.shuffle(seq)
    if order == "by_tag":
        seq.sort(key=lambda a: (a["topics"][0] if a["topics"] else "~", a["id"]))
    elif order == "reverse":
        seq.reverse()
    problems, i, step, event, placed = [], 0, 0, 0, 0

    def audit(label):
        found = checks.all_problems(doc)
        if found:
            problems.append((seed, step, label, {k: v[:3] for k, v in found.items()}))
        found = district_problems(doc, plan, tv)
        if found:
            problems.append((seed, step, f"{label} (districts)", found[:4]))
        found = lay_problems(doc, plan, tv)
        if found:
            problems.append((seed, step, f"{label} (laid again)", found[:4]))
        if len(zw.houses(doc)) != placed:
            problems.append((seed, step, label, f"{len(zw.houses(doc))} lots for {placed} houses"))

    while i < len(seq):
        batch = seq[i:i + rng.randint(1, batch_max)]
        i += len(batch)
        step += 1
        event += 1
        chron0, world_before = len(doc["chronicle"]), doc
        res = zw.assign(plan, tv, doc, batch, event_id=event)
        doc = zw.apply_delta(doc, res["delta"])
        problems += [(seed, step, "land laid beyond need", w) for w in land_waste(world_before, doc, max_houses)]
        problems += [(seed, step, f"invariant {n}: {what}", detail) for n, what, detail in step_problems(world_before, doc, may_change_after(plan, world_before, doc))]
        placed += len(batch)
        after = zw.houses(doc)
        if set(res["placements"]) != {a["id"] for a in batch} or any(res["placements"][a] != after[a] for a in res["placements"]):
            problems.append((seed, step, "placements are not the arrivals as they stand", sorted(res["placements"])[:3]))
        if any(e["event_id"] != event for e in doc["chronicle"][chron0:]):
            problems.append((seed, step, "an entry of the chronicle carries another event", event))
        if step % check_every == 0:
            audit("assign")
    doc = zw.apply_delta(doc, zw.complete(plan, tv, doc)["delta"])
    audit("complete")
    if mode == plan_mod.MIRROR and set(roads_of(doc)) != {tag_street(t) for t in plan["roads"]}:
        problems.append((seed, step, "a completed mirror world lacks a road of its plan", sorted(set(plan["roads"]) - {p["tag"] for p in roads_of(doc).values()})[:3]))
    return problems, doc, step, plan, tv
