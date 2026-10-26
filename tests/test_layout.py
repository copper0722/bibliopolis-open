"""The vocabulary of the document (bibliopolis.layout) and the coast (bibliopolis.coast): angles, geometry, records, the measures and the text."""

import json
import math
from pathlib import Path

import pytest
from support import T, make_tree

import bibliopolis
from bibliopolis import coast
from bibliopolis import layout as lay

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------------------------------------ angles ----
def test_allocate_shares_a_total_in_proportion_to_the_weights_and_the_parts_add_up():
    assert lay.allocate(100, [1, 3], [0, 0]) == [25, 75]
    assert lay.allocate(36000, [1, 1], [1400, 1400]) == [18000, 18000]
    assert lay.allocate(10, [1, 1, 1], [0, 0, 0]) == [4, 3, 3]  # the largest remainder wins, ties go to the lower index
    assert lay.allocate(7, [0, 0], [0, 0]) == [4, 3]  # a weight of nothing counts as one
    assert lay.allocate(100, [], []) == []
    rng_cases = [([5, 9, 1, 1, 200], [14, 14, 14, 14, 14]), ([1] * 7, [3] * 7), ([100, 1], [100, 100]), ([2, 2, 2], [50, 1, 1])]
    for weights, mins in rng_cases:
        parts = lay.allocate(1000, weights, mins)
        assert sum(parts) == 1000 and all(p >= m for p, m in zip(parts, mins)) and len(parts) == len(weights)


def test_allocate_keeps_a_minimum_even_when_the_weight_alone_would_give_less_and_shares_the_minimums_when_they_do_not_fit():
    assert lay.allocate(1000, [100, 1], [100, 100]) == [900, 100]
    assert lay.allocate(100, [5, 5], [80, 80]) == [50, 50]  # the minimums alone ask for more than there is: they share it in proportion to themselves
    assert lay.allocate(100, [1, 1, 1], [60, 60, 60]) == [34, 33, 33]


def test_a_wedge_knows_its_span_axis_and_half_angle():
    w = lay.Wedge(-3000, 6000)
    assert (w.span, w.axis, w.half) == (9000, 15.0, 45.0)


def test_a_wedge_is_split_into_a_central_wedge_and_side_wedges_that_cover_it_exactly():
    class S:
        def __init__(self, weight):
            self.weight = weight

    wedge = lay.Wedge(-9000, 9000)
    central, left, right = lay.split_wedge(wedge, S(300), [S(200), S(100)], [S(150)])
    assert central.lo > wedge.lo and central.hi < wedge.hi and central.lo + central.hi == wedge.lo + wedge.hi  # the heavy child keeps the axis of its parent
    assert [w.span for w in left + right] and left[0].lo == wedge.lo and left[-1].hi == central.lo and right[-1].hi == wedge.hi and right[0].lo == central.hi
    assert sum(w.span for w in left) == central.lo - wedge.lo == wedge.hi - central.hi == sum(w.span for w in right)  # both sides have the same angle
    assert left[0].span >= left[1].span  # the heaviest child is outermost and widest
    assert lay.split_wedge(wedge, S(1), [], []) == (wedge, [], [])


# --------------------------------------------------------------------------------------------- geometry ----
def test_bearings_run_clockwise_from_north_with_x_east_and_z_south():
    for deg, want in ((0, (0, -10)), (90, (10, 0)), (180, (0, 10)), (270, (-10, 0))):
        x, z = lay.polar_xz(10, deg)
        assert (round(x, 9), round(z, 9)) == want
    x, z = lay.frame_xz(90, 5, 2)  # 5 along the spoke that points east, 2 to its right (south)
    assert (round(x, 9), round(z, 9)) == (5, 2)


def test_the_display_class_of_a_ring_saturates_at_the_alley():
    assert [lay.class_of(r) for r in (1, 2, 3, 4, 5, 30)] == ["大道", "路", "巷", "弄", "弄", "弄"]


def test_numbers_are_rounded_to_three_decimals_and_minus_zero_is_zero():
    assert lay.r3(1.23456) == 1.235 and str(lay.r3(-0.0000001)) == "0.0" and lay.pt((1.00049, -2.0006)) == [1.0, -2.001]


def test_an_arc_has_a_point_every_five_degrees_at_most_and_ends_where_it_is_asked_to():
    pts = lay.arc_points(10.0, 0.0, 22.0)
    assert len(pts) == 6 and pts[0] == lay.pt(lay.polar_xz(10.0, 0.0)) and pts[-1] == lay.pt(lay.polar_xz(10.0, 22.0))
    assert len(lay.arc_points(10.0, 5.0, 5.0)) == 2


def test_a_street_of_the_plan_weighs_its_lots_and_the_empty_lots_kept_for_growth():
    assert [lay.rib_slots(n) for n in (0, 1, 8, 20)] == [3, 4, 11, 26]  # 1 + n + max(2, ceil(n / 4))


def test_the_records_of_a_lot_an_empty_lot_and_a_road_have_the_keys_the_format_names():
    assert lay.lot_record("x", "place:tag:a", 3, 3, (1.0004, -2.0), 370.0) == {"kind": "lot", "article": "x", "parent": "place:tag:a", "order": 3, "slot": 3,
                                                                              "position": {"x": 1.0, "z": -2.0}, "facing": 10.0}
    assert lay.reserved_record("place:tag:a", 4, "tail", (0.0, 1.0), 90.0) == {"kind": "reserved", "parent": "place:tag:a", "slot": 4, "end": "tail",
                                                                              "position": {"x": 0.0, "z": 1.0}, "facing": 90.0}
    road = lay.road_record("place:tag:a", "lane", 2, "road:p", 1.5, [[0.0, 0.0], [1.0, 0.0]], 1.0, band=0)
    assert road == {"street": "place:tag:a", "kind": "lane", "class": "路", "parent": "road:p", "at": 1.5, "length": 1.0, "band": 0, "points": [[0.0, 0.0], [1.0, 0.0]]}
    assert (lay.article_place("i1"), lay.tag_place("a"), lay.lane_place("a", 2), lay.reserved_place("a", 7)) == ("place:article:i1", "place:tag:a", "place:lane:a:2",
                                                                                                             "place:reserved:a:7")


# ----------------------------------------------------------------------------------------------- the text ----
@pytest.fixture(scope="module")
def city():
    tree = json.loads((EXAMPLES / "tree.json").read_text(encoding="utf-8"))
    library = json.loads((EXAMPLES / "library.json").read_text(encoding="utf-8"))
    return bibliopolis.build_city(library, tree, mode="grow")


def test_the_text_is_json_with_one_road_and_one_place_per_line(city):
    text = lay.render(city)
    assert json.loads(text) == json.loads(json.dumps(city)) and text.endswith("}\n") and "\r" not in text
    lines = text.splitlines()
    road_lines = [line for line in lines if line.startswith('  "road:')]
    place_lines = [line for line in lines if line.startswith('  "place:')]
    assert len(road_lines) == len(city["roads"]) and len(place_lines) == len(city["places"])
    assert [json.loads("{" + line.rstrip(",") + "}") for line in road_lines[:2]] == [{k: city["roads"][k]} for k in list(city["roads"])[:2]]
    assert list(city["roads"]) == sorted(city["roads"]) and list(city["places"]) == sorted(city["places"])  # sorted by id
    assert lay.render(city) == text  # (rendering changes nothing)


def test_the_text_of_a_town_hall_with_no_road_is_still_json():
    doc = bibliopolis.build_city({"items": []}, {"nodes": []})
    assert json.loads(lay.render(doc))["roads"] == {} and lay.render(doc).count('"roads": {') == 1


# ---------------------------------------------------------------------------------------------- measures ----
def test_the_measures_agree_with_the_document_they_are_read_from(city):
    m = city["composition"]["measure"]
    lots = [p for p in city["places"].values() if p["kind"] == "lot"]
    assert m["lots"] == sum(1 for p in lots if not p.get("underground")) and m["underground_lots"] == sum(1 for p in lots if p.get("underground"))
    assert m["lots"] + m["underground_lots"] == city["world"]["houses"] == 600 and m["roads"] == len(city["roads"])
    assert 0 < m["walk_median"] <= m["walk_longest"] and 0 < m["walk_mean"] <= m["walk_longest"]
    surface = max(math.hypot(p["position"]["x"], p["position"]["z"]) for p in lots if not p.get("underground"))
    assert m["max_radius"] == round(surface + 0.71, 1)  # the farthest cell, to its far corner
    assert sum(m["streets_by_class"].values()) == city["composition"]["streets"]["total"] and m["max_ring"] == max(p["level"] for p in city["places"].values() if p["kind"] == "street" and not p.get("underground"))
    assert [r["span"] for r in m["ring1_wedges"]] == [r["span"] for r in city["composition"]["ring1"]]
    assert round(sum(r["length"] for r in city["roads"].values()), 1) == m["road_length"]


# ----------------------------------------------------------------------------------------------- the coast ----
def inside(poly, x, z):
    """Ray casting: whether (x, z) lies inside the polygon."""
    hit = False
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        if (az > z) != (bz > z) and x < (bx - ax) * (z - az) / (bz - az) + ax:
            hit = not hit
    return hit


def test_the_land_holds_every_house_on_the_surface_and_every_road_and_the_plaza(city):
    polys = city["coast"]["polygons"]
    assert polys and city["coast"]["buffer"] == coast.COAST_BUFFER and city["coast"]["tolerance"] == coast.COAST_TOLERANCE
    ok = lambda x, z: any(inside(p, x, z) for p in polys)  # noqa: E731
    assert all(ok(p["position"]["x"], p["position"]["z"]) for p in city["places"].values() if p["kind"] == "lot")
    assert all(ok(x, z) for r in city["roads"].values() for x, z in r["points"]) and ok(0.0, 0.0) and ok(lay.PLAZA_RADIUS, 0.0)
    assert not ok(500.0, 500.0)
    assert round(sum(coast.polygon_area(p) for p in polys), 1) == city["composition"]["measure"]["land_area"]  # the land of the measures is the land of the coast


def test_the_land_of_a_town_hall_with_nothing_else_is_a_disc_round_the_plaza():
    doc = bibliopolis.build_city({"items": []}, {"nodes": []})
    (poly,) = doc["coast"]["polygons"]
    radii = [math.hypot(x, z) for x, z in poly]
    assert min(radii) > lay.PLAZA_RADIUS and max(radii) < lay.PLAZA_RADIUS + coast.COAST_BUFFER + 2


def test_the_land_grows_with_the_houses_and_the_underground_houses_do_not_count():
    tree, items = make_tree({"a": T(9), "b": T(9), "c": T(9)})  # nothing leaves the root zone: no road, no surface lot
    under = bibliopolis.build_city({"items": items}, tree)
    none = bibliopolis.build_city({"items": []}, tree)
    assert under["coast"] == none["coast"] and under["composition"]["measure"]["underground_lots"] == 27
    tree, items = make_tree({"a": T(45), "b": T(9)})
    assert bibliopolis.build_city({"items": items}, tree)["composition"]["measure"]["land_area"] > none["composition"]["measure"]["land_area"]


def test_a_wedge_too_narrow_for_the_minimums_scales_them_down_together_and_no_part_is_empty():
    class S:
        def __init__(self, weight):
            self.weight = weight

    wedge = lay.Wedge(0, 1000)  # 10 degrees: the minimums (4 per side, 8 central) alone would need 16 or more
    central, left, right = lay.split_wedge(wedge, S(100), [S(50), S(50)], [S(50), S(50)])
    parts = [central.span, *(w.span for w in left + right)]
    assert all(p >= 1 for p in parts) and sum(w.span for w in left) + central.span + sum(w.span for w in right) == wedge.span
    assert left[0].lo == wedge.lo and right[0].hi == wedge.hi and left[-1].hi == central.lo and right[-1].lo == central.hi  # (the heaviest child of a side is outermost: first)
