"""What docs/format.md says is true of the program: its examples load through the reader, its chronicle entries have the keys the engine writes, and its
reading of `lots` and `reserved` (one segment each; a whole road is its record plus its continuation lanes) gives the houses of every road of the sample."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

import bibliopolis
from bibliopolis import inputs
from bibliopolis.document import world_layout

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "format.md").read_text(encoding="utf-8")
EXAMPLES = ROOT / "examples"


def json_values(block):
    """The JSON values one after another in a block of a page (an object may run over several lines)."""
    decoder, i, out = json.JSONDecoder(), 0, []
    while True:
        while i < len(block) and block[i].isspace():
            i += 1
        if i >= len(block):
            return out
        value, i = decoder.raw_decode(block, i)
        out.append(value)


def examples():
    values = [v for block in re.findall(r"^```json\n(.*?)^```", PAGE, flags=re.S | re.M) for v in json_values(block)]
    return ([v for v in values if "items" in v], [v for v in values if "nodes" in v], [v for v in values if "n" in v and "trigger" in v])


@pytest.fixture(scope="module")
def sample():
    return json.loads((EXAMPLES / "tree.json").read_text(encoding="utf-8")), json.loads((EXAMPLES / "library.json").read_text(encoding="utf-8"))


def test_every_complete_json_example_of_the_format_page_loads_through_the_reader():
    libraries, trees, entries = examples()
    assert len(libraries) >= 1 and len(trees) >= 1 and len(entries) == 2  # the library, the tree, and the two chronicle entries
    for tree in trees:
        checked = inputs.read_tree(tree)
        assert len(checked["nodes"]) == len(tree["nodes"])
        for library in libraries:  # the library example files its item under a topic of the tree example
            items = inputs.read_library(library, checked)
            assert len(items) == len(library["items"])
            doc = bibliopolis.build_city(library, tree)  # ... and the two examples make a city
            assert doc["world"]["houses"] == len(items)


def test_the_chronicle_entries_of_the_format_page_have_the_keys_the_engine_writes(sample):
    tree, library = sample
    doc = bibliopolis.build_city(library, tree, mode="grow")
    split = next(e for e in doc["world"]["chronicle"] if "from" in e)
    over = next(e for e in doc["world"]["chronicle"] if "over" in e)
    _libraries, _trees, entries = examples()
    shown_split = next(e for e in entries if "from" in e)
    shown_over = next(e for e in entries if "over" in e)
    assert list(shown_split) == list(split) and list(shown_over) == list(over)  # the same keys in the same order
    assert (shown_split["trigger"], shown_split["event_id"], shown_over["trigger"], shown_over["event_id"]) == ("arrival", None, "arrival", None)
    assert shown_split["seq"] == split["seq"] == 41 and shown_split["from"] == split["from"] and shown_split["to"] == split["to"]


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_a_whole_road_is_its_record_plus_its_continuation_lanes_and_not_the_roads_below_it(sample, mode):
    tree, library = sample
    _plan, _tv, world, _items = bibliopolis.build_world(library, tree, mode=mode)
    doc = world_layout(world)
    places = doc["places"]
    direct = Counter(p["street"] for p in world["places"].values() if p["kind"] == "lot")
    empty = Counter(p["parent"] for p in world["places"].values() if p["kind"] == "reserved")
    roads = [pid for pid, rec in places.items() if rec["kind"] == "street" and "lane_of" not in rec]
    assert len(roads) >= 22
    for pid in roads:
        segments = [places[pid], *(places[lane] for lane in places[pid].get("lanes", []))]
        assert sum(seg["lots"] for seg in segments) == direct[pid], pid  # the houses of the road itself
        assert all(seg["reserved"] == empty[seg_id] for seg, seg_id in zip(segments, [pid, *places[pid].get("lanes", [])])), pid  # reserved is per segment too
        assert all(seg["lots"] == sum(1 for p in places.values() if p["kind"] == "lot" and p["parent"] == seg_id)
                   for seg, seg_id in zip(segments, [pid, *places[pid].get("lanes", [])])), pid  # a segment's lots are the lots whose parent it is
    assert sum(direct.values()) == doc["world"]["houses"] == 600


def test_ecology_of_the_sample_is_eighteen_in_its_record_and_seventeen_in_its_continuation(sample):
    tree, library = sample
    doc = bibliopolis.build_city(library, tree, mode="grow")
    road = doc["places"]["place:tag:ecology"]
    (lane_id,) = road["lanes"]
    lane = doc["places"][lane_id]
    assert (road["lots"], lane["lots"], road["lots"] + lane["lots"]) == (18, 17, 35)
    assert lane["continued"] is True and lane["lane_of"] == "place:tag:ecology" and lane["label"] == road["address"][-1] == "Ecology"


def test_the_houses_of_the_roads_below_a_road_are_not_its_own(sample):
    tree, library = sample
    _plan, _tv, world, _items = bibliopolis.build_world(library, tree, mode="grow")
    doc = world_layout(world)
    direct = Counter(p["street"] for p in world["places"].values() if p["kind"] == "lot")
    children: dict[str, list[str]] = {}
    for pid, rec in doc["places"].items():
        if rec["kind"] == "street" and "lane_of" not in rec and rec["parent"] != "place:plaza":
            children.setdefault(rec["parent"], []).append(pid)

    def subtree(pid):
        return direct[pid] + sum(subtree(c) for c in children.get(pid, []))

    computing = "place:tag:computing"
    own = doc["places"][computing]["lots"] + sum(doc["places"][lane]["lots"] for lane in doc["places"][computing].get("lanes", []))
    assert children[computing] and own == direct[computing] < subtree(computing)  # Computing has roads below it: their houses are theirs
    assert subtree(computing) == 190  # the whole district: the sample files 190 items under Computing, none of them is left under the town hall
