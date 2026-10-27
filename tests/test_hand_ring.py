"""The ring road in a world built by hand (docs/world.md, "The ring road" and "A new radius"): the world starts with it, `Knowledge` until `rename_road` with `road` null names
it, its gates are the spoke axes of all the N directions of the table so that no avenue that opens later moves a house of the ring, and its radius follows the rule: a `max`
that the first lap cannot hold, or another number of branches, lays the whole world out again, every house keeping its road and its place in the order along its street, every
avenue keeping its bearing."""

import copy
import math
import time

import checks
import pytest
from hand_support import (
    Hand,
    direction_violations,
    expansion_violations,
    hand_problems,
    hid,
    lot_snapshot,
    order_along,
    play,
    radius_of,
    ring_snapshot,
    stability_violations,
    text_problems,
    topic,
)
from support import capacity, cells_table, gates_of, radius_for, slot_cell

from bibliopolis import hand
from bibliopolis import layout as lay
from bibliopolis import world as zw
from bibliopolis.city import chronicle_lines
from bibliopolis.events import Problems, Refusal, check_event
from bibliopolis.journal import Journal, read_world, world_document

ROOT = "place:root"
TABLE13 = cells_table(13)
GATES = sorted({round((axis / 100) % 360, 3) for _, _, axis in TABLE13})  # the 13 spoke axes, stated apart from the engine
W_MIN = min(2 * min(axis - lo, hi - axis) for lo, hi, axis in TABLE13) / 100  # 20.06: the narrowest LAND, twice the narrower side of a spoke


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def sound(h):
    assert hand_problems(h.state) == [] and text_problems(h.state) == []
    assert stability_violations(h.journal.events, h.journal.rule) == [] and direction_violations(h.journal.events, h.journal.rule) == []
    return h.state


# ----------------------------------------------------------------------------------------------- day one ----
def test_the_world_starts_with_the_ring_road_and_nothing_else_not_even_a_house():
    h = Hand()
    state = h.state
    doc, plan = state.doc, state.plan
    assert sorted(doc["places"]) == ["place:plaza", ROOT] and sorted(doc["roads"]) == ["road:place:root"] and doc["lines"] == {} and doc["chronicle"] == []
    ring = plan["params"]["ring"]
    assert (ring["label"], ring["radius"]) == ("Knowledge", 8.5)
    assert ring["sectors"] == [[lo / 100, hi / 100] for lo, hi, _ in TABLE13] and ring["axes"] == [axis / 100 for _, _, axis in TABLE13]
    assert doc["places"][ROOT] == {"kind": "street", "shape": "ring", "level": 1, "class": "大道", "label": "Knowledge", "address": ["Knowledge"], "parent": "place:plaza",
                                   "lots": 0, "reserved": 0, "road": "road:place:root", "ring": {"lap": 1, "radius": 8.5, "slots": capacity(8.5, GATES), "gaps": GATES}}
    assert gates_of(plan) == GATES and len(GATES) == 13 and capacity(8.5, GATES) == 58
    city = state.city()
    assert sorted(city["places"]) == ["place:plaza", ROOT] and city["composition"]["ring1"] == [] and city["composition"]["measure"]["ring_lots"] == 0
    assert city["composition"]["streets"]["ring"] == 1 and hand_problems(state) == [] and checks.ring_problems(city) == []
    assert "underground" not in str(city) and "根區" not in str(city)


def test_the_radius_is_the_one_the_rule_asks_for_stated_apart_from_the_engine():
    assert radius_for(GATES, 40, W_MIN) == 8.5 == hand.ring_radius({"max": 40, "min": 10, "auto": False, "branches": 13})
    for top in (1, 8, 12, 40, 58, 59, 110, 150, 200, 300, 1000):
        assert hand.ring_radius({"max": top, "branches": 13}) == radius_for(GATES, top, W_MIN), top
    # up to 58 houses the cells decide (8.5: the narrowest land, 20.06 degrees, has an arc of 3.5 there); beyond it the houses decide
    assert hand.ring_radius({"max": 58, "branches": 13}) == 8.5 and hand.ring_radius({"max": 59, "branches": 13}) > 8.5
    assert (8.5 + 1.5) * math.radians(W_MIN) >= 3.0


def test_a_world_that_starts_with_a_big_max_or_other_branches_starts_with_a_big_ring():
    j = Journal({"max": 200, "min": 10, "auto": False})
    assert j.state.plan["params"]["ring"]["radius"] == radius_for(GATES, 200, W_MIN) and j.state.doc["places"][ROOT]["ring"]["radius"] == j.state.plan["params"]["ring"]["radius"]
    assert hand_problems(j.state) == []
    k = Journal({"max": 40, "min": 10, "auto": False, "branches": 34})
    ring = k.state.plan["params"]["ring"]
    assert len(ring["axes"]) == len(ring["sectors"]) == 34 and ring["radius"] == 21.5 and len(k.state.doc["places"][ROOT]["ring"]["gaps"]) == 34 and hand_problems(k.state) == []


# ----------------------------------------------------------------- the table of N: widths and radii as reported ----
@pytest.mark.parametrize("n, narrowest, widest, land, radius", [
    (5, 40.00, 40.00, 40.00, 8.5),
    (13, 26.26, 32.47, 20.06, 8.5),
    (21, 16.23, 20.07, 12.38, 12.5),
    (34, 10.03, 12.40, 7.66, 21.5),
    (89, 3.83, 4.74, 2.92, 57.5),
])
def test_the_widths_of_the_sectors_and_of_the_land_and_the_radius_for_the_numbers_of_branches_that_were_reported(n, narrowest, widest, land, radius):
    table = cells_table(n)
    widths = [(hi - lo) / 100 for lo, hi, _ in table]
    assert (min(widths), max(widths)) == (narrowest, widest)
    # the land of an avenue is the part of its sector within the narrower side of its spoke: its width is twice that side, and the narrowest land is the narrowest gap between bearings
    assert min(2 * min(axis - lo, hi - axis) for lo, hi, axis in table) / 100 == land
    gates = sorted({round((axis / 100) % 360, 3) for _, _, axis in table})
    assert radius_for(gates, 40, land) == hand.ring_radius({"max": 40, "branches": n}) == radius  # the radius of the rule: the narrowest LAND must hold the arc of an avenue
    assert radius_for(gates, 40, narrowest) <= radius  # (the narrowest sector would give a ring too small for the narrow side of its spoke: 8.5, 8.5, 9.5, 16.5, 43.5)


def test_a_plan_whose_radius_suits_the_sectors_but_not_the_lands_is_refused():
    plan = hand.new_plan({"max": 40, "min": 10, "auto": False, "branches": 21})
    assert plan["params"]["ring"]["radius"] == 12.5
    plan["params"]["ring"]["radius"] = 9.5  # the narrowest sector (16.23 degrees) has its arc of 3 cells there; the narrowest land (12.38) has 2.4
    with pytest.raises(ValueError, match="narrowest land"):
        zw.PlanView(plan)
    plan["params"]["ring"]["radius"] = 12.5
    assert zw.PlanView(plan).sector_min() == 12.38
    plan["params"]["ring"]["radius"] = 13.5  # the plan is the authority: a larger radius is a plan
    assert zw.PlanView(plan).ring["radius"] == 13.5


def test_the_radius_never_falls_when_the_branches_grow():
    last = 0.0
    for n in range(2, 201):
        r = hand.ring_radius({"max": 40, "branches": n})
        assert r >= last, n
        last = r
    assert hand.ring_radius({"max": 40, "branches": 200}) > hand.ring_radius({"max": 40, "branches": 13})


# --------------------------------------------------------------- the geometry of N avenues, N = 5, 13, 21, 34, 89 ----
def bearing_in(lo, hi, deg):
    return any(lo - 1e-9 <= deg + turn <= hi + 1e-9 for turn in (-360.0, 0.0, 360.0))


@pytest.mark.parametrize("n", [5, 13, 21, 34, 89])
def test_every_avenue_of_a_ring_of_n_branches_keeps_all_its_lots_inside_its_sector_and_no_roads_cross(n):
    h = Hand({"max": 40, "min": 3, "auto": False, "branches": n})
    sizes = [3 + 9 * (k % 5) for k in range(n)]  # 3, 12, 21, 30, 39 houses: long streets and short ones
    h.add(sum(sizes) + 6)
    left = h.state.houses_at(None)
    start = 0
    for k in range(n):
        h.open(f"r{k}", f"Road {k}", None, left[start:start + sizes[k]])
        start += sizes[k]
    state = h.state
    assert hand_problems(state) == [] and len(state.children(None)) == n  # (the checks of the engine: no crossing, no road through a lot, every lot inside the wedge of its trunk)
    city = state.city()
    rows = {r["place"]: r for r in city["composition"]["ring1"]}
    assert len(rows) == n
    lots = lot_snapshot(state)
    for key in state.nodes:
        row = rows[f"place:tag:{key}"]
        for article, lot in lots.items():
            if state.road_of[article] == key:
                x, z = lot["position"]["x"], lot["position"]["z"]
                bearing = math.degrees(math.atan2(x, -z)) % 360
                assert bearing_in(row["from"], row["to"], bearing), (key, article, bearing, row["from"], row["to"])  # no lot outside its sector
    # the spoke of an avenue runs on the bearing of its number
    for k, key in sorted(state.held.items()):
        assert round(city["places"][f"place:tag:{key}"]["axis"] * 100) == cells_table(n)[k][2]


# ------------------------------------------------------------------------------------ houses on the ring ----
def test_the_houses_stand_on_the_ring_from_north_clockwise_and_a_full_lap_goes_on_as_a_lap():
    h = Hand()
    h.add(60, topic(1, 1, 1, 1))
    city = sound(h).city()
    lots = lot_snapshot(h.state)
    for i in range(1, 59):
        (x, z), _facing = slot_cell(8.5, GATES, i - 1)
        assert lots[hid(i)]["parent"] == ROOT and (lots[hid(i)]["position"]["x"], lots[hid(i)]["position"]["z"]) == (round(x, 3), round(z, 3)), i
    assert [lots[hid(i)]["parent"] for i in (59, 60)] == ["place:root:lap:2"] * 2
    lap2 = city["places"]["place:root:lap:2"]
    assert lap2["ring"]["radius"] == 11.5 == 8.5 + 3.0 and lap2["label"] == "Knowledge" and lap2["lane_of"] == ROOT  # no road is open: back to back
    assert city["composition"]["streets"]["ring"] == 2 and city["composition"]["measure"]["ring_lots"] == 60


def test_an_avenue_that_opens_in_any_of_the_thirteen_directions_moves_no_house_of_the_ring():
    h = Hand({"max": 40, "min": 3, "auto": False})
    h.add(70)
    before = lot_snapshot(h.state)
    left = houses(1, 70)
    for k in range(13):  # thirteen avenues, each taking three houses of the ring: the gates were all there from day one
        h.open(f"r{k}", f"Road {k}", None, left[3 * k:3 * k + 3])
        after = lot_snapshot(h.state)
        for x in left[3 * (k + 1):]:
            if before[x]["parent"] == ROOT:
                assert after[x] == before[x], (k, x)  # every house still on the ring stands where it stood
        sound(h)
    assert sorted(h.state.held) == list(range(13)) and len(h.state.nodes) == 13
    spoke = h.state.doc["roads"]["road:place:tag:r0"]
    assert spoke["s0"] == 9.0 == 8.5 + 0.5  # an avenue leaves the outer edge of the ring
    for line in h.state.doc["lines"].values():  # ... and nothing of an avenue stands nearer than the outer edge of the ring's outer row (R + 1.5): a spoke rib starts there or later, a band is 3 across
        assert all(lo >= 8.5 + 1.5 - 1e-9 for lo, _ in line["spokes"]) and all(b["s"] - 1.5 >= 8.5 + 1.5 - 1e-9 for b in line["bands"])


# ------------------------------------------------------------------------------------------------ renaming ----
def test_the_ring_road_is_renamed_with_a_null_road_and_its_laps_follow():
    h = Hand()
    h.add(60, topic(1, 1, 1, 1))
    e = h.rename(None, "Inbox")
    assert e["payload"] == {"road": None, "name": "Inbox"}
    state = sound(h)
    city = state.city()
    assert city["places"][ROOT]["label"] == "Inbox" and city["places"][ROOT]["address"] == ["Inbox"]
    assert city["places"]["place:root:lap:2"]["label"] == "Inbox" and city["places"]["place:root:lap:2"]["address"] == ["Inbox"]
    entry = city["world"]["chronicle"][-1]
    assert (entry["trigger"], entry["renamed"], entry["was"], entry["label"]) == ("rename_road", ROOT, "Knowledge", "Inbox")
    assert chronicle_lines(city)[-1].split(": ", 1)[1] == "Knowledge is renamed Inbox."
    h.add(1)
    h.open("a", "A", None, houses(1, 40))
    assert sound(h).city()["places"][ROOT]["label"] == "Inbox"
    with pytest.raises(Refusal) as why:
        h.rename(None, "Inbox")
    assert (why.value.code, why.value.params) == ("same_name", {"road": None, "name": "Inbox"}) and "the ring road is called 'Inbox' already" in str(why.value)
    h.undo(61)  # the rename: nothing names it
    assert sound(h).city()["places"][ROOT]["label"] == "Knowledge"


def test_a_lap_that_opens_after_the_rename_has_the_new_name():
    h = Hand()
    h.add(50, topic(1, 1, 1, 1))
    h.rename(None, "Inbox")
    h.add(15, topic(1, 1, 1, 1))
    assert sound(h).city()["places"]["place:root:lap:2"]["label"] == "Inbox"


def test_the_shape_of_a_rename_allows_a_null_road_and_nothing_else_that_is_not_text():
    for road, ok in ((None, True), ("a", True), (3, False), ("", False), ([], False)):
        problems = Problems()
        got = check_event({"seq": 1, "at": "2026-01-01", "kind": "rename_road", "payload": {"road": road, "name": "X"}}, "event", problems)
        assert (got is not None) == ok, road


# ----------------------------------------------------------------------------------------- a new radius ----
def scene(rule=None):
    """A town with an avenue, a road below it, a continuation rib, holes in front of houses, and a second lap on the ring: the world that a resize must put again."""
    h = Hand(rule or {"max": 30, "min": 5, "auto": False})
    h.add(130, topic(1, 1, 1, 1))
    h.open("a", "Alpha", None, houses(1, 36))  # 36 houses: a first rib and a continuation
    h.open("b", "Beta", None, houses(40, 60))
    h.open("a1", "Alpha one", "a", houses(5, 14))
    h.file(hid(2), "b")  # holes
    h.file(hid(70), "a")
    h.file(hid(71), "a1")
    return h


def test_a_max_that_the_first_lap_cannot_hold_lays_the_world_out_again_in_the_order_along_the_streets():
    h = scene()
    kept, before_lots = ring_snapshot(h.state), lot_snapshot(h.state)
    assert radius_of(h.state) == 8.5
    h.rule(200, 5)  # the ring road must hold 200 houses between its gates now
    state = sound(h)
    want = radius_for(GATES, 200, W_MIN)
    assert radius_of(state) == want > 8.5 and state.doc["places"][ROOT]["ring"]["radius"] == want
    assert expansion_violations(kept, state) == []
    assert order_along(state) == kept[0]  # no house passed another, on the ring or on any road
    lots = lot_snapshot(state)
    assert {x for x in lots if lots[x] != before_lots[x]} == set(lots)  # every house stands on another lot: the radius moved the avenues and the cells
    assert state.doc["roads"]["road:place:tag:a"]["s0"] == want + 0.5
    assert all(b["s"] >= want + 3.0 for line in state.doc["lines"].values() for b in line["bands"])
    first, second = state.city()["world"]["chronicle"][-2:]
    assert (first["trigger"], first["rule"]) == ("set_rule", {"max": 200, "min": 5, "auto": False, "branches": 13})
    assert (second["trigger"], second["resized"], second["was_radius"], second["radius"], second["was_branches"], second["branches"]) == ("set_rule", ROOT, 8.5, want, 13, 13)
    assert len(second["houses"]) == len(state.items) and second["houses"][:3] == order_along(state)[ROOT][:3]  # the ring road's houses first, in the order they stood
    assert chronicle_lines(state.city())[-1].split(": ", 1)[1] == f"the ring road Knowledge grows from radius 8.5 to {want:g}; {len(state.items)} houses are put again, in the order they stood."


def test_a_hole_closes_when_the_world_is_laid_out_again_and_the_lap_count_follows_the_new_ring():
    h = Hand({"max": 40, "min": 3, "auto": False})
    h.add(130, topic(1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 20))  # twenty holes at the front of the ring road
    assert sorted({lot["slot"] for lot in lot_snapshot(h.state).values() if lot["parent"] == ROOT})[:3] == [20, 21, 22]
    h.rule(200, 3)
    state = sound(h)
    on_ring = sorted(lot["slot"] for lot in lot_snapshot(state).values() if lot["parent"] == ROOT)
    assert on_ring == list(range(110)) and "lanes" not in state.doc["places"][ROOT]  # the hole closed: the 110 houses of the ring fill the first lap, from slot 0
    assert state.doc["places"][ROOT]["ring"]["slots"] >= 200


def test_a_smaller_max_that_asks_for_a_smaller_ring_lays_the_world_out_again_on_it():
    h = scene()
    h.rule(200, 5)
    big = radius_of(h.state)
    kept = ring_snapshot(h.state)
    h.rule(40, 5)  # back to what the sectors alone ask for
    state = sound(h)
    assert radius_of(state) == 8.5 and expansion_violations(kept, state) == []
    second = state.city()["world"]["chronicle"][-1]
    assert (second["was_radius"], second["radius"]) == (big, 8.5)
    assert chronicle_lines(state.city())[-1].split(": ", 1)[1].startswith(f"the ring road Knowledge shrinks from radius {big:g} to 8.5;")


def test_a_rule_that_keeps_the_radius_changes_nothing_but_the_rule():
    h = scene()
    before = lot_snapshot(h.state)
    h.rule(58, 5)  # 58 houses fit in the first lap at 8.5: the radius is the same
    assert sound(h).city()["world"]["chronicle"][-1].keys() >= {"rule"} and lot_snapshot(h.state) == before
    assert not [e for e in h.state.city()["world"]["chronicle"] if "resized" in e]


def test_undoing_a_resize_gives_the_world_back_as_it_was():
    h = scene()
    h.rule(200, 5)
    h.file(hid(100), "b")  # a later event names a house the resize put again: it depends on nothing the resize did
    h.undo(len(h.journal.events) - 1)  # the set_rule that resized
    state = sound(h)
    assert radius_of(state) == 8.5 and state.rule["max"] == 30
    assert state.road_of[hid(100)] == "b"


def test_the_resize_keeps_the_arrival_numbers_the_chronicle_and_the_sectors_of_the_avenues():
    h = scene()
    seq = {x: lot["seq"] for x, lot in lot_snapshot(h.state).items()}
    chronicle = [dict(e) for e in h.state.city()["world"]["chronicle"]]
    sectors = h.state.city()["composition"]["ring1"]
    h.rule(200, 5)
    state = sound(h)
    assert {x: lot["seq"] for x, lot in lot_snapshot(state).items()} == seq
    assert state.city()["world"]["chronicle"][:len(chronicle)] == chronicle and state.city()["composition"]["ring1"] == sectors


def test_a_max_of_a_hundred_thousand_is_a_ring_of_eight_thousand_cells_and_is_laid_out_in_a_blink():
    h = Hand({"max": 40, "min": 3, "auto": False})
    h.add(400, topic(1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 200))
    start = time.perf_counter()
    h.rule(100_000, 3)
    took = time.perf_counter() - start
    assert took < 10.0, took  # (the walk to the radius starts at the lower bound the houses give: it was minutes before)
    assert radius_of(h.state) == radius_for(GATES, 100_000, W_MIN) == hand.ring_radius({"max": 100_000, "branches": 13}) and radius_of(h.state) > 7000
    assert hand_problems(h.state) == []


# ----------------------------------------------------------------------------- another number of branches ----
def test_raising_the_branches_lays_the_world_out_again_every_bearing_stays_every_sector_narrows_or_stays():
    h = scene()
    kept = ring_snapshot(h.state)
    h.rule(30, 5, False, 21)
    state = sound(h)
    assert state.rule["branches"] == 21 and expansion_violations(kept, state) == []
    assert len(state.plan["params"]["ring"]["axes"]) == 21 and radius_of(state) == hand.ring_radius({"max": 30, "branches": 21}) == 12.5
    rows = {r["place"]: r for r in state.city()["composition"]["ring1"]}
    for key, (lo, hi, axis) in zip(("a", "b"), (cells_table(21)[0], cells_table(21)[1])):
        assert (rows[f"place:tag:{key}"]["from"], rows[f"place:tag:{key}"]["to"], rows[f"place:tag:{key}"]["axis"]) == (lo / 100, hi / 100, axis / 100)
    first, second = state.city()["world"]["chronicle"][-2:]
    assert first["rule"]["branches"] == 21 and (second["resized"], second["was_branches"], second["branches"], second["was_radius"], second["radius"]) == (ROOT, 13, 21, 8.5, 12.5)
    assert chronicle_lines(state.city())[-1].split(": ", 1)[1] == f"the ring road Knowledge grows from radius 8.5 to 12.5 as the branches go from 13 to 21; {len(state.items)} houses are put again, in the order they stood."


def test_raising_the_branches_without_a_new_radius_still_lays_the_world_out_again_for_the_gates_are_more():
    h = scene({"max": 30, "min": 5, "auto": False, "branches": 8})
    assert radius_of(h.state) == 8.5
    kept = ring_snapshot(h.state)
    h.rule(30, 5, False, 13)
    state = sound(h)
    assert radius_of(state) == 8.5 and expansion_violations(kept, state) == []
    second = state.city()["world"]["chronicle"][-1]
    assert (second["resized"], second["was_radius"], second["radius"], second["was_branches"], second["branches"]) == (ROOT, 8.5, 8.5, 8, 13)
    assert chronicle_lines(state.city())[-1].split(": ", 1)[1] == f"the ring road Knowledge keeps radius 8.5 as the branches go from 8 to 13; {len(state.items)} houses are put again, in the order they stood."


def test_lowering_the_branches_widens_the_sectors_and_lays_the_world_out_again():
    h = scene({"max": 30, "min": 5, "auto": False, "branches": 21})
    kept = ring_snapshot(h.state)
    h.rule(30, 5, False, 13)
    state = sound(h)
    assert expansion_violations(kept, state) == [] and state.rule["branches"] == 13


def test_the_branches_cannot_fall_below_a_direction_number_that_an_avenue_holds_nor_below_the_roads_a_road_holds():
    h = Hand({"max": 40, "min": 3, "auto": False})
    h.add(60)
    for k in range(10):
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None)[:3])
    for k in (3, 4, 5, 6, 7):  # avenues 3 to 7 move below r0: their directions are free, the numbers 8 and 9 are still held
        h.move(f"r{k}", "r0")
    assert sorted(h.state.held) == [0, 1, 2, 8, 9] and len(h.state.children(None)) == 5 and len(h.state.children("r0")) == 5
    before = (len(h.journal.events), dict(h.state.held), h.state.plan["params"]["ring"]["radius"])
    with pytest.raises(Refusal) as why:
        h.rule(40, 3, False, 6)  # five avenues, so the count would allow 6; the numbers 8 and 9 do not exist in a table of 6
    assert (why.value.code, why.value.params) == ("branches_below_standing", {"road": None, "needs": 10, "branches": 6})
    assert "6 branches would leave the world over: an avenue holds the direction number 9, so the rule needs 10 at least" in str(why.value)
    assert (len(h.journal.events), dict(h.state.held), h.state.plan["params"]["ring"]["radius"]) == before
    with pytest.raises(Refusal) as why:
        h.rule(40, 3, False, 9)
    assert why.value.params["needs"] == 10
    h.rule(40, 3, False, 10)  # the least that keeps number 9
    assert sound(h).rule["branches"] == 10
    for k in (8, 9):  # the two avenues that hold 8 and 9 move below r0: now r0 holds 7 roads
        h.move(f"r{k}", "r0")
    assert h.state.least_branches() == (7, "r0")
    with pytest.raises(Refusal) as why:
        h.rule(40, 3, False, 6)
    assert (why.value.code, why.value.params) == ("branches_below_standing", {"road": "r0", "needs": 7, "branches": 6}) and "the road 'r0' holds 7 roads" in str(why.value)
    h.rule(40, 3, False, 7)
    assert sound(h).rule["branches"] == 7


def test_the_branches_are_two_at_the_least_and_a_thousand_at_the_most_and_default_to_thirteen():
    for bad in (1, 0, -3, 1001, 2.5, "13", True, None):
        with pytest.raises(Refusal):
            Journal({"max": 40, "min": 10, "auto": False, "branches": bad})
    assert Journal({"max": 40, "min": 10, "auto": False}).rule["branches"] == 13
    assert Journal({"max": 40, "min": 10, "auto": False, "branches": 2}).rule["branches"] == 2
    assert Journal({"max": 40, "min": 10, "auto": False, "branches": 1000}).rule["branches"] == 1000
    j = Journal()
    with pytest.raises(Refusal, match="missing branches"):
        j.append("set_rule", {"max": 40, "min": 10, "auto": True}, "2026-01-01")  # a set_rule event carries every key


def test_the_branches_full_refusal_names_the_road_and_the_remedy_at_every_level():
    h = Hand({"max": 40, "min": 3, "auto": False, "branches": 3})
    h.add(40)
    h.open("a", "A", None, houses(1, 30))
    for k in range(3):
        h.open(f"a{k}", f"A{k}", "a", h.state.houses_at("a")[:3])
    with pytest.raises(Refusal) as why:
        h.open("a3", "A3", "a", h.state.houses_at("a")[:3])
    err = why.value
    assert (err.code, err.params) == ("branches_full", {"road": "a", "limit": 3, "number": 4, "remedy": "merge_roads"})
    assert str(err).startswith("the road 'a' holds 3 roads directly, the most the rule allows (branches 3), so the 4th category goes below one of them, or similar roads are merged")
    h.open("b", "B", None, houses(31, 40))
    with pytest.raises(Refusal) as why:
        h.move("b", "a")  # a move below a full road is refused in the same way
    assert (why.value.code, why.value.params["road"], why.value.params["number"]) == ("branches_full", "a", 4)
    assert hand_problems(h.state) == []


# ----------------------------------------------------------------------------------------------- the oracles ----
def test_the_oracle_is_red_when_the_world_is_laid_out_in_the_order_the_houses_arrived_and_not_in_the_order_they_stand(monkeypatch):
    original = hand.State.layout_order

    def by_arrival(self):
        return [(place, sorted(lots, key=lambda lot: lot["seq"])) for place, lots in original(self)]

    h = scene()
    monkeypatch.setattr(hand.State, "layout_order", by_arrival)
    h.rule(200, 5)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and any("do not stand along it in the order they did" in line for line in found)


def test_the_oracle_is_red_when_a_resize_changes_the_road_of_a_house(monkeypatch):
    original = hand.State.relay

    def forgetful(self, e):
        w, base, put = original(self, e)
        self.road_of[hid(7)] = None  # a house falls back to the ring road
        return w, base, put

    h = scene()
    monkeypatch.setattr(hand.State, "relay", forgetful)
    h.rule(200, 5)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert any("changed road" in line for line in found)


def test_the_oracle_is_red_when_the_branches_turn_a_spoke_or_widen_a_sector_as_they_grow():
    h = scene()
    kept = ring_snapshot(h.state)
    h.rule(30, 5, False, 21)
    state = h.state
    assert expansion_violations(kept, state) == []
    turned = (kept[0], kept[1], kept[2], {k: (lo, hi, axis + 1.0) for k, (lo, hi, axis) in kept[3].items()}, kept[4])  # as if the spokes had been at other bearings before
    assert any("turned" in line for line in expansion_violations(turned, state))
    narrower = (kept[0], kept[1], kept[2], {k: (lo + 1.0, hi - 1.0, axis) for k, (lo, hi, axis) in kept[3].items()}, kept[4])  # as if the sectors had been narrower before
    assert any("did not narrow or stay" in line for line in expansion_violations(narrower, state))


def test_the_check_of_the_world_is_red_when_the_plan_asks_for_a_radius_the_world_does_not_have():
    h = scene()
    h.rule(200, 5)
    state = copy.copy(h.state)
    state.plan = copy.deepcopy(h.state.plan)
    state.plan["params"]["ring"]["radius"] = 8.5  # the plan says 8.5 and the world stands on a larger ring
    assert hand_problems(state)


@pytest.mark.parametrize("seed", [0, 1, 2, 4, 5, 8])
def test_a_random_player_whose_rule_changes_a_max_and_the_branches_now_and_then_leaves_a_sound_stable_world(seed):
    journal = play(seed, steps=170, resizing=True, merging=True, suggested=True)
    state = journal.state
    assert hand_problems(state) == [] and text_problems(state) == []
    assert stability_violations(journal.events, journal.rule) == [] and direction_violations(journal.events, journal.rule) == []
    assert [e for e in state.city()["world"]["chronicle"] if "resized" in e]  # (these seeds put the world out again)


def test_the_text_of_the_city_after_a_resize_is_the_same_in_every_fold_and_the_world_file_reads_back():
    h = scene()
    h.rule(200, 5)
    h.rule(200, 5, False, 21)
    again = read_world(world_document(h.journal))
    assert lay.render(again.state.city()) == lay.render(h.state.city())
