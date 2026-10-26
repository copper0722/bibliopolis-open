"""Suggestions and the rule `auto` (bibliopolis.suggest): a road is split one level of OpenAlex at a time, a house goes to the deepest road whose node it is under, the places that
are crowded."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hand_support import Hand, hand_problems, hid, landing_violations, lot_snapshot, play, sample_world_items, stability_violations, topic

from bibliopolis.events import ORDER, Refusal
from bibliopolis.suggest import crowded, landing, roads_by_node, suggest_file, suggest_road

ROOT = Path(__file__).resolve().parents[1]
T = topic


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def node(level, d, f=1, s=1, t=1):
    """The node of a topic made by `topic(d, f, s, t)` at `level`, as a road carries it: `node("field", 1, 2)` is field 2 of domain 1."""
    return {"id": topic(d, f, s, t)[level]["id"], "level": level, "name": topic(d, f, s, t)[level]["name"]}


def open_node(h, road, level, *numbers, parent=None, members=None):
    """Open the road `road` for the node `node(level, *numbers)`, with the houses of the parent place that are under it (or `members`)."""
    n = node(level, *numbers)
    under = [x for x in h.state.houses_at(parent) if any(t[level]["id"] == n["id"] for t in h.state.items[x]["openalex"])]
    return h.open(road, n["name"], parent, members or under, n)


# ------------------------------------------------------------------------- the root zone: by domain ----
def test_the_root_zone_is_grouped_by_domain_whatever_the_levels_below_say():
    h = Hand()
    h.add(8, T(1, 1, 1, 1))
    h.add(4, T(1, 2, 1, 1))  # 12 houses of domain 1, in two fields; one topic of 8 is the most any level below the domain gives
    h.add(5, T(2, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert s == {"at": None, "topic": {"id": "ex:d1", "level": "domain", "name": "Domain 1"}, "name": "Domain 1", "houses": houses(1, 12)}


def test_the_largest_group_wins_and_of_two_as_large_the_lower_node_id():
    h = Hand()
    h.add(10, T(2, 1, 1, 1))
    h.add(10, T(1, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert s["topic"]["id"] == "ex:d1" and s["houses"] == houses(11, 20)  # a tie: the lower id
    h.add(11, T(3, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert s["topic"]["id"] == "ex:d3" and s["houses"] == houses(21, 31)  # a group of 11 beats the two of 10, though its id is the highest


def test_a_house_is_in_the_group_of_every_domain_it_carries_once():
    h = Hand()
    h.add(6, T(1, 1, 1, 1))
    h.add(6, T(2, 1, 1, 1), T(1, 2, 2, 2))  # primary in domain 2, a second topic in domain 1
    s = suggest_road(h.state, None)
    assert s["topic"]["id"] == "ex:d1" and s["houses"] == houses(1, 12)  # all twelve carry domain 1; only six carry domain 2
    h = Hand()
    h.add(5, T(1, 1, 1, 1), T(1, 2, 1, 1), T(1, 3, 1, 1))  # three topics, one domain: the house is one house of that domain
    h.add(5, T(1, 1, 1, 1))
    assert suggest_road(h.state, None)["houses"] == houses(1, 10)  # ten houses, not twenty
    h = Hand()
    h.add(10, T(1, 1, 1, 1), T(2, 1, 1, 1), T(3, 1, 1, 1))  # three domains of ten each: the lowest id wins
    assert suggest_road(h.state, None)["topic"]["id"] == "ex:d1"


def test_a_house_with_no_topic_is_in_no_group_and_the_group_needs_the_least_in_force():
    h = Hand()
    h.add(20)
    h.add(9, T(1, 1, 1, 1))
    assert suggest_road(h.state, None) is None
    h.add(1, T(1, 1, 1, 1))
    assert suggest_road(h.state, None)["houses"] == houses(21, 30)
    h.rule(40, 12)
    assert suggest_road(h.state, None) is None
    h.rule(40, 3)
    assert suggest_road(h.state, None)["houses"] == houses(21, 30)


def test_only_the_houses_that_stand_directly_at_the_place_count_and_a_road_that_is_not_there_is_refused():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.add(2, T(2, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert s["houses"] == houses(1, 12)
    h.take(s, "d1")
    assert suggest_road(h.state, None) is None  # two houses are left in the root zone
    s = suggest_road(h.state, "d1")
    assert (s["at"], s["topic"], s["houses"]) == ("d1", node("field", 1, 1), houses(1, 12))
    h.take(s, "f1")
    assert suggest_road(h.state, "d1") is None and suggest_road(h.state, "f1")["topic"] == node("subfield", 1, 1, 1)
    with pytest.raises(Refusal, match="there is no road 'x'"):
        suggest_road(h.state, "x")


def test_the_name_is_the_one_the_first_house_that_carries_the_node_writes():
    h = Hand()
    first = T(1, 1, 1, 1)
    other = T(1, 1, 1, 1)
    other["domain"] = {"id": "ex:d1", "name": "Another spelling"}
    h.add(1, first)
    h.add(9, other)
    s = suggest_road(h.state, None)
    assert s["name"] == s["topic"]["name"] == "Domain 1" and len(s["houses"]) == 10


def test_a_suggestion_is_plain_data_that_open_road_takes_as_it_stands_and_the_same_world_gives_the_same_one_in_another_process():
    h = Hand()
    h.add(7, T(1, 1, 1, 1))
    h.add(6, T(1, 1, 1, 2), T(2, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert json.loads(json.dumps(s)) == s and list(s) == ["at", "topic", "name", "houses"] and list(s["topic"]) == ["id", "level", "name"]
    h.take(s, "r")
    assert h.state.nodes["r"] == {"key": "r", "name": s["name"], "parent": None, "topic": s["topic"]} and h.state.count("r") == len(s["houses"])
    code = ("import sys, json; sys.path.insert(0, 'tests'); import hand_support as hs; from bibliopolis.suggest import suggest_road; h = hs.Hand(); "
            "h.add(7, hs.topic(1, 1, 1, 1)); h.add(6, hs.topic(1, 1, 1, 2), hs.topic(2, 1, 1, 1)); print(json.dumps(suggest_road(h.state, None)))")
    outs = set()
    for seed in ("0", "4242"):
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"},
                              capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        outs.add(done.stdout.strip())
    h2 = Hand()
    h2.add(7, T(1, 1, 1, 1))
    h2.add(6, T(1, 1, 1, 2), T(2, 1, 1, 1))
    assert outs == {json.dumps(suggest_road(h2.state, None))}


# ----------------------------------------------------------------------------- one level at a time ----
def chain_town():
    """30 houses of domain 1: 12 + 10 in field 1 (subfield 1, topics 1 and 2), 8 in field 2."""
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.add(10, T(1, 1, 1, 2))
    h.add(8, T(1, 2, 1, 1))
    return h


def test_a_road_that_stands_for_a_node_is_split_by_the_level_below_its_node_down_to_the_topic():
    h = chain_town()
    s = suggest_road(h.state, None)
    assert s["topic"] == node("domain", 1) and len(s["houses"]) == 30
    h.take(s, "d1")
    s = suggest_road(h.state, "d1")
    assert (s["topic"], s["houses"]) == (node("field", 1, 1), houses(1, 22)) and s["at"] == "d1"  # field 1 holds 22 of them, field 2 only 8
    h.take(s, "f1")
    s = suggest_road(h.state, "f1")
    assert (s["topic"], s["houses"]) == (node("subfield", 1, 1, 1), houses(1, 22))  # one subfield: the road would hold the same houses, and it is still the next level
    h.take(s, "s1")
    s = suggest_road(h.state, "s1")
    assert (s["topic"], s["houses"]) == (node("topic", 1, 1, 1, 1), houses(1, 12))  # topic 1: 12 houses, topic 2: 10
    h.take(s, "t1")
    assert suggest_road(h.state, "t1") is None  # a topic is the last level: no road below it
    s = suggest_road(h.state, "s1")
    assert s["topic"] == node("topic", 1, 1, 1, 2) and s["houses"] == houses(13, 22)  # the node that has a road is left out
    h.take(s, "t2")
    assert suggest_road(h.state, "s1") is None and hand_problems(h.state) == []
    assert [(k, n["parent"], n["topic"]["level"]) for k, n in h.state.nodes.items()] == [
        ("d1", None, "domain"), ("f1", "d1", "field"), ("s1", "f1", "subfield"), ("t1", "s1", "topic"), ("t2", "s1", "topic")]


def test_only_the_topics_under_the_node_of_the_place_count():
    h = Hand()
    h.add(12, T(1, 1, 1, 1), T(2, 5, 1, 1))  # a second topic in another domain
    h.add(10, T(2, 5, 1, 1))
    open_node(h, "d1", "domain", 1)
    s = suggest_road(h.state, "d1")
    assert s["topic"] == node("field", 1, 1) and s["houses"] == houses(1, 12)  # field 5 of domain 2 is not a field of domain 1, though twelve houses carry it
    assert suggest_road(h.state, None)["topic"] == node("domain", 2)  # the ten houses that did not move, and nothing of d1: they are domain 2 only


def test_a_stray_house_that_is_not_under_the_node_of_its_road_is_in_no_group():
    h = Hand()
    h.add(10, T(1, 1, 1, 1))
    h.add(10, T(2, 1, 1, 1))
    open_node(h, "d1", "domain", 1)
    h.file(hid(11), "d1")  # a player filing: not under domain 1
    s = suggest_road(h.state, "d1")
    assert s["houses"] == houses(1, 10) and hid(11) not in s["houses"]


def test_a_node_that_a_road_stands_for_is_left_out_whichever_place_has_the_houses():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    open_node(h, "d1", "domain", 1, members=houses(1, 10))
    h.add(14, T(1, 1, 1, 1))  # domain 1 again in the root zone (no rule auto): its node has a road
    assert suggest_road(h.state, None) is None  # (the group of domain 1 is 16 houses, and it is not offered a second time)
    h.add(10, T(2, 1, 1, 1))
    assert suggest_road(h.state, None)["topic"] == node("domain", 2)


# ------------------------------------------------------------------------------------ the node of a road ----
def test_the_world_refuses_a_second_road_for_a_node_and_a_house_that_is_not_under_it_and_is_as_it_was():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.add(12, T(2, 1, 1, 1))
    h.open("a", "A", None, houses(1, 10), node("domain", 1))
    before = (list(h.state.nodes), dict(h.state.road_of), len(h.journal.events))
    with pytest.raises(Refusal) as why:
        h.open("b", "B", None, houses(13, 22), node("domain", 1))  # the same node, other houses
    assert (why.value.code, why.value.params) == ("node_taken", {"level": "domain", "topic": "ex:d1", "road": "a"})
    with pytest.raises(Refusal) as why:
        h.open("c", "C", None, houses(13, 22), node("domain", 3))  # a node none of the houses is under
    assert (why.value.code, why.value.params) == ("house_not_under_node", {"house": hid(13), "level": "domain", "topic": "ex:d3"})
    assert (list(h.state.nodes), dict(h.state.road_of), len(h.journal.events)) == before and hand_problems(h.state) == []
    h.open("b", "B", None, houses(13, 22), node("domain", 2))  # another node: taken
    assert roads_by_node(h.state) == {("domain", "ex:d1"): "a", ("domain", "ex:d2"): "b"}


def test_a_node_may_be_below_any_place_and_a_road_for_a_topic_may_stand_at_the_root_zone():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.open("t", "T", None, houses(1, 10), node("topic", 1, 1, 1, 1))  # no level is demanded of a road the player opens: only the suggestions go level by level
    assert h.state.nodes["t"]["topic"] == node("topic", 1, 1, 1, 1) and suggest_road(h.state, "t") is None


def test_the_node_stays_with_the_road_when_it_is_renamed_or_moved_and_an_undo_gives_it_back():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.add(12, T(2, 1, 1, 1))
    h.open("a", "A", None, houses(1, 10), node("domain", 1))
    h.open("b", "B", None, houses(13, 22), node("domain", 2))
    h.rename("a", "Mine")
    h.move("b", "a")
    assert [n["topic"] for n in h.state.nodes.values()] == [node("domain", 1), node("domain", 2)] and h.state.nodes["a"]["name"] == "Mine"
    h.undo(28)  # the move, the rename, and then the road 'b' are taken back, from the end
    h.undo(27)
    h.undo(26)
    assert list(h.state.nodes) == ["a"]
    h.open("c", "C", None, houses(13, 22), node("domain", 2))  # the node is free again
    assert roads_by_node(h.state) == {("domain", "ex:d1"): "a", ("domain", "ex:d2"): "c"}


# --------------------------------------------------------------------- a category the player named ----
def category(rows, least=10):
    """A category with no node ('p') that holds houses with the topics of `rows`, [(count, topic, ...), ...] (the houses are brought to the root zone and put on it)."""
    h = Hand({"max": 100, "min": least, "auto": False})
    for count, *topics in rows:
        h.add(count, *topics)
    h.open("p", "P", None, list(h.state.items))
    return h


@pytest.mark.parametrize("rows, want, why", [
    ([(14, T(1, 1, 1, 1)), (10, T(1, 1, 2, 1))], node("subfield", 1, 1, 1), "one domain and one field are shared by all: below the field, subfield 1 has 14 houses and subfield 2 has 10"),
    ([(14, T(1, 1, 1, 1)), (10, T(1, 1, 2, 1)), (5, T(3, 1, 1, 1))], node("subfield", 1, 1, 1),
     "five strays of another domain do not hide it: all but fewer than 10 of the 29 houses are in field 1"),
    ([(14, T(1, 1, 1, 1)), (10, T(1, 2, 1, 1))], node("field", 1, 1), "the houses share the domain and split below it, by field: 14 and 10"),
    ([(12, T(1, 1, 1, 1)), (11, T(2, 1, 1, 1)), (10, T(3, 1, 1, 1))], node("domain", 1), "no domain is shared by all but fewer than 10 of 33: it is split by domain, like the root zone"),
    ([(12, T(1, 1, 1, 1))], None, "every house is under topic 1.1.1.1: nothing is left to split by"),
    ([(8, T(1, 1, 1, 1)), (2, T(1, 1, 1, 2))], None, "ten houses all carrying domain 1 (and the same field, subfield): the groups below are 8 and 2"),
    ([(30, ), (14, T(1, 1, 1, 1)), (10, T(1, 1, 2, 1))], node("subfield", 1, 1, 1), "houses with no topic are not counted among those that share"),
    ([(1, ), (9, T(1, 1, 1, 1))], None, "fewer houses with a topic than the least"),
])
def test_a_category_with_no_node_stands_for_the_deepest_node_that_all_but_fewer_than_the_least_of_its_houses_share(rows, want, why):
    h = category(rows)
    s = suggest_road(h.state, "p")
    assert (s["topic"] if s else None) == want, why
    if s:
        assert s["at"] == "p" and set(s["houses"]) <= set(h.state.houses_at("p"))


def test_the_reading_of_the_least_that_would_give_nothing_is_not_the_one_used():
    """'The level below the deepest level shared by at least `min` houses' would never give a group: by that definition no node of the level below is carried by `min` houses."""
    h = category([(14, T(1, 1, 1, 1)), (10, T(1, 1, 2, 1))])
    counts = {}
    for x in h.state.houses_at("p"):
        for t in h.state.items[x]["openalex"]:
            for level in ORDER:
                counts.setdefault(level, {}).setdefault(t[level]["id"], set()).add(x)
    deepest = max((level for level in ORDER if any(len(v) >= 10 for v in counts[level].values())), key=ORDER.index)
    below = ORDER[ORDER.index(deepest) + 1] if deepest != "topic" else None
    assert deepest == "topic" and below is None  # every level has a node of 10 houses or more here, down to topic 1: the reading has nothing to split
    assert suggest_road(h.state, "p") is not None  # ... and the rule in use does


# ------------------------------------------------------------------------------------------ the filing ----
def two_roads():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))  # road a
    h.add(12, T(2, 1, 1, 1))  # road b
    h.open("a", "A", None, houses(1, 12))
    h.open("b", "B", None, houses(13, 24))
    return h


def test_a_house_goes_to_the_category_whose_houses_share_the_most_topics_with_it_and_the_confidence_says_how_clear_it_is():
    h = two_roads()
    h.add(1, T(1, 1, 1, 1))
    s = suggest_file(h.state, hid(25))
    assert s == {"house": hid(25), "road": "a", "name": "A", "level": "topic", "shared": 12, "confidence": 1.0}
    h.add(1, T(1, 1, 1, 2))  # a topic of its own, in the subfield of road a
    s = suggest_file(h.state, hid(26))
    assert (s["road"], s["level"], s["shared"], s["confidence"]) == ("a", "subfield", 12, 1.0)
    h.add(1, T(1, 2, 1, 1))  # only the domain is shared
    assert [suggest_file(h.state, hid(27))[k] for k in ("road", "level", "shared")] == ["a", "domain", 12]
    h.add(1, T(3, 1, 1, 1))  # nothing shared with anybody
    assert suggest_file(h.state, hid(28)) is None


def test_two_categories_that_share_the_same_make_the_confidence_the_part_of_the_one_that_wins_and_an_older_road_wins_a_tie():
    h = two_roads()
    h.add(1, T(1, 1, 1, 1), T(2, 1, 1, 1))  # shares a topic with all of a and all of b
    s = suggest_file(h.state, hid(25))
    assert (s["road"], s["shared"], s["confidence"]) == ("a", 12, 0.5)  # a tie: the road opened first, and half of the matches
    h = Hand()
    h.add(9, T(1, 1, 1, 1))
    h.add(1, T(9, 9, 9, 9))
    h.add(3, T(1, 1, 1, 1))
    h.add(7, T(8, 8, 8, 8))
    h.open("a", "A", None, houses(1, 10))  # nine houses of the topic, and one of another
    h.open("b", "B", None, houses(11, 20))  # three houses of the topic, and seven of another
    h.add(1, T(1, 1, 1, 1))
    s = suggest_file(h.state, hid(21))
    assert (s["road"], s["level"], s["shared"], s["confidence"]) == ("a", "topic", 9, 0.75)  # 9 matches on a against 3 on b: 9 of 12


def test_a_house_on_a_category_is_moved_only_to_a_category_that_fits_it_better_than_its_own():
    h = two_roads()
    assert suggest_file(h.state, hid(1)) is None  # a house of a stands where it fits
    h.file(hid(1), "b")
    s = suggest_file(h.state, hid(1))
    assert (s["road"], s["shared"], s["confidence"]) == ("a", 11, 1.0)  # back to a: it shares a topic with the eleven others there, and with none of b
    h.file(hid(1), "a")
    assert suggest_file(h.state, hid(1)) is None  # its own house does not count for its own road


def test_no_suggestion_for_a_house_with_no_topic_or_a_world_with_no_road_and_a_house_that_is_not_there_is_refused():
    h = Hand()
    h.add(3, T(1, 1, 1, 1))
    assert suggest_file(h.state, hid(1)) is None  # no road
    h = two_roads()
    h.add(1)
    assert suggest_file(h.state, hid(25)) is None
    with pytest.raises(Refusal, match="'nobody' is not a house"):
        suggest_file(h.state, "nobody")


def node_town():
    """Domain 1 and domain 2 have a road each, and field 1 of domain 1 has one below the road of its domain. Houses 1 to 12 are in field 1 (on its road), 13 to 24 in field 2
    of the domain (on the road of the domain), 25 to 36 in domain 2 (on its road)."""
    h = Hand()
    h.add(12, T(1, 1, 1, 1))
    h.add(12, T(1, 2, 1, 1))
    h.add(12, T(2, 1, 1, 1))
    open_node(h, "d1", "domain", 1)
    open_node(h, "d2", "domain", 2)
    open_node(h, "f1", "field", 1, 1, parent="d1")
    return h


def test_a_house_under_the_node_of_a_road_goes_to_that_road_and_the_deepest_node_wins():
    h = node_town()
    assert (h.state.road_of[hid(1)], h.state.road_of[hid(13)], h.state.road_of[hid(25)]) == ("f1", "d1", "d2")
    h.add(1, T(1, 1, 1, 2))  # field 1 of domain 1
    s = suggest_file(h.state, hid(37))
    assert s == {"house": hid(37), "road": "f1", "name": "Field 1.1", "level": "field", "shared": 12, "confidence": 1.0}
    h.add(1, T(1, 3, 1, 1))  # domain 1, but a field with no road
    s = suggest_file(h.state, hid(38))
    assert s == {"house": hid(38), "road": "d1", "name": "Domain 1", "level": "domain", "shared": 12, "confidence": 1.0}  # the 12 houses on d1 are under domain 1; those of f1 are on f1
    h.add(1, T(3, 1, 1, 1))  # a domain with no road: nothing to say by the hierarchy, and nothing shared
    assert suggest_file(h.state, hid(39)) is None


def test_a_house_that_stands_on_a_road_of_a_node_is_moved_only_to_a_deeper_one():
    h = node_town()
    assert suggest_file(h.state, hid(1)) is None  # on f1, the deepest road of its node
    assert suggest_file(h.state, hid(13)) is None  # on d1, and no deeper road under it fits
    h.file(hid(13), "d2")  # ... put on the road of another domain by the player
    s = suggest_file(h.state, hid(13))
    assert (s["road"], s["level"]) == ("d1", "domain")
    h.file(hid(1), "d1")  # a house of field 1 on the road of its domain: f1 is deeper
    s = suggest_file(h.state, hid(1))
    assert (s["road"], s["level"], s["confidence"]) == ("f1", "field", 1.0)


def test_a_house_with_topics_in_two_roads_goes_to_the_deeper_and_when_they_are_as_deep_to_the_one_of_its_primary_topic():
    h = node_town()
    h.add(1, T(2, 1, 1, 1), T(1, 1, 1, 1))  # primary in domain 2 (a domain road), a second topic in field 1 of domain 1 (a field road, deeper)
    s = suggest_file(h.state, hid(37))
    assert (s["road"], s["level"], s["confidence"]) == ("f1", "field", 1.0)
    h.add(1, T(2, 1, 1, 1), T(1, 7, 1, 1))  # domains 2 and 1, both roads at the domain level
    s = suggest_file(h.state, hid(38))
    assert (s["road"], s["level"], s["confidence"]) == ("d2", "domain", 0.5)  # its primary topic first; it is half sure
    h.file(hid(38), "d1")
    assert suggest_file(h.state, hid(38)) is None  # as deep as the other: it stands where it fits


def test_a_house_on_a_category_is_pointed_to_the_road_of_its_node_whatever_the_category_scores():
    h = node_town()
    h.add(10, T(5, 5, 5, 5))
    h.open("p", "Mine", None, houses(37, 46))
    h.add(1, T(1, 1, 1, 1))
    h.file(hid(47), "p")
    s = suggest_file(h.state, hid(47))
    assert (s["road"], s["level"]) == ("f1", "field")  # the roads of a node come first


# ------------------------------------------------------------------------------------------------ crowded ----
def test_the_places_that_hold_more_than_max_are_listed_the_root_zone_first_and_nothing_is_marked():
    h = Hand({"max": 12, "min": 5, "auto": False})
    h.add(30)
    assert crowded(h.state) == [{"at": None, "name": None, "houses": 30}]
    h.open("a", "A", None, houses(1, 14))
    h.open("b", "B", None, houses(15, 20))
    assert crowded(h.state) == [{"at": "a", "name": "A", "houses": 14}]  # the root zone holds 10 now, and b 6
    h.add(5)
    assert [(c["at"], c["houses"]) for c in crowded(h.state)] == [(None, 15), ("a", 14)]
    h.rule(14, 5)
    assert [(c["at"], c["houses"]) for c in crowded(h.state)] == [(None, 15)]  # the limit is the rule in force: 14 is not more than 14
    assert not any(p.get("over") for p in h.state.doc["places"].values())


# ------------------------------------------------------------------------------------- the rule auto ----
def auto_town(max_houses=40, min_houses=10):
    return Hand({"max": max_houses, "min": min_houses, "auto": True})


def test_the_rule_opens_a_road_for_the_largest_domain_when_the_41st_house_arrives_and_names_it_after_the_node():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    state = h.state
    assert not state.nodes and state.count(None) == 40  # 40 houses: nothing yet
    h.add(1, T(1, 1, 1, 1))  # the 41st: the root zone holds more than 40
    state = h.state
    assert list(state.nodes) == ["auto:41"] and state.nodes["auto:41"] == {"key": "auto:41", "name": "Domain 1", "parent": None, "topic": node("domain", 1)}
    assert state.houses_at("auto:41") == [*houses(1, 20), hid(41)] and state.count(None) == 20
    assert hand_problems(state) == []
    entry = state.city()["world"]["chronicle"][-1]
    assert (entry["trigger"], entry["from"], entry["to"], entry["label"], entry["count_before"], entry["count_after"], entry["event_id"]) == (
        "add_item", "place:root", "place:tag:auto:41", "Domain 1", 41, 20, 41)
    assert state.city()["composition"]["ring1"][0]["label"] == "Domain 1"


def test_the_houses_that_stay_keep_their_lots_when_the_rule_opens_a_road():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    before = lot_snapshot(h.state)
    h.add(1, T(1, 1, 1, 1))
    after = lot_snapshot(h.state)
    assert all(after[x] == before[x] for x in houses(21, 40))  # the twenty of the second domain stay on the lots they have, at slots 20 to 39


def test_a_road_that_the_rule_opened_is_a_road_like_any_other_it_is_renamed_and_filed_onto_and_undo_keeps_the_log_whole():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    h.add(1, T(1, 1, 1, 1))  # event 41 opens auto:41
    h.rename("auto:41", "Mine")
    h.file(hid(30), "auto:41")
    assert h.state.nodes["auto:41"]["name"] == "Mine" and h.state.road_of[hid(30)] == "auto:41"
    assert h.state.nodes["auto:41"]["topic"] == node("domain", 1)  # the node does not change with the name
    with pytest.raises(Refusal, match=r"event 41 cannot be undone: event 42 \(rename_road\) depends on it"):
        h.undo(41)
    h.undo(43)
    h.undo(42)
    h.undo(41)  # the arrival, and the road it opened, are taken back together
    assert list(h.state.nodes) == [] and hid(41) not in h.state.items and hand_problems(h.state) == []


def test_an_arrival_stands_on_the_deepest_road_whose_node_it_is_under_and_otherwise_underground():
    h = auto_town()
    h.add(41, T(1, 1, 1, 1))  # the 41st opens domain 1, then (it holds 41) field 1, subfield 1 and topic 1 below it, one in each step
    assert list(h.state.nodes) == ["auto:41", "auto:41.2", "auto:41.3", "auto:41.4"]
    assert h.state.road_of[hid(41)] == "auto:41.4" and h.state.count(None) == 0
    h.add(1, T(1, 1, 1, 2))  # the same subfield, another topic: the road of the subfield
    assert h.state.road_of[hid(42)] == "auto:41.3"
    h.add(1, T(1, 1, 2, 1))  # the same field, another subfield: the road of the field
    assert h.state.road_of[hid(43)] == "auto:41.2"
    h.add(1, T(1, 2, 1, 1))  # the same domain, another field
    assert h.state.road_of[hid(44)] == "auto:41"
    h.add(1, T(2, 1, 1, 1))  # another domain: no road
    h.add(1)  # no topic
    assert h.state.road_of[hid(45)] is None and h.state.road_of[hid(46)] is None
    assert hand_problems(h.state) == [] and landing_violations(h.journal.events, h.journal.rule) == []


def check_the_primary_topic_decides():
    h = auto_town(12, 5)
    h.add(13, T(1, 1, 1, 1))  # opens domain 1 and the fields, subfield and topic below it
    h.add(13, T(2, 1, 1, 1))  # ... and the same for domain 2
    keys = {n["topic"]["id"]: k for k, n in h.state.nodes.items()}
    assert {"ex:d1", "ex:d2"} <= set(keys)
    h.add(1, T(2, 3, 1, 1), T(1, 3, 1, 1))  # both a domain road, nothing deeper: the primary topic
    assert h.state.road_of[hid(27)] == keys["ex:d2"]
    h.add(1, T(1, 3, 1, 1), T(2, 3, 1, 1))  # the same two roads, the other way round
    assert h.state.road_of[hid(28)] == keys["ex:d1"]
    h.add(1, T(2, 3, 1, 1), T(1, 3, 1, 1), T(1, 1, 1, 1))  # a third topic reaches the topic road of domain 1: the deeper
    assert h.state.road_of[hid(29)] == keys["ex:d1.f1.s1.t1"]
    return h


def test_of_two_roads_as_deep_the_primary_topic_decides_and_a_deeper_one_wins_over_the_primary():
    h = check_the_primary_topic_decides()
    assert landing_violations(h.journal.events, h.journal.rule) == []


def test_a_planted_fault_in_the_order_of_the_topics_turns_the_check_of_the_primary_topic_red_and_the_world_ends_green(monkeypatch):
    import bibliopolis.hand as hand_module

    real = hand_module.landing
    monkeypatch.setattr(hand_module, "landing", lambda world, item: real(world, {**item, "openalex": item["openalex"][::-1]}))
    with pytest.raises(AssertionError):
        check_the_primary_topic_decides()
    monkeypatch.undo()
    check_the_primary_topic_decides()


def test_there_are_never_two_roads_for_one_node_and_the_arrivals_of_a_node_with_a_road_do_not_wait_underground():
    h = auto_town(12, 5)
    for _ in range(30):
        h.add(1, T(1, 1, 1, 1))
    ids = [(n["topic"]["level"], n["topic"]["id"]) for n in h.state.nodes.values()]
    assert len(ids) == len(set(ids)) == 4 and h.state.count(None) == 0  # one road each for the domain, field, subfield and topic, and all thirty on the last
    assert h.state.count("auto:13.4") == 30


def test_a_road_that_holds_more_than_max_splits_in_the_same_event_one_level_down_in_the_order_they_were_opened():
    h = auto_town(12, 5)
    h.add(7, T(1, 1, 1, 1))
    h.add(5, T(1, 2, 1, 1))
    assert not h.state.nodes  # 12: not more than 12
    h.add(1, T(1, 2, 1, 1))  # the 13th: domain 1 (13 houses), then field 1 (7 of them) in the road of the domain, which holds 13
    assert [(k, n["parent"], n["topic"]["level"]) for k, n in h.state.nodes.items()] == [("auto:13", None, "domain"), ("auto:13.2", "auto:13", "field")]
    # field 1 has 7 houses (not more than 12), field 2 has 6 and stays on the road of the domain
    assert (h.state.count("auto:13"), h.state.count("auto:13.2"), h.state.count(None)) == (6, 7, 0)
    assert [e["to"] for e in h.state.city()["world"]["chronicle"] if "from" in e] == ["place:tag:auto:13", "place:tag:auto:13.2"]
    assert [e["from"] for e in h.state.city()["world"]["chronicle"] if "from" in e] == ["place:root", "place:tag:auto:13"]
    assert hand_problems(h.state) == [] and stability_violations(h.journal.events, h.journal.rule) == []


def test_a_road_for_a_topic_is_not_split_and_stays_crowded():
    h = auto_town(12, 5)
    h.add(13, T(1, 1, 1, 1))
    assert crowded(h.state) == [{"at": "auto:13.4", "name": "Topic 1.1.1.1", "houses": 13}]
    h.add(1, T(1, 1, 1, 1))
    assert crowded(h.state) == [{"at": "auto:13.4", "name": "Topic 1.1.1.1", "houses": 14}] and len(h.state.nodes) == 4


def test_two_roads_in_one_arrival_are_auto_n_and_auto_n_dot_2():
    h = Hand({"max": 40, "min": 10, "auto": False})
    for k in range(3):
        h.add(10, T(k + 1, 1, 1, 1))
    h.rule(12, 10, True)
    h.add(1, T(1, 1, 1, 1))  # 31 houses in the root zone, 12 at most: two domains leave
    assert [(k, n["topic"]["id"]) for k, n in h.state.nodes.items()] == [("auto:32", "ex:d1"), ("auto:32.2", "ex:d2")]  # (event 31 was the rule, event 32 the arrival)
    assert h.state.count(None) == 10 and hand_problems(h.state) == []
    assert [e["trigger"] for e in h.state.city()["world"]["chronicle"][1:]] == ["add_item", "add_item"]


def test_when_no_group_reaches_the_least_nothing_happens_and_the_root_zone_stays_crowded():
    h = auto_town()
    for i in range(41):
        h.add(1, T(i + 1, 1, 1, 1))  # a domain, a field, a subfield and a topic of its own in every house: no group at any level
    assert not h.state.nodes and h.state.count(None) == 41
    assert crowded(h.state) == [{"at": None, "name": None, "houses": 41}]
    assert not any(e["trigger"] == "add_item" for e in h.state.city()["world"]["chronicle"])


def test_when_the_first_ring_is_full_the_arrival_is_taken_and_the_rule_opens_nothing_at_the_root_zone():
    h = Hand({"max": 12, "min": 5, "auto": False})
    for k in range(13):
        h.add(5, T(k + 1, 1, 1, 1))
        open_node(h, f"r{k}", "domain", k + 1)
    h.rule(12, 5, True)
    h.add(13, T(20, 1, 1, 1))  # thirteen houses of a domain with no road: the rule would open one, and the first ring has no direction left
    assert h.state.count(None) == 13 and len(h.state.nodes) == 13 and hand_problems(h.state) == []
    assert crowded(h.state) == [{"at": None, "name": None, "houses": 13}]
    h.add(30, T(1, 1, 1, 1))  # ... and the arrivals of a road that is there split it, whatever the first ring is
    assert len(h.state.nodes) == 13 + 3 and h.state.road_of[hid(108)] == list(h.state.nodes)[-1]  # the field, subfield and topic of domain 1 below r0, and the last house on the last
    assert h.state.count(None) == 13 and hand_problems(h.state) == []


def test_the_rule_opens_nothing_without_auto_and_a_set_rule_alone_opens_nothing_either():
    h = Hand({"max": 12, "min": 5, "auto": False})
    h.add(20, T(1, 1, 1, 1))
    assert not h.state.nodes
    h.rule(12, 5, True)
    assert not h.state.nodes and h.state.count(None) == 20  # applied after each arrival, not when it is switched on
    h.add(1, T(1, 1, 1, 1))
    assert list(h.state.nodes)[0] == "auto:22"


def test_the_place_that_is_looked_at_is_the_one_the_house_landed_on_so_a_crowded_root_zone_waits_for_an_arrival_that_stays_underground():
    h = Hand({"max": 12, "min": 5, "auto": False})
    h.add(13, T(1, 1, 1, 1))
    h.add(6, T(2, 1, 1, 1))
    open_node(h, "d2", "domain", 2)
    h.rule(12, 5, True)
    assert h.state.count(None) == 13 and not [k for k in h.state.nodes if k.startswith("auto:")]
    h.add(1, T(2, 1, 1, 1))  # lands on the road of domain 2: the root zone is not looked at
    assert h.state.count(None) == 13 and h.state.road_of[hid(20)] == "d2"
    h.add(1, T(1, 1, 1, 1))  # stays underground (no road for domain 1): the root zone has 14 and is split
    assert h.state.count(None) == 0 and h.state.road_of[hid(21)] == "auto:23.4"  # (events 20 to 23: the road of domain 2, the rule, two arrivals)


@pytest.mark.parametrize("seed", range(12))
def test_a_random_player_with_the_rule_on_leaves_a_sound_stable_world(seed):
    j = play(seed, steps=300, auto=True, suggested=True, arrivals=0.85)
    assert hand_problems(j.state) == []
    assert stability_violations(j.events, j.rule) == []
    assert landing_violations(j.events, j.rule) == []
    nodes = [(n["topic"]["level"], n["topic"]["id"]) for n in j.state.nodes.values() if n["topic"] is not None]
    assert len(nodes) == len(set(nodes)) == len(roads_by_node(j.state))


def test_the_random_player_with_the_rule_on_does_open_roads_by_the_rule_and_by_suggestion():
    by_rule = by_hand = 0
    for seed in range(12):
        for k, n in play(seed, steps=300, auto=True, suggested=True, arrivals=0.85).state.nodes.items():
            by_rule += k.startswith("auto:")
            by_hand += k.startswith("r") and n["topic"] is not None
    assert by_rule >= 50 and by_hand >= 20


@pytest.mark.parametrize("seed", range(6))
def test_a_random_player_who_takes_suggestions_without_the_rule_leaves_a_sound_stable_world(seed):
    j = play(seed, steps=200, suggested=True)
    assert hand_problems(j.state) == [] and stability_violations(j.events, j.rule) == []
    assert not any(k.startswith("auto:") for k in j.state.nodes) or any(e["kind"] == "set_rule" and e["payload"]["auto"] for e in j.events)


# ------------------------------------------------------------------------------------------- the sample ----
@pytest.fixture(scope="module")
def sample_items():
    """The 600 items of the sample as items of a world, in arrival order, with invented OpenAlex-shaped topics (hand_support.sample_world_items)."""
    return sample_world_items()


@pytest.fixture(scope="module")
def sample_world(sample_items):
    h = Hand()
    h.add_items(sample_items)
    return h


def test_the_suggestion_on_the_sample_is_the_largest_domain(sample_world, sample_items):
    state = sample_world.state
    assert len(state.items) == 600 and state.count(None) == 600
    s = suggest_road(state, None)
    groups = {}
    for it in sample_items:
        for did in {t["domain"]["id"] for t in it["openalex"]}:
            groups.setdefault(did, []).append(it["id"])
    did = sorted(groups, key=lambda k: (-len(groups[k]), k))[0]
    assert (s["topic"]["level"], s["topic"]["id"], s["houses"]) == ("domain", did, groups[did]) and did == "ex:domain:computing"
    assert crowded(state) == [{"at": None, "name": None, "houses": 600}]


def test_taking_every_suggestion_in_turn_builds_a_sound_town_one_level_at_a_time(sample_items):
    h = Hand()
    h.add_items(sample_items)
    opened, places = 0, [None]
    while places:
        at = places.pop(0)
        while True:
            s = suggest_road(h.state, at)
            if s is None:
                break
            h.take(s, f"s{opened}")
            places.append(f"s{opened}")
            opened += 1
    assert opened >= 20
    assert hand_problems(h.state) == []
    assert all(len(e["houses"]) >= 10 for e in h.state.city()["world"]["chronicle"] if "from" in e)
    for key, n in h.state.nodes.items():  # a node is one level below the node of the road it is below
        above = h.state.nodes[n["parent"]]["topic"]["level"] if n["parent"] is not None else None
        assert ORDER.index(n["topic"]["level"]) == (0 if above is None else ORDER.index(above) + 1), key


@pytest.fixture(scope="module")
def auto_sample(sample_items):
    h = Hand({"max": 40, "min": 10, "auto": True})
    h.add_items(sample_items)
    return h


def simulate(items, top, least):
    """The rule `auto` written out again from docs/world.md, on plain dictionaries and not on the program: (the road of every house, the roads in the order they opened as
    (id, parent, level, node id))."""
    levels = ("domain", "field", "subfield", "topic")
    by_id = {it["id"]: it for it in items}
    road_of, roads, by_node, order = {}, {}, {}, []
    for seq, it in enumerate(items, start=1):
        found = {}
        for o, t in enumerate(it["openalex"]):
            for d, level in enumerate(levels):
                road = by_node.get((level, t[level]["id"]))
                if road is not None and road not in found:
                    found[road] = (d, o)
        land = min(found, key=lambda r: (-found[r][0], found[r][1])) if found else None
        road_of[it["id"]] = land
        order.append(it["id"])
        n, queue = 0, [land]
        while queue:
            at = queue.pop(0)
            while sum(1 for x in order if road_of[x] == at) > top:
                if at is not None and roads[at][2] == "topic":
                    break
                level = levels[0] if at is None else levels[levels.index(roads[at][2]) + 1]
                groups = {}
                for x in order:
                    if road_of[x] != at:
                        continue
                    topics = by_id[x]["openalex"]
                    if at is not None:
                        topics = [t for t in topics if t[roads[at][2]]["id"] == roads[at][3]]
                    for nid in {t[level]["id"] for t in topics}:
                        if (level, nid) not in by_node:
                            groups.setdefault(nid, []).append(x)
                if not groups:
                    break
                nid, members = min(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
                if len(members) < least or (at is None and sum(1 for r in roads.values() if r[1] is None) >= 13):
                    break
                n += 1
                key = f"auto:{seq}" + (f".{n}" if n > 1 else "")
                roads[key] = (key, at, level, nid)
                by_node[(level, nid)] = key
                for x in members:
                    road_of[x] = key
                queue.append(key)
    return road_of, [roads[k] for k in roads]


def sample_differences(items, state):
    """How the world differs from the rule written out again (`simulate`): the road of a house, or a road (id, parent, level, node). Empty: they agree."""
    road_of, roads = simulate(items, 40, 10)
    out = [f"the house {h} stands on {state.road_of[h]!r}, not {road!r}" for h, road in road_of.items() if state.road_of.get(h) != road]
    opened = [(k, n["parent"], n["topic"]["level"], n["topic"]["id"]) for k, n in state.nodes.items()]
    return out + ([] if opened == [tuple(r) for r in roads] else ["the roads opened are not the same, or not in the same order"])


def test_the_rule_auto_on_the_sample_agrees_with_the_rule_written_out_again(auto_sample, sample_items):
    assert sample_differences(sample_items, auto_sample.state) == []


def refold_sample(items):
    h = Hand({"max": 40, "min": 10, "auto": True})
    h.add_items(items)
    return h.state


def shallowest_landing(world, item):
    from bibliopolis.suggest import _descent

    found = _descent(world, item["openalex"])
    return min(found, key=lambda r: (found[r][0], found[r][1])) if found else None


@pytest.mark.parametrize("fault", ["shallowest road", "no landing", "root zone only"])
def test_a_planted_fault_in_the_rule_auto_turns_the_agreement_with_the_rule_written_out_red_and_the_world_ends_green(fault, monkeypatch, sample_items):
    import bibliopolis.hand as hand_module

    if fault == "shallowest road":
        monkeypatch.setattr(hand_module, "landing", shallowest_landing)
    elif fault == "no landing":
        monkeypatch.setattr(hand_module, "landing", lambda world, item: None)
    else:  # looks at the root zone after each arrival, not at the place the house landed on and the roads the split opens
        real = hand_module.State.settle
        monkeypatch.setattr(hand_module.State, "settle", lambda self, w, e, start, touched, opened: real(self, w, e, None, touched, opened))
    assert sample_differences(sample_items, refold_sample(sample_items)), fault
    monkeypatch.undo()
    assert sample_differences(sample_items, refold_sample(sample_items)) == []


def depth(state, key):
    d = 1
    while state.nodes[key]["parent"] is not None:
        key, d = state.nodes[key]["parent"], d + 1
    return d


def test_the_rule_auto_on_the_sample_builds_the_tree_of_openalex_level_by_level(auto_sample, sample_items):
    """The first ring holds the domains (6 in the invented topics of the sample; 4 in OpenAlex), the next rings the fields, subfields and topics below them. These numbers are
    pinned: a change to the rule moves them."""
    state = auto_sample.state
    assert len(state.items) == 600 and hand_problems(state) == []
    by_ring = {r: sum(1 for k in state.nodes if depth(state, k) == r) for r in (1, 2, 3, 4)}
    assert by_ring == {1: 6, 2: 10, 3: 6, 4: 1} and len(state.nodes) == 23
    assert {n["topic"]["level"] for k, n in state.nodes.items() if depth(state, k) == 1} == {"domain"}
    for k, n in state.nodes.items():  # the level of a road is its ring: a node is one level below the node of the road it is below
        assert ORDER.index(n["topic"]["level"]) == depth(state, k) - 1 and n["name"] == n["topic"]["name"]
    assert len(roads_by_node(state)) == len(state.nodes)  # no two roads for one node
    assert state.count(None) == 15  # the 15 arrivals that no road took: 'methods' has 40 houses and the root zone never passed 40 with them
    assert crowded(state) == [{"at": "auto:575", "name": "Topic networks", "houses": 44}]  # a topic is not split: its 44 houses stay on one road
    chronicle = [e for e in state.city()["world"]["chronicle"] if "from" in e]
    assert len(chronicle) == 23 and all(e["trigger"] == "add_item" and len(e["houses"]) >= 10 for e in chronicle) and chronicle[-1]["event_id"] == 593
    assert sum(1 for e in chronicle if e["from"] == "place:root") == 6  # the six domains come from the root zone; the others from the road above them
    assert stability_violations(auto_sample.journal.events, auto_sample.journal.rule) == []
    assert landing_violations(auto_sample.journal.events, auto_sample.journal.rule) == []


def test_no_house_of_the_sample_is_underground_that_a_road_would_take_and_no_crowded_road_has_a_group_left_to_split_off(auto_sample):
    state = auto_sample.state
    assert all(landing(state, state.items[h]) is None for h in state.houses_at(None))  # no road would take an underground house now
    for road in state.nodes:
        if state.count(road) > state.rule["max"]:
            assert suggest_road(state, road) is None
    assert state.count(None) <= state.rule["max"]
