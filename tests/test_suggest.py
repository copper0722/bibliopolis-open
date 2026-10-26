"""Suggestions and the rule `auto` (bibliopolis.suggest): the largest group that shares an OpenAlex topic, the road a house belongs on, the places that are crowded."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hand_support import Hand, hand_problems, hid, play, stability_violations, topic
from support import sample

from bibliopolis import inputs
from bibliopolis.events import LEVELS, Refusal
from bibliopolis.suggest import Group, crowded, largest_group, suggest_file, suggest_road
from bibliopolis.tree import TreeView, major_tag

ROOT = Path(__file__).resolve().parents[1]
T = topic


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


# ---------------------------------------------------------------------------------------------- the group ----
def test_the_group_is_taken_at_the_most_specific_level_that_still_gives_the_least():
    h = Hand()
    h.add(8, T(1, 1, 1, 1))
    h.add(4, T(1, 1, 1, 2))  # 8 and 4 share a topic each; all 12 share a subfield
    s = suggest_road(h.state, None)
    assert (s["level"], s["topic"], s["name"], s["at"]) == ("subfield", {"id": "ex:d1.f1.s1", "name": "Subfield 1.1.1"}, "Subfield 1.1.1", None)
    assert s["houses"] == houses(1, 12)
    h = Hand()
    h.add(10, T(1, 1, 1, 1))
    h.add(2, T(1, 1, 1, 2))  # ten share a topic: the group is those ten, not the twelve that share the subfield
    s = suggest_road(h.state, None)
    assert (s["level"], s["topic"]["id"], s["name"], s["houses"]) == ("topic", "ex:d1.f1.s1.t1", "Topic 1.1.1.1", houses(1, 10))


def test_it_falls_back_through_subfield_and_field_to_the_domain():
    h = Hand()
    for sub in (1, 2):
        h.add(4, T(1, 1, sub, 1))  # two subfields of one field: 4 + 4
    h.add(3, T(1, 2, 1, 1))  # a second field of the domain: 3
    s = suggest_road(h.state, None)
    assert s["level"] == "domain" and s["topic"]["id"] == "ex:d1" and s["houses"] == houses(1, 11)  # 8 in the field (under 10), 11 in the domain
    h.add(2, T(1, 1, 1, 3))
    s = suggest_road(h.state, None)
    assert s["level"] == "field" and s["topic"]["id"] == "ex:d1.f1" and s["houses"] == [*houses(1, 8), hid(12), hid(13)]  # 10 in the field now: more specific than the domain


def test_the_largest_group_wins_and_of_two_as_large_the_lower_topic_id():
    h = Hand()
    h.add(10, T(1, 1, 1, 2))
    h.add(10, T(1, 1, 1, 1))
    assert suggest_road(h.state, None)["topic"]["id"] == "ex:d1.f1.s1.t1" and suggest_road(h.state, None)["houses"] == houses(11, 20)  # a tie: the lower id
    h.add(11, T(2, 1, 1, 1))
    s = suggest_road(h.state, None)
    assert s["topic"]["id"] == "ex:d2.f1.s1.t1" and s["houses"] == houses(21, 31)  # a group of 11 beats the two of 10, though its id is the highest


def test_a_house_is_in_the_group_of_every_topic_it_carries_the_primary_one_and_up_to_two_more():
    h = Hand()
    h.add(6, T(1, 1, 1, 1))
    h.add(6, T(1, 1, 1, 2), T(1, 1, 1, 1))  # primary t2, and t1 as a second topic
    s = suggest_road(h.state, None)
    assert s["topic"]["id"] == "ex:d1.f1.s1.t1" and s["houses"] == houses(1, 12)  # all twelve carry t1; only six carry t2
    h = Hand()
    h.add(10, T(1, 1, 1, 1), T(2, 1, 1, 1), T(2, 2, 2, 2))  # three topics each: three groups of ten, the lowest id wins
    assert suggest_road(h.state, None)["topic"]["id"] == "ex:d1.f1.s1.t1"


def test_a_house_counts_once_for_a_topic_it_names_twice_at_a_wider_level():
    h = Hand()
    h.add(5, T(1, 1, 1, 1), T(1, 1, 1, 2))  # two topics of one subfield: the house is one house of that subfield
    h.add(5, T(1, 1, 1, 3))
    s = suggest_road(h.state, None)
    assert s["level"] == "subfield" and s["houses"] == houses(1, 10)  # ten houses, not fifteen


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
    assert suggest_road(h.state, None)["houses"] == houses(1, 12)
    h.open("a", "A", None, houses(1, 10))
    assert suggest_road(h.state, None) is None  # two houses are left in the root zone
    s = suggest_road(h.state, "a")
    assert (s["at"], s["houses"]) == ("a", houses(1, 10))
    h.open("a1", s["name"], "a", s["houses"])  # a suggestion is a road opened as it stands
    assert suggest_road(h.state, "a") is None and suggest_road(h.state, "a1")["houses"] == houses(1, 10)
    with pytest.raises(Refusal, match="there is no road 'x'"):
        suggest_road(h.state, "x")


def mixed_town():
    h = Hand()
    h.add(7, T(1, 1, 1, 1))
    h.add(6, T(1, 1, 1, 2), T(2, 1, 1, 1))
    return h


def test_a_suggestion_is_plain_data_that_open_road_takes_and_the_same_world_gives_the_same_one_in_another_process():
    h = mixed_town()
    s = suggest_road(h.state, None)
    assert json.loads(json.dumps(s)) == s and list(s) == ["at", "level", "topic", "name", "houses"]
    h.open("r", s["name"], s["at"], s["houses"])
    assert h.state.nodes["r"]["name"] == s["name"] and h.state.count("r") == len(s["houses"])
    code = ("import sys, json; sys.path.insert(0, 'tests'); import hand_support as hs; from bibliopolis.suggest import suggest_road; h = hs.Hand(); "
            "h.add(7, hs.topic(1, 1, 1, 1)); h.add(6, hs.topic(1, 1, 1, 2), hs.topic(2, 1, 1, 1)); print(json.dumps(suggest_road(h.state, None)))")
    outs = set()
    for seed in ("0", "4242"):
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"},
                              capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        outs.add(done.stdout.strip())
    assert outs == {json.dumps(s)}


def test_the_name_is_the_one_the_first_house_that_carries_the_topic_writes():
    a, b = T(1, 1, 1, 1), T(1, 1, 1, 1)
    b["topic"] = {"id": "ex:d1.f1.s1.t1", "name": "Another spelling"}
    out = largest_group({hid(i): [a if i == 1 else b] for i in range(1, 11)}, 10)
    assert out == Group("topic", "ex:d1.f1.s1.t1", "Topic 1.1.1.1", houses(1, 10))
    assert largest_group({}, 1) is None and largest_group({hid(1): []}, 1) is None


# --------------------------------------------------------------------------------------------- the filing ----
def two_roads():
    h = Hand()
    h.add(12, T(1, 1, 1, 1))  # road a
    h.add(12, T(2, 1, 1, 1))  # road b
    h.open("a", "A", None, houses(1, 12))
    h.open("b", "B", None, houses(13, 24))
    return h


def test_a_house_goes_to_the_road_whose_houses_share_the_most_topics_with_it_and_the_confidence_says_how_clear_it_is():
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


def test_two_roads_that_share_the_same_make_the_confidence_the_part_of_the_one_that_wins_and_an_older_road_wins_a_tie():
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


def test_a_house_on_a_road_is_moved_only_to_a_road_that_fits_it_better_than_its_own():
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


# ---------------------------------------------------------------------------------------------- the rule auto ----
def auto_town(max_houses=40, min_houses=10):
    return Hand({"max": max_houses, "min": min_houses, "auto": True})


def test_the_rule_opens_a_road_for_the_largest_group_when_the_41st_house_arrives_and_names_it_after_the_topic():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    state = h.state
    assert not state.nodes and state.count(None) == 40  # 40 houses: nothing yet
    h.add(1, T(1, 1, 1, 1))  # the 41st: the root zone holds more than 40
    state = h.state
    assert list(state.nodes) == ["auto:41"] and state.nodes["auto:41"] == {"key": "auto:41", "name": "Topic 1.1.1.1", "parent": None}
    assert state.houses_at("auto:41") == [*houses(1, 20), hid(41)] and state.count(None) == 20
    assert hand_problems(state) == []
    entry = state.city()["world"]["chronicle"][-1]
    assert (entry["trigger"], entry["from"], entry["to"], entry["label"], entry["count_before"], entry["count_after"], entry["event_id"]) == (
        "add_item", "place:root", "place:tag:auto:41", "Topic 1.1.1.1", 41, 20, 41)
    assert state.city()["composition"]["ring1"][0]["label"] == "Topic 1.1.1.1"


def test_the_houses_that_stay_keep_their_lots_when_the_rule_opens_a_road():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    from hand_support import lot_snapshot

    before = lot_snapshot(h.state)
    h.add(1, T(1, 1, 1, 1))
    after = lot_snapshot(h.state)
    assert all(after[x] == before[x] for x in houses(21, 40))  # the twenty of the second topic stay on the lots they have, at slots 20 to 39


def test_a_road_that_the_rule_opened_is_a_road_like_any_other_it_is_renamed_and_filed_onto_and_undo_keeps_the_log_whole():
    h = auto_town()
    h.add(20, T(1, 1, 1, 1))
    h.add(20, T(2, 1, 1, 1))
    h.add(1, T(1, 1, 1, 1))  # event 41 opens auto:41
    h.rename("auto:41", "Mine")
    h.file(hid(30), "auto:41")
    assert h.state.nodes["auto:41"]["name"] == "Mine" and h.state.road_of[hid(30)] == "auto:41"
    with pytest.raises(Refusal, match=r"event 41 cannot be undone: event 42 \(rename_road\) depends on it"):
        h.undo(41)
    h.undo(43)
    h.undo(42)
    h.undo(41)  # the arrival, and the road it opened, are taken back together
    assert list(h.state.nodes) == [] and hid(41) not in h.state.items and hand_problems(h.state) == []


def test_two_roads_in_one_arrival_are_auto_n_and_auto_n_dot_2():
    h = Hand({"max": 40, "min": 10, "auto": False})
    for k in range(3):
        h.add(10, T(k + 1, 1, 1, 1))
    h.rule(12, 10, True)
    h.add(1, T(1, 1, 1, 1))  # 31 houses in the root zone, 12 at most: two groups leave
    assert list(h.state.nodes) == ["auto:32", "auto:32.2"]  # (event 31 was the rule, event 32 the arrival)
    assert h.state.count(None) == 10 and hand_problems(h.state) == []
    assert [e["trigger"] for e in h.state.city()["world"]["chronicle"][1:]] == ["add_item", "add_item"]


def test_a_group_that_reaches_the_least_only_at_a_wider_level_is_named_after_that_level():
    h = auto_town(12, 6)
    for sub in (1, 2, 3):
        h.add(4, T(1, 1, sub, 1))  # three subfields of four: the field has twelve
    h.add(1, T(1, 1, 1, 2))
    state = h.state
    assert state.nodes["auto:13"]["name"] == "Field 1.1" and state.count(None) == 0 and state.count("auto:13") == 13


def test_when_no_group_reaches_the_least_nothing_happens_and_the_root_zone_stays_crowded():
    h = auto_town()
    for i in range(41):
        h.add(1, T(i + 1, 1, 1, 1))  # a domain, a field, a subfield and a topic of its own in every house: no group at any level
    assert not h.state.nodes and h.state.count(None) == 41
    assert crowded(h.state) == [{"at": None, "name": None, "houses": 41}]
    assert not any(e["trigger"] == "add_item" for e in h.state.city()["world"]["chronicle"])


def test_when_the_first_ring_is_full_the_arrival_is_taken_and_the_rule_opens_nothing():
    h = Hand({"max": 12, "min": 5, "auto": False})
    for k in range(13):
        h.add(5, T(k + 1, 1, 1, 1))
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    h.rule(12, 5, True)
    h.add(13, T(20, 1, 1, 1))  # thirteen houses of one topic: the rule would open a road, and the first ring has no direction left
    assert h.state.count(None) == 13 and len(h.state.nodes) == 13 and hand_problems(h.state) == []
    assert crowded(h.state) == [{"at": None, "name": None, "houses": 13}]


def test_the_rule_opens_nothing_without_auto_and_a_set_rule_alone_opens_nothing_either():
    h = Hand({"max": 12, "min": 5, "auto": False})
    h.add(20, T(1, 1, 1, 1))
    assert not h.state.nodes
    h.rule(12, 5, True)
    assert not h.state.nodes and h.state.count(None) == 20  # applied after each arrival, not when it is switched on
    h.add(1, T(1, 1, 1, 1))
    assert list(h.state.nodes) == ["auto:22"]


@pytest.mark.parametrize("seed", range(12))
def test_a_random_player_with_the_rule_on_leaves_a_sound_stable_world(seed):
    j = play(seed, steps=200, auto=True)
    assert hand_problems(j.state) == []
    assert stability_violations(j.events, j.rule) == []


def test_the_random_player_with_the_rule_on_does_open_roads_by_the_rule():
    opened = sum(1 for seed in range(12) for k in play(seed, steps=200, auto=True).state.nodes if k.startswith("auto:"))
    assert opened >= 10


# -------------------------------------------------------------------------------------------- the sample ----
def oa_of(path):
    """An invented OpenAlex-shaped topic for a node of the sample tree, from its path (the root first): the root is the domain, its child the field, and so on; a node
    that is not deep enough is its own subfield and topic."""
    pick = lambda i: path[min(i, len(path) - 1)]  # noqa: E731
    return {"domain": {"id": f"ex:domain:{pick(0)}", "name": f"Domain {pick(0)}"}, "field": {"id": f"ex:field:{pick(1)}", "name": f"Field {pick(1)}"},
            "subfield": {"id": f"ex:subfield:{pick(2)}", "name": f"Subfield {pick(2)}"}, "topic": {"id": f"ex:topic:{path[-1]}", "name": f"Topic {path[-1]}"}}


@pytest.fixture(scope="module")
def sample_items():
    """The 600 items of the sample as items of a world, in arrival order, with the invented topics of the nodes they are filed under (the deepest first)."""
    tree, library = sample()
    checked = inputs.read_tree(tree)
    items = inputs.read_library(library, checked)
    view = TreeView(checked)

    def path(node):
        out = []
        while node is not None:
            out.append(node)
            node = view.parent(node)
        return out[::-1]

    out = []
    for it in items:
        main = major_tag(view, it)
        order = ([main] if main else []) + [t for t in it["topics"] if t != main]
        out.append({"id": it["id"], "title": it["title"], "authors": it["authors"], "year": it["year"], "doi": it["doi"], "type": it["type"],
                    "openalex": [oa_of(path(t)) for t in order[:3]]})
    return out


def brute_force(items, least):
    for level in LEVELS:
        groups = {}
        for it in items:
            for tid in {t[level]["id"] for t in it["openalex"]}:
                groups.setdefault(tid, []).append(it["id"])
        if groups:
            tid = sorted(groups, key=lambda k: (-len(groups[k]), k))[0]
            if len(groups[tid]) >= least:
                return level, tid, groups[tid]
    return None


@pytest.fixture(scope="module")
def sample_world(sample_items):
    h = Hand()
    h.add_items(sample_items)
    return h


def test_the_suggestion_on_the_sample_is_the_largest_group_at_the_most_specific_level(sample_world, sample_items):
    state = sample_world.state
    assert len(state.items) == 600 and state.count(None) == 600
    s = suggest_road(state, None)
    level, tid, members = brute_force(sample_items, 10)
    assert (s["level"], s["topic"]["id"], s["houses"]) == (level, tid, members)
    assert s["level"] == "topic" and s["topic"]["id"] == "ex:topic:networks" and len(s["houses"]) >= 44  # the topic with the most houses: 44 of its own, and more that list it second
    by_id = {it["id"]: it for it in sample_items}
    assert all(any(t["topic"]["id"] == tid for t in by_id[x]["openalex"]) for x in s["houses"])  # every house of the group carries the topic ...
    assert {x for x in by_id if any(t["topic"]["id"] == tid for t in by_id[x]["openalex"])} == set(s["houses"])  # ... and every house that carries it is in the group
    assert crowded(state) == [{"at": None, "name": None, "houses": 600}]


def test_taking_every_suggestion_in_turn_builds_a_sound_town_of_roads_that_each_took_at_least_the_least(sample_items):
    h = Hand()
    h.add_items(sample_items)
    opened = 0
    while True:
        s = suggest_road(h.state, None)
        if s is None:
            break
        try:
            h.open(f"s{opened}", s["name"], None, s["houses"])
        except Refusal as why:
            assert why.code == "ring1_full" and opened == 13  # the first ring is full: that is the one reason to stop
            break
        opened += 1
    assert opened >= 10
    assert hand_problems(h.state) == []
    assert all(len(e["houses"]) >= 10 for e in h.state.city()["world"]["chronicle"] if "from" in e)


@pytest.fixture(scope="module")
def auto_sample(sample_items):
    h = Hand({"max": 40, "min": 10, "auto": True})
    h.add_items(sample_items)
    return h


def test_the_rule_auto_on_the_sample_opens_roads_named_after_topics_until_the_first_ring_is_full(auto_sample, sample_items):
    """What the rule does with a stream of 600 items that all arrive in the root zone: it opens a road each time the root zone passes its limit, at the most specific level
    that gives a group of 10, and the first ring (13 roads) is full by the 180th arrival; the rest stay underground. (Arrivals are not filed onto a road that is there: the
    houses of a domain that a road took gather in the root zone again, and a second road of the same name opens. That is the rule as the page describes it.)"""
    state = auto_sample.state
    assert len(state.items) == 600 and hand_problems(state) == []
    roads = [k for k in state.nodes if k.startswith("auto:")]
    assert len(roads) == len(state.nodes) == 13 and all(state.nodes[k]["parent"] is None for k in roads)
    chronicle = [e for e in state.city()["world"]["chronicle"] if "from" in e]
    assert all(e["trigger"] == "add_item" and e["from"] == "place:root" and len(e["houses"]) >= 10 for e in chronicle) and len(chronicle) == 13
    names = {oa["topic"]["name"] for it in sample_items for oa in it["openalex"]} | {oa[lv]["name"] for it in sample_items for oa in it["openalex"] for lv in LEVELS}
    assert all(state.nodes[k]["name"] in names for k in roads)  # a road is named after a topic of the houses
    assert state.count(None) == 453 and crowded(state) == [{"at": None, "name": None, "houses": 453}]  # the arrivals after the 13th road stay underground
    assert [e["event_id"] for e in chronicle][-1] == 180
    assert stability_violations(auto_sample.journal.events, auto_sample.journal.rule) == []
