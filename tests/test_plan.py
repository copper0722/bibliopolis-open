"""The plan (bibliopolis.cut, bibliopolis.plan): which topics are streets, how the circle is shared, which child continues a trunk.

The plan reads the whole library once and pins the directions of the city before the first house arrives. Every number below follows from the rules
of docs/engine.md: a rib of n lots weighs 1 + n + max(2, ceil(n / 4)), a street holds H = 20 lots in a rib, a sector is not narrower than 14 degrees."""

import json
import math
import random

import pytest
from support import T, make_tree

from bibliopolis import cut
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis.tree import TreeView


def plan_of(spec, **kw):
    tree, items = make_tree(spec)
    return plan_mod.build_plan(TreeView(tree), items, **kw), tree, items


def weight(n):
    return lay.rib_slots(n)


def test_the_circle_is_shared_in_proportion_to_weight_centred_on_north():
    plan, _tree, _items = plan_of({"a": T(30), "b": T(30)})
    assert [r["wedge"] for r in plan["ring1"]] == [[-180.0, 0.0], [0.0, 180.0]]  # equal weight: half each; the sectors start at the south and go round clockwise
    plan, _tree, _items = plan_of({"a": T(90), "b": T(30)})
    spans = [r["wedge"][1] - r["wedge"][0] for r in plan["ring1"]]
    assert sum(spans) == 360 and plan["ring1"][0]["wedge"][0] == -180.0 and spans[0] > 2 * spans[1]  # the heavier root has the wider sector
    assert [r["weight"] for r in plan["ring1"]] == [4 * weight(20) + weight(10), weight(20) + weight(10)] == [118, 40]  # ribs of 20 lots, and what is left


def test_no_sector_is_narrower_than_14_degrees_while_there_is_room_and_they_share_what_there_is_when_there_is_not():
    plan, _t, _i = plan_of({"big": T(300), "small": T(3)})
    assert plan["ring1"][1]["wedge"][1] - plan["ring1"][1]["wedge"][0] == 14.0
    many, _t, _i = plan_of({f"r{i:02d}": T(5) for i in range(40)})  # 40 sectors of at least 14 degrees do not fit in 360: they share it
    spans = [r["wedge"][1] - r["wedge"][0] for r in many["ring1"]]
    assert abs(sum(spans) - 360) < 0.4 and max(spans) - min(spans) < 0.02 and spans[0] < 14


def test_a_tree_with_one_root_has_the_root_as_its_centre_and_its_children_as_ring_one():
    plan, _t, _i = plan_of({"root": T(2, a=T(30), b=T(30))})
    assert plan["params"]["centre_tag"] == "root"
    assert [r["place"] for r in plan["ring1"]] == ["place:tag:root", "place:tag:a", "place:tag:b"]  # (the root's own houses get a sector too: see docs/engine.md)
    plan, _t, _i = plan_of({"r1": T(30), "r2": T(30)})
    assert plan["params"]["centre_tag"] is None


def test_a_topic_with_at_most_20_houses_below_it_is_a_leaf_street_that_holds_everything_below_it():
    plan, _t, _i = plan_of({"top": T(0, small=T(6, s1=T(5), s2=T(4)), big=T(0, b1=T(30), b2=T(25)))})
    streets = plan["streets"]
    small = streets["place:tag:small"]
    assert small["kind"] == "leaf" and small["absorbed"] == ["s1", "s2"] and small["ribs"] == [15] and small["weight"] == weight(15)
    assert plan["sites"]["s1"] == plan["sites"]["s2"] == "place:tag:small"  # a topic folded into a leaf is held by it
    big = streets["place:tag:big"]
    assert big["kind"] == "container" and big["ribs"] == []  # no house of its own, and a weight that is the weight of the streets below it
    assert streets["place:tag:b1"]["ribs"] == [20, 10] and streets["place:tag:b2"]["ribs"] == [20, 5] and streets["place:tag:b1"]["kind"] == "leaf"  # 30 and 25 lots
    assert big["weight"] == (weight(20) + weight(10)) + (weight(20) + weight(5)) == 74


def test_a_container_with_no_house_of_its_own_and_one_child_with_houses_is_collapsed_into_the_child():
    plan, _t, _i = plan_of({"a": T(0, mid=T(0, deep=T(25))), "b": T(25)})
    street = plan["streets"]["place:tag:deep"]
    assert street["collapsed"] == ["a", "mid"] and street["name"] == "deep" and street["label"] == "A・Mid・Deep" and street["address"] == ["A・Mid・Deep"]
    assert "place:tag:a" not in plan["streets"] and plan["sites"]["a"] == plan["sites"]["mid"] == "place:tag:deep"
    assert [r["place"] for r in plan["ring1"]] == ["place:tag:deep", "place:tag:b"]  # the ring-1 street is the deepest topic of the chain, in the place of its root
    plan, _t, _i = plan_of({"a": T(1, mid=T(0, deep=T(25))), "b": T(25)})  # a house of its own: not a chain
    assert "place:tag:a" in plan["streets"] and plan["streets"]["place:tag:a"]["kind"] == "container"


def test_a_topic_with_no_house_at_or_below_it_has_no_street():
    plan, _t, _i = plan_of({"a": T(25, ghost=T(0, deeper=T(0))), "b": T(0, void=T(0), c=T(25), d=T(25))})
    assert "place:tag:ghost" not in plan["streets"] and "place:tag:void" not in plan["streets"] and "place:tag:deeper" not in plan["streets"]
    assert plan["sites"]["ghost"] == plan["sites"]["deeper"] == "place:tag:a"  # under a leaf street an empty topic is folded in with the rest
    assert "void" not in plan["sites"]  # under a container street it is nothing at all


def test_the_heaviest_container_child_continues_the_trunk_and_each_other_child_takes_the_lighter_side():
    spec = {"top": T(0, c1=T(0, x=T(100), y=T(100)), c2=T(0, x2=T(50), y2=T(50)), c3=T(0, x3=T(40), y3=T(40)), c4=T(0, x4=T(30), y4=T(30))), "other": T(25)}
    plan, _t, _i = plan_of(spec, trunk_min=40)
    top = plan["trunks"]["place:tag:top"]
    assert top["role"] == "ring1" and top["heavy"] == "place:tag:c1"  # the heaviest container continues straight
    sides = {s["place"] for s in top["left"] + top["right"]}
    # c2 (132) goes left (both sides are empty: the left one on a tie), c3 (104) to the lighter right, c4 (80) to the right again (104 < 132)
    assert sides == {"place:tag:c2", "place:tag:c3", "place:tag:c4"} and [s["place"] for s in top["left"]] == ["place:tag:c2"]
    assert [s["place"] for s in top["right"]] == ["place:tag:c3", "place:tag:c4"]
    assert plan["trunks"]["place:tag:c1"]["role"] == "heavy" and plan["trunks"]["place:tag:c3"]["role"] == "side" and plan["trunks"]["place:tag:c3"]["side"] == 1
    assert plan["trunks"]["place:tag:c2"]["side"] == -1 and plan["trunks"]["place:tag:c4"]["parent"] == "place:tag:top"
    lo, hi = top["wedge"]
    for side in (*top["left"], *top["right"]):  # every side wedge lies inside the wedge of the trunk, and the central wedge is what is left
        assert lo <= side["wedge"][0] < side["wedge"][1] <= hi
    assert lo <= top["inner"][0] < top["inner"][1] <= hi


def test_a_container_under_the_weight_line_is_no_trunk_and_hangs_on_the_trunk_above():
    plan, _t, _i = plan_of({"top": T(0, c1=T(0, x=T(30), y=T(30)), c2=T(0, x2=T(25), y2=T(25))), "other": T(25)}, trunk_min=10_000)
    assert [p for p, t in plan["trunks"].items()] == ["place:tag:other", "place:tag:top"]  # only the ring-1 streets are trunks
    assert plan["streets"]["place:tag:c1"]["carrier"] == "place:tag:top" and plan["streets"]["place:tag:x"]["carrier"] == "place:tag:top"


def test_the_plan_does_not_depend_on_the_order_of_the_items_or_of_the_nodes():
    tree, items = make_tree({"a": T(10, a1=T(30), a2=T(25)), "b": T(0, b1=T(0, b2=T(22))), "c": T(8)})
    shuffled_items = list(items)
    shuffled_nodes = list(tree["nodes"])
    rng = random.Random(5)
    rng.shuffle(shuffled_items)
    rng.shuffle(shuffled_nodes)
    one = plan_mod.build_plan(TreeView(tree), items)
    two = plan_mod.build_plan(TreeView({"nodes": shuffled_nodes}), shuffled_items)
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True) and json.dumps(one) == json.dumps(plan_mod.build_plan(TreeView(tree), items))


def test_the_mirror_plan_makes_every_topic_that_holds_a_house_a_street_and_names_them():
    tree, items = make_tree({"a": T(0, mid=T(0, deep=T(25)), side=T(3)), "b": T(2), "empty": T(0, void=T(0))})
    tv = TreeView(tree)
    plan = plan_mod.build_plan(tv, items, mode="mirror")
    assert plan["roads"] == ["a", "b", "deep", "mid", "side"] and set(plan["streets"]) == {f"place:tag:{x}" for x in plan["roads"]}
    assert plan["streets"]["place:tag:mid"]["parent"] == "place:tag:a" and plan["streets"]["place:tag:deep"]["parent"] == "place:tag:mid"
    grown = plan_mod.build_plan(tv, items, mode="grow")
    assert "roads" not in grown and "place:tag:mid" not in grown["streets"]  # grow folds the chain a > mid into deep, mirror does not


def test_the_cut_counts_the_houses_of_each_topic_and_below_it():
    tree, items = make_tree({"a": T(3, b=T(4, c=T(5)), d=T(2)), "e": T(1)})
    comp = cut.compose(TreeView(tree), items)
    assert comp.sub == {"a": 14, "b": 9, "c": 5, "d": 2, "e": 1} and comp.centre_tag is None and comp.topic_roots == ["a", "e"]
    assert comp.holders() == ["a", "b", "c", "d", "e"]
    assert {k: len(n.direct) for k, n in comp.nodes.items()} == {"a": 3, "b": 4, "c": 5, "d": 2, "e": 1}
    assert comp.role == {"a": "leaf", "b": "interior", "c": "interior", "d": "interior", "e": "leaf"}  # a holds 14 <= 20: a leaf street, everything below is folded
    whole = cut.compose(TreeView(tree), items, whole_tree=True)
    assert {k: v for k, v in whole.role.items()} == {"a": "container", "b": "container", "c": "leaf", "d": "leaf", "e": "leaf"}


@pytest.mark.parametrize("home_max", [5, 20, 33])
def test_a_street_with_more_lots_than_a_rib_holds_has_overflow_lanes_of_the_same_size(home_max):
    tree, items = make_tree({"a": T(home_max * 2 + 3), "b": T(1)})
    plan = plan_mod.build_plan(TreeView(tree), items, home_max=home_max)
    assert plan["streets"]["place:tag:a"]["ribs"] == [home_max, home_max, 3]
    assert plan["streets"]["place:tag:a"]["weight"] == 2 * lay.rib_slots(home_max) + lay.rib_slots(3)
    assert math.isclose(sum(r["weight"] for r in plan["ring1"]), plan["streets"]["place:tag:a"]["weight"] + plan["streets"]["place:tag:b"]["weight"])


def test_the_plan_is_json_and_a_plan_view_reads_it_back():
    plan, tree, items = plan_of({"a": T(30), "b": T(30)})
    again = json.loads(json.dumps(plan))
    assert again == plan
    from bibliopolis import world as zw
    assert zw.PlanView(again).districts == {"max": 40, "min": 10, "extract": "largest", "count": "direct"} and zw.PlanView(again).mode == "grow"
    with pytest.raises(ValueError, match="mode"):
        zw.PlanView({**plan, "mode": "both"})
