"""The command line (bibliopolis.cli): what it writes, what it refuses and what it reports; and that the same input gives the same bytes."""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from hand_support import play
from support import T, art, make_tree, stamp

import bibliopolis
from bibliopolis import cli, picture
from bibliopolis.journal import dumps_world, world_document
from bibliopolis.store import Store

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
    assert err.strip() == (f"wrote {out}: {s['houses']} houses on {s['roads']} roads, {s['ring']} on the ring road, "
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


@pytest.mark.parametrize("mode", ["grow", "mirror"])
@pytest.mark.parametrize("huge", [str(10**400), "10001"])
def test_a_maximum_beyond_the_range_of_the_rule_is_a_refusal_with_a_message_and_not_a_traceback(files, tmp_path, capsys, mode, huge):
    t, lib, *_ = files
    out = tmp_path / "c.json"
    code, err = run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--mode", mode, "--out", str(out), "--max-houses", huge, "--min-houses", "4")
    assert code == 2 and err.startswith("bibliopolis: ") and "1 <= min <= max <= 10000" in err and "Traceback" not in err and not out.exists()


def test_a_world_with_a_maximum_beyond_the_range_of_the_rule_is_refused_by_the_same_range(tmp_path, capsys):
    for huge in (str(10**400), "10001"):
        code, err = run_main(capsys, "world", "new", "--world", str(tmp_path / "w.db"), "--max-houses", huge)
        assert code == 2 and "must be a whole number from 1 to 10000" in err and not (tmp_path / "w.db").exists()


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


def run_module(*args, hashseed="0", timeout=None):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "bibliopolis", *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=timeout)


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


def test_the_temporary_file_of_an_output_is_never_an_input_that_is_called_what_it_used_to_be(files, tmp_path, capsys):
    """`build` and `picture` put their output in place through a file of their own. It used to be called `.<output>.<pid>.part`, and a library or a city with that name was opened for
    writing, which empties it, and then renamed away."""
    t, lib, *_ = files
    library = tmp_path / f".city.json.{os.getpid()}.part"
    shutil.copy(lib, library)
    out = tmp_path / "city.json"
    assert run_main(capsys, "build", "--library", str(library), "--tree", str(t), "--out", str(out))[0] == 0
    assert library.read_bytes() == lib.read_bytes() and json.loads(out.read_text(encoding="utf-8"))["world"]["houses"] == 58
    city = tmp_path / f".city.svg.{os.getpid()}.part"
    shutil.copy(out, city)
    assert run_main(capsys, "picture", "--city", str(city), "--out", str(tmp_path / "city.svg"))[0] == 0
    assert city.read_bytes() == out.read_bytes() and (tmp_path / "city.svg").read_text(encoding="utf-8").startswith("<svg ")
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([library.name, city.name, "city.json", "city.svg", "library.json", "tree.json"])


def test_an_output_that_is_there_is_still_replaced_by_build_and_picture(files, tmp_path, capsys):
    """The scope of the commands that never replace a file is `world export` and `world fold`: a city or a picture is made again whenever it is wanted."""
    t, lib, *_ = files
    out = tmp_path / "city.json"
    out.write_text("an old city", encoding="utf-8")
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0
    first = out.read_bytes()
    assert first != b"an old city" and run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0 and out.read_bytes() == first
    svg = tmp_path / "city.svg"
    svg.write_text("an old picture", encoding="utf-8")
    assert run_main(capsys, "picture", "--city", str(out), "--out", str(svg))[0] == 0 and svg.read_text(encoding="utf-8").startswith("<svg ")


def test_build_and_picture_sync_their_file_before_the_rename_and_the_folder_after_it(files, tmp_path, capsys, monkeypatch):
    t, lib, *_ = files
    seen, real_fsync, real_replace = [], os.fsync, os.replace

    def fsync(fd):
        seen.append("sync folder" if stat.S_ISDIR(os.fstat(fd).st_mode) else "sync file")
        return real_fsync(fd)

    def replace(src, dst):
        seen.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    out = tmp_path / "city.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0
    assert seen == ["sync file", "replace", "sync folder"]
    seen.clear()
    assert run_main(capsys, "picture", "--city", str(out), "--out", str(tmp_path / "city.svg"))[0] == 0
    assert seen == ["sync file", "replace", "sync folder"]


def test_build_and_picture_need_no_hard_links(files, tmp_path, capsys, monkeypatch):
    """They put their output in place with a rename, not a link: a disk with no hard links is no reason to refuse them."""
    t, lib, *_ = files

    def no_links(*args, **kw):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    out = tmp_path / "city.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(out))[0] == 0
    assert run_main(capsys, "picture", "--city", str(out), "--out", str(tmp_path / "city.svg"))[0] == 0


# ----------------------------------------------------------------------------------- what build and picture replace ----
def the_files_that_must_not_be_replaced(tmp_path):
    """name -> (the file, the words of the refusal): a world (SQLite), a world file (JSON), and the world file with a byte order mark and white space in front of it."""
    journal = play(3, steps=40)
    Store.import_journal(tmp_path / "world.sqlite", journal)
    text = dumps_world(world_document(journal))
    (tmp_path / "world.json").write_text(text, encoding="utf-8")
    (tmp_path / "bom.json").write_text("\ufeff\n  " + text, encoding="utf-8")
    return {"a world": (tmp_path / "world.sqlite", "is a SQLite database already"), "a world file": (tmp_path / "world.json", "is a world file"),
            "a world file that begins with a byte order mark": (tmp_path / "bom.json", "is a world file")}


def commands_of(files, tmp_path, capsys):
    """The two commands that replace their output, each as a function of the output: build reads the library and the tree, picture the city."""
    t, lib, *_ = files
    city = tmp_path / "the-city.json"
    assert run_main(capsys, "build", "--library", str(lib), "--tree", str(t), "--out", str(city))[0] == 0
    return {"build": (lambda out: ("build", "--library", str(lib), "--tree", str(t), "--out", str(out)), [lib, t]),
            "picture": (lambda out: ("picture", "--city", str(city), "--out", str(out)), [city])}


@pytest.mark.parametrize("command", ["build", "picture"])
def test_build_and_picture_never_replace_a_world_or_a_world_file(command, files, tmp_path, capsys):
    """They replace their own output (a city, a picture), which is made again whenever it is wanted; a world, as a SQLite file or as a world file, is never theirs to replace."""
    argv, _ = commands_of(files, tmp_path, capsys)[command]
    for what, (out, words) in the_files_that_must_not_be_replaced(tmp_path).items():
        before = out.read_bytes()
        code, err = run_main(capsys, *argv(out))
        assert code == 2 and err.startswith("bibliopolis: ") and str(out) in err and words in err, (what, err)
        assert out.read_bytes() == before and not [p for p in tmp_path.iterdir() if p.name.endswith(".part")], what


@pytest.mark.parametrize("command", ["build", "picture"])
def test_build_and_picture_never_replace_what_they_read_whatever_the_name_of_it(command, files, tmp_path, capsys):
    argv, reads = commands_of(files, tmp_path, capsys)[command]
    for read in reads:
        before = read.read_bytes()
        names = {"the name itself": read, "another spelling": read.parent / "." / read.name, "a path from where the command runs": Path(os.path.relpath(read))}
        try:
            (tmp_path / f"link-to-{read.name}").symlink_to(read)
            os.link(read, tmp_path / f"hard-link-to-{read.name}")
            names["a link"], names["a hard link"] = tmp_path / f"link-to-{read.name}", tmp_path / f"hard-link-to-{read.name}"
        except OSError:
            pass
        for what, out in names.items():
            code, err = run_main(capsys, *argv(out))
            assert code == 2 and "is read to make it" in err and err.startswith("bibliopolis: "), (what, err)
            assert read.read_bytes() == before, what


@pytest.mark.parametrize("command", ["build", "picture"])
def test_build_and_picture_still_replace_a_json_file_that_is_not_a_world_and_any_other_output(command, files, tmp_path, capsys):
    """The controls: a city, a picture, a JSON object of another kind, an object whose format is another, text, a list, a file of nothing: all are theirs to replace."""
    argv, _ = commands_of(files, tmp_path, capsys)[command]
    others = {"a city": '{"schema_version": 4, "layout_version": "v4"}', "another format": '{"format": "something.else", "version": 1}', "text": "an old file", "a list": "[1, 2]",
              "nothing": "", "a broken object": '{"format": "bibliopolis.world", '}
    for what, text in others.items():
        out = tmp_path / "out.txt"
        out.write_text(text, encoding="utf-8")
        code, err = run_main(capsys, *argv(out))
        assert code == 0 and out.read_text(encoding="utf-8") != text, (what, err)


def test_build_and_picture_do_not_wait_for_a_named_pipe_that_has_the_name(files, tmp_path, capsys):
    """The look at the output opens it without blocking: a named pipe on the name is not read (and is replaced as any file is)."""
    import signal

    if not hasattr(os, "mkfifo") or not hasattr(signal, "alarm"):
        pytest.skip("this system has no named pipes or no alarm")
    commands = commands_of(files, tmp_path, capsys)
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError("the command waited for the named pipe")))
    for command, (argv, _) in commands.items():
        pipe = tmp_path / f"{command}.pipe"
        os.mkfifo(pipe)
        signal.alarm(20)
        try:
            code, err = run_main(capsys, *argv(pipe))
        finally:
            signal.alarm(0)
        assert code == 0, (command, err)


@pytest.mark.parametrize("command", ["build", "picture"])
def test_the_program_as_run_refuses_the_same_way(command, files, tmp_path, capsys):
    argv, _ = commands_of(files, tmp_path, capsys)[command]
    out, words = the_files_that_must_not_be_replaced(tmp_path)["a world"]
    before = out.read_bytes()
    done = run_module(*argv(out))
    assert done.returncode == 2 and done.stderr.startswith("bibliopolis: ") and words in done.stderr and "Traceback" not in done.stderr
    assert out.read_bytes() == before


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
    assert shown.out == "" and shown.err.strip() == "the chronicle is empty: it has no split and no over entry"  # it says nothing about roads:
    assert bibliopolis.summary(json.loads(mirror.read_text(encoding="utf-8")))["roads"] > 0  # this city has some, and no crowded one
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


# ------------------------------------------------------------------------------------ a city file that is wrong ----
def own_parent(doc):
    street = next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("shape") != "ring")
    doc["places"][street]["parent"] = street  # `picture` once looped for ever on this


def each_others_parent(doc):
    above = doc["composition"]["ring1"][0]["place"]
    below = next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("parent") == above)
    doc["places"][above]["parent"] = below


def lane_of_no_radius(doc):
    street = next(pid for pid, p in doc["places"].items() if p["kind"] == "street" and p.get("rib") and p["rib"].get("band") is not None)
    doc["places"][street]["rib"]["s"] = 0  # a division by zero


WRONG_CITIES = [
    ("a chronicle entry that is neither a split nor an over", lambda d: d["world"].update(chronicle=[{"seq": 1}]), "must be a split"),
    ("an empty measure", lambda d: d["composition"].update(measure={}), "measure: max_radius is missing"),
    ("a plaza with no position", lambda d: d["places"]["place:plaza"].pop("position"), "position is missing"),
    ("a plaza position with no x", lambda d: d["places"]["place:plaza"].update(position={"z": 0}), "position: must be {x, z}"),
    ("a street that is its own parent", own_parent, "the parents lead round in a circle"),
    ("two streets that are each other's parent", each_others_parent, "the parents lead round in a circle"),
    ("a house on a street that is not there", lambda d: next(p for p in d["places"].values() if p["kind"] == "lot").update(parent="place:nowhere"), "is not a street"),
    ("a lane of radius 0", lane_of_no_radius, "must be a number of at least 1"),
    ("a coast that is null", lambda d: d.update(coast=None), "coast: must be an object"),
    ("an integer too large for a float", lambda d: d["composition"]["measure"].update(walk_mean=10**400), "measure.walk_mean: must be a number"),
    ("a number that is infinity", lambda d: d["composition"]["measure"].update(max_radius=float("inf")), "measure.max_radius: must be a number, got inf"),
    ("an arrival that is an integer of 401 digits", lambda d: d["world"]["chronicle"][0].update(seq=10**400), "chronicle[0].seq: must be a whole number"),
    ("a count that is text", lambda d: d["world"]["chronicle"][0].update(count_before="41"), "count_before: must be a whole number"),
    ("a street with an empty address", lambda d: next(p for p in d["places"].values() if p["kind"] == "street").update(address=[]), "address: must be a list of names"),
    ("a street with no shape", lambda d: next(p for p in d["places"].values() if p["kind"] == "street").pop("shape"), "shape is missing"),
    ("a rule with no max", lambda d: d["world"].update(districts={"min": 10}), "whole numbers max and min"),
    ("a road with a point that is a word", lambda d: next(iter(d["roads"].values())).update(points=[[0, 0], [1, "x"]]), "points: must be a list of at least two"),
]


@pytest.mark.parametrize("command", ["picture", "chronicle"])
@pytest.mark.parametrize("what, wrong, names", WRONG_CITIES, ids=[w[0] for w in WRONG_CITIES])
def test_a_city_file_that_is_wrong_is_refused_by_both_commands_with_the_place_and_never_hangs(city_file, tmp_path, command, what, wrong, names):
    doc = json.loads(city_file.read_text(encoding="utf-8"))
    wrong(doc)
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "out.svg"
    args = ["--city", str(path), "--out", str(out)] if command == "picture" else ["--city", str(path)]
    done = run_module(command, *args, timeout=30)  # a loop would be a TimeoutExpired here
    assert done.returncode == 2, done.stderr
    assert done.stderr.startswith("bibliopolis: city") and names in done.stderr and "Traceback" not in done.stderr and done.stdout == ""
    assert not out.exists()


@pytest.mark.parametrize("command", ["picture", "chronicle"])
def test_a_city_file_nested_too_deeply_to_read_is_refused_by_both_commands(tmp_path, command):
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    args = ["--city", str(deep), "--out", str(tmp_path / "out.svg")] if command == "picture" else ["--city", str(deep)]
    done = run_module(command, *args, timeout=60)
    assert done.returncode == 2 and "nested too deeply to read" in done.stderr and "Traceback" not in done.stderr
