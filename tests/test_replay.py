"""A replay (`first=n`) is the build stopped after n items: what keeps its place, what does not, and what a mirror replay leaves out."""

import math

import pytest
from support import art, sample

import bibliopolis
from bibliopolis import city, document
from bibliopolis import world as world_mod

# Ring-1 road `a` has a leaf `d` and a container `c` (two leaves under it). The 200 houses of `d` arrive first and push the frontier of `a` outward; `c` is
# reached only by the 201st item. `c` has a weight of its own in the plan, and below `trunk_min` it is a road on a band of `a`, at or above it a trunk with a spoke.
TREE = {"nodes": [
    {"id": "r", "label": "R", "parent": None},
    {"id": "a", "label": "A", "parent": "r"}, {"id": "b", "label": "B", "parent": "r"},
    {"id": "c", "label": "C", "parent": "a"}, {"id": "d", "label": "D", "parent": "a"},
    {"id": "c1", "label": "C1", "parent": "c"}, {"id": "c2", "label": "C2", "parent": "c"},
]}
ARRIVALS = (("d", 200), ("c1", 170), ("c2", 170), ("b", 100), ("a", 20), ("c", 10))
SWEEP = (0, 1, 50, 100, 199, 200, 201, 300, 569, 570, 669)  # the last of 670 items is left out: that is the full city
ROAD_C = "road:place:tag:c"


def late_trunk_case():
    items = []
    for topic, count in ARRIVALS:
        items += [art(len(items) + 1 + k, [topic]) for k in range(count)]
    return {"items": items}


@pytest.fixture(scope="module")
def case():
    library = late_trunk_case()
    weight = bibliopolis.build_city(library, TREE, mode="mirror")["places"]["place:tag:c"]["weight"]
    return library, weight


def keeps_its_place(part, full, label):
    """Assert what a replay keeps of the full city: the bearing of every street that has one, and of every spoke its bearing and its start, and that it
    only grows longer. Returns the spokes checked."""
    for pid, street in part["places"].items():
        if street["kind"] == "street" and street.get("axis") is not None:
            assert full["places"][pid]["axis"] == street["axis"], (label, pid)
    spokes = set()
    for rid, road in part["roads"].items():
        if road["kind"] == "spoke":
            later = full["roads"][rid]
            assert later["axis"] == road["axis"] and later["points"][0] == road["points"][0] and later["length"] >= road["length"], (label, rid)
            spokes.add(rid)
    return spokes


def houses_below(doc):
    """The streets that a house stands on or below (every street above a lot's street, up to the plaza)."""
    places, seen = doc["places"], set()
    for p in places.values():
        if p["kind"] == "lot":
            pid = p["parent"]
            while pid in places and pid not in seen and places[pid]["kind"] == "street":
                seen.add(pid)
                pid = places[pid].get("parent")
    return seen


# ------------------------------------------------------------------------------- what keeps its place ----
def test_the_case_sits_on_trunk_min_c_is_a_trunk_of_its_own_at_its_weight_and_not_one_above_it(case):
    library, weight = case
    assert weight > 300  # more than the default `trunk_min`: with the defaults c is a trunk
    at = bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight)
    above = bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight + 1)
    assert (at["places"]["place:tag:c"]["shape"], at["roads"][ROAD_C]["kind"]) == ("trunk", "spoke")
    assert (above["places"]["place:tag:c"]["shape"], above["roads"][ROAD_C]["kind"]) == ("group", "lane")


@pytest.mark.parametrize("mode", ["grow", "mirror"])
@pytest.mark.parametrize("above", [0, 1])
def test_every_spoke_of_a_replay_keeps_its_bearing_and_its_start_and_only_grows_longer(case, mode, above):
    library, weight = case
    trunk_min = weight + above  # above = 0: c is a trunk; 1: c is not (its weight is one short of trunk_min)
    full = bibliopolis.build_city(library, TREE, mode=mode, trunk_min=trunk_min)
    checked = set()
    for n in SWEEP:
        part = bibliopolis.build_city(library, TREE, mode=mode, trunk_min=trunk_min, first=n)
        checked |= keeps_its_place(part, full, (mode, trunk_min, n))
    assert {"road:place:tag:a", "road:place:tag:b"} <= checked  # the roads of ring 1
    if mode == "mirror" and not above:
        assert ROAD_C in checked  # the trunk that opens late was checked, after it opened


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_every_spoke_of_a_replay_of_the_sample_keeps_its_bearing_and_its_start(mode):
    tree, library = sample()
    full = bibliopolis.build_city(library, tree, mode=mode)
    checked = set()
    for n in (1, 41, 150, 300, 599):
        checked |= keeps_its_place(bibliopolis.build_city(library, tree, mode=mode, first=n), full, (mode, n))
    assert len(checked) >= 5


def test_the_control_completing_a_replay_early_puts_the_late_road_nearer_the_plaza_than_the_full_city_does(case):
    """What a replay used to do: take the last step of the build as well. The check above would see it: c starts nearer the plaza than it does in the full city."""
    library, weight = case
    full = bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight)
    late = full["roads"][ROAD_C]["points"][0]
    for n in (0, 50, 100):
        plan, tv, world, _items = city.build_world(library, TREE, mode="mirror", trunk_min=weight, first=n)
        assert "place:tag:c" not in world["places"]  # the replay itself has no such road yet ...
        world = world_mod.apply_delta(world, world_mod.complete(plan, tv, world)["delta"])  # ... the early completion makes it, near the plaza
        early = document.world_layout(world)["roads"][ROAD_C]["points"][0]
        assert early != late and math.hypot(*early) < math.hypot(*late), (n, early, late)
        with pytest.raises(AssertionError):
            keeps_its_place(document.world_layout(world), full, n)  # and the check refuses it


# ------------------------------------------------------------------------------- a mirror replay ----
def test_a_mirror_replay_has_no_road_that_no_house_stands_on_or_below(case):
    library, weight = case
    for n in SWEEP:
        part = bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight, first=n)
        places = part["places"]
        roads = {pid for pid, p in places.items() if p["kind"] == "street" and p.get("shape") != "ring" and "lane_of" not in p}
        standing = {pid for pid in houses_below(part) if "lane_of" not in places[pid] and places[pid].get("shape") != "ring"}
        assert roads == standing, (n, sorted(roads ^ standing))  # the roads of the replay are exactly the streets a house stands on or below (the ring road stands from day one)


def test_a_road_that_opens_late_is_not_in_a_replay_before_its_first_house_and_is_where_the_full_city_has_it_after(case):
    library, weight = case
    full = bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight)
    for n in (0, 100, 200):
        assert ROAD_C not in bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight, first=n)["roads"]
    for n in (201, 300, 669):
        assert bibliopolis.build_city(library, TREE, mode="mirror", trunk_min=weight, first=n)["roads"][ROAD_C]["points"][0] == full["roads"][ROAD_C]["points"][0]


def test_a_topic_an_item_is_filed_under_while_its_house_stands_elsewhere_is_a_road_only_in_the_complete_city():
    tree = {"nodes": [{"id": "x", "label": "X", "parent": None}, {"id": "y", "label": "Y", "parent": None}]}
    library = {"items": [art(1, ["x", "y"])] + [art(k, ["x"]) for k in range(2, 6)]}  # the first item is filed under both; its house stands at x (the lower id)
    full = bibliopolis.build_city(library, tree, mode="mirror")
    assert full["places"]["place:tag:y"]["lots"] == 0 and "place:tag:x" in full["places"]  # y is a road with no house, made by the last step
    for n in range(5):
        assert "place:tag:y" not in bibliopolis.build_city(library, tree, mode="mirror", first=n)["places"], n
    assert bibliopolis.build_city(library, tree, mode="mirror", first=5) == full and bibliopolis.build_city(library, tree, mode="mirror", first=99) == full


# ------------------------------------------------------------------------------------- what does not ----
def test_a_spoke_grows_longer_as_houses_arrive():
    tree, library = sample()
    road = "road:place:tag:computing"
    full = bibliopolis.build_city(library, tree)
    assert bibliopolis.build_city(library, tree, first=41)["roads"][road]["length"] < full["roads"][road]["length"]


def test_a_later_split_repacks_the_houses_that_stay_so_a_lot_can_stand_elsewhere_in_the_full_city():
    tree, library = sample()
    full, part = bibliopolis.build_city(library, tree), bibliopolis.build_city(library, tree, first=150)
    moved = [pid for pid, p in part["places"].items() if p["kind"] == "lot" and pid in full["places"]
             and full["places"][pid]["parent"] == p["parent"] and full["places"][pid]["position"] != p["position"]]
    assert moved  # the same house, on the same road, in another cell


def test_a_continuation_rib_that_a_later_split_empties_is_in_the_replay_and_not_in_the_full_city():
    tree, library = sample()
    full, part = bibliopolis.build_city(library, tree), bibliopolis.build_city(library, tree, first=150)
    gone = [rid for rid, road in part["roads"].items() if road["kind"] == "lane" and rid not in full["roads"]]
    assert gone and all(part["roads"][rid]["street"] not in full["places"] for rid in gone)
