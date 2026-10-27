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
    return after, res


def sound(doc, plan, tree):
    assert checks.all_problems(doc) == {}
    assert district_problems(doc, plan, tree) == []


class Town:
    """A world with districts and its tree: `send` checks the world after every step (the geometry and the rule)."""

    def __init__(self, spec, **kw):
        self.tree, self.items, self.plan, self.doc = world_of(spec, **kw)
        self.tv = TreeView(self.tree)

    def check(self):
        sound(self.doc, self.plan, self.tv)

    def send(self, arrivals, event_id=None, check=True):
        res = zw.assign(self.plan, self.tv, self.doc, arrivals, event_id=event_id)
        self.doc = zw.apply_delta(self.doc, res["delta"])
        if check:
            self.check()
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
    of the road of a topic is asked again, not remembered). A world only grows here, so the ribs of a road fill in order: a rib has houses only
    when every rib before it is full."""
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
    # the ribs of a road: none above `max` lots; a continuation is the road itself; a road that was never over holds `max` lots at most in its ribs
    ever_over = {e["over"] for e in doc["chronicle"] if "over" in e}
    for pid, road in roads.items():
        carriers = ([pid] if "rib" in road else []) + list(road.get("lanes", []))
        label = road.get("label") or road["address"][-1]
        slots = 0
        for k, carrier in enumerate(carriers):
            c = places[carrier]
            slots += c["rib"]["slots"]
            if c["rib"]["slots"] > mx:
                bad.append((carrier, f"a rib of {c['rib']['slots']} lots, over {mx}"))
            if k:
                same = {"lane_of": pid, "continued": True, "label": label, "level": road["level"], "class": road["class"], "address": road["address"], "parent": pid}
                bad += [(carrier, f"a continuation has {j} {c.get(j)!r}, not {v!r}") for j, v in same.items() if c.get(j) != v]
            if k and c["lots"] and any(places[e]["lots"] < places[e]["rib"]["slots"] for e in carriers[:k]):
                bad.append((carrier, "a rib has houses while a rib before it is not full"))
        if pid not in ever_over and slots > mx:
            bad.append((pid, f"ribs of {slots} lots on a road that was never over"))
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
    """The ribs of a road in order: its own rib (when it has one), then its continuation ribs by ordinal."""
    rec = doc["places"][road]
    return ([road] if "rib" in rec else []) + sorted(rec.get("lanes", []), key=lambda r: doc["places"][r].get("ordinal", 0))


def on_the_ring(doc):
    """The ids of the houses that stand on a lap of the ring road."""
    return {p["article"] for p in doc["places"].values() if p["kind"] == "lot" and doc["places"].get(p["parent"], {}).get("shape") == "ring"}


def land_waste(before, after, max_houses):
    """The land that one step of a world laid beyond need, as a list of (what, place, detail): empty when there is none. `before` and `after` are the world on either
    side of one call.
      rib  a rib laid in this step (a street record with a rib that is new, or whose lots changed) leaves its road holding more lots than rib_need(n). n is the houses of
           the road after the step. A call of one arrival is read exactly: the arrival is the last thing that happens to its road, so a rib that it lays (also for the
           survivors of a split, or for the group of a split that splits again at once) is laid for the houses the road holds after the step. A call of several arrivals
           is read leniently, since a rib may have been laid before a split of the same call: n then counts the houses that a split of this step took from the road too;
      lap  a lap of the ring opened in this step although the laps that stood had free slots that the houses this step put on the ring did not fill: the step put fewer
           houses on the ring than the free slots plus the one that opened the lap. The houses that came to the ring and left it again in a split of the same call count;
      lot  a house placed in this step (it came, or a split put it on another lot) stands farther along its road than a lot the step left free: farther than its
           road's houses need (a house takes the lowest free lot, and a split packs the houses that stay onto the first lots). The ring road keeps its own fill order
           and is no such road;
      cont a continuation rib that is new in this step while the ribs before it, which its road had before the step, still have free lots after it (a road continues
           only when it is full), unless a split of this step took houses from the road (in a call of several arrivals)."""
    bad = []
    places, prev = after["places"], before["places"]
    new = after["chronicle"][len(before["chronicle"]):]  # what happened in this step
    left = Counter()
    for e in new:
        if "from" in e:
            left[e["from"]] += len(e["houses"])
    held = Counter(p["street"] for p in places.values() if p["kind"] == "lot")
    arrivals = sum(held.values()) - sum(1 for p in prev.values() if p["kind"] == "lot")
    laid = {}  # road -> the ribs laid for it in this step
    for pid, rec in places.items():
        if rec["kind"] == "street" and "rib" in rec:
            old = prev.get(pid)
            if old is None or "rib" not in old or old["rib"]["slots"] != rec["rib"]["slots"]:
                laid.setdefault(rec.get("lane_of", pid), []).append(pid)
    on_rib = Counter(p["parent"] for p in places.values() if p["kind"] == "lot")
    for road, ribs in laid.items():
        lots = sum(places[r]["rib"]["slots"] for r in frontage(after, road))
        n = held[road] + (left[road] if arrivals > 1 else 0)
        if lots > rib_need(n, max_houses):
            bad.append(("rib", road, f"{lots} lots for {n} houses, need {rib_need(n, max_houses)} (laid: {', '.join(sorted(ribs))})"))
        if arrivals == 1 or not left[road]:
            order = frontage(after, road)
            for lane in (r for r in order if r in ribs and "lane_of" in places[r] and r not in prev):  # a continuation rib that is new
                free = sum(places[r]["rib"]["slots"] - on_rib[r] for r in order[:order.index(lane)] if r in prev)  # on the ribs before it
                if free:
                    bad.append(("cont", road, f"{lane} opened while the ribs before it had {free} free lot(s)"))
    if ROOT in prev and prev[ROOT].get("shape") == "ring":
        laps = [ROOT, *prev[ROOT].get("lanes", [])]
        opened = [k for k in places[ROOT].get("lanes", []) if k not in laps]
        if opened:
            free = sum(prev[k]["ring"]["slots"] - prev[k]["lots"] for k in laps)
            gone = {h for e in new if e.get("from") == ROOT for h in e["houses"]}  # came to the ring in this call and left it again in a split
            came = len((on_the_ring(after) | gone) - on_the_ring(before))
            if came < free + 1:
                bad += [("lap", k, f"opened with {free} free slots on the laps before it, {came} house(s) came to the ring") for k in opened]
    was = {p["article"]: (p["parent"], p["slot"]) for p in prev.values() if p["kind"] == "lot"}
    placed, taken = {}, {}
    for p in places.values():
        if p["kind"] == "lot":
            taken.setdefault(p["street"], set()).add((p["parent"], p["slot"]))
            if was.get(p["article"]) != (p["parent"], p["slot"]):
                placed.setdefault(p["street"], set()).add((p["parent"], p["slot"]))
    for road, now in placed.items():
        rec = places.get(road, {})
        if rec.get("shape") == "ring" or not ("rib" in rec or rec.get("lanes")):
            continue
        order = [(r, s) for r in frontage(after, road) for s in range(places[r]["rib"]["slots"])]
        first_free = next((i for i, lot in enumerate(order) if lot not in taken[road]), len(order))
        beyond = sorted(i for i, lot in enumerate(order) if lot in now and i > first_free)
        if beyond:
            bad.append(("lot", road, f"{len(beyond)} house(s) placed beyond lot {first_free}, which the step left free"))
    return bad


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
        if len(zw.houses(doc)) != placed:
            problems.append((seed, step, label, f"{len(zw.houses(doc))} lots for {placed} houses"))

    while i < len(seq):
        batch = seq[i:i + rng.randint(1, batch_max)]
        i += len(batch)
        step += 1
        event += 1
        before, chron0, world_before = zw.houses(doc), len(doc["chronicle"]), doc
        res = zw.assign(plan, tv, doc, batch, event_id=event)
        doc = zw.apply_delta(doc, res["delta"])
        problems += [(seed, step, "land laid beyond need", w) for w in land_waste(world_before, doc, max_houses)]
        placed += len(batch)
        after = zw.houses(doc)
        splitting = {e["from"] for e in doc["chronicle"][chron0:] if "from" in e}  # the houses of a road that split may change lot

        def may_change(lot, now):  # a house of a road that split may change lot, except a survivor of the ring road
            return lot["street"] in splitting and not (plan["params"].get("ring") and lot["street"] == zw.ROOT_PLACE == now["street"])

        problems += [(seed, step, "a house moved with no split of its road", aid) for aid, lot in before.items() if after[aid] != lot and not may_change(lot, after[aid])]
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
