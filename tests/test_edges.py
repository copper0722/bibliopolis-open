"""Libraries and trees at the edges: nothing, one root, many roots, a long chain. Both modes build them and the geometry stays sound."""

import checks
import pytest
from support import art

import bibliopolis


def tree(*nodes):
    return {"nodes": [{"id": i, "label": i.upper(), "parent": p} for i, p in nodes]}


def build(nodes, items, mode, **kw):
    doc = bibliopolis.build_city({"items": items}, nodes, mode=mode, **kw)
    assert checks.document_problems(doc) == {}
    assert doc["world"]["houses"] == doc["composition"]["articles"] == len(items)
    return doc, bibliopolis.summary(doc)


CHAIN = tree(("c0", None), *[(f"c{i}", f"c{i - 1}") for i in range(1, 60)])


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_an_empty_tree_and_an_empty_library_make_the_town_hall_alone(mode):
    doc, s = build({"nodes": []}, [], mode)
    assert list(doc["places"]) == ["place:plaza"] and doc["roads"] == {} and doc["composition"]["ring1"] == [] and doc["world"]["chronicle"] == []
    assert s == {"mode": mode, "houses": 0, "roads": 0, "underground": 0, "splits": 0, "over": 0}
    assert doc["coast"]["polygons"] and doc["composition"]["measure"]["lots"] == 0
    doc, s = build(tree(("a", None), ("b", "a")), [], mode)  # a tree with no item is the same city
    assert list(doc["places"]) == ["place:plaza"] and s["houses"] == 0


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_items_with_no_topic_stay_under_the_town_hall_and_the_root_zone_is_over_when_it_holds_more_than_max(mode):
    doc, s = build(tree(("a", None)), [art(i, []) for i in range(1, 70)], mode)
    assert (s["roads"], s["underground"], s["splits"], s["over"]) == (0, 69, 0, 1)
    assert doc["places"]["place:root"]["over"] is True and doc["world"]["chronicle"][0] == {**doc["world"]["chronicle"][0], "over": "place:root", "count": 41}


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_a_tree_with_one_root_and_every_item_on_the_root_has_no_road_at_all(mode):
    doc, s = build(tree(("only", None)), [art(i, ["only"]) for i in range(1, 101)], mode)
    assert (s["roads"], s["underground"]) == (0, 100) and doc["centre"]["tag"] == "only"


def test_many_roots_share_the_circle_and_a_root_with_few_items_opens_no_road_in_grow_mode():
    roots = [(f"q{i}", None) for i in range(200)]
    items = [art(i * 3 + k + 1, [f"q{i}"]) for i in range(200) for k in range(3)]  # 200 roots of 3 items: no group of 10 anywhere
    grown, g = build(tree(*roots), items, "grow")
    assert (g["roads"], g["underground"], g["over"]) == (0, 600, 1)
    mirrored, m = build(tree(*roots), items, "mirror")
    assert (m["roads"], m["underground"], m["over"]) == (200, 0, 0)
    assert len(mirrored["composition"]["ring1"]) == 200 and abs(sum(r["span"] for r in mirrored["composition"]["ring1"]) - 360) < 0.1 + 200 * 0.01


def test_sixty_roots_of_a_random_library_in_both_modes():
    roots = [(f"r{i}", None) for i in range(60)]
    items = [art(i, [f"r{(i * 7919) % 60}"]) for i in range(1, 900)]
    assert build(tree(*roots), items, "mirror")[1]["roads"] == 60
    assert build(tree(*roots), items, "grow")[1]["roads"] > 40


def test_a_chain_of_sixty_levels_is_one_road_in_grow_mode_and_a_road_for_every_level_in_mirror_mode():
    items = [art(i, ["c59"]) for i in range(1, 120)]
    doc, s = build(CHAIN, items, "grow")
    road = next(p for p in doc["places"].values() if p["kind"] == "street" and p.get("tag") == "c59")
    assert s["roads"] == 1 and len(road["collapsed"]) == 58 and road["label"].count("・") == 58 and road["over"] is True  # c0 is the centre: 58 topics are collapsed
    doc, s = build(CHAIN, items, "mirror")
    assert s["roads"] == 59 and doc["composition"]["measure"]["max_ring"] == 59
    assert doc["places"]["place:tag:c59"]["address"][0] == "C1" and len(doc["places"]["place:tag:c59"]["address"]) == 59


def test_items_at_every_level_of_a_long_chain():
    items = [art(i, [f"c{i % 60}"]) for i in range(1, 300)]
    for mode in ("grow", "mirror"):
        build(CHAIN, items, mode)


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_one_topic_of_four_hundred_items(mode):
    doc, s = build(tree(("a", None), ("b", None)), [art(i, ["a"]) for i in range(1, 401)], mode)
    assert s["roads"] == 1 and s["over"] == 1 and doc["composition"]["streets"]["continuations"] >= 9  # 400 houses in ribs of at most 40 lots
