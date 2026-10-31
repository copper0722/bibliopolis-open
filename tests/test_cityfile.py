"""Reading a city file (inputs.read_city): what it accepts, what it refuses and says where, and that nothing it accepts can crash or loop the commands that
read the file (`picture` and `chronicle`)."""

import collections
import copy
import json

import pytest
from support import T, art, make_tree, random_world, sample

import bibliopolis
from bibliopolis import city, inputs, picture
from bibliopolis import layout as lay


@pytest.fixture(scope="module")
def real_city():
    tree, items = make_tree({"med": T(0, a=T(25), b=T(16)), "pub": T(14)})
    items += [art(60 + k, [], annex_of=items[k % 3]["id"], annex_form="wing" if k % 4 else "mailbox") for k in range(9)]  # nine items that exist for the first three houses
    doc = json.loads(json.dumps(bibliopolis.build_city({"items": items}, tree)))
    doc["world"]["chronicle"].append({"n": 9, "seq": 9, "over": "place:tag:pub", "count": 41})  # an over entry as well as the split
    return doc


def worlds(mode):
    """A city of 179 houses with every kind of place the engine makes: roads on two levels, a lap of the ring road, an inner trunk, splits, roads that are over, and
    houses with no topic on the ring road. The rule is small (12 houses to a road) to get all of that from few houses."""
    tree, items = make_tree({"r": T(0, a=T(3, c=T(0, c1=T(14), c2=T(14)), d=T(10)), b=T(8, e=T(6), f=T(14)))})
    items += [art(900 + k, []) for k in range(110)]
    on_road, on_ring = items[5]["id"], items[-1]["id"]
    items += [art(1100 + k, [], annex_of=on_road, annex_form="wing") for k in range(6)] + [art(1110 + k, [], annex_of=on_road, annex_form="mailbox") for k in range(2)]
    items += [art(1120, [], annex_of=on_ring, annex_form="wing"), art(1121, [], annex_of=on_ring, annex_form="mailbox")]
    doc = bibliopolis.build_city({"items": items}, tree, mode=mode, max_houses=12, min_houses=4, trunk_min=20)
    return json.loads(json.dumps(doc))


def first_lot(doc):
    return next(pid for pid, p in doc["places"].items() if p["kind"] == "lot")


def an_annex(doc):
    """The id of the first annex (an item that exists for another item) of the document."""
    return next(pid for pid, p in doc["places"].items() if p["kind"] == "annex")


def an_entry(doc, key):
    """The first entry of the chronicle that has `key`."""
    return next(e for e in doc["world"]["chronicle"] if key in e)


def a_street(doc, *keys):
    """A road (not the ring road, not a continuation) that has all of `keys`."""
    return next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("shape") != "ring" and "lane_of" not in p and all(k in p for k in keys))


def the_ring(doc):
    """The street of the ring road (lap 1)."""
    return next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("shape") == "ring" and "lane_of" not in p)


def the_root(doc):
    """The street the houses of no road stand on: the ring road (lap 1)."""
    return next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("shape") == "ring" and "lane_of" not in p)


def a_city_with_laps(mode):
    """A city whose ring road is full and goes on as a lap: fourteen roots of nine houses (no group of ten anywhere) and 130 houses with no topic stand on the ring
    road in both modes (in `grow` mode the roots' houses stand there too)."""
    tree, items = make_tree({f"t{i}": T(9) for i in range(14)})
    items += [art(900 + k, []) for k in range(130)]
    doc = bibliopolis.build_city({"items": items}, tree, mode=mode)
    assert any(p.get("lane_of") == "place:root" for p in doc["places"].values())
    return json.loads(json.dumps(doc))


def circle(doc):
    """Two streets that are each other's parent: a ring-1 street and a road with a rib."""
    above, below = doc["composition"]["ring1"][0]["place"], a_street(doc, "rib")
    assert above != below
    doc["places"][below]["parent"] = above
    doc["places"][above]["parent"] = below


def lane_without_radius(doc):
    rib = doc["places"][a_street(doc, "rib")]["rib"]
    rib["band"] = 0
    del rib["s"]


# ------------------------------------------------------------------------------------------- accepted ----
def test_a_city_that_build_wrote_is_read_as_it_is_also_after_a_round_trip_through_json(real_city):
    assert inputs.read_city(real_city) is real_city
    assert inputs.read_city(json.loads(json.dumps(real_city))) == real_city


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_every_city_the_engine_makes_is_read_and_drawn_and_told(mode):
    tree, library = sample()
    docs = [bibliopolis.build_city(library, tree, mode=mode, first=n, with_coast=coast) for n in (None, 0, 1, 41, 150) for coast in (True, False)]
    docs += [bibliopolis.build_city({"items": items}, t, mode=mode) for t, items in (random_world(seed) for seed in range(12))]
    tree3, items3 = random_world(3)
    docs += [worlds(mode), a_city_with_laps(mode), bibliopolis.build_city({"items": items3}, tree3, mode=mode, trunk_min=40, max_houses=15, min_houses=5)]
    for doc in docs:
        inputs.read_city(json.loads(json.dumps(doc)))
        picture.render(doc)
        city.chronicle_lines(doc)


# ------------------------------------------------------------------------------------------- refused ----
@pytest.mark.parametrize("doc", [None, [], "city", 3, {}, {"items": []}, {"nodes": []}, {"layout_version": "v4"}])
def test_what_is_no_city_at_all_is_refused_with_a_hint(doc):
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert "city" in str(refused.value) and len(str(refused.value).splitlines()) <= inputs.MAX_PROBLEMS + 1


MISTAKES = [
    # (what is wrong, how to make it so, what the message names)
    ("no roads", lambda d: d.pop("roads"), "city.roads: must be an object"),
    ("no world", lambda d: d.pop("world"), "city.world: must be an object"),
    ("a layout of another version", lambda d: d.update(layout_version="v3"), "layout_version is 'v3', not 'v4'"),
    ("no plaza", lambda d: d["places"].pop("place:plaza"), "city.places['place:plaza']: the town hall plaza is missing"),
    ("a plaza that is a street", lambda d: d["places"]["place:plaza"].update(kind="street"), "the town hall plaza is missing"),
    ("a plaza radius that is a word", lambda d: d["places"]["place:plaza"].update(radius="big"), "places['place:plaza'].radius: must be a number, 0 or more"),
    ("a plaza radius below 0", lambda d: d["places"]["place:plaza"].update(radius=-1), "places['place:plaza'].radius: must be a number, 0 or more"),
    ("a plaza with no name", lambda d: d["places"]["place:plaza"].update(label=3), "places['place:plaza'].label: must be a string"),
    ("a plaza with no position", lambda d: d["places"]["place:plaza"].pop("position"), "places['place:plaza']: position is missing"),
    ("a plaza position with no x", lambda d: d["places"]["place:plaza"].update(position={"z": 0}), "places['place:plaza'].position: must be {x, z}"),
    ("a place of a kind nobody knows", lambda d: d["places"][first_lot(d)].update(kind="castle"), "must be an object whose kind is one of plaza, street, lot, reserved, annex"),
    ("a place that is a string", lambda d: d["places"].update({"place:odd": "x"}), "city.places['place:odd']: must be an object whose kind is one of"),
    ("a house with no position", lambda d: d["places"][first_lot(d)].pop("position"), ".position: must be {x, z}: two numbers"),
    ("a house at a position that is a word", lambda d: d["places"][first_lot(d)]["position"].update(x="far"), ".position: must be {x, z}: two numbers"),
    ("a house at the end of the world", lambda d: d["places"][first_lot(d)]["position"].update(z=1e300), ".position: must be {x, z}: two numbers"),
    ("a house with no street", lambda d: d["places"][first_lot(d)].pop("parent"), "parent is missing"),
    ("a house on the plaza", lambda d: d["places"][first_lot(d)].update(parent="place:plaza"), "'place:plaza' is not a street"),
    ("a house on a street that is not there", lambda d: d["places"][first_lot(d)].update(parent="place:nowhere"), "'place:nowhere' is not a street"),
    ("a house with no item", lambda d: d["places"][first_lot(d)].pop("article"), "article is missing"),
    ("a house whose item is a list", lambda d: d["places"][first_lot(d)].update(article=["a"]), ".article: must be the item id (a string)"),
    ("a house that faces a word", lambda d: d["places"][first_lot(d)].update(facing="north"), ".facing: must be a bearing in degrees"),
    ("an annex with no house", lambda d: d["places"][an_annex(d)].pop("parent"), "parent is missing"),
    ("an annex whose house is a list", lambda d: d["places"][an_annex(d)].update(parent=["a"]), ".parent: must be the id of the house it stands beside"),
    ("an annex whose house is not there", lambda d: d["places"][an_annex(d)].update(parent="place:nowhere"), "'place:nowhere' is not a house (the place of a lot)"),
    ("an annex whose house is the plaza", lambda d: d["places"][an_annex(d)].update(parent="place:plaza"), "'place:plaza' is not a house (the place of a lot)"),
    ("an annex whose house is a street", lambda d: d["places"][an_annex(d)].update(parent=a_street(d)), "is not a house (the place of a lot)"),
    ("an annex whose house is an annex", lambda d: d["places"][an_annex(d)].update(parent=an_annex(d)), "is not a house (the place of a lot)"),
    ("an annex of a form nobody knows", lambda d: d["places"][an_annex(d)].update(form="shed"), ".form: must be one of wing, mailbox, got 'shed'"),
    ("an annex with no form", lambda d: d["places"][an_annex(d)].pop("form"), "form is missing (one of wing, mailbox)"),
    ("an annex whose form is a list", lambda d: d["places"][an_annex(d)].update(form=["wing"]), ".form: must be one of wing, mailbox"),
    ("an annex with a rank that is a word", lambda d: d["places"][an_annex(d)].update(rank="first"), ".rank: must be a whole number, 1 or more"),
    ("an annex with rank 0", lambda d: d["places"][an_annex(d)].update(rank=0), ".rank: must be a whole number, 1 or more, got 0"),
    ("an annex with a rank that is a fraction", lambda d: d["places"][an_annex(d)].update(rank=1.5), ".rank: must be a whole number, 1 or more"),
    ("an annex with no rank", lambda d: d["places"][an_annex(d)].pop("rank"), "rank is missing (a whole number, 1 or more)"),
    ("an annex with no item", lambda d: d["places"][an_annex(d)].pop("article"), "article is missing"),
    ("an annex whose item is a list", lambda d: d["places"][an_annex(d)].update(article=["a"]), ".article: must be the item id (a string)"),
    ("an annex with a position that is a word", lambda d: d["places"][an_annex(d)].update(position="here"), ".position: must be {x, z}: two numbers"),
    ("a street with no shape", lambda d: d["places"][a_street(d)].pop("shape"), "shape is missing"),
    ("a street with no address", lambda d: d["places"][a_street(d)].pop("address"), "address is missing"),
    ("a street whose address is empty", lambda d: d["places"][a_street(d)].update(address=[]), ".address: must be a list of names"),
    ("a street whose address is a word", lambda d: d["places"][a_street(d)].update(address="abc"), ".address: must be a list of names"),
    ("a street whose address holds a number", lambda d: d["places"][a_street(d)].update(address=[1]), ".address: must be a list of names"),
    ("a street with no parent", lambda d: d["places"][a_street(d)].pop("parent"), "parent is missing"),
    ("a street that is its own parent", lambda d: d["places"][a_street(d)].update(parent=a_street(d)), "the parents lead round in a circle"),
    ("two streets that are each other's parent", circle, "the parents lead round in a circle"),
    ("a street whose parent is not there", lambda d: d["places"][a_street(d)].update(parent="place:nowhere"), "'place:nowhere' is not a street, and not the plaza"),
    ("a street whose parent is a house", lambda d: d["places"][a_street(d)].update(parent=first_lot(d)), "is not a street, and not the plaza"),
    ("a street with a level that is a word", lambda d: d["places"][a_street(d)].update(level="two"), ".level: must be a whole number"),
    ("a street with a weight that is a word", lambda d: d["places"][a_street(d)].update(weight="heavy"), ".weight: must be a number"),
    ("a street whose road is a list", lambda d: d["places"][a_street(d)].update(road=["x"]), ".road: must be a road id"),
    ("a street whose name is a number", lambda d: d["places"][a_street(d)].update(label=5), ".label: must be a string"),
    ("a lane of radius 0", lambda d: d["places"][a_street(d, "rib")]["rib"].update(band=0, s=0), ".rib.s: must be a number of at least 1"),
    ("a road hung on the ring road", lambda d: d["places"][a_street(d)].update(parent=the_ring(d)), "is no lap of it, a street of shape ring (a house on it:"),
    ("a ring road with no ring", lambda d: d["places"][the_ring(d)].pop("ring"), ".ring: must be an object {radius, ...} for a street of shape ring"),
    ("a ring road whose ring is a list", lambda d: d["places"][the_ring(d)].update(ring=[8.5]), ".ring: must be an object {radius, ...} for a street of shape ring"),
    ("a ring road of radius 0", lambda d: d["places"][the_ring(d)]["ring"].update(radius=0), ".ring.radius: must be a number of at least 1 (the radius of the lane)"),
    ("a ring road with no radius", lambda d: d["places"][the_ring(d)]["ring"].pop("radius"), ".ring: radius is missing (a number of at least 1"),
    ("a ring road whose radius is a word", lambda d: d["places"][the_ring(d)]["ring"].update(radius="wide"), ".ring.radius: must be a number of at least 1"),
    ("a count of houses on the ring that is a word", lambda d: d["composition"]["measure"].update(ring_lots="many"), "measure.ring_lots: must be a number"),
    ("a lane with no radius", lane_without_radius, "rib: s is missing"),
    ("a rib that is a list", lambda d: d["places"][a_street(d, "rib")].update(rib=[1]), ".rib: must be an object"),
    ("a sector that is no longer there", lambda d: d["composition"]["ring1"].pop(0), "which is not a sector in composition.ring1 (a house on it:"),
    ("a sector that is a house", lambda d: d["composition"]["ring1"][0].update(place=first_lot(d)), "is a place of kind lot, not a street"),
    ("a road of a class nobody knows", lambda d: next(iter(d["roads"].values())).update({"class": "avenue"}), "must be an object whose class is one of 大道, 路, 巷, 弄"),
    ("a road of one point", lambda d: next(iter(d["roads"].values())).update(points=[[1, 2]]), ".points: must be a list of at least two [x, z] pairs"),
    ("a road with a point that is a word", lambda d: next(iter(d["roads"].values())).update(points=[[1, 2], [3, "x"]]), ".points: must be a list of at least two"),
    ("a road with three numbers in a point", lambda d: next(iter(d["roads"].values())).update(points=[[1, 2], [3, 4, 5]]), ".points: must be a list of at least two"),
    ("a road that runs off the map", lambda d: next(iter(d["roads"].values())).update(points=[[0, 0], [1e300, 1]]), ".points: must be a list of at least two"),
    ("a coast that is null", lambda d: d.update(coast=None), "city.coast: must be an object"),
    ("a coast that is a word", lambda d: d.update(coast="sea"), "city.coast: must be an object"),
    ("coast polygons that are a word", lambda d: d["coast"].update(polygons="x"), "city.coast.polygons: must be a list of polygons"),
    ("a polygon of two corners", lambda d: d["coast"]["polygons"].__setitem__(0, [[0, 0], [1, 1]]), "coast.polygons[0]: must be a list of at least three [x, z] corners"),
    ("sectors that are a word", lambda d: d["composition"].update(ring1="x"), "composition.ring1: must be a list of sectors"),
    ("a sector that is a number", lambda d: d["composition"]["ring1"].__setitem__(0, 7), "composition.ring1[0]: must be an object"),
    ("a sector whose bearing is a word", lambda d: d["composition"]["ring1"][0].update({"from": "a"}), "ring1[0].from: must be a bearing in degrees"),
    ("a sector with no name", lambda d: d["composition"]["ring1"][0].pop("label"), "ring1[0]: label is missing"),
    ("an empty measure", lambda d: d["composition"].update(measure={}), "city.composition.measure: max_radius is missing"),
    ("a walk that is a word", lambda d: d["composition"]["measure"].update(walk_mean="far"), "measure.walk_mean: must be a number"),
    ("no count of buildings", lambda d: d["composition"].pop("buildings"), "city.composition: buildings is missing"),
    ("no count of streets", lambda d: d["composition"]["streets"].pop("total"), "composition.streets: total is missing"),
    ("a rule with no max", lambda d: d["world"].update(districts={"min": 10}), "city.world.districts: must be an object with whole numbers max and min"),
    ("a rule whose max is a word", lambda d: d["world"]["districts"].update(max="40"), "city.world.districts: must be an object with whole numbers max and min"),
    ("a chronicle that is a word", lambda d: d["world"].update(chronicle="none"), "city.world.chronicle: must be a list of entries"),
    ("a chronicle entry that is a number", lambda d: d["world"]["chronicle"].__setitem__(0, 3), "chronicle[0]: must be an object"),
    ("a chronicle entry that is neither split nor over", lambda d: d["world"].update(chronicle=[{"seq": 1}]), "must be a split (from, label, houses, count_before, count_after) or an over"),
    ("a chronicle entry with no arrival", lambda d: d["world"]["chronicle"][0].pop("seq"), "chronicle[0]: seq is missing"),
    ("a chronicle entry for arrival 0", lambda d: d["world"]["chronicle"][0].update(seq=0), "chronicle[0].seq: must be a whole number, 1 or more"),
    ("a split with no houses", lambda d: d["world"]["chronicle"][0].pop("houses"), "chronicle[0]: houses is missing"),
    ("a split whose count is a word", lambda d: d["world"]["chronicle"][0].update(count_before="41"), "chronicle[0].count_before: must be a whole number"),
    ("a split with no new road", lambda d: d["world"]["chronicle"][0].pop("label"), "chronicle[0]: label is missing"),
    ("an over with no count", lambda d: d["world"]["chronicle"][-1].pop("count"), ": count is missing (a whole number)"),
    ("an over of a road that is a number", lambda d: d["world"]["chronicle"][-1].update(over=7), ".over: must be a place id (a string)"),
    ("an entry of an annex whose item is a number", lambda d: an_entry(d, "annex").update(annex=7), ".annex: must be the id of the item (a string)"),
    ("an entry of an annex with no house", lambda d: an_entry(d, "annex").pop("parent"), ": parent is missing (the id of its house (a string))"),
    ("an entry of an annex of a form nobody knows", lambda d: an_entry(d, "annex").update(form="shed"), ".form: must be one of wing, mailbox, got 'shed'"),
    ("an entry of an annex with no arrival", lambda d: an_entry(d, "annex").pop("seq"), ": seq is missing"),
    ("an entry of an annex for arrival 0", lambda d: an_entry(d, "annex").update(seq=0), ".seq: must be a whole number, 1 or more"),
]


@pytest.mark.parametrize("what, mistake, names", MISTAKES, ids=[m[0] for m in MISTAKES])
def test_a_city_that_is_not_what_build_writes_is_refused_and_the_message_names_the_place(real_city, what, mistake, names):
    doc = copy.deepcopy(real_city)
    mistake(doc)
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert names in str(refused.value), str(refused.value)


BIG = 10**400  # an integer of 401 digits: too large for a float, and for every field

NUMBERS = [  # (the number, how to put a value there, what the message names)
    ("a measure", lambda d, v: d["composition"]["measure"].update(walk_mean=v), "measure.walk_mean: must be a number"),
    ("the radius of the plaza", lambda d, v: d["places"]["place:plaza"].update(radius=v), "places['place:plaza'].radius: must be a number, 0 or more"),
    ("a coordinate of a house", lambda d, v: d["places"][first_lot(d)]["position"].update(x=v), ".position: must be {x, z}: two numbers"),
    ("a facing", lambda d, v: d["places"][first_lot(d)].update(facing=v), ".facing: must be a bearing in degrees"),
    ("a point of a road", lambda d, v: next(iter(d["roads"].values())).update(points=[[0, 0], [v, 1]]), ".points: must be a list of at least two"),
    ("a bearing of a sector", lambda d, v: d["composition"]["ring1"][0].update({"from": v}), "ring1[0].from: must be a bearing in degrees"),
    ("the weight of a street", lambda d, v: d["places"][a_street(d)].update(weight=v), ".weight: must be a number"),
    ("the position of an annex", lambda d, v: d["places"][an_annex(d)].update(position={"x": v, "z": 0}), ".position: must be {x, z}: two numbers"),
    ("the radius of a lane", lambda d, v: d["places"][a_street(d, "rib")]["rib"].update(band=0, s=v), ".rib.s: must be a number of at least 1"),
    ("the radius of the ring road", lambda d, v: d["places"][the_ring(d)]["ring"].update(radius=v), ".ring.radius: must be a number of at least 1"),
    ("a corner of the coast", lambda d, v: d["coast"]["polygons"][0].__setitem__(0, [v, 0]), "coast.polygons[0]: must be a list of at least three"),
    ("the number of buildings", lambda d, v: d["composition"].update(buildings=v), "composition.buildings: must be a number"),
    ("the total of streets", lambda d, v: d["composition"]["streets"].update(total=v), "composition.streets.total: must be a number"),
]
WHOLES = [  # (the whole number, how to put a value there, what the message names)
    ("a level", lambda d, v: d["places"][a_street(d)].update(level=v), ".level: must be a whole number"),
    ("a band", lambda d, v: d["places"][a_street(d, "rib")]["rib"].update(band=v), ".rib.band: must be a whole number or null"),
    ("the rank of an annex", lambda d, v: d["places"][an_annex(d)].update(rank=v), ".rank: must be a whole number, 1 or more"),
    ("an arrival", lambda d, v: d["world"]["chronicle"][0].update(seq=v), "chronicle[0].seq: must be a whole number, 1 or more"),
    ("a count of a split", lambda d, v: d["world"]["chronicle"][0].update(count_before=v), "chronicle[0].count_before: must be a whole number"),
    ("the count of an over", lambda d, v: d["world"]["chronicle"][-1].update(count=v), ".count: must be a whole number"),
    ("the rule", lambda d, v: d["world"]["districts"].update(max=v), "world.districts: must be an object with whole numbers max and min"),
]
SIZED = [pytest.param(put, names, id=what) for what, put, names in NUMBERS + WHOLES]


@pytest.mark.parametrize("put, names", SIZED)
@pytest.mark.parametrize("value", [BIG, -BIG, 10**5000], ids=["10**400", "-10**400", "10**5000"])
def test_an_integer_too_large_for_a_float_is_an_input_error_with_its_place_and_not_an_overflow(real_city, put, names, value):
    doc = copy.deepcopy(real_city)
    put(doc, value)
    with pytest.raises(inputs.InputError) as refused:  # (an OverflowError from `math.isfinite` would not be one)
        inputs.read_city(doc)
    assert names in str(refused.value)


@pytest.mark.parametrize("put, names", SIZED)
@pytest.mark.parametrize("value", [BIG, -BIG, float("inf"), -float("inf"), float("nan")], ids=["10**400", "-10**400", "inf", "-inf", "nan"])
def test_the_same_after_a_round_trip_through_json_text(real_city, put, names, value):
    doc = copy.deepcopy(real_city)
    put(doc, value)
    text = json.dumps(doc)  # an integer is written out in full; infinity and NaN as the words that `json` reads back
    assert str(value) in text or isinstance(value, float)
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(json.loads(text))
    assert names in str(refused.value)


LANES = [("a lane", lambda d, v: d["places"][a_street(d, "rib")]["rib"].update(band=0, s=v), ".rib.s"),
         ("the ring road", lambda d, v: d["places"][the_ring(d)]["ring"].update(radius=v), ".ring.radius")]


@pytest.mark.parametrize("put, where", [pytest.param(put, where, id=what) for what, put, where in LANES])
@pytest.mark.parametrize("value", [5e-324, 1e-300, 1e-9, 0.5, 0.999], ids=["5e-324", "1e-300", "1e-9", "0.5", "0.999"])
def test_the_radius_of_a_lane_is_at_least_a_cell_and_the_reader_says_so_where_the_picture_would_divide_by_nothing(real_city, put, where, value):
    """A house of a band or of the ring road is a polar cell of its lane: `picture` takes half a cell as the angle 0.5 / radius, which for the smallest number above 0 is 1e323, infinity,
    and the sine of it a ValueError. A lane is at least 1 cell from the town hall (a house stands one cell inside it, so it must have an inside)."""
    doc = copy.deepcopy(real_city)
    put(doc, value)
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert f"{where}: must be a number of at least 1 (the radius of the lane" in str(refused.value)
    for kind, edge in (("a lane of one cell is read and drawn", 1.0), ("so is one of a hundred", 100.0)):
        doc = copy.deepcopy(real_city)
        put(doc, edge)
        assert picture.render(inputs.read_city(doc), None, size=400).startswith("<svg"), kind


def test_a_number_written_as_1e400_is_infinity_in_a_json_file_and_is_refused(real_city):
    doc = copy.deepcopy(real_city)
    doc["composition"]["measure"]["walk_mean"] = "@@"
    text = json.dumps(doc).replace('"@@"', "1e400")
    assert json.loads(text)["composition"]["measure"]["walk_mean"] == float("inf")
    with pytest.raises(inputs.InputError, match="measure.walk_mean: must be a number, got inf"):
        inputs.read_city(json.loads(text))


def test_a_number_is_judged_by_its_range_first_so_that_no_integer_can_overflow_and_a_message_never_prints_thousands_of_digits():
    for huge in (BIG, -BIG, 10**5000):
        assert inputs._number(huge) is False and inputs._whole(huge) is False  # no OverflowError, no ValueError for the 4300 digits of `repr`
        assert inputs._shown(huge).startswith("an integer of about ") and len(inputs._shown(huge)) < 40
    assert [inputs._number(v) for v in (0, 1e7, -1e7, 1e7 + 1, float("nan"), float("inf"), True, "1")] == [True, True, True, False, False, False, False, False]
    assert [inputs._whole(v) for v in (0, 10**12, -(10**12), 10**12 + 1, True, 2.0)] == [True, True, True, False, False, False]
    assert inputs._shown("x" * 100) == repr("x" * 100)[:37] + "..." and inputs._shown(41) == "41"


def test_the_problems_of_a_city_are_reported_together_and_a_street_outside_the_sectors_once(real_city):
    doc = copy.deepcopy(real_city)
    template = next(iter(doc["roads"].values()))
    doc["roads"].update({f"road:extra:{i}": dict(template) for i in range(30)})
    for road in doc["roads"].values():
        road["class"] = "bad"
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    lines = str(refused.value).splitlines()
    assert len(lines) == inputs.MAX_PROBLEMS + 1 and lines[-1].startswith("... and ") and all("class" in line for line in lines[:-1])
    gone = copy.deepcopy(real_city)
    gone["composition"]["ring1"].pop(0)  # the houses of the sector's roads stand under a street that is no sector any more: one line a street, not one a house
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(gone)
    assert len(str(refused.value).splitlines()) == 2


def test_the_links_are_followed_only_when_the_shapes_are_right(real_city):
    doc = copy.deepcopy(real_city)
    doc["places"][a_street(doc)]["parent"] = 5  # a shape problem: the line of parents is not walked, so nothing breaks while checking
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert ".parent: must be the id of the street above, or of the plaza" in str(refused.value)


# ------------------------------------------------------------------------- a city file of an earlier version ----
def with_a_continuation_rib(doc, road, first):
    """The document as version 0.3 wrote a full road: the slots from `first` on in a second record of the road (`lane_of`, `ordinal` 2, `continued`), listed in the `lanes` of
    the road, with a road of its own. The engine makes no such rib any more; city files that have them are still read."""
    places, roads = doc["places"], doc["roads"]
    rec = places[road]
    slots, key = rec["rib"]["slots"], road.removeprefix("place:tag:")
    lane, lane_road = f"place:lane:{key}:2", f"road:place:lane:{key}:2"
    lots = [p for p in places.values() if p["kind"] == "lot" and p["parent"] == road and p["slot"] >= first]
    for p in lots:
        p["parent"], p["slot"], p["order"] = lane, p["slot"] - first, p["slot"] - first
    places[lane] = {"kind": "street", "shape": "rib", "lane_of": road, "ordinal": 2, "continued": True, "level": rec["level"], "class": rec["class"], "parent": road,
                    "label": rec["address"][-1], "address": list(rec["address"]), "carrier": rec["carrier"], "lots": len(lots), "reserved": slots - first - len(lots),
                    "road": lane_road, "rib": {**rec["rib"], "x0": rec["rib"]["x0"] + first // 2, "slots": slots - first}}
    rec["lots"], rec["reserved"], rec["lanes"] = rec["lots"] - len(lots), 0, [lane]
    rec["rib"]["slots"], rec["rib"]["x1"] = first, rec["rib"]["x0"] + first // 2
    roads[lane_road] = {**roads[rec["road"]], "street": lane, "parent": rec["road"]}
    doc["composition"]["streets"]["continuations"] += 1
    return doc


def test_a_city_file_of_version_0_3_with_a_continuation_rib_is_still_read_drawn_and_counted_once():
    chronicle_lines, summary = city.chronicle_lines, city.summary
    tree, library = sample()
    made = json.loads(lay.render(bibliopolis.build_city(library, tree)))
    doc = with_a_continuation_rib(copy.deepcopy(made), "place:tag:ecology", 24)
    assert doc["places"]["place:tag:ecology"]["lanes"] == ["place:lane:ecology:2"] and doc["places"]["place:lane:ecology:2"]["lots"] == 11
    old = inputs.read_city(copy.deepcopy(doc))
    assert summary(old)["roads"] == summary(inputs.read_city(copy.deepcopy(made)))["roads"] == 23  # (a road is counted once, whatever the ribs it has)
    assert picture.render(old) and chronicle_lines(old) == chronicle_lines(inputs.read_city(copy.deepcopy(made)))


# ------------------------------------------------------------------------------------ nothing gets through ----
WRONG = (None, "x", -1, 0, 2.5, [], {}, [1, 2], float("inf"), True, 10**400)  # what to put where the right thing was (or take the key away)
LINKS = ("parent", "place", "road", "from", "over", "lane_of", "trunk", "carrier", "lane")  # keys that name another place or road


def targets(doc):
    """The parts of the document to break: two places of every kind (kind, shape, continuation, level), two roads of every kind, and every other
    part that the two commands read."""
    paths: list[list] = [[], ["composition"], ["composition", "ring1", 0], ["composition", "measure"], ["composition", "streets"], ["world"], ["world", "districts"]]
    if "coast" in doc:
        paths += [["coast"], ["coast", "polygons", 0], ["coast", "polygons", 0, 0]]
    seen: collections.Counter = collections.Counter()
    for pid, p in doc["places"].items():
        sig = (pid == "place:plaza", p["kind"], p.get("shape"), "lane_of" in p, p.get("level"))
        if seen[sig] < 2:
            seen[sig] += 1
            paths.append(["places", pid])
            paths += [["places", pid, key] for key in ("position", "rib", "address") if key in p]
    seen.clear()
    for rid, r in doc["roads"].items():
        if seen[r["kind"]] < 2:
            seen[r["kind"]] += 1
            paths += [["roads", rid], ["roads", rid, "points"], ["roads", rid, "points", 0]]
    chronicle = doc["world"]["chronicle"]
    for wanted in ("from", "over", "annex", "absorbed"):
        i = next((i for i, e in enumerate(chronicle) if wanted in e), None)
        if i is not None:
            paths.append(["world", "chronicle", i])
            if wanted == "from":
                paths.append(["world", "chronicle", i, "houses"])
    return paths


def at(doc, path):
    for key in path:
        doc = doc[key]
    return doc


def fuzz(base, reader, stop_after=None, only=None):
    """Break `base` one field at a time (take a key away, or put each of WRONG there; a key that names a place gets a few places as well) and return what
    `reader` let through that then crashed `picture.render` or `city.chronicle_lines`, with how many documents were refused and how many accepted.
    `stop_after`: give up after that many findings. `only`: break the parts whose path it accepts, and no others."""
    ids = ["place:plaza", the_root(base), first_lot(base), base["composition"]["ring1"][0]["place"], a_street(base), *([an_annex(base)] if any(p["kind"] == "annex" for p in base["places"].values()) else [])]
    failures, tally = [], collections.Counter()
    for path in (p for p in targets(base) if only is None or only(p)):
        node = at(base, path)
        for key in (list(node) if isinstance(node, dict) else range(len(node))):
            options = ["take away", *WRONG, *(ids + [path[-1]] if key in LINKS else [])]
            for wrong in options:
                doc = copy.deepcopy(base)
                holder = at(doc, path)
                if wrong == "take away":
                    holder.pop(key)
                else:
                    holder[key] = copy.deepcopy(wrong)
                try:
                    reader(doc)
                except inputs.InputError:
                    tally["refused"] += 1
                    continue
                tally["accepted"] += 1
                try:
                    picture.render(doc)
                    city.chronicle_lines(doc)
                except Exception as exc:  # noqa: BLE001 - any exception at all is the finding
                    failures.append((path, key, wrong, f"{type(exc).__name__}: {str(exc)[:60]}"))
                    if stop_after and len(failures) >= stop_after:
                        return failures, tally
    return failures, tally


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_no_single_wrong_field_gets_past_the_reader_to_crash_a_picture_or_the_chronicle(mode):
    base = worlds(mode)
    assert inputs.read_city(copy.deepcopy(base))
    kinds = {(p["kind"], p.get("shape"), "lane_of" in p) for p in base["places"].values()}
    assert {("lot", None, False), ("street", "ring", True), ("street", "rib", False), ("street", "trunk", False), ("street", "ring", False), ("annex", None, False)} <= kinds
    assert {"wing", "mailbox"} == {p["form"] for p in base["places"].values() if p["kind"] == "annex"} and [e for e in base["world"]["chronicle"] if "annex" in e]
    assert not [p for p in base["places"].values() if p.get("underground")]  # (no house, no street under the town hall: the ring road is on the surface)
    failures, tally = fuzz(base, inputs.read_city)
    assert failures == [], failures[:5]
    assert tally["refused"] > 1_000 and tally["accepted"] > 1_000  # the documents that were broken, and refused or not worth refusing (a key nothing reads)


def test_the_break_in_reaches_the_annexes_and_their_entries_and_a_reader_that_lets_everything_through_is_caught_there_too():
    """The one-field break-in takes the annex places and the entries of the chronicle that are theirs as targets, like any other part, and a reader that accepts everything lets crashes of
    the picture and the chronicle through there: the reader of the annex keys is what stops them."""
    base = worlds("grow")
    ids = {pid for pid, p in base["places"].items() if p["kind"] == "annex"}
    assert len(ids) >= 8 and any(path[:2] == ["places", pid] for path in targets(base) for pid in ids) and ["world", "chronicle"] in [path[:2] for path in targets(base)]
    only = lambda path: (path[:1] == ["places"] and path[1] in ids) or (path[:2] == ["world", "chronicle"] and "annex" in base["world"]["chronicle"][path[2]])  # noqa: E731
    failures, tally = fuzz(base, inputs.read_city, only=only)
    assert failures == [] and tally["refused"] > 100
    failures, tally = fuzz(base, lambda doc: doc, only=only)
    assert tally["refused"] == 0 and len(failures) > 20
    assert {"KeyError", "TypeError"} <= {f[3].split(":")[0] for f in failures} and {f[1] for f in failures} >= {"parent", "rank"}  # (the keys that the picture reads)
    assert any(f[0][:1] == ["world"] for f in failures)  # (and the chronicle: the sentence of an entry reads its keys)


def test_the_control_a_reader_that_lets_everything_through_is_caught_by_the_same_break_in():
    base = worlds("mirror")
    failures, tally = fuzz(base, lambda doc: doc, stop_after=400)
    assert tally["refused"] == 0 and len(failures) == 400
    assert {"KeyError", "TypeError", "AttributeError"} <= {f[3].split(":")[0] for f in failures}  # crashes ...
    # ... and the circle of parents, which would have been a loop for ever and is a ValueError since `picture` bounds its walk
    doc = copy.deepcopy(base)
    street = a_street(doc)
    doc["places"][street]["parent"] = street
    with pytest.raises(ValueError, match="round in a circle"):
        picture.render(doc)
