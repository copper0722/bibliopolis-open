"""The golden files of the engine (examples/*.world.json and their index examples/worlds.json): the committed files are what examples/make_worlds.py makes today, byte for byte, they
equal what the helpers of the tests write, they fold to the pinned cities, and the index says so. A port in another language uses them as they are."""

import hashlib
import importlib.util
import json
from pathlib import Path

import hand_support
import pytest
from schema_support import faults
from test_world_file import PIN_BRANCHES_CITY, PIN_BRANCHES_WORLD, PIN_CITY, PIN_MERGE_CITY, PIN_MERGE_WORLD, PIN_NODES_CITY, PIN_NODES_WORLD, PIN_WORLD

from bibliopolis import cli
from bibliopolis import layout as lay
from bibliopolis.journal import dumps_world, load_world_file, world_document

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
MAKE = "python3 examples/make_worlds.py"
SCHEMA = json.loads((ROOT / "schema" / "world.schema.json").read_text(encoding="utf-8"))
WORLDS = {
    "scripted": ("scripted.world.json", PIN_WORLD, PIN_CITY),
    "scripted_nodes": ("scripted_nodes.world.json", PIN_NODES_WORLD, PIN_NODES_CITY),
    "scripted_merge": ("scripted_merge.world.json", PIN_MERGE_WORLD, PIN_MERGE_CITY),
    "scripted_branches": ("scripted_branches.world.json", PIN_BRANCHES_WORLD, PIN_BRANCHES_CITY),
}
FILES = sorted([name for name, _, _ in WORLDS.values()] + ["worlds.json"])


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_script():
    spec = importlib.util.spec_from_file_location("make_worlds", EXAMPLES / "make_worlds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


@pytest.fixture(scope="module")
def made(script):
    return script.worlds()


def test_the_script_makes_the_four_world_files_and_the_index(made):
    assert sorted(made) == FILES


def test_the_committed_files_are_what_the_script_makes_byte_for_byte(made):
    for name, text in made.items():
        assert (EXAMPLES / name).read_bytes() == text.encode("utf-8"), f"{name} is stale: run `{MAKE}` and commit the result"
    assert sorted(p.name for p in EXAMPLES.glob("*.world.json")) == [n for n in FILES if n != "worlds.json"]  # no file of an older script is left behind


@pytest.mark.parametrize("helper", list(WORLDS))
def test_each_world_file_is_what_the_helper_of_the_tests_writes(helper):
    name, _, _ = WORLDS[helper]
    journal = getattr(hand_support, helper)().journal
    assert (EXAMPLES / name).read_text(encoding="utf-8") == dumps_world(world_document(journal))


@pytest.mark.parametrize("helper", list(WORLDS))
def test_each_world_file_reads_and_writes_the_same_bytes_and_folds_to_the_pinned_city(helper):
    name, pin_world, pin_city = WORLDS[helper]
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    assert sha256(text) == pin_world
    journal = load_world_file(EXAMPLES / name)
    assert dumps_world(world_document(journal)) == text
    assert sha256(lay.render(journal.state.city())) == pin_city


@pytest.mark.parametrize("helper", list(WORLDS))
def test_each_world_file_satisfies_the_schema(helper):
    name, _, _ = WORLDS[helper]
    assert faults(json.loads((EXAMPLES / name).read_text(encoding="utf-8")), SCHEMA) == []


@pytest.mark.parametrize("helper", list(WORLDS))
def test_the_command_world_fold_writes_the_pinned_city_from_each_file(helper, tmp_path, capsys):
    name, _, pin_city = WORLDS[helper]
    store = tmp_path / "w.sqlite"
    assert cli.main(["world", "import", str(EXAMPLES / name), "--world", str(store)]) == 0
    city = tmp_path / "city.json"
    assert cli.main(["world", "fold", "--out", str(city), "--world", str(store)]) == 0
    capsys.readouterr()
    assert sha256(city.read_text(encoding="utf-8")) == pin_city
    export = tmp_path / "again.world.json"
    assert cli.main(["world", "export", str(export), "--world", str(store)]) == 0
    assert export.read_bytes() == (EXAMPLES / name).read_bytes()  # the store keeps the file as it is


def test_the_index_names_each_file_with_the_numbers_of_the_pins_and_what_is_in_it():
    index = json.loads((EXAMPLES / "worlds.json").read_text(encoding="utf-8"))
    assert list(index) == ["about", "worlds"] and "docs/world.md" in index["about"] and "tests/test_world_examples.py" in index["about"]
    assert [(row["helper"], row["file"], row["world_sha256"], row["city_sha256"]) for row in index["worlds"]] == [
        (helper, name, pin_world, pin_city) for helper, (name, pin_world, pin_city) in WORLDS.items()]
    for row in index["worlds"]:
        assert list(row) == ["file", "helper", "what", "events", "world_sha256", "city_sha256"] and row["what"]
        assert row["events"] == len(json.loads((EXAMPLES / row["file"]).read_text(encoding="utf-8"))["events"])


def test_the_script_writes_the_same_bytes_to_any_directory_and_says_what_it_wrote(script, tmp_path, capsys):
    where = tmp_path / "new" / "worlds"  # (the directory is made)
    assert script.main(["--out", str(where)]) == 0
    said = capsys.readouterr().err
    for name in FILES:
        assert (where / name).read_bytes() == (EXAMPLES / name).read_bytes() and f"wrote {where / name}: " in said


def test_the_files_are_named_where_a_port_looks_for_them():
    card = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    page = (ROOT / "docs" / "world.md").read_text(encoding="utf-8")
    for name in FILES + ["make_worlds.py"]:
        assert name in card, name
    section = page.split("## For a port")[1].split("## Limits")[0]
    assert "examples/worlds.json" in section and all(f"examples/{n}" in section for n in FILES if n != "worlds.json")
