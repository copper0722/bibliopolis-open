"""The world file (JSON) and the SQLite store (bibliopolis.journal, bibliopolis.store): what they hold, that they round-trip byte for byte, and what they refuse."""

import copy
import json
import os
import sqlite3
from pathlib import Path

import pytest
from hand_support import Hand, hid, item, play, stamp, topic

from bibliopolis import layout as lay
from bibliopolis import store
from bibliopolis.events import Refusal
from bibliopolis.inputs import InputError
from bibliopolis.journal import FORMAT, VERSION, Journal, WorldFileError, dumps_world, load_world_file, read_world, world_document
from bibliopolis.store import Store


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def small():
    """A world of 14 houses, a road, a filing and an undo: every table has rows."""
    h = Hand({"max": 20, "min": 5, "auto": False})
    h.add(12, topic(1, 1, 1, 1))
    h.add(2)
    h.open("a", "Alpha", None, houses(1, 10))
    h.file(hid(11), "a")
    h.undo()
    return h.journal


def text_of(journal):
    return dumps_world(world_document(journal))


# -------------------------------------------------------------------------------------------- the file ----
def test_an_empty_world_is_this_text():
    assert dumps_world(world_document(Journal())) == ('{\n "format": "bibliopolis.world",\n "version": 1,\n "rule": {"max":40,"min":10,"auto":false},\n'
                                                      ' "items": [],\n "events": []\n}\n')


def test_a_world_file_has_the_header_then_one_item_and_one_event_to_a_line():
    j = small()
    text = text_of(j)
    lines = text.split("\n")
    assert lines[:3] == ['{', ' "format": "bibliopolis.world",', ' "version": 1,'] and lines[3] == ' "rule": {"max":20,"min":5,"auto":false},'
    assert lines[4] == ' "items": [' and lines[4 + 14 + 1] == ' ],' and lines[4 + 14 + 2] == ' "events": [' and lines[-3] == ' ]' and lines[-2:] == ['}', '']
    items, events = lines[5:19], lines[4 + 14 + 3:-3]
    assert len(items) == 14 and len(events) == len(j.events) == 14 + 3
    assert [json.loads(line.rstrip(",")) for line in items] == j.items() and [json.loads(line.rstrip(",")) for line in events] == j.events
    assert all(line.startswith("  {") for line in items + events) and "\r" not in text


def test_the_document_of_a_journal_says_the_rule_it_started_with_and_the_items_of_every_add_item_event():
    j = small()
    doc = world_document(j)
    assert list(doc) == ["format", "version", "rule", "items", "events"] and (doc["format"], doc["version"]) == (FORMAT, VERSION) == ("bibliopolis.world", 1)
    assert doc["rule"] == {"max": 20, "min": 5, "auto": False} and [i["id"] for i in doc["items"]] == houses(1, 14) and doc["events"] == j.events
    j.append("set_rule", {"max": 7, "min": 2, "auto": True}, stamp(99))
    assert world_document(j)["rule"] == {"max": 20, "min": 5, "auto": False}  # the rule of the start; a set_rule event is in the log


@pytest.mark.parametrize("seed", [1, 4, 9, 16])
def test_a_world_file_read_and_written_again_is_the_same_bytes_and_the_same_world(seed):
    j = play(seed, steps=120)
    text = text_of(j)
    again = read_world(json.loads(text))
    assert text_of(again) == text and again.events == j.events and again.rule == j.rule
    assert lay.render(again.state.city()) == lay.render(j.state.city())


def test_a_file_that_is_not_canonical_is_read_and_written_in_the_canonical_form(tmp_path):
    j = small()
    doc = json.loads(text_of(j))
    messy = {k: doc[k] for k in reversed(list(doc))}  # the keys the other way round
    messy["events"] = [{k: e[k] for k in reversed(list(e))} for e in doc["events"]]
    messy["items"] = [{k: i[k] for k in reversed(list(i))} for i in doc["items"]]
    path = tmp_path / "messy.json"
    path.write_text(json.dumps(messy, indent=4), encoding="utf-8")
    assert dumps_world(world_document(load_world_file(path))) == text_of(j)


def test_a_file_with_a_byte_order_mark_or_that_is_not_json_is_read_or_refused_by_the_loader(tmp_path):
    path = tmp_path / "w.json"
    path.write_bytes(b"\xef\xbb\xbf" + text_of(small()).encode("utf-8"))
    assert text_of(load_world_file(path)) == text_of(small())
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError, match="not valid JSON"):
        load_world_file(path)


# ---------------------------------------------------------------------------------------------- refusals ----
def corrupt(change):
    doc = json.loads(text_of(small()))
    change(doc)
    return doc


PROBLEMS = [
    (lambda d: d.pop("rule"), "world: not a world file: missing rule"),
    (lambda d: d.update(colour="red"), "unknown colour"),
    (lambda d: d.update(format="something.else"), "world.format: must be 'bibliopolis.world'"),
    (lambda d: d.update(version=2), "world.version: this program reads version 1, got 2"),
    (lambda d: d.update(version=True), "world.version"),
    (lambda d: d["rule"].update(min=30), "world.rule: min (30) is more than max (20)"),
    (lambda d: d["rule"].update(auto="yes"), "world.rule.auto: must be true or false"),
    (lambda d: d.update(items={}), "world.items: must be a list"),
    (lambda d: d["items"][2].update(year="2020"), "world.items[2].year: must be a whole number"),
    (lambda d: d["items"][0].update(colour="red"), "world.items[0]: unknown colour"),
    (lambda d: d["events"][3]["payload"]["item"].update(id=""), "world.events[3].payload.item.id: must not be empty"),
    (lambda d: d["events"].__setitem__(1, {"seq": 2}), "world.events[1]: missing at, kind, payload"),
    (lambda d: d["events"][0].update(at="yesterday"), "world.events[0].at: 'yesterday' is not an ISO 8601"),
    (lambda d: d["events"][14].update(kind="sweep"), "world.events[14].kind"),
    (lambda d: d["events"][5].update(seq=7), "world.events[5].seq: must be 6"),
    (lambda d: d["events"].pop(5), "world.events[5].seq: must be 6"),
    (lambda d: d["events"][15]["payload"].update(road="nowhere"), "world.events[15] (file): there is no road 'nowhere'"),
    (lambda d: d["events"][16]["payload"].update(seq=40), "world.events[16] (undo): an undo names an earlier event"),
    (lambda d: d["items"].pop(), "world.items[13]: the items are those of the add_item events, in order (14 of them), and the file says otherwise (13)"),
    (lambda d: d["items"].reverse(), "world.items[0]: the items are those of the add_item events"),
    (lambda d: d["items"][4].update(title="Another title"), "world.items[4]: the items are those of the add_item events"),
]


@pytest.mark.parametrize("change, message", PROBLEMS, ids=[str(i) for i in range(len(PROBLEMS))])
def test_a_world_file_that_is_not_a_world_is_refused_with_the_place_of_the_problem(change, message):
    with pytest.raises(WorldFileError) as why:
        read_world(corrupt(change))
    assert message in str(why.value), str(why.value)
    assert isinstance(why.value, InputError)


@pytest.mark.parametrize("value", [[], "world", 3, None])
def test_a_world_file_must_be_an_object(value):
    with pytest.raises(WorldFileError, match="world: not a world file: it must be a JSON object"):
        read_world(value)


def test_every_problem_of_shape_is_reported_at_once():
    def change(d):
        d["rule"]["max"] = 0
        d["items"][0]["year"] = "x"
        d["events"][1]["at"] = "never"

    with pytest.raises(WorldFileError) as why:
        read_world(corrupt(change))
    lines = str(why.value).splitlines()
    assert len(lines) >= 3 and any("world.rule.max" in line for line in lines) and any("world.items[0].year" in line for line in lines) and any("world.events[1].at" in line for line in lines)


def test_a_log_that_the_world_would_not_have_taken_is_refused_where_the_world_stops():
    def again(doc):  # the first house added a second time, in the place of the open_road, and the events numbered again
        doc["events"].insert(14, copy.deepcopy(doc["events"][0]))
        for i, e in enumerate(doc["events"]):
            e["seq"] = i + 1

    with pytest.raises(WorldFileError, match=r"world\.events\[14\] \(add_item\): 'h0001' is a house already"):
        read_world(corrupt(again))


# ------------------------------------------------------------------------------------------------- the store ----
def test_a_store_is_made_with_a_rule_and_nothing_else_and_is_never_overwritten(tmp_path):
    path = tmp_path / "w.sqlite"
    made = Store.create(path, {"max": 25, "min": 6, "auto": True})
    assert made.path == path and path.is_file()
    j = made.journal()
    assert (j.rule, j.events, list(j.state.items)) == ({"max": 25, "min": 6, "auto": True}, [], [])
    with pytest.raises(Refusal, match="is there already; a world is not overwritten"):
        Store.create(path)
    assert Store(path).journal().rule == {"max": 25, "min": 6, "auto": True}
    with pytest.raises(Refusal, match="min"):
        Store.create(tmp_path / "bad.sqlite", {"max": 5, "min": 9, "auto": False})
    assert not (tmp_path / "bad.sqlite").exists()  # a rule that cannot be leaves no file behind


def test_the_tables_of_a_store_are_world_item_and_event_with_the_payloads_as_canonical_text(tmp_path):
    j = small()
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, j)
    with sqlite3.connect(path) as db:
        tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
        head = db.execute("SELECT format, version, rule FROM world").fetchall()
        events = db.execute("SELECT seq, at, kind, payload FROM event ORDER BY seq").fetchall()
        items = db.execute("SELECT seq, id, json FROM item ORDER BY seq").fetchall()
    assert tables == ["event", "item", "world"] and head == [("bibliopolis.world", 1, '{"max":20,"min":5,"auto":false}')]
    assert [(r[0], r[1], r[2]) for r in events] == [(e["seq"], e["at"], e["kind"]) for e in j.events]
    assert events[14][3] == '{"road":"a","name":"Alpha","parent":null,"houses":[' + ",".join(f'"{x}"' for x in houses(1, 10)) + "]}"
    assert [(r[0], r[1]) for r in items] == [(i, hid(i)) for i in range(1, 15)] and json.loads(items[0][2]) == j.items()[0]


def test_json_to_sqlite_to_json_and_sqlite_to_json_to_sqlite_are_byte_identical(tmp_path):
    for seed in (2, 6):
        j = play(seed, steps=100)
        want = text_of(j)
        one = tmp_path / f"a{seed}.sqlite"
        Store.import_journal(one, read_world(json.loads(want)))
        assert Store(one).export_text() == want  # JSON -> SQLite -> JSON
        two = tmp_path / f"b{seed}.sqlite"
        Store.import_journal(two, read_world(json.loads(Store(one).export_text())))  # SQLite -> JSON -> SQLite
        with sqlite3.connect(one) as a, sqlite3.connect(two) as b:
            for table in ("world", "event", "item"):
                assert a.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() == b.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        assert Store(two).export_text() == want
        assert lay.render(Store(two).journal().state.city()) == lay.render(j.state.city())


def test_an_event_appended_to_a_store_is_there_when_it_is_read_again_and_only_the_next_number_goes_in(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.create(path)
    j = Store(path).journal()
    for i in range(1, 4):
        Store(path).append(j.append("add_item", {"item": item(i, topic(1, 1, 1, 1))}, stamp(i)))
    again = Store(path).journal()
    assert again.events == j.events and list(again.state.items) == houses(1, 3) and text_of(again) == text_of(j)
    with pytest.raises(Refusal, match="holds 3 events; the next is number 4, not 6"):
        Store(path).append({**j.events[0], "seq": 6})
    with pytest.raises(Refusal, match="not 3"):
        Store(path).append(j.events[2])
    assert len(Store(path).journal().events) == 3


def test_the_log_of_a_store_is_append_only_the_file_itself_refuses_an_update_or_a_delete(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())
    with sqlite3.connect(path) as db:
        for sql in ("UPDATE event SET at = 'x' WHERE seq = 1", "DELETE FROM event WHERE seq = 1", "UPDATE item SET id = 'z'", "DELETE FROM item",
                    "UPDATE world SET rule = '{}'", "DELETE FROM world"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(sql)
    assert text_of(Store(path).journal()) == text_of(small())


def test_a_file_that_is_not_a_world_is_refused(tmp_path):
    with pytest.raises(WorldFileError, match="there is no world here"):
        Store(tmp_path / "none.sqlite").journal()
    text = tmp_path / "text.sqlite"
    text.write_text("this is not a database", encoding="utf-8")
    with pytest.raises(WorldFileError, match="not a world of this program"):
        Store(text).journal()
    other = tmp_path / "other.sqlite"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE world (id INTEGER, format TEXT, version INTEGER, rule TEXT)")
        db.execute("INSERT INTO world VALUES (1, 'something.else', 1, '{}')")
        db.execute("CREATE TABLE event (seq INTEGER, at TEXT, kind TEXT, payload TEXT)")
        db.execute("CREATE TABLE item (seq INTEGER, id TEXT, json TEXT)")
    with pytest.raises(WorldFileError, match="its world table must hold one row"):
        Store(other).journal()


def test_a_world_that_was_tampered_with_is_refused_where_the_log_stops_making_sense(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())  # 17 events
    with sqlite3.connect(path) as db:  # a row put in by hand, past the triggers (they guard update and delete, not insert)
        db.execute("INSERT INTO event VALUES (18, '2026-01-01', 'file', '{\"house\":\"h0012\",\"road\":\"gone\"}')")
    with pytest.raises(WorldFileError, match=r"w\.sqlite: event 18 \(file\): there is no road 'gone'"):
        Store(path).journal()
    skipped = tmp_path / "skipped.sqlite"
    Store.import_journal(skipped, small())
    with sqlite3.connect(skipped) as db:
        db.execute("INSERT INTO event VALUES (19, '2026-01-01', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false}')")
    with pytest.raises(WorldFileError, match="event 19 comes in place 18"):
        Store(skipped).journal()
    broken = tmp_path / "broken.sqlite"
    Store.import_journal(broken, small())
    with sqlite3.connect(broken) as db:
        db.execute("INSERT INTO event VALUES (18, '2026-01-01', 'set_rule', 'not json')")
    with pytest.raises(WorldFileError, match="a row does not hold JSON"):
        Store(broken).journal()


def test_an_item_table_that_does_not_say_what_the_events_say_is_refused(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO event VALUES (18, '2026-01-02', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false}')")
        db.execute("INSERT INTO item VALUES (18, 'ghost', '{\"id\":\"ghost\"}')")
    with pytest.raises(WorldFileError, match="the item table is not the items of the add_item events"):
        Store(path).journal()


def test_a_failed_import_leaves_no_file_behind(tmp_path, monkeypatch):
    path = tmp_path / "w.sqlite"
    j = small()
    insert = Store._insert

    def boom(db, event):
        if event["seq"] == 5:
            raise RuntimeError("the disk is full")
        insert(db, event)

    monkeypatch.setattr(Store, "_insert", staticmethod(boom))
    with pytest.raises(RuntimeError, match="disk is full"):
        Store.import_journal(path, j)
    assert not path.exists()


# --------------------------------------------------------------------------------------------- the home ----
def test_the_home_folder_is_the_one_the_environment_names_and_is_made_on_first_use(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b" / "Worlds"
    monkeypatch.setenv("BIBLIOPOLIS_HOME", str(target))
    assert not target.exists()
    assert store.home() == (target, True) and target.is_dir()
    assert store.home() == (target, False)  # made once


def test_without_the_environment_the_home_folder_is_bibliopolis_in_the_users_home(tmp_path, monkeypatch):
    monkeypatch.delenv("BIBLIOPOLIS_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert store.home() == (tmp_path / "Bibliopolis", True) and (tmp_path / "Bibliopolis").is_dir()


def test_a_tilde_in_the_environment_is_the_users_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("BIBLIOPOLIS_HOME", "~/Mine")
    assert store.home() == (tmp_path / "Mine", True)


def test_every_test_has_a_home_folder_of_its_own_that_is_not_the_real_one():
    folder = Path(os.environ["BIBLIOPOLIS_HOME"])
    assert folder.name == "Bibliopolis" and not folder.exists()  # (nothing has asked for it yet)
    assert folder != Path.home() / "Bibliopolis" and "pytest" in str(folder)
    assert store.home() == (folder, True)
