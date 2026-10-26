"""The mirror mode: the topic tree is the street plan (docs/engine.md).

Every topic that holds an item, directly or below, is a road from the start. Nothing splits: a road that holds more than `max` houses is `over`, and
the chronicle says when. An item with no topic (or the topic that is the town hall itself) lives on the ring road. Chains are not collapsed and
nothing is folded into a leaf: one topic, one road.
"""

import json

import checks
import pytest
from support import ROOT, T, Town, art, as_text, by_tag, count, make_tree, ribs_of, roads_of, simulate_districts, sound, stamp, tag_street

import bibliopolis
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.tree import TreeView

SMALL = dict(max_houses=12, min_houses=4)
SPEC = {"sci": T(0, comp=T(3, ml=T(30), db=T(5)), phys=T(0, optics=T(8))), "arts": T(0, design=T(0, type=T(6))), "empty": T(0, void=T(0)), "misc": T(2)}


def mirror(spec=SPEC, **kw):
    return Town(spec, mode="mirror", **kw)


def test_every_topic_that_holds_an_item_directly_or_below_is_a_road_before_the_first_house():
    t = mirror()
    holders = {"sci", "comp", "ml", "db", "phys", "optics", "arts", "design", "type", "misc"}
    assert set(t.plan["roads"]) == holders  # the plan names them: `empty` and `void` hold nothing
    assert t.plan["mode"] == "mirror" and t.doc["mode"] == "mirror"
    w = zw.World(zw.PlanView(t.plan), t.tv, t.doc)  # a world with no house yet already has its roads
    assert {w.road_def[p][0] for p in w.road_def} == holders and all(not w.road_def[p][1] for p in w.road_def)  # no chain collapsed into any road
    assert [w.road_for_tag(x) for x in ("ml", "sci", "void", "empty", None)] == [tag_street("ml"), tag_street("sci"), ROOT, ROOT, ROOT]


def test_each_road_holds_the_houses_of_its_own_topic_and_a_road_with_none_of_its_own_is_a_group_with_no_lots():
    t = mirror(trunk_min=20)
    t.send(t.items, event_id=1)
    doc = t.doc
    assert set(roads_of(doc)) == {tag_street(x) for x in t.plan["roads"]}
    own = {"sci": 0, "comp": 3, "ml": 30, "db": 5, "phys": 0, "optics": 8, "arts": 0, "design": 0, "type": 6, "misc": 2}
    assert {r["tag"]: count(doc, p) for p, r in roads_of(doc).items()} == own and count(doc, ROOT) == 0
    for name in ("sci", "phys", "arts", "design"):  # nothing of their own: a street with no rib, a group of the roads below it
        rec = doc["places"][tag_street(name)]
        assert rec["shape"] in ("group", "trunk") and rec["lots"] == 0 and rec["reserved"] == 0 and "rib" not in rec
    assert doc["places"][tag_street("ml")]["parent"] == tag_street("comp") and doc["places"][tag_street("comp")]["parent"] == tag_street("sci")
    assert doc["places"][tag_street("type")]["address"] == ["Arts", "Design", "Type"]  # the address is the path of the tree, every topic named
    assert [doc["places"][tag_street(x)]["level"] for x in ("sci", "comp", "ml", "arts", "design", "type")] == [1, 2, 3, 1, 2, 3]
    assert doc["chronicle"] == [] and not [p for p in doc["places"].values() if p["kind"] == "street" and p.get("collapsed")]


def test_nothing_splits_and_a_road_over_max_is_over_with_an_entry_in_the_chronicle():
    t = mirror(max_houses=12, min_houses=4)
    ml = t.tagged("ml")
    t.send(t.items[:t.items.index(ml[0])] + ml[:12], event_id=1)  # ml holds 12 = max: not over
    assert "over" not in t.doc["places"][tag_street("ml")] and t.doc["chronicle"] == []
    t.send(ml[12:13], event_id=2)  # the 13th house of ml: over, and no group below it (it is a leaf) could open
    (entry,) = t.doc["chronicle"]
    assert entry == {"n": 1, "event_id": 2, "seq": entry["seq"], "trigger": "arrival", "over": tag_street("ml"), "count": 13}
    assert t.doc["places"][tag_street("ml")]["over"] is True and count(t.doc, tag_street("ml")) == 13
    t.send(ml[13:], event_id=3)  # more houses: over stays, no second entry
    assert len(t.doc["chronicle"]) == 1 and count(t.doc, tag_street("ml")) == 30
    assert ribs_of(t.doc, tag_street("ml"))[0] <= 12 and len(ribs_of(t.doc, tag_street("ml"))) >= 2  # a full road continues as the same road
    for p, rec in roads_of(t.doc).items():  # a road is over exactly when it holds more than max
        assert bool(rec.get("over")) == (count(t.doc, p) > 12)


def test_a_group_that_could_open_a_road_does_not_in_mirror_mode():
    spec = {"med": T(0, a=T(30), b=T(2)), "x": T(1)}
    grown = Town(spec, **SMALL)
    grown.send(grown.items, event_id=1)
    assert [e for e in grown.doc["chronicle"] if "from" in e]  # in grow mode the road med splits: a opens
    t = Town(spec, mode="mirror", **SMALL)
    t.send(t.items, event_id=1)
    assert [e for e in t.doc["chronicle"] if "from" in e] == []  # in mirror mode `a` was a road from the start, and the roads never split again
    assert count(t.doc, tag_street("a")) == 30 and t.doc["places"][tag_street("a")]["over"] is True
    assert tag_street("med") in roads_of(t.doc) and count(t.doc, tag_street("med")) == 0


def test_items_with_no_topic_and_the_town_hall_topic_live_on_the_ring_road():
    spec = {"sci": T(3, a=T(5), b=T(5))}  # one root: it is the town hall; its own 3 houses and the 3 without a topic live on the ring road
    t = Town(spec, mode="mirror", **SMALL)
    assert t.plan["params"]["centre_tag"] == "sci" and t.plan["roads"] == ["a", "b"]  # the centre is no road
    loose = [art(900 + i, []) for i in range(3)]
    t.send(t.items + loose, event_id=1)
    assert count(t.doc, ROOT) == 6 and count(t.doc, tag_street("a")) == 5 and set(roads_of(t.doc)) == {tag_street("a"), tag_street("b")}
    assert all(road_of_(t.doc, a) == ROOT for a in by_tag(t.items, "sci") + loose)
    assert t.doc["places"][ROOT]["lots"] == 6 and all(p["parent"] == ROOT and "underground" not in p for p in t.doc["places"].values() if p["kind"] == "lot" and p["street"] == ROOT)


def road_of_(doc, item):
    return doc["places"][lay.article_place(item["id"])]["street"]


def test_the_roads_do_not_depend_on_the_order_the_items_arrive_in():
    tree, items = make_tree(SPEC)
    docs = []
    for shift in (0, 7, 31):
        order = items[shift:] + items[:shift]
        library = {"items": [{**a, "added_at": stamp(k)} for k, a in enumerate(order)]}
        plan, tv, world, _ = bibliopolis.build_world(library, tree, mode="mirror", max_houses=12, min_houses=4)
        docs.append(world)
    tables = [{p: (r["tag"], r["parent"], r["level"], count(d, p), bool(r.get("over"))) for p, r in roads_of(d).items()} for d in docs]
    assert tables[0] == tables[1] == tables[2]  # the same roads, parents, levels, houses and over flags: the tree is the plan, the order only places the ribs
    assert all(w["chronicle"] and all("over" in e for e in w["chronicle"]) for w in docs)  # ml holds 30 > 12 in every order: over, and nothing else happens


def test_min_houses_does_not_matter_in_mirror_mode():
    tree, items = make_tree(SPEC)
    library = {"items": items}
    a = bibliopolis.build_city(library, tree, mode="mirror", max_houses=12, min_houses=1)
    b = bibliopolis.build_city(library, tree, mode="mirror", max_houses=12, min_houses=12)
    assert as_text(a["places"]) == as_text(b["places"]) and as_text(a["roads"]) == as_text(b["roads"])
    assert a["world"]["districts"]["min"] == 1 and b["world"]["districts"]["min"] == 12  # (it is the rule's, and kept in the document)


def test_the_mirror_plan_has_a_street_for_every_road_and_the_grow_plan_does_not_fold_the_other_way():
    tree, items = make_tree(SPEC)
    tv = TreeView(tree)
    mirror_plan = plan_mod.build_plan(tv, items, mode="mirror")
    grow_plan = plan_mod.build_plan(tv, items, mode="grow")
    assert set(mirror_plan["streets"]) == {tag_street(x) for x in mirror_plan["roads"]}  # every road has its street in the plan
    assert "roads" not in grow_plan
    assert set(grow_plan["streets"]) < set(mirror_plan["streets"])  # the cut of grow mode folds small topics into a street and collapses chains: fewer streets
    assert all(not s["collapsed"] and not s["absorbed"] for s in mirror_plan["streets"].values())  # nothing is collapsed or folded in mirror mode


def test_the_document_of_a_mirror_city_is_sound_and_says_its_mode():
    tree, items = make_tree(SPEC)
    doc = bibliopolis.build_city({"items": items}, tree, mode="mirror")
    assert doc["world"]["mode"] == "mirror" and doc["world"]["houses"] == len(items) and doc["world"]["chronicle"] == []
    assert checks.document_problems(doc) == {}
    assert doc["composition"]["streets"]["total"] == 10 + 1 and doc["composition"]["streets"]["ring"] == 1  # ten roads and the ring road, which no house stands on: none has no topic
    text = bibliopolis.render(doc)
    assert json.loads(text)["world"]["mode"] == "mirror" and text == bibliopolis.render(bibliopolis.build_city({"items": items}, tree, mode="mirror"))


@pytest.mark.parametrize("seed", [0, 2, 4, 6])
def test_random_mirror_worlds_keep_every_invariant(seed):
    problems, doc, steps, plan, _tv = simulate_districts(seed, mode="mirror")
    assert problems == [] and steps > 0 and zw.houses(doc) and plan["mode"] == "mirror"
    assert doc["chronicle"] == [] or all("over" in e for e in doc["chronicle"])  # nothing splits, ever
    roads = roads_of(doc)
    assert set(roads) <= {tag_street(x) for x in plan["roads"]}  # a road stands once a house stands on it or below it


# ------------------------------------------------------------------------ an item filed under several topics ----
def two_branches():
    """Two roots with a child each, and one item filed under both children: its house stands once, the second topic is a road with no lots."""
    tree = {"nodes": [{"id": "a", "label": "A", "parent": None}, {"id": "x", "label": "X", "parent": "a"},
                      {"id": "b", "label": "B", "parent": None}, {"id": "y", "label": "Y", "parent": "b"}]}
    return tree, [art(1, ["y", "x"])]


def test_an_item_filed_under_two_branches_makes_a_road_on_each_and_its_house_stands_once_at_the_deepest_topic():
    tree, items = two_branches()
    doc = bibliopolis.build_city({"items": items}, tree, mode="mirror")
    places = doc["places"]
    roads = {p["tag"]: pid for pid, p in places.items() if p["kind"] == "street" and p.get("tag")}
    assert sorted(roads) == ["a", "b", "x", "y"]  # a road for every topic the item is filed under, and for the topics above them
    lots = [p for p in places.values() if p["kind"] == "lot"]
    assert len(lots) == doc["world"]["houses"] == 1 and lots[0]["parent"] == tag_street("x")  # one house, at the deepest topic (both are depth 2: the lower id)
    for name in ("a", "b", "y"):  # the roads that no house stands on: a road all the same, with a place, an address, a level and no lots
        rec = places[tag_street(name)]
        assert (rec["lots"], rec["reserved"]) == (0, 0) and "rib" not in rec and rec["address"][-1] == name.upper() and rec["level"] == len(rec["address"])
    assert places[tag_street("b")]["shape"] == "trunk" and places[tag_street("b")]["road"] in doc["roads"]  # a ring-1 road keeps its wedge and its spoke
    assert places[tag_street("y")]["parent"] == tag_street("b") and places[tag_street("x")]["parent"] == tag_street("a")
    assert checks.document_problems(doc) == {} and doc["composition"]["streets"]["total"] == 4 + 1  # (and the ring road)
    assert [r["place"] for r in doc["composition"]["ring1"]] == [tag_street("a"), tag_street("b")]


def test_two_roots_and_one_item_filed_under_both_make_two_roads_and_one_house():
    tree = {"nodes": [{"id": "a", "label": "A", "parent": None}, {"id": "b", "label": "B", "parent": None}]}
    doc = bibliopolis.build_city({"items": [art(1, ["a", "b"])]}, tree, mode="mirror")
    roads = {p["tag"]: p for p in doc["places"].values() if p["kind"] == "street" and p.get("tag")}
    assert sorted(roads) == ["a", "b"] and doc["world"]["houses"] == 1 and bibliopolis.summary(doc)["roads"] == 2 + 1  # (the ring road counts as one)
    assert roads["a"]["lots"] == 1 and (roads["b"]["lots"], roads["b"]["reserved"]) == (0, 0) and "rib" not in roads["b"]
    assert next(p for p in doc["places"].values() if p["kind"] == "lot")["parent"] == tag_street("a")  # both topics are depth 1: the lower id
    assert checks.document_problems(doc) == {}
    flipped = bibliopolis.build_city({"items": [art(1, ["b", "a"])]}, tree, mode="mirror")  # the order of the topics in the item does not matter
    assert bibliopolis.render(flipped) == bibliopolis.render(doc)


def test_in_grow_mode_the_same_item_makes_no_road_at_all():
    tree, items = two_branches()
    doc = bibliopolis.build_city({"items": items}, tree, mode="grow")
    assert doc["composition"]["streets"]["total"] == 1 and doc["composition"]["measure"]["ring_lots"] == 1  # roads open for houses, not for filing: the ring road alone


def test_a_topic_above_an_address_and_a_topic_beside_it_are_both_roads():
    tree = {"nodes": [{"id": "a", "label": "A", "parent": None}, {"id": "b", "label": "B", "parent": None}, {"id": "y", "label": "Y", "parent": "b"},
                      {"id": "z", "label": "Z", "parent": "y"}]}
    doc = bibliopolis.build_city({"items": [art(1, ["a", "z"])]}, tree, mode="mirror")  # the address is z (depth 3); a is filed only; b and y are above z
    roads = sorted(p["tag"] for p in doc["places"].values() if p["kind"] == "street" and p.get("tag"))
    assert roads == ["a", "b", "y", "z"] and doc["places"][tag_street("z")]["lots"] == 1 and doc["places"][tag_street("a")]["lots"] == 0
    assert checks.document_problems(doc) == {}


def test_a_filed_topic_that_is_the_town_hall_is_no_road_and_an_item_filed_only_there_stands_on_the_ring_road():
    tree = {"nodes": [{"id": "r", "label": "R", "parent": None}, {"id": "c", "label": "C", "parent": "r"}, {"id": "d", "label": "D", "parent": "r"}]}
    doc = bibliopolis.build_city({"items": [art(1, ["r"]), art(2, ["c", "d"])]}, tree, mode="mirror")
    assert sorted(p["tag"] for p in doc["places"].values() if p["kind"] == "street" and p.get("tag")) == ["c", "d"]  # r is the centre
    assert doc["composition"]["measure"]["ring_lots"] == 1 and doc["world"]["houses"] == 2


def test_the_mirror_plan_names_the_roads_of_every_filing_and_has_a_street_for_each():
    tree, items = two_branches()
    plan = plan_mod.build_plan(TreeView(tree), items, mode="mirror")
    assert plan["roads"] == ["a", "b", "x", "y"] and set(plan["streets"]) == {tag_street(t) for t in plan["roads"]}
    assert plan["streets"][tag_street("y")]["weight"] == 0 and plan["streets"][tag_street("x")]["weight"] == lay.rib_slots(1)
    assert [r["place"] for r in plan["ring1"]] == [tag_street("a"), tag_street("b")] and plan["trunks"][tag_street("b")]["role"] == "ring1"
    grown = plan_mod.build_plan(TreeView(tree), items, mode="grow")
    assert "roads" not in grown and tag_street("y") not in grown["streets"]


def test_the_roads_nobody_stands_on_are_made_by_complete_and_not_before():
    tree, items = two_branches()
    plan = plan_mod.build_plan(TreeView(tree), items, mode="mirror")
    doc = zw.new_world(plan)
    doc = zw.apply_delta(doc, zw.assign(plan, tree, doc, items)["delta"])
    assert sorted(p["tag"] for p in roads_of(doc).values()) == ["a", "x"]  # the road of the address and the one above it: what a house needs
    done = zw.complete(plan, tree, doc)
    assert sorted(t for t in (p.get("tag") for p in done["places"].values()) if t) == ["b", "y"] and done["delta"]["chronicle"] == doc["chronicle"]
    full = zw.apply_delta(doc, done["delta"])
    assert sorted(p["tag"] for p in roads_of(full).values()) == ["a", "b", "x", "y"] and full["seq"] == doc["seq"] == 1
    assert zw.complete(plan, tree, full)["delta"]["places"] == {} and zw.complete(plan, tree, full)["delta"]["roads"] == {}  # done once, done
    grow_plan = plan_mod.build_plan(TreeView(tree), items, mode="grow")
    grow = zw.new_world(grow_plan)
    assert zw.complete(grow_plan, tree, grow)["delta"]["places"] == {}  # a grow world has nothing to complete


def test_a_mirror_world_is_the_same_whether_its_arrivals_come_in_one_call_or_one_by_one():
    # a trunk with houses of its own and of four roads below it, a heavy path (m) and a side branch (q): the bands of the trunk fill up before the first
    # house of m arrives, so a member that opened early would start nearer the plaza than one that opens when its first house comes
    spec = {"a": T(12, a1=T(12), a2=T(12), a3=T(12), m=T(0, m1=T(8), m2=T(8)), q=T(0, q1=T(8), q2=T(8))), "b": T(3)}
    tree, items = make_tree(spec)
    by_tag(items, "m1")[0]["topics"].append("q2")  # an item of m1 also filed under q2: the same depth, the address is the lower id, m1
    by_tag(items, "q1")[0]["topics"].append("b")  # an item of q1 also filed under b: the address is the deeper one, q1
    plan = plan_mod.build_plan(TreeView(tree), items, mode="mirror", max_houses=12, min_houses=4, trunk_min=10)
    assert {r["role"] for r in plan["trunks"].values()} == {"ring1", "heavy", "side"}
    whole = zw.new_world(plan)
    whole = zw.apply_delta(whole, zw.assign(plan, tree, whole, items)["delta"])
    one = zw.new_world(plan)
    for a in items:
        one = zw.apply_delta(one, zw.assign(plan, tree, one, [a])["delta"])
    assert as_text(one["places"]) == as_text(whole["places"]) and as_text(one["lines"]) == as_text(whole["lines"])  # (nothing is made early: the geometry is the same)
    whole, one = (zw.apply_delta(d, zw.complete(plan, tree, d)["delta"]) for d in (whole, one))
    assert as_text(one["places"]) == as_text(whole["places"]) and as_text(one["roads"]) == as_text(whole["roads"]) and as_text(one["lines"]) == as_text(whole["lines"])
    assert {p["tag"] for p in roads_of(whole).values()} == set(plan["roads"])
    assert [m["s0"] for m in whole["lines"]["place:tag:a"]["members"]] == [9.0, 15.0]  # the trunk leaves the ring's outer edge (8.5 + 0.5); m opened at the frontier of a trunk whose bands had grown
    sound(whole, plan, tree)
