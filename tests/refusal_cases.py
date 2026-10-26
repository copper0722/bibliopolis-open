"""One scenario for every id of bibliopolis.events.CODES: a function that makes the world say it. A scenario takes a folder of the test (for the files and the stores) and returns

  the `Refusal` or the `WorldFileError` that carries the id, or
  for an id of a problem of shape, `{where, code, params, text}`: the problem as `Problems` keeps it, and its English line.

The test of the ids (tests/test_refusals.py) and the test of the page (tests/test_world_page.py) read them: the ids are the ones the program uses, the params are the names
`CODES` gives, and the table of docs/world.md shows the messages that these scenarios make. Not collected by pytest (the name has no test_ prefix)."""

import copy
import json
import sqlite3

from hand_support import Hand, hid, item, stamp, topic

from bibliopolis import events as ev
from bibliopolis.events import Problems, Refusal
from bibliopolis.journal import Journal, WorldFileError, dumps_world, read_world, world_document
from bibliopolis.store import Store, check_output
from bibliopolis.suggest import suggest_file, suggest_road


DOMAIN_1 = {"id": "ex:d1", "level": "domain", "name": "Domain 1"}


def raised(act):
    """Run `act`: the refusal or the file error it raises."""
    try:
        act()
    except (Refusal, WorldFileError) as exc:
        return exc
    raise AssertionError("nothing was refused")


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def town(n=15, rule=None):
    h = Hand(rule)
    h.add(n)
    return h


def one_problem(check, doc, where, code):
    """The first problem with the id `code` that `check` finds in `doc`."""
    problems = Problems()
    check(doc, where, problems)
    for line, entry in zip(problems.found, problems.items):
        if entry["code"] == code:
            return {**entry, "text": line}
    raise AssertionError(f"no problem {code!r} in {problems.found}")


def event_problem(code, **change):
    """A problem of an event: `change` is put into an event that is right (an add_item, and its payload for the keys of an item), and the event is checked."""
    good = {"seq": 1, "at": "2026-10-26T09:30:00Z", "kind": "add_item", "payload": {"item": item(1, topic(1, 1, 1, 1))}}
    doc = copy.deepcopy(good)
    for key, value in change.items():
        where, _, name = key.rpartition("__")
        target = doc if not where else doc["payload"]["item"] if where == "item" else doc["payload"]
        if value is KeyError:
            del target[name]
        else:
            target[name] = value
    return one_problem(ev.check_event, doc, "event", code)


def road_problem(code, kind, payload):
    return one_problem(ev.check_event, {"seq": 1, "at": "2026-10-26", "kind": kind, "payload": payload}, "event", code)


def file_problem(code, change):
    """A problem of shape of a world file: `change` breaks a small world file, and reading it reports the problems."""
    doc = json.loads(dumps_world(world_document(small_journal())))
    change(doc)
    error = raised(lambda: read_world(doc))
    assert error.code == "invalid", error.code
    for entry in error.params["problems"]:
        if entry["code"] == code:
            return {**entry, "text": str(error).splitlines()[error.params["problems"].index(entry)]}
    raise AssertionError(f"no problem {code!r} in {error}")


def small_journal():
    h = Hand({"max": 20, "min": 5, "auto": False})
    h.add(12, topic(1, 1, 1, 1))
    h.add(2)
    h.open("a", "Alpha", None, houses(1, 10))
    h.file(hid(11), "a")
    h.undo()
    return h.journal


def thirteen_avenues():
    h = Hand()
    for k in range(13):
        h.add(10)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    h.add(10)
    return h


# ------------------------------------------------------------------------------------ the world refuses ----
def ring1_full(tmp):
    h = thirteen_avenues()
    return raised(lambda: h.open("r13", "Road 13", None, h.state.houses_at(None)))


def too_deep(tmp):
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(1)
    parent = None
    for d in range(1, ev.RING_LIMIT + 1):
        h.open(f"r{d}", f"Road {d}", parent, [hid(1)])
        parent = f"r{d}"
    return raised(lambda: h.open("deeper", "Deeper", parent, [hid(1)]))


def house_exists(tmp):
    h = town(2)
    return raised(lambda: h.event("add_item", {"item": h.state.items[hid(1)]}))


def not_a_house(tmp):
    return raised(lambda: town(3).file("nobody", "a"))


def road_exists(tmp):
    h = town(14)
    h.open("a", "A", None, houses(1, 10))
    return raised(lambda: h.open("a", "A again", None, houses(11, 14)))


def no_road(tmp):
    return raised(lambda: town(3).file(hid(1), "nowhere"))


def parent_missing(tmp):
    return raised(lambda: town(12).open("a", "A", "ghost", houses(1, 10)))


def move_parent_missing(tmp):
    h = town(12)
    h.open("a", "A", None, houses(1, 10))
    return raised(lambda: h.move("a", "nowhere"))


def too_few_here(tmp):
    return raised(lambda: town(9).open("a", "A", None, houses(1, 9)))


def too_few_chosen(tmp):
    return raised(lambda: town(14).open("a", "A", None, houses(1, 9)))


def house_elsewhere(tmp):
    h = town(24)
    h.open("a", "A", None, houses(1, 10))
    return raised(lambda: h.open("b", "B", None, houses(1, 10)))


def node_taken(tmp):
    h = Hand()
    h.add(24, topic(1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 12), DOMAIN_1)
    return raised(lambda: h.open("b", "B", None, houses(13, 24), DOMAIN_1))


def house_not_under_node(tmp):
    h = Hand()
    h.add(12, topic(1, 1, 1, 1))
    h.add(12, topic(2, 1, 1, 1))
    return raised(lambda: h.open("a", "A", None, [*houses(2, 10), hid(13)], DOMAIN_1))


def not_an_avenue(tmp):
    h = town(10)
    h.open("a", "A", None, houses(1, 10))
    h.open("a1", "A one", "a", houses(1, 10))
    return raised(lambda: h.merge("m", "M", ["a", "a1"]))


def already_there(tmp):
    h = town(12)
    h.open("a", "A", None, houses(1, 10))
    return raised(lambda: h.file(hid(1), "a"))


def same_name(tmp):
    h = town(12)
    h.open("a", "Alpha", None, houses(1, 10))
    return raised(lambda: h.rename("a", "Alpha"))


def move_into_itself(tmp):
    h = town(30)
    h.open("a", "A", None, houses(1, 20))
    h.open("a1", "A one", "a", houses(1, 10))
    return raised(lambda: h.move("a1", "a1"))


def already_below(tmp):
    h = town(30)
    h.open("a", "A", None, houses(1, 20))
    h.open("a1", "A one", "a", houses(1, 10))
    return raised(lambda: h.move("a1", "a"))


def rule_unchanged(tmp):
    h = Hand()
    return raised(lambda: h.rule(40, 10, False))


# ------------------------------------------------------------------------------------------------ an undo ----
def undo_not_earlier(tmp):
    return raised(lambda: town(3).event("undo", {"seq": 9}))


def undo_not_counting(tmp):
    h = town(3)
    h.undo(3)
    return raised(lambda: h.undo(3))


def undo_depends(tmp):
    h = town(14)
    h.open("a", "A", None, houses(1, 10))
    h.rename("a", "Alpha")
    return raised(lambda: h.undo(15))


def undo_unfoldable(tmp):
    h = town(40)
    h.open("a", "A", None, houses(1, 10))  # 41
    h.file(hid(11), "a")  # 42
    h.undo(42)  # 43
    h.open("b", "B", None, houses(11, 20))  # 44
    return raised(lambda: h.undo(43))


# ------------------------------------------------------------------------------------- a log or a store ----
def event_out_of_place(tmp):
    j = small_journal()
    skipped = [{**e, "seq": e["seq"] + (1 if e["seq"] > 5 else 0)} for e in j.events]
    return raised(lambda: Journal.replay(j.rule, skipped))


def world_exists(tmp):
    Store.create(tmp / "w.sqlite")
    return raised(lambda: Store.create(tmp / "w.sqlite"))


def not_next_event(tmp):
    path = tmp / "w.sqlite"
    Store.create(path)
    j = Store(path).journal()
    for i in range(1, 4):
        Store(path).append(j.append("add_item", {"item": item(i)}, stamp(i)))
    return raised(lambda: Store(path).append({**j.events[0], "seq": 6}))


def output_is_the_world(tmp):
    path = tmp / "w.sqlite"
    Store.create(path)
    return raised(lambda: check_output(path, path))


def output_is_a_database(tmp):
    Store.create(tmp / "w.sqlite")
    Store.create(tmp / "other.sqlite")
    return raised(lambda: check_output(tmp / "other.sqlite", tmp / "w.sqlite"))


def invalid(tmp):
    return raised(lambda: Journal().append("add_item", {"item": {"id": 5, "title": "T", "authors": [], "year": None, "type": "article"}}, stamp(1)))


# ------------------------------------------------------------------------------------ problems of shape ----
def keys_missing(tmp):
    return one_problem(ev.check_event, {"seq": 1}, "event", "keys_missing")


def keys_unknown(tmp):
    return event_problem("keys_unknown", item__colour="red")


def not_an_object(tmp):
    return one_problem(ev.check_event, [], "event", "not_an_object")


def not_a_list(tmp):
    return file_problem("not_a_list", lambda d: d.update(items={}))


def not_text(tmp):
    return event_problem("not_text", item__id=5)


def text_empty(tmp):
    return event_problem("text_empty", item__id="")


def text_not_utf8(tmp):
    return event_problem("text_not_utf8", item__title="\ud800")


def text_control(tmp):
    return event_problem("text_control", item__id="a\nb")


def authors_not_a_list(tmp):
    return event_problem("authors_not_a_list", item__authors="A. Author")


def year_bad(tmp):
    return event_problem("year_bad", item__year="2020")


def topics_not_a_list(tmp):
    return event_problem("topics_not_a_list", item__openalex="x")


def topics_too_many(tmp):
    return event_problem("topics_too_many", item__openalex=[topic(1, 1, 1, k) for k in range(1, 5)])


def topic_not_an_object(tmp):
    return event_problem("topic_not_an_object", item__openalex=[5])


def level_not_an_object(tmp):
    return event_problem("level_not_an_object", item__openalex=[{**topic(1, 1, 1, 1), "domain": 5}])


def topic_twice(tmp):
    return event_problem("topic_twice", item__openalex=[topic(1, 1, 1, 1), topic(2, 1, 1, 1), topic(1, 1, 1, 1)])


def rule_not_an_object(tmp):
    return one_problem(ev.check_rule, [], "world.rule", "rule_not_an_object")


def rule_number_bad(tmp):
    return one_problem(ev.check_rule, {"max": 0, "min": 1, "auto": False}, "world.rule", "rule_number_bad")


def not_a_boolean(tmp):
    return one_problem(ev.check_rule, {"max": 40, "min": 10, "auto": "yes"}, "world.rule", "not_a_boolean")


def rule_min_over_max(tmp):
    return one_problem(ev.check_rule, {"max": 5, "min": 9, "auto": False}, "world.rule", "rule_min_over_max")


def road_id_lane_like(tmp):
    return road_problem("road_id_lane_like", "open_road", {"road": "lane:x:2", "name": "N", "parent": None, "houses": ["a"]})


def road_id_reserved(tmp):
    return road_problem("road_id_reserved", "open_road", {"road": "auto:7", "name": "N", "parent": None, "houses": ["a"]})


def undo_seq_bad(tmp):
    return road_problem("undo_seq_bad", "undo", {"seq": 0})


def houses_empty(tmp):
    return road_problem("houses_empty", "open_road", {"road": "r", "name": "N", "parent": None, "houses": []})


def house_chosen_twice(tmp):
    return road_problem("house_chosen_twice", "open_road", {"road": "r", "name": "N", "parent": None, "houses": ["a", "a"]})


def node_not_an_object(tmp):
    return road_problem("node_not_an_object", "open_road", {"road": "r", "name": "N", "parent": None, "houses": ["a"], "topic": "domain"})


def node_level_bad(tmp):
    return road_problem("node_level_bad", "open_road", {"road": "r", "name": "N", "parent": None, "houses": ["a"], "topic": {**DOMAIN_1, "level": "planet"}})


def members_too_few(tmp):
    return road_problem("members_too_few", "merge_roads", {"road": "m", "name": "M", "parent": None, "members": ["a"]})


def member_chosen_twice(tmp):
    return road_problem("member_chosen_twice", "merge_roads", {"road": "m", "name": "M", "parent": None, "members": ["a", "a"]})


def parent_not_root(tmp):
    return road_problem("parent_not_root", "merge_roads", {"road": "m", "name": "M", "parent": "r", "members": ["a", "b"]})


def event_seq_bad(tmp):
    return event_problem("event_seq_bad", seq=0)


def date_bad(tmp):
    return event_problem("date_bad", at="yesterday")


def kind_unknown(tmp):
    return event_problem("kind_unknown", kind="sweep")


# ---------------------------------------------------------------------------------- not a world file ----
def not_a_world_file(tmp):
    return raised(lambda: read_world([]))


def file_keys(tmp):
    doc = json.loads(dumps_world(world_document(small_journal())))
    del doc["rule"]
    return raised(lambda: read_world(doc))


def format_wrong(tmp):
    doc = json.loads(dumps_world(world_document(small_journal())))
    doc["format"] = "something.else"
    return raised(lambda: read_world(doc))


def version_wrong(tmp):
    doc = json.loads(dumps_world(world_document(small_journal())))
    doc["version"] = 2
    return raised(lambda: read_world(doc))


def events_not_numbered(tmp):
    doc = json.loads(dumps_world(world_document(small_journal())))
    doc["events"][5]["seq"] = 7
    return raised(lambda: read_world(doc))


def items_differ(tmp):
    doc = json.loads(dumps_world(world_document(small_journal())))
    doc["items"].pop()
    return raised(lambda: read_world(doc))


def no_world(tmp):
    return raised(lambda: Store(tmp / "none.sqlite").journal())


def not_a_world(tmp):
    path = tmp / "text.sqlite"
    path.write_text("this is not a database", encoding="utf-8")
    return raised(lambda: Store(path).journal())


def world_table_wrong(tmp):
    path = tmp / "other.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE world (id INTEGER, format TEXT, version INTEGER, rule TEXT)")
        db.execute("INSERT INTO world VALUES (1, 'something.else', 1, '{}')")
        db.execute("CREATE TABLE event (seq INTEGER, at TEXT, kind TEXT, payload TEXT)")
        db.execute("CREATE TABLE item (seq INTEGER, id TEXT, json TEXT)")
    return raised(lambda: Store(path).journal())


def row_not_json(tmp):
    path = tmp / "w.sqlite"
    Store.import_journal(path, small_journal())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO event VALUES (18, '2026-01-01', 'set_rule', 'not json')")
    return raised(lambda: Store(path).journal())


def item_table_differs(tmp):
    path = tmp / "w.sqlite"
    Store.import_journal(path, small_journal())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO event VALUES (18, '2026-01-02', 'set_rule', '{\"max\":9,\"min\":3,\"auto\":false}')")
        db.execute("INSERT INTO item VALUES (18, 'ghost', '{\"id\":\"ghost\"}')")
    return raised(lambda: Store(path).journal())


CASES = {name: fn for name, fn in globals().items() if name in ev.CODES and callable(fn)}

# the ids that a call of the suggestions can also make (no_road, not_a_house): the same refusals, from another place
FROM_SUGGESTIONS = {"no_road": lambda world: suggest_road(world, "x"), "not_a_house": lambda world: suggest_file(world, "nobody")}
