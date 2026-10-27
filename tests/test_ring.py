"""The ring road round the town hall (bibliopolis.ring and bibliopolis.world, "The ring road"; docs/engine.md).

Synthetic trees and arrivals, no files. The root of the road tree is a closed circular road round the town hall, on the surface, with houses on both sides; it
exists from day one; the cells of its lane keep clear of a gate at every direction an avenue can take; avenues leave from its outer edge; a full ring goes on as
a lap; a split from the ring frees only the lots of the group that leaves.

The expectations are stated here apart from the engine: the cells of a lap are re-derived by `checks.free_cells` (the union of the blocked intervals, whole cells
in each free stretch), the gates from the plan file (the middle of each ring-1 wedge), the walks by hand.
"""

import bisect
import copy
import heapq
import json
import math
import random

import checks
import pytest
from support import (ROOT, T, Town, art, by_tag, capacity, fill_order_of, first_free, gates_of, land_waste, laps_of, make_tree, on_ring, radius_for, ring_root_problems,
                     simulate_districts, slot_cell, tag_street, world_of)

import bibliopolis
from bibliopolis import document
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import ring
from bibliopolis import world as zw
from bibliopolis.tree import TreeView

G6 = [84.57, 98.57, 113.285, 128.0, 232.0, 338.285]  # six gates (the axes of six ring-1 trunks): 45 cells at the least radius, 90 houses
SPEC_A = {"med": T(0, a1=T(8), a2=T(7), b=T(9), c=T(9)), "pub": T(12)}  # 33 houses of med, then 12 of pub: house 41 is the 8th of pub
# med: a wide sector whose road lies on bands; pub: a narrow one, a leaf street along its spoke; top: a ring-1 trunk whose member has a side child (a branch circle)
LAP_SPEC = {"med": T(0, a1=T(30), a2=T(30)), "pub": T(14), "top": T(0, hv=T(0, h1=T(14), h2=T(14)), sd=T(0, s1=T(14), s2=T(14)))}
NARROW = {"big": T(300), **{f"s{i}": T(1) for i in range(12)}}  # twelve roots at the least angle of ring 1 (14 degrees): the sector sets the radius, not the houses


def untagged(n, first=900):
    """`n` items with no topic: the ring's own, which no group ever claims (an item without a topic is no group's)."""
    return [art(first + k, []) for k in range(n)]


def frontier(line):
    """The radius from which a line is free (`World.frontier`, stated again): beyond its last member, branch circle, band and spoke rib."""
    f = 0.0
    for m in line["members"]:
        f = max(f, m["s0"] + 1.0, (m["r1"] + 1.0) if m["r1"] is not None else 0.0)
    for b in line["bands"]:
        f = max(f, b["s"] + 1.5)
    for lo, hi in line["spokes"]:
        f = max(f, hi)
    return f


def ceil3(v):
    return math.ceil(v * 1000 - 1e-7) / 1000


def sound(town):
    """The geometry checks of the world and of the document that is served, the rule of the districts, and the records of the ring."""
    town.check()
    shown = town.shown()
    assert checks.document_problems(shown) == {} and checks.ring_problems(shown) == []
    return shown


# ----------------------------------------------------------------------------------------------- the plan ----
def test_the_plan_of_every_city_carries_the_ring_with_its_name_and_the_radius_the_formula_gives():
    for spec, rule in ((SPEC_A, (40, 10)), (LAP_SPEC, (40, 10)), (NARROW, (40, 10)), (SPEC_A, (30, 5)), (SPEC_A, (300, 10))):
        tree, items = make_tree(spec)
        for mode in ("grow", "mirror"):
            plan = plan_mod.build_plan(TreeView(tree), items, mode=mode, max_houses=rule[0], min_houses=rule[1], trunk_min=20)
            pv = zw.PlanView(plan)
            w_min = min(r["wedge"][1] - r["wedge"][0] for r in plan["trunks"].values() if r["role"] == "ring1")
            assert plan["params"]["ring"] == {"label": "Knowledge", "radius": radius_for(gates_of(plan), rule[0], round(w_min, 2))}, (spec, rule, mode)
            assert pv.ring == plan["params"]["ring"] and list(plan["params"])[-1] == "ring"
            assert plan_mod.build_plan(TreeView(tree), items, mode=mode, max_houses=rule[0], min_houses=rule[1], trunk_min=20) == plan  # same input, same plan


def test_a_ring_whose_narrowest_sector_is_the_least_angle_of_ring_one_is_sector_bound():
    tree, items, plan, _doc = world_of(NARROW)
    pv = zw.PlanView(plan)
    assert pv.sector_min() == 14.0 and len(pv.sectors()) == 13  # the least angle of ring 1: twelve small roots and the big one
    assert ring.ring_radius_for(gates_of(plan), 40) == 8.5  # the houses alone would fit at the least radius ...
    assert plan["params"]["ring"]["radius"] == 11.5 == radius_for(gates_of(plan), 40, 14.0)  # ... but a sector of 14 degrees has an arc of 2.4 at 8.5 + 1.5, less than 3
    assert (8.5 + 1.5) * math.radians(14.0) < ring.RING_AVENUE_ARC <= (11.5 + 1.5) * math.radians(14.0)
    assert ring.RING_MIN == 8.5 == lay.PLAZA_RADIUS + lay.LEAD + lay.BAND / 2 and ring.RING_AVENUE_ARC == 3.0


def test_the_gates_are_the_axes_of_the_ring_one_trunks_and_with_the_side_trunks_those_of_a_lap_beyond_the_first():
    tree, items, plan, doc = world_of(LAP_SPEC)
    pv = zw.PlanView(plan)
    assert list(pv.gates()) == gates_of(plan) == [4.115, 101.83, 262.285]  # the middle of each ring-1 wedge, mod 360, to three decimals
    assert list(pv.gates(sides=True)) == gates_of(plan, sides=True) == [4.115, 60.745, 101.83, 262.285]  # G2: the spoke of the side line is a gate too
    assert {t for t, r in plan["trunks"].items() if r["role"] == "side"} == {"place:tag:sd"} and gates_of(plan) == sorted(set(gates_of(plan)))
    assert doc["places"][ROOT]["ring"]["gaps"] == gates_of(plan) and ring.gates_of(plan["trunks"], True) == pv.gates(sides=True)


# ---------------------------------------------------------------------------------------------- the radius ----
@pytest.mark.parametrize("want", [1, 40, 90, 91, 122, 123, 200, 333, 1000])
@pytest.mark.parametrize("w_min", [None, 180.0, 14.0])
def test_the_radius_is_the_least_that_holds_max_between_the_gates_and_the_narrowest_sector(want, w_min):
    radius = ring.ring_radius_for(G6, want, w_min)
    assert radius == radius_for(G6, want, w_min) and (radius - 8.5) % 1 == 0  # a whole step from RING_MIN, stated apart with the independent cells
    assert capacity(radius, G6) >= want and (w_min is None or (radius + 1.5) * math.radians(w_min) >= 3.0 - 1e-9)  # both conditions hold ...
    earlier = [8.5 + k for k in range(int(radius - 8.5))]  # ... and no smaller whole step has both
    assert not [r for r in earlier if capacity(r, G6) >= want and (w_min is None or (r + 1.5) * math.radians(w_min) >= 3.0 - 1e-9)]
    assert ring.ring_radius_for(G6, want, w_min) >= ring.ring_radius_for(G6, want)  # a sector never makes the ring smaller


def test_the_numbers_of_six_gates_and_the_ladder_of_the_narrowest_sector():
    assert ring.ring_capacity(8.5, G6) == capacity(8.5, G6) == 90 and len(ring.ring_cells(8.5, G6)) == 45
    assert ring.ring_capacity(11.5, G6) == 122 and ring.ring_radius_for(G6, 40) == 8.5 and ring.ring_radius_for(G6, 40, 14.0) == 11.5
    assert ring.ring_radius_for((), 1) == 8.5 and ring.ring_capacity(8.5, ()) == 2 * 53  # no gate and no sector (N = 0): whole cells all round (L = 53.4)
    ladder = [ring.ring_radius_for(G6, 40, w) for w in (180.0, 90.0, 45.0, 28.6, 14.0, 12.52, 7.0, 5.0)]
    assert ladder == sorted(ladder) and ladder[0] == 8.5 and ladder[4] == 11.5 > ladder[3] and ladder[5] == 12.5 and ladder[-1] > ladder[-2] > ladder[5]
    exact = math.degrees(ring.RING_AVENUE_ARC / 13.0)  # (11.5 + 1.5) * radians(w) is 3 up to rounding: the bound is `>= 3 - EPS`
    assert ring.ring_radius_for(G6, 40, exact) == 11.5 and ring.ring_radius_for(G6, 40, exact - 1e-6) == 12.5
    for bad in (0, -14.0, float("nan"), float("inf"), True, "14"):
        with pytest.raises(ValueError, match="narrowest land"):
            ring.ring_radius_for(G6, 40, bad)


@pytest.mark.parametrize("edit, text", [
    (lambda p: p["params"]["ring"].update(radius=8.4), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius=0), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius=-9), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius=True), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius="9"), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius=float("nan")), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(radius=float("inf")), "RING_MIN"),
    (lambda p: p["params"]["ring"].update(label=""), "label"),
    (lambda p: p["params"]["ring"].update(label="  "), "label"),
    (lambda p: p["params"]["ring"].update(label=None), "label"),
    (lambda p: p["params"]["ring"].update(label=5), "label"),
    (lambda p: p["params"]["ring"].pop("label"), "label"),
    (lambda p: p["params"]["ring"].pop("radius"), "RING_MIN"),
    (lambda p: p["params"].update(ring="ring"), "object"),
    (lambda p: p["params"].update(ring=[8.5]), "object"),
    (lambda p: p["params"]["districts"].update(max=500), "fewer than districts.max"),
])
def test_a_ring_the_engine_cannot_build_is_refused_when_the_plan_is_read(edit, text):
    _tree, _items, plan, _doc = world_of(SPEC_A)
    edit(plan)
    with pytest.raises(ValueError, match=text):
        zw.PlanView(plan)
    with pytest.raises(ValueError):
        zw.new_world(plan)


def test_a_radius_too_small_for_the_narrowest_sector_is_refused_and_a_larger_one_than_the_formula_gives_is_taken():
    _tree, _items, plan, _doc = world_of(NARROW)
    assert plan["params"]["ring"]["radius"] == 11.5
    plan["params"]["ring"]["radius"] = 10.5  # holds the houses, not an avenue in the narrowest sector: (10.5 + 1.5) * radians(14) = 2.93
    with pytest.raises(ValueError, match="narrowest land"):
        zw.PlanView(plan)
    plan["params"]["ring"]["radius"] = 12.5  # the plan is the authority: a larger radius is a plan
    assert zw.PlanView(plan).ring["radius"] == 12.5 and zw.new_world(plan)["places"][ROOT]["ring"]["radius"] == 12.5


def test_a_plan_radius_that_holds_max_exactly_is_taken_and_one_house_more_is_not():
    _tree, _items, plan, _doc = world_of(SPEC_A)
    g = gates_of(plan)
    plan["params"]["districts"]["max"] = capacity(8.5, g)
    assert zw.PlanView(plan).ring["radius"] == 8.5
    plan["params"]["districts"]["max"] = capacity(8.5, g) + 1
    with pytest.raises(ValueError, match="fewer than districts.max"):
        zw.PlanView(plan)
    plan["params"]["ring"]["radius"] = 9.5
    assert zw.PlanView(plan).ring["radius"] == 9.5  # (any radius from RING_MIN up that holds max is a plan; `build_plan` writes the least)
    plan["params"]["ring"]["radius"] = 10  # an integer is a number
    assert zw.PlanView(plan).ring["radius"] == 10


def test_a_larger_max_makes_the_plan_a_larger_radius_and_the_engine_takes_it():
    tree, items = make_tree(SPEC_A)
    big = plan_mod.build_plan(TreeView(tree), items, max_houses=200, min_houses=10, trunk_min=20)
    g = gates_of(big)
    assert big["params"]["ring"]["radius"] == radius_for(g, 200, 87.87) > 8.5
    assert capacity(big["params"]["ring"]["radius"], g) >= 200 > capacity(big["params"]["ring"]["radius"] - 1, g)  # the houses set it: the least step that holds max
    assert zw.new_world(big)["places"][ROOT]["ring"]["slots"] == capacity(big["params"]["ring"]["radius"], g)


def test_a_plan_with_no_ring_is_refused_and_a_world_must_start_with_the_ring_of_its_plan():
    tree, items, plan, doc = world_of(SPEC_A)
    bare_plan = copy.deepcopy(plan)
    del bare_plan["params"]["ring"]
    with pytest.raises(ValueError, match="has no ring road"):
        zw.PlanView(bare_plan)
    with pytest.raises(ValueError, match="has no ring road"):
        zw.new_world(bare_plan)
    bare = {**doc, "places": {k: v for k, v in doc["places"].items() if k != ROOT}}  # (a world that lacks the ring of its plan)
    with pytest.raises(ValueError, match="starts with the ring road"):
        zw.assign(plan, tree, bare, [art(1, [])])


# -------------------------------------------------------------------------------------------------- cells ----
CELL_CASES = [(8.5, G6), (9.5, G6), (11.5, G6), (14.5, G6), (28.881, G6), (8.5, ()), (11.5, ()), (8.5, (0.0,)), (8.5, (359.9,)), (8.5, (0.0, 359.0)), (11.5, (10.0, 10.3)),
              (8.5, (10.0, 17.0, 17.5)), (20.5, tuple(range(0, 360, 12))), (14.5, (60.555, *G6))]


@pytest.mark.parametrize("radius, gates", CELL_CASES)
def test_the_cells_of_a_lap_are_whole_cells_that_keep_clear_of_every_gate_on_both_rows(radius, gates):
    cells = ring.ring_cells(radius, gates)
    free = checks.free_cells(radius, gates)
    assert len(cells) == len(free) and list(cells) == pytest.approx(free, abs=1e-9)  # the walk of the spec, stated again
    assert ring.ring_cells(radius, list(gates)) == cells and ring.ring_cells(radius, gates) is ring.ring_cells(radius, gates)  # pure and cached: the same answer each time
    assert ring.ring_capacity(radius, gates) == 2 * len(cells)
    length = 2 * math.pi * radius
    assert all(0.5 - 1e-9 <= c and c + 0.5 <= length + 1e-9 for c in cells) and list(cells) == sorted(cells)  # from north, clockwise, inside one turn
    steps = [b - a for a, b in zip(cells, cells[1:])]
    assert all(abs(s - 1.0) < 1e-9 or s >= 2.0 - 1e-9 for s in steps)  # a cell starts where the one before ended, except across a gate (a whole cell of gap at least)
    for slot in range(2 * len(cells)):  # no lot centre nearer than 1.0 along the lane to a gate axis, on the inner row and on the outer row
        (x, z), facing = ring.ring_slot(radius, gates, slot)
        bearing = math.degrees(math.atan2(x, -z))
        for g in gates:
            along = abs((bearing - g + 180.0) % 360.0 - 180.0) * math.pi / 180.0 * radius
            assert along >= 1.0 - 5e-3, (slot, g, along)  # (a lot is a cell along the lane: its near edge stands TRUNK_LANE = 0.5 off the axis)
        assert math.hypot(x, z) == pytest.approx(radius - 1.0 if slot % 2 == 0 else radius + 1.0, abs=1e-9)  # inner row one cell inside the lane, outer row one outside
        want = math.degrees(cells[slot // 2] / radius) % 360
        assert abs((facing - (want if slot % 2 == 0 else want + 180.0) + 180.0) % 360.0 - 180.0) < 1e-9  # every house faces the ring road


def test_a_gate_at_north_or_just_before_it_cuts_the_cell_the_walk_starts_with_and_two_gates_close_together_are_one_blocked_stretch():
    length = 2 * math.pi * 8.5
    north = ring.ring_cells(8.5, (0.0,))  # the interval (-0.5, 0.5) is cut: the first cell starts at 0.5, its centre is 1.0; the one before the turn ends at L - 0.5
    assert north[0] == pytest.approx(1.0) and north[-1] + 0.5 <= length - 0.5 + 1e-9 and len(north) == 52
    before = ring.ring_cells(8.5, (359.9,))  # the gate's interval of the NEXT turn (k = -1) ends at 8.5 * radians(359.9) - L + 0.5 = 0.485: the first cell starts there
    assert before[0] == pytest.approx(8.5 * math.radians(359.9) - length + 0.5 + 0.5, abs=1e-9) and before[-1] + 0.5 <= 8.5 * math.radians(359.9) - 0.5 + 1e-9
    near, one = ring.ring_cells(11.5, (10.0, 10.3)), ring.ring_cells(11.5, (10.0,))  # 0.06 cells apart on the lane: the second gate costs at most one more cell
    assert list(near) == pytest.approx(checks.free_cells(11.5, (10.0, 10.3))) and len(one) - 1 <= len(near) <= len(one)


# -------------------------------------------------------------------------------------------------- day one ----
def test_the_ring_road_stands_from_day_one_with_its_road_and_no_house():
    tree, items, plan, doc = world_of(SPEC_A)
    g = gates_of(plan)
    assert sorted(doc["places"]) == ["place:plaza", ROOT] and sorted(doc["roads"]) == ["road:place:root"] and doc["lines"] == {} and doc["seq"] == 0
    assert doc["places"][ROOT] == {"kind": "street", "shape": "ring", "level": 1, "class": "大道", "label": "Knowledge", "address": ["Knowledge"], "parent": "place:plaza",
                                   "lots": 0, "reserved": 0, "road": "road:place:root", "ring": {"lap": 1, "radius": 8.5, "slots": capacity(8.5, g), "gaps": g}}
    road = doc["roads"]["road:place:root"]
    circle = [[round(8.5 * math.sin(math.radians(a)), 3) + 0.0, round(-8.5 * math.cos(math.radians(a)), 3) + 0.0] for a in (5 * k for k in range(73))]
    assert road == {"street": ROOT, "kind": "ring", "class": "大道", "parent": None, "at": 0.0, "length": round(2 * math.pi * 8.5, 3), "radius": 8.5, "points": circle}
    assert len(road["points"]) == 73 and road["points"][0] == road["points"][-1] == [0.0, -8.5]  # a closed polyline from north, clockwise
    assert "underground" not in json.dumps(doc) and "根區" not in json.dumps(doc)
    shown = document.world_layout(doc)
    assert sorted(shown["places"]) == ["place:plaza", ROOT] and sorted(shown["roads"]) == ["road:place:root"]  # the document shows the ring and its road at once
    assert shown["world"]["houses"] == 0 and shown["composition"]["articles"] == shown["composition"]["buildings"] == 0 and shown["counts"] == {"plaza": 1, "street": 1}
    streets, m = shown["composition"]["streets"], shown["composition"]["measure"]
    assert streets == {"total": 1, "containers": 0, "leaves": 0, "trunks": 0, "groups": 0, "spokes": 0, "lanes": 0, "continuations": 0, "ring": 1}
    assert (m["lots"], m["ring_lots"], m["max_radius"], m["walk_longest"], m["roads"], m["streets_by_class"]["大道"], m["max_ring"]) == (0, 0, 0.0, 0.0, 1, 1, 1)
    assert "underground_lots" not in m and shown["world"]["chronicle"] == [] and shown["coast"]["polygons"]  # the land is the plaza's and the ring's
    assert checks.all_problems(doc) == {} and checks.ring_problems(shown) == [] and ring_root_problems(doc["places"], plan) == []


def test_the_notes_of_a_ring_city_say_ring_and_never_underground():
    tree, items, plan, doc = world_of(SPEC_A)
    shown = document.world_layout(doc, with_coast=False)
    text = json.dumps({k: shown[k] for k in ("kinds", "roads_kinds", "geometry")} | {"notes": shown["world"]["notes"]}, ensure_ascii=False)
    assert "underground" not in text and "根區" not in text and "root zone" not in text
    assert "street.ring" in shown["world"]["notes"] and "ring" in shown["roads_kinds"] and "ring" in shown["kinds"]["street"]
    assert set(document.NOTES_DISTRICTS) <= set(shown["world"]["notes"]) and "street.ring" in document.NOTES_DISTRICTS  # the notes of the districts, the ring's among them


# --------------------------------------------------------------------- houses 1..40 and the split at house 41 ----
def test_the_first_forty_houses_stand_on_the_ring_round_the_whole_circle_in_fill_order():
    t = Town(SPEC_A)
    g = gates_of(t.plan)
    assert g == list(zw.PlanView(t.plan).gates()) and t.plan["params"]["ring"]["radius"] == 8.5
    fill = fill_order_of(capacity(8.5, g))
    for n, a in enumerate(t.items[:40], start=1):
        t.send([a])
        lot, slot = t.doc["places"][lay.article_place(a["id"])], fill[n - 1]
        assert (lot["parent"], lot["street"], lot["slot"], lot["order"], lot["seq"]) == (ROOT, ROOT, slot, slot, n)  # the n-th arrival takes the n-th slot in fill order
        (x, z), facing = slot_cell(8.5, g, slot)
        assert (lot["position"]["x"], lot["position"]["z"]) == (round(x, 3), round(z, 3)) and lot["facing"] == pytest.approx(round(facing, 3), abs=2e-3)
        assert math.hypot(lot["position"]["x"], lot["position"]["z"]) == pytest.approx(7.5 if slot % 2 == 0 else 9.5, abs=2e-3)  # inner row 7.5, outer row 9.5
        assert "underground" not in lot and t.doc["chronicle"] == []
    places = t.doc["places"]
    first, second, third, fourth = (places[lay.article_place(a["id"])] for a in t.items[:4])
    assert (first["position"]["x"], first["position"]["z"]) == (0.441, -7.487) and first["facing"] == pytest.approx(math.degrees(0.5 / 8.5), abs=2e-3)  # the first stands at the north
    cells = len(checks.free_cells(8.5, g))
    assert cells == 50 and len(fill) == 100 and fill[:4] == [0, 50, 25, 75]  # by hand: the 100 slots at 0, 1/2, 1/4 and 3/4 of the way round
    assert [p["slot"] for p in (first, second, third, fourth)] == [0, 50, 25, 75]  # the north, half way round, the quarters: spread evenly
    assert [p["slot"] // 2 for p in (first, second, third, fourth)] == [0, 25, 12, 37] and [p["slot"] % 2 for p in (first, second, third, fourth)] == [0, 0, 1, 1]  # (cells 0, 25, 12, 37; the rows)
    ring_street = places[ROOT]
    assert ring_street["lots"] == 40 and ring_street["reserved"] == 0 and "lanes" not in ring_street and "over" not in ring_street
    assert ring_street["ring"]["slots"] == capacity(8.5, g)
    assert [p for p in places.values() if p["kind"] == "reserved"] == [] and t.doc["lines"] == {} and list(t.doc["roads"]) == ["road:place:root"]  # no empty-lot record
    shown = t.shown()  # the ring's houses are surface lots like any: counted, in the coast, in the measures
    m = shown["composition"]["measure"]
    assert shown["composition"]["articles"] == shown["composition"]["buildings"] == shown["world"]["houses"] == 40 and m["lots"] == m["ring_lots"] == 40
    assert m["max_radius"] == round(max(math.hypot(p["position"]["x"], p["position"]["z"]) for p in on_ring(t.doc)) + 0.71, 1)
    assert [p["slot"] for p in sorted((q for q in shown["places"].values() if q["kind"] == "lot"), key=lambda q: q["seq"])] == fill[:40]
    sound(t)


def test_the_41st_house_opens_the_first_road_and_the_houses_that_stay_keep_their_lots():
    t = Town(SPEC_A)
    for a in t.items[:40]:
        t.send([a])
    before = {p["article"]: copy.deepcopy(p) for p in on_ring(t.doc)}
    fill = fill_order_of(capacity(8.5, gates_of(t.plan)))
    assert [before[a["id"]]["slot"] for a in by_tag(t.items, "pub")[:7]] == fill[33:40]  # behind the 33 houses of med
    res = t.send([t.items[40]])  # the 41st: the eighth house of pub
    (entry,) = t.doc["chronicle"]
    assert (entry["n"], entry["seq"], entry["trigger"], entry["from"], entry["to"], entry["label"]) == (1, 41, "arrival", ROOT, tag_street("med"), "Med")
    assert entry["count_before"] == 41 and entry["count_after"] == 8 and len(entry["houses"]) == 33
    assert entry["houses"] == [a["id"] for a in t.tagged("a1", "a2", "b", "c")]  # the group of the largest root topic, in arrival order
    left = set(entry["houses"])
    after = {p["article"]: p for p in on_ring(t.doc)}
    assert set(after) == (set(before) - left) | {t.items[40]["id"]} and len(after) == 8
    for aid in set(before) - left:  # the survivors keep their exact lot records (slot, position, facing, order, seq)
        assert after[aid] == before[aid]
    new = after[t.items[40]["id"]]
    assert (new["slot"], new["parent"]) == (fill[0], ROOT) == (0, ROOT)  # the house of the call that stays takes the first free slot in fill order: a hole the split left
    assert sorted(p["slot"] for p in after.values()) == sorted([fill[0], *fill[33:40]])
    assert t.doc["places"][ROOT]["lots"] == 8 and t.doc["places"][ROOT]["reserved"] == 0
    assert not [p for p in t.doc["places"].values() if p["kind"] == "reserved" and p["parent"] == ROOT]  # a ring lot leaves no empty-lot record
    assert [t.road(a) for a in by_tag(t.items, "pub")[:7]] == [ROOT] * 7 and all(t.road(h) == tag_street("med") for h in left)
    assert res["placements"][t.items[40]["id"]] == new and res["stats"]["splits"] == 1
    for k, a in enumerate(by_tag(t.items, "pub")[8:11], start=1):  # the next arrivals take the first holes in fill order, one after the other
        t.send([a])
        assert (t.doc["places"][lay.article_place(a["id"])]["slot"], t.doc["places"][lay.article_place(a["id"])]["parent"]) == (fill[k], ROOT)
    sound(t)


def test_the_avenue_leaves_from_the_outer_edge_of_the_ring_its_first_band_is_at_radius_plus_3():
    t = Town(SPEC_A)
    t.send(t.items[:41])
    line = t.doc["lines"][tag_street("med")]
    (member,) = line["members"]
    assert member["s0"] == 9.0 == 8.5 + 0.5  # the spoke starts at the outer edge of the ring road (R1 + TRUNK_LANE), not at the plaza rim
    spoke = t.doc["roads"]["road:" + tag_street("med")]
    assert spoke["parent"] is None and spoke["s0"] == 9.0 and math.hypot(*spoke["points"][0]) == pytest.approx(9.0, abs=2e-3)
    assert [b["s"] for b in line["bands"]] == [11.5] == [8.5 + 3.0]  # the first band lies at R1 + 3 ...
    outer_row_edge, band_inner_edge = 8.5 + 1.0 + 0.5, 11.5 - 1.5  # ... back to back with the outer row of the ring: its lots stand at 9.5 +- 0.5, the band's at 10.5 +- 0.5
    assert outer_row_edge == band_inner_edge == 10.0
    lane = t.doc["roads"]["road:" + tag_street("med") + ":lane"]
    assert lane["radius"] == 11.5 and lane["parent"] == "road:" + tag_street("med") and lane["at"] == pytest.approx(11.5 - 9.0)
    inner = [p for p in t.doc["places"].values() if p["kind"] == "lot" and p["parent"] == tag_street("med") and p["slot"] % 2 == 0]
    assert t.doc["places"][tag_street("med")]["rib"]["s"] == 11.5 and inner
    assert all(math.hypot(p["position"]["x"], p["position"]["z"]) == pytest.approx(10.5, abs=2e-3) for p in inner)  # the inner row of the band, at 11.5 - 1
    first = t.doc["places"][lay.article_place(t.tagged("a1")[0]["id"])]  # the walk to the first house of the avenue: out through the spoke to the lane (9 + 2.5), then 1.0 along it
    assert first["parent"] == tag_street("med") and first["slot"] == 0
    assert lay.lot_door_walks(t.shown())[first["article"]] == pytest.approx(11.5 + 1.0, abs=2e-3)
    sound(t)


def test_a_leaf_street_of_ring_one_lies_along_its_spoke_from_radius_plus_1_5():
    t = Town(LAP_SPEC)
    t.send(by_tag(t.items, "pub")[:10] + untagged(31))  # 10 houses of pub, then 31 with no topic: the 41st house makes the group of pub leave
    (entry,) = [e for e in t.doc["chronicle"] if "from" in e]
    assert (entry["to"], entry["seq"], len(entry["houses"])) == (tag_street("pub"), 41, 10)
    street = t.doc["places"][tag_street("pub")]
    assert street["rib"]["mode"] == "spoke" and street["rib"]["x0"] == 10.0 == 8.5 + 1.5  # a rib along the spoke starts at the outer edge of the ring + 1
    assert t.doc["lines"][tag_street("pub")]["spokes"][0][0] == 10.0 and t.doc["lines"][tag_street("pub")]["members"][0]["s0"] == 9.0
    sound(t)


def test_with_a_sector_bound_radius_the_avenues_leave_from_the_outer_edge_and_every_check_stands():
    t = Town(NARROW)
    r1 = t.plan["params"]["ring"]["radius"]
    assert r1 == 11.5
    t.send(by_tag(t.items, "big")[:40] + by_tag(t.items, "s0")[:1] + by_tag(t.items, "s1")[:1])
    (entry,) = [e for e in t.doc["chronicle"] if "from" in e]
    line = t.doc["lines"][entry["to"]]
    assert line["members"][0]["s0"] == r1 + 0.5 == 12.0 and t.doc["places"][ROOT]["ring"]["radius"] == 11.5
    assert all(b["s"] >= r1 + 3.0 for b in line["bands"])  # no band nearer than back to back with the outer row of the ring
    sound(t)


# --------------------------------------------------------------------- several hundred houses, several splits ----
def test_a_world_of_several_hundred_houses_with_several_splits_keeps_every_check():
    spec = {"sci": T(0, comp=T(0, ml=T(60), db=T(50), sys=T(0, os=T(30), net=T(30))), phys=T(0, optics=T(45), astro=T(40))), "arts": T(0, hist=T(40), lit=T(30)), "misc": T(12)}
    t = Town(spec, trunk_min=40)
    order = list(t.items)
    import random
    random.Random(5).shuffle(order)
    sizes, i = random.Random(9), 0
    while i < len(order):
        batch = order[i:i + sizes.randint(1, 14)]
        i += len(batch)
        t.send(batch)
    splits = [e for e in t.doc["chronicle"] if "from" in e]
    assert len(t.items) >= 300 and len(zw.houses(t.doc)) == len(t.items) and len(splits) >= 3
    shown = sound(t)
    m = shown["composition"]["measure"]
    assert m["lots"] == len(t.items) == shown["world"]["houses"] and m["ring_lots"] == t.doc["places"][ROOT]["lots"] + sum(
        t.doc["places"][lap]["lots"] for lap in laps_of(t.doc)[1:]) and shown["composition"]["streets"]["ring"] >= 1
    assert shown["composition"]["streets"]["total"] == len([p for p in t.doc["places"].values() if p["kind"] == "street" and "lane_of" not in p and p.get("tag")]) + 1


@pytest.mark.parametrize("seed", [0, 3, 5])
def test_random_worlds_keep_every_check_and_the_survivors_of_the_ring_stand(seed):
    problems, doc, steps, plan, tv = simulate_districts(seed)  # (the simulation also checks that a house that stays on the ring never changes lot)
    assert problems == [] and steps > 20 and any(e.get("from") == ROOT for e in doc["chronicle"])


def test_a_random_world_with_laps_stays_sound():
    problems, doc, steps, plan, tv = simulate_districts(7, max_houses=300, min_houses=60, trunk_min=40, batch_max=40)
    assert problems == [] and steps > 5


# -------------------------------------------------------------------------------------------------- laps ----
def test_a_ring_over_max_with_no_group_to_leave_opens_lap_2_back_to_back_when_no_line_is_open():
    t = Town(LAP_SPEC)
    g1, g2 = gates_of(t.plan), gates_of(t.plan, sides=True)
    assert g1 != g2 and t.plan["params"]["ring"]["radius"] == 8.5
    c1, c2 = capacity(8.5, g1), capacity(11.5, g2)
    filler = untagged(c1 + 12)
    t.one_by_one(filler[:c1], check=False)
    assert t.doc["places"][ROOT]["lots"] == c1 and "lanes" not in t.doc["places"][ROOT]  # every slot of lap 1 is taken: no lap yet
    (over,) = t.doc["chronicle"]
    assert (over["over"], over["count"], over["seq"], over["trigger"]) == (ROOT, 41, 41, "arrival") and t.doc["places"][ROOT]["over"] is True  # no group can reach min
    res = t.send([filler[c1]])  # one more house comes to the ring
    lap = t.doc["places"]["place:root:lap:2"]
    assert res["stats"]["laps"] == 1 and t.doc["places"][ROOT]["lanes"] == ["place:root:lap:2"] and t.doc["places"][ROOT]["lots"] == c1
    assert lap == {"kind": "street", "shape": "ring", "lane_of": ROOT, "ordinal": 2, "continued": True, "level": 1, "class": "大道", "label": "Knowledge",
                   "address": ["Knowledge"], "parent": ROOT, "lots": 1, "reserved": 0, "road": "road:place:root:lap:2",
                   "ring": {"lap": 2, "radius": 11.5, "slots": c2, "gaps": g2}}
    assert lap["ring"]["radius"] == 8.5 + 3.0  # no line is open: the laps stand back to back (R1 + BAND): the span of lap 2 starts where the span of lap 1 ends
    assert t.doc["lines"] == {} and t.doc["places"][ROOT]["ring"]["gaps"] == g1  # lap 1 keeps G1; the lap beyond has G2 (a side line's spoke can cross it)
    road = t.doc["roads"]["road:place:root:lap:2"]
    assert road == {"street": "place:root:lap:2", "kind": "ring", "class": "大道", "parent": None, "at": 0.0, "length": round(2 * math.pi * 11.5, 3), "radius": 11.5,
                    "points": road["points"]} and len(road["points"]) == 73 and road["points"][0] == road["points"][-1] == [0.0, -11.5]
    first = on_ring(t.doc)[c1]
    (x, z), _facing = slot_cell(11.5, g2, 0)
    assert (first["parent"], first["slot"], first["street"]) == ("place:root:lap:2", 0, ROOT) and (first["position"]["x"], first["position"]["z"]) == (round(x, 3), round(z, 3))
    assert math.hypot(first["position"]["x"], first["position"]["z"]) == pytest.approx(10.5, abs=2e-3)  # the inner row of lap 2, one cell inside its lane
    t.one_by_one(filler[c1 + 1:], check=False)  # lap 2 fills in turn, lap 1 stays as it was
    assert t.doc["places"]["place:root:lap:2"]["lots"] == 12 and t.doc["places"][ROOT]["lots"] == c1 and len(t.doc["chronicle"]) == 1  # (the ring is over once: one entry)
    assert [p["slot"] for p in on_ring(t.doc) if p["parent"] == "place:root:lap:2"] == fill_order_of(c2)[:12]  # the same rule on every lap: its first twelve in fill order
    shown = sound(t)  # ring_lots counts every lap; the ring is one street, its laps are continuations
    assert shown["composition"]["measure"]["ring_lots"] == c1 + 12 == shown["composition"]["measure"]["lots"]
    assert shown["composition"]["streets"]["total"] == 1 and shown["composition"]["streets"]["continuations"] == 1 and shown["composition"]["streets"]["ring"] == 2
    assert shown["places"][ROOT]["lanes"] == ["place:root:lap:2"] and shown["composition"]["measure"]["streets_by_class"] == {"大道": 1, "路": 0, "巷": 0, "弄": 0}


def test_with_lines_open_the_new_lap_lies_beyond_everything_that_stands_and_later_ribs_skip_it():
    t = Town(LAP_SPEC)
    g1 = gates_of(t.plan)
    c1 = capacity(8.5, g1)
    filler = untagged(c1 + 40)
    t.one_by_one(by_tag(t.items, "a1")[:10] + filler[:31])  # 10 houses of med first: the 41st house (the 31st filler) makes them leave and opens the line med
    assert [e["to"] for e in t.doc["chronicle"] if "from" in e] == [tag_street("med")] and set(t.doc["lines"]) == {tag_street("med")}
    f = frontier(t.doc["lines"][tag_street("med")])
    assert f == 13.0 == 11.5 + 1.5  # its first band is at R1 + 3: the line stands as far as the outer edge of that band
    t.one_by_one(filler[31:], check=False)  # the holes the group left are taken first (lowest free slot of the lowest lap), then lap 1 is full, then lap 2 opens
    lap = t.doc["places"]["place:root:lap:2"]
    assert t.doc["places"][ROOT]["lots"] == c1 and lap["lots"] == 40 and laps_of(t.doc) == [ROOT, "place:root:lap:2"]  # (c1 + 40 houses with no topic: 40 on lap 2)
    radius = lap["ring"]["radius"]
    assert radius == ceil3(max(8.5 + 3.0, f + 1.5)) == 14.5 and radius > 8.5 + 3.0  # beyond everything: the span of the lap starts where the line ends
    assert radius - 1.5 >= f - 1e-9
    assert lap["ring"]["gaps"] == gates_of(t.plan, sides=True)
    t.check()
    t.one_by_one(by_tag(t.items, "a2")[:20] + by_tag(t.items, "a1")[10:20])  # the line goes on growing: nothing it builds later lies across the lap
    assert t.count(tag_street("med")) == 40
    line = t.doc["lines"][tag_street("med")]
    assert not [(lo, hi) for lo, hi in [(b["s"] - 1.5, b["s"] + 1.5) for b in line["bands"]] + [tuple(sp) for sp in line["spokes"]]
                if lo < radius + 1.5 - 1e-9 and hi > radius - 1.5 + 1e-9]
    assert checks.registry_problems(t.doc) == []
    sound(t)


def test_a_line_that_opens_after_a_lap_skips_it_and_its_branch_circle_clears_it():
    c1 = capacity(8.5, gates_of(Town(LAP_SPEC).plan))

    def run(with_lap):
        t = Town(LAP_SPEC)
        t.one_by_one(untagged(c1 + 12 if with_lap else 41), check=False)  # (41: the ring is over max, so a road can open; c1 + 12: lap 2 stands too)
        t.one_by_one(by_tag(t.items, "pub")[:10] + by_tag(t.items, "a1")[:10] + by_tag(t.items, "h1")[:10])
        return t

    plain, lapped = run(False), run(True)
    assert "lanes" not in plain.doc["places"][ROOT] and lapped.doc["places"][ROOT]["lanes"] == ["place:root:lap:2"]
    lap_lo, lap_hi = 11.5 - 1.5, 11.5 + 1.5  # the span of lap 2: (10, 13)
    # a spoke rib starts at R1 + 1.5 = 10 where there is no lap, and at the upper end of the span of the lap where there is one
    assert plain.doc["lines"][tag_street("pub")]["spokes"][0][0] == 10.0 and lapped.doc["lines"][tag_street("pub")]["spokes"][0][0] == lap_hi == 13.0
    # the first band is at R1 + 3 = 11.5 where there is no lap, and beyond the lap where there is one: its span starts at 13
    assert [b["s"] for b in plain.doc["lines"][tag_street("med")]["bands"]] == [11.5] and [b["s"] for b in lapped.doc["lines"][tag_street("med")]["bands"]] == [14.5]
    # the branch circle of the ring-1 member with a side child is at frontier + 1 = R1 + 2.5 = 11, its clearance (10, 12); it meets the lap, so it moves to 13 + 1
    (m_plain,), (m_lapped,) = ([m for m in x.doc["lines"][tag_street("top")]["members"]] for x in (plain, lapped))
    assert m_plain["place"] == m_lapped["place"] == tag_street("top") and m_plain["s0"] == m_lapped["s0"] == 9.0
    assert m_plain["r1"] == 11.0 == 8.5 + 0.5 + 1.0 + 1.0 and m_lapped["r1"] == lap_hi + 1.0 == 14.0
    assert lapped.doc["roads"]["road:" + tag_street("top")]["s_end"] >= 14.0 and plain.doc["roads"]["road:" + tag_street("top")]["s_end"] >= 11.0
    for t in (plain, lapped):  # every span of every line stands clear of the lap (the check of the registry), and the roads cross the lap only at its gates
        assert checks.registry_problems(t.doc) == [] and checks.crossings(t.doc) == []
    spans = sorted([(b["s"] - 1.5, b["s"] + 1.5) for line in lapped.doc["lines"].values() for b in line["bands"]]
                   + [tuple(sp) for line in lapped.doc["lines"].values() for sp in line["spokes"]]
                   + [(m["r1"] - 1.0, m["r1"] + 1.0) for line in lapped.doc["lines"].values() for m in line["members"] if m["r1"] is not None])
    assert spans and not [s for s in spans if s[0] < lap_hi - 1e-9 and s[1] > lap_lo + 1e-9]  # no span meets (10, 13)
    sound(lapped)


def test_an_avenue_band_opens_beyond_the_lap_when_the_ring_is_already_in_lap_2():
    spec = {"med": T(0, a1=T(12), a2=T(12)), "pub": T(14)}
    t = Town(spec)
    c1 = capacity(8.5, gates_of(t.plan))
    t.one_by_one(untagged(c1 + 12), check=False)  # lap 2 stands, back to back: its span is (10, 13)
    assert t.doc["places"]["place:root:lap:2"]["ring"]["radius"] == 11.5
    t.one_by_one(by_tag(t.items, "a1")[:10])  # the group of med reaches min: the road opens; its first band wants 11.5 (R1 + 3), where the lap is
    line = t.doc["lines"][tag_street("med")]
    assert [b["s"] for b in line["bands"]] == [14.5] and line["members"][0]["s0"] == 9.0  # the first band beyond the lap: 13 + 1.5
    assert t.doc["roads"]["road:" + tag_street("med") + ":lane"]["radius"] == 14.5
    without = Town(spec)
    without.one_by_one(untagged(41), check=False)
    without.one_by_one(by_tag(without.items, "a1")[:10])
    assert [b["s"] for b in without.doc["lines"][tag_street("med")]["bands"]] == [11.5]  # (no lap: the band is where it always was)


def test_a_lap_the_houses_left_stays_in_the_world_and_takes_the_next_houses_before_a_new_lap_opens():
    t = Town(LAP_SPEC)
    c1 = capacity(8.5, gates_of(t.plan))
    filler = untagged(c1 + 14)
    t.one_by_one(filler[:c1], check=False)
    t.one_by_one(by_tag(t.items, "pub")[:10])  # lap 1 is full: the ten houses of pub open lap 2 and take its first slots, then leave as a group
    assert laps_of(t.doc) == [ROOT, "place:root:lap:2"] and t.doc["places"]["place:root:lap:2"]["lots"] == 0 and t.count(tag_street("pub")) == 10
    shown = t.shown()  # a lap with no house stands in the world, not in the document: the ring is one street, its laps none
    assert "place:root:lap:2" not in shown["places"] and "road:place:root:lap:2" not in shown["roads"] and "lanes" not in shown["places"][ROOT]
    assert shown["composition"]["streets"]["ring"] == 1 and shown["composition"]["streets"]["continuations"] == 0 and t.doc["places"][ROOT]["lots"] == c1
    t.one_by_one(filler[c1:])  # the next houses take lap 2 again: no third lap
    assert laps_of(t.doc) == [ROOT, "place:root:lap:2"] and t.doc["places"]["place:root:lap:2"]["lots"] == 14
    assert [p["slot"] for p in on_ring(t.doc) if p["parent"] == "place:root:lap:2"] == fill_order_of(t.doc["places"]["place:root:lap:2"]["ring"]["slots"])[:14]
    assert "place:root:lap:2" in t.shown()["places"] and t.shown()["composition"]["streets"]["ring"] == 2


def test_laps_open_one_after_the_other_each_beyond_the_one_before_and_only_when_the_laps_before_it_are_full():
    t = Town(LAP_SPEC)
    g1, g2 = gates_of(t.plan), gates_of(t.plan, sides=True)
    t.one_by_one(untagged(capacity(8.5, g1) + capacity(11.5, g2) + 10), check=False)
    laps = laps_of(t.doc)
    assert laps == [ROOT, "place:root:lap:2", "place:root:lap:3"]
    radii = [t.doc["places"][lap]["ring"]["radius"] for lap in laps]
    assert radii == [8.5, 11.5, 14.5]  # back to back while no line is open: R1 + 3 each
    assert [t.doc["places"][lap]["ring"]["lap"] for lap in laps] == [1, 2, 3] and t.doc["places"]["place:root:lap:3"]["ring"]["gaps"] == g2
    assert [t.doc["places"][lap]["lots"] for lap in laps] == [capacity(8.5, g1), capacity(11.5, g2), 10]  # a lap opens only when the laps before it are full
    assert t.doc["places"][ROOT]["lanes"] == laps[1:] and sorted(r for r, rec in t.doc["roads"].items() if rec["kind"] == "ring") == sorted(f"road:{lap}" for lap in laps)
    t.check()


def test_the_measure_of_waste_lets_a_lap_open_when_the_laps_before_it_are_full_and_finds_one_opened_over_free_slots():
    """The measure of waste (`support.land_waste`), its laps: a lap opens only when the houses the step put on the ring filled every free slot of the laps that stood.
    The engine opens lap 2 with the house after the last free slot of lap 1: no waste. The control: the same step read against a lap 1 with two more slots than it
    has (two of them free) is a lap opened over free slots."""
    t = Town(LAP_SPEC)
    c1 = capacity(8.5, gates_of(t.plan))
    filler = untagged(c1 + 1)
    t.one_by_one(filler[:c1], check=False)
    before = t.doc
    t.send(filler[c1:])
    assert laps_of(t.doc) == [ROOT, "place:root:lap:2"] and land_waste(before, t.doc, 40) == []
    wide = copy.deepcopy(before)
    wide["places"][ROOT]["ring"]["slots"] += 2  # (lap 1 as if it had two free slots when lap 2 opened)
    assert land_waste(wide, t.doc, 40) == [("lap", "place:root:lap:2", "opened with 2 free slots on the laps before it, 1 house(s) came to the ring")]


def test_the_measure_of_waste_counts_the_houses_that_came_to_the_ring_and_left_it_again_in_the_same_call():
    """A call that needs lap 2 and then splits from the ring. The ring holds 100 houses with no topic (lap 1 is full); then the ten houses of a come in one call: nine of them
    fill the ring over lap 1 and open lap 2, the tenth makes the group of `min` and all ten leave for road a. At the end of the call lap 2 is empty and no house of the call stands
    on the ring, but ten came to it: the lap was not opened early. The control: against a lap 1 with twelve more slots than it has (twelve of them free), ten houses are too few."""
    t = Town({"a": T(10), "b": T(1)})
    c1 = capacity(8.5, gates_of(t.plan))
    assert c1 == 100
    t.one_by_one(untagged(c1), check=False)
    before = t.doc
    t.send(t.tagged("a"))
    assert laps_of(t.doc) == [ROOT, "place:root:lap:2"] and t.doc["places"]["place:root:lap:2"]["lots"] == 0 and t.count(tag_street("a")) == 10
    assert [(e["from"], e["to"], len(e["houses"])) for e in t.doc["chronicle"][len(before["chronicle"]):]] == [(ROOT, tag_street("a"), 10)]
    assert land_waste(before, t.doc, 40) == []
    wide = copy.deepcopy(before)
    wide["places"][ROOT]["ring"]["slots"] += 12  # (lap 1 as if it had twelve free slots when lap 2 opened)
    assert land_waste(wide, t.doc, 40) == [("lap", "place:root:lap:2", "opened with 12 free slots on the laps before it, 10 house(s) came to the ring")]


# -------------------------------------------------------------------------------------------------- walks ----
def test_the_walk_to_a_ring_house_goes_out_through_the_nearest_gate_and_along_the_lane():
    tree, items, plan, doc = world_of(LAP_SPEC)
    g1, g2 = gates_of(plan), gates_of(plan, sides=True)  # [4.115, 101.83, 262.285] and the side gate 60.745
    c1, c2 = capacity(8.5, g1), capacity(11.5, g2)
    houses = untagged(c := c1 + c2)
    doc = zw.apply_delta(doc, zw.assign(plan, TreeView(tree), doc, houses[:2])["delta"])
    walks = lay.lot_door_walks(document.world_layout(doc, with_coast=False))
    # the gate 4.115 cuts the lane from u = 8.5 * radians(4.115) - 0.5 = 0.1105 to 1.1105, so the first cell starts at 1.1105 and its centre is u = 1.6105: one cell along the
    # lane from the axis of the gate. Slot 0 stands in it: the walk is out to the lane, 8.5, and one cell along it, 1.0, the nearest gate of G1 being that one
    assert checks.free_cells(8.5, g1)[0] == pytest.approx(8.5 * math.radians(4.115) + 1.0)
    assert walks[houses[0]["id"]] == pytest.approx(8.5 + 1.0, abs=3e-3)
    # the second house takes the slot half a circle round (fill order): its walk is out to the lane and along it to the nearest gate of G1, found from the independent cells
    second = fill_order_of(c1)[1]
    theta = math.degrees(checks.free_cells(8.5, g1)[second // 2] / 8.5)
    d = min(abs((theta - g + 180.0) % 360.0 - 180.0) for g in g1)
    assert doc["places"][lay.article_place(houses[1]["id"])]["slot"] == second and walks[houses[1]["id"]] == pytest.approx(8.5 + 8.5 * math.radians(d), abs=3e-3)
    # a house on lap 2 (R2 = 11.5, no line is open) next to the side gate 60.745 of G2 only: the walk counts the gates of G1 (the gates by which the plaza reaches the
    # ring), not the gates of the lap
    doc = zw.apply_delta(doc, zw.assign(plan, TreeView(tree), doc, houses[2:c])["delta"])  # (both laps are full now: every cell of lap 2 has its houses)
    cells2 = checks.free_cells(11.5, g2)
    k = min(range(len(cells2)), key=lambda i: abs(math.degrees(cells2[i] / 11.5) - 60.745))
    (house,) = [p for p in on_ring(doc) if p["parent"] == "place:root:lap:2" and p["slot"] == 2 * k]
    theta = math.degrees(cells2[k] / 11.5)
    d_g1 = min(abs((theta - g + 180.0) % 360.0 - 180.0) for g in g1)
    d_g2 = min(abs((theta - g + 180.0) % 360.0 - 180.0) for g in g2)
    assert d_g2 < 5.0 and d_g1 - d_g2 > 10.0  # (the cell stands next to the gate that only the laps have: G2 would give another walk, by more than 2 cells)
    shown = document.world_layout(doc, with_coast=False)
    assert lay.lot_door_walks(shown)[house["article"]] == pytest.approx(11.5 + 11.5 * math.radians(d_g1), abs=3e-3)
    m, walks = shown["composition"]["measure"], lay.lot_door_walks(shown)
    assert m["walk_longest"] == round(max(walks.values()), 1) and m["walk_mean"] == round(sum(walks.values()) / len(walks), 1) and m["ring_lots"] == c
    # without any gate the angle is the one from north
    bare = {"places": {"p": {"kind": "street", "shape": "ring", "ring": {"lap": 1, "radius": 8.5, "slots": 106, "gaps": []}},
                       "l": {"kind": "lot", "article": "x", "parent": "p", "position": {"x": 8.5, "z": 0.0}}}, "roads": {}, "centre": {"radius": 6.0}}
    assert lay.lot_door_walks(bare)["x"] == pytest.approx(8.5 + 8.5 * math.pi / 2)  # a house due east: a quarter turn from north


def test_a_road_starts_at_its_own_s0_a_ring_road_at_its_radius_and_any_other_at_the_plaza_rim():
    layout = {"centre": {"radius": 6.0}, "roads": {"s": {"parent": None, "kind": "spoke", "s0": 9.0, "at": 0}, "r": {"parent": None, "kind": "ring", "radius": 11.5, "at": 0},
                                                    "x": {"parent": None, "kind": "lane", "at": 0}, "c": {"parent": "s", "kind": "lane", "at": 2.5}}}
    assert lay.road_starts(layout) == {"s": 9.0, "r": 11.5, "x": 6.0, "c": 11.5}


# ------------------------------------------------------------------------------------------------ same bytes ----
def test_the_same_inputs_give_the_same_bytes_twice_and_a_stored_world_gives_the_same_answer():
    tree, items = make_tree(LAP_SPEC)
    items = items[:60] + untagged(200)
    a = bibliopolis.render(bibliopolis.build_city({"items": items}, tree, mode="grow"))
    assert a == bibliopolis.render(bibliopolis.build_city({"items": items}, tree, mode="grow"))
    plan = plan_mod.build_plan(TreeView(tree), items, trunk_min=20)
    doc = zw.new_world(plan)
    stored = json.loads(json.dumps(doc))
    res = zw.assign(plan, TreeView(tree), doc, items[:5], event_id=1)
    again = zw.assign(json.loads(json.dumps(plan)), TreeView(tree), stored, items[:5], event_id=1)
    assert json.dumps(res["delta"], sort_keys=True) == json.dumps(again["delta"], sort_keys=True)
    one, two = bibliopolis.build_city({"items": items}, tree, first=100), bibliopolis.build_city({"items": items}, tree)
    assert one["world"]["chronicle"] == [e for e in two["world"]["chronicle"] if e["seq"] <= 100] and one["places"][ROOT]["ring"] == two["places"][ROOT]["ring"]


# ----------------------------------------------------------------------------------------------- the fill order ----
@pytest.mark.parametrize("slots", [1, 2, 3, 5, 8, 50, 58, 64, 90, 106, 289])
def test_the_fill_order_is_the_bit_reversal_permutation_of_the_slots_with_the_numbers_of_slots_or_more_left_out(slots):
    order = ring.ring_fill_order(slots)
    assert list(order) == fill_order_of(slots) and sorted(order) == list(range(slots))  # a permutation of the slots, found two ways
    if slots >= 4 and slots & (slots - 1) == 0:
        assert order[:4] == (0, slots // 2, slots // 4, 3 * slots // 4)  # the north, the south, the quarters


def test_the_engine_and_the_independent_statement_give_the_same_fill_order_for_every_lap_size_up_to_400_slots():
    assert [n for n in range(1, 401) if list(ring.ring_fill_order(n)) != fill_order_of(n)] == []
    assert ring.ring_fill_order(58)[:12] == (0, 29, 14, 43, 7, 36, 21, 50, 3, 32, 18, 47)  # the lap of 58 slots: the second house half way round, at 29
    assert ring.ring_fill_order(122)[:9] == (0, 61, 30, 91, 15, 76, 45, 106, 7)
    for slots, want in ((1, [0]), (2, [0, 1]), (3, [0, 1, 2]), (4, [0, 2, 1, 3]), (5, [0, 2, 1, 3, 4]), (6, [0, 3, 1, 4, 2, 5]), (7, [0, 3, 1, 5, 4, 2, 6])):
        assert list(ring.ring_fill_order(slots)) == want  # by hand: floor(j * slots / 8) for the 3-bit numbers read backwards, 0 4 2 6 1 5 3 7, a slot counted when it first comes up
    for m in range(1, 9):  # a power of two: the first 2^j houses stand 2^(m-j) slots apart, as in the bit-reversal order
        for j in range(m + 1):
            assert sorted(ring.ring_fill_order(1 << m)[:1 << j]) == [i << (m - j) for i in range(1 << j)]
    for slots in range(2, 400):  # the second house stands half way round whatever the number of slots
        assert ring.ring_fill_order(slots)[1] == slots // 2
        assert sorted(ring.ring_fill_order(slots)) == list(range(slots))  # every slot once


def test_the_first_2_to_the_i_slots_of_the_fill_order_cut_the_lap_into_stretches_of_floor_or_ceil_of_n_over_2_to_the_i():
    for slots in range(1, 401):
        order = ring.ring_fill_order(slots)
        for i in range(slots.bit_length()):  # 2^i <= slots
            taken = sorted(order[:1 << i])
            stretches = [b - a for a, b in zip(taken, taken[1:])] + [slots - taken[-1] + taken[0]]  # round the lap, the last back to the first
            assert set(stretches) <= {slots // (1 << i), -(-slots // (1 << i))}, (slots, i)


def prefix_gaps(taken, slots):
    """For every prefix k of `taken` (distinct slots of a lap of `slots` slots, in the order the houses took them): the largest cyclic gap, in slots, between the slots of the
    first k, a whole lap for one. The gaps are kept in a max-heap; a gap that a new slot has split is dropped when it comes to the top."""
    points, after, heap, out = [], {}, [], []
    for x in taken:
        if not points:
            points, after, heap = [x], {x: x}, [(-slots, x, x)]
        else:
            i = bisect.bisect_left(points, x)
            a, b = points[i - 1], points[i % len(points)]
            points.insert(i, x)
            after[a], after[x] = x, b
            for lo, hi in ((a, x), (x, b)):
                heapq.heappush(heap, (-((hi - lo) % slots or slots), lo, hi))
        while after[heap[0][1]] != heap[0][2]:
            heapq.heappop(heap)
        out.append(-heap[0][0])
    return out


def brute_gaps(taken, slots):
    """The same by a plain sort at every prefix (what `prefix_gaps` is checked against)."""
    out = []
    for k in range(1, len(taken) + 1):
        have = sorted(taken[:k])
        out.append(max([b - a for a, b in zip(have, have[1:])] + [have[0] + slots - have[-1]]))
    return out


def test_the_gap_checker_agrees_with_a_plain_sort_at_every_prefix_whatever_the_order():
    rng = random.Random(11)
    for slots in (1, 2, 7, 58, 90):
        shuffled = list(range(slots))
        rng.shuffle(shuffled)
        for taken in (fill_order_of(slots), list(range(slots)), shuffled):
            assert prefix_gaps(taken, slots) == brute_gaps(taken, slots), (slots, taken[:6])
    assert prefix_gaps([0, 2], 58) == [58, 56] and prefix_gaps([0, 1], 58) == [58, 57]  # by hand: one slot leaves the whole lap, two neighbours leave all but one


def test_every_prefix_of_the_fill_order_is_spread_round_the_lap_no_gap_is_over_twice_the_even_spacing_and_a_slot_and_the_clockwise_fill_is_not():
    """After k houses, the largest gap between neighbours round a lap of n slots is at most 2 * n / k + 1 slots, for every k and every lap size up to 400 slots (a table of what
    holds, not a proof; in cells, the gates left out, at most n / k + 1). The planted fault, the clockwise fill, breaks it at once: after half the houses all stand in one half of the ring."""
    for slots in range(1, 401):
        gaps = prefix_gaps(fill_order_of(slots), slots)
        assert [k for k, g in enumerate(gaps, start=1) if g * k > 2 * slots + k] == [], slots
    for slots in (58, 90, 122, 156):
        bad = prefix_gaps(list(range(slots)), slots)
        assert any(g * k > 2 * slots + k for k, g in enumerate(bad, start=1)), slots
        assert bad[slots // 2 - 1] == slots - slots // 2 + 1  # after half the houses: all the other half and one slot is one gap


def test_the_houses_the_engine_puts_on_each_lap_take_the_fill_order_and_every_prefix_is_spread():
    t = Town(LAP_SPEC)
    g1, g2 = gates_of(t.plan), gates_of(t.plan, sides=True)
    c1, c2 = capacity(8.5, g1), capacity(11.5, g2)
    t.one_by_one(untagged(c1 + c2), check=False)  # lap 1 fills, lap 2 opens and fills
    assert laps_of(t.doc) == [ROOT, "place:root:lap:2"]
    for lap, slots in ((ROOT, c1), ("place:root:lap:2", c2)):
        taken = [p["slot"] for p in on_ring(t.doc) if p["parent"] == lap]  # the slots in the order the houses arrived
        assert taken == fill_order_of(slots) and len(taken) == slots  # the fill order, the whole lap
        assert all(g * k <= 2 * slots + k for k, g in enumerate(prefix_gaps(taken, slots), start=1)), lap  # every prefix of what the engine did is spread
    t.check()


def ring_cells_of(doc):
    """{house id: (index of its lap from 0, slot)} of the houses on the ring, and the slots of each lap that stands."""
    laps = laps_of(doc)
    return {p["article"]: (laps.index(p["parent"]), p["slot"]) for p in on_ring(doc)}, [doc["places"][lap]["ring"]["slots"] for lap in laps]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_each_house_that_comes_to_the_ring_takes_the_first_free_slot_in_fill_order_of_the_lowest_lap_that_has_one(seed):
    """Stated apart from the engine (`first_free` of tests/support.py): after each arrival, a house that stands on the ring stands at the first free slot in fill order of the lowest lap that has
    one, the houses that stood on the ring before and stand on it still taking no other lot (a split frees the lots of the group that leaves and nothing else)."""
    t = Town(LAP_SPEC)
    rng = random.Random(seed)
    arrivals = untagged(260) + by_tag(t.items, "a1", "a2")[:50] + by_tag(t.items, "pub") + by_tag(t.items, "h1", "h2", "s1", "s2")
    rng.shuffle(arrivals)
    checked = opened_laps = 0
    for a in arrivals[:300]:
        before, _ = ring_cells_of(t.doc)
        laps_before = len(laps_of(t.doc))
        t.send([a], check=False)
        after, laps = ring_cells_of(t.doc)
        assert all(after[h] == cell for h, cell in before.items() if h in after), "a house that stayed on the ring changed lot"
        if a["id"] in after:
            taken = {cell for h, cell in after.items() if h != a["id"]}
            want = first_free(laps[:laps_before] if laps_before else laps, taken)
            assert after[a["id"]] == want, (a["id"], after[a["id"]], want)
            checked += 1
            opened_laps += want[0] >= laps_before
    assert checked > 200 and opened_laps >= 1 and any(e.get("from") == ROOT for e in t.doc["chronicle"])  # (the run has laps and splits from the ring)
    t.check()


# --------------------------------------------------------------------------------------- the polyline of the road ----
@pytest.mark.parametrize("radius", [8.5, 11.5, 20.0, 52.5, 52.6, 53.5, 100.0, 200.0, 500.0, 800.0])
def test_the_polyline_of_a_ring_road_has_the_least_multiple_of_72_chords_that_keeps_every_chord_within_a_twentieth_of_a_cell_of_its_circle(radius):
    points = ring.ring_points(radius)
    n = len(points) - 1
    assert n % 72 == 0 and len(points) == checks.chord_points(radius) == ring.ring_chords(radius) + 1  # (the count is found two ways)
    assert points[0] == points[-1] == [0.0, -radius] and all(abs(math.hypot(x, z) - radius) < 2e-3 for x, z in points)
    assert radius * (1 - math.cos(math.pi / n)) <= 0.05  # the sagitta of a chord
    assert n == 72 or radius * (1 - math.cos(math.pi / (n - 72))) > 0.05  # and with 72 chords fewer it would not be
    for (x1, z1), (x2, z2) in zip(points, points[1:]):  # the middle of each chord lies at most 0.05 inside the lane (the points are rounded to 3 decimals)
        assert radius - math.hypot((x1 + x2) / 2, (z1 + z2) / 2) <= 0.05 + 2e-3


def test_up_to_a_radius_of_52_5_the_polyline_is_the_73_points_of_every_five_degrees_byte_for_byte_and_it_is_73_at_the_ends_and_289_at_800():
    for radius in (8.5, 11.5, 20.0, 40.0, 52.5):
        assert ring.ring_points(radius) == lay.arc_points(radius, 0.0, 360.0) and len(ring.ring_points(radius)) == 73
    assert [len(ring.ring_points(r)) for r in (52.5, 52.6, 800.0)] == [73, 145, 289]
    road = ring.ring_road_record(2, 800.0)
    assert road["points"] == ring.ring_points(800.0) and road["radius"] == 800.0 and road["kind"] == "ring" and abs(road["length"] - 2 * math.pi * 800.0) < 1e-3  # (the length is written to three decimals)


def test_a_far_ring_of_a_world_built_by_hand_carries_the_longer_polyline_and_the_check_is_red_with_the_73_points_of_old(monkeypatch):
    from hand_support import Hand

    h = Hand({"max": 10000, "min": 3, "auto": False})
    h.add(12)
    road = h.state.doc["roads"]["road:place:root"]
    assert h.state.plan["params"]["ring"]["radius"] == 799.5 and len(road["points"]) == 289
    assert checks.ring_problems(h.state.city()) == [] and checks.all_problems(h.state.doc) == {}
    monkeypatch.setattr(ring, "ring_chords", lambda radius: 72)
    old = Hand({"max": 10000, "min": 3, "auto": False})
    old.add(12)
    assert len(old.state.doc["roads"]["road:place:root"]["points"]) == 73
    assert any("closed circle" in why for _, why in checks.ring_problems(old.state.city()))
