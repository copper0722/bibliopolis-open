"""The geometry checks of the tests (tests/checks.py) find what they are meant to find at every radius.

`overlaps` and `roads_through_lots` compare angles on a lane. They allowed a fixed 0.02 degrees for the rounding of the positions (three decimals), which is the width of a lot from the
radius 1432 on: beyond it the allowance was wider than the lot, the threshold went negative and no lot was ever found to overlap or to have a road through it. The allowance is a length
along the lane now (`checks.EDGE`, 0.003 cell), so that it shrinks as an angle when the lane widens. A planted fault at each radius is found, and its confusable twin (one cell off, or
touching) is not: a detector that never fires is no check."""

import math

import checks
import pytest

from support import five_degree_arc

from bibliopolis import layout as lay

RADII = [8.5, 100.0, 1000.0, 1500.0, 7964.5]  # the last is the radius of the ring road of the review (max 100000), where the arc of a street had two points


def lot_at(places, name, radius, bearing, lane):
    xz = lay.polar_xz(radius, bearing)
    places[name] = {"kind": "lot", "parent": lane, "position": {"x": lay.r3(xz[0]), "z": lay.r3(xz[1])}}


def ring_layout(radius, lots, roads=None):
    """A lap of the ring road of lane radius `radius` with lots `[(name, row radius, bearing)]` on it and the roads `{id: [[x, z], ...]}`, as a document of a city holds them."""
    places = {"place:root": {"kind": "street", "shape": "ring", "ring": {"lap": 1, "radius": radius, "slots": 1_000_000, "gaps": []}}}
    for name, rho, bearing in lots:
        lot_at(places, name, rho, bearing, "place:root")
    return {"places": places, "roads": {rid: {"points": pts} for rid, pts in (roads or {}).items()}, "centre": {"radius": 6.0}}


def chord(radius, sagitta):
    """The chord of the circle of `radius` whose middle is `sagitta` cells inside it, from north, with the bearing of its middle: ([[x, z], [x, z]], bearing in degrees)."""
    half = math.acos(1 - sagitta / radius)  # radians
    ends = [lay.pt(lay.polar_xz(radius, 0.0)), lay.pt(lay.polar_xz(radius, math.degrees(2 * half)))]
    return ends, math.degrees(half)


@pytest.mark.parametrize("radius", RADII)
def test_a_road_that_cuts_through_a_lot_is_found_whatever_the_radius(radius):
    ends, middle = chord(radius, 1.0)  # the middle of the chord is on the inner row of the lap, one cell inside the lane
    layout = ring_layout(radius, [("lot", radius - 1.0, middle)], {"road": ends})
    found = checks.roads_through_lots(layout)
    assert found and set(found) == {("road", "lot")}


@pytest.mark.parametrize("radius", RADII)
def test_a_road_that_runs_beside_a_lot_is_not_found_whatever_the_radius(radius):
    ends, middle = chord(radius, 1.0)
    layout = ring_layout(radius, [("outer", radius + 1.0, middle)], {"road": ends})  # the outer row: two cells from the middle of the chord
    assert checks.roads_through_lots(layout) == []
    ends, _ = chord(radius, 0.0001)  # a chord that is the lane itself, to the rounding of three decimals
    assert checks.roads_through_lots(ring_layout(radius, [("inner", radius - 1.0, 0.0), ("outer", radius + 1.0, 0.0)], {"road": ends})) == []


@pytest.mark.parametrize("radius", RADII)
def test_two_lots_that_overlap_are_found_and_two_that_touch_are_not_whatever_the_radius(radius):
    half = math.degrees(0.5 / radius)  # half a cell along the lane
    overlapping = ring_layout(radius, [("a", radius + 1.0, 10.0), ("b", radius + 1.0, 10.0 + half)])
    assert checks.overlaps(overlapping) == [("a", "b")]
    touching = ring_layout(radius, [("a", radius + 1.0, 10.0), ("b", radius + 1.0, 10.0 + 2 * half)])  # one cell apart: next to each other in a row
    assert checks.overlaps(touching) == []


def test_the_allowance_for_the_rounding_is_a_length_along_the_lane_so_that_in_angle_it_shrinks_with_the_radius_and_never_passes_a_lot():
    assert checks.EDGE == 0.003  # (positions are rounded to 0.001: a point moves by 0.0014 cell at the most)
    for radius in (8.5, 850.0, 7964.5):
        assert 0 < math.degrees(checks.EDGE / radius) < math.degrees(0.5 / radius) / 100  # under a hundredth of half a lot, at every radius
    assert math.degrees(0.5 / 1431.0) > 0.02 > math.degrees(0.5 / 1433.0)  # the fixed 0.02 degrees was wider than half a lot from the radius 1432 on


def test_a_far_arc_drawn_a_chord_every_5_degrees_runs_through_its_inner_row_and_the_chord_rule_keeps_it_on_its_lane():
    """A lane at radius 7964.5 from bearing 10 to 14 degrees (556 cells) with a lot on each row of every cell. Drawn a chord every 5 degrees (one chord) its middle lies 4.85 cells inside
    the circle, and the road runs through the inner row near both ends: the check flags those lots. Drawn by the chord rule (10 chords, at most 0.05 cell inside the circle) the road is
    clear of both rows."""
    radius, a, b = 7964.5, 10.0, 14.0
    cells = int(radius * math.radians(b - a))  # whole cells along the lane
    places = {"place:s": {"kind": "street", "parent": "place:plaza"}, "place:s:rib": {"kind": "rib", "parent": "place:s", "rib": {"s": radius, "band": 0}}}
    for c in range(cells):
        theta = a + math.degrees((c + 0.5) / radius)
        places[f"lot:{c}:in"] = lay.lot_record(f"a{c}i", "place:s:rib", c, 2 * c, lay.polar_xz(radius - 1, theta), theta)
        places[f"lot:{c}:out"] = lay.lot_record(f"a{c}o", "place:s:rib", c, 2 * c + 1, lay.polar_xz(radius + 1, theta), theta + 180)
    old = {"places": places, "roads": {"road:s": {"points": five_degree_arc(radius, a, b)}}}
    new = {"places": places, "roads": {"road:s": {"points": lay.arc_points(radius, a, b)}}}
    assert cells == 556 and len(old["roads"]["road:s"]["points"]) == 2 and len(new["roads"]["road:s"]["points"]) == 11
    flagged = {lot for _rid, lot in checks.roads_through_lots(old)}
    assert len(flagged) > 40 and all(lot.endswith(":in") for lot in flagged)  # the inner row, near both ends of the chord
    assert {int(lot.split(":")[1]) < cells // 2 for lot in flagged} == {True, False}
    assert checks.roads_through_lots(new) == [] and checks.overlaps(new) == []
