"""A world built by hand (bibliopolis.hand): the directions of the first ring, and what each kind of event does to the world, what it refuses, and what an undo takes back."""

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import checks
import pytest
from hand_support import Hand, hand_problems, hid, lot_snapshot, play, stamp, text_problems
from support import cells_table, fill_order_of

import bibliopolis
from bibliopolis import hand, inputs, picture, plan
from bibliopolis import layout as lay
from bibliopolis.city import chronicle_lines, summary
from bibliopolis.events import Refusal
from bibliopolis.hand import GOLDEN, bearing, fold, sector_table
from bibliopolis.journal import Journal
from bibliopolis.tree import TreeView

ROOT = Path(__file__).resolve().parents[1]
FILL = fill_order_of(58)  # the ring of the default rule: 13 gates at radius 8.5 leave 29 cells and 58 slots; a house takes the first free slot in this order (0, 29, 14, 43, 7, ...)
FIRST_RING = [(-1623, 1003, 0), (12128, 14754, 13751), (-10121, -7495, -8498), (3629, 6256, 5252), (-18620, -15994, -16997), (-4869, -1623, -3246), (8882, 12128, 10505),
              (-13368, -10121, -11745), (1003, 3629, 2006), (14754, 17380, 15757), (-7495, -4869, -6492), (6256, 8882, 7259), (-15994, -13368, -14991)]  # the thirteen sectors of a
# ring road of 13 branches, (lo, hi, axis) in units of 1/100 degree: the spoke is on the bearing of the number, the sector is its nearest-bearing cell


def sound(h):
    assert hand_problems(h.state) == []
    return h.state


def town(n=15, rule=None):
    h = Hand(rule)
    h.add(n)
    return h


def snapshot(h):
    return len(h.journal.events), lay.render(h.state.city(with_coast=False)), dict(h.state.road_of), copy.deepcopy(h.state.nodes)


def refuses(h, fragment, kind, payload):
    """The world refuses the event, says why, and is as it was."""
    before = snapshot(h)
    with pytest.raises(Refusal) as why:
        h.event(kind, payload)
    assert fragment in str(why.value), str(why.value)
    assert snapshot(h) == before
    return why.value


def the_street(h, key):
    return h.state.doc["places"][lay.tag_place(key)]


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


# ------------------------------------------------------------------------------------------ the directions ----
def test_the_bearing_of_the_k_th_road_is_k_golden_angles_in_units_of_a_hundredth_of_a_degree():
    assert GOLDEN == 13750776405003785 and GOLDEN / 10**12 / lay.UNIT == pytest.approx(137.50776405003785)
    assert [bearing(k) for k in range(14)] == [0, 13751, 27502, 5252, 19003, 32754, 10505, 24255, 2006, 15757, 29508, 7259, 21009, 34760]
    assert all(0 <= bearing(k) < lay.FULL for k in range(500))
    assert bearing(1000) == (1000 * 13750776405003785 + 5 * 10**11) // 10**12 % lay.FULL  # whole-number arithmetic whatever k is


def test_the_sector_of_a_direction_is_the_cell_nearest_its_bearing_among_the_bearings_cut_to_twenty_degrees_either_side():
    assert list(sector_table(13)) == FIRST_RING == cells_table(13)  # the table of the default, stated twice: written out here, and found by looking at every other bearing
    spans = [hi - lo for lo, hi, _ in FIRST_RING]
    assert sorted(set(spans)) == [2626, 2627, 3246, 3247] and sum(spans) == lay.FULL  # the cells tile the circle: nothing is left
    assert [hand.tenths(x) for x in spans] == [263, 263, 263, 263, 263, 325, 325, 325, 263, 263, 263, 263, 263]  # in tenths: the hundredths are the tiling, not a difference
    for k, (lo, hi, axis) in enumerate(FIRST_RING):
        assert axis % lay.FULL == bearing(k) and lo <= axis <= hi  # the spoke runs ON the bearing, which lies inside the sector, not always in the middle of it
        assert -lay.FULL // 2 <= axis <= lay.FULL // 2 and hi - lo <= 2 * 2000  # the axis is kept between -180 and 180 degrees, and no sector is wider than 40
    assert FIRST_RING[0] == (-1623, 1003, 0) and (1003 - 0, 0 - -1623) == (1003, 1623)  # the first bearing has 10.03 degrees to its right, 16.23 to its left: not the middle
    assert sector_table(1) == ((-2000, 2000, 0),) and sector_table(2)[0] == (-2000, 2000, 0)  # alone, or with room all round: 20 degrees either side
    assert sector_table(2)[1] == (13751 - 2000, 13751 + 2000, 13751)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233])
def test_the_table_the_engine_makes_is_the_table_found_by_looking_at_every_other_bearing(n):
    assert list(sector_table(n)) == cells_table(n)
    cells = sector_table(n)
    assert len({axis % lay.FULL for _, _, axis in cells}) == n  # no two directions share a bearing


def test_a_larger_n_moves_no_bearing_and_only_narrows_the_sectors():
    for n in range(1, 120):
        before, after = sector_table(n), sector_table(n + 1)
        for k in range(n):
            assert after[k][2] == before[k][2], (n, k)  # the spoke of a direction never turns
            assert after[k][0] >= before[k][0] and after[k][1] <= before[k][1], (n, k)  # its sector narrows or stays


@pytest.mark.parametrize("n", range(1, 130))
def test_the_cells_of_n_directions_tile_the_circle_as_far_as_the_cut_to_twenty_degrees_leaves_them(n):
    cells = sorted(sector_table(n), key=lambda c: c[2] % lay.FULL)
    for here, there in zip(cells, cells[1:] + cells[:1]):
        gap = (there[2] - here[2]) % lay.FULL or lay.FULL
        cut = here[1] - here[2] == 2000 or there[2] - there[0] == 2000
        assert cut or (here[1] - here[2]) + (there[2] - there[0]) == gap, (n, here, there)  # the two halves of the gap are the two cells' shares of it, or one is cut


def test_the_land_of_an_avenue_is_the_part_of_its_sector_within_the_narrower_side_of_its_spoke():
    for n in (1, 5, 13, 21, 34, 89):
        for lo, hi, axis in sector_table(n):
            land_lo, land_hi = hand.land_of(lo, hi, axis)
            assert land_lo >= lo and land_hi <= hi and (land_lo + land_hi) == 2 * axis  # inside the sector, and the spoke is the middle of it
            assert min(axis - land_lo, land_hi - axis) == min(axis - lo, hi - axis) and land_hi - axis == axis - land_lo


def test_a_town_has_as_many_avenues_as_branches_and_the_next_category_goes_below_an_avenue():
    h = town(10, {"max": 40, "min": 10, "auto": False, "branches": 5})
    for k in range(5):
        if k:
            h.add(10)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None)[:10])
    h.add(10)
    err = refuses(h, "the ring road holds 5 avenues directly, the most the rule allows (branches 5), so the 6th category goes below one of them, "
                     "or similar avenues are merged under a new one (merge_roads) to make room", "open_road",
                  {"road": "r5", "name": "Road 5", "parent": None, "houses": h.state.houses_at(None)[:10]})
    assert err.code == "branches_full" and err.params == {"road": None, "limit": 5, "number": 6, "remedy": "merge_roads"}  # the id and the values a page translates from


# ----------------------------------------------------------------------------------------------- add_item ----
def test_an_item_becomes_a_house_on_the_ring_road_and_the_town_has_no_road_but_the_ring_yet():
    h = town(3)
    state = sound(h)
    city = state.city()
    assert [state.road_of[hid(i)] for i in (1, 2, 3)] == [None] * 3 and list(state.nodes) == []
    assert summary(city) == {"mode": "hand", "houses": 3, "roads": 1, "ring": 3, "splits": 0, "over": 0}
    lots = lot_snapshot(state)
    assert [lots[hid(i)]["slot"] for i in (1, 2, 3)] == FILL[:3] == [0, 29, 14] and all(lots[hid(i)]["parent"] == "place:root" for i in (1, 2, 3))
    assert city["places"]["place:root"]["label"] == "Knowledge" and city["places"]["place:root"]["lots"] == 3
    assert city["world"]["mode"] == "hand" and city["world"]["chronicle"] == [] and city["composition"]["ring1"] == []
    assert state.items[hid(2)]["title"] == "Title 2" and state.items[hid(2)]["openalex"] == []


def test_an_item_that_is_a_house_already_is_refused_and_may_come_again_after_an_undo():
    h = town(2)
    refuses(h, "'h0001' is a house already", "add_item", {"item": h.state.items[hid(1)]})
    h.undo(1)  # the first house is taken back ...
    assert list(h.state.items) == [hid(2)]
    h.event("add_item", {"item": {**h.state.items[hid(2)], "id": hid(1)}})  # ... and its id is free again
    assert list(h.state.items) == [hid(2), hid(1)]
    sound(h)


def test_a_41st_house_just_lands_on_the_ring_nothing_splits_nothing_is_over_and_the_chronicle_stays_empty():
    h = town(41)
    state = sound(h)
    city = state.city()
    assert summary(city) == {"mode": "hand", "houses": 41, "roads": 1, "ring": 41, "splits": 0, "over": 0}
    assert city["world"]["chronicle"] == [] and not any(p.get("over") for p in state.doc["places"].values())


def test_log_order_is_arrival_order_and_the_date_of_an_event_is_only_written_down():
    h = Hand()
    for i, at in enumerate(["2030-01-01", "2020-01-01T00:00:00Z", "2025-06-30T12:00:00+08:00"], start=1):  # a clock that runs backwards
        h.journal.append("add_item", {"item": {"id": hid(i), "title": "", "authors": [], "year": None, "type": "article"}}, at)
    lots = lot_snapshot(h.state)
    assert [lots[hid(i)]["seq"] for i in (1, 2, 3)] == [1, 2, 3] and [lots[hid(i)]["slot"] for i in (1, 2, 3)] == FILL[:3]
    h.journal.append("set_rule", {"max": 30, "min": 5, "auto": False, "branches": 13}, "1999-12-31")
    entry = h.state.city()["world"]["chronicle"][0]
    assert entry["at"] == "1999-12-31" and entry["event_id"] == 4 and entry["trigger"] == "set_rule"


def test_no_module_of_the_package_reads_the_clock():
    clock = re.compile(r"\b(now|today|utcnow|fromtimestamp|monotonic|perf_counter|time_ns|localtime|gmtime|strftime)\(|\btime\.time\b|import time\b|from time import")
    for path in sorted((ROOT / "bibliopolis").glob("*.py")):
        assert not clock.search(path.read_text(encoding="utf-8")), path.name


# ----------------------------------------------------------------------------------------------- open_road ----
def test_the_first_road_opens_at_the_north_with_the_houses_chosen_and_the_others_keep_their_lots():
    h = town(15)
    before = lot_snapshot(h.state)
    chosen = houses(1, 12)
    h.open("a", "Alpha", None, chosen)
    state = sound(h)
    after = lot_snapshot(state)
    assert [state.road_of[x] for x in chosen] == ["a"] * 12 and [state.road_of[hid(i)] for i in (13, 14, 15)] == [None] * 3
    for i in (13, 14, 15):
        assert after[hid(i)] == before[hid(i)]  # the houses that stay keep their lots, whatever the hole in front of them
    assert [after[hid(i)]["slot"] for i in (13, 14, 15)] == FILL[12:15]
    street = the_street(h, "a")
    assert (street["shape"], street["level"], street["class"], street["address"], street["lots"], street["parent"]) == ("trunk", 1, "大道", ["Alpha"], 12, "place:plaza")
    assert (street["wedge"], street["axis"]) == ([-10.03, 10.03], 0.0)  # the land: within the narrower side (10.03) of the spoke, which is on the bearing
    assert [after[x]["slot"] for x in chosen] == list(range(12)) and {after[x]["parent"] for x in chosen} == {"place:tag:a"}
    city = state.city()
    assert city["composition"]["ring1"] == [{"place": "place:tag:a", "label": "Alpha", "weight": 0, "from": -16.23, "to": 10.03, "span": 26.26, "axis": 0.0}]
    assert city["composition"]["measure"]["ring_lots"] == 3 and summary(city)["roads"] == 2  # (the ring road and the avenue)
    (entry,) = city["world"]["chronicle"]
    assert entry == {"n": 1, "event_id": 16, "seq": 15, "trigger": "open_road", "from": "place:root", "to": "place:tag:a", "label": "Alpha", "houses": chosen,
                     "count_before": 15, "count_after": 3, "at": stamp(16)}
    assert list(entry)[:4] == ["n", "event_id", "seq", "trigger"]


def test_the_next_ring_one_roads_take_the_next_directions_of_the_golden_angle():
    h = town(15)
    h.open("a", "Alpha", None, houses(1, 10))
    h.add(10)
    h.open("b", "Beta", None, houses(11, 20))
    h.add(10)
    h.open("c", "Gamma", None, houses(21, 30))
    state = sound(h)
    sectors = state.city()["composition"]["ring1"]
    assert [(s["label"], s["from"], s["to"]) for s in sectors] == [("Alpha", -16.23, 10.03), ("Beta", 121.28, 147.54), ("Gamma", -101.21, -74.95)]
    assert [the_street(h, k)["axis"] for k in "abc"] == [0.0, 137.51, -84.98]


def test_a_road_below_a_road_is_a_rib_on_the_line_of_its_ring_one_road_and_the_houses_that_stay_keep_their_lots():
    h = town(30)
    h.open("a", "Alpha", None, houses(1, 25))
    before = lot_snapshot(h.state)
    below = houses(3, 12)
    h.open("a1", "Alpha one", "a", below)
    state = sound(h)
    after = lot_snapshot(state)
    street, parent = the_street(h, "a1"), the_street(h, "a")
    assert (street["shape"], street["level"], street["class"], street["address"], street["parent"], street["carrier"]) == (
        "rib", 2, "路", ["Alpha", "Alpha one"], "place:tag:a", "place:tag:a")
    assert parent["shape"] == "trunk" and parent["lots"] == 15 and street["lots"] == 10  # the houses of a road below are not the houses of the road above
    for x in before:
        if x not in below:
            assert after[x] == before[x], x
    assert all(state.road_of[x] == "a1" for x in below)
    entry = state.city()["world"]["chronicle"][-1]
    assert (entry["from"], entry["to"], entry["count_before"], entry["count_after"]) == ("place:tag:a", "place:tag:a1", 25, 15)
    assert state.city()["composition"]["streets"]["total"] == 3  # (the ring road, the avenue and the road below it)


def test_a_road_below_a_road_below_a_road_is_a_ring_three_lane_of_the_same_line():
    h = town(60)
    h.open("a", "A", None, houses(1, 40))
    h.open("b", "B", "a", houses(1, 20))
    h.open("c", "C", "b", houses(1, 10))
    state = sound(h)
    c = the_street(h, "c")
    assert (c["level"], c["class"], c["address"], c["carrier"], c["parent"]) == (3, "巷", ["A", "B", "C"], "place:tag:a", "place:tag:b")
    assert the_street(h, "b")["shape"] == "group" and the_street(h, "a")["shape"] == "trunk"
    assert state.city()["composition"]["measure"]["max_ring"] == 3


def test_a_road_opens_from_a_place_that_holds_the_least_and_with_the_least_chosen_and_the_world_says_why_not():
    h = town(9)
    refuses(h, "the ring road holds 9 houses directly; a road is opened from a place that holds at least 10", "open_road",
            {"road": "a", "name": "A", "parent": None, "houses": houses(1, 9)})
    h.add(5)
    refuses(h, "9 houses are chosen; a road takes at least 10", "open_road", {"road": "a", "name": "A", "parent": None, "houses": houses(1, 9)})
    refuses(h, "'nobody' is not a house", "open_road", {"road": "a", "name": "A", "parent": None, "houses": [*houses(1, 9), "nobody"]})
    refuses(h, "there is no road 'ghost' to open a road below", "open_road", {"road": "a", "name": "A", "parent": "ghost", "houses": houses(1, 10)})
    h.open("a", "A", None, houses(1, 10))
    refuses(h, "there is a road 'a' already", "open_road", {"road": "a", "name": "A again", "parent": None, "houses": houses(11, 14)})
    h.add(10)  # the ring road holds 14 again
    refuses(h, "the house 'h0001' does not stand directly on the ring road; it stands on the road 'a'", "open_road",
            {"road": "b", "name": "B", "parent": None, "houses": houses(1, 10)})
    refuses(h, "the house 'h0011' does not stand directly on the road 'a'; it stands on the ring road", "open_road",
            {"road": "b", "name": "B", "parent": "a", "houses": houses(11, 20)})
    sound(h)


def test_the_least_a_road_takes_is_the_rule_in_force():
    h = town(8)
    refuses(h, "holds 8 houses directly", "open_road", {"road": "a", "name": "A", "parent": None, "houses": houses(1, 8)})
    h.rule(40, 5)
    h.add(2)
    h.open("a", "A", None, houses(1, 5))  # five houses are enough now, and five are left on the ring road
    refuses(h, "4 houses are chosen; a road takes at least 5", "open_road", {"road": "b", "name": "B", "parent": None, "houses": houses(6, 9)})
    sound(h)


def test_more_houses_than_max_may_be_chosen_the_road_opens_continuation_ribs_and_is_not_marked_over():
    h = town(70, {"max": 20, "min": 5, "auto": False})
    h.open("a", "A", None, houses(1, 60))
    state = sound(h)
    street = the_street(h, "a")
    assert street["lots"] + sum(state.doc["places"][lane]["lots"] for lane in street["lanes"]) == 60 and len(street["lanes"]) >= 2
    assert "over" not in street and len(state.city()["world"]["chronicle"]) == 1
    assert [state.doc["places"][lane]["address"] for lane in street["lanes"]] == [["A"]] * len(street["lanes"])


def test_a_continuation_rib_of_a_road_built_by_hand_holds_what_the_road_needs_less_its_ribs_and_has_no_cap_once_the_road_passes_max():
    def ribs(h):
        street = the_street(h, "a")
        return [street["rib"]["slots"]] + [h.state.doc["places"][lane]["rib"]["slots"] for lane in street["lanes"]]

    h = town(70, {"max": 20, "min": 5, "auto": False})
    h.open("a", "A", None, houses(1, 22))
    sound(h)
    assert ribs(h) == [20, 14]  # 22 houses need 34 lots (a road built by hand is never over, so there is no cap): the first rib is max lots, the second the rest
    h = town(70, {"max": 20, "min": 5, "auto": False})
    h.open("a", "A", None, houses(1, 6))
    for k in range(7, 30):  # one house at a time
        h.file(hid(k), "a")
    sound(h)
    assert ribs(h) == [10, 8, 2, 12]  # the need of 6 houses is 10 lots, of 11 houses 18, of 19 houses 30 but at most max = 20 (2 more), of 21 houses 32 with no cap (12 more)


def test_the_fourteenth_road_of_the_first_ring_is_refused_and_a_road_below_a_road_still_opens():
    h = town(10)
    for k in range(13):
        if k:
            h.add(10)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None)[:10])
    state = sound(h)
    assert [(s["from"], s["to"], s["axis"]) for s in state.city()["composition"]["ring1"]] == [(lo / 100, hi / 100, axis / 100) for lo, hi, axis in FIRST_RING]
    h.add(10)
    err = refuses(h, "the ring road holds 13 avenues directly, the most the rule allows (branches 13), so the 14th category goes below one of them", "open_road",
                  {"road": "r13", "name": "Road 13", "parent": None, "houses": h.state.houses_at(None)[:10]})
    assert (err.code, err.params) == ("branches_full", {"road": None, "limit": 13, "number": 14, "remedy": "merge_roads"})
    h.open("r13", "Road 13", "r0", h.state.houses_at("r0"))
    assert sound(h).nodes["r13"]["parent"] == "r0"


# ---------------------------------------------------------------------------------------------------- file ----
def test_a_house_is_filed_from_the_root_zone_or_another_road_and_leaves_an_empty_lot_behind():
    h = town(30)
    h.open("a", "A", None, houses(1, 12))
    h.open("b", "B", None, houses(13, 24))
    before = lot_snapshot(h.state)
    h.file(hid(25), "a")
    state = sound(h)
    after = lot_snapshot(state)
    assert state.road_of[hid(25)] == "a" and after[hid(25)]["parent"] == "place:tag:a" and after[hid(25)]["slot"] == 12 and the_street(h, "a")["lots"] == 13
    assert {x: lot for x, lot in after.items() if x != hid(25)} == {x: lot for x, lot in before.items() if x != hid(25)}  # nobody else moved
    h.file(hid(13), "a")  # from one road to another: the lot it leaves in b is an empty lot of b
    state = sound(h)
    assert state.road_of[hid(13)] == "a" and the_street(h, "b")["lots"] == 11 and the_street(h, "b")["reserved"] >= 1
    (_, _, first, second) = state.city()["world"]["chronicle"]
    assert (first["filed"], first["left"], first["joined"], first["trigger"]) == (hid(25), "place:root", "place:tag:a", "file")
    assert (second["filed"], second["left"], second["joined"]) == (hid(13), "place:tag:b", "place:tag:a") and not {"from", "over"} & set(first)
    h.file(hid(26), "b")
    assert lot_snapshot(h.state)[hid(26)]["slot"] == 0  # the lowest empty lot of the road is taken first: the one that house 13 left
    sound(h)


def test_a_house_that_is_filed_into_a_crowded_road_is_taken_and_a_house_not_there_or_a_road_not_there_is_refused():
    h = town(30, {"max": 12, "min": 10, "auto": False})
    h.open("a", "A", None, houses(1, 12))
    h.file(hid(13), "a")
    h.file(hid(14), "a")
    sound(h)
    assert h.state.count("a") == 14 > h.state.rule["max"]
    refuses(h, "'nobody' is not a house", "file", {"house": "nobody", "road": "a"})
    refuses(h, "there is no road 'nowhere'", "file", {"house": hid(15), "road": "nowhere"})
    refuses(h, "the house 'h0013' stands on the road 'a' already", "file", {"house": hid(13), "road": "a"})


# ------------------------------------------------------------------------------------------- rename_road ----
def test_a_road_is_renamed_with_the_addresses_below_it_and_no_house_moves():
    h = town(60)
    h.open("a", "Alpha", None, houses(1, 40))
    h.open("b", "Beta", "a", houses(1, 20))
    before = lot_snapshot(h.state)
    h.rename("a", "Omega")
    state = sound(h)
    assert lot_snapshot(state) == before
    assert the_street(h, "a")["address"] == ["Omega"] and the_street(h, "b")["address"] == ["Omega", "Beta"]
    assert state.city()["composition"]["ring1"][0]["label"] == "Omega" and state.plan["trunks"]["place:tag:a"]["label"] == "Omega"
    h.rename("b", "Gamma")
    state = sound(h)
    assert the_street(h, "b")["address"] == ["Omega", "Gamma"] and the_street(h, "b")["label"] == "Gamma"
    entries = state.city()["world"]["chronicle"]
    assert entries[-2] == {"n": 3, "event_id": 63, "seq": 60, "trigger": "rename_road", "renamed": "place:tag:a", "was": "Alpha", "label": "Omega", "at": stamp(63)}
    assert [chronicle_lines(state.city())[i].split(": ", 1)[1] for i in (2, 3)] == ["Alpha is renamed Omega.", "Beta is renamed Gamma."]


def test_the_continuation_ribs_of_a_renamed_road_carry_the_new_name():
    h = town(70, {"max": 20, "min": 5, "auto": False})
    h.open("a", "Alpha", None, houses(1, 60))
    assert the_street(h, "a")["lanes"]
    h.rename("a", "Omega")
    state = sound(h)
    assert all(state.doc["places"][lane]["label"] == "Omega" and state.doc["places"][lane]["address"] == ["Omega"] for lane in the_street(h, "a")["lanes"])


def test_a_road_is_not_renamed_to_its_own_name_nor_a_road_that_is_not_there():
    h = town(12)
    h.open("a", "Alpha", None, houses(1, 10))
    refuses(h, "the road 'a' is called 'Alpha' already", "rename_road", {"road": "a", "name": "Alpha"})
    refuses(h, "there is no road 'b'", "rename_road", {"road": "b", "name": "Beta"})


# --------------------------------------------------------------------------------------------- move_road ----
def build_two_districts():
    h = town(80)
    h.open("a", "A", None, houses(1, 30))
    h.open("b", "B", None, houses(31, 60))
    h.open("a1", "A one", "a", houses(1, 12))
    h.open("a2", "A two", "a1", houses(1, 10))
    return h


def test_a_road_moves_below_another_with_its_roads_and_houses_and_every_other_house_keeps_its_lot():
    h = build_two_districts()
    before = lot_snapshot(h.state)
    moving = set(houses(1, 12))  # a1 holds 2 houses of its own, a2 holds 10
    h.move("a1", "b")
    state = sound(h)
    after = lot_snapshot(state)
    for x in before:
        assert (after[x] != before[x]) == (x in moving), x  # exactly the houses of the subtree are placed again
    assert state.nodes["a1"]["parent"] == "b" and state.nodes["a2"]["parent"] == "a1"
    a1, a2 = the_street(h, "a1"), the_street(h, "a2")
    assert (a1["address"], a1["parent"], a1["carrier"], a1["level"]) == (["B", "A one"], "place:tag:b", "place:tag:b", 2)
    assert (a2["address"], a2["parent"], a2["carrier"], a2["level"]) == (["B", "A one", "A two"], "place:tag:a1", "place:tag:b", 3)
    assert the_street(h, "a")["lots"] == 18 and the_street(h, "b")["lots"] == 30
    entry = state.city()["world"]["chronicle"][-1]
    assert entry == {"n": 5, "event_id": 85, "seq": 80, "trigger": "move_road", "moved": "place:tag:a1", "below": "place:tag:b", "was_below": "place:tag:a",
                     "houses": houses(1, 12), "at": stamp(85)}


def test_the_ground_a_moved_road_claimed_stays_claimed_and_its_new_ribs_stand_on_the_line_of_its_new_trunk():
    h = build_two_districts()
    old_rib = the_street(h, "a1")["rib"]
    line = h.state.doc["lines"]["place:tag:a"]
    claimed = copy.deepcopy((line["bands"], line["spokes"]))
    h.move("a1", "b")
    state = sound(h)  # (no empty lot left over, no overlap, no lot outside the wedge of its trunk: the checks of the engine)
    new_rib = the_street(h, "a1")["rib"]
    assert (old_rib["trunk"], new_rib["trunk"]) == ("place:tag:a", "place:tag:b")
    line = state.doc["lines"]["place:tag:a"]
    assert (line["bands"], line["spokes"]) == claimed  # a road opened later on that line does not stand on the ghost of the moved one


def test_a_ring_one_road_may_move_below_a_road_and_then_its_direction_is_free_for_the_next_avenue():
    h = build_two_districts()
    h.move("b", "a")
    state = sound(h)
    assert the_street(h, "b")["level"] == 2 and the_street(h, "b")["address"] == ["A", "B"] and the_street(h, "b")["carrier"] == "place:tag:a"
    assert [s["label"] for s in state.city()["composition"]["ring1"]] == ["A"]  # b is not a road of the first ring now ...
    assert [r["name"] for r in state.plan["ring1"]] == ["a", "b"] and state.held == {0: "a"}  # ... and it holds no direction: number 1 is free
    h.add(20)
    h.open("c", "C", None, h.state.houses_at(None)[:10])
    state = sound(h)
    assert state.held == {0: "a", 1: "c"}  # the third road takes the lowest free number: the one that b gave up
    assert [s["from"] for s in state.city()["composition"]["ring1"]] == [-16.23, 121.28]  # the sector and the bearing of number 1


def test_a_road_moves_only_below_a_road_that_is_not_its_own_and_not_where_it_is_already():
    h = build_two_districts()
    refuses(h, "there is no road 'nowhere' to move a road below", "move_road", {"road": "a1", "parent": "nowhere"})
    refuses(h, "there is no road 'ghost'", "move_road", {"road": "ghost", "parent": "a"})
    refuses(h, "the road 'a1' is below 'a' already", "move_road", {"road": "a1", "parent": "a"})
    refuses(h, "cannot move below 'a1', which is itself or one of its own roads", "move_road", {"road": "a1", "parent": "a1"})
    refuses(h, "cannot move below 'a2', which is itself or one of its own roads", "move_road", {"road": "a", "parent": "a2"})
    with pytest.raises(Refusal, match="must be a string"):  # the town hall is not a road: a road is not promoted to the first ring by a move
        h.journal.append("move_road", {"road": "a1", "parent": None}, stamp(99))


# ------------------------------------------------------------------------------------------------ set_rule ----
def test_the_rule_changes_from_its_event_on_and_is_written_in_the_document():
    h = town(30)
    h.rule(25, 5, True)
    state = sound(h)
    assert state.rule == {"max": 25, "min": 5, "auto": True, "branches": 13} and state.city()["world"]["districts"] == {"max": 25, "min": 5, "extract": "largest", "count": "direct"}
    entry = state.city()["world"]["chronicle"][-1]
    assert (entry["trigger"], entry["rule"], entry["seq"]) == ("set_rule", {"max": 25, "min": 5, "auto": True, "branches": 13}, 30)
    refuses(h, "the rule is this already", "set_rule", {"max": 25, "min": 5, "auto": True, "branches": 13})
    with pytest.raises(Refusal, match="more than max"):
        h.rule(5, 6)
    assert chronicle_lines(state.city())[-1].endswith("the rule is now 25 houses at most and 5 at least for a new road, 13 branches to a road, auto on.")


def test_the_rule_at_the_start_of_the_world_is_the_rule_the_journal_was_made_with():
    h = Hand({"max": 12, "min": 3, "auto": False})
    assert h.state.city()["world"]["districts"]["max"] == 12 and h.journal.rule == {"max": 12, "min": 3, "auto": False, "branches": 13}  # (the default is written in)
    h.add(3)
    h.open("a", "A", None, h.state.houses_at(None))
    sound(h)


# ------------------------------------------------------------------------------------------------- the undo ----
def scene():
    h = town(40)
    h.open("a", "A", None, houses(1, 20))  # event 41
    h.file(hid(21), "a")  # 42
    h.rename("a", "Alpha")  # 43
    return h


def test_the_last_event_is_taken_back_and_the_world_is_the_one_before_it_with_the_undo_in_the_chronicle():
    h = scene()
    h.undo()  # the rename: event 44
    state = sound(h)
    assert the_street(h, "a")["address"] == ["A"] and state.nodes["a"]["name"] == "A" and state.road_of[hid(21)] == "a"
    ref = Journal.replay(h.journal.rule, h.journal.events[:42]).state  # the world that never had the rename
    city, before = state.city(), ref.city()
    for key in ("places", "roads", "coast", "composition", "centre", "counts"):
        assert city[key] == before[key], key
    entry = city["world"]["chronicle"][-1]
    assert (entry["trigger"], entry["undone"], entry["of"], entry["event_id"]) == ("undo", 43, "rename_road", 44)
    assert chronicle_lines(city)[-1].split(": ", 1)[1] == "event 43 (rename_road) is undone."


def test_the_events_are_undone_from_the_end_backwards_down_to_an_empty_world():
    h = scene()
    for target in (43, 42, 41):
        h.undo(target)
        sound(h)
    assert h.state.nodes == {} and set(h.state.road_of.values()) == {None}
    lots = lot_snapshot(h.state)
    assert len(lots) == 40 and all(lots[x]["parent"] == "place:root" for x in lots)
    assert [e["trigger"] for e in h.state.city()["world"]["chronicle"]] == ["undo", "undo", "undo"]


def test_an_undo_of_an_undo_gives_the_event_back_and_the_world_is_the_one_before_the_first_undo():
    h = scene()
    before = lot_snapshot(h.state)
    h.undo(43)  # the rename, taken back (event 44)
    assert the_street(h, "a")["address"] == ["A"]
    h.undo(44)  # ... and given back (event 45)
    state = sound(h)
    assert the_street(h, "a")["address"] == ["Alpha"] and lot_snapshot(state) == before
    h.undo(45)  # taken back again (event 46)
    assert the_street(h, "a")["address"] == ["A"]
    h.undo(46)  # and again given back
    assert the_street(h, "a")["address"] == ["Alpha"]
    sound(h)


def test_an_event_that_nothing_depends_on_may_be_undone_from_the_middle_and_the_later_houses_are_placed_again():
    h = town(5)
    h.add(2)  # events 6 and 7: the houses h0006 and h0007
    before = lot_snapshot(h.state)
    h.undo(6)  # a house taken back from the middle: nothing names it
    state = sound(h)
    assert hid(6) not in state.items and hid(7) in state.items
    after = lot_snapshot(state)
    assert after[hid(7)]["slot"] == FILL[5] and before[hid(7)]["slot"] == FILL[6]  # the house after it moves up a place in fill order: an undo may re-place what came after the event
    assert all(after[hid(i)] == before[hid(i)] for i in range(1, 6))


def test_an_event_that_a_later_event_depends_on_is_not_undone_and_the_world_says_which():
    h = scene()
    h.add(1)  # 44: a house nothing names
    refuses(h, "event 41 cannot be undone: event 42 (file) depends on it; undo that one first", "undo", {"seq": 41})  # the filing names the road that a opened
    refuses(h, "event 5 cannot be undone: event 41 (open_road) depends on it", "undo", {"seq": 5})  # the open_road took the house that event 5 placed
    h.undo(44)  # the one nothing names goes
    h.undo(43)
    refuses(h, "event 41 cannot be undone: event 42 (file) depends on it", "undo", {"seq": 41})
    h.undo(42)
    h.undo(41)
    assert sound(h).nodes == {}


def test_a_house_moved_again_depends_on_the_event_that_moved_it_before():
    h = town(40)
    h.open("a", "A", None, houses(1, 20))
    h.open("b", "B", None, houses(21, 30))
    h.file(hid(35), "a")  # 43
    h.file(hid(35), "b")  # 44: the same house again
    refuses(h, "event 43 cannot be undone: event 44 (file) depends on it; undo that one first", "undo", {"seq": 43})
    h.undo(44)
    h.undo(43)
    sound(h)


def test_an_undo_names_an_earlier_event_that_counts_and_nothing_else():
    h = scene()
    refuses(h, "an undo names an earlier event", "undo", {"seq": 44})
    refuses(h, "an undo names an earlier event", "undo", {"seq": 99})
    h.undo(43)
    refuses(h, "event 43 does not count", "undo", {"seq": 43})  # it is undone already
    with pytest.raises(Refusal, match="number of an event"):
        h.journal.append("undo", {"seq": 0}, stamp(99))
    sound(h)


def test_giving_an_event_back_is_refused_when_a_later_event_could_not_be_taken_after_it():
    h = town(40)
    h.open("a", "A", None, houses(1, 10))  # 41
    h.file(hid(11), "a")  # 42
    h.undo(42)  # 43: the house is on the ring road again
    h.open("b", "B", None, houses(11, 20))  # 44: ... and event 44 takes it from there
    # no event names anything that event 43 (an undo) opened or placed, but the log with event 42 given back would file house 11 onto a first,
    # and then event 44 would take it from the ring road, where it is not
    refuses(h, "event 43 cannot be undone: event 44 (open_road): the house 'h0011' does not stand directly on the ring road; it stands on the road 'a'", "undo", {"seq": 43})
    sound(h)


# ------------------------------------------------------------------------------------------------ the fold ----
def text_of(state):
    return lay.render(state.city())


def test_a_log_folds_to_the_same_bytes_whatever_the_route_to_it():
    for seed in (3, 11, 29):
        j = play(seed, steps=150)
        assert text_of(fold(j.events, j.rule)) == text_of(j.state), seed  # the journal's incremental state is the fold of its log
        replayed = Journal.replay(j.rule, j.events)
        assert text_of(replayed.state) == text_of(j.state) and replayed.events == j.events


def test_a_log_folds_to_the_same_bytes_in_another_process_with_another_hash_seed():
    j = play(5, steps=150)
    want = hashlib.sha256(text_of(j.state).encode("utf-8")).hexdigest()
    code = ("import sys; sys.path.insert(0, 'tests'); import hashlib, hand_support as hs; from bibliopolis import layout; j = hs.play(5, steps=150); "
            "print(hashlib.sha256(layout.render(j.state.city()).encode('utf-8')).hexdigest())")
    for seed in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == want


def test_the_events_given_to_the_fold_are_not_changed():
    j = play(7, steps=100)
    frozen = copy.deepcopy(j.events)
    fold(j.events, j.rule)
    assert j.events == frozen


@pytest.mark.parametrize("seed", range(12))
def test_a_random_player_always_leaves_a_sound_world_and_a_city_that_can_be_read_and_drawn(seed):
    j = play(seed, steps=160)
    assert hand_problems(j.state, coast=seed % 4 == 0) == []
    assert text_problems(j.state) == []


def test_the_random_player_uses_every_kind_of_event_and_the_geometry_checks_of_the_engine_hold():
    j = play(21, steps=300)
    assert {e["kind"] for e in j.events} == {"add_item", "open_road", "file", "rename_road", "move_road", "undo", "set_rule"}
    assert checks.all_problems(j.state.doc) == {} and checks.document_problems(j.state.city()) == {}


# ---------------------------------------------------------------------------------------------- documents ----
def test_the_city_of_a_hand_built_world_is_read_by_picture_and_chronicle_and_says_it_is_hand_built():
    h = build_two_districts()
    h.move("a1", "b")
    city = h.state.city()
    assert city["world"]["mode"] == "hand" and city["world"]["zoning_version"] == "hand-1" and "hand:" in city["world"]["notes"]["world.mode"]
    assert city["generator"]["input"].startswith("a log of events")
    read = inputs.read_city(json.loads(bibliopolis.render(city)))
    assert ET.fromstring(picture.render(read)).tag.endswith("svg")
    lines = chronicle_lines(read)
    assert len(lines) == 5
    assert lines[0] == "event 81, 2026-01-01: Knowledge held 80 houses. A opens as a road with 30 of them; 50 stay."
    assert lines[4] == "event 85, 2026-01-01: A one moves from below A to below B, with 12 houses."


def test_a_chronicle_entry_that_is_none_of_the_known_shapes_is_refused_by_the_reader_of_a_city_file():
    city = build_two_districts().state.city()
    broken = copy.deepcopy(city)
    broken["world"]["chronicle"].append({"n": 9, "event_id": 9, "seq": 1, "trigger": "x", "surprise": True})
    with pytest.raises(inputs.InputError, match="must be a split"):
        inputs.read_city(broken)
    broken = copy.deepcopy(city)
    broken["world"]["chronicle"].append({"n": 9, "event_id": 9, "seq": 1, "trigger": "file", "filed": 7, "left": "x", "joined": "y"})
    with pytest.raises(inputs.InputError, match="the id of the house"):
        inputs.read_city(broken)


def test_the_modes_of_build_are_still_grow_and_mirror_and_hand_is_not_one_of_them(tmp_path):
    from bibliopolis import cli

    assert plan.MODES == ("grow", "mirror") and plan.HAND == "hand"
    (tmp_path / "t.json").write_text('{"nodes": []}', encoding="utf-8")
    (tmp_path / "l.json").write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        cli.main(["build", "--library", str(tmp_path / "l.json"), "--tree", str(tmp_path / "t.json"), "--mode", "hand", "--out", str(tmp_path / "c.json")])
    assert stop.value.code == 2 and not (tmp_path / "c.json").exists()
    with pytest.raises(ValueError, match="mode must be one of"):
        plan.build_plan(TreeView({"nodes": []}), [], mode="hand")


def test_the_module_names_the_limits_it_has():
    text = " ".join(hand.__doc__.split())
    assert "a road holds at most N roads directly, at every level" in text and "the next category goes below one of the roads" in text and "No trunk is promoted" in text
