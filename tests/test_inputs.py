"""Reading and checking the library and the topic tree (bibliopolis.inputs, docs/format.md)."""

import copy
import json

import pytest
from support import T, make_tree

import bibliopolis
from bibliopolis import inputs
from bibliopolis.tree import TreeView, major_tag

TREE = {"nodes": [{"id": "sci", "label": "Science", "parent": None}, {"id": "bio", "label": "Biology", "parent": "sci"},
                  {"id": "gen", "label": "Genetics", "parent": "bio"}, {"id": "phy", "label": "Physics", "parent": "sci"},
                  {"id": "arts", "label": "Arts", "parent": None}]}


def item(i="a", **kw):
    base = {"id": i, "title": f"Title {i}", "authors": ["A. Author"], "year": 2020, "doi": f"10.0000/{i}", "added_at": "2024-03-01", "type": "article",
            "tags": ["x"], "topics": ["gen"]}
    base.update(kw)
    return base


def library(*items):
    return {"items": list(items)}


def problems(fn, *args):
    with pytest.raises(inputs.InputError) as caught:
        fn(*args)
    return str(caught.value).splitlines()


# ------------------------------------------------------------------------------------------------ tree ----
def test_a_tree_is_read_as_it_is_with_the_extra_keys_dropped():
    doc = {"nodes": [{"id": "a", "label": "A", "parent": None, "note": "ignored"}, {"id": "b", "label": "B", "parent": "a"}], "extra": 1}
    assert inputs.read_tree(doc) == {"nodes": [{"id": "a", "label": "A", "parent": None}, {"id": "b", "label": "B", "parent": "a"}]}
    assert inputs.read_tree({"nodes": []}) == {"nodes": []}


def test_a_tree_view_gives_parents_depths_children_and_roots():
    tv = TreeView(inputs.read_tree(TREE))
    assert tv.roots() == ["arts", "sci"] and tv.kids("sci") == ["bio", "phy"] and tv.parent("gen") == "bio" and tv.label("gen") == "Genetics"
    assert [tv.depth(x) for x in ("sci", "bio", "gen", "arts")] == [1, 2, 3, 1] and "gen" in tv and "nowhere" not in tv and len(tv) == 5
    assert tv.ids() == ["arts", "bio", "gen", "phy", "sci"] and tv.kids("gen") == []


@pytest.mark.parametrize("doc, where", [
    ([], "tree: must be an object"),
    ({"nodes": "x"}, "tree: must be an object"),
    ({"nodes": [5]}, "tree.nodes[0]: must be an object"),
    ({"nodes": [{"id": "a", "label": "A"}]}, "tree.nodes[0]: missing parent"),
    ({"nodes": [{"label": "A"}]}, "tree.nodes[0]: missing id, parent"),
    ({"nodes": [{"id": "", "label": "A", "parent": None}]}, "tree.nodes[0].id: must not be empty"),
    ({"nodes": [{"id": 7, "label": "A", "parent": None}]}, "tree.nodes[0].id: must be a string"),
    ({"nodes": [{"id": "a", "label": " ", "parent": None}]}, "tree.nodes[0].label: must not be empty"),
    ({"nodes": [{"id": "a\nb", "label": "A", "parent": None}]}, "tree.nodes[0].id: must not contain control characters"),
    ({"nodes": [{"id": "a", "label": "A", "parent": 3}]}, "tree.nodes[0].parent: must be a node id or null"),
    ({"nodes": [{"id": "a", "label": "A", "parent": "b"}]}, "tree.nodes[0].parent: 'b' is not the id of a node"),
    ({"nodes": [{"id": "a", "label": "A", "parent": None}, {"id": "a", "label": "B", "parent": None}]}, "tree.nodes[1].id: 'a' is used twice (first at tree.nodes[0])"),
    ({"nodes": [{"id": "lane:a:2", "label": "A", "parent": None}]}, "looks like the block key of a continuation rib"),
    ({"nodes": [{"id": "a", "label": "A", "parent": "a"}]}, "lead round in a circle"),
    ({"nodes": [{"id": "a", "label": "A", "parent": "b"}, {"id": "b", "label": "B", "parent": "a"}]}, "lead round in a circle"),
    ({"nodes": [{"id": "a\ud800", "label": "A", "parent": None}]}, "cannot be written as UTF-8"),
])
def test_a_tree_that_is_not_what_the_format_says_is_refused_with_the_place(doc, where):
    lines = problems(inputs.read_tree, doc)
    assert any(where in line for line in lines), lines


def test_a_tree_deeper_than_the_engine_takes_is_refused():
    nodes = [{"id": f"n{i}", "label": f"N{i}", "parent": f"n{i - 1}" if i else None} for i in range(inputs.MAX_DEPTH + 1)]
    assert "levels deep" in problems(inputs.read_tree, {"nodes": nodes})[0]
    assert len(inputs.read_tree({"nodes": nodes[:inputs.MAX_DEPTH]})["nodes"]) == inputs.MAX_DEPTH


def test_every_problem_of_a_document_is_reported_at_once_up_to_a_limit():
    nodes = [{"id": f"n{i}", "label": "", "parent": None} for i in range(inputs.MAX_PROBLEMS + 5)]
    lines = problems(inputs.read_tree, {"nodes": nodes})
    assert len(lines) == inputs.MAX_PROBLEMS + 1 and lines[-1] == "... and 5 more" and lines[0].startswith("tree.nodes[0].label")
    two = problems(inputs.read_tree, {"nodes": [{"id": "a", "label": "", "parent": None}, {"id": "b", "label": "B", "parent": "zz"}]})
    assert len(two) == 2


# -------------------------------------------------------------------------------------------- library ----
def read(*items):
    return inputs.read_library(library(*items), inputs.read_tree(TREE))


def test_items_arrive_in_added_at_order_and_ties_come_in_code_point_order_of_the_id():
    got = read(item("c", added_at="2024-03-02"), item("b", added_at="2024-03-01"), item("a", added_at="2024-03-01"), item("B", added_at="2024-03-01"))
    assert [i["id"] for i in got] == ["B", "a", "b", "c"]  # "B" < "a" in code points


def test_added_at_is_an_instant_so_dates_times_and_offsets_order_by_the_moment_they_name():
    got = read(item("late", added_at="2024-03-01T02:00:00Z"), item("early", added_at="2024-03-01T09:00:00+08:00"), item("day", added_at="2024-03-01"),
               item("space", added_at="2024-03-01 01:30:00"), item("next", added_at="2024-03-02"))
    # 09:00+08:00 is 01:00Z; a date is midnight UTC; a time without an offset is read as UTC
    assert [i["id"] for i in got] == ["day", "early", "space", "late", "next"]
    assert [i["added_at"] for i in got][0] == "2024-03-01"  # the string is kept as it was written


def test_an_item_comes_back_with_its_fields_and_repeated_topics_once_and_the_doi_may_be_missing_or_null():
    got = read(item("a", topics=["gen", "phy", "gen"], doi=None, extra="dropped"), {k: v for k, v in item("b").items() if k != "doi"})
    assert got[0] == {"id": "a", "title": "Title a", "authors": ["A. Author"], "year": 2020, "doi": None, "added_at": "2024-03-01", "type": "article",
                      "tags": ["x"], "topics": ["gen", "phy"]}
    assert got[1]["doi"] is None
    assert read(item("a", year=None, authors=[], tags=[], topics=[], title=""))[0]["year"] is None


def test_the_address_of_an_item_is_its_deepest_topic_and_ties_go_to_the_lower_id():
    tv = TreeView(inputs.read_tree(TREE))
    assert major_tag(tv, item(topics=["sci", "gen", "bio"])) == "gen"
    assert major_tag(tv, item(topics=["phy", "bio"])) == "bio"  # both depth 2: "bio" < "phy"
    assert major_tag(tv, item(topics=["arts", "sci"])) == "arts" and major_tag(tv, item(topics=[])) is None
    assert major_tag(tv, item(topics=["nowhere"])) is None  # (the engine ignores what the tree lacks; inputs refuses it before)


@pytest.mark.parametrize("doc, where", [
    ([], "library: must be an object"),
    ({"items": {}}, "library: must be an object"),
    (library(7), "library.items[0]: must be an object"),
    (library({"id": "a"}), "library.items[0]: missing title, authors, year, added_at, type, tags, topics"),
    (library(item(id="")), "library.items[0].id: must not be empty"),
    (library(item(title=3)), "title: must be a string"),
    (library(item(type="")), "type: must not be empty"),
    (library(item(year="2020")), "year: must be a whole number or null"),
    (library(item(year=True)), "year: must be a whole number or null"),
    (library(item(year=2020.5)), "year: must be a whole number or null"),
    (library(item(doi="")), "doi: must not be empty"),
    (library(item(doi=7)), "doi: must be a string"),
    (library(item(authors="A. Author")), "authors: must be a list of strings"),
    (library(item(authors=[3])), "authors[0]: must be a string"),
    (library(item(tags="x")), "tags: must be a list of strings"),
    (library(item(topics="gen")), "topics: must be a list of topic ids"),
    (library(item(topics=[4])), "topics[0]: must be a topic id"),
    (library(item(topics=["nowhere"])), "topics[0]: 'nowhere' is not the id of a node of the tree"),
    (library(item(added_at="yesterday")), "added_at: 'yesterday' is not an ISO 8601 date"),
    (library(item(added_at="")), "added_at: must not be empty"),
    (library(item(added_at=20240301)), "added_at: must be a string"),
    (library(item("a"), item("a")), "library.items[1] ('a').id: used twice (first at library.items[0])"),
    (library(item(title="x\ud800")), "cannot be written as UTF-8"),
    (library(item(id="a\x00")), "must not contain control characters"),
])
def test_a_library_that_is_not_what_the_format_says_is_refused_with_the_place(doc, where):
    lines = problems(inputs.read_library, doc, inputs.read_tree(TREE))
    assert any(where in line for line in lines), lines


def test_all_the_problems_of_a_library_are_listed_each_with_its_item():
    lines = problems(inputs.read_library, library(item("a", topics=["nowhere"]), item("b", added_at="never"), item("c")), inputs.read_tree(TREE))
    assert len(lines) == 2 and "('a')" in lines[0] and "('b')" in lines[1]


def test_an_empty_library_is_a_library():
    assert inputs.read_library(library(), inputs.read_tree(TREE)) == [] and inputs.read_library(library(), inputs.read_tree({"nodes": []})) == []


# ---------------------------------------------------------------------------------------------- files ----
def test_json_files_are_read_as_utf8_with_or_without_a_byte_order_mark_and_a_bad_file_says_which(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"nodes": [{"id": "文", "label": "文獻", "parent": None}]}, ensure_ascii=False), encoding="utf-8")
    assert inputs.load_json(good)["nodes"][0]["label"] == "文獻"
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + good.read_bytes())
    assert inputs.load_json(bom) == inputs.load_json(good)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(inputs.InputError, match="bad.json: not valid JSON"):
        inputs.load_json(bad)
    latin = tmp_path / "latin.json"
    latin.write_bytes('{"a": "café"}'.encode("latin-1"))
    with pytest.raises(inputs.InputError, match="latin.json: not UTF-8"):
        inputs.load_json(latin)
    with pytest.raises(OSError):
        inputs.load_json(tmp_path / "missing.json")


# ------------------------------------------------------------------------------------------------ the city ----
@pytest.fixture(scope="module")
def real_city():
    tree, items = make_tree({"med": T(0, a=T(25), b=T(16)), "pub": T(14)})
    return bibliopolis.build_city({"items": items}, tree)


def test_a_city_that_build_wrote_is_read_as_it_is_also_after_a_round_trip_through_json(real_city):
    assert inputs.read_city(real_city) is real_city
    assert inputs.read_city(json.loads(json.dumps(real_city))) == real_city
    tree, items = make_tree({"med": T(0, a=T(25), b=T(16)), "pub": T(14)})
    assert inputs.read_city(bibliopolis.build_city({"items": items}, tree, mode="mirror"))["world"]["mode"] == "mirror"


def first_lot(doc):
    return next(p for p in doc["places"].values() if p["kind"] == "lot" and not p.get("underground"))


@pytest.mark.parametrize("change, expected", [
    (lambda d: d.pop("roads"), "city.roads: must be an object"),
    (lambda d: d.pop("world"), "city.world: must be an object"),
    (lambda d: d.update(layout_version="v3"), "layout_version is 'v3', not 'v4'"),
    (lambda d: d["places"].pop("place:plaza"), "city.places.place:plaza: must be an object with a label and a radius"),
    (lambda d: d["places"]["place:plaza"].update(radius="big"), "city.places.place:plaza"),
    (lambda d: d["places"].update({"place:odd": {"kind": "castle"}}), "city.places['place:odd']: must be an object whose kind is one of"),
    (lambda d: first_lot(d).pop("position"), "a house on the surface needs a position"),
    (lambda d: first_lot(d).update(parent="place:nowhere"), "a house on the surface needs a position"),
    (lambda d: next(iter(d["roads"].values())).update({"class": "avenue"}), "must be an object whose class is one of 大道, 路, 巷, 弄"),
    (lambda d: next(iter(d["roads"].values())).update(points=[[1, 2]]), "points must be a list of at least two [x, z] pairs"),
    (lambda d: next(iter(d["roads"].values())).update(points=[[1, 2], [3, "x"]]), "points must be a list of at least two [x, z] pairs"),
    (lambda d: d["composition"].update(ring1=[{"place": 1}]), "city.composition.ring1: must be a list of {place, label, from, to}"),
    (lambda d: d["composition"].pop("measure"), "city.composition: needs buildings, measure and streets"),
    (lambda d: d["world"].update(chronicle="none"), "city.world.chronicle: must be a list of entries that have a seq"),
    (lambda d: d["world"].update(chronicle=[{"n": 1}]), "city.world.chronicle"),
    (lambda d: d["world"].update(districts={"max": 40}), "city.world.districts: must be an object with max and min"),
])
def test_a_city_that_is_not_what_build_writes_is_refused_with_the_place(real_city, change, expected):
    doc = copy.deepcopy(real_city)
    change(doc)
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert expected in str(refused.value)


@pytest.mark.parametrize("doc", [None, [], "city", 3, {}, {"items": []}, {"nodes": []}, {"layout_version": "v4"}])
def test_what_is_no_city_at_all_is_refused_with_a_hint(doc):
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    assert "city" in str(refused.value) and len(str(refused.value).splitlines()) <= inputs.MAX_PROBLEMS + 1


def test_the_problems_of_a_city_are_reported_together(real_city):
    doc = copy.deepcopy(real_city)
    template = next(iter(doc["roads"].values()))
    doc["roads"].update({f"road:extra:{i}": dict(template) for i in range(30)})
    for road in doc["roads"].values():
        road["class"] = "bad"
    with pytest.raises(inputs.InputError) as refused:
        inputs.read_city(doc)
    lines = str(refused.value).splitlines()
    roads = len(doc["roads"])
    assert roads > 3 and len(lines) == (roads if roads <= inputs.MAX_PROBLEMS else inputs.MAX_PROBLEMS + 1)  # one line a road, then "... and n more"
    assert all("class" in line for line in lines[:3])
