"""The journal (bibliopolis.journal): the one way an event enters a world, and what it keeps and what it gives back."""

import copy
import json

import pytest
from hand_support import Hand, hid, item, scripted, scripted_merge, scripted_nodes, stamp, topic

from bibliopolis import hand
from bibliopolis import layout as lay
from bibliopolis.events import KINDS, Refusal
from bibliopolis.journal import Journal, dumps_world, read_world, world_document


def test_a_journal_starts_with_the_rule_40_10_and_auto_off_or_the_one_it_is_given():
    assert Journal().rule == {"max": 40, "min": 10, "auto": False} and Journal().events == []
    assert Journal({"max": 12, "min": 4, "auto": True}).rule == {"max": 12, "min": 4, "auto": True}
    for bad in ({"max": 3, "min": 4, "auto": False}, {"max": 3}, [], {"max": 3, "min": 1, "auto": 0}):
        with pytest.raises(Refusal):
            Journal(bad)


def test_an_event_is_kept_with_its_number_and_in_the_order_of_its_kind_and_a_refused_one_is_not_kept():
    j = Journal()
    event = j.append("add_item", {"item": item(1, topic(1, 1, 1, 1))}, stamp(1))
    assert event == {"seq": 1, "at": stamp(1), "kind": "add_item", "payload": {"item": item(1, topic(1, 1, 1, 1))}} and j.events == [event]
    with pytest.raises(Refusal, match=r"event\.payload\.item\.title"):
        j.append("add_item", {"item": {"id": "x", "authors": [], "year": None, "type": "article", "title": 5}}, stamp(2))
    with pytest.raises(Refusal, match="not a kind of event"):
        j.append("sweep", {}, stamp(3))
    with pytest.raises(Refusal, match="is a house already"):
        j.append("add_item", {"item": item(1)}, stamp(4))
    assert len(j.events) == 1 and list(j.state.items) == [hid(1)]
    assert j.append("add_item", {"item": item(2)}, stamp(5))["seq"] == 2


def test_the_event_a_journal_keeps_is_a_copy_in_canonical_order_not_the_dict_that_was_given():
    j = Journal()
    given = {"item": {"type": "article", "year": 1999, "authors": ["A"], "title": "T", "id": "z"}}
    event = j.append("add_item", given, stamp(1))
    assert list(event["payload"]["item"]) == ["id", "title", "authors", "year", "doi", "type", "openalex"]
    given["item"]["authors"].append("B")
    assert j.events[0]["payload"]["item"]["authors"] == ["A"]


def test_a_list_that_the_caller_goes_on_changing_does_not_change_the_road_that_was_opened():
    j = Journal({"max": 40, "min": 3, "auto": False})
    for i in range(1, 6):
        j.append("add_item", {"item": item(i)}, stamp(i))
    houses = [hid(1), hid(2), hid(3)]
    event = j.append("open_road", {"road": "a", "name": "A", "parent": None, "houses": houses}, stamp(10))
    houses.append("absent")  # the caller reuses its list
    houses[0] = "another"
    assert event["payload"]["houses"] == [hid(1), hid(2), hid(3)] and j.events[-1] is event
    again = Journal.replay(j.rule, j.events)  # the log still replays: it was never changed
    assert lay.render(again.state.city()) == lay.render(j.state.city())


def test_a_list_that_the_caller_goes_on_changing_does_not_change_the_merge_that_was_made():
    j = Journal({"max": 40, "min": 3, "auto": False})
    for i in range(1, 10):
        j.append("add_item", {"item": item(i)}, stamp(i))
    for n, road in enumerate(("a", "b", "c")):
        j.append("open_road", {"road": road, "name": road.upper(), "parent": None, "houses": [hid(3 * n + 1), hid(3 * n + 2), hid(3 * n + 3)]}, stamp(20 + n))
    members = ["a", "b"]
    event = j.append("merge_roads", {"road": "m", "name": "M", "parent": None, "members": members}, stamp(30))
    members.append("c")
    members[0] = "absent"
    assert event["payload"]["members"] == ["a", "b"]
    again = Journal.replay(j.rule, j.events)
    assert lay.render(again.state.city()) == lay.render(j.state.city())


def containers(value, path="payload"):
    """Every list and dict inside `value`, with its place."""
    if isinstance(value, (list, dict)):
        yield path, value
        for key, child in value.items() if isinstance(value, dict) else enumerate(value):
            yield from containers(child, f"{path}[{key!r}]")


def test_no_list_or_dict_that_a_payload_is_made_of_is_shared_with_the_event_that_is_kept_for_any_kind_of_event():
    """Every event of the scripted worlds is appended again to a new journal with a payload of its own; whatever list or dict of it the journal keeps must be a copy."""
    seen = set()
    for world in (scripted, scripted_nodes, scripted_merge):
        source = world().journal
        fresh = Journal(source.rule)
        for e in source.events:
            payload = copy.deepcopy(e["payload"])
            given = {id(value): place for place, value in containers(payload)}
            kept = fresh.append(e["kind"], payload, e["at"])
            assert [place for place, value in containers(kept["payload"]) if id(value) in given] == [], e["kind"]
            seen.add(e["kind"])
    assert seen == set(KINDS)


def test_a_world_file_that_is_read_and_changed_afterwards_does_not_change_the_world_that_was_read():
    doc = world_document(scripted_merge().journal)
    text = dumps_world(doc)
    parsed = json.loads(text)
    journal = read_world(parsed)
    for e in parsed["events"]:  # the reader's own document is changed in every list it has
        for value in e["payload"].values():
            if isinstance(value, list):
                value.append("absent")
    assert dumps_world(world_document(journal)) == text


def test_the_items_are_those_of_the_add_item_events_in_log_order_the_undone_ones_too():
    h = Hand()
    h.add(3)
    h.undo(2)
    h.add(1)
    assert [i["id"] for i in h.journal.items()] == [hid(1), hid(2), hid(3), hid(4)] and list(h.state.items) == [hid(1), hid(3), hid(4)]


def test_a_log_is_replayed_event_by_event_under_the_rules_of_append():
    h = Hand()
    h.add(12)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    h.file(hid(11), "a")
    again = Journal.replay(h.journal.rule, h.journal.events)
    assert again.events == h.journal.events and lay.render(again.state.city()) == lay.render(h.state.city())
    skipped = [{**e, "seq": e["seq"] + (1 if e["seq"] > 5 else 0)} for e in h.journal.events]
    with pytest.raises(Refusal, match="event 7 comes in place 6"):
        Journal.replay(h.journal.rule, skipped)
    bad = [dict(e) for e in h.journal.events]
    bad[-1] = {**bad[-1], "payload": {"house": hid(11), "road": "nowhere"}}
    with pytest.raises(Refusal, match=r"event 14 \(file\): there is no road 'nowhere'"):
        Journal.replay(h.journal.rule, bad)


def test_a_fault_in_the_engine_in_the_middle_of_an_event_leaves_the_journal_as_it_was(monkeypatch):
    h = Hand()
    h.add(12)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    before = (list(h.journal.events), lay.render(h.state.city(with_coast=False)), dict(h.state.road_of))
    original = hand.State.do_file

    def half_done(self, e, p):
        self.road_of[p["house"]] = p["road"]  # the world half changed ...
        raise RuntimeError("a fault")  # ... and then the engine fails

    monkeypatch.setattr(hand.State, "do_file", half_done)
    with pytest.raises(RuntimeError, match="a fault"):
        h.file(hid(11), "a")
    monkeypatch.setattr(hand.State, "do_file", original)
    assert (h.journal.events, lay.render(h.journal.state.city(with_coast=False)), dict(h.journal.state.road_of)) == before  # the state was folded again from the log
    h.file(hid(11), "a")
    assert h.state.road_of[hid(11)] == "a"


def thirteen_avenues_and_a_fourteenth():
    """A log of 13 ring-1 roads, and the event that would open a 14th: the events as a list (the 14th is not in any journal, a journal would not take it)."""
    h = Hand()
    for k in range(13):
        h.add(10)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    h.add(10)
    fourteenth = {"seq": len(h.journal.events) + 1, "at": stamp(500), "kind": "open_road",
                  "payload": {"road": "r13", "name": "Road 13", "parent": None, "houses": h.state.houses_at(None)}}
    return h.journal, [*h.journal.events, fourteenth]


def test_the_id_of_a_refusal_survives_the_replay_and_the_fold_of_a_log_that_the_world_would_not_take():
    journal, log = thirteen_avenues_and_a_fourteenth()
    assert log[-1]["seq"] == 154  # 13 roads of 10 houses and an open_road each, and ten houses more
    message = ("event 154 (open_road): the first ring has at most 13 avenues and all 13 directions are used, so the 14th category goes below an avenue, "
               "or similar avenues are merged under a new one (merge_roads) to free their directions")
    for refuse in (lambda: Journal.replay(journal.rule, log), lambda: hand.fold(log, journal.rule)):
        with pytest.raises(Refusal) as why:
            refuse()
        assert str(why.value) == message and (why.value.code, why.value.params) == ("ring1_full", {"limit": 13, "number": 14, "remedy": "merge_roads"})
    with pytest.raises(Refusal) as why:
        journal.append(log[-1]["kind"], log[-1]["payload"], log[-1]["at"])
    assert str(why.value) == message.split(": ", 1)[1] and why.value.code == "ring1_full"
