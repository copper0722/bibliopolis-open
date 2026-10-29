"""A full road grows its one rib in place, and what lies beyond it moves outward (bibliopolis.world: `grow_rib`, `lay_line`; docs/engine.md, rule 8).

The rule: a rib with no empty lot gains `max(need - held, 1)` lots at its end and the line is laid again from it outward. The ten invariants of that, each read after EVERY
arrival of random worlds (one house to a call) and after every event of random worlds built by hand, and each with a control that shows the instrument can fail:

   1 address    every house keeps its road and its topic unless a split or a move put it again
   2 lot        every house keeps its rib and its slot unless a split or a move put it again
   3 one stretch  every road but the ring has one rib; no street continues another but the laps of the ring road
   4 row, side  a rib keeps its mode, band and side; a house keeps its row (inner, outer) and its side of the axis
   5 geometry   the spans of a line are disjoint and clear of every lap, every lot lies in its wedge (the geometry checks of tests/checks.py)
   6 order      the radial order of the spans of a line and the order of the ribs along a side of a band never change
   7 monotone   nothing moves inward, no rib loses lots
   8 idempotence  a fresh World lays every line from its log and writes nothing
   9 waste      a rib grows only when it has no empty lot, by max(need - held, 1), and ends with at most rib_need(n) lots; no lap opens over empty slots
  10 determinism  the same bytes for the same input, a call leaves the world it reads as it was, a world folded from its deltas is the world

then the effects on concrete worlds, and the planted faults: a growth that skips the laying, a laying in the order the ribs opened in, a radius rounded another way, a
ghost dropped when a road moves, a laying that forgets where the line has got to, a laying that forgets the laps. Each turns a check red.
"""

import collections
import copy
import inspect
import json
import math
import random
import textwrap

import checks
import pytest
from hand_support import Hand, houses, stability_violations
from support import (T, Town, art, as_text, district_problems, grow_by, land_waste, lay_problems, may_change_after, random_world, row_and_side, sample, sound,
                     step_problems, tag_street)

from bibliopolis import city
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.hand import HandWorld
from bibliopolis.tree import TreeView

SMALL = dict(max_houses=12, min_houses=4)
CONFIGS = [{}, {"max_houses": 8, "min_houses": 3, "trunk_min": 10}, {"mode": "mirror"}]


# --------------------------------------------------------------------------------------------- the instruments ----
def walk(seed, *, limit=None, max_houses=12, min_houses=4, trunk_min=40, mode="grow"):
    """A random world, one house to a call, in the order that `simulate_districts` shuffles them: yields (step, world before, world after, plan, tree view) for the first `limit`."""
    tree, items = random_world(seed)
    tv = TreeView(tree)
    plan = plan_mod.build_plan(tv, items, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    doc = zw.new_world(plan)
    seq = list(items)
    random.Random(seed * 7919 + 3).shuffle(seq)
    for step, a in enumerate(seq[:limit], 1):
        after = zw.apply_delta(doc, zw.assign(plan, tv, doc, [a], event_id=step)["delta"])
        yield step, doc, after, plan, tv
        doc = after


def effects(before, after):
    """What a step moved, counted: ribs that grew, ribs that shifted along their side of a band, bands, ribs along the spoke, members and branch circles that moved out, side lines
    that started farther out."""
    out = collections.Counter()
    for pid, p in before["places"].items():
        q = after["places"].get(pid)
        if p["kind"] == "street" and "rib" in p and q is not None:
            out["rib grew"] += q["rib"]["slots"] > p["rib"]["slots"]
            out["rib shifted"] += q["rib"]["x0"] > p["rib"]["x0"] + 1e-9
    for lid, line in before["lines"].items():
        later = after["lines"][lid]
        out["band moved out"] += sum(later["bands"][k]["s"] > b["s"] + 1e-9 for k, b in enumerate(line["bands"]))
        out["rib along the spoke moved"] += sum(later["spokes"][k][0] > sp[0] + 1e-9 for k, sp in enumerate(line["spokes"]))
        out["member moved out"] += sum(n["s0"] > m["s0"] + 1e-9 for m, n in zip(line["members"], later["members"]))
        out["circle moved out"] += sum(m["r1"] is not None and n["r1"] > m["r1"] + 1e-9 for m, n in zip(line["members"], later["members"]))
        out["side line moved out"] += line["parent"] is not None and later["members"][0]["s0"] > line["members"][0]["s0"] + 1e-9
    return out


def by_invariant(before, after, plan, tv):
    """Every check of the ten, run on one step: {invariant: what it found}."""
    found = collections.defaultdict(list)
    for n, what, detail in step_problems(before, after, may_change_after(plan, before, after)):
        found[n].append((what, detail))
    found[3] += district_problems(after, plan, tv)
    found[5] += [(name, f[:2]) for name, f in checks.all_problems(after).items()]
    found[8] += lay_problems(after, plan, tv)
    found[9] += land_waste(before, after, plan["params"]["districts"]["max"])
    return {n: v for n, v in found.items() if v}


@pytest.fixture(scope="module")
def walked():
    """Random worlds, one house to a call, every invariant read after every arrival: (config, seed, steps, what was found, what moved)."""
    out = []
    for kw, seed, limit in (({}, 0, 500), ({}, 3, 500), ({}, 7, 500), ({"max_houses": 8, "min_houses": 3, "trunk_min": 10}, 5, 500), ({"mode": "mirror"}, 1, 500)):
        found, moved, steps = {}, collections.Counter(), 0
        for step, before, after, plan, tv in walk(seed, limit=limit, **kw):
            steps += 1
            moved += effects(before, after)
            for n, what in by_invariant(before, after, plan, tv).items():
                found.setdefault(n, []).append((step, what[:2]))
        out.append((kw, seed, steps, found, moved))
    return out


# ------------------------------------------------------------------------------------------------ the ten ----
def test_after_every_arrival_of_random_worlds_none_of_the_ten_invariants_is_broken_and_the_worlds_grew_every_way_a_world_can(walked):
    moved = collections.Counter()
    for kw, seed, steps, found, effect in walked:
        assert steps >= 290 and found == {}, (kw, seed, steps, found)
        moved += effect
    for what in ("rib grew", "rib shifted", "band moved out", "rib along the spoke moved", "member moved out"):
        assert moved[what] >= 5, (what, dict(moved))
    assert moved["circle moved out"] >= 1 and moved["side line moved out"] >= 1, dict(moved)


def damaged(doc, change):
    out = copy.deepcopy(doc)
    change(out)
    return out


def a_world_with_growth():
    """(world before, world after, plan, tree view): the 11th house of road a, which grows its rib of 10 lots, with a road behind it on its side of the band."""
    t = scenario_wide()
    before = t.doc
    t.send([t.tagged("a")[10]], event_id=20)
    return before, t.doc, t.plan, t.tv


def test_invariant_1_a_house_keeps_its_road_and_its_topic_and_the_instrument_sees_one_that_does_not():
    before, after, plan, tv = a_world_with_growth()
    assert step_problems(before, after) == []
    house = next(p for p in after["places"].values() if p["kind"] == "lot" and p["street"] == tag_street("b"))
    other = damaged(after, lambda d: d["places"][lay.article_place(house["article"])].update(street=tag_street("c")))
    assert [n for n, *_ in step_problems(before, other)] == [1]
    other = damaged(after, lambda d: d["places"][lay.article_place(house["article"])].update(tag="c"))
    assert [n for n, *_ in step_problems(before, other)] == [1]
    assert step_problems(before, other, lambda lot, now: lot["article"] == house["article"]) == []  # (a house a split put again may change)


def test_invariant_2_a_house_keeps_its_rib_and_its_slot_and_the_instrument_sees_one_that_does_not():
    before, after, plan, tv = a_world_with_growth()
    house = next(p for p in after["places"].values() if p["kind"] == "lot" and p["street"] == tag_street("b"))
    other = damaged(after, lambda d: d["places"][lay.article_place(house["article"])].update(slot=house["slot"] + 1))
    assert [n for n, *_ in step_problems(before, other)] == [2]
    assert {(p["parent"], p["slot"]) for p in before["places"].values() if p["kind"] == "lot"} <= {(p["parent"], p["slot"]) for p in after["places"].values() if p["kind"] == "lot"}


def test_invariant_3_a_road_is_one_stretch_and_the_instrument_sees_a_road_that_continues_in_a_second_rib():
    before, after, plan, tv = a_world_with_growth()
    assert [p for p in district_problems(after, plan, tv) if "stretch" in p[1]] == []
    a = tag_street("a")

    def continued(d):
        d["places"]["place:lane:a:2"] = {**d["places"][a], "lane_of": a, "ordinal": 2, "continued": True}
    assert [p for p in district_problems(damaged(after, continued), plan, tv) if "stretch" in p[1]]

    def laned(d):
        d["places"][a]["lanes"] = ["place:lane:a:2"]
    assert [p for p in district_problems(damaged(after, laned), plan, tv) if "stretch" in p[1]]


def test_invariant_4_a_rib_keeps_its_mode_band_and_side_and_a_house_its_row_and_its_side_and_the_instrument_sees_each_change():
    before, after, plan, tv = a_world_with_growth()
    b = tag_street("b")
    for key, value in (("mode", "spoke"), ("band", 3), ("side", 1), ("trunk", "place:tag:z")):
        other = damaged(after, lambda d: d["places"][b]["rib"].update({key: value}))
        assert [n for n, what, _ in step_problems(before, other) if n == 4 and key in what], key
    house = next(p for p in after["places"].values() if p["kind"] == "lot" and p["street"] == b and p["slot"] == 1)  # slot 1: an outer lot
    assert row_and_side(after, house)[0] == "outer"
    lot = lay.article_place(house["article"])
    other = damaged(after, lambda d: d["places"][lot].update(position={"x": house["position"]["x"] * 0.5, "z": house["position"]["z"] * 0.5}))
    assert [n for n, what, _ in step_problems(before, other) if "row or its side" in what] == [4]


def test_invariant_5_the_spans_of_a_line_are_disjoint_and_clear_of_the_laps_and_the_instrument_sees_two_that_meet():
    before, after, plan, tv = a_world_with_growth()
    assert checks.all_problems(after) == {}
    line = next(iter(after["lines"]))

    def overlap(d):
        d["lines"][line]["bands"][0]["s"] += 1.0
        d["lines"][line]["spokes"].append([d["lines"][line]["bands"][0]["s"] - 1.0, d["lines"][line]["bands"][0]["s"] + 1.0])
    assert "registry_problems" in checks.all_problems(damaged(after, overlap))


def test_invariant_6_the_radial_order_of_the_spans_and_the_order_along_a_side_never_change_and_the_instrument_sees_two_swapped():
    before, after, plan, tv = a_world_with_growth()
    assert not [p for p in step_problems(before, after) if p[0] == 6]
    a, b = tag_street("a"), tag_street("b")

    def reorder(d):  # a and the rib behind it on their side of the band change places along it
        d["roads"][d["places"][a]["road"]]["off"], d["roads"][d["places"][b]["road"]]["off"] = d["roads"][d["places"][b]["road"]]["off"], d["roads"][d["places"][a]["road"]]["off"]
    assert 6 in {n for n, *_ in step_problems(before, damaged(after, reorder))}
    narrow = scenario_narrow().doc  # a rib along the spoke, then the band of d, then the band of b and c

    def swap(d):  # the two bands change places
        bands = d["lines"]["place:tag:m"]["bands"]
        bands[0]["s"], bands[1]["s"] = bands[1]["s"], bands[0]["s"]
    assert 6 in {n for n, *_ in step_problems(narrow, damaged(narrow, swap))}


def test_invariant_7_nothing_moves_inward_and_no_rib_loses_lots_and_the_instrument_sees_each_that_does():
    before, after, plan, tv = a_world_with_growth()
    assert not [p for p in step_problems(before, after) if p[0] == 7]
    line, a = next(iter(after["lines"])), tag_street("a")
    for change in (lambda d: d["lines"][line]["bands"][0].update(s=d["lines"][line]["bands"][0]["s"] - 0.5),
                   lambda d: d["lines"][line]["bands"][0].update(used=[0.5, 0.5]),
                   lambda d: d["lines"][line]["members"][0].update(s0=d["lines"][line]["members"][0]["s0"] - 0.5),
                   lambda d: d["places"][a]["rib"].update(slots=d["places"][a]["rib"]["slots"] - 4),
                   lambda d: d["roads"][d["places"][a]["road"]].update(radius=d["roads"][d["places"][a]["road"]]["radius"] - 0.5)):
        assert 7 in {n for n, *_ in step_problems(before, damaged(after, change))}


def test_invariant_8_a_fresh_world_lays_every_line_from_its_log_and_writes_nothing_and_the_instrument_sees_a_record_that_differs():
    before, after, plan, tv = a_world_with_growth()
    assert lay_problems(after, plan, tv, full=True) == [] and lay_problems(before, plan, tv, full=True) == []
    b = tag_street("b")
    assert lay_problems(damaged(after, lambda d: d["places"][b]["rib"].update(x0=d["places"][b]["rib"]["x0"] - 1.0)), plan, tv)


def test_invariant_9_a_rib_grows_only_when_it_is_full_by_what_the_road_needs_and_the_measure_sees_a_rib_that_does_not():
    before, after, plan, tv = a_world_with_growth()
    a = tag_street("a")
    assert after["places"][a]["rib"]["slots"] - before["places"][a]["rib"]["slots"] == 2 and land_waste(before, after, 12) == []
    greedy = damaged(after, lambda d: d["places"][a]["rib"].update(slots=40))
    assert [w[0] for w in land_waste(before, greedy, 12)] == ["rib", "grow"]
    def without_a_house(doc):  # a house of a left its lot before the step, and the lot is empty
        doc = copy.deepcopy(doc)
        lot = doc["places"].pop(lay.article_place(lots_of(before, "a")[3]["article"]))
        doc["places"][a]["lots"] -= 1
        doc["places"][lay.reserved_place(doc["places"][a]["rib"]["block"], lot["slot"])] = {"kind": "reserved", "parent": a, "slot": lot["slot"]}
        return doc

    gap = land_waste(without_a_house(before), without_a_house(after), 12)  # the rib was full of 10 houses less one: it grew with an empty lot
    assert [w for w in gap if w[0] == "grow" and "with 1 empty" in w[2]]


def test_invariant_10_the_same_input_gives_the_same_bytes_a_call_leaves_the_world_it_reads_and_a_world_folded_from_its_deltas_is_the_world():
    tree, library = sample()
    plan, tv, world, items = city.build_world(library, tree)
    assert as_text(world) == as_text(city.build_world(library, tree)[2])  # the same bytes (in another process too: the test of the pictures)
    folded = zw.new_world(plan)
    for k, item in enumerate(items):  # one call to an arrival, the deltas folded one after the other
        frozen = json.dumps(folded, sort_keys=True) if k % 97 == 0 else None
        res = zw.assign(plan, tv, folded, [item])
        assert frozen is None or json.dumps(folded, sort_keys=True) == frozen  # the call did not touch the world it read
        folded = zw.apply_delta(folded, res["delta"])
    for entry in folded["chronicle"]:
        entry["at"] = items[entry["seq"] - 1]["added_at"]
    assert as_text(folded) == as_text(world)  # the world made of the 600 deltas is the world made by the one call that is `build_world`


# ------------------------------------------------------------------------------- what moves, on worlds one reads ----
def scenario_wide():
    """Road m of a wedge so wide that no band has to move out for the reach of its ribs: three roads on one band, b after a on one side of it, c on the other."""
    t = Town({"m": T(0, a=T(30), b=T(30), c=T(30)), "z": T(3)}, trunk_min=400, **SMALL)
    a, b, c = (t.tagged(x) for x in "abc")
    t.send(a[:5] + b[:4] + c[:4], event_id=1)
    t.send(b[4:9], event_id=2)
    t.send(c[4:13], event_id=3)
    t.send(a[5:10], event_id=4)
    return t


def rib_of(doc, key):
    return doc["places"][tag_street(key)]["rib"]


def lots_of(doc, key):
    return {p["slot"]: p for p in doc["places"].values() if p["kind"] == "lot" and p["street"] == tag_street(key)}


def test_the_rib_after_a_growing_rib_on_its_side_of_a_band_moves_along_the_band_by_what_the_rib_gained_and_nothing_else_moves():
    t = scenario_wide()
    a, b, c = (rib_of(t.doc, x) for x in "abc")
    assert (a["slots"], a["x0"], a["x1"], a["band"], a["side"]) == (10, 0.5, 5.5, 0, -1) and (b["x0"], b["x1"], b["side"], b["slots"]) == (6.5, 12.5, -1, 12)
    assert (c["x0"], c["x1"], c["side"], c["slots"], c["s"]) == (7.5, 17.5, 1, 20, 12.5) and t.doc["lines"]["place:tag:m"]["bands"][0]["used"] == [12.5, 17.5]
    before = t.doc
    t.send([t.tagged("a")[10]], event_id=5)  # the 11th house of a: its rib is full and gains 2 lots (need 12, held 10)
    after = t.doc
    a2, b2, c2 = (rib_of(after, x) for x in "abc")
    assert (a2["slots"], a2["x0"], a2["x1"]) == (12, 0.5, 6.5) and (b2["x0"], b2["x1"], b2["slots"]) == (7.5, 13.5, 12) and (c2["x0"], c2["x1"]) == (7.5, 17.5)
    assert after["lines"]["place:tag:m"]["bands"][0]["s"] == 12.5 == before["lines"]["place:tag:m"]["bands"][0]["s"] and after["lines"]["place:tag:m"]["bands"][0]["used"] == [13.5, 17.5]
    for slot, lot in lots_of(before, "a").items():  # the houses of a stand where they stood, and the 11th takes slot 10
        assert after["places"][lay.article_place(lot["article"])] == lot
    assert lots_of(after, "a")[10]["article"] == t.tagged("a")[10]["id"]
    for slot, lot in lots_of(before, "c").items():  # the road on the other side of the band does not move
        assert after["places"][lay.article_place(lot["article"])] == lot
    for slot, lot in lots_of(before, "b").items():  # the road behind a moves along the band by one cell: same radius, same slot, a bearing 1 / s radians farther from the axis
        now = after["places"][lay.article_place(lot["article"])]
        assert (now["parent"], now["slot"]) == (lot["parent"], lot["slot"]) and abs(math.hypot(*now["position"].values()) - math.hypot(*lot["position"].values())) < 2e-3
        axis = after["lines"]["place:tag:m"]["axis"]
        turn = lambda p: (math.degrees(math.atan2(p["position"]["x"], -p["position"]["z"])) - axis + 180.0) % 360.0 - 180.0  # noqa: E731
        assert abs(abs(turn(now)) - abs(turn(lot)) - math.degrees(1.0 / 12.5)) < 0.02
    assert row_and_side(before, lots_of(before, "b")[0]) == row_and_side(after, lots_of(after, "b")[0])
    assert [r for r in after["roads"].values() if r["kind"] == "lane" and r["street"] == tag_street("b")][0]["off"] == 6.5  # (it starts where a ended: 6.5)
    t.send([t.tagged("a")[11]], event_id=6)  # the 12th fits; the 13th: a is over (13 > max) and the rib gains 8 lots (need 20, held 12)
    t.send([t.tagged("a")[12]], event_id=7)
    a3, b3 = rib_of(t.doc, "a"), rib_of(t.doc, "b")
    assert (a3["slots"], a3["x1"], b3["x0"], b3["x1"]) == (20, 10.5, 11.5, 17.5) and t.doc["lines"]["place:tag:m"]["bands"][0]["used"] == [17.5, 17.5]


def scenario_narrow():
    """Road m of a wedge so narrow that a band reaches only far out: a and m itself lie along the spoke (a at 10, m after it), b and c on a band, d on a band inward of theirs."""
    spec = {"m": T(0, a=T(30), b=T(30), c=T(30), d=T(30)), **{f"z{i}": T(80) for i in range(15)}}
    t = Town(spec, trunk_min=400, **SMALL)
    a, b, c, d = (t.tagged(x) for x in "abcd")
    t.send(a[:5] + b[:4] + c[:4], event_id=1)
    t.send(b[4:9], event_id=2)
    t.send(c[4:13], event_id=3)
    t.send(d[:13], event_id=4)
    return t


def test_a_rib_along_the_spoke_that_grows_pushes_the_next_one_along_the_spoke_and_the_bands_beyond_stay():
    t = scenario_narrow()
    line_id, a = "place:tag:m", tag_street("a")
    line = t.doc["lines"][line_id]
    assert rib_of(t.doc, "a")["mode"] == "spoke" and line["spokes"] == [[10.0, 16.0], [16.0, 23.0]] and rib_of(t.doc, "a")["slots"] == 10
    second = next(pid for pid, p in t.doc["places"].items() if p["kind"] == "street" and "rib" in p and p["rib"]["mode"] == "spoke" and pid != a)
    assert t.doc["places"][second]["rib"]["x0"] == 16.0
    bands = [(b["s"], list(b["used"])) for b in line["bands"]]
    for k in (5, 6, 7, 8, 9):  # up to 10 houses: the rib is full
        t.send([t.tagged("a")[k]], event_id=10 + k)
    assert t.doc["lines"][line_id]["spokes"] == [[10.0, 16.0], [16.0, 23.0]]
    t.send([t.tagged("a")[10]], event_id=20)  # the 11th: 2 lots more, one cell
    assert t.doc["lines"][line_id]["spokes"] == [[10.0, 17.0], [17.0, 24.0]] and t.doc["places"][second]["rib"]["x0"] == 17.0
    for k in (11, 12):  # the 13th: a is over, and gains 8 lots
        t.send([t.tagged("a")[k]], event_id=30 + k)
    assert rib_of(t.doc, "a")["slots"] == 20 and t.doc["lines"][line_id]["spokes"] == [[10.0, 21.0], [21.0, 28.0]] and t.doc["places"][second]["rib"]["x0"] == 21.0
    assert [(b["s"], list(b["used"])) for b in t.doc["lines"][line_id]["bands"]] == bands  # the bands lie beyond: they stay


def test_a_band_that_has_to_reach_farther_moves_out_and_the_band_beyond_it_moves_with_it_flush_and_nothing_inward_moves():
    t = scenario_narrow()
    line_id = "place:tag:m"
    line = t.doc["lines"][line_id]
    assert [(b["s"], b["used"]) for b in line["bands"]] == [(42.139, [6.5, 10.5]), (39.139, [10.5, 0.5])]  # band 1, d's, lies INWARD of band 0, b's and c's: it opened later, in a gap
    before = t.doc
    d = t.tagged("d")
    for k in range(13, 21):  # the 21st house of d: its rib of 20 lots is full and gains 12 (d is over: need 32, held 20)
        t.send([d[k]], event_id=100 + k)
    after = t.doc
    bands = after["lines"][line_id]["bands"]
    assert rib_of(after, "d")["slots"] == 32 and rib_of(after, "d")["x1"] == 16.5
    assert [(b["s"], b["used"]) for b in bands] == [(62.669, [6.5, 10.5]), (59.669, [16.5, 0.5])]  # one cell of reach costs 1 / radians(half) = 3.4 cells of radius in this wedge
    assert bands[1]["s"] < bands[0]["s"] and bands[0]["s"] - bands[1]["s"] == 3.0  # the radial order is the same, and the outer band lies flush against the inner
    assert after["lines"][line_id]["spokes"] == before["lines"][line_id]["spokes"] and after["lines"][line_id]["members"] == before["lines"][line_id]["members"]  # inward: nothing moves
    assert rib_of(after, "a") == rib_of(before, "a")
    for key in "bc":
        assert rib_of(after, key)["s"] == 62.669 and rib_of(after, key)["slots"] == rib_of(before, key)["slots"]
        for slot, lot in lots_of(before, key).items():
            now = after["places"][lay.article_place(lot["article"])]
            assert (now["parent"], now["slot"]) == (lot["parent"], lot["slot"]) and abs(math.hypot(*now["position"].values()) - math.hypot(*lot["position"].values()) - 20.53) < 0.02
    assert step_problems(before, after) == [] and sound(after, t.plan, t.tv) is None


def scenario_narrow_with_a_lap(lap):
    """The narrow wedge again, a little narrower; with `lap` the ring is full and a lap stands against the outer band."""
    spec = {"m": T(0, a=T(30), b=T(30), c=T(30), d=T(30)), **{f"z{i}": T(80) for i in range(15)}, "nowhere": T(200)}
    t = Town(spec, trunk_min=400, **SMALL)
    a, b, c, d = (t.tagged(x) for x in "abcd")
    t.send(a[:5] + b[:4] + c[:4], event_id=1)
    t.send(b[4:9], event_id=2)
    t.send(c[4:13], event_id=3)
    t.send(d[:13], event_id=4)
    if lap:
        t.send([art(5000 + k, []) for k in range(130)], event_id=5)  # the ring is full: a lap opens beyond everything that stands
    return t


def grow_d_by_a_cell(t):
    """The 21st house of d, whose rib of 20 lots is full, with a growth of one cell (2 lots) in place of what the road needs."""
    for k in range(13, 21):
        t.send([t.tagged("d")[k]], event_id=100 + k)


def test_a_lap_of_the_ring_road_that_lies_beyond_a_band_is_not_crossed_the_band_that_has_to_move_jumps_it(monkeypatch):
    """The lap opens against the outer band (its span starts where the band ends). A rib that gains one cell, 2 lots, makes the bands reach 3.94 cells farther out in this wedge,
    which is into the lap: d's band and the band beyond it jump the lap. Without the lap they move by the 3.94."""
    t, plain = scenario_narrow_with_a_lap(True), scenario_narrow_with_a_lap(False)

    def radii(w):
        return [b["s"] for b in w.doc["lines"]["place:tag:m"]["bands"]]

    lap = t.doc["places"]["place:root:lap:2"]["ring"]["radius"]
    assert radii(t) == radii(plain) == [47.832, 44.832] and abs(lap - 1.5 - (max(radii(t)) + 1.5)) < 1e-9  # the lap stands against the outer band
    monkeypatch.setattr(zw.World, "grow_rib", grow_by(lambda need, held, top: 2))  # one cell
    grow_d_by_a_cell(t)
    grow_d_by_a_cell(plain)
    assert rib_of(t.doc, "d")["slots"] == rib_of(plain.doc, "d")["slots"] == 22
    inner, outer = radii(plain)[1], radii(plain)[0]
    assert abs(inner - 44.832 - 3.939) < 0.002 and abs(outer - inner - 3.0) < 1e-9  # without the lap: 3.94 cells farther out (one cell of reach), still flush
    assert radii(t)[1] == lap + 1.5 + 1.5 and radii(t)[0] == radii(t)[1] + 3.0  # with it: d's band begins where the lap ends, the other flush behind it
    spans = sorted((b["s"] - 1.5, b["s"] + 1.5) for b in t.doc["lines"]["place:tag:m"]["bands"])
    assert all(hi <= lap - 1.5 + 1e-9 or lo >= lap + 1.5 - 1e-9 for lo, hi in spans)  # no band lies across the lap


def test_a_branch_circle_that_moves_takes_the_lines_that_start_on_it_with_it():
    seen = 0
    for step, before, after, plan, tv in walk(0, limit=440):
        for lid, line in before["lines"].items():
            if line["parent"] is None:
                continue
            owner = line["parent"]
            circle = lambda doc: next(m for m in doc["lines"][owner["line"]]["members"] if m["place"] == owner["member"])["r1"]  # noqa: E731
            if circle(after) > circle(before) + 1e-9:
                seen += 1
                assert line["members"][0]["s0"] == circle(before) and after["lines"][lid]["members"][0]["s0"] == circle(after)  # a side line starts on the circle of its parent
                assert after["roads"][after["lines"][lid]["members"][0]["road"]]["s0"] == circle(after)
        if seen:
            assert lay_problems(after, plan, tv, full=True) == [] and checks.all_problems(after) == {} and step_problems(before, after, may_change_after(plan, before, after)) == []
            break
    assert seen


# ----------------------------------------------------------------------- a call, its delta and what it carries ----
def test_the_delta_of_a_growth_carries_every_record_it_moved_and_only_those():
    t = scenario_wide()
    before = t.doc
    frozen = json.dumps(before, sort_keys=True)
    res = zw.assign(t.plan, t.tv, before, [t.tagged("a")[10]], event_id=5)
    assert json.dumps(before, sort_keys=True) == frozen  # the world it read is as it was
    delta = res["delta"]
    a, b, c = (tag_street(x) for x in "abc")
    moved = {k for k, v in delta["places"].items() if v is not None}
    assert {a, b} <= moved and c not in moved and lay.article_place(t.tagged("a")[10]["id"]) in moved
    assert all(lay.article_place(lot["article"]) in moved for lot in lots_of(before, "b").values())  # b's houses moved along the band
    assert not any(lay.article_place(lot["article"]) in moved for lot in lots_of(before, "c").values()) and not any(lay.article_place(lot["article"]) in moved for lot in lots_of(before, "a").values())
    assert set(delta["lines"]) == {"place:tag:m"} and all(v is not None for v in delta["lines"].values())
    stored = json.loads(json.dumps(before))
    assert json.dumps(zw.assign(json.loads(json.dumps(t.plan)), t.tv, stored, [t.tagged("a")[10]], event_id=5)["delta"], sort_keys=True) == json.dumps(delta, sort_keys=True)  # (a stored world)
    folded = zw.apply_delta(before, delta)
    assert lay_problems(folded, t.plan, t.tv, full=True) == [] and checks.all_problems(folded) == {}


# --------------------------------------------------------------------- a road that moves leaves its ground claimed ----
def a_town_with_a_road_that_moves():
    """Avenue a with three roads on one band, b and d on one side (d behind b), c on the other; b moves below another avenue and leaves a ghost."""
    h = Hand({"max": 12, "min": 4, "auto": False, "branches": 5})
    h.add(160)
    h.open("a", "A", None, houses(1, 40))
    h.open("e", "E", None, houses(41, 60))
    for key, first in (("b", 1), ("c", 6), ("d", 11)):
        h.open(key, key.upper(), "a", houses(first, first + 4))
    return h


def test_a_road_that_moves_away_leaves_the_ground_it_claimed_claimed_and_the_road_behind_it_stays_where_it_stood():
    h = a_town_with_a_road_that_moves()
    state = h.state
    d = state.doc["places"][lay.tag_place("d")]["rib"]
    assert (d["band"], d["side"], d["x0"], d["x1"], d["s"]) == (0, -1, 6.5, 11.5, 45.5)  # behind b on one side of the band
    assert state.doc["lines"]["place:tag:a"]["bands"][0]["used"] == [11.5, 5.5]
    h.move("b", "e")
    after = h.state.doc
    ghost = [r for e in after["lines"]["place:tag:a"]["log"] if e["kind"] == "band" for r in e["ribs"][0] if r.get("ghost")]
    assert [(r["place"], r["width"]) for r in ghost] == [(lay.tag_place("b"), 5)] and after["roads"][ghost[0]["road"]]["kind"] == "lane"
    assert after["places"][lay.tag_place("d")]["rib"]["x0"] == 6.5 and after["lines"]["place:tag:a"]["bands"][0]["used"] == [11.5, 5.5]  # nothing moves in
    for k, house in enumerate(houses(61, 75)):  # d grows, and the ghost's ground stays in front of it
        h.file(house, "d")
    after = h.state.doc
    rib = after["places"][lay.tag_place("d")]["rib"]
    assert (rib["slots"], rib["x0"]) == (20, 6.5) and rib["x1"] == 16.5 and after["lines"]["place:tag:a"]["bands"][0]["s"] == 50.202  # (the band had to reach farther: 16.5 cells)
    assert stability_violations(h.journal.events, h.journal.rule) == []


# ------------------------------------------------------------------------------------------------ planted faults ----
def mutated(method, old, new, *, count=1):
    """A copy of an engine method with a piece of its source changed: a fault planted by editing the text of the function itself (the change must be found in it)."""
    source = textwrap.dedent(inspect.getsource(method))
    assert source.count(old) == count, (old, source.count(old))
    namespace: dict = {}
    exec(source.replace(old, new), vars(zw), namespace)  # noqa: S102 - a test of the engine plants a fault in a copy of it
    return namespace[method.__name__]


def scenario_with_bands_out_of_order():
    t = scenario_narrow()
    line = t.doc["lines"]["place:tag:m"]
    assert [b["s"] for b in line["bands"]] == [42.139, 39.139] and lay_problems(t.doc, t.plan, t.tv, full=True) == []
    return t


def grow_d(t):
    for k in range(13, 21):
        t.send([t.tagged("d")[k]], event_id=100 + k)


def test_planted_a_growth_that_does_not_lay_the_line_again_turns_the_checks_red(monkeypatch):
    t = scenario_wide()
    t.send([t.tagged("a")[10]], event_id=5)  # (unplanted: sound)
    t = scenario_wide()
    monkeypatch.setattr(zw.World, "lay_line", lambda self, line_id, **kw: False)  # the rib gains its lots, and nothing is laid again
    with pytest.raises(AssertionError):
        t.send([t.tagged("a")[10]], event_id=5)  # (no empty lot: the rib has lots that no record holds)


def test_planted_a_growth_that_makes_its_lots_and_moves_nothing_turns_the_checks_red(monkeypatch):
    original = zw.World.lay_line

    def only_the_new_lots(self, line_id, *, grown=None, full=False):
        if grown is None:
            return original(self, line_id, full=full)
        rib = self.places.get(grown)["rib"]
        for slot in range(rib["slots"]):
            key = lay.reserved_place(rib["block"], slot)
            if self.places.get(key) is None and not any(p["slot"] == slot and p["parent"] == grown for p in self.by_road().get(grown, ())):
                xz, facing = self.cell(rib, self.lines.get(line_id)["axis"], slot)
                self.places.put(key, lay.reserved_record(grown, slot, "tail", xz, facing))
        return True

    t = scenario_wide()
    monkeypatch.setattr(zw.World, "lay_line", only_the_new_lots)
    with pytest.raises(AssertionError):
        t.send([t.tagged("a")[10]], event_id=5)  # the road behind a is still where it was: its cells overlap the new lots of a, and the world is not what its log lays


def test_planted_a_line_laid_in_the_order_the_ribs_opened_in_and_not_the_radial_order_turns_the_check_red(monkeypatch):
    t = scenario_with_bands_out_of_order()

    def in_opening_order(self, line):
        log = [dict(e) for e in line["log"]]
        slots = [i for i, e in enumerate(log) if e["kind"] == "band"]
        for i, e in zip(slots, sorted((log[i] for i in slots), key=lambda e: e["band"])):
            log[i] = e
        return original(self, {**line, "log": log})

    original = zw.World.derive
    monkeypatch.setattr(zw.World, "derive", in_opening_order)
    found = lay_problems(t.doc, t.plan, t.tv, full=True)
    assert found and any(name == "lines" for name, *_ in found)  # the band that opened second lies inward of the first, and laid first-opened-first it would not
    monkeypatch.undo()
    assert lay_problems(t.doc, t.plan, t.tv, full=True) == []


def test_planted_a_radius_rounded_another_way_than_first_placement_turns_the_check_red(monkeypatch):
    t = scenario_with_bands_out_of_order()
    monkeypatch.setattr(zw.World, "derive", mutated(zw.World.derive, "nxt = ceil3(self.jump(laps, max(s, need) - BAND / 2, BAND) + BAND / 2)",
                                                    "nxt = math.ceil((self.jump(laps, max(s, need) - BAND / 2, BAND) + BAND / 2) * 100) / 100"))
    found = lay_problems(t.doc, t.plan, t.tv)
    assert found and any(name == "lines" for name, *_ in found)
    monkeypatch.undo()
    assert lay_problems(t.doc, t.plan, t.tv) == []


def test_planted_a_line_laid_without_remembering_where_it_has_got_to_lets_a_band_fall_into_the_gap_behind_it(monkeypatch):
    t = scenario_with_bands_out_of_order()
    before = t.doc
    monkeypatch.setattr(zw.World, "derive", mutated(zw.World.derive, "cursor = s + BAND / 2", "pass"))
    with pytest.raises(AssertionError):
        grow_d(t)  # d's band moves out, and b's and c's, which lie outward of it, are laid at the first radius that fits: inward of d's
    monkeypatch.undo()
    t = scenario_with_bands_out_of_order()
    grow_d(t)
    assert step_problems(before, t.doc) == []


def test_planted_a_line_laid_without_the_laps_of_the_ring_road_lets_a_band_lie_across_a_lap(monkeypatch):
    monkeypatch.setattr(zw.World, "grow_rib", grow_by(lambda need, held, top: 2))
    grow_d_by_a_cell(scenario_narrow_with_a_lap(True))  # (unplanted: sound)
    monkeypatch.setattr(zw.World, "derive", mutated(zw.World.derive, "laps = sorted(self.lap_spans())", "laps = []"))
    t = scenario_narrow_with_a_lap(True)  # (built by the planted engine too: the setup has no growth)
    with pytest.raises(AssertionError):
        grow_d_by_a_cell(t)


def test_planted_a_ghost_dropped_when_a_road_moves_pulls_the_road_behind_it_inward_and_the_checks_see_it(monkeypatch):
    def drop(self, rib_place, line_id):
        if self.lines.get(line_id) is None:
            return
        line = self.lines.mut(line_id)
        for e in line["log"]:
            if e["kind"] == "band":
                e["ribs"] = [[r for r in side if r["place"] != rib_place] for side in e["ribs"]]

    h = a_town_with_a_road_that_moves()
    h.move("b", "e")
    assert lay_problems(h.state.doc, h.state.plan, h.state.tree, world=zw_hand_world(h), full=True) == []  # (unplanted: the ghost keeps the ground)
    monkeypatch.setattr(zw.World, "ghost_rib", drop)
    h = a_town_with_a_road_that_moves()
    h.move("b", "e")
    found = lay_problems(h.state.doc, h.state.plan, h.state.tree, world=zw_hand_world(h), full=True)
    assert found and any(name == "places" and key == lay.tag_place("d") for name, key, _ in found)  # the road behind the one that left would move in


def zw_hand_world(h):
    from bibliopolis.hand import HandWorld

    return HandWorld(zw.PlanView(h.state.plan), h.state.tree, h.state.doc, event_id=0)
