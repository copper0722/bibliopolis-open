"""Roads open from the root zone when a road gets crowded (bibliopolis.world, "Roads"; docs/engine.md).

Synthetic trees and arrivals, no files. The rule under test: the first houses lie in the root zone (根區), UNDER the town hall (no road, no rib on
the surface); a road holds `max` houses directly; the house that would be one more is decided before it is placed; the largest group of at least
`min` (the child topic of the road's key on the path of each house) opens a road below it; the houses that stay are packed again onto the first
lots; no group of `min`: the road is over. A rib is sized to the houses its road holds plus headroom; a full road opens a continuation rib, the same
road, over or not.
"""

import json
import math

import checks
import pytest
from support import (ROOT, T, Town, art, as_text, by_tag, count, direct_counts, lot_of, make_tree, ribs_of, road_of, roads_of, send, simulate_districts,
                     tag_street, underground, world_of)

from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.document import NOTES_DISTRICTS, world_layout
from bibliopolis.tree import TreeView

SMALL = dict(max_houses=12, min_houses=4)  # the same rule on a small scale: the cases below need dozens of houses, not hundreds


# ------------------------------------------------------------------------------------------- the rule ----
@pytest.mark.parametrize("rule", [{"max": 10, "min": 11}, {"max": 10, "min": 0}, {"max": 10.5, "min": 3}, {"max": "40", "min": 10}, {"max": True, "min": 1},
                                  {"max": 40, "min": 10, "extract": "all"}, {"max": 40, "min": 10, "count": "subtree"}])
def test_a_rule_the_engine_does_not_know_is_refused(rule):
    tree, items = make_tree({"a": T(30), "b": T(5)})
    plan = plan_mod.build_plan(TreeView(tree), items, trunk_min=20)
    plan["params"]["districts"] = {"extract": "largest", "count": "direct", **rule}
    with pytest.raises(ValueError):
        zw.PlanView(plan)
    plan["params"]["districts"] = {"max": 40, "min": 10, "extract": "largest", "count": "direct"}
    assert zw.PlanView(plan).districts["max"] == 40


@pytest.mark.parametrize("kw", [{"max_houses": 10, "min_houses": 11}, {"max_houses": 0, "min_houses": 0}, {"max_houses": 10.5, "min_houses": 3},
                                {"mode": "both"}, {"home_max": 0}])
def test_a_plan_is_not_built_for_a_rule_or_a_mode_the_engine_does_not_know(kw):
    tree, items = make_tree({"a": T(30), "b": T(5)})
    with pytest.raises(ValueError):
        plan_mod.build_plan(TreeView(tree), items, **kw)


def test_a_new_world_starts_with_the_rule_an_empty_chronicle_and_the_town_hall_alone():
    tree, items, plan, doc = world_of({"a": T(30), "b": T(5)})
    assert doc["chronicle"] == [] and doc["districts"] == {"max": 40, "min": 10, "extract": "largest", "count": "direct"} and doc["mode"] == "grow"
    assert [r["place"] for r in doc["composition"]["ring1"]] == [tag_street("a"), tag_street("b")] and list(doc["places"]) == [lay.PLAZA_PLACE]
    assert sum(r["span"] for r in doc["composition"]["ring1"]) == 360  # the ring-1 streets share the whole circle: there is no sector for anything else
    assert "zone" not in plan and not [r for r in plan["ring1"] if "zone" in r]
    day_one = world_layout(doc)
    assert list(day_one["places"]) == [lay.PLAZA_PLACE] and day_one["roads"] == {} and day_one["world"]["houses"] == 0 and day_one["world"]["chronicle"] == []
    assert day_one["composition"]["measure"]["lots"] == 0 and day_one["coast"]["polygons"]  # the land is the plaza's


# ------------------------------------------------------------------------------- the grid under the plaza ----
def test_the_cells_under_the_plaza_are_whole_cells_nearest_first_and_the_first_89_lie_inside_it():
    cells = [zw.underground_cell(k) for k in range(300)]
    assert cells[0] == (0.0, 0.0) and len(set(cells)) == 300  # the centre first, no cell twice
    assert sorted(cells[1:5]) == [(-1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (1.0, 0.0)]  # then the four next to it
    dist = [math.hypot(x, z) for x, z in cells]
    assert dist == sorted(dist)  # nearest first, all the way out
    inside = [math.hypot(abs(x) + 0.5, abs(z) + 0.5) <= lay.PLAZA_RADIUS for x, z in cells]
    assert all(inside[:89]) and not any(inside[89:])  # a lot is a cell of 1 x 1: the first 89 lie wholly inside the plaza, no later one does
    assert [zw.underground_cell(k) for k in range(300)] == cells and zw._cells_within(7) == zw._cells_within(15)[:len(zw._cells_within(7))]


# ---------------------------------------------------------------- the root zone and the first split ----
SPEC_A = {"med": T(0, a1=T(8), a2=T(7), b=T(9), c=T(9)), "pub": T(12)}  # 33 houses of med, then 12 of pub: house 41 is the 8th of pub


def test_the_first_forty_houses_lie_underground_and_the_41st_opens_the_first_road():
    tree, arts, plan, doc = world_of(SPEC_A)
    for n, a in enumerate(arts[:40], start=1):
        doc, _ = send(plan, tree, doc, [a], event_id=n)
        lot = lot_of(doc, a)
        assert lot["street"] == ROOT and lot["parent"] == ROOT and lot["underground"] is True and doc["chronicle"] == []
        assert (lot["slot"], lot["order"]) == (n - 1, n - 1) and (lot["position"]["x"], lot["position"]["z"]) == zw.underground_cell(n - 1)  # arrival order
    # the root zone is one street under the town hall: no road, no rib, nothing on the surface
    assert doc["places"][ROOT] == {"kind": "street", "shape": "underground", "underground": True, "label": "根區", "address": ["根區"],
                                   "parent": lay.PLAZA_PLACE, "lots": 40, "reserved": 0}
    assert doc["roads"] == {} and doc["lines"] == {} and len(doc["places"]) == 2 + 40 and roads_of(doc) == {}
    shown = world_layout(doc)
    assert shown["composition"]["articles"] == shown["composition"]["buildings"] == shown["world"]["houses"] == 40  # (they are houses: one lot each)
    m = shown["composition"]["measure"]  # the surface measures do not see them
    assert (m["lots"], m["max_radius"], m["walk_longest"], m["roads"], m["underground_lots"]) == (0, 0.0, 0.0, 0, 40)
    assert shown["coast"] == world_layout(zw.new_world(plan))["coast"]  # the land is the plaza's and nothing more
    assert shown["composition"]["streets"] == {"total": 0, "containers": 0, "leaves": 0, "trunks": 0, "groups": 0, "spokes": 0, "lanes": 0,
                                               "continuations": 0, "underground": 1}
    assert [p for p in shown["places"].values() if p["kind"] == "lot" and not p.get("underground")] == []
    doc, res = send(plan, tree, doc, [arts[40]], event_id=41)
    (entry,) = doc["chronicle"]
    assert (entry["n"], entry["event_id"], entry["seq"], entry["trigger"]) == (1, 41, 41, "arrival")
    assert (entry["from"], entry["to"], entry["label"]) == (ROOT, tag_street("med"), "Med")  # the chronicle says the road came out of 根區
    assert entry["count_before"] == 41 and entry["count_after"] == 8 and len(entry["houses"]) == 33
    assert set(entry["houses"]) == {a["id"] for a in by_tag(arts, "a1", "a2", "b", "c")}  # the group of the largest root topic
    assert count(doc, ROOT) == 8 and count(doc, tag_street("med")) == 33
    assert all(road_of(doc, a) == tag_street("med") and "underground" not in lot_of(doc, a) for a in by_tag(arts, "a1", "a2", "b", "c"))
    assert all(road_of(doc, a) == ROOT for a in by_tag(arts, "pub")[:8])  # pub has 8 houses: below min, it stays underground
    med = doc["places"][tag_street("med")]  # a ring-1 road on its plan wedge: its record's parent stays the plaza
    assert (med["level"], med["class"], med["shape"], med["tag"], med["parent"]) == (1, "大道", "trunk", "med", lay.PLAZA_PLACE)
    assert ribs_of(doc, tag_street("med")) == [zw.district_rib_size(33, 40)] == [40] and res["stats"]["splits"] == 1
    assert res["placements"][arts[40]["id"]]["street"] == ROOT  # the arrival is where it stands now


def test_a_group_of_nine_stays_underground_and_a_group_of_ten_leaves():
    # the 41st house finds 32 + 9 in the root zone: min is 10, so only the 32 leave (a house of another root arrives after)
    tree, arts, plan, doc = world_of({"big": T(32), "nine": T(9), "one": T(1)})
    doc, _ = send(plan, tree, doc, arts, event_id=1)
    (entry,) = doc["chronicle"]
    assert entry["to"] == tag_street("big") and len(entry["houses"]) == 32 and (entry["count_before"], entry["count_after"]) == (41, 9)
    assert count(doc, ROOT) == 10 and all(road_of(doc, a) == ROOT for a in by_tag(arts, "nine", "one"))
    # the same root zone with a group of exactly 10 among 31 single houses: the 10 leave, the others stay
    spec = {"ten": T(10), **{f"s{i}": T(1) for i in range(31)}}
    tree, arts, plan, doc = world_of(spec)
    doc, _ = send(plan, tree, doc, arts, event_id=1)
    (entry,) = doc["chronicle"]
    assert entry["to"] == tag_street("ten") and len(entry["houses"]) == 10 and (entry["count_before"], entry["count_after"]) == (41, 31)
    assert count(doc, ROOT) == 31 and count(doc, tag_street("ten")) == 10


def test_the_survivors_of_a_split_are_packed_again_onto_the_first_cells_in_arrival_order():
    tree, arts, plan, doc = world_of(SPEC_A)
    doc, _ = send(plan, tree, doc, arts[:40])
    before = {p["article"]: p for p in doc["places"].values() if p["kind"] == "lot"}
    assert [before[a["id"]]["slot"] for a in by_tag(arts, "pub")[:7]] == list(range(33, 40))  # behind the 33 houses of med
    doc, _ = send(plan, tree, doc, [arts[40]])
    stay = underground(doc)
    assert [p["slot"] for p in stay] == list(range(8)) and {p["parent"] for p in stay} == {ROOT}  # no hole: the first cells, in order
    assert [p["article"] for p in stay] == [a["id"] for a in by_tag(arts, "pub")[:8]]
    assert [(p["position"]["x"], p["position"]["z"]) for p in stay] == [zw.underground_cell(k) for k in range(8)]
    assert doc["places"][ROOT]["lots"] == 8 and not [q for q in doc["places"].values() if q["kind"] == "reserved" and q["parent"] == ROOT]  # (an empty cell is nothing)
    new_road = [p for p in doc["places"].values() if p["kind"] == "lot" and p["street"] == tag_street("med")]
    assert sorted(p["slot"] for p in new_road) == list(range(33)) and {p["parent"] for p in new_road} == {tag_street("med")}
    assert [p["seq"] for p in sorted(new_road, key=lambda p: p["slot"])] == sorted(p["seq"] for p in new_road)  # (seq is kept: arrival order)
    assert all(lot_of(doc, a["id"])["seq"] == before[a["id"]]["seq"] for a in arts[:40])


def test_a_split_in_the_middle_of_one_call_changes_where_the_next_houses_of_that_topic_stand():
    tree, arts, plan, doc = world_of(SPEC_A)
    order = by_tag(arts, "pub")[:7] + by_tag(arts, "a1", "a2", "b", "c")[:26] + by_tag(arts, "a1", "a2", "b", "c")[26:] + by_tag(arts, "pub")[7:]
    doc, res = send(plan, tree, doc, order, event_id=77)  # ONE call: 45 houses; the 41st is a house of pub
    (entry,) = doc["chronicle"]
    assert entry["seq"] == 41 and entry["event_id"] == 77 and entry["trigger"] == "arrival" and entry["to"] == tag_street("med")
    assert set(res["placements"]) == {a["id"] for a in order} and all(res["placements"][a["id"]] == lot_of(doc, a) for a in order)
    assert count(doc, tag_street("med")) == 33 and count(doc, ROOT) == 12
    # the same arrivals one house at a time give the same world
    one = zw.new_world(plan)
    for a in order:
        one, _ = send(plan, tree, one, [a], event_id=77)
    assert as_text(one["places"]) == as_text(doc["places"]) and one["chronicle"] == doc["chronicle"]


def test_a_split_happens_mid_batch_so_the_houses_after_it_stand_on_the_new_road_directly():
    spec = {"med": T(0, a=T(0, a1=T(12), a2=T(12)), b=T(20)), "pub": T(5)}
    tree, arts, plan, doc = world_of(spec, max_houses=40, min_houses=10)
    first = by_tag(arts, "pub")[:5] + by_tag(arts, "b")[:20] + by_tag(arts, "a1")[:12] + by_tag(arts, "a2")[:3]  # 40 houses
    rest = by_tag(arts, "a2")[3:]  # the 41st is a house of med
    doc, res = send(plan, tree, doc, first + rest, event_id=5)
    first_entry = doc["chronicle"][0]
    assert first_entry["seq"] == 41 and first_entry["to"] == tag_street("med") and first_entry["from"] == ROOT
    for a in rest[1:]:  # houses 42 and after: the road is open, they stand on it
        assert road_of(doc, a) in (tag_street("med"), tag_street("a"))  # (the road below may have opened by then)
    assert all(e["event_id"] == 5 for e in doc["chronicle"])
    assert res["stats"]["houses"] == len(first + rest)  # every arrival counted once, whatever it went through


def test_a_tree_with_one_root_has_the_root_as_its_centre_and_the_root_zone_groups_by_the_children_of_the_centre():
    tree, arts, plan, doc = world_of({"med": T(3, a=T(25), b=T(16))})
    assert plan["params"]["centre_tag"] == "med"  # (the plan has a ring-1 street for the centre's own houses; a house tagged the centre gets no road)
    doc, _ = send(plan, tree, doc, arts[:44], event_id=2)  # 3 houses tagged med itself, then 25 of a and 16 of b: 44 in all
    (entry,) = doc["chronicle"]
    assert (entry["from"], entry["to"], entry["seq"]) == (ROOT, tag_street("a"), 41) and len(entry["houses"]) == 25
    assert count(doc, ROOT) == 19 and count(doc, tag_street("a")) == 25  # b stayed (16 houses, but the root zone is at 19, under max); so did the centre's own
    assert all(road_of(doc, a) == ROOT for a in by_tag(arts, "med", "b"))


def test_a_group_above_max_splits_again_at_once():
    spec = {"med": T(0, a=T(25), b=T(16)), "pub": T(2)}
    tree, arts, plan, doc = world_of(spec)
    doc, _ = send(plan, tree, doc, arts[:41], event_id=9)  # all 41 houses are of med: the first road is born with 41 houses, over max
    first, second = doc["chronicle"]
    assert (first["from"], first["to"], first["count_before"], first["count_after"]) == (ROOT, tag_street("med"), 41, 0)
    assert (second["from"], second["to"]) == (tag_street("med"), tag_street("a"))  # the new road is checked at once: its largest group opens
    assert second["seq"] == first["seq"] == 41 and second["count_before"] == 41 and second["count_after"] == 16 and len(second["houses"]) == 25
    assert [e["n"] for e in doc["chronicle"]] == [1, 2]
    assert count(doc, tag_street("med")) == 16 and count(doc, tag_street("a")) == 25 and count(doc, ROOT) == 0
    assert doc["places"][tag_street("med")]["shape"] == "trunk" and doc["places"][tag_street("a")]["shape"] == "rib"
    assert doc["places"][tag_street("a")]["parent"] == tag_street("med") and doc["places"][tag_street("a")]["level"] == 2
    assert doc["places"][tag_street("a")]["address"] == ["Med", "A"]
    # nothing was put on a rib that a split took away again: each road holds one rib, sized to the houses it holds (no continuation)
    assert ribs_of(doc, tag_street("med")) == [zw.district_rib_size(16, 40)] == [24] and ribs_of(doc, tag_street("a")) == [zw.district_rib_size(25, 40)] == [38]
    # the root zone stands in the document once it exists, empty or not: the chronicle names it, and what it names must be there
    shown = world_layout(doc, with_coast=False)
    assert shown["places"][ROOT]["lots"] == 0 and shown["places"][ROOT]["underground"] is True and shown["composition"]["streets"]["underground"] == 1
    assert [e["from"] for e in shown["world"]["chronicle"] if "from" in e] == [ROOT, tag_street("med")] and all(
        e["from"] in shown["places"] and e["to"] in shown["places"] for e in shown["world"]["chronicle"] if "from" in e)
    assert list(world_layout(zw.new_world(plan), with_coast=False)["places"]) == [lay.PLAZA_PLACE]  # day one: the town hall alone, no root zone yet


# ----------------------------------------------------------------------------- ribs: sized to the road ----
def test_the_size_of_a_rib_is_the_houses_of_the_road_and_headroom_in_whole_cells_never_above_max():
    assert [zw.district_rib_size(n, 40) for n in (1, 2, 4, 8, 10, 11, 16, 20, 26, 27, 40, 41, 100)] == [6, 6, 8, 12, 16, 18, 24, 30, 40, 40, 40, 40, 40]
    assert [zw.district_rib_size(n, 12) for n in (1, 3, 5, 6, 7, 13)] == [6, 8, 10, 10, 12, 12]
    assert all(zw.district_rib_size(n, m) % 2 == 0 or zw.district_rib_size(n, m) == m for n in range(1, 120) for m in (8, 12, 40))  # whole cells (or max)
    assert all(zw.district_rib_size(n, 40) >= min(n + 4, 40) for n in range(1, 120))  # the houses and at least four lots more, until max


def test_a_full_road_opens_a_continuation_rib_the_same_road_and_over_is_another_matter():
    t = Town({"a": T(14), "b": T(3), "c": T(3), "d": T(1)}, **SMALL)
    a = tag_street("a")
    own = t.tagged("a")
    # six houses of a, three of b, three of c, one of d: the 13th makes the root zone over max; a is the largest group (6 >= min 4) and opens a road
    t.send(own[:6] + t.tagged("b", "c", "d"), event_id=1)
    assert [(e["from"], e["to"]) for e in t.doc["chronicle"]] == [(ROOT, a)] and t.count(a) == 6 and t.count(ROOT) == 7
    assert ribs_of(t.doc, a) == [zw.district_rib_size(6, 12)] == [10]  # the first rib is sized to the 6 houses of the road and headroom (4 lots), not to max
    t.send(own[6:10], event_id=2)  # 10 houses: the first rib is full
    assert ribs_of(t.doc, a) == [10] and "lanes" not in t.doc["places"][a]
    t.send(own[10:12], event_id=3)  # the 11th: a continuation rib, sized on the count (11) but capped so that the ribs hold `max` = 12 lots in all
    assert ribs_of(t.doc, a) == [10, 2] and t.count(a) == 12 and "over" not in t.doc["places"][a]
    cont, road = t.doc["places"]["place:lane:a:2"], t.doc["places"][a]
    assert cont["lane_of"] == a and cont["continued"] is True and cont["ordinal"] == 2 and cont["parent"] == a  # a record that says it continues the road
    assert (cont["label"], cont["level"], cont["class"], cont["address"]) == (road["address"][-1], road["level"], road["class"], road["address"])  # one road, named once
    assert "・" not in cont["label"] and cont["rib"]["slots"] == 2 and cont["lots"] == 2
    t.send(own[12:13], event_id=4)  # the 13th house: a holds more than max and no group can open: over - and a continuation rib, sized on the count, uncapped
    assert t.doc["places"][a]["over"] is True and ribs_of(t.doc, a) == [10, 2, 12] and t.doc["places"]["place:lane:a:3"]["continued"] is True
    assert [e["over"] for e in t.doc["chronicle"] if "over" in e] == [a]  # `over` is independent of the continuation ribs: the 11th house made one, not an entry
    shown = t.shown()  # one road in the document: counted once, named once
    streets = shown["composition"]["streets"]
    assert (streets["total"], streets["continuations"], streets["lanes"], streets["underground"]) == (1, 2, 0, 1)
    assert shown["composition"]["measure"]["streets_by_class"]["大道"] == 1 and sum(shown["composition"]["measure"]["streets_by_class"].values()) == 1
    assert shown["places"]["place:lane:a:3"]["label"] == shown["places"][a]["address"][-1] and shown["places"]["place:lane:a:3"]["continued"] is True
    assert "street.continued" in NOTES_DISTRICTS and "street.continued" in shown["world"]["notes"]


def test_a_road_that_never_was_over_holds_max_lots_in_its_ribs_at_most_and_no_road_has_a_numbered_lane():
    for seed in (0, 3):
        problems, doc, _steps, _plan, _tv = simulate_districts(seed)
        assert problems == []
        ever_over = {e["over"] for e in doc["chronicle"] if "over" in e}
        for road in roads_of(doc):
            assert road in ever_over or sum(ribs_of(doc, road)) <= 12
        assert not [p for p in doc["places"].values() if p["kind"] == "street" and "lane_of" in p and not p.get("continued")]
        assert not [p for p in doc["places"].values() if p["kind"] == "street" and p.get("label", "").endswith(tuple(f"・{n}" for n in range(2, 30)))]


# ------------------------------------------------------------------------------ over, no merge back ----
def test_a_road_over_max_with_no_group_of_min_is_over_and_a_group_of_min_lets_it_split():
    t = Town({"med": T(8, m1=T(4), m2=T(3), m3=T(3)), "x": T(2)}, **SMALL)
    med = tag_street("med")
    own, m1, m2 = t.tagged("med"), t.tagged("m1"), t.tagged("m2")
    t.send(own + m1[:3] + m2[:1], event_id=1)  # 12 houses: the root zone is at max, nothing has happened
    assert t.doc["chronicle"] == [] and t.count(ROOT) == 12 and "over" not in t.doc["places"][ROOT]
    t.send(m2[1:2], event_id=2)  # the 13th: med opens for the group of its root topic and holds 13, with no group of 4 below it
    split, over = t.doc["chronicle"]
    assert (split["from"], split["to"], split["seq"]) == (ROOT, med, 13) and (over["over"], over["count"], over["seq"], over["n"]) == (med, 13, 13, 2)
    road = t.doc["places"][med]
    assert road["over"] is True and t.count(med) == 13 and "over" not in t.doc["places"][ROOT]
    assert ribs_of(t.doc, med) == [12, 12] and road["lanes"] == ["place:lane:med:2"]  # (the first rib is sized to 13 houses: 12 = max; the 13th goes on)
    assert t.doc["places"]["place:lane:med:2"]["continued"] is True and t.doc["places"]["place:lane:med:2"]["lots"] == 1
    shown = t.shown()
    assert shown["places"][med]["over"] is True and "place:lane:med:2" in shown["places"]
    assert shown["world"]["chronicle"] == t.doc["chronicle"] and shown["world"]["districts"] == t.doc["districts"]
    assert "world.chronicle" in shown["world"]["notes"] and "street.over" in shown["world"]["notes"]
    # the 14th, of a group of 4: the road splits and is not over any more; the continuation rib stands empty and is no part of the document
    t.send(m1[3:4], event_id=3)
    third = t.doc["chronicle"][2]
    assert (third["from"], third["to"], third["seq"], third["count_before"], third["count_after"]) == (med, tag_street("m1"), 14, 14, 10)
    assert [e["n"] for e in t.doc["chronicle"]] == [1, 2, 3] and "over" not in t.doc["places"][med] and t.count(med) == 10
    assert t.doc["places"]["place:lane:med:2"]["lots"] == 0  # (the rib stays in the world: the ground it claimed is claimed)
    again = t.shown()
    assert "place:lane:med:2" not in again["places"] and "lanes" not in again["places"][med]
    assert not [r for r in again["roads"] if "lane:med:2" in r]


def test_the_root_zone_over_max_with_no_group_of_min_is_over_and_a_group_of_min_leaves():
    t = Town({"p": T(3), "q": T(3), "r": T(3), "s": T(3), "t": T(1)}, **SMALL)
    t.send(t.items[:13], event_id=1)  # 13 houses: four roots of 3 (= min - 1) and one of 1: no group can open
    (over,) = t.doc["chronicle"]
    assert over["over"] == ROOT and over["count"] == 13 and t.doc["places"][ROOT]["over"] is True and roads_of(t.doc) == {}
    assert "rib" not in t.doc["places"][ROOT] and "lanes" not in t.doc["places"][ROOT]  # the root zone has no ribs, so it has nothing to continue
    assert [p["slot"] for p in underground(t.doc)] == list(range(13))  # the 13th has its cell too (the grid does not end at max)
    t.send([art(900, ["p"])], event_id=2)  # p has 4 = min: it opens
    entry = t.doc["chronicle"][1]
    assert (entry["from"], entry["to"], entry["count_before"], entry["count_after"]) == (ROOT, tag_street("p"), 14, 10) and len(entry["houses"]) == 4
    assert "over" not in t.doc["places"][ROOT] and t.count(ROOT) == 10 and t.count(tag_street("p")) == 4


def test_a_road_the_split_leaves_under_min_stays_open_there_is_no_merge_back():
    t = Town({"med": T(2, a=T(10), b=T(2)), "x": T(1)}, **SMALL)
    med = tag_street("med")
    t.send(t.tagged("med") + t.tagged("a") + t.tagged("b")[:1], event_id=1)  # 13 houses: the root zone opens med, then med opens a for its 10
    first, second = t.doc["chronicle"]
    assert (first["from"], first["to"]) == (ROOT, med) and (second["from"], second["to"]) == (med, tag_street("a"))
    assert second["count_after"] == 3 < SMALL["min_houses"] and t.count(med) == 3  # the houses that stay are fewer than `min` ...
    assert med in roads_of(t.doc) and t.count(ROOT) == 0  # ... and the road stays open: nothing merges back, whatever its size
    t.send(t.tagged("b")[1:] + [art(900, ["x"])], event_id=2)
    assert med in roads_of(t.doc) and t.count(med) == 4 and t.count(ROOT) == 1 and len(t.doc["chronicle"]) == 2


# --------------------------------------------------------------------------------------------- collapse ----
CHAIN = {"med": T(5, m1=T(0, m2=T(0, m3=T(8), m2b=T(1)))), "x": T(1)}  # med and a chain of single children m1 > m2 > m3 (and a sibling of m3)


def test_a_group_that_sits_in_a_chain_of_one_child_topics_opens_the_deepest_road_with_the_chain_in_its_label():
    t = Town(CHAIN, **SMALL)
    med, m3 = tag_street("med"), tag_street("m3")
    t.send(t.tagged("med") + t.tagged("m3"), event_id=7)  # 13 houses: 5 on med itself, 8 under the chain
    first, second = t.doc["chronicle"]
    assert (first["from"], first["to"], second["from"], second["to"]) == (ROOT, med, med, m3)  # med opens from the root zone, then the group below it
    road = t.doc["places"][m3]
    assert road["collapsed"] == ["m1", "m2"] and road["tag"] == "m3" and road["label"] == lay.JOIN.join(["M1", "M2", "M3"]) == "M1・M2・M3"
    assert second["label"] == road["label"] and road["parent"] == med and road["level"] == 2 and road["address"] == ["Med", "M1・M2・M3"]
    assert t.count(m3) == 8 and t.count(med) == 5 and t.shown()["places"][m3]["collapsed"] == ["m1", "m2"]
    # a house of any topic of the chain stands on the road; a house of another child of a topic of the chain does not
    fresh = [art(901, ["m1"]), art(902, ["m2"]), art(903, ["m3"]), art(904, ["m2b"]), art(905, ["med"])]
    t.send(fresh, event_id=8)
    assert [t.road(h) for h in fresh] == [m3, m3, m3, med, med]
    w = zw.World(zw.PlanView(t.plan), t.tv, t.doc)  # the lookup itself: the nearest open road at or above the topic, a chain topic holds itself only
    assert [w.road_for_tag(x) for x in ("m3", "m2", "m1", "m2b", "med", "x", "nowhere")] == [m3, m3, m3, med, med, ROOT, ROOT]
    assert w.road_for_tag(None) == ROOT


def test_the_chains_of_two_roads_never_share_a_topic_the_second_chain_starts_below_the_first():
    spec = {"med": T(5, m=T(0, p=T(0, la=T(8)), q=T(0, lb=T(8)), r1=T(2), r2=T(2))), "x": T(1)}
    t = Town(spec, **SMALL)
    med = tag_street("med")
    t.send(t.tagged("med") + t.tagged("la"), event_id=1)  # 13: the group of m sits in p > la: a road la with the chain m, p
    la = t.doc["places"][tag_street("la")]
    assert la["collapsed"] == ["m", "p"] and la["label"] == "M・P・La"
    t.send(t.tagged("lb"), event_id=2)  # med (5) + lb (8) = 13: the group of m again, now in q > lb, and m belongs to the first road
    lb = t.doc["places"][tag_street("lb")]
    assert lb["collapsed"] == ["q"] and lb["label"] == "Q・Lb" and lb["parent"] == med and lb["address"] == ["Med", "Q・Lb"]
    held = [x for r in roads_of(t.doc).values() for x in [r["tag"], *r.get("collapsed", [])]]
    assert len(held) == len(set(held))  # one topic, one road
    w = zw.World(zw.PlanView(t.plan), t.tv, t.doc)
    assert [w.road_for_tag(x) for x in ("m", "p", "q", "r1", "r2")] == [tag_street("la"), tag_street("la"), tag_street("lb"), med, med]


def test_a_group_whose_road_would_have_to_sit_above_an_open_road_stays_where_it_is_and_the_road_is_over():
    spec = {"med": T(9, m=T(0, p=T(0, la=T(8)), r1=T(2), r2=T(2))), "x": T(1)}
    t = Town(spec, **SMALL)
    med = tag_street("med")
    t.send(t.tagged("med")[:5] + t.tagged("la"), event_id=1)  # a road la with the chain m, p below med
    assert t.doc["places"][tag_street("la")]["collapsed"] == ["m", "p"]
    res = t.send(t.tagged("med")[5:] + t.tagged("r1") + t.tagged("r2"), event_id=2)  # 4 more of med, then r1 and r2 (4 = min together, below m)
    # the group of m is r1 + r2: it spreads over two children, so its road would be m itself - which the road la holds in its chain
    assert t.doc["places"][med].get("over") is True and t.count(med) == 13 and res["stats"]["blocked"] >= 1
    assert [e for e in t.doc["chronicle"] if e["event_id"] == 2 and "from" in e] == []  # no split in the second send: nothing left med
    assert t.doc["chronicle"][-1]["over"] == med and t.doc["chronicle"][-1]["count"] == 13 and t.doc["chronicle"][-1]["event_id"] == 2


# ------------------------------------------------------------------ the root zone, the plan's ring 1 ----
def test_an_item_with_no_topic_and_an_item_of_an_unknown_topic_lie_underground_there_are_no_other_streets():
    tree, arts, plan, doc = world_of(SPEC_A)
    plain = art(901, [])
    unknown = art(902, ["a_topic_the_tree_never_had"])  # the engine reads a topic the tree does not have as no topic (bibliopolis.inputs refuses it earlier)
    both = art(903, ["a_topic_the_tree_never_had", "pub"])  # ... and takes the deepest topic of the tree it does know
    doc, res = send(plan, tree, doc, [plain, unknown, both], event_id=1)
    assert [res["placements"][a["id"]]["street"] for a in (plain, unknown, both)] == [ROOT] * 3
    assert [res["placements"][a["id"]]["tag"] for a in (plain, unknown, both)] == [None, None, "pub"]
    assert all(res["placements"][a["id"]]["underground"] is True for a in (plain, unknown, both))
    assert doc["places"][ROOT]["label"] == "根區" and [pid for pid, p in doc["places"].items() if p["kind"] == "street"] == [ROOT]


def test_the_root_zone_opens_the_ring_one_street_of_the_plan_with_the_chain_the_plan_pins():
    spec = {"science": T(0, computing=T(0, ml=T(25), systems=T(0, db=T(3)), theory=T(1))), "life": T(16)}
    tree, arts, plan, doc = world_of(spec)
    street = plan["streets"]["place:tag:computing"]  # science has nothing of its own and one child with houses: it is collapsed into computing
    assert street["collapsed"] == ["science"] and plan["trunks"]["place:tag:computing"]["role"] == "ring1" and plan["sites"]["science"] == "place:tag:computing"
    arrivals = by_tag(arts, "life") + by_tag(arts, "ml")  # 16 + 25 houses
    doc, res = send(plan, tree, doc, arrivals, event_id=5)
    cs = tag_street("computing")
    (entry,) = doc["chronicle"]
    assert (entry["from"], entry["to"], entry["seq"], entry["count_before"], entry["count_after"]) == (ROOT, cs, 41, 41, 16)
    road = doc["places"][cs]
    assert road["collapsed"] == ["science"] and road["tag"] == "computing" and road["shape"] == "trunk" and road["level"] == 1
    assert road["parent"] == lay.PLAZA_PLACE  # (a ring-1 road on its plan wedge: the surface topology)
    assert entry["label"] == "Science・Computing" and road["label"] == entry["label"]
    assert count(doc, cs) == 25 and count(doc, ROOT) == 16
    more = [art(100, ["science"]), art(101, ["computing"]), art(102, ["life"]), art(103, ["db"])]  # the chain topic, the key and a topic below it: the road
    res = zw.assign(plan, tree, doc, more, event_id=6)  # (a topic of another root stays underground)
    assert [res["placements"][a["id"]]["street"] for a in more] == [cs, cs, ROOT, cs]


def test_below_ring_one_a_group_in_a_chain_opens_the_deepest_road_with_the_whole_chain():
    spec = {"clinical": T(3, internal=T(0, neuro=T(0, degen=T(0, alz=T(41))))), "other": T(2)}  # (two roots: clinical is a ring-1 street, not the centre)
    tree, arts, plan, doc = world_of(spec, trunk_min=300)
    doc, _ = send(plan, tree, doc, by_tag(arts, "alz"), event_id=1)  # 41 houses, all of one disease
    first, second, third = doc["chronicle"]
    assert first["from"] == ROOT and first["to"] == "place:tag:clinical" and first["label"] == "Clinical"  # ring 1 is the plan's street
    assert third["over"] == "place:tag:alz" and third["count"] == 41  # (41 houses of the key itself: no group below it, so it is over)
    road = doc["places"]["place:tag:alz"]
    assert second["from"] == first["to"] and second["to"] == "place:tag:alz" and road["tag"] == "alz"
    assert road["collapsed"] == ["internal", "neuro", "degen"] and road["parent"] == first["to"] and road["level"] == 2
    assert road["label"] == "Internal・Neuro・Degen・Alz" and second["count_after"] == 0
    parent = world_layout(doc, with_coast=False)["places"][first["to"]]  # the road above it kept no house: a road with no lots of its own is still a road
    assert (parent["lots"], parent["reserved"]) == (0, 0) and "rib" not in parent and parent["level"] == 1 and parent["shape"] == "trunk"


# -------------------------------------------------------------------------------------- the calls are pure ----
def test_assign_does_not_change_the_world_it_reads_and_a_stored_world_gives_the_same_answer():
    tree, arts, plan, doc = world_of(SPEC_A)
    doc, _ = send(plan, tree, doc, arts[:41], event_id=1)  # a world with a split in its chronicle
    frozen = json.dumps(doc, sort_keys=True)
    a = zw.assign(plan, tree, doc, arts[41:45], event_id=2)
    assert json.dumps(doc, sort_keys=True) == frozen and a["placements"]
    stored = json.loads(json.dumps(doc))  # the world as a file would store and read it back
    text = lambda r: json.dumps(r["delta"], sort_keys=True)  # noqa: E731
    assert text(a) == text(zw.assign(json.loads(json.dumps(plan)), tree, stored, arts[41:45], event_id=2))
    assert text(a) == text(zw.assign(json.loads(json.dumps(plan)), TreeView(tree), json.loads(json.dumps(doc)), arts[41:45], event_id=2))
    assert json.loads(json.dumps(a["delta"])) == json.loads(text(a))  # a delta is plain JSON, chronicle and all


def test_an_item_cannot_arrive_twice_or_be_placed_again():
    tree, arts, plan, doc = world_of(SPEC_A)
    with pytest.raises(ValueError, match="twice"):
        zw.assign(plan, tree, doc, [arts[0], arts[0]])
    doc, _ = send(plan, tree, doc, arts[:3])
    with pytest.raises(ValueError, match="already placed"):
        zw.assign(plan, tree, doc, [arts[2]])


# ------------------------------------------------------------------------- the surface and the coast ----
def test_the_houses_under_the_plaza_are_left_out_of_the_coast_the_roads_and_the_surface_measures_however_many_they_are():
    spec = {f"t{i}": T(9) for i in range(14)}  # fourteen roots of 9 houses: no group of 10, so every house stays underground
    tree, arts, plan, doc = world_of(spec)
    doc, _ = send(plan, tree, doc, arts[:120], event_id=1)
    assert roads_of(doc) == {} and count(doc, ROOT) == 120 and doc["places"][ROOT]["over"] is True  # over 40, and no group of 10 anywhere
    assert max(p["position"]["x"] ** 2 + p["position"]["z"] ** 2 for p in underground(doc)) > lay.PLAZA_RADIUS ** 2  # more than 89 cells: some lie beyond the plaza
    shown = world_layout(doc)
    m = shown["composition"]["measure"]
    assert (m["lots"], m["max_radius"], m["walk_longest"], m["walk_mean"], m["underground_lots"]) == (0, 0.0, 0.0, 0.0, 120)
    assert shown["coast"] == world_layout(zw.new_world(plan))["coast"] and shown["roads"] == {}
    assert shown["composition"]["articles"] == 120 and shown["world"]["houses"] == 120  # ... and still 120 houses, one lot each


def test_the_document_holds_what_stands_and_with_reserved_the_empty_lots_too():
    tree, arts, plan, doc = world_of(SPEC_A)
    doc, _ = send(plan, tree, doc, arts[:41], event_id=1)
    plain = world_layout(doc, with_coast=False)
    with_empty = world_layout(doc, with_reserved=True, with_coast=False)
    assert plain["composition"]["reserved_lots"] == 0 and with_empty["composition"]["reserved_lots"] == plain["world"]["unbuilt"] > 0
    assert with_empty["composition"]["measure"]["reserved_lots"] == with_empty["composition"]["reserved_lots"]
    assert {pid for pid, p in with_empty["places"].items() if p["kind"] != "reserved"} == set(plain["places"])
    assert "coast" not in plain and "coast" in world_layout(doc)
    assert checks.document_problems(world_layout(doc)) == {}


# ------------------------------------------------------------------------------------ random worlds ----
@pytest.mark.parametrize("seed", [0, 1, 3, 5, 7, 9])
def test_random_worlds_keep_every_invariant_through_arrivals(seed):
    problems, doc, steps, _plan, _tv = simulate_districts(seed)
    assert problems == [] and steps > 0 and zw.houses(doc)


@pytest.mark.parametrize("kw", [{"max_houses": 8, "min_houses": 3, "trunk_min": 10}, {"max_houses": 30, "min_houses": 10, "batch_max": 200},
                                {"max_houses": 12, "min_houses": 12, "order": "by_tag"}, {"max_houses": 5, "min_houses": 1, "order": "reverse", "check_every": 5},
                                {"max_houses": 20, "min_houses": 5, "trunk_min": 120, "batch_max": 5}])
def test_random_worlds_in_other_configurations(kw):
    for seed in (101, 102):
        problems, _doc, _steps, _plan, _tv = simulate_districts(seed, **kw)
        assert problems == [], (kw, seed)


def test_the_counts_of_a_random_world_add_up_to_the_items():
    problems, doc, _steps, _plan, _tv = simulate_districts(4)
    assert problems == [] and sum(direct_counts(doc).values()) == len(zw.houses(doc)) == doc["seq"]
