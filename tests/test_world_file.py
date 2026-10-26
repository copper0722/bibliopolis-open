"""The world file (JSON) and the SQLite store (bibliopolis.journal, bibliopolis.store): what they hold, that they round-trip byte for byte, and what they refuse."""

import copy
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from hand_support import Hand, hid, item, play, scripted, scripted_branches, scripted_merge, scripted_nodes, stamp, topic

from bibliopolis import events as ev
from bibliopolis import layout as lay
from bibliopolis import store
from bibliopolis.canonical import dumps
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
    assert dumps_world(world_document(Journal())) == ('{\n "format": "bibliopolis.world",\n "version": 1,\n "rule": {"max":40,"min":10,"auto":false,"branches":13},\n'
                                                      ' "items": [],\n "events": []\n}\n')


def test_a_world_file_has_the_header_then_one_item_and_one_event_to_a_line():
    j = small()
    text = text_of(j)
    lines = text.split("\n")
    assert lines[:3] == ['{', ' "format": "bibliopolis.world",', ' "version": 1,'] and lines[3] == ' "rule": {"max":20,"min":5,"auto":false,"branches":13},'
    assert lines[4] == ' "items": [' and lines[4 + 14 + 1] == ' ],' and lines[4 + 14 + 2] == ' "events": [' and lines[-3] == ' ]' and lines[-2:] == ['}', '']
    items, events = lines[5:19], lines[4 + 14 + 3:-3]
    assert len(items) == 14 and len(events) == len(j.events) == 14 + 3
    assert [json.loads(line.rstrip(",")) for line in items] == j.items() and [json.loads(line.rstrip(",")) for line in events] == j.events
    assert all(line.startswith("  {") for line in items + events) and "\r" not in text


def test_the_document_of_a_journal_says_the_rule_it_started_with_and_the_items_of_every_add_item_event():
    j = small()
    doc = world_document(j)
    assert list(doc) == ["format", "version", "rule", "items", "events"] and (doc["format"], doc["version"]) == (FORMAT, VERSION) == ("bibliopolis.world", 1)
    assert doc["rule"] == {"max": 20, "min": 5, "auto": False, "branches": 13} and [i["id"] for i in doc["items"]] == houses(1, 14) and doc["events"] == j.events
    j.append("set_rule", {"max": 7, "min": 2, "auto": True, "branches": 13}, stamp(99))
    assert world_document(j)["rule"] == {"max": 20, "min": 5, "auto": False, "branches": 13}  # the rule of the start; a set_rule event is in the log


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


PIN_WORLD = "00cdd986d9c25997ee18ef20d8995e1e843f0bbe36d7f93bc9e95e5e7a351ea1"  # the sha256 of the world file of the scripted log (hand_support.scripted)
PIN_CITY = "57e3d960c0cb3bc05c66634d54b2844797c60219bd31dc5c45cab9c43c851185"  # ... and of the text of the city that it folds to; change them on purpose, with the engine
PIN_NODES_WORLD = "909c0564d34aca455dab84f7c659faf891f6e3a875d733ac6c1086561d860243"  # the same for the log with OpenAlex topics (hand_support.scripted_nodes): roads for nodes, the rule auto
PIN_NODES_CITY = "bcf9eee0e772d6cde66b420b9070d82bf8e79115338a32b5c3266d03762cd5f6"
PIN_MERGE_WORLD = "f8ef1194ff53f26e2d908c6e677f8b1fe62507ff89b0780a28028f04aded5274"  # ... and for the log in which the first ring fills and is merged (hand_support.scripted_merge)
PIN_MERGE_CITY = "436c7e3276f229dd7ad47fa423476189984b7a0c319c9bb4125714a27d35b68c"
PIN_BRANCHES_WORLD = "8bca726c6f6558d4b946f76c04a5de67540e528801c1fd600711e893886b5faf"  # ... and for the log of the branches (hand_support.scripted_branches): the rule merges a full ring itself, a merge below a road, the expansion
PIN_BRANCHES_CITY = "1d46fb02cccb325502a49d293117d5b2fb72cbb2457ba27eda1b709b34471db6"


def test_the_scripted_world_and_its_city_are_pinned_by_their_sha256():
    """A port in another language has these bytes to match: the file of a fixed log of every kind of event, and the city that the fold makes of it."""
    journal = scripted().journal
    assert hashlib.sha256(text_of(journal).encode("utf-8")).hexdigest() == PIN_WORLD
    assert hashlib.sha256(lay.render(journal.state.city()).encode("utf-8")).hexdigest() == PIN_CITY
    nodes = scripted_nodes().journal
    assert hashlib.sha256(text_of(nodes).encode("utf-8")).hexdigest() == PIN_NODES_WORLD
    assert hashlib.sha256(lay.render(nodes.state.city()).encode("utf-8")).hexdigest() == PIN_NODES_CITY
    merged = scripted_merge().journal
    assert hashlib.sha256(text_of(merged).encode("utf-8")).hexdigest() == PIN_MERGE_WORLD
    assert hashlib.sha256(lay.render(merged.state.city()).encode("utf-8")).hexdigest() == PIN_MERGE_CITY
    branches = scripted_branches().journal
    assert hashlib.sha256(text_of(branches).encode("utf-8")).hexdigest() == PIN_BRANCHES_WORLD
    assert hashlib.sha256(lay.render(branches.state.city()).encode("utf-8")).hexdigest() == PIN_BRANCHES_CITY


def test_titles_and_names_in_any_script_are_written_as_they_are_and_read_back(tmp_path):
    h = Hand()
    h.add_items([item(1, title="文獻城邦: 市政廳 \U0001d4b3 \u00e9", authors=["王小明", "Zoë Müller"]), item(2, title='quote " backslash \\ tab \t')])
    h.add(10)
    h.open("a", "大道 \"A\"", None, [hid(i) for i in range(1, 11)])
    text = text_of(h.journal)
    assert "文獻城邦" in text and "\\u" not in text.replace("\\u0009", "")  # written as characters, not as escapes (a tab is the one escape here)
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, read_world(json.loads(text)))
    assert Store(path).export_text() == text and Store(path).journal().state.nodes["a"]["name"] == '大道 "A"'


def test_a_lone_surrogate_is_refused_because_it_cannot_be_written_as_text():
    from bibliopolis import events as ev

    problems = ev.Problems()
    assert ev.check_item(item(1, title="\ud800"), "item", problems) is None and "cannot be written as UTF-8" in problems.found[0]


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
    assert (j.rule, j.events, list(j.state.items)) == ({"max": 25, "min": 6, "auto": True, "branches": 13}, [], [])
    with pytest.raises(Refusal, match="is there already; a world is not overwritten"):
        Store.create(path)
    assert Store(path).journal().rule == {"max": 25, "min": 6, "auto": True, "branches": 13}
    with pytest.raises(Refusal, match="min"):
        Store.create(tmp_path / "bad.sqlite", {"max": 5, "min": 9, "auto": False})
    assert not (tmp_path / "bad.sqlite").exists()  # a rule that cannot be leaves no file behind


def test_a_world_is_not_made_through_a_link_that_leads_nowhere(tmp_path):
    """A name that is a link to a file that is not there is a name that is taken: making the world would make the file behind the link."""
    behind, path = tmp_path / "behind.sqlite", tmp_path / "w.sqlite"
    try:
        path.symlink_to(behind)
    except OSError:
        pytest.skip("this system makes no links")
    with pytest.raises(Refusal, match="is there already"):
        Store.create(path)
    assert not behind.exists() and path.is_symlink()


def test_the_tables_of_a_store_are_world_item_and_event_with_the_payloads_as_canonical_text(tmp_path):
    j = small()
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, j)
    with sqlite3.connect(path) as db:
        tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
        head = db.execute("SELECT format, version, rule FROM world").fetchall()
        events = db.execute("SELECT seq, at, kind, payload FROM event ORDER BY seq").fetchall()
        items = db.execute("SELECT seq, id, json FROM item ORDER BY seq").fetchall()
    assert tables == ["event", "item", "world"] and head == [("bibliopolis.world", 1, '{"max":20,"min":5,"auto":false,"branches":13}')]
    assert [(r[0], r[1], r[2]) for r in events] == [(e["seq"], e["at"], e["kind"]) for e in j.events]
    assert events[14][3] == '{"road":"a","name":"Alpha","parent":null,"houses":[' + ",".join(f'"{x}"' for x in houses(1, 10)) + '],"topic":null}'
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


@pytest.mark.parametrize("journal_mode", ["delete", "wal"])
def test_a_store_is_read_as_it_is_at_one_moment_while_another_call_appends_to_it(journal_mode, tmp_path, monkeypatch):
    """The three tables are read in one read transaction. Another call, on a connection of its own, that appends after the event table is read and before the item table is read must not
    give the reader the old events and the new item (a false `item_table_differs`). In the default journal the reader's transaction holds the file and the writer waits for it (here:
    "database is locked", since no waiting is asked); in WAL a writer is not held, and the reader keeps the file as it was when its first read began. Either way the reader has its three
    events and the three items of them."""
    path = tmp_path / "w.sqlite"
    Store.create(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute(f"PRAGMA journal_mode={journal_mode}").fetchone() == (journal_mode,)
    j = Store(path).journal()
    for i in range(1, 4):
        Store(path).append(j.append("add_item", {"item": item(i)}, stamp(i)))
    fourth = j.append("add_item", {"item": item(4)}, stamp(4))
    said = []

    def another_call_appends():
        with closing(sqlite3.connect(path, timeout=0)) as db:  # (no waiting: a writer that cannot go on at once says so)
            try:
                with db:
                    db.execute("INSERT INTO event (seq, at, kind, payload) VALUES (?, ?, ?, ?)", (4, fourth["at"], fourth["kind"], dumps(fourth["payload"])))
                    db.execute("INSERT INTO item (seq, id, json) VALUES (?, ?, ?)", (4, hid(4), dumps(fourth["payload"]["item"])))
            except sqlite3.OperationalError as exc:
                return str(exc)
        return "appended"

    class Spy(sqlite3.Connection):
        def execute(self, sql, *args):
            if "FROM item" in sql and not said:  # the event table has been read, the item table is next
                said.append(another_call_appends())
            return super().execute(sql, *args)

    def spy_connect(where):
        db = sqlite3.connect(where, factory=Spy)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    monkeypatch.setattr(store, "_connect", spy_connect)
    seen = Store(path).journal()  # once the read is done, the writer may go on
    monkeypatch.undo()
    assert said == [{"delete": "database is locked", "wal": "appended"}[journal_mode]]
    assert len(seen.events) == 3 and list(seen.state.items) == houses(1, 3) and len(seen.items()) == 3
    if journal_mode == "delete":
        Store(path).append(fourth)  # the writer that had to wait goes on now
    assert len(Store(path).journal().events) == 4


def test_the_log_of_a_store_is_append_only_the_file_itself_refuses_an_update_or_a_delete(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())
    with sqlite3.connect(path) as db:
        for sql in ("UPDATE event SET at = 'x' WHERE seq = 1", "DELETE FROM event WHERE seq = 1", "UPDATE item SET id = 'z'", "DELETE FROM item",
                    "UPDATE world SET rule = '{}'", "DELETE FROM world"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(sql)
    assert text_of(Store(path).journal()) == text_of(small())


REPLACING_ROWS = {  # a row for each table with the key of a row that is there: (the columns, the values, the key, the column to change)
    "world": ("id, format, version, rule", "1, 'bibliopolis.world', 1, '{\"max\":1,\"min\":1,\"auto\":false}'", "id", "rule"),
    "event": ("seq, at, kind, payload", "1, '2030-01-01', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false,\"branches\":13}'", "seq", "payload"),
    "item": ("seq, id, json", "1, 'changed', '{\"id\":\"changed\"}'", "seq", "json"),
}
REPLACING_FORMS = {
    "INSERT OR REPLACE": "INSERT OR REPLACE INTO {table} ({columns}) VALUES ({values})",
    "REPLACE INTO": "REPLACE INTO {table} ({columns}) VALUES ({values})",
    "INSERT OR IGNORE": "INSERT OR IGNORE INTO {table} ({columns}) VALUES ({values})",
    "an upsert that updates": "INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT ({key}) DO UPDATE SET {change} = excluded.{change}",
    "an upsert that does nothing": "INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT DO NOTHING",
}


@pytest.mark.parametrize("form", list(REPLACING_FORMS))
@pytest.mark.parametrize("table", list(REPLACING_ROWS))
def test_the_log_of_a_store_is_append_only_a_row_that_is_there_is_not_replaced_either(table, form, tmp_path):
    """`INSERT OR REPLACE` removes the row that is in the way without the delete trigger (SQLite fires it only for recursive triggers), so a trigger on insert guards the key."""
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())
    columns, values, key, change = REPLACING_ROWS[table]
    with closing(sqlite3.connect(path)) as db:
        before = db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(REPLACING_FORMS[form].format(table=table, columns=columns, values=values, key=key, change=change))
        db.rollback()
        assert db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() == before
    assert text_of(Store(path).journal()) == text_of(small())


def test_a_row_with_a_new_key_goes_in_as_before_and_a_plain_insert_of_a_key_that_is_there_is_refused(tmp_path):
    """The controls of the guard on insert: appending (what `Store.append` does) is not hindered, and the key itself still refuses a plain insert."""
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())  # 17 events
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO event VALUES (18, '2030-01-01', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false,\"branches\":13}')")
        assert db.execute("SELECT COUNT(*) FROM event").fetchone() == (18,)
    with closing(sqlite3.connect(path)) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO event VALUES (18, 'x', 'x', 'x')")


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


def crafted(path, journal):
    """The three tables of a store with no type, no constraint and no trigger: what a file made elsewhere may hold."""
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE world (id, format, version, rule)")
        db.execute("CREATE TABLE event (seq, at, kind, payload)")
        db.execute("CREATE TABLE item (seq, id, json)")
        db.execute("INSERT INTO world VALUES (1, ?, ?, ?)", (FORMAT, VERSION, dumps(journal.rule)))
        for e in journal.events:
            db.execute("INSERT INTO event VALUES (?, ?, ?, ?)", (e["seq"], e["at"], e["kind"], dumps(e["payload"])))
            if e["kind"] == "add_item":
                db.execute("INSERT INTO item VALUES (?, ?, ?)", (e["seq"], e["payload"]["item"]["id"], dumps(e["payload"]["item"])))
    return path


def registered(error):
    """An error of a store is what the list of ids says: an id of the list, the params of that id and only plain JSON; the problems of an `invalid` the same."""
    assert error.code in ev.CODES, error.code
    assert set(error.params) == set(ev.CODES[error.code]), (error.code, sorted(error.params))
    assert json.loads(json.dumps(error.as_dict())) == error.as_dict()
    for problem in error.params.get("problems", ()):
        assert problem["code"] in ev.CODES and set(problem["params"]) == set(ev.CODES[problem["code"]]), problem


def test_a_store_with_a_cell_that_cannot_be_what_the_column_holds_is_refused_with_an_id_and_not_a_traceback(tmp_path):
    """The plainest case: `world.rule` is NULL. `json.loads(None)` raised a TypeError that no command caught."""
    j = small()
    path = crafted(tmp_path / "w.sqlite", j)
    assert text_of(Store(path).journal()) == text_of(j)  # (the control: the tables as they are read as the world)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE world SET rule = NULL")
    with pytest.raises(WorldFileError) as why:
        Store(path).journal()
    registered(why.value)
    assert why.value.code == "cell_wrong_type"
    assert why.value.params == {"path": str(path), "table": "world", "column": "rule", "row": 1, "expected": "text", "got": "NoneType"}
    assert str(why.value) == f"{path}: world.rule (row 1) must be text, got NoneType"


DEEP = "[" * 100_000 + "]" * 100_000
BAD_CELLS = {"null": None, "a whole number": 7, "a real": 1.5, "bytes": b"\xff\xfe", "empty text": "", "text that is no JSON": "not json", "JSON null": "null", "a JSON number": "5",
             "a JSON list": "[]", "a JSON text": '"x"', "a JSON object": "{}", "an object with another key": '{"a":1}', "a number of 5000 digits": "1" * 5000, "a list nested 100000 deep": DEEP}
CELLS = {"world": (("format", "version", "rule"), (1,)), "event": (("seq", "at", "kind", "payload"), (1, 14, 17)), "item": (("seq", "id", "json"), (1, 14))}


def test_whatever_a_cell_of_a_store_holds_the_store_is_read_or_refused_with_an_id_of_the_list(tmp_path):
    """One cell at a time of a store made elsewhere is set to a null, a number, bytes, text that is no JSON, JSON of another shape, a number of 5000 digits and a list nested 100000 deep:
    the store is read (when the cell can be what it is) or refused with a `WorldFileError` that has an id of the list; no other exception comes out."""
    base = crafted(tmp_path / "base.sqlite", small())
    seen = {}
    for table, (columns, rows) in CELLS.items():
        for column in columns:
            for row in rows:
                for what, bad in BAD_CELLS.items():
                    path = tmp_path / "case.sqlite"
                    shutil.copy(base, path)
                    with closing(sqlite3.connect(path)) as db, db:
                        db.execute(f"UPDATE {table} SET {column} = ? WHERE rowid = ?", (bad, row))
                    try:
                        Store(path).journal()
                    except WorldFileError as error:
                        registered(error)
                        seen.setdefault(error.code, []).append(f"{table}.{column}[{row}] = {what}")
    assert {"cell_wrong_type", "row_not_json"} <= set(seen) and len(seen["cell_wrong_type"]) >= 20, {code: len(cases) for code, cases in seen.items()}
    assert any("5000 digits" in case for case in seen["row_not_json"]) and any("nested 100000 deep" in case for case in seen["row_not_json"])


def test_an_event_is_not_appended_to_a_store_whose_numbers_are_not_numbers(tmp_path):
    """`append` takes the next number from the largest `seq`; in a column that holds text the largest is text, and adding to it was a TypeError."""
    j = small()
    path = crafted(tmp_path / "w.sqlite", j)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE event SET seq = 'last' WHERE seq = 17")
    with pytest.raises(WorldFileError) as why:
        Store(path).append(j.append("add_item", {"item": item(99)}, stamp(99)))
    registered(why.value)
    assert why.value.code == "cell_wrong_type" and why.value.params["row"] is None and str(why.value) == f"{path}: event.seq must be a whole number, got str"


def test_a_number_of_too_many_digits_and_a_list_nested_too_deep_are_rows_that_do_not_hold_json(tmp_path):
    for bad, reason in (("1" * 5000, "Exceeds the limit"), (DEEP, "nested too deeply to read")):
        path = crafted(tmp_path / "w.sqlite", small())
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE event SET payload = ? WHERE seq = 5", (bad,))
        with pytest.raises(WorldFileError) as why:
            Store(path).journal()
        registered(why.value)
        assert why.value.code == "row_not_json" and reason in why.value.params["reason"] and str(why.value).startswith(f"{path}: a row does not hold JSON (")
        path.unlink()


def test_a_world_that_was_tampered_with_is_refused_where_the_log_stops_making_sense(tmp_path):
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, small())  # 17 events
    with sqlite3.connect(path) as db:  # a row put in by hand, past the triggers (they refuse an update, a delete and a replace of a row, not a row with a new key)
        db.execute("INSERT INTO event VALUES (18, '2026-01-01', 'file', '{\"house\":\"h0012\",\"road\":\"gone\"}')")
    with pytest.raises(WorldFileError, match=r"w\.sqlite: event 18 \(file\): there is no road 'gone'"):
        Store(path).journal()
    skipped = tmp_path / "skipped.sqlite"
    Store.import_journal(skipped, small())
    with sqlite3.connect(skipped) as db:
        db.execute("INSERT INTO event VALUES (19, '2026-01-01', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false,\"branches\":13}')")
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
        db.execute("INSERT INTO event VALUES (18, '2026-01-02', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false,\"branches\":13}')")
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
    assert not path.exists() and list(tmp_path.iterdir()) == []  # not the world, and not the file it was built in


def test_a_file_is_not_written_over_the_world_it_comes_from_even_where_no_file_is_there_yet(tmp_path):
    with pytest.raises(Refusal) as why:
        store.check_output(tmp_path / "none.sqlite", tmp_path / "none.sqlite")
    assert why.value.code == "output_is_the_world" and why.value.params == {"path": str(tmp_path / "none.sqlite"), "world": str(tmp_path / "none.sqlite")}
    store.check_output(tmp_path / "a.json", tmp_path / "none.sqlite")  # two names, nothing there: nothing to protect
    (tmp_path / "taken").mkdir()
    with pytest.raises(Refusal) as taken:  # (a folder is no database, but it is a taken name)
        store.check_output(tmp_path / "taken", tmp_path / "none.sqlite")
    assert (taken.value.code, taken.value.params) == ("output_exists", {"path": str(tmp_path / "taken")})


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
