"""The synthetic sample in examples/: made from a seed, valid, and what the README says it shows (the README builds a city from it)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import checks
import pytest

import bibliopolis
from bibliopolis import inputs

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def load_generator():
    spec = importlib.util.spec_from_file_location("make_example", EXAMPLES / "make_example.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sample():
    return json.loads((EXAMPLES / "tree.json").read_text(encoding="utf-8")), json.loads((EXAMPLES / "library.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grown(sample):
    return bibliopolis.build_city(sample[1], sample[0], mode="grow")


@pytest.fixture(scope="module")
def mirrored(sample):
    return bibliopolis.build_city(sample[1], sample[0], mode="mirror")


def test_the_files_are_what_the_generator_makes_from_its_seed(tmp_path):
    gen = load_generator()
    assert gen.main(["--out", str(tmp_path)]) == 0
    for name in ("tree.json", "library.json"):
        assert (tmp_path / name).read_bytes() == (EXAMPLES / name).read_bytes(), name
    again = tmp_path / "again"
    assert gen.main(["--seed", "7", "--out", str(again)]) == 0 and (again / "library.json").read_bytes() == (EXAMPLES / "library.json").read_bytes()
    other = tmp_path / "other"
    assert gen.main(["--seed", "8", "--out", str(other)]) == 0 and (other / "library.json").read_bytes() != (EXAMPLES / "library.json").read_bytes()


def test_the_sample_has_about_80_topics_and_600_items_and_every_field_the_format_names(sample):
    tree, library = sample
    nodes = inputs.read_tree(tree)["nodes"]
    items = inputs.read_library(library, {"nodes": nodes})
    assert len(nodes) == 80 and len(items) == 600
    assert all(i["doi"] is None or i["doi"].startswith("10.0000/") for i in items) and 0 < sum(1 for i in items if i["doi"] is None) < 100
    assert sum(1 for i in items if not i["topics"]) == 15 and sum(1 for i in items if len(i["topics"]) > 1) > 20
    assert {i["type"] for i in items} >= {"article", "review", "editorial", "letter", "news", "erratum", "retraction notice"}
    assert any("T" in i["added_at"] for i in items) and any("T" not in i["added_at"] for i in items)
    assert [i["id"] for i in library["items"]] == sorted(i["id"] for i in library["items"])  # the file is in id order: the arrival order is added_at's
    assert [i["id"] for i in items] != [i["id"] for i in library["items"]]


def test_the_growing_city_opens_its_first_road_at_house_41_and_shows_a_split_an_over_road_and_a_chain(grown):
    chronicle = grown["world"]["chronicle"]
    first = chronicle[0]
    assert (first["seq"], first["from"], first["count_before"]) == (41, "place:root", 41) and first["to"] == "place:tag:computing" and first["at"]
    assert grown["world"]["houses"] == grown["composition"]["articles"] == 600
    assert [e["over"] for e in chronicle if "over" in e] == ["place:tag:networks"]  # 44 houses of its own, no group below it: over
    labels = {p["label"] if "label" in p else p["address"][-1] for p in grown["places"].values() if p["kind"] == "street"}
    assert "Humanities・History" in labels  # a chain of topics, one road
    streets = grown["composition"]["streets"]
    assert streets["total"] == len([p for p in grown["places"].values() if p["kind"] == "street" and "lane_of" not in p and not p.get("underground")]) >= 20
    assert streets["continuations"] > 0 and streets["underground"] == 1
    assert 0 < grown["composition"]["measure"]["underground_lots"] < 40  # the houses of topics too thin for a road, and those with no topic
    assert sum(1 for e in chronicle if "from" in e) >= 20 and [e["n"] for e in chronicle] == list(range(1, len(chronicle) + 1))


def test_the_mirror_city_has_a_road_for_every_topic_that_holds_a_house(sample, mirrored):
    tree, library = sample
    held = {t for i in library["items"] for t in i["topics"]}
    ancestors = {n["id"]: n["parent"] for n in tree["nodes"]}
    holders = set(held)
    for t in held:
        while ancestors[t] is not None:
            t = ancestors[t]
            holders.add(t)
    roads = {p["tag"] for p in mirrored["places"].values() if p["kind"] == "street" and "lane_of" not in p and p.get("tag")}
    assert roads == holders and len(roads) == 79 and "literature" not in roads  # a topic with nothing in it is no road
    assert not [e for e in mirrored["world"]["chronicle"] if "from" in e]
    assert [e["over"] for e in mirrored["world"]["chronicle"] if "over" in e] == ["place:tag:networks"]
    assert mirrored["composition"]["measure"]["underground_lots"] == 15  # exactly the items with no topic


def test_both_cities_are_sound_geometry(grown, mirrored):
    assert checks.document_problems(grown) == {} and checks.document_problems(mirrored) == {}
    for doc in (grown, mirrored):
        assert doc["composition"]["measure"]["lots"] + doc["composition"]["measure"]["underground_lots"] == 600
        assert len([p for p in doc["places"].values() if p["kind"] == "lot"]) == 600  # one house per item


def test_the_readme_command_builds_the_cities_from_the_files_of_the_repository(tmp_path):
    for mode in ("grow", "mirror"):
        out = tmp_path / f"city-{mode}.json"
        done = subprocess.run([sys.executable, "-m", "bibliopolis", "build", "--library", "examples/library.json", "--tree", "examples/tree.json",
                               "--mode", mode, "--out", str(out)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        assert json.loads(out.read_text(encoding="utf-8"))["world"]["mode"] == mode
