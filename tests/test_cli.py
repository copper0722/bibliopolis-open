"""The command line (bibliopolis.cli): what it writes, what it refuses and what it reports; and that the same input gives the same bytes."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from support import T, art, make_tree, stamp

import bibliopolis
from bibliopolis import cli, picture

ROOT = Path(__file__).resolve().parents[1]
SPEC = {"med": T(0, a=T(25), b=T(16)), "pub": T(14), "x": T(3)}


@pytest.fixture
def files(tmp_path):
    tree, items = make_tree(SPEC)
    t, lib = tmp_path / "tree.json", tmp_path / "library.json"
    t.write_text(json.dumps(tree), encoding="utf-8")
    lib.write_text(json.dumps({"items": items}), encoding="utf-8")
    return t, lib, tree, {"items": items}


def run_main(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().err


def test_build_writes_the_city_and_reports_what_it_made(files, tmp_path, capsys):
    t, lib, tree, library = files
    out = tmp_path / "out" / "city.json"  # (the directory is made)
    code, err = run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--mode", "grow", "--out", str(out))
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["layout_version"] == "v4" and doc["world"]["mode"] == "grow" and doc["world"]["houses"] == len(library["items"])
    s = bibliopolis.summary(doc)
    assert err.strip() == (f"wrote {out}: {s['houses']} houses on {s['roads']} roads, {s['underground']} under the town hall, "
                           f"{s['splits']} splits, {s['over']} over (mode grow)")
    assert s["houses"] == 58 and s["splits"] >= 2 and s["roads"] >= 2
    assert out.read_text(encoding="utf-8") == bibliopolis.render(bibliopolis.build_city(library, tree, mode="grow"))
    assert [p.name for p in out.parent.iterdir()] == ["city.json"]  # no temporary file is left


def test_the_mode_defaults_to_grow_and_mirror_is_chosen_by_name(files, tmp_path, capsys):
    t, lib, tree, library = files
    default, mirror = tmp_path / "default.json", tmp_path / "mirror.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(default))[0] == 0
    code, err = run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--mode", "mirror", "--out", str(mirror))
    assert code == 0 and "(mode mirror)" in err and "0 splits" in err
    assert json.loads(default.read_text(encoding="utf-8"))["world"]["mode"] == "grow"
    assert json.loads(mirror.read_text(encoding="utf-8"))["world"]["mode"] == "mirror"


def test_the_rule_can_be_changed_and_is_kept_in_the_document(files, tmp_path, capsys):
    t, lib, *_ = files
    out = tmp_path / "city.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out), "--max-houses", "12", "--min-houses", "4")[0] == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["world"]["districts"] == {"max": 12, "min": 4, "extract": "largest", "count": "direct"}


def test_a_wrong_document_is_refused_with_the_place_and_nothing_is_written(files, tmp_path, capsys):
    t, lib, tree, library = files
    broken = dict(library, items=[*library["items"], art(900, ["nowhere"])])
    lib2 = tmp_path / "broken.json"
    lib2.write_text(json.dumps(broken), encoding="utf-8")
    out = tmp_path / "city.json"
    code, err = run_main(capsys, "build", "--library", str(lib2), "--tree", str(t), "--out", str(out))
    assert code == 2 and "library.items[58]" in err and "'nowhere' is not the id of a node of the tree" in err and err.startswith("bibliopolis: ")
    assert not out.exists()


def test_a_rule_that_cannot_be_is_refused(files, tmp_path, capsys):
    t, lib, *_ = files
    code, err = run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(tmp_path / "c.json"), "--max-houses", "5", "--min-houses", "9")
    assert code == 2 and "1 <= min <= max" in err and not (tmp_path / "c.json").exists()


def test_a_missing_or_unwritable_file_is_an_error_and_leaves_no_temporary_file(files, tmp_path, capsys):
    t, lib, *_ = files
    code, err = run_main(capsys, "build", "--library", str(tmp_path / "missing.json"), "--tree", str(t), "--out", str(tmp_path / "c.json"))
    assert code == 1 and "missing.json" in err
    target = tmp_path / "taken"
    target.mkdir()  # the output path is a directory: the file cannot replace it
    before = sorted(p.name for p in tmp_path.iterdir())
    code, err = run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(target))
    assert code == 1 and err.startswith("bibliopolis: ")
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_an_option_the_command_does_not_know_stops_the_parser(files, tmp_path):
    t, lib, *_ = files
    with pytest.raises(SystemExit) as stop:
        cli.main(["build", "--library", str(lib), "--tree", str(t), "--mode", "both", "--out", str(tmp_path / "c.json")])
    assert stop.value.code == 2
    with pytest.raises(SystemExit) as stop:
        cli.main([])
    assert stop.value.code == 2


def run_module(*args, hashseed="0"):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "bibliopolis", *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def test_the_module_runs_as_a_program_and_prints_its_version():
    done = run_module("--version")
    assert done.returncode == 0 and done.stdout.strip() == f"bibliopolis {bibliopolis.__version__}"
    assert run_module("build").returncode == 2  # the required options are missing


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_the_same_input_gives_the_same_bytes_whatever_the_hash_seed_and_the_process(files, tmp_path, mode):
    t, lib, tree, library = files
    outs = []
    for seed in ("0", "1", "4242"):
        out = tmp_path / f"{mode}-{seed}.json"
        done = run_module("build", "--library", str(lib), "--tree", str(t), "--mode", mode, "--out", str(out), hashseed=seed)
        assert done.returncode == 0, done.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1] == outs[2]
    assert outs[0] == bibliopolis.render(bibliopolis.build_city(library, tree, mode=mode)).encode("utf-8")  # ... and the same as in this process
    assert b"\r" not in outs[0] and outs[0].endswith(b"\n")


def test_the_order_of_the_items_in_the_file_does_not_matter_only_added_at_and_the_id(files, tmp_path):
    t, lib, tree, library = files
    shuffled = {"items": list(reversed(library["items"]))}
    assert bibliopolis.render(bibliopolis.build_city(shuffled, tree)) == bibliopolis.render(bibliopolis.build_city(library, tree))
    same_day = {"items": [{**a, "added_at": "2024-05-05"} for a in library["items"]]}  # every item on one day: the arrival order is the id order
    a = bibliopolis.render(bibliopolis.build_city(same_day, tree))
    b = bibliopolis.render(bibliopolis.build_city({"items": list(reversed(same_day["items"]))}, tree))
    assert a == b
    assert stamp(1) < stamp(2)


def test_the_city_file_has_the_permissions_of_any_file_the_user_makes(files, tmp_path, capsys):
    t, lib, *_ = files
    out = tmp_path / "city.json"
    plain = tmp_path / "plain.txt"
    plain.write_text("x", encoding="utf-8")
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0
    assert stat.S_IMODE(out.stat().st_mode) == stat.S_IMODE(plain.stat().st_mode)  # (a temporary file would be 0600)


# ------------------------------------------------------------------------------------- picture and chronicle ----
@pytest.fixture
def city_file(files, tmp_path, capsys):
    t, lib, *_ = files
    out = tmp_path / "built" / "city.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0
    return out


def test_picture_draws_the_city_and_says_how_big_the_file_is(city_file, tmp_path, capsys):
    out = tmp_path / "pictures" / "city.svg"  # (the directory is made)
    code, err = run_main(capsys, "picture", "--city", str(city_file), "--out", str(out))
    doc = json.loads(city_file.read_text(encoding="utf-8"))
    text = out.read_text(encoding="utf-8")
    assert code == 0 and text == picture.render(doc) and picture.TITLE in text
    assert err.strip() == f"wrote {out}: {len(text.encode('utf-8'))} bytes"
    assert [p.name for p in out.parent.iterdir()] == ["city.svg"]  # no temporary file is left


def test_picture_takes_a_title_and_a_size(city_file, tmp_path, capsys):
    out = tmp_path / "titled.svg"
    assert run_main(capsys, "picture", "--city", str(city_file), "--out", str(out), "--title", "A <small> town", "--size", "600")[0] == 0
    doc = json.loads(city_file.read_text(encoding="utf-8"))
    text = out.read_text(encoding="utf-8")
    assert text == picture.render(doc, "A <small> town", size=600) and "A &lt;small&gt; town" in text
    assert text != picture.render(doc, "A <small> town")


def test_picture_refuses_what_is_not_a_city_a_size_that_is_no_picture_and_a_missing_file(files, city_file, tmp_path, capsys):
    t, lib, *_ = files
    out = tmp_path / "x.svg"
    for wrong in (lib, t):  # the usual mistake: a library or a tree instead of the city
        code, err = run_main(capsys, "picture", "--city", str(wrong), "--out", str(out))
        assert code == 2 and "not a city document" in err and "layout v4" in err and err.startswith("bibliopolis: ") and "Traceback" not in err
    broken = json.loads(city_file.read_text(encoding="utf-8"))
    del broken["roads"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    code, err = run_main(capsys, "picture", "--city", str(path), "--out", str(out))
    assert code == 2 and "city.roads: must be an object" in err
    code, err = run_main(capsys, "picture", "--city", str(city_file), "--out", str(out), "--size", "50")
    assert code == 2 and "--size must be at least 100" in err
    code, err = run_main(capsys, "picture", "--city", str(tmp_path / "missing.json"), "--out", str(out))
    assert code == 1 and "missing.json" in err
    assert not out.exists()


def test_chronicle_prints_one_sentence_per_entry_on_standard_output(city_file, capsys):
    doc = json.loads(city_file.read_text(encoding="utf-8"))
    assert cli.main(["chronicle", "--city", str(city_file)]) == 0
    shown = capsys.readouterr()
    assert shown.err == "" and shown.out.splitlines() == bibliopolis.city.chronicle_lines(doc)
    assert len(shown.out.splitlines()) == len(doc["world"]["chronicle"]) >= 2
    assert cli.main(["chronicle", "--city", str(city_file), "--limit", "1"]) == 0
    assert capsys.readouterr().out.splitlines() == bibliopolis.city.chronicle_lines(doc, 1)


def test_chronicle_says_so_when_it_is_empty_and_refuses_what_it_cannot_read(files, city_file, tmp_path, capsys):
    t, lib, *_ = files
    mirror = tmp_path / "mirror.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--mode", "mirror", "--out", str(mirror))[0] == 0
    assert cli.main(["chronicle", "--city", str(mirror)]) == 0
    shown = capsys.readouterr()
    assert shown.out == "" and "the chronicle is empty" in shown.err
    code, err = run_main(capsys, "chronicle", "--city", str(lib))
    assert code == 2 and "not a city document" in err
    code, err = run_main(capsys, "chronicle", "--city", str(city_file), "--limit", "0")
    assert code == 2 and "--limit must be at least 1" in err
    assert run_main(capsys, "chronicle", "--city", str(tmp_path / "missing.json"))[0] == 1


@pytest.mark.parametrize("command", ["picture", "chronicle"])
def test_picture_and_chronicle_give_the_same_bytes_whatever_the_hash_seed(city_file, tmp_path, command):
    outs = []
    for seed in ("0", "1", "4242"):
        args = ["--city", str(city_file), "--out", str(tmp_path / f"{seed}.svg")] if command == "picture" else ["--city", str(city_file)]
        done = run_module(command, *args, hashseed=seed)
        assert done.returncode == 0, done.stderr
        outs.append((tmp_path / f"{seed}.svg").read_bytes() if command == "picture" else done.stdout.encode("utf-8"))
    assert outs[0] == outs[1] == outs[2] and outs[0].endswith(b"\n") and b"\r" not in outs[0]
