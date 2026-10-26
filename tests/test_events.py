"""The events of a hand-built world (bibliopolis.events): the shape of an item, of an event of each kind and of the rule, and which events of a log count."""

import copy

import pytest
from hand_support import hid, item, stamp, topic

from bibliopolis import events as ev
from bibliopolis.inputs import _Problems


def checked(check, value, where="x"):
    problems = _Problems()
    out = check(value, where, problems)
    return out, problems.found


def event(kind, payload, seq=1, at="2026-10-26T09:30:00Z"):
    return {"seq": seq, "at": at, "kind": kind, "payload": payload}


# ------------------------------------------------------------------------------------------------------ items ----
def test_an_item_keeps_its_metadata_and_gets_every_key_in_the_same_order():
    out, found = checked(ev.check_item, {"id": "a", "title": "", "authors": [], "year": None, "type": "article"})
    assert found == [] and list(out) == list(ev.ITEM_KEYS)
    assert out == {"id": "a", "title": "", "authors": [], "year": None, "doi": None, "type": "article", "openalex": []}
    full = {"type": "review", "openalex": [topic(1, 1, 1, 1)], "doi": "10.0000/x", "year": 2020, "authors": ["A. B"], "title": "T", "id": "i"}
    out, found = checked(ev.check_item, full)
    assert found == [] and list(out) == list(ev.ITEM_KEYS) and out["openalex"] == [topic(1, 1, 1, 1)]


def test_an_item_carries_the_primary_topic_and_up_to_two_more_with_all_four_levels():
    for n in range(4):
        out, found = checked(ev.check_item, item(1, *[topic(1, 1, 1, k) for k in range(1, n + 1)]))
        assert found == [] and len(out["openalex"]) == n
    out, found = checked(ev.check_item, item(1, *[topic(1, 1, 1, k) for k in range(1, 5)]))
    assert out is None and "holds 4 topics" in found[0]
    entry = topic(1, 1, 1, 1)
    del entry["subfield"]
    out, found = checked(ev.check_item, item(1, entry))
    assert out is None and "missing subfield" in found[0]


@pytest.mark.parametrize("make, fragment", [
    (lambda: [], "must be an object"),
    (lambda: {"id": "a"}, "missing title, authors, year, type"),
    (lambda: {**item(1), "colour": "red"}, "unknown colour"),
    (lambda: {**item(1), "id": ""}, "must not be empty"),
    (lambda: {**item(1), "id": "a\nb"}, "control characters"),
    (lambda: {**item(1), "year": "2020"}, "whole number"),
    (lambda: {**item(1), "year": True}, "whole number"),
    (lambda: {**item(1), "year": 10**9}, "whole number"),
    (lambda: {**item(1), "authors": "A. Author"}, "list of strings"),
    (lambda: {**item(1), "authors": [1]}, "must be a string"),
    (lambda: {**item(1), "doi": ""}, "must not be empty"),
    (lambda: {**item(1), "type": ""}, "must not be empty"),
    (lambda: {**item(1), "openalex": "x"}, "list of up to 3"),
    (lambda: {**item(1), "openalex": [{"domain": {"id": "d"}, "field": {}, "subfield": {}, "topic": {}}]}, "missing name"),
    (lambda: {**item(1), "openalex": [{**topic(1, 1, 1, 1), "extra": 1}]}, "unknown extra"),
    (lambda: {**item(1), "openalex": [{**topic(1, 1, 1, 1), "topic": {"id": "", "name": "n"}}]}, "must not be empty"),
    (lambda: {**item(1), "openalex": [topic(1, 1, 1, 1), topic(2, 1, 1, 1), topic(1, 1, 1, 1)]}, "the topic of item.openalex[0] already"),
])
def test_an_item_that_is_not_what_the_page_describes_is_refused_with_its_place(make, fragment):
    out, found = checked(ev.check_item, make(), "item")
    assert out is None and any(fragment in line for line in found), found
    assert all(line.startswith("item") for line in found)


def test_the_item_given_is_not_changed_and_the_one_returned_does_not_share_its_lists():
    original = item(1, topic(1, 1, 1, 1))
    snapshot = copy.deepcopy(original)
    out, _ = checked(ev.check_item, original)
    out["authors"].append("X")
    out["openalex"].append("y")
    assert original == snapshot


# ------------------------------------------------------------------------------------------------------ rules ----
def test_a_rule_is_two_whole_numbers_and_a_boolean():
    assert checked(ev.check_rule, {"auto": True, "min": 5, "max": 9}) == ({"max": 9, "min": 5, "auto": True}, [])
    assert checked(ev.check_rule, ev.DEFAULT_RULE) == ({"max": 40, "min": 10, "auto": False}, [])
    for bad, fragment in (({"max": 9, "min": 10, "auto": False}, "more than max"), ({"max": 0, "min": 0, "auto": False}, "from 1 to"),
                          ({"max": 9.5, "min": 1, "auto": False}, "whole number"), ({"max": True, "min": 1, "auto": False}, "whole number"),
                          ({"max": 9, "min": 1, "auto": 1}, "true or false"), ({"max": 9, "min": 1}, "missing auto"),
                          ({"max": 9, "min": 1, "auto": False, "x": 1}, "unknown x"), ({"max": ev.RULE_LIMIT + 1, "min": 1, "auto": False}, "from 1 to"), ([], "must be an object")):
        out, found = checked(ev.check_rule, bad)
        assert out is None and any(fragment in line for line in found), (bad, found)


# ---------------------------------------------------------------------------------------------------- events ----
GOOD = [("add_item", {"item": item(1)}), ("open_road", {"road": "r1", "name": "Road one", "parent": None, "houses": [hid(1), hid(2)]}),
        ("open_road", {"road": "r2", "name": "Road two", "parent": "r1", "houses": [hid(3)]}), ("file", {"house": hid(1), "road": "r1"}),
        ("rename_road", {"road": "r1", "name": "New"}), ("move_road", {"road": "r2", "parent": "r1"}), ("undo", {"seq": 1}),
        ("set_rule", {"max": 40, "min": 10, "auto": False})]


@pytest.mark.parametrize("kind, payload", GOOD, ids=[k for k, _ in GOOD])
def test_each_kind_of_event_is_taken_with_its_payload_and_written_in_the_same_order(kind, payload):
    out, found = checked(ev.check_event, event(kind, dict(reversed(list(payload.items())))), "event")
    assert found == [] and list(out) == ["seq", "at", "kind", "payload"] and list(out["payload"]) == list(ev.PAYLOAD_KEYS[kind])
    assert out["payload"] == payload or kind == "add_item"


def test_the_kinds_are_the_seven_of_the_page():
    assert ev.KINDS == ("add_item", "open_road", "file", "rename_road", "move_road", "undo", "set_rule") and set(ev.PAYLOAD_KEYS) == set(ev.KINDS)


@pytest.mark.parametrize("make, fragment", [
    (lambda: [], "must be an object"),
    (lambda: {"seq": 1, "at": "2026-10-26", "kind": "file"}, "missing payload"),
    (lambda: event("file", {"house": "a", "road": "b"}, seq=0), "1 or more"),
    (lambda: event("file", {"house": "a", "road": "b"}, seq="1"), "whole number"),
    (lambda: event("file", {"house": "a", "road": "b"}, at="yesterday"), "not an ISO 8601"),
    (lambda: event("file", {"house": "a", "road": "b"}, at=""), "must not be empty"),
    (lambda: event("sweep", {}), "not a kind of event"),
    (lambda: event("file", {"house": "a"}), "missing road"),
    (lambda: event("file", {"house": "a", "road": "b", "extra": 1}), "unknown extra"),
    (lambda: event("file", []), "must be an object"),
    (lambda: event("add_item", {"item": {"id": "a"}}), "missing title"),
    (lambda: event("open_road", {"road": "r", "name": "N", "parent": None, "houses": []}), "not empty"),
    (lambda: event("open_road", {"road": "r", "name": "N", "parent": None, "houses": ["a", "a"]}), "chosen twice"),
    (lambda: event("open_road", {"road": "r", "name": "  ", "parent": None, "houses": ["a"]}), "must not be empty"),
    (lambda: event("open_road", {"road": "lane:x:2", "name": "N", "parent": None, "houses": ["a"]}), "continuation rib"),
    (lambda: event("open_road", {"road": "auto:7", "name": "N", "parent": None, "houses": ["a"]}), "starts with 'auto:'"),
    (lambda: event("open_road", {"road": "r", "name": "N", "parent": 5, "houses": ["a"]}), "must be a string"),
    (lambda: event("move_road", {"road": "r", "parent": None}), "must be a string"),
    (lambda: event("rename_road", {"road": "r", "name": ""}), "must not be empty"),
    (lambda: event("undo", {"seq": 0}), "number of an event"),
    (lambda: event("undo", {"seq": "3"}), "number of an event"),
    (lambda: event("set_rule", {"max": 5, "min": 6, "auto": False}), "more than max"),
])
def test_an_event_of_the_wrong_shape_is_refused_with_its_place(make, fragment):
    out, found = checked(ev.check_event, make(), "event")
    assert out is None and any(fragment in line for line in found), found
    assert all(line.startswith("event") for line in found)


def test_a_road_id_may_start_with_auto_only_when_it_names_a_road_that_already_exists():
    assert checked(ev.check_event, event("file", {"house": "a", "road": "auto:7"}), "event")[1] == []  # the rule opens such a road, and a player can file onto it
    assert checked(ev.check_event, event("rename_road", {"road": "auto:7.2", "name": "N"}), "event")[1] == []


# ---------------------------------------------------------------------------------------------- what counts ----
def log(*kinds_and_targets):
    """A log of undo and non-undo events: ('x') is an event of no importance, ('undo', n) an undo of event n."""
    out = []
    for i, k in enumerate(kinds_and_targets, start=1):
        out.append(event("undo", {"seq": k[1]}, seq=i) if isinstance(k, tuple) else event("rename_road", {"road": "r", "name": str(k)}, seq=i))
    return out


def test_every_event_counts_until_an_undo_names_it():
    assert ev.standing(log("a", "b", "c")) == {1, 2, 3}
    assert ev.standing(log("a", "b", ("undo", 2))) == {1, 3}  # (the undo is an event that counts itself)
    assert ev.standing(log("a", "b", ("undo", 1))) == {2, 3}
    assert ev.standing([]) == set()


def test_an_undo_of_an_undo_gives_the_first_event_back_and_so_on_down_the_line():
    assert ev.standing(log("a", ("undo", 1), ("undo", 2))) == {1, 3}  # the first counts again, and the first undo does not
    assert ev.standing(log("a", ("undo", 1), ("undo", 2), ("undo", 3))) == {2, 4}  # taken away again
    assert ev.standing(log("a", "b", ("undo", 2), ("undo", 1), ("undo", 3))) == {2, 4, 5}


def test_references_are_the_roads_and_the_houses_a_payload_names_other_than_the_road_it_creates():
    assert ev.references(event("open_road", {"road": "new", "name": "N", "parent": "p", "houses": ["a", "b"]})) == ({"p"}, {"a", "b"})
    assert ev.references(event("open_road", {"road": "new", "name": "N", "parent": None, "houses": ["a"]})) == (set(), {"a"})
    assert ev.references(event("file", {"house": "a", "road": "r"})) == ({"r"}, {"a"})
    assert ev.references(event("rename_road", {"road": "r", "name": "N"})) == ({"r"}, set())
    assert ev.references(event("move_road", {"road": "r", "parent": "p"})) == ({"r", "p"}, set())
    for kind, payload in (("add_item", {"item": item(1)}), ("undo", {"seq": 1}), ("set_rule", {"max": 40, "min": 10, "auto": False})):
        assert ev.references(event(kind, payload)) == (set(), set())


def test_the_clock_of_the_examples_grows_so_a_test_can_tell_log_order_from_the_clock():
    assert stamp(1) < stamp(2) < stamp(11)
