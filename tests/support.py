"""Worlds for the tests: small synthetic topic trees with items, a world with districts that checks itself after every step, and the invariants
of the rule (`district_problems`) with random simulations of a world.

Not collected by pytest (the name has no test_ prefix)."""

import itertools
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import checks

from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
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
    """{road place: street record} of the roads (the street records with a key); the root zone and the continuation ribs are not roads."""
    return {pid: p for pid, p in doc["places"].items() if p["kind"] == "street" and "lane_of" not in p and p.get("tag") is not None}


def direct_counts(doc):
    """{road or root zone place: houses standing on it directly} - on its ribs, never on a road below it."""
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
    decimals."""
    out = set()
    for rec in plan["trunks"].values():
        if rec["role"] == "ring1" or (sides and rec["role"] == "side"):
            lo, hi = (round(v * 100) for v in rec["wedge"])
            out.add(round(((lo + hi) / 200) % 360, 3) + 0.0)
    return sorted(out)


def capacity(radius, gates):
    """What a lap holds, from the independent cells of tests/checks.py."""
    return 2 * len(checks.free_cells(radius, gates))


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
def ring_root_problems(places, pv):
    """The root of a world on a plan with the ring road: it stands from day one, with the plan's label, the plan's radius for lap 1 and the gates G1 (G2 beyond)."""
    root = zw.ROOT_PLACE
    rec = places.get(root)
    if rec is None:
        return [(root, "a world with the ring road has the ring from day one")]
    want = {"kind": "street", "shape": "ring", "label": pv.ring["label"], "address": [pv.ring["label"]], "parent": lay.PLAZA_PLACE, "level": 1, "class": "大道",
            "road": f"road:{root}"}
    bad = [(root, f"{k} is {rec.get(k)!r}") for k, v in want.items() if rec.get(k) != v]
    if rec["ring"]["radius"] != pv.ring["radius"] or rec["ring"]["gaps"] != list(pv.gates()) or rec["ring"]["lap"] != 1:
        bad.append((root, "lap 1 is not the plan's radius with the gates G1"))
    if any(places[lap]["ring"]["gaps"] != list(pv.gates(sides=True)) for lap in rec.get("lanes", [])):
        bad.append((root, "a lap beyond the first does not have the gates G2"))
    return bad


def root_zone_problems(places):
    """The root zone of a world on a plan with no ring road: under the town hall, no road, no rib, lots on the cells of a grid in slot order (the first ones inside
    the plaza)."""
    root = zw.ROOT_PLACE
    rec = places.get(root)
    under = sorted((p for p in places.values() if p["kind"] == "lot" and p["street"] == root), key=lambda p: p["slot"])
    bad = []
    if rec is None:
        if under:
            bad.append((root, "houses without a root zone"))
    else:
        want = {"kind": "street", "shape": "underground", "underground": True, "label": "根區", "address": ["根區"], "parent": lay.PLAZA_PLACE}
        bad += [(root, f"{k} is {rec.get(k)!r}") for k, v in want.items() if rec.get(k) != v]
        bad += [(root, f"the root zone has a {k}") for k in ("rib", "road", "lane", "lanes", "tag", "carrier") if k in rec]
        if rec["lots"] != len(under) or rec["reserved"] != 0:
            bad.append((root, f"counters {rec['lots']}/{rec['reserved']} for {len(under)} houses"))
    if [p["slot"] for p in under] != sorted(set(p["slot"] for p in under)):
        bad.append((root, "two houses in one slot"))
    for p in under:
        x, z = zw.underground_cell(p["slot"])
        if p["parent"] != root or p["order"] != p["slot"] or (p["position"]["x"], p["position"]["z"]) != (x, z):
            bad.append((p["article"], "an underground house is not on the cell of its slot"))
        if p["slot"] < 89 and math.hypot(abs(x) + 0.5, abs(z) + 0.5) > lay.PLAZA_RADIUS + 1e-9:
            bad.append((p["article"], "one of the first 89 cells is not inside the plaza"))
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
    # every house stands where the rule says: the nearest open road at or above its topic, the root zone when there is none
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
        if pv.ring is not None:  # the ring road is on the surface: nothing is underground
            if "underground" in p:
                bad.append((pid, "a house of a world with the ring road is not underground"))
        elif bool(p.get("underground")) != (p["street"] == root):
            bad.append((pid, "a house is underground when and only when it stands in the root zone"))
    bad += ring_root_problems(places, pv) if pv.ring is not None else root_zone_problems(places)
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
        before, chron0 = zw.houses(doc), len(doc["chronicle"])
        res = zw.assign(plan, tv, doc, batch, event_id=event)
        doc = zw.apply_delta(doc, res["delta"])
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
