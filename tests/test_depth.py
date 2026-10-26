"""How deep a road may stand (bibliopolis.events.RING_LIMIT: ring 64, an avenue being ring 1, the limit the engine takes of a library's tree too). The engine walks the roads ring by ring,
so a chain of roads that is deep enough once ran out of stack in the middle of an event, with the road in the world and the event not in the log. Now an event that would put a road
below the limit is refused by the id `too_deep` before anything changes, and a chain as deep as the limit is taken, folded again, undone and written with most of the stack to spare."""

import copy
import json
import sqlite3
import sys
from contextlib import closing

import pytest
from hand_support import Hand, hand_problems, hid, stamp, topic

from bibliopolis import layout as lay
from bibliopolis import picture
from bibliopolis.events import RING_LIMIT, Refusal
from bibliopolis.hand import fold
from bibliopolis.inputs import read_city
from bibliopolis.journal import Journal, WorldFileError, dumps_world, read_world, world_document
from bibliopolis.store import Store
from bibliopolis.suggest import crowded, suggest_merge, suggest_road

DOMAIN_1 = {"id": "ex:d1", "level": "domain", "name": "Domain 1"}


def chain(h, first, depth, house, prefix="r"):
    """Roads `<prefix>1` to `<prefix><depth>`, the first below `first` (a road, or None for the town hall), each opened below the one before with the one `house`, which goes down the
    chain with them. Returns the id of the last."""
    parent = first
    for d in range(1, depth + 1):
        h.open(f"{prefix}{d}", f"Road {prefix}{d}", parent, [house])
        parent = f"{prefix}{d}"
    return parent


def a_chain(depth):
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(1)
    chain(h, None, depth, hid(1))
    return h


def ring_of(state, road):
    """The ring a road stands in, counted up the parents (not by the engine)."""
    n = 1
    while state.nodes[road]["parent"] is not None:
        road, n = state.nodes[road]["parent"], n + 1
    return n


def everything(h):
    """All that an event may change in a journal and its world, as a value to compare before and after."""
    s = h.state
    return copy.deepcopy((h.journal.events, s.rule, s.nodes, s.items, s.road_of, s.held, s.kinds, s.effects, s.plan, s.doc))


def stack_depth():
    frame, n = sys._getframe(), 0
    while frame is not None:
        frame, n = frame.f_back, n + 1
    return n


# ------------------------------------------------------------------------------------------ the limit ----
def test_the_limit_is_ring_64_as_for_the_tree_of_a_library():
    from bibliopolis.inputs import MAX_DEPTH

    assert RING_LIMIT == MAX_DEPTH == 64


def test_a_chain_of_roads_as_deep_as_the_limit_is_taken_and_every_way_to_read_it_again_gives_the_same_world():
    h = a_chain(RING_LIMIT)
    j, city = h.journal, lay.render(h.state.city())
    assert len(h.state.nodes) == RING_LIMIT and ring_of(h.state, f"r{RING_LIMIT}") == RING_LIMIT and hand_problems(h.state) == []
    assert lay.render(fold(j.events, j.rule).city()) == city
    assert lay.render(Journal.replay(j.rule, j.events).state.city()) == city
    text = dumps_world(world_document(j))
    assert dumps_world(world_document(read_world(json.loads(text)))) == text
    assert picture.render(read_city(json.loads(city)), None, size=400).startswith("<svg ")
    assert [e["seq"] for e in j.events] == list(range(1, RING_LIMIT + 2))


def test_the_deepest_chain_needs_a_few_hundred_frames_of_the_stack_and_leaves_the_rest_to_the_caller():
    """Built, folded again, undone and read as a world file with only 400 frames above the caller's: the limit is the one for which that is true on any caller."""
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(stack_depth() + 400)
    try:
        h = a_chain(RING_LIMIT)
        h.undo()
        j = Journal.replay(h.journal.rule, h.journal.events)
        again = read_world(json.loads(dumps_world(world_document(j))))
        assert lay.render(again.state.city()) == lay.render(h.state.city())
    finally:
        sys.setrecursionlimit(before)


def test_the_road_one_ring_too_deep_is_refused_by_id_before_anything_changes_and_the_world_goes_on():
    h = a_chain(RING_LIMIT)
    before, city = everything(h), lay.render(h.state.city())
    with pytest.raises(Refusal) as why:
        h.open(f"r{RING_LIMIT + 1}", "Too deep", f"r{RING_LIMIT}", [hid(1)])
    assert (why.value.code, why.value.params) == ("too_deep", {"road": f"r{RING_LIMIT + 1}", "ring": RING_LIMIT + 1, "limit": RING_LIMIT})
    assert str(why.value) == f"the road 'r{RING_LIMIT + 1}' would put a road in ring {RING_LIMIT + 1}; the most the engine takes is ring {RING_LIMIT}"
    assert everything(h) == before and lay.render(h.state.city()) == city
    assert f"r{RING_LIMIT + 1}" not in h.state.nodes
    h.rename(f"r{RING_LIMIT}", "Renamed")  # the world goes on, and an undo that folds the whole log again works
    h.undo()
    assert lay.render(fold(h.journal.events, h.journal.rule).city()) == lay.render(h.state.city())


def test_a_road_that_is_not_in_a_chain_is_refused_the_same_way_below_the_deepest_road_and_taken_one_ring_higher():
    h = a_chain(RING_LIMIT)
    h.add(2)
    h.file(hid(2), f"r{RING_LIMIT - 1}")
    h.file(hid(3), f"r{RING_LIMIT}")
    h.open("side", "Side", f"r{RING_LIMIT - 1}", [hid(2)])  # ring 64 below the road of ring 63: taken
    assert ring_of(h.state, "side") == RING_LIMIT
    before = everything(h)
    with pytest.raises(Refusal) as why:
        h.open("deeper", "Deeper", "side", [hid(2)])
    assert why.value.code == "too_deep" and why.value.params["road"] == "deeper" and everything(h) == before


@pytest.mark.parametrize(("height", "taken"), [(RING_LIMIT - 40, True), (RING_LIMIT - 40 + 1, False)])
def test_a_road_with_roads_below_it_moves_where_its_deepest_road_still_stands_in_the_limit_and_not_deeper(height, taken):
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(2)
    chain(h, None, 40, hid(1), "a")  # a1 to a40: a40 is in ring 40
    chain(h, None, height, hid(2), "b")  # b1 is an avenue, its chain `height` rings deep
    before = everything(h)
    if taken:
        h.move("b1", "a40")  # b1 in ring 41, the last of its chain in ring 40 + height
        assert ring_of(h.state, f"b{height}") == RING_LIMIT and hand_problems(h.state) == []
        return
    with pytest.raises(Refusal) as why:
        h.move("b1", "a40")
    assert (why.value.code, why.value.params) == ("too_deep", {"road": "b1", "ring": RING_LIMIT + 1, "limit": RING_LIMIT})
    assert everything(h) == before  # b1 still holds its direction, and nothing was put again


@pytest.mark.parametrize(("depth", "taken"), [(RING_LIMIT - 1, True), (RING_LIMIT, False)])
def test_a_merge_puts_every_road_of_the_members_one_ring_down_and_is_refused_where_that_passes_the_limit(depth, taken):
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(2)
    chain(h, None, depth, hid(1), "a")  # the avenue a1 with a chain of `depth` rings
    chain(h, None, 1, hid(2), "b")
    before = everything(h)
    if taken:
        h.merge("m", "M", ["a1", "b1"])
        assert ring_of(h.state, f"a{depth}") == RING_LIMIT and hand_problems(h.state) == []
        return
    with pytest.raises(Refusal) as why:
        h.merge("m", "M", ["a1", "b1"])
    assert (why.value.code, why.value.params) == ("too_deep", {"road": "m", "ring": RING_LIMIT + 1, "limit": RING_LIMIT})
    assert everything(h) == before and "m" not in h.state.nodes


def test_the_rule_auto_leaves_a_place_crowded_that_has_no_ring_left_below_it():
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(1, topic(1, 1, 1, 1))
    last = chain(h, None, RING_LIMIT - 1, hid(1))
    h.open("deepest", "Domain 1", last, [hid(1)], DOMAIN_1)  # the road of ring 64 stands for a domain: the rule would split it by field
    h.rule(5, 1, True)
    h.add(6, topic(1, 1, 1, 1))  # 7 houses on it, above the 5 it is meant to hold
    state = h.state
    assert state.rule["auto"] and state.count("deepest") == 7 and max(ring_of(state, k) for k in state.nodes) == RING_LIMIT
    assert not [k for k in state.nodes if k.startswith("auto:")]
    assert crowded(state) == [{"at": "deepest", "name": "Domain 1", "houses": 7}]
    assert hand_problems(state) == []


def a_domain_road_in_ring(ring):
    """A road that stands for the domain 1, in the ring `ring`, with one house under it that a field road could take."""
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(1, topic(1, 1, 1, 1))
    last = chain(h, None, ring - 1, hid(1))
    h.open("deep", "Domain 1", last, [hid(1)], DOMAIN_1)
    return h


def test_no_road_is_suggested_below_the_last_ring_and_one_ring_higher_it_is():
    suggestion = suggest_road(a_domain_road_in_ring(RING_LIMIT - 1).state, "deep")
    assert suggestion is not None and suggestion["topic"]["level"] == "field"  # (the control: a ring is left below this one)
    assert suggest_road(a_domain_road_in_ring(RING_LIMIT).state, "deep") is None


def two_fields(depth):
    """Two avenues that stand for two fields of one domain, the first with a chain of `depth` roads below it."""
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(1, topic(1, 1, 1, 1))
    h.add(1, topic(1, 2, 1, 1))
    h.open("f1", "Field 1.1", None, [hid(1)], {"id": "ex:d1.f1", "level": "field", "name": "Field 1.1"})
    h.open("f2", "Field 1.2", None, [hid(2)], {"id": "ex:d1.f2", "level": "field", "name": "Field 1.2"})
    chain(h, "f1", depth, hid(1), "c")
    return h


@pytest.mark.parametrize(("depth", "suggested"), [(RING_LIMIT - 2, True), (RING_LIMIT - 1, False)])
def test_no_merge_is_suggested_that_would_put_a_road_below_the_last_ring_by_sibling_nodes_or_by_likeness(depth, suggested):
    h = two_fields(depth)  # the last road of the chain is in ring depth + 1; the merge would put it one ring down
    suggestion = suggest_merge(h.state)
    assert (suggestion is not None) == suggested
    if suggested:
        assert suggestion["by"] == "parent_node" and suggestion["members"] == ["f1", "f2"]
        h.take_merge(suggestion, "m")  # ... and the world takes what is suggested
        assert max(ring_of(h.state, k) for k in h.state.nodes) == RING_LIMIT
    plain = Hand({"max": 40, "min": 1, "auto": False})  # the same by likeness: avenues with no node, houses with a topic in common
    plain.add(2, topic(1, 1, 1, 1))
    chain(plain, None, depth + 1, hid(1), "a")
    plain.open("b", "B", None, [hid(2)])
    assert (suggest_merge(plain.state) is not None) == suggested
    if suggested:
        assert suggest_merge(plain.state)["by"] == "similar_houses"
        plain.take_merge(suggest_merge(plain.state), "m")


def test_an_undo_after_which_a_road_would_stand_too_deep_is_refused_as_unfoldable_with_the_id_of_the_cause():
    h = Hand({"max": 40, "min": 1, "auto": False})
    h.add(2)
    chain(h, None, 40, hid(1), "a")
    moved = h.move("a20", "a1")  # a40 is in ring 22 now
    h.file(hid(2), "a40")
    chain(h, "a40", 42, hid(2), "z")  # z42 is in ring 64
    before = everything(h)
    with pytest.raises(Refusal) as why:
        h.undo(moved["seq"])  # without the move a40 is in ring 40, and z25 would be in ring 65
    assert why.value.code == "undo_unfoldable" and (why.value.params["cause"], why.value.params["kind"]) == ("too_deep", "open_road")
    assert why.value.params["cause_params"] == {"road": "z25", "ring": RING_LIMIT + 1, "limit": RING_LIMIT}
    assert everything(h) == before


# ---------------------------------------------------------------------------- a world file or a store with a chain too deep ----
def one_too_deep(h):
    return {"seq": len(h.journal.events) + 1, "at": stamp(500), "kind": "open_road",
            "payload": {"road": f"r{RING_LIMIT + 1}", "name": "Too deep", "parent": f"r{RING_LIMIT}", "houses": [hid(1)], "topic": None}}


def test_a_world_file_that_holds_a_chain_one_ring_too_deep_is_refused_with_the_id_and_the_place():
    h = a_chain(RING_LIMIT)
    doc = json.loads(dumps_world(world_document(h.journal)))
    doc["events"].append(one_too_deep(h))
    with pytest.raises(WorldFileError) as why:
        read_world(doc)
    assert (why.value.code, why.value.params) == ("too_deep", {"road": f"r{RING_LIMIT + 1}", "ring": RING_LIMIT + 1, "limit": RING_LIMIT})
    assert (why.value.event, why.value.where) == ({"seq": RING_LIMIT + 2, "kind": "open_road"}, f"world.events[{RING_LIMIT + 1}]")


def test_a_store_that_holds_a_chain_one_ring_too_deep_is_refused_with_the_id_and_the_file(tmp_path):
    h = a_chain(RING_LIMIT)
    path = tmp_path / "w.sqlite"
    Store.import_journal(path, h.journal)
    event = one_too_deep(h)
    with closing(sqlite3.connect(path)) as db, db:  # a row put in by hand
        db.execute("INSERT INTO event VALUES (?, ?, ?, ?)", (event["seq"], event["at"], event["kind"], json.dumps(event["payload"])))
    with pytest.raises(WorldFileError) as why:
        Store(path).journal()
    assert why.value.code == "too_deep" and why.value.event == {"seq": event["seq"], "kind": "open_road"} and why.value.where == str(path)
