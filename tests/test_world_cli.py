"""The command `world` (bibliopolis.cli): new, import, export and fold, on a store in the home folder or in a file of the caller, and the chain from the log to the picture."""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from hand_support import hid, play, scripted_merge, stamp

from bibliopolis import cli, store
from bibliopolis import layout as lay
from bibliopolis.city import chronicle_lines
from bibliopolis.inputs import read_city
from bibliopolis.journal import Journal, dumps_world, world_document
from bibliopolis.store import Store

ROOT = Path(__file__).resolve().parents[1]


def run_main(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.err, captured.out


def run_module(*args, hashseed="0"):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "bibliopolis", *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def home_folder():
    return Path(os.environ["BIBLIOPOLIS_HOME"])


def world_file(tmp_path, journal=None, name="w.json"):
    journal = journal or play(3, steps=90)
    path = tmp_path / name
    path.write_text(dumps_world(world_document(journal)), encoding="utf-8")
    return path, journal


# -------------------------------------------------------------------------------------------------- new ----
def test_new_makes_an_empty_world_in_the_home_folder_made_on_first_use_and_says_where(capsys):
    folder = home_folder()
    assert not folder.exists()
    code, err, _ = run_main(capsys, "world", "new")
    assert code == 0 and (folder / "world.sqlite").is_file()
    lines = err.splitlines()
    assert lines[0] == f"home: {folder} (made now)"
    assert lines[1] == f"made {folder / 'world.sqlite'}: a world with no house yet (at most 40, at least 10, auto off)" and len(lines) == 2
    j = Store(folder / "world.sqlite").journal()
    assert j.events == [] and j.rule == {"max": 40, "min": 10, "auto": False}


def test_new_never_overwrites_a_world_and_the_second_time_the_home_folder_is_not_made_now(capsys):
    run_main(capsys, "world", "new", "--max-houses", "25")
    path = home_folder() / "world.sqlite"
    before = path.read_bytes()
    code, err, _ = run_main(capsys, "world", "new", "--max-houses", "30")
    assert code == 2 and err.splitlines()[0] == f"home: {home_folder()}" and "is there already; a world is not overwritten" in err
    assert path.read_bytes() == before and Store(path).journal().rule["max"] == 25


def test_a_world_of_a_file_of_the_callers_does_not_touch_the_home_folder(tmp_path, capsys):
    code, err, _ = run_main(capsys, "world", "new", "--world", str(tmp_path / "mine" / "city.sqlite"))
    assert code == 0 and (tmp_path / "mine" / "city.sqlite").is_file() and "home:" not in err
    assert not home_folder().exists()


def test_new_takes_the_rule_and_a_rule_that_cannot_be_leaves_no_file(tmp_path, capsys):
    path = tmp_path / "w.sqlite"
    code, err, _ = run_main(capsys, "world", "new", "--world", str(path), "--max-houses", "12", "--min-houses", "4", "--auto")
    assert code == 0 and err.strip() == f"made {path}: a world with no house yet (at most 12, at least 4, auto on)"
    assert Store(path).journal().rule == {"max": 12, "min": 4, "auto": True}
    other = tmp_path / "bad.sqlite"
    code, err, _ = run_main(capsys, "world", "new", "--world", str(other), "--min-houses", "50")
    assert code == 2 and "min (50) is more than max (40)" in err and not other.exists()


# -------------------------------------------------------------------------------------- import and export ----
def test_import_reads_a_world_file_and_export_writes_the_same_bytes_back(tmp_path, capsys):
    source, journal = world_file(tmp_path)
    code, err, _ = run_main(capsys, "world", "import", str(source))
    houses = len(journal.state.items)
    assert code == 0 and err.splitlines()[-1] == f"read {source} into {home_folder() / 'world.sqlite'}: {len(journal.events)} events, {houses} houses"
    out = tmp_path / "out" / "back.json"
    code, err, _ = run_main(capsys, "world", "export", str(out))
    assert code == 0 and err.splitlines()[-1] == f"wrote {out}: {len(journal.events)} events, {len(journal.items())} items"
    assert out.read_bytes() == source.read_bytes()  # JSON -> SQLite -> JSON
    assert [p.name for p in out.parent.iterdir()] == ["back.json"]  # no temporary file is left


def test_import_does_not_overwrite_a_world_and_a_file_that_is_not_a_world_leaves_nothing_behind(tmp_path, capsys):
    source, _ = world_file(tmp_path)
    run_main(capsys, "world", "import", str(source), "--world", str(tmp_path / "a.sqlite"))
    before = (tmp_path / "a.sqlite").read_bytes()
    code, err, _ = run_main(capsys, "world", "import", str(source), "--world", str(tmp_path / "a.sqlite"))
    assert code == 2 and "is there already" in err and (tmp_path / "a.sqlite").read_bytes() == before
    for name, text, message in (("bad.json", "{not json", "not valid JSON"), ("other.json", json.dumps({"items": []}), "not a world file"),
                                ("wrong.json", dumps_world(world_document(Journal())).replace("bibliopolis.world", "other"), "world.format")):
        bad = tmp_path / name
        bad.write_text(text, encoding="utf-8")
        target = tmp_path / f"{name}.sqlite"
        code, err, _ = run_main(capsys, "world", "import", str(bad), "--world", str(target))
        assert code == 2 and message in err and not target.exists(), name
    doc = json.loads(source.read_text(encoding="utf-8"))
    doc["events"][-1]["payload"] = {"house": "nobody", "road": "nowhere"}
    doc["events"][-1]["kind"] = "file"
    (tmp_path / "refused.json").write_text(json.dumps(doc), encoding="utf-8")
    code, err, _ = run_main(capsys, "world", "import", str(tmp_path / "refused.json"), "--world", str(tmp_path / "r.sqlite"))
    assert code == 2 and f"world.events[{len(doc['events']) - 1}] (file)" in err and not (tmp_path / "r.sqlite").exists()
    code, err, _ = run_main(capsys, "world", "import", str(tmp_path / "missing.json"), "--world", str(tmp_path / "m.sqlite"))
    assert code == 1 and "missing.json" in err and not (tmp_path / "m.sqlite").exists()


def test_export_and_fold_of_a_world_that_is_not_there_say_so(tmp_path, capsys):
    for argv in (("export", str(tmp_path / "o.json")), ("fold", "--out", str(tmp_path / "c.json"))):
        code, err, _ = run_main(capsys, "world", *argv, "--world", str(tmp_path / "none.sqlite"))
        assert code == 2 and "there is no world here" in err
    text = tmp_path / "text.sqlite"
    text.write_text("not a database", encoding="utf-8")
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(tmp_path / "c.json"), "--world", str(text))
    assert code == 2 and "not a world of this program" in err and not (tmp_path / "c.json").exists()


# ---------------------------------------------------------------------------------------------------- fold ----
def test_fold_writes_the_city_as_build_does_and_the_picture_and_the_chronicle_read_it(tmp_path, capsys):
    source, journal = world_file(tmp_path)
    run_main(capsys, "world", "import", str(source), "--world", str(tmp_path / "w.sqlite"))
    city_file = tmp_path / "city.json"
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(city_file), "--world", str(tmp_path / "w.sqlite"))
    city = journal.state.city()
    assert code == 0 and city_file.read_text(encoding="utf-8") == lay.render(city)
    s = {"houses": city["world"]["houses"], "roads": city["composition"]["streets"]["total"], "under": city["composition"]["measure"]["underground_lots"]}
    splits = sum(1 for e in city["world"]["chronicle"] if "from" in e)
    assert err.strip() == f"wrote {city_file}: {s['houses']} houses on {s['roads']} roads, {s['under']} under the town hall, {splits} splits, 0 over (mode hand)"
    svg = tmp_path / "city.svg"
    assert run_main(capsys, "picture", "--city", str(city_file), "--out", str(svg))[0] == 0
    assert ET.fromstring(svg.read_text(encoding="utf-8")).tag.endswith("svg")
    code, _, out = run_main(capsys, "chronicle", "--city", str(city_file))
    assert code == 0 and out.splitlines() == chronicle_lines(read_city(json.loads(city_file.read_text(encoding="utf-8")))) and len(out.splitlines()) >= 10


def test_a_world_with_merged_avenues_goes_through_import_fold_the_picture_and_the_chronicle(tmp_path, capsys):
    source, journal = world_file(tmp_path, scripted_merge().journal)
    run_main(capsys, "world", "import", str(source), "--world", str(tmp_path / "w.sqlite"))
    city_file = tmp_path / "city.json"
    assert run_main(capsys, "world", "fold", "--out", str(city_file), "--world", str(tmp_path / "w.sqlite"))[0] == 0
    assert city_file.read_text(encoding="utf-8") == lay.render(journal.state.city())
    svg = tmp_path / "city.svg"
    assert run_main(capsys, "picture", "--city", str(city_file), "--out", str(svg))[0] == 0 and ET.fromstring(svg.read_text(encoding="utf-8")).tag.endswith("svg")
    code, _, out = run_main(capsys, "chronicle", "--city", str(city_file))
    merged = [line for line in out.splitlines() if "are merged below the new avenue" in line]
    assert code == 0 and len(merged) == 2
    assert merged[0].endswith("3 avenues (Field 1.1, Field 1.2, Field 1.3) are merged below the new avenue Domain 1, which takes the direction of Field 1.3; 21 houses are put again.")


def test_fold_of_an_empty_world_is_the_town_hall_alone(tmp_path, capsys):
    run_main(capsys, "world", "new", "--world", str(tmp_path / "w.sqlite"))
    out = tmp_path / "city.json"
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(out), "--world", str(tmp_path / "w.sqlite"))
    assert code == 0 and err.strip() == f"wrote {out}: 0 houses on 0 roads, 0 under the town hall, 0 splits, 0 over (mode hand)"
    assert json.loads(out.read_text(encoding="utf-8"))["world"]["houses"] == 0


def test_the_events_a_store_took_one_by_one_fold_to_the_same_city_as_the_journal_that_made_them(tmp_path, capsys):
    path = tmp_path / "w.sqlite"
    Store.create(path, {"max": 20, "min": 5, "auto": False})
    j = Store(path).journal()
    for i in range(1, 15):
        Store(path).append(j.append("add_item", {"item": {"id": hid(i), "title": "", "authors": [], "year": None, "type": "article"}}, stamp(i)))
    Store(path).append(j.append("open_road", {"road": "a", "name": "A", "parent": None, "houses": [hid(i) for i in range(1, 8)]}, stamp(20)))
    out = tmp_path / "city.json"
    assert run_main(capsys, "world", "fold", "--out", str(out), "--world", str(path))[0] == 0
    assert out.read_text(encoding="utf-8") == lay.render(j.state.city())


def test_fold_into_a_place_that_cannot_be_written_is_an_error_and_not_a_traceback(tmp_path, capsys):
    run_main(capsys, "world", "new", "--world", str(tmp_path / "w.sqlite"))
    (tmp_path / "taken").mkdir()
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(tmp_path / "taken"), "--world", str(tmp_path / "w.sqlite"))
    assert code == 1 and err.startswith("bibliopolis: ")


# ---------------------------------------------------------------------------------------- as a program ----
def test_world_runs_as_a_program_with_the_home_folder_of_the_environment_and_the_same_bytes_whatever_the_hash_seed(tmp_path):
    source, journal = world_file(tmp_path, play(5, steps=100))
    done = run_module("world", "import", str(source))
    assert done.returncode == 0, done.stderr
    assert done.stderr.splitlines()[0] == f"home: {home_folder()} (made now)" and (home_folder() / "world.sqlite").is_file()
    texts = []
    for seed in ("0", "4242"):
        out = tmp_path / f"city-{seed}.json"
        done = run_module("world", "fold", "--out", str(out), hashseed=seed)
        assert done.returncode == 0, done.stderr
        texts.append(out.read_text(encoding="utf-8"))
    assert texts[0] == texts[1] == lay.render(journal.state.city())


def test_world_with_no_command_or_an_unknown_one_stops_the_parser():
    for argv in (["world"], ["world", "sweep"], ["world", "export"], ["world", "fold"], ["world", "new", "--max-houses", "x"]):
        with pytest.raises(SystemExit) as stop:
            cli.main(argv)
        assert stop.value.code == 2, argv


def test_the_home_folder_of_a_test_is_not_the_real_one_and_is_where_a_command_without_world_writes(capsys):
    run_main(capsys, "world", "new")
    assert (home_folder() / store.WORLD_NAME).is_file() and home_folder() != Path.home() / "Bibliopolis"


def test_the_help_of_the_command_names_the_home_folder_and_the_four_commands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["world", "--help"])
    out = capsys.readouterr().out
    assert all(word in out for word in ("new", "import", "export", "fold"))
    with pytest.raises(SystemExit):
        cli.main(["world", "new", "--help"])
    assert "$BIBLIOPOLIS_HOME" in " ".join(capsys.readouterr().out.split())
