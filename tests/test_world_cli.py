"""The command `world` (bibliopolis.cli): new, import, export and fold, on a store in the home folder or in a file of the caller, and the chain from the log to the picture."""

import errno
import json
import os
import sqlite3
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import closing
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
    assert lines[1] == f"made {folder / 'world.sqlite'}: a world with no house yet (at most 40, at least 10, 13 branches, auto off)" and len(lines) == 2
    j = Store(folder / "world.sqlite").journal()
    assert j.events == [] and j.rule == {"max": 40, "min": 10, "auto": False, "branches": 13}


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
    assert code == 0 and err.strip() == f"made {path}: a world with no house yet (at most 12, at least 4, 13 branches, auto on)"
    assert Store(path).journal().rule == {"max": 12, "min": 4, "auto": True, "branches": 13}
    other = tmp_path / "bad.sqlite"
    code, err, _ = run_main(capsys, "world", "new", "--world", str(other), "--min-houses", "50")
    assert code == 2 and "min (50) is more than max (40)" in err and not other.exists()
    third = tmp_path / "branches.sqlite"
    code, err, _ = run_main(capsys, "world", "new", "--world", str(third), "--branches", "21")
    assert code == 0 and Store(third).journal().rule["branches"] == 21 and "21 branches" in err
    code, err, _ = run_main(capsys, "world", "new", "--world", str(tmp_path / "one.sqlite"), "--branches", "1")
    assert code == 2 and "from 2 to 1000" in err and not (tmp_path / "one.sqlite").exists()


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


# ------------------------------------------------------------------------------------------ never over a world ----
WRITERS = {"export": lambda out, world: ("world", "export", str(out), "--world", str(world)),
           "fold": lambda out, world: ("world", "fold", "--out", str(out), "--world", str(world))}


def a_world(tmp_path, name="w.sqlite"):
    path = tmp_path / name
    Store.import_journal(path, play(3, steps=60))
    return path


def everything_in(folder):
    """name -> bytes of every file of the folder (a temporary file left behind shows), and the names that are links."""
    files = {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}
    return files, sorted(p.name for p in folder.iterdir() if p.is_symlink())


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_command_never_writes_over_the_world_it_reads(command, tmp_path, capsys):
    world = a_world(tmp_path)
    before = everything_in(tmp_path)
    code, err, _ = run_main(capsys, *WRITERS[command](world, world))
    assert code == 2 and "is the world that is being read" in err, err
    assert everything_in(tmp_path) == before  # the world is as it was, and no temporary file is left
    assert Store(world).journal().events


def other_names_of(tmp_path, world):
    """Other names for the file `world`, by how they come about; a link a system does not allow is left out."""
    names = {"another spelling": world.parent / "." / world.name, "a path from where the command runs": Path(os.path.relpath(world))}
    for what, make in (("a link to the folder", lambda: (tmp_path / "folder-link").symlink_to(tmp_path, target_is_directory=True)),
                       ("a link to the file", lambda: (tmp_path / "file-link.sqlite").symlink_to(world)),
                       ("a hard link", lambda: os.link(world, tmp_path / "hard.sqlite"))):
        try:
            make()
        except OSError:
            continue
        names[what] = {"a link to the folder": tmp_path / "folder-link" / world.name, "a link to the file": tmp_path / "file-link.sqlite", "a hard link": tmp_path / "hard.sqlite"}[what]
    assert len(names) >= 2
    return names


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_command_never_writes_over_the_world_under_another_name_either(command, tmp_path, capsys):
    world = a_world(tmp_path)
    names = other_names_of(tmp_path, world)
    before = everything_in(tmp_path)
    for what, name in names.items():
        code, err, _ = run_main(capsys, *WRITERS[command](name, world))
        assert code == 2 and "is the world that is being read" in err, (what, err)
        assert everything_in(tmp_path) == before, what  # no name was replaced by text, and no temporary file is left
        code, err, _ = run_main(capsys, *WRITERS[command](world, name))  # ... and the same when the world is the one with the other name
        assert code == 2 and "is the world that is being read" in err, (what, err)
        assert everything_in(tmp_path) == before, what


def a_sqlite_file_that_is_no_world(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE notes (text TEXT)")
    return path


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_command_never_writes_over_another_sqlite_file(command, tmp_path, capsys):
    world = a_world(tmp_path)
    others = [a_world(tmp_path, "other.sqlite"), a_sqlite_file_that_is_no_world(tmp_path / "notes.sqlite")]
    before = everything_in(tmp_path)
    for other in others:
        code, err, _ = run_main(capsys, *WRITERS[command](other, world))
        assert code == 2 and f"{other} is a SQLite database already" in err, err
        assert everything_in(tmp_path) == before


def expected_text(command, journal):
    return dumps_world(world_document(journal)) if command == "export" else lay.render(journal.state.city())


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_command_writes_a_new_file_and_makes_its_folder(command, tmp_path, capsys):
    """The control of the refusals: a file that is not there is written, in a folder that is made if it is not there."""
    world = a_world(tmp_path)
    out = tmp_path / "new" / "fresh.json"
    code, err, _ = run_main(capsys, *WRITERS[command](out, world))
    assert code == 0, err
    assert out.read_text(encoding="utf-8") == expected_text(command, Store(world).journal())
    assert sorted(p.name for p in out.parent.iterdir()) == ["fresh.json"] and sorted(p.name for p in tmp_path.iterdir()) == ["new", "w.sqlite"]  # no temporary file is left


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_command_never_writes_over_a_file_that_is_there_whatever_it_holds(command, tmp_path, capsys):
    """An old export, text that begins like a database file, a folder, a link that leads nowhere: all are taken names. (Only `build` and `picture` replace their output.)"""
    world = a_world(tmp_path)
    old = tmp_path / "old.json"
    old.write_text("an old file", encoding="utf-8")
    lookalike = tmp_path / "lookalike.json"
    lookalike.write_text("SQLite format 3 is how such a file begins, but this is text", encoding="utf-8")
    (tmp_path / "taken").mkdir()
    try:
        (tmp_path / "nowhere.json").symlink_to(tmp_path / "behind.json")
    except OSError:
        pass
    before = everything_in(tmp_path)
    for name in (old, lookalike, tmp_path / "taken", tmp_path / "nowhere.json"):
        if not os.path.lexists(name):
            continue
        code, err, _ = run_main(capsys, *WRITERS[command](name, world))
        assert code == 2 and f"{name} is there already" in err, (name, err)
        assert everything_in(tmp_path) == before and not (tmp_path / "behind.json").exists(), name  # nothing changed, no file made behind a link, no temporary file left


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_name_that_is_a_named_pipe_or_a_file_that_cannot_be_read_is_a_taken_name_and_is_not_waited_on(command, tmp_path, capsys):
    import signal

    world = a_world(tmp_path)
    taken = []
    if hasattr(os, "mkfifo") and hasattr(signal, "alarm"):
        os.mkfifo(tmp_path / "pipe")
        taken.append(tmp_path / "pipe")
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        (tmp_path / "unreadable").write_text("not for reading", encoding="utf-8")
        (tmp_path / "unreadable").chmod(0)
        taken.append(tmp_path / "unreadable")
    if not taken:
        pytest.skip("this system has no named pipes, and the user can read any file")
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError("the command waited")))
    try:
        for name in taken:
            signal.alarm(20)
            try:
                code, err, _ = run_main(capsys, *WRITERS[command](name, world))
            finally:
                signal.alarm(0)
            assert code == 2 and f"{name} is there already" in err, (name, err)
    finally:
        if (tmp_path / "unreadable").exists():
            (tmp_path / "unreadable").chmod(0o600)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["w.sqlite", *(n.name for n in taken)])  # nothing made, no temporary file left


@pytest.mark.parametrize("command", list(WRITERS))
@pytest.mark.parametrize("appears", ["a world", "a file of text"])
def test_a_file_that_appears_between_the_check_and_the_write_is_never_written_over(command, appears, tmp_path, capsys, monkeypatch):
    """The check that the output is not a database passes, the world is read, and the other party makes the file in the meantime: the write was an `os.replace`, which replaced it."""
    world = a_world(tmp_path)
    out, made = tmp_path / "out.json", []
    real = Store.journal

    def read_and_then_the_file_appears(self):
        journal = real(self)
        if appears == "a world":
            Store.create(out)
        else:
            out.write_text("the other party's file", encoding="utf-8")
        made.append(out.read_bytes())
        return journal

    monkeypatch.setattr(Store, "journal", read_and_then_the_file_appears)
    code, err, _ = run_main(capsys, *WRITERS[command](out, world))
    monkeypatch.undo()
    assert code == 2 and f"{out} is there already" in err, err
    assert made and out.read_bytes() == made[0]  # the other party's file is as it was made
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.json", "w.sqlite"]  # no temporary file is left


@pytest.mark.parametrize("command", ["new", "import", *WRITERS])
def test_where_there_are_no_hard_links_a_command_that_makes_a_file_is_refused_and_leaves_nothing(command, tmp_path, capsys, monkeypatch):
    """A disk with no hard links (a FAT volume, some network shares): nothing is published, the temporary file is removed, and the user is told what to do."""
    world = a_world(tmp_path)
    source, _ = world_file(tmp_path)
    argv = {"new": ("world", "new", "--world", str(tmp_path / "made.sqlite")), "import": ("world", "import", str(source), "--world", str(tmp_path / "made.sqlite")),
            "export": WRITERS["export"](tmp_path / "made.json", world), "fold": WRITERS["fold"](tmp_path / "made.json", world)}[command]
    before = everything_in(tmp_path)

    def no_links(*args, **kw):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    code, err, _ = run_main(capsys, *argv)
    assert code == 2 and "cannot be published: a hard link could not be made in " in err and err.strip().endswith("choose a folder on a disk that supports hard links"), err
    assert everything_in(tmp_path) == before  # nothing made, no temporary file left


@pytest.mark.parametrize("command", list(WRITERS))
def test_the_temporary_file_of_an_output_is_never_a_file_that_is_there(command, tmp_path, capsys):
    """The temporary file was named `.<output>.<pid>.part`: a world with that name was opened for writing, which empties it, and was then renamed away."""
    world = tmp_path / f".out.json.{os.getpid()}.part"
    Store.import_journal(world, play(3, steps=60))
    before, out = world.read_bytes(), tmp_path / "out.json"
    code, err, _ = run_main(capsys, *WRITERS[command](out, world))
    assert code == 0, err
    assert world.read_bytes() == before  # the world is where it was, as it was
    assert out.read_text(encoding="utf-8") == expected_text(command, Store(world).journal())
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([world.name, "out.json"])


@pytest.mark.parametrize("command", list(WRITERS))
def test_the_file_a_command_writes_has_the_permissions_of_any_file_the_user_makes(command, tmp_path, capsys):
    """The file that is published has the permissions asked for less the umask, not the private ones that a temporary file is often given."""
    world = a_world(tmp_path)
    before = os.umask(0o027)
    try:
        plain = tmp_path / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        code, err, _ = run_main(capsys, *WRITERS[command](tmp_path / "out.json", world))
    finally:
        os.umask(before)
    assert code == 0, err
    assert stat.S_IMODE((tmp_path / "out.json").stat().st_mode) == stat.S_IMODE(plain.stat().st_mode) == 0o640


@pytest.mark.parametrize("command", list(WRITERS))
def test_a_store_with_a_cell_that_is_not_what_the_column_holds_is_an_error_of_the_command_and_not_a_traceback(command, tmp_path, capsys):
    path = tmp_path / "w.sqlite"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE world (id, format, version, rule)")
        db.execute("CREATE TABLE event (seq, at, kind, payload)")
        db.execute("CREATE TABLE item (seq, id, json)")
        db.execute("INSERT INTO world VALUES (1, 'bibliopolis.world', 1, NULL)")
    out = tmp_path / "out.json"
    code, err, _ = run_main(capsys, *WRITERS[command](out, path))
    assert code == 2 and err.strip() == f"bibliopolis: {path}: world.rule (row 1) must be text, got NoneType" and not out.exists()


# ---------------------------------------------------------------------------------------------------- fold ----
def test_fold_writes_the_city_as_build_does_and_the_picture_and_the_chronicle_read_it(tmp_path, capsys):
    source, journal = world_file(tmp_path)
    run_main(capsys, "world", "import", str(source), "--world", str(tmp_path / "w.sqlite"))
    city_file = tmp_path / "city.json"
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(city_file), "--world", str(tmp_path / "w.sqlite"))
    city = journal.state.city()
    assert code == 0 and city_file.read_text(encoding="utf-8") == lay.render(city)
    s = {"houses": city["world"]["houses"], "roads": city["composition"]["streets"]["total"], "ring": city["composition"]["measure"]["ring_lots"]}
    splits = sum(1 for e in city["world"]["chronicle"] if "from" in e)
    assert err.strip() == f"wrote {city_file}: {s['houses']} houses on {s['roads']} roads, {s['ring']} on the ring road, {splits} splits, 0 over (mode hand)"
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


def test_fold_of_an_empty_world_is_the_town_hall_and_the_empty_ring_road(tmp_path, capsys):
    run_main(capsys, "world", "new", "--world", str(tmp_path / "w.sqlite"))
    out = tmp_path / "city.json"
    code, err, _ = run_main(capsys, "world", "fold", "--out", str(out), "--world", str(tmp_path / "w.sqlite"))
    assert code == 0 and err.strip() == f"wrote {out}: 0 houses on 1 roads, 0 on the ring road, 0 splits, 0 over (mode hand)"
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
    assert code == 2 and err.startswith("bibliopolis: ") and f"{tmp_path / 'taken'} is there already" in err  # (a folder is a taken name)
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked").chmod(0o500)
    try:
        if os.access(tmp_path / "locked", os.W_OK):
            return  # (a user who may write anywhere cannot be refused here)
        code, err, _ = run_main(capsys, "world", "fold", "--out", str(tmp_path / "locked" / "c.json"), "--world", str(tmp_path / "w.sqlite"))
        assert code == 1 and err.startswith("bibliopolis: ") and not list((tmp_path / "locked").iterdir())
    finally:
        (tmp_path / "locked").chmod(0o700)


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
