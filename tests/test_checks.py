"""The geometry checks of the tests (tests/checks.py) find what they are meant to find at every radius.

`overlaps` and `roads_through_lots` compare angles on a lane. They allowed a fixed 0.02 degrees for the rounding of the positions (three decimals), which is the width of a lot from the
radius 1432 on: beyond it the allowance was wider than the lot, the threshold went negative and no lot was ever found to overlap or to have a road through it. The allowance is a length
along the lane now (`checks.LANE_ROUNDING`), so that it shrinks as an angle when the lane widens. A planted fault at each radius is found, and its confusable twin (one cell off, or
touching) is not: a detector that never fires is no check."""

import math

import checks
import pytest

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


def test_the_allowance_for_the_rounding_is_a_length_along_the_lane_and_was_0_02_degrees_at_the_first_ring():
    assert checks.rounding_degrees(8.5) == pytest.approx(0.02) and checks.rounding_degrees(850.0) == pytest.approx(0.0002)
    assert checks.rounding_degrees(7964.5) < math.degrees(0.5 / 7964.5) / 100  # at the radius of the review it is a hundredth of a lot
