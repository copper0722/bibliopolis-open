"""The mirror mode: the topic tree is the street plan (docs/engine.md).

Every topic that holds an item, directly or below, is a road from the start. Nothing splits: a road that holds more than `max` houses is `over`, and
the chronicle says when. An item with no topic (or the topic that is the town hall itself) lives in the root zone. Chains are not collapsed and
nothing is folded into a leaf: one topic, one road.
"""

import json

import checks
import pytest
from support import ROOT, T, Town, art, as_text, by_tag, count, make_tree, ribs_of, roads_of, simulate_districts, stamp, tag_street

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


def test_items_with_no_topic_and_the_town_hall_topic_live_in_the_root_zone():
    spec = {"sci": T(3, a=T(5), b=T(5))}  # one root: it is the town hall; its own 3 houses and the 3 without a topic live underground
    t = Town(spec, mode="mirror", **SMALL)
    assert t.plan["params"]["centre_tag"] == "sci" and t.plan["roads"] == ["a", "b"]  # the centre is no road
    loose = [art(900 + i, []) for i in range(3)]
    t.send(t.items + loose, event_id=1)
    assert count(t.doc, ROOT) == 6 and count(t.doc, tag_street("a")) == 5 and set(roads_of(t.doc)) == {tag_street("a"), tag_street("b")}
    assert all(road_of_(t.doc, a) == ROOT for a in by_tag(t.items, "sci") + loose)
    assert t.doc["places"][ROOT]["lots"] == 6 and all(p.get("underground") for p in t.doc["places"].values() if p["kind"] == "lot" and p["street"] == ROOT)


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
    assert doc["composition"]["streets"]["total"] == 10 and doc["composition"]["streets"]["underground"] == 0  # no house under the plaza: none has no topic
    text = bibliopolis.render(doc)
    assert json.loads(text)["world"]["mode"] == "mirror" and text == bibliopolis.render(bibliopolis.build_city({"items": items}, tree, mode="mirror"))


@pytest.mark.parametrize("seed", [0, 2, 4, 6])
def test_random_mirror_worlds_keep_every_invariant(seed):
    problems, doc, steps, plan, _tv = simulate_districts(seed, mode="mirror")
    assert problems == [] and steps > 0 and zw.houses(doc) and plan["mode"] == "mirror"
    assert doc["chronicle"] == [] or all("over" in e for e in doc["chronicle"])  # nothing splits, ever
    roads = roads_of(doc)
    assert set(roads) <= {tag_street(x) for x in plan["roads"]}  # a road stands once a house stands on it or below it
