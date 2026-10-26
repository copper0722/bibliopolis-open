"""The journal (bibliopolis.journal): the one way an event enters a world, and what it keeps and what it gives back."""

import copy
import errno
import json

import pytest
from hand_support import Hand, hid, item, journal_value, scripted, scripted_merge, scripted_nodes, stamp, topic

from bibliopolis import hand
from bibliopolis import journal as journal_module
from bibliopolis import layout as lay
from bibliopolis.events import KINDS, Refusal
from bibliopolis.hand import HandWorld, State
from bibliopolis.journal import Journal, dumps_world, read_world, world_document


def test_a_journal_starts_with_the_rule_40_10_and_auto_off_or_the_one_it_is_given():
    assert Journal().rule == {"max": 40, "min": 10, "auto": False, "branches": 13} and Journal().events == []
    assert Journal({"max": 12, "min": 4, "auto": True}).rule == {"max": 12, "min": 4, "auto": True, "branches": 13}
    assert Journal({"max": 12, "min": 4, "auto": True, "branches": 21}).rule == {"max": 12, "min": 4, "auto": True, "branches": 21}
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
    assert event["payload"]["houses"] == [hid(1), hid(2), hid(3)] and j.events[-1] == event
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


def test_the_event_append_returns_is_a_copy_that_shares_nothing_with_the_log_and_changing_it_changes_nothing():
    """What `append` gives back used to be the event of the log itself: a caller who set a key or emptied a list of it changed the log. Every event of the scripted worlds is appended to a
    new journal; what comes back equals the event in the log, is not it, shares no list or dict with it, and is changed all over without changing the log."""
    seen = set()
    for world in (scripted, scripted_nodes, scripted_merge):
        source = world().journal
        fresh = Journal(source.rule)
        for e in source.events:
            returned = fresh.append(e["kind"], copy.deepcopy(e["payload"]), e["at"])
            kept = fresh.events[-1]
            assert returned == kept == e and returned is not kept, e["kind"]
            in_the_log = {id(value) for _, value in containers(kept)}
            assert [place for place, value in containers(returned) if id(value) in in_the_log] == [], e["kind"]
            for _, value in list(containers(returned)):  # change what came back, all over
                value.clear()
            returned["seq"] = 0
            assert kept == e, e["kind"]
            seen.add(e["kind"])
        again = Journal.replay(source.rule, fresh.events)
        assert lay.render(again.state.city()) == lay.render(source.state.city())
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
    assert (h.journal.events, lay.render(h.journal.state.city(with_coast=False)), dict(h.journal.state.road_of)) == before  # the state was put back as it was
    h.file(hid(11), "a")
    assert h.state.road_of[hid(11)] == "a"


# ------------------------------------------------------------------------------------------ all or nothing ----
def a_world_where_every_kind_of_event_can_come_next():
    h = Hand({"max": 6, "min": 2, "auto": False})
    h.add(9, topic(1, 1, 1, 1))
    h.add(4, topic(2, 1, 1, 1))
    h.open("a", "A", None, [hid(i) for i in range(1, 5)])
    h.open("b", "B", None, [hid(i) for i in range(10, 13)])
    h.file(hid(5), "a")
    h.file(hid(6), "a")
    h.open("a1", "A one", "a", [hid(5), hid(6)])
    h.rule(6, 2, True)
    return h


NEXT = {
    "add_item": lambda h: {"item": item(99, topic(1, 1, 1, 1))},
    "open_road": lambda h: {"road": "c", "name": "C", "parent": None, "houses": [hid(7), hid(8)]},
    "file": lambda h: {"house": hid(9), "road": "b"},
    "rename_road": lambda h: {"road": "a", "name": "Alpha"},
    "move_road": lambda h: {"road": "a1", "parent": "b"},
    "merge_roads": lambda h: {"road": "m", "name": "M", "parent": None, "members": ["a", "b"]},
    "undo": lambda h: {"seq": len(h.journal.events)},
    "set_rule": lambda h: {"max": 9, "min": 3, "auto": True, "branches": 13},
}
AT = "2026-10-26T12:00:00Z"
PLACING = ("add_item", "open_road", "file", "move_road", "merge_roads")  # the kinds that put houses on a road
FAULTS = {  # a place in the engine, the error it fails with once it has done its work, and the kinds of event that go through it
    "after the houses are placed": (HandWorld, "add_houses", RuntimeError("a fault"), PLACING),
    "when the document is to be committed": (State, "commit", RuntimeError("a fault"), KINDS),
    "after the whole event is applied": (State, "apply", RuntimeError("a fault"), KINDS),
    "an interrupt in the middle": (State, "commit", KeyboardInterrupt(), KINDS),
    "the stack runs out": (State, "commit", RecursionError("maximum recursion depth exceeded"), KINDS),
}
PAIRS = [(kind, fault) for fault, (*_, kinds) in FAULTS.items() for kind in kinds]


def fail_after(cls, name, error, *, first=False):
    """The method `name` of `cls` as it is, and failing with `error` after it has done its work (`first`: before it does any)."""
    real = getattr(cls, name)

    def failing(*args, **kw):
        if first:
            raise error
        real(*args, **kw)
        raise error

    return failing


def fails_in_the_middle(kind, fault):
    """Take the event `kind` in a world with `fault` planted (the fault is gone after): returns the journal, its value before, and the objects that must still be the journal's."""
    h = a_world_where_every_kind_of_event_can_come_next()
    before, state, nodes = journal_value(h.journal), h.state, h.state.nodes
    cls, name, error, _ = FAULTS[fault]
    with pytest.MonkeyPatch.context() as plant:
        plant.setattr(cls, name, fail_after(cls, name, error))
        with pytest.raises(type(error)):
            h.journal.append(kind, copy.deepcopy(NEXT[kind](h)), AT)
    return h, before, (state, nodes)


def is_changed_by(kind, fault):
    """Whether the journal is different after the event `kind` failed with `fault` from what it was before."""
    h, before, _ = fails_in_the_middle(kind, fault)
    return journal_value(h.journal) != before


@pytest.mark.parametrize(("kind", "fault"), PAIRS)
def test_an_event_that_fails_in_the_middle_leaves_the_journal_exactly_as_it_was(kind, fault):
    """Whatever the engine does before it fails, or however: a fault, an interrupt, the stack running out. The log, the rule, the roads, the houses, the directions, the plan and the
    document are equal to what they were, the State is the same object (whoever holds it holds the journal's) and its live tree still reads its roads; and the journal goes on as one
    that never failed."""
    h, before, (state, nodes) = fails_in_the_middle(kind, fault)
    assert journal_value(h.journal) == before
    assert h.journal.state is state and state.nodes is nodes and state.tree.nodes is nodes
    control = a_world_where_every_kind_of_event_can_come_next()
    h.journal.append(kind, copy.deepcopy(NEXT[kind](h)), AT)
    control.journal.append(kind, copy.deepcopy(NEXT[kind](control)), AT)
    assert h.journal.events == control.journal.events and lay.render(h.state.city()) == lay.render(control.state.city())


@pytest.mark.parametrize("kind", KINDS)
def test_a_log_that_cannot_take_the_event_after_the_world_took_it_leaves_the_journal_as_it_was(kind):
    class FullDisk(list):
        def append(self, event):
            raise OSError(errno.ENOSPC, "No space left on device")

    h = a_world_where_every_kind_of_event_can_come_next()
    before, kept = journal_value(h.journal), h.journal.events
    h.journal.events = FullDisk(kept)
    with pytest.raises(OSError, match="No space left"):
        h.journal.append(kind, NEXT[kind](h), AT)
    h.journal.events = list(h.journal.events)
    assert journal_value(h.journal) == before


@pytest.mark.parametrize("kind", KINDS)
def test_a_copy_of_the_event_that_cannot_be_made_leaves_the_journal_as_it_was(kind, monkeypatch):
    """The copy that `append` gives back is made before anything changes: a failure to make it (no memory) used to come after the commit, with the event in the log and the world changed."""
    h = a_world_where_every_kind_of_event_can_come_next()
    before = journal_value(h.journal)

    def no_memory(value):
        raise MemoryError("no memory for a copy")

    monkeypatch.setattr(journal_module, "copy_json", no_memory)
    with pytest.raises(MemoryError):
        h.journal.append(kind, copy.deepcopy(NEXT[kind](h)), AT)
    monkeypatch.undo()
    assert journal_value(h.journal) == before
    h.journal.append(kind, copy.deepcopy(NEXT[kind](h)), AT)  # ... and the same event goes in


def test_a_restore_keeps_the_identity_of_the_state_and_its_main_dictionaries_and_replaces_the_records_the_rule_and_the_document():
    """The scope of "in place": what the journal holds is the same object after a failed event, except the records of the roads, the rule and the document, which are the copies taken before.
    A reference to a road record taken before the event is not the journal's afterwards, and still shows what the failed event did to it."""
    h = a_world_where_every_kind_of_event_can_come_next()
    state, tree = h.state, h.state.tree
    same = {name: getattr(state, name) for name in ("nodes", "items", "road_of", "plan", "held", "kinds", "effects")}
    record, rule, doc = state.nodes["a"], state.rule, state.doc
    with pytest.MonkeyPatch.context() as plant:
        plant.setattr(State, "commit", fail_after(State, "commit", RuntimeError("a fault"), first=True))
        with pytest.raises(RuntimeError):
            h.journal.append("rename_road", {"road": "a", "name": "Alpha"}, AT)  # the name is changed in the record before the commit is reached
    assert h.journal.state is state and state.tree is tree and all(getattr(state, name) is same[name] for name in same)
    assert state.nodes["a"] is not record and state.nodes["a"]["name"] == "A" and record["name"] == "Alpha"
    assert state.rule is not rule and state.rule == rule and state.doc is doc


def test_an_arrival_that_fails_after_the_rule_opened_some_roads_leaves_no_road_behind(monkeypatch):
    h = Hand({"max": 5, "min": 2, "auto": True})
    h.add(5, topic(1, 1, 1, 1))
    before, real, calls = journal_value(h.journal), State.open, []

    def the_third_fails(self, *args, **kw):
        calls.append(args[1])
        if len(calls) == 3:
            raise RuntimeError("a fault")
        return real(self, *args, **kw)

    monkeypatch.setattr(State, "open", the_third_fails)
    with pytest.raises(RuntimeError, match="a fault"):  # the sixth house takes the ring road over 5: the domain and the field are opened, the subfield is not
        h.add(1, topic(1, 1, 1, 1))
    monkeypatch.undo()
    assert len(calls) == 3 and journal_value(h.journal) == before and not h.state.nodes
    h.add(1, topic(1, 1, 1, 1))
    assert list(h.state.nodes) == ["auto:6", "auto:6.2", "auto:6.3", "auto:6.4"]


def test_the_snapshot_covers_every_attribute_of_a_state():
    state = State({"max": 40, "min": 10, "auto": False})
    assert set(vars(state)) == set(state.snapshot()) | {"tree"} and state.tree.nodes is state.nodes


@pytest.mark.parametrize("forgotten", ["rule", "nodes", "items", "road_of", "plan", "doc", "held", "kinds", "effects"])
def test_the_faults_see_a_restore_that_forgets_an_attribute_of_the_state(forgotten):
    """The proof that the table of faults has teeth: with the restore of one attribute left out (it keeps what the failed event made of it), some fault of the table leaves the journal changed."""
    real = State.restore

    def forgetting(self, saved):
        real(self, {**saved, forgotten: copy.deepcopy(getattr(self, forgotten))})

    with pytest.MonkeyPatch.context() as flaw:
        flaw.setattr(State, "restore", forgetting)
        changed = [pair for pair in PAIRS if is_changed_by(*pair)]
    assert changed, forgotten


def test_the_faults_see_a_snapshot_that_shares_the_records_of_the_roads():
    real = State.snapshot

    def sharing(self):
        saved = real(self)
        saved["nodes"] = dict(self.nodes)  # the same records, not copies: a rename or a move changes them in place
        return saved

    with pytest.MonkeyPatch.context() as flaw:
        flaw.setattr(State, "snapshot", sharing)
        changed = [pair for pair in PAIRS if is_changed_by(*pair)]
    assert {kind for kind, _ in changed} >= {"rename_road", "move_road"}


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
    message = ("event 154 (open_road): the ring road holds 13 avenues directly, the most the rule allows (branches 13), so the 14th category goes below one of them, "
               "or similar avenues are merged under a new one (merge_roads) to make room")
    for refuse in (lambda: Journal.replay(journal.rule, log), lambda: hand.fold(log, journal.rule)):
        with pytest.raises(Refusal) as why:
            refuse()
        assert str(why.value) == message and (why.value.code, why.value.params) == ("branches_full", {"road": None, "limit": 13, "number": 14, "remedy": "merge_roads"})
    with pytest.raises(Refusal) as why:
        journal.append(log[-1]["kind"], log[-1]["payload"], log[-1]["at"])
    assert str(why.value) == message.split(": ", 1)[1] and why.value.code == "branches_full"
