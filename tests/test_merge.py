"""Merging avenues (docs/world.md, "Merging avenues"): a full first ring is the moment to group upward. `merge_roads` gives a new avenue the direction of the largest of its members,
puts the members below it as roads of ring 2, and frees the directions of the others; the next avenues take the freed directions, the lowest number first. `suggest_merge` proposes
the members."""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import hand_support
import pytest
from hand_support import (
    Hand,
    direction_violations,
    hand_problems,
    hid,
    item,
    landing_violations,
    lot_snapshot,
    node,
    play,
    scripted_merge,
    stability_violations,
    text_problems,
    topic,
)

from bibliopolis import hand
from bibliopolis.city import chronicle_lines
from bibliopolis.events import Refusal
from bibliopolis.hand import AVENUES, SECTORS
from bibliopolis.suggest import roads_by_node, suggest_merge

ROOT = Path(__file__).resolve().parents[1]
T = topic


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def avenues(n=13, each=10, rule=None):
    """A town of `n` avenues r0, r1, ... (categories with no node) with `each` houses each; avenue k holds the direction number k."""
    h = Hand(rule or {"max": 40, "min": 10, "auto": False})
    for k in range(n):
        h.add(each)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    return h


def sound(h):
    """The world is sound (the engine's checks, the text of the city read again), and the log is stable, the directions are held as the rule says."""
    assert hand_problems(h.state) == [] and text_problems(h.state) == []
    assert stability_violations(h.journal.events, h.journal.rule) == [] and direction_violations(h.journal.events, h.journal.rule) == []
    return h.state


def refuses(h, code, params, *event):
    """The merge `event` (road, name, members[, node]) is refused with `code` and `params`, and the world is as it was."""
    before = (list(h.state.nodes), dict(h.state.road_of), dict(h.state.held), len(h.journal.events))
    with pytest.raises(Refusal) as why:
        h.merge(*event)
    assert (why.value.code, why.value.params) == (code, params)
    assert (list(h.state.nodes), dict(h.state.road_of), dict(h.state.held), len(h.journal.events)) == before
    assert hand_problems(h.state) == []


# --------------------------------------------------------------------------------- the directions, as a number ----
def test_an_avenue_takes_the_lowest_direction_that_no_avenue_holds_and_all_thirteen_held_refuse_the_next():
    h = avenues(13)
    assert h.state.held == {k: f"r{k}" for k in range(13)} and AVENUES == 13
    assert [(s["from"], s["to"]) for s in h.state.city()["composition"]["ring1"]] == [(lo / 100, hi / 100) for lo, hi in SECTORS]
    h.add(10)
    with pytest.raises(Refusal) as why:
        h.open("x", "X", None, h.state.houses_at(None))
    assert (why.value.code, why.value.params) == ("ring1_full", {"limit": 13, "number": 14, "remedy": "merge_roads"}) and "(merge_roads)" in str(why.value)
    sound(h)


def test_the_holder_of_a_direction_keeps_it_when_the_road_moves_away_and_only_a_merge_frees_one():
    h = avenues(13)
    h.move("r4", "r0")  # an avenue below another road: it keeps its direction
    assert h.state.held[4] == "r4" and h.state.nodes["r4"]["parent"] == "r0"
    h.add(10)
    with pytest.raises(Refusal, match="all 13 directions are used"):
        h.open("x", "X", None, h.state.houses_at(None))
    sound(h)


# ------------------------------------------------------------------------------------------------ the merge ----
def test_a_merge_gives_the_new_avenue_the_direction_of_its_largest_member_and_frees_the_others():
    h = avenues(13)
    h.add(5)
    h.file(hid(131), "r5")  # r5 has 11 houses, the others 10: the largest of the three
    before = {r["label"]: (r["from"], r["to"]) for r in h.state.city()["composition"]["ring1"]}
    h.merge("m", "Merged", ["r2", "r5", "r7"])
    state = sound(h)
    assert state.held == {**{k: f"r{k}" for k in range(13) if k not in (2, 5, 7)}, 5: "m"}  # the direction of r5; 2 and 7 are free
    after = {r["label"]: (r["from"], r["to"]) for r in state.city()["composition"]["ring1"]}
    assert after["Merged"] == before["Road 5"] and not {"Road 2", "Road 5", "Road 7"} & set(after) and len(after) == 11
    assert [state.nodes[k]["parent"] for k in ("r2", "r5", "r7")] == ["m"] * 3 and state.nodes["m"]["parent"] is None
    places = state.city()["places"]
    assert [places[f"place:tag:{k}"]["address"] for k in ("r2", "r5", "r7")] == [["Merged", "Road 2"], ["Merged", "Road 5"], ["Merged", "Road 7"]]  # roads of ring 2
    assert {places[f"place:tag:{k}"]["level"] for k in ("r2", "r5", "r7")} == {2} and places["place:tag:m"]["level"] == 1


def test_the_largest_member_has_the_most_houses_on_it_and_below_it_and_of_two_as_large_the_lower_direction():
    h = avenues(8, each=12)
    h.open("r1a", "R1 A", "r1", houses(13, 24))  # r1 has nothing of its own: its 12 houses are on the road below it
    h.add(12)
    h.file(hid(97), "r3")  # r3: 13 houses
    assert h.state.largest_avenue(["r3", "r1"]) == "r3" and h.state.largest_avenue(["r1", "r2"]) == "r1"  # 12 against 13; 12 and 12: the lower direction
    for x in houses(98, 103):
        h.file(x, "r1a")  # r1 has 18 on the road below it
    assert h.state.largest_avenue(["r3", "r1"]) == "r1" and h.state.largest_avenue(["r3", "r1", "r5"]) == "r1"
    h.merge("m", "M", ["r5", "r3", "r1"])
    assert h.state.held[1] == "m" and 3 not in h.state.held and 5 not in h.state.held
    sound(h)


def test_the_next_avenues_take_the_freed_directions_lowest_number_first_and_before_any_that_was_never_used():
    h = avenues(9)
    h.add(2)
    h.file(hid(91), "r6")
    h.merge("m", "M", ["r2", "r6", "r3"])  # r6 is the largest: the new avenue holds direction 6; 2 and 3 are free
    assert sorted(h.state.held) == [0, 1, 4, 5, 6, 7, 8] and h.state.held[6] == "m"
    taken = []
    for name in ("n1", "n2", "n3", "n4"):
        h.add(10)
        h.open(name, name.upper(), None, h.state.houses_at(None)[:10])
        taken.append(h.state.direction_of(name))
    assert taken == [2, 3, 9, 10]  # the freed ones, then the never used ones, in the golden-angle order
    assert [s["from"] for s in h.state.city()["composition"]["ring1"][-4:]] == [SECTORS[k][0] / 100 for k in (2, 3, 9, 10)]  # each has the sector and the bearing of its number
    sound(h)


def test_with_all_thirteen_held_a_merge_makes_room_for_a_fourteenth_category_and_the_ring_fills_again():
    h = avenues(13)
    h.merge("m1", "Merged 1", ["r1", "r2"])  # as large: r1 has the lower direction, so the new avenue holds 1 and 2 is free
    h.merge("m2", "Merged 2", ["r8", "r9", "r10"])  # 8 is kept; 9 and 10 are free
    assert sorted(h.state.held) == [0, 1, 3, 4, 5, 6, 7, 8, 11, 12]
    for want in (2, 9, 10):
        h.add(10)
        h.open(f"n{want}", f"New {want}", None, h.state.houses_at(None))
        assert h.state.direction_of(f"n{want}") == want  # the lowest free direction each time
    h.add(10)
    with pytest.raises(Refusal, match="all 13 directions are used"):
        h.open("again", "Again", None, h.state.houses_at(None))
    sound(h)


def test_the_members_stand_below_the_new_avenue_with_their_roads_and_only_their_houses_are_put_again():
    h = avenues(6, each=12)
    h.open("r2a", "R2 A", "r2", houses(25, 36))
    before = lot_snapshot(h.state)
    h.merge("m", "M", ["r2", "r4"])
    state = sound(h)
    after = lot_snapshot(state)
    moved = set(houses(25, 36)) | set(houses(49, 60))  # the houses of r2 (on r2a) and of r4
    changed = {x for x in before if before[x] != after[x]}
    assert changed <= moved and set(houses(49, 60)) <= changed  # no house but those of the subtrees of the members changed lot; the houses of r4 are on another line now
    # (a house of r2, the member whose direction the new avenue has, may be put again onto the very cell it stood on: the line of the new avenue is the line r2 had)
    assert state.nodes["r2a"]["parent"] == "r2" and state.nodes["r2"]["parent"] == "m"
    places = state.city()["places"]
    assert places["place:tag:r2a"]["address"] == ["M", "Road 2", "R2 A"]  # r2a is a road of ring 3 now
    carriers = {places[places[f"place:article:{x}"]["parent"]].get("carrier", places[f"place:article:{x}"]["parent"]) for x in moved}
    assert carriers == {"place:tag:m"}  # every one of them stands on a rib of the line of the new avenue


def test_the_merge_writes_one_entry_of_the_chronicle_and_a_sentence_for_it():
    h = avenues(4)
    h.add(2)
    h.file(hid(41), "r1")
    h.merge("m", "Merged", ["r3", "r1"])
    chronicle = h.state.city()["world"]["chronicle"]
    entry = chronicle[-1]
    assert list(entry) == ["n", "event_id", "seq", "trigger", "merged", "label", "members", "took", "houses", "at"]
    assert (entry["trigger"], entry["merged"], entry["label"], entry["members"], entry["took"]) == ("merge_roads", "place:tag:m", "Merged", ["place:tag:r3", "place:tag:r1"], "place:tag:r1")
    assert entry["houses"] == [*houses(11, 20), *houses(31, 41)]  # the houses of the two members and of what is below them, in the order they arrived
    assert [e["event_id"] for e in chronicle].count(entry["event_id"]) == 1
    assert chronicle_lines(h.state.city())[-1].endswith("2 avenues (Road 3, Road 1) are merged below the new avenue Merged, which takes the direction of Road 1; 21 houses are put again.")


# --------------------------------------------------------------------------------------- what the world refuses ----
def test_a_merge_is_refused_for_a_road_that_exists_a_member_that_is_not_there_and_one_that_is_not_an_avenue():
    h = avenues(4)
    h.open("r0a", "R0 A", "r0", houses(1, 10))
    refuses(h, "road_exists", {"road": "r1"}, "r1", "X", ["r2", "r3"])
    refuses(h, "no_road", {"road": "ghost"}, "m", "M", ["r2", "ghost"])
    refuses(h, "not_an_avenue", {"road": "r0a"}, "m", "M", ["r2", "r0a"])


def test_a_merge_with_a_node_is_refused_when_another_road_stands_for_it_and_when_a_house_is_not_under_it():
    h = Hand()
    for k in range(3):
        h.add(10, T(k + 1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 10), node("domain", 1))
    h.open("b", "B", None, houses(11, 20), node("domain", 2))
    h.open("c", "C", None, houses(21, 30), node("domain", 3))
    refuses(h, "node_taken", {"level": "domain", "topic": "ex:d1", "road": "a"}, "m", "M", ["b", "c"], node("domain", 1))
    refuses(h, "house_not_under_node", {"house": hid(11), "level": "domain", "topic": "ex:d9"}, "m", "M", ["b", "c"], node("domain", 9))
    sound(h)


def test_a_merge_that_names_a_node_needs_every_house_below_the_members_to_be_under_it_and_the_members_keep_their_nodes():
    h = Hand()
    h.add(10, T(1, 1, 1, 1))
    h.add(10, T(1, 2, 1, 1))
    h.add(10, T(2, 1, 1, 1))
    h.open("f1", "F1", None, houses(1, 10), node("field", 1, 1))
    h.open("f2", "F2", None, houses(11, 20), node("field", 1, 2))
    h.open("g", "G", None, houses(21, 30), node("domain", 2))
    h.merge("d1", "Domain 1", ["f1", "f2"], node("domain", 1))  # both fields of domain 1
    state = sound(h)
    assert state.nodes["d1"]["topic"] == node("domain", 1) and roads_by_node(state)[("domain", "ex:d1")] == "d1"
    assert state.nodes["f1"]["topic"] == node("field", 1, 1) and state.nodes["f2"]["topic"] == node("field", 1, 2)


# -------------------------------------------------------------------------------------------------- undo ----
def test_an_undo_of_a_merge_gives_the_avenues_and_their_directions_back_when_nothing_depends_on_it():
    h = avenues(13)
    before = lot_snapshot(h.state)
    h.merge("m", "M", ["r2", "r5"])
    h.undo(len(h.journal.events))
    assert h.state.held == {k: f"r{k}" for k in range(13)} and set(h.state.nodes) == {f"r{k}" for k in range(13)}
    assert all(h.state.nodes[f"r{k}"]["parent"] is None for k in range(13)) and lot_snapshot(h.state) == before
    h.undo(len(h.journal.events))  # an undo of an undo gives the merge back
    assert h.state.nodes["m"]["parent"] is None and h.state.nodes["r2"]["parent"] == "m"
    sound(h)


def test_a_merge_is_not_undone_while_a_later_event_names_the_new_avenue_nor_the_event_that_opened_a_member():
    h = avenues(5)
    merged = len(h.journal.events) + 1
    h.merge("m", "M", ["r1", "r2"])
    h.rename("m", "M two")
    with pytest.raises(Refusal) as why:
        h.undo(merged)
    assert why.value.code == "undo_depends" and why.value.params == {"target": merged, "later": merged + 1, "kind": "rename_road"}
    h.undo(merged + 1)  # the rename is taken back first ...
    h.undo(merged)  # ... and then the merge can go
    assert h.state.nodes["r1"]["parent"] is None
    h.undo(len(h.journal.events))  # the merge comes back
    assert h.state.nodes["r1"]["parent"] == "m"
    opened = next(e["seq"] for e in h.journal.events if e["kind"] == "open_road" and e["payload"]["road"] == "r1")
    with pytest.raises(Refusal) as why:
        h.undo(opened)  # the merge names the road that this event opened
    assert (why.value.code, why.value.params["target"], why.value.params["kind"]) == ("undo_depends", opened, "merge_roads")


def test_a_merge_is_not_undone_while_a_later_event_names_a_house_that_it_put_again():
    h = avenues(4)
    merged = len(h.journal.events) + 1
    h.merge("m", "M", ["r1", "r2"])
    h.file(hid(11), "r2")  # a house of r1, put again by the merge
    with pytest.raises(Refusal) as why:
        h.undo(merged)
    assert why.value.code == "undo_depends" and why.value.params == {"target": merged, "later": merged + 1, "kind": "file"}
    h.undo(merged + 1)
    h.undo(merged)  # the filing is taken back first: the merge goes
    assert h.state.nodes["r1"]["parent"] is None
    sound(h)


def test_a_house_the_merge_did_not_touch_filed_onto_a_member_is_no_dependency_on_the_merge():
    h = avenues(4)
    merged = len(h.journal.events) + 1
    h.merge("m", "M", ["r1", "r2"])
    h.add(1)
    h.file(hid(41), "r2")  # the merge names r2 and a later event names it too, but this house was not put again by the merge
    h.undo(merged)
    assert h.state.nodes["r1"]["parent"] is None and h.state.road_of[hid(41)] == "r2"
    sound(h)


def test_a_merge_is_not_undone_while_a_later_avenue_stands_in_a_direction_it_freed_and_the_ring_would_then_be_full():
    h = avenues(13)
    h.merge("m", "M", ["r2", "r5"])  # as large: the new avenue holds direction 2, and 5 is free
    merged = len(h.journal.events)
    h.add(10)
    h.open("n", "N", None, h.state.houses_at(None))
    assert h.state.direction_of("n") == 5
    with pytest.raises(Refusal) as why:
        h.undo(merged)  # without the merge the thirteen directions are held and N has none
    assert why.value.code == "undo_unfoldable" and why.value.params["cause"] == "ring1_full" and why.value.params["kind"] == "open_road"
    assert why.value.params["cause_params"] == {"limit": 13, "number": 14, "remedy": "merge_roads"}
    h.undo(len(h.journal.events))  # N goes first ...
    h.undo(merged)  # ... and then the merge
    assert h.state.held == {k: f"r{k}" for k in range(13)}
    sound(h)


# ------------------------------------------------------------------------------------------- suggest_merge ----
def fields_town(layout, each=6):
    """Avenues for fields, `layout` a list of (domain, field) pairs: r0, r1, ... Each holds `each` houses that carry the topic of its field (min 5)."""
    h = Hand({"max": 40, "min": 5, "auto": False})
    for k, (d, f) in enumerate(layout):
        h.add(each, T(d, f, 1, 1))
        h.open(f"r{k}", f"Field {d}.{f}", None, h.state.houses_at(None), node("field", d, f))
    return h


def test_avenues_that_stand_for_the_fields_of_one_domain_are_merged_under_that_domain():
    h = fields_town([(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (2, 2)])
    s = suggest_merge(h.state)
    assert s == {"members": ["r0", "r2", "r4"], "topic": node("domain", 1), "name": "Domain 1", "by": "parent_node", "takes": "r0", "frees": 2}  # three fields of domain 1: the most
    h.take_merge(s, "m")
    state = sound(h)
    assert state.nodes["m"]["topic"] == node("domain", 1) and state.nodes["m"]["name"] == "Domain 1" and state.held[0] == "m"  # as large: r0 holds the lowest direction
    nxt = suggest_merge(state)
    assert nxt["members"] == ["r1", "r5"] and nxt["topic"] == node("domain", 2)  # the next group: the two fields of domain 2


def test_the_group_with_the_most_avenues_comes_first_then_the_most_houses_then_the_lower_parent_id():
    h = fields_town([(1, 1), (1, 2), (2, 1), (2, 2), (2, 3)])  # two fields of domain 1, three of domain 2
    assert suggest_merge(h.state)["topic"] == node("domain", 2)
    h = fields_town([(1, 1), (1, 2), (2, 1), (2, 2)])  # two groups of two, as many houses: the lower parent id
    assert suggest_merge(h.state)["topic"] == node("domain", 1)
    h.add(3, T(2, 1, 1, 1))
    for x in houses(25, 27):
        h.file(x, "r2")  # the avenues of domain 2 hold more houses
    assert suggest_merge(h.state)["topic"] == node("domain", 2)


def test_a_group_is_left_out_when_a_road_stands_for_its_parent_node_already_or_a_house_is_not_under_it():
    h = fields_town([(1, 1), (1, 2), (2, 1), (2, 2)])
    assert suggest_merge(h.state)["topic"] == node("domain", 1)
    h.add(10, T(1, 1, 1, 1))
    h.open("dom1", "Domain one", None, h.state.houses_at(None), node("domain", 1))  # an avenue stands for domain 1 already
    assert suggest_merge(h.state)["topic"] == node("domain", 2)  # a merge under that node would be refused
    h2 = fields_town([(1, 1), (1, 2), (2, 1), (2, 2)])
    h2.add(5, T(5, 1, 1, 1))
    for x in houses(25, 29):
        h2.file(x, "r1")  # strays of another domain stand on the field road of domain 1
    assert suggest_merge(h2.state)["topic"] == node("domain", 2)  # domain 1 is passed over: its merge would be refused
    with pytest.raises(Refusal, match="not under the domain 'ex:d1'"):
        h2.merge("m", "M", ["r0", "r1"], node("domain", 1))


def test_with_no_siblings_the_two_avenues_whose_houses_are_most_alike_are_proposed():
    h = Hand({"max": 40, "min": 5, "auto": False})
    h.add(6, T(1, 1, 1, 1), T(2, 1, 1, 1))  # r0: domains 1 and 2
    h.add(6, T(2, 1, 1, 1), T(3, 1, 1, 1))  # r1: domains 2 and 3
    h.add(6, T(4, 1, 1, 1))  # r2: domain 4
    h.add(6, T(3, 1, 1, 1), T(4, 1, 1, 1))  # r3: domains 3 and 4
    for k in range(4):
        h.open(f"r{k}", f"Road {k}", None, houses(6 * k + 1, 6 * k + 6))
    s = suggest_merge(h.state)
    # (r0, r1), (r1, r3) and (r2, r3) share one topic of six houses each; r0 and r2, r0 and r3, r1 and r2 share nothing: of the three, the pair of the lowest road ids
    assert (s["members"], s["topic"], s["by"], s["name"], s["frees"]) == (["r0", "r1"], None, "similar_houses", "Road 0 / Road 1", 1) and s["takes"] == "r0"
    h.take_merge(s, "m")
    sound(h)


def test_the_most_specific_shared_node_decides_which_pair_is_the_most_alike():
    h = Hand({"max": 40, "min": 5, "auto": False})
    h.add(6, T(1, 1, 1, 1))  # r0
    h.add(6, T(1, 1, 1, 2))  # r1: the same subfield as r0
    h.add(6, T(1, 2, 1, 1))  # r2: the same domain only
    for k in range(3):
        h.open(f"r{k}", f"Road {k}", None, houses(6 * k + 1, 6 * k + 6))
    assert suggest_merge(h.state)["members"] == ["r0", "r1"]  # a shared subfield beats a shared domain


def test_nothing_is_proposed_when_no_two_avenues_have_a_node_in_common_or_there_are_fewer_than_two():
    h = Hand({"max": 40, "min": 5, "auto": False})
    for k in range(3):
        h.add(6, T(k + 1, 1, 1, 1))
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    assert suggest_merge(h.state) is None
    h.add(6)
    h.open("r3", "Road 3", None, h.state.houses_at(None))  # houses with no topic share nothing
    assert suggest_merge(h.state) is None
    assert suggest_merge(Hand().state) is None and suggest_merge(avenues(1).state) is None


def suggestion_in_a_town():
    h = fields_town([(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (2, 2)])
    s = suggest_merge(h.state)
    assert list(s) == ["members", "topic", "name", "by", "takes", "frees"]
    return s


def test_a_suggestion_is_plain_data_the_same_in_every_process_and_a_merge_takes_it_as_it_stands():
    code = "import sys, json; sys.path.insert(0, 'tests'); import test_merge as t; print(json.dumps(t.suggestion_in_a_town(), sort_keys=True))"
    outs = set()
    for seed in ("0", "4242"):
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"},
                              capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        outs.add(done.stdout.strip())
    s = suggestion_in_a_town()
    assert outs == {json.dumps(s, sort_keys=True)} and json.loads(json.dumps(s)) == s
    h = fields_town([(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (2, 2)])
    direction = h.state.direction_of(s["takes"])
    h.take_merge(s, "m")
    assert h.state.nodes["m"]["name"] == s["name"] and h.state.nodes["m"]["topic"] == s["topic"] and h.state.direction_of("m") == direction
    sound(h)


# ---------------------------------------------------------------------------------- an auto world, a full ring ----
def stream(seed, n, domains):
    """n items with a primary topic in one of `domains` domains and, for most, a second topic in another domain (invented topics), from a fixed seed."""
    rng = random.Random(seed)
    out = []
    for i in range(1, n + 1):
        d = rng.randint(1, domains)
        topics = [T(d, rng.randint(1, 2), rng.randint(1, 2), rng.randint(1, 3))]
        if rng.random() < 0.8:
            topics.append(T(rng.choice([x for x in range(1, domains + 1) if x != d]), rng.randint(1, 2), 1, 1))
        out.append(item(i, *topics))
    return out


def test_an_auto_world_whose_first_ring_is_full_merges_by_suggestion_and_goes_on():
    h = Hand({"max": 12, "min": 5, "auto": True})
    items = stream(7, 900, 20)
    arrived = 0
    for arrived, it in enumerate(items, start=1):  # the rule opens avenues for domains until the ring is full ...
        h.add_items([it])
        if len(h.state.held) == AVENUES:
            break
    assert len(h.state.held) == AVENUES
    for it in items[arrived:]:  # ... and the arrivals of a domain with no avenue wait underground until the root zone is over max: no direction is left
        arrived += 1
        h.add_items([it])
        if h.state.count(None) > h.state.rule["max"]:
            break
    assert h.state.count(None) > h.state.rule["max"] and len(h.state.held) == AVENUES
    s = suggest_merge(h.state)
    assert s is not None and len(s["members"]) >= 2 and s["by"] == "similar_houses"  # the avenues of domains stand for no parent node: the houses that two of them share
    direction = h.state.direction_of(s["takes"])
    freed = {h.state.direction_of(m) for m in s["members"] if m != s["takes"]}
    h.take_merge(s, "m1")
    state = sound(h)
    assert len(state.held) == AVENUES - s["frees"] and state.direction_of("m1") == direction and not freed & set(state.held)

    def auto_avenues():
        return {k for k, n in h.state.nodes.items() if k.startswith("auto:") and n["parent"] is None}

    before, opened = auto_avenues(), set()
    for it in items[arrived:]:  # the next arrival that stays underground finds a direction: the rule opens its avenue
        h.add_items([it])
        opened = auto_avenues() - before
        if opened:
            break
    assert opened and h.state.direction_of(next(k for k in h.state.nodes if k in opened)) == min(freed)  # in the lowest freed direction
    sound(h)


# ---------------------------------------------------------------------------------------- random worlds ----
@pytest.mark.parametrize("seed", range(20))
def test_a_random_player_who_merges_leaves_a_sound_stable_world_with_the_directions_in_order(seed):
    j = play(seed, steps=250, auto=(seed % 2 == 0), suggested=True, arrivals=0.6, merging=True)
    assert hand_problems(j.state) == [] and text_problems(j.state) == []
    assert stability_violations(j.events, j.rule) == [] and direction_violations(j.events, j.rule) == [] and landing_violations(j.events, j.rule) == []


def test_the_random_players_merge_and_the_merges_free_directions_that_later_avenues_take():
    merges = reused = 0
    for seed in range(20):
        j = play(seed, steps=250, auto=(seed % 2 == 0), suggested=True, arrivals=0.6, merging=True)
        merges += sum(1 for e in j.events if e["kind"] == "merge_roads")
        state, seen = hand.State(j.rule), []
        for e in j.events:
            seen.append(e)
            if e["kind"] == "undo":
                state = hand.fold(seen, j.rule)
                continue
            top, before = max(state.held, default=-1), set(state.held)
            state.apply(e)
            reused += sum(1 for k in set(state.held) - before if k < top)  # an avenue that took a direction below one that was held: a freed one
    assert merges >= 60 and reused >= 30


# ------------------------------------------------------------------------------------------------ scripted ----
def test_the_scripted_merge_log_fills_the_ring_merges_by_suggestion_and_by_hand_and_ends_sound():
    h = scripted_merge()
    kinds = [e["kind"] for e in h.journal.events]
    assert kinds.count("merge_roads") == 2 and {"undo", "rename_road", "move_road", "file"} <= set(kinds)
    state = sound(h)
    assert landing_violations(h.journal.events, h.journal.rule) == []
    assert state.held == {0: "n1", 1: "n2", 2: "d1", 3: "n3", 4: "d2", 5: "f5", 6: "f6", 7: "f7", 8: "f8", 9: "f9", 10: "f10", 11: "f11", 12: "mine"}
    assert state.nodes["n3"]["parent"] == "n2" and state.direction_of("n3") == 3  # an avenue moved below another keeps its direction
    assert [state.nodes[k]["parent"] for k in ("f0", "f1", "f2")] == ["d1"] * 3 and [state.nodes[k]["parent"] for k in ("f3", "f4")] == ["d2"] * 2


# ------------------------------------------------------------------------------------- the planted faults ----
def merge_log(tie=False):
    """Thirteen avenues with houses and a road below one of them, merged: the log that the planted faults go wrong on. The members r2, r5 and r9 have 12 houses each (`tie`),
    or r5 has 15 and is the largest."""
    h = avenues(13, each=12)
    h.open("r2a", "R2 A", "r2", houses(25, 36))
    if not tie:
        h.add(3)
        for x in houses(157, 159):
            h.file(x, "r5")
    h.merge("m", "M", ["r2", "r5", "r9"])
    return h


def test_the_stability_check_is_red_when_a_merge_puts_a_house_of_another_avenue_again(monkeypatch):
    h = merge_log()
    original = hand.HandWorld.merge_avenues

    def careless(self, key, label, members, took, keys, trigger):
        out = original(self, key, label, members, took, keys, trigger)
        lots = self.lots_on("place:tag:r0")  # an avenue that is not a member: its houses are put again, the other way round
        for lot in lots:
            self.free_lot(lot)
        self.add_houses("place:tag:r0", [{"article": lot["article"], "tag": lot["tag"], "seq": lot["seq"]} for lot in reversed(lots)], trigger)
        return out

    monkeypatch.setattr(hand.HandWorld, "merge_avenues", careless)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and all("(merge_roads)" in line and "moved the house" in line for line in found), found
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_the_stability_check_has_to_know_the_event_or_a_merge_looks_like_houses_that_moved_without_being_asked(monkeypatch):
    h = merge_log()
    monkeypatch.setattr(hand_support, "moved_by", lambda event, before: set())
    assert any("(merge_roads)" in line for line in stability_violations(h.journal.events, h.journal.rule))
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


@pytest.mark.parametrize("fault", ["the smallest member", "the higher direction of two as large"])
def test_the_direction_check_is_red_when_the_new_avenue_takes_the_direction_of_another_member_than_the_largest(fault, monkeypatch):
    h = merge_log(tie=fault != "the smallest member")
    if fault == "the smallest member":
        monkeypatch.setattr(hand.State, "largest_avenue", lambda self, members: min(members, key=lambda m: (len(self.houses_below(m)), self.direction_of(m))))
    else:
        monkeypatch.setattr(hand.State, "largest_avenue", lambda self, members: min(members, key=lambda m: (-len(self.houses_below(m)), -self.direction_of(m))))
    found = direction_violations(h.journal.events, h.journal.rule)
    assert found and all("(merge_roads)" in line for line in found), found
    monkeypatch.undo()
    assert direction_violations(h.journal.events, h.journal.rule) == []


def test_the_direction_check_is_red_when_a_merge_frees_no_direction(monkeypatch):
    h = merge_log()
    original = hand.State.do_merge_roads

    def keeping(self, e, p):
        held = dict(self.held)
        original(self, e, p)
        for k, road in held.items():
            self.held.setdefault(k, road)  # the members keep the directions they had

    monkeypatch.setattr(hand.State, "do_merge_roads", keeping)
    found = direction_violations(h.journal.events, h.journal.rule)
    assert found and all("(merge_roads)" in line for line in found), found
    monkeypatch.undo()
    assert direction_violations(h.journal.events, h.journal.rule) == []


def test_the_engine_check_is_red_when_the_old_lines_of_the_members_stay_to_lie_under_the_new_one(monkeypatch):
    def town():
        h = Hand({"max": 40, "min": 5, "auto": False})
        for k in range(2):
            h.add(6)
            h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
        h.open("s0", "Sub 0", "r0", houses(1, 5))
        h.merge("m", "M", ["r0", "r1"])
        return h

    assert hand_problems(town().state) == []
    monkeypatch.setattr(hand.HandWorld, "drop_line", lambda self, place: None)
    assert any(kind == "geometry" for kind, _ in hand_problems(town().state))  # the ghost roads of the old line cross the roads of the new one
    monkeypatch.undo()
    assert hand_problems(town().state) == []
