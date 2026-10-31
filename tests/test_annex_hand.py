"""Items that exist for another item in a world built by hand (docs/world.md, "An item that exists for another item"): an item whose house stands is an annex at once; one whose house has
not arrived waits as an ordinary house and is absorbed when the house arrives; the event `annex` links two houses later. An annex has no lot and counts for nothing against `max` or
`min`; every other house keeps its lot, byte for byte; an undo is the fold of the log without the event."""

import json

import pytest
import refusal_cases as rc
from hand_support import (Hand, every_entry, hand_problems, hid, houses, item, journal_value, lap_slots, lot_snapshot, play_annexes, ring_cells, stability_violations, stamp,
                          text_problems, topic)
from support import first_free

from bibliopolis import events as ev
from bibliopolis import layout as lay
from bibliopolis.events import Refusal
from bibliopolis.hand import State, fold
from bibliopolis.journal import Journal, dumps_world, read_world, world_document
from bibliopolis.suggest import crowded, suggest_file, suggest_merge, suggest_road


def town(n=3, rule=None):
    h = Hand(rule or {"max": 12, "min": 4, "auto": False})
    h.add(n)
    return h


def annex_record(state, house):
    return state.doc["places"][lay.article_place(house)]


def lots_except(state, *skip):
    """house id -> its lot record as the city shows it, but for the houses in `skip`."""
    return {h: lot for h, lot in lot_snapshot(state).items() if h not in skip}


def entries_of(state, key):
    return [e for e in state.doc["chronicle"] if key in e]


# --------------------------------------------------------------------------------------------- at once ----
def test_an_item_that_exists_for_a_house_that_stands_is_an_annex_at_once_with_no_lot_and_no_road():
    h = town(3)
    before = lots_except(h.state)
    event = h.add(1, annex_of=hid(2), annex_form="wing")
    state = h.state
    assert event == [hid(4)] and state.annexes == {hid(4): {"parent": hid(2), "form": "wing"}} and hid(4) not in state.items and hid(4) not in state.road_of
    assert annex_record(state, hid(4)) == {"kind": "annex", "article": hid(4), "parent": lay.article_place(hid(2)), "form": "wing", "rank": 1, "seq": 4}
    assert lots_except(state) == before and state.count(None) == 3  # the houses stand where they stood, and the ring road holds three
    (entry,) = entries_of(state, "annex")
    assert entry == {"n": 1, "event_id": 4, "seq": 4, "trigger": "add_item", "annex": hid(4), "parent": hid(2), "form": "wing", "at": stamp(4)}
    assert state.effects[4] == {"houses": [hid(4)], "roads": []} and hand_problems(state) == [] and text_problems(state) == []
    assert state.city()["counts"]["annex"] == 1 and state.city()["composition"]["buildings"] == 4 and state.city()["world"]["houses"] == 3


def test_the_item_is_kept_with_its_two_keys_last_in_the_log_and_in_the_world_file():
    h = town(2)
    h.add(1, topic(1, 1, 1, 1), annex_of=hid(1), annex_form="mailbox")
    kept = h.journal.events[-1]["payload"]["item"]
    assert list(kept)[-3:] == ["openalex", "annex_of", "annex_form"] and (kept["annex_of"], kept["annex_form"]) == (hid(1), "mailbox")
    doc = json.loads(dumps_world(world_document(h.journal)))
    assert doc["items"][-1] == kept and read_world(doc).state.annexes == h.state.annexes
    assert dumps_world(world_document(read_world(doc))) == dumps_world(world_document(h.journal))  # a file read and written again is the same bytes


def test_the_annexes_of_one_house_and_form_are_ranked_by_arrival_and_a_house_with_annexes_stays_where_it_is():
    h = town(4)
    for form in ("wing", "mailbox", "wing", "wing", "wing", "wing", "wing"):
        h.add(1, annex_of=hid(3), annex_form=form)
    ranks = {a: (annex_record(h.state, a)["form"], annex_record(h.state, a)["rank"]) for a in h.state.annexes}
    assert list(ranks.values()) == [("wing", 1), ("mailbox", 1), ("wing", 2), ("wing", 3), ("wing", 4), ("wing", 5), ("wing", 6)]
    assert hand_problems(h.state) == [] and h.state.count(None) == 4


@pytest.mark.parametrize("auto", [False, True])
def test_an_annex_is_not_landed_and_counts_for_nothing_against_max(auto):
    h = Hand({"max": 6, "min": 3, "auto": auto})
    h.add(6, topic(1, 1, 1, 1))
    h.add(10, topic(1, 1, 1, 1), annex_of=hid(2), annex_form="wing")  # ten items that exist for one house, and carry its topic
    assert h.state.count(None) == 6 and crowded(h.state) == [] and len(h.state.annexes) == 10 and not h.state.nodes
    assert suggest_road(h.state, None)["houses"] == houses(1, 6)  # a road would be for the six houses: the ten annexes carry the topic and are in no group
    h.add(1, topic(1, 1, 1, 1))  # the seventh house: now the ring road is over `max`
    assert [c["houses"] for c in crowded(h.state)] == [7] and hand_problems(h.state) == []  # (under `auto` the seven houses open roads down to their topic, where the last holds them: a topic is not split)
    assert (len(h.state.nodes) > 0) is auto and all(hid(k) in h.state.annexes for k in range(7, 17)) and len(h.state.annexes) == 10  # the annexes stay as they were


def test_an_annex_stays_with_its_house_when_the_house_is_filed_a_road_opens_from_it_and_roads_move_and_merge():
    h = Hand({"max": 40, "min": 5, "auto": False})
    h.add(20)
    h.add(1, annex_of=hid(6), annex_form="wing")
    h.add(1, annex_of=hid(6), annex_form="mailbox")
    h.add(1, annex_of=hid(7), annex_form="wing")
    kept = {a: dict(annex_record(h.state, a)) for a in h.state.annexes}
    h.open("a", "A", None, houses(1, 8))  # the houses 6 and 7 move onto a road
    h.open("b", "B", None, houses(9, 15))
    assert {a: annex_record(h.state, a) for a in h.state.annexes} == kept and h.state.lots()[hid(6)]["street"] == "place:tag:a"
    h.file(hid(6), "b")
    h.open("a1", "A one", "a", [hid(1), hid(2), hid(3), hid(4), hid(7)])
    h.move("a1", "b")
    h.merge("m", "M", ["a", "b"])
    assert {a: annex_record(h.state, a) for a in h.state.annexes} == kept and hand_problems(h.state) == [] and text_problems(h.state) == []
    assert stability_violations(h.journal.events, h.journal.rule) == []


# -------------------------------------------------------------------------------------- waiting and absorbed ----
def test_an_item_whose_house_has_not_arrived_is_an_ordinary_house_that_waits_and_is_absorbed_when_the_house_arrives():
    h = town(5)
    h.add(1, annex_of=hid(9), annex_form="mailbox")  # h0006 waits for h0009
    waiting = h.state
    assert hid(6) in waiting.items and waiting.road_of[hid(6)] is None and waiting.annexes == {} and hid(6) in lot_snapshot(waiting)
    h.add(2)
    cells_before, others = h.state.doc["places"][lay.article_place(hid(6))]["street"], lots_except(h.state, hid(6))
    h.add(1)  # h0009 arrives
    state = h.state
    assert hid(6) not in state.items and hid(6) not in state.road_of and state.annexes == {hid(6): {"parent": hid(9), "form": "mailbox"}}
    assert annex_record(state, hid(6)) == {"kind": "annex", "article": hid(6), "parent": lay.article_place(hid(9)), "form": "mailbox", "rank": 1, "seq": 6}  # (it keeps its arrival number)
    assert lots_except(state, hid(9)) == {k: v for k, v in others.items()}, "every other house keeps its lot, byte for byte"
    assert hid(6) not in lot_snapshot(state) and cells_before == "place:root"  # (it stood on the ring road)
    (entry,) = entries_of(state, "absorbed")
    assert entry == {"n": 1, "event_id": 9, "seq": 9, "trigger": "add_item", "absorbed": hid(6), "parent": hid(9), "form": "mailbox", "left": "place:root", "at": stamp(9)}
    assert state.effects[9] == {"houses": [hid(9), hid(6)], "roads": []} and hand_problems(state) == [] and text_problems(state) == []


def test_the_lot_that_an_absorbed_house_leaves_is_free_for_the_next_house_on_the_ring_road():
    h = town(5)
    h.add(1, annex_of=hid(8), annex_form="wing")  # h0006 waits
    h.add(1)
    freed = ring_cells(h.state)[hid(6)]
    h.add(1)  # h0008 arrives: h0006 is absorbed, and the first free slot of the ring in fill order is the one it left or one that is earlier in the order
    assert hid(6) not in ring_cells(h.state) and freed not in set(ring_cells(h.state).values())
    want = first_free(lap_slots(h.state), set(ring_cells(h.state).values()))
    h.add(1)
    assert ring_cells(h.state)[hid(9)] == want and want[0] == 0
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_an_absorbed_house_on_a_road_leaves_its_lot_reserved_and_the_other_houses_of_the_road_keep_theirs():
    h = Hand({"max": 40, "min": 5, "auto": False})
    h.add(9)
    h.add(1, annex_of=hid(30), annex_form="wing")  # h0010 waits
    h.add(9)
    h.open("a", "A", None, houses(1, 12))  # the waiting house goes onto the road with eleven others
    road = h.state.doc["places"]["place:tag:a"]
    lots_before, slot = dict(lot_snapshot(h.state)), lot_snapshot(h.state)[hid(10)]["slot"]
    held, free = road["lots"], road["reserved"]
    h.add(11)  # the houses 20 to 30: h0030 arrives
    state, road = h.state, h.state.doc["places"]["place:tag:a"]
    assert state.annexes == {hid(10): {"parent": hid(30), "form": "wing"}} and (road["lots"], road["reserved"]) == (held - 1, free + 1)
    assert state.doc["places"][lay.reserved_place(road["rib"]["block"], slot)]["kind"] == "reserved"  # the lot stays reserved
    after = lot_snapshot(state)
    assert all(after[k] == v for k, v in lots_before.items() if k != hid(10)) and hand_problems(state) == []


def test_every_house_that_waited_is_absorbed_in_the_order_it_arrived_each_with_an_entry_and_a_rank():
    h = town(2)
    for form in ("wing", "mailbox", "wing", "wing"):
        h.add(1, annex_of=hid(12), annex_form=form)
    h.add(5)
    h.add(1)  # h0012
    state = h.state
    assert [e["absorbed"] for e in entries_of(state, "absorbed")] == [hid(3), hid(4), hid(5), hid(6)] and [e["event_id"] for e in entries_of(state, "absorbed")] == [12] * 4
    assert [(annex_record(state, a)["form"], annex_record(state, a)["rank"]) for a in state.annexes] == [("wing", 1), ("mailbox", 1), ("wing", 2), ("wing", 3)]
    assert list(state.annexes) == [hid(3), hid(4), hid(5), hid(6)] and state.effects[12]["houses"] == [hid(12), hid(3), hid(4), hid(5), hid(6)]


def test_a_house_that_waits_may_stand_on_a_road_before_its_house_arrives_and_is_absorbed_from_there():
    h = Hand({"max": 40, "min": 5, "auto": False})
    h.add(5)
    h.add(1, annex_of=hid(30), annex_form="wing")  # h0006 waits
    h.add(4)
    h.open("a", "A", None, houses(1, 9))  # h0006 is one of the nine houses of a road
    h.add(20)  # h0030 arrives
    assert hid(30) in h.state.items and h.state.annexes == {hid(6): {"parent": hid(30), "form": "wing"}} and hand_problems(h.state) == []
    assert h.state.doc["places"]["place:tag:a"]["lots"] == 8 and stability_violations(h.journal.events, h.journal.rule) == []


def test_houses_that_waited_for_an_annex_stay_houses_and_an_annex_that_waits_takes_none():
    h = town(2)
    h.add(1, annex_of=hid(6), annex_form="wing")  # h0003 waits for h0006
    h.add(2)
    h.add(1, annex_of=hid(1), annex_form="mailbox")  # h0006 arrives as an annex itself (of h0001, which stands): it is no house, and h0003 cannot be absorbed into it
    assert hid(3) in h.state.items and h.state.annexes == {hid(6): {"parent": hid(1), "form": "mailbox"}} and hand_problems(h.state) == []
    assert entries_of(h.state, "absorbed") == []


def test_a_house_that_waits_is_no_house_for_another_to_stand_beside_while_it_waits():
    h = town(2)
    h.add(1, annex_of=hid(9), annex_form="wing")  # h0003 waits for h0009
    made = rc.raised(lambda: h.add(1, annex_of=hid(3), annex_form="mailbox"))
    assert (made.code, made.params) == ("annex_of_annex", {"house": hid(4), "parent": hid(3), "above": hid(9)})
    made = rc.raised(lambda: h.event("annex", {"house": hid(1), "parent": hid(3), "form": "wing"}))
    assert (made.code, made.params) == ("annex_of_annex", {"house": hid(1), "parent": hid(3), "above": hid(9)})


# --------------------------------------------------------------------------------------- a link learned later ----
def test_the_event_annex_takes_a_house_off_its_lot_and_it_stands_beside_the_other_house_from_then_on():
    h = town(6)
    before = lots_except(h.state, hid(2))
    h.event("annex", {"house": hid(2), "parent": hid(5), "form": "wing"})
    state = h.state
    assert state.annexes == {hid(2): {"parent": hid(5), "form": "wing"}} and hid(2) not in state.items and hid(2) not in state.road_of
    assert lots_except(state) == before and annex_record(state, hid(2))["seq"] == 2
    (entry,) = entries_of(state, "absorbed")
    assert entry == {"n": 1, "event_id": 7, "seq": 6, "trigger": "annex", "absorbed": hid(2), "parent": hid(5), "form": "wing", "left": "place:root", "at": stamp(7)}
    assert state.effects[7] == {"houses": [hid(2)], "roads": []} and hand_problems(state) == []


def test_a_link_learned_for_an_item_that_arrived_before_the_annexes_that_stand_takes_the_first_rank_and_moves_theirs_up():
    h = town(3)
    h.add(1, annex_of=hid(1), annex_form="wing")  # h0004
    h.add(1, annex_of=hid(1), annex_form="wing")  # h0005
    assert [annex_record(h.state, a)["rank"] for a in (hid(4), hid(5))] == [1, 2]
    h.event("annex", {"house": hid(3), "parent": hid(1), "form": "wing"})  # h0003 arrived before both
    assert [annex_record(h.state, a)["rank"] for a in (hid(3), hid(4), hid(5))] == [1, 2, 3]
    h.add(1, annex_of=hid(1), annex_form="mailbox")
    assert annex_record(h.state, hid(6))["rank"] == 1 and hand_problems(h.state) == []


def test_a_house_that_waits_for_one_house_may_be_linked_to_another_and_is_then_not_absorbed_by_the_first():
    h = town(3)
    h.add(1, annex_of=hid(8), annex_form="wing")  # h0004 waits for h0008
    h.event("annex", {"house": hid(4), "parent": hid(1), "form": "mailbox"})
    h.add(3)
    h.add(1)  # h0008
    assert h.state.annexes == {hid(4): {"parent": hid(1), "form": "mailbox"}} and entries_of(h.state, "absorbed")[0]["trigger"] == "annex" and len(entries_of(h.state, "absorbed")) == 1
    assert hand_problems(h.state) == []


# ----------------------------------------------------------------------------------------------- refusals ----
def refused(h, act):
    before = journal_value(h.journal)
    made = rc.raised(act)
    assert journal_value(h.journal) == before, "a refusal leaves the world and the log as they were"
    return made.code, made.params


def test_each_refusal_of_an_annex_has_its_own_id_and_leaves_the_world_as_it_was():
    h = town(4)
    h.add(1, annex_of=hid(1), annex_form="wing")  # h0005 stands beside h0001
    h.add(1, annex_of=hid(30), annex_form="mailbox")  # h0006 waits for h0030
    new = lambda **keys: h.event("add_item", {"item": item(7, **keys)})  # noqa: E731 - the item h0007, which none of these makes
    cases = [
        (lambda: new(annex_of=hid(7), annex_form="wing"), ("annex_of_itself", {"house": hid(7)})),
        (lambda: new(annex_of=hid(5), annex_form="wing"), ("annex_of_annex", {"house": hid(7), "parent": hid(5), "above": hid(1)})),
        (lambda: new(annex_of=hid(6), annex_form="wing"), ("annex_of_annex", {"house": hid(7), "parent": hid(6), "above": hid(30)})),
        (lambda: h.event("add_item", {"item": h.state.items[hid(2)]}), ("house_exists", {"house": hid(2)})),
        (lambda: h.event("add_item", {"item": item(5)}), ("house_exists", {"house": hid(5)})),  # (an annex is an item of the world, and its id is taken)
        (lambda: h.event("annex", {"house": hid(2), "parent": hid(2), "form": "wing"}), ("annex_of_itself", {"house": hid(2)})),
        (lambda: h.event("annex", {"house": "nobody", "parent": hid(2), "form": "wing"}), ("not_a_house", {"house": "nobody"})),
        (lambda: h.event("annex", {"house": hid(5), "parent": hid(2), "form": "wing"}), ("house_is_annex", {"house": hid(5), "parent": hid(1), "form": "wing"})),
        (lambda: h.event("annex", {"house": hid(2), "parent": hid(5), "form": "wing"}), ("annex_of_annex", {"house": hid(2), "parent": hid(5), "above": hid(1)})),
        (lambda: h.event("annex", {"house": hid(2), "parent": "nobody", "form": "wing"}), ("annex_parent_missing", {"house": hid(2), "parent": "nobody"})),
        (lambda: h.event("annex", {"house": hid(1), "parent": hid(2), "form": "wing"}), ("annex_has_annexes", {"house": hid(1), "count": 1})),
        (lambda: h.file(hid(5), "a"), ("house_is_annex", {"house": hid(5), "parent": hid(1), "form": "wing"})),
        (lambda: suggest_file(h.state, hid(5)), ("house_is_annex", {"house": hid(5), "parent": hid(1), "form": "wing"})),
    ]
    for act, expected in cases:
        assert refused(h, act) == expected


def test_a_road_cannot_be_opened_for_an_annex_and_the_rule_does_not_count_it():
    h = Hand({"max": 40, "min": 3, "auto": False})
    h.add(6)
    h.add(2, annex_of=hid(1), annex_form="wing")
    assert refused(h, lambda: h.open("a", "A", None, [hid(1), hid(2), hid(7)])) == ("house_is_annex", {"house": hid(7), "parent": hid(1), "form": "wing"})
    assert refused(h, lambda: h.open("a", "A", None, [hid(1), hid(2)])) == ("too_few_chosen", {"chosen": 2, "least": 3})
    h.open("a", "A", None, [hid(1), hid(2), hid(3)])
    assert [n for n in h.state.nodes] == ["a"]


def test_the_shape_of_an_annex_event_and_of_the_keys_of_an_item_is_checked_before_the_world_is_asked():
    h = town(3)
    for payload, code in (({"house": hid(1), "parent": hid(2), "form": "shed"}, "annex_form_bad"), ({"house": 5, "parent": hid(2), "form": "wing"}, "not_text"),
                          ({"house": hid(1), "parent": hid(2)}, "keys_missing"), ({"house": hid(1), "parent": hid(2), "form": "wing", "x": 1}, "keys_unknown")):
        made = rc.raised(lambda: h.event("annex", payload))
        assert made.code == "invalid" and code in {p["code"] for p in made.params["problems"]}, payload
    for extra, code in (({"annex_of": hid(1)}, "annex_keys_unpaired"), ({"annex_form": "wing"}, "annex_keys_unpaired"), ({"annex_of": hid(1), "annex_form": "shed"}, "annex_form_bad"),
                        ({"annex_of": 5, "annex_form": "wing"}, "not_text")):
        made = rc.raised(lambda: h.event("add_item", {"item": item(9, **extra)}))
        assert made.code == "invalid" and code in {p["code"] for p in made.params["problems"]}, extra


def test_an_item_that_is_refused_is_not_left_half_done_when_a_fault_comes_after_the_annex_is_made(monkeypatch):
    h = town(4)
    before = journal_value(h.journal)

    def interrupted(self, *args, **kwargs):
        raise KeyboardInterrupt

    with monkeypatch.context() as flaw:
        flaw.setattr(State, "commit", interrupted)  # the item was made an annex in the State, and then the world could not take it
        with pytest.raises(KeyboardInterrupt):
            h.add(1, annex_of=hid(1), annex_form="wing")
        with pytest.raises(KeyboardInterrupt):
            h.event("annex", {"house": hid(2), "parent": hid(1), "form": "wing"})
    assert journal_value(h.journal) == before and h.state.annexes == {}


# ------------------------------------------------------------------------------------------------------ undo ----
def undone(h, seq):
    h.undo(seq)
    return h.state


def test_undoing_the_arrival_of_an_annex_takes_it_away_and_undoing_the_arrival_of_its_house_puts_it_on_a_lot_of_its_own():
    h = town(3)
    h.add(1, annex_of=hid(2), annex_form="wing")  # event 4: beside h0002
    h.add(1)  # event 5
    state = undone(h, 4)
    assert state.annexes == {} and hid(4) not in state.items and entries_of(state, "annex") == []
    h = town(3)
    h.add(1, annex_of=hid(2), annex_form="wing")  # event 4
    state = undone(h, 2)  # h0002 never arrived: the item that exists for it waits as a house on a lot of its own
    assert state.annexes == {} and hid(4) in state.items and hid(4) in lot_snapshot(state) and hid(2) not in state.items and hand_problems(state) == []


def test_undoing_the_arrival_of_the_house_that_absorbed_a_house_puts_the_house_back_on_a_lot_and_it_waits_again():
    h = town(3)
    h.add(1, annex_of=hid(6), annex_form="wing")  # event 4: h0004 waits
    h.add(1)  # 5
    h.add(1)  # 6: h0006 arrives, h0004 is absorbed
    assert h.state.annexes and hid(4) not in h.state.items
    state = undone(h, 6)
    assert state.annexes == {} and hid(4) in state.items and hid(4) in lot_snapshot(state) and hid(6) not in state.items and hand_problems(state) == []


def test_undoing_the_link_learned_later_puts_the_house_back_and_an_event_that_names_both_holds_the_arrivals_back():
    h = town(4)
    h.event("annex", {"house": hid(2), "parent": hid(3), "form": "mailbox"})  # event 5
    with pytest.raises(Refusal) as why:
        h.undo(3)  # the arrival of h0003, which the link names
    assert why.value.code == "undo_depends" and (why.value.params["later"], why.value.params["kind"]) == (5, "annex")
    state = undone(h, 5)
    assert state.annexes == {} and hid(2) in state.items and hid(2) in lot_snapshot(state) and entries_of(state, "absorbed") == [] and hand_problems(state) == []
    state = undone(h, 3)  # now nothing names it
    assert hid(3) not in state.items


def test_undoing_each_event_that_made_an_annex_leaves_a_sound_world_or_is_refused_by_what_depends_on_it():
    log = every_entry().journal
    made = [e["seq"] for e in log.events if e["kind"] == "annex" or (e["kind"] == "add_item" and (e["payload"]["item"].get("annex_of") or e["payload"]["item"]["id"] == hid(40)))]
    assert len(made) == 4  # the item that waits, the arrival of its house, an item beside a house at once, and the link learned later
    for target in made:
        j = Journal.replay(log.rule, log.events)
        try:
            j.append("undo", {"seq": target}, stamp(999))
        except Refusal as why:
            assert why.code in ("undo_depends", "undo_unfoldable"), (target, why)
            continue
        assert hand_problems(j.state) == [] and text_problems(j.state) == [], target


# -------------------------------------------------------------------------------------------- a new radius ----
@pytest.mark.parametrize("rule", [(200, 5, False, None), (40, 5, False, 34), (12, 5, True, 5)])
def test_a_new_radius_of_the_ring_road_lays_the_houses_out_again_and_the_annexes_stand_as_they_stood(rule):
    h = town(30, {"max": 12, "min": 5, "auto": False})
    for form, parent in (("wing", 3), ("mailbox", 3), ("wing", 17), ("wing", 3)):
        h.add(1, annex_of=hid(parent), annex_form=form)
    kept = {a: dict(annex_record(h.state, a)) for a in h.state.annexes}
    radius = h.state.plan["params"]["ring"]["radius"]
    max_, min_, auto, branches = rule
    h.rule(max_, min_, auto, branches)
    assert any(c.get("resized") for c in h.state.doc["chronicle"]) or h.state.plan["params"]["ring"]["radius"] == radius
    assert {a: annex_record(h.state, a) for a in h.state.annexes} == kept and hand_problems(h.state) == [] and text_problems(h.state) == []
    assert stability_violations(h.journal.events, h.journal.rule) == []


# ------------------------------------------------------------------------------------ the world and the file ----
def test_the_city_of_a_world_with_annexes_is_read_drawn_and_told_and_has_the_notes_for_annexes_only_then():
    h = every_entry()
    city = h.state.city()
    assert city["counts"]["annex"] == 3 and "world.chronicle.absorbed" in city["world"]["notes"] and "world.chronicle.annex" in city["world"]["notes"] and "annex" in city["kinds"]
    plain = Hand()
    plain.add(3)
    assert not any("annex" in n or "absorbed" in n for n in plain.state.city()["world"]["notes"]) and "annex" not in plain.state.city()["kinds"]
    assert city["composition"]["buildings"] == city["world"]["houses"] + 3 == city["composition"]["measure"]["lots"] + 3


def test_the_world_file_of_a_world_with_annexes_is_read_back_to_the_same_world_and_the_same_bytes():
    h = every_entry()
    text = dumps_world(world_document(h.journal))
    again = read_world(json.loads(text))
    assert dumps_world(world_document(again)) == text and lay.render(again.state.city()) == lay.render(h.state.city()) and again.state.annexes == h.state.annexes
    assert lay.render(fold(h.journal.events, h.journal.rule).city()) == lay.render(h.state.city())


def test_the_commands_of_a_world_say_houses_and_annexes_and_fold_the_same_city(tmp_path, capsys):
    from bibliopolis import cli

    journal = every_entry().journal
    (tmp_path / "w.world.json").write_text(dumps_world(world_document(journal)), encoding="utf-8")
    store, city = tmp_path / "w.sqlite", tmp_path / "city.json"
    assert cli.main(["world", "import", str(tmp_path / "w.world.json"), "--world", str(store)]) == 0
    assert f"{len(journal.events)} events, {len(journal.state.items)} houses and 3 annexes" in capsys.readouterr().err
    assert cli.main(["world", "fold", "--out", str(city), "--world", str(store)]) == 0
    assert f"{len(journal.state.items)} houses and 3 annexes on " in capsys.readouterr().err
    assert city.read_text(encoding="utf-8") == lay.render(journal.state.city())
    plain = Hand()
    plain.add(3)
    (tmp_path / "p.world.json").write_text(dumps_world(world_document(plain.journal)), encoding="utf-8")
    assert cli.main(["world", "import", str(tmp_path / "p.world.json"), "--world", str(tmp_path / "p.sqlite")]) == 0
    assert capsys.readouterr().err.strip().endswith("3 events, 3 houses")  # (a world with no annex says what it said)


def test_the_state_says_which_items_stand_beside_a_house_and_the_suggestions_never_see_them():
    h = Hand({"max": 20, "min": 3, "auto": False})
    h.add(8, topic(1, 1, 1, 1))
    h.add(8, topic(1, 1, 1, 1), annex_of=hid(2), annex_form="wing")
    assert len(h.state.annexes) == 8 and len(h.state.items) == 8
    assert suggest_merge(h.state, None) is None and h.state.houses_at(None) == houses(1, 8)


# ---------------------------------------------------------------------------------------- the random player ----
@pytest.mark.parametrize("seed", range(10))
def test_a_random_player_of_annexes_keeps_every_rule_of_the_world_after_every_event(seed):
    """Items that exist for houses that stand, for houses that have not arrived and for annexes, links learned later, roads opened and filed and moved and merged, new rules and new radii,
    and undos: the world is sound at the end, the log folds to the same bytes, a file reads back to the same world, and no event moved a house that it did not name."""
    journal = play_annexes(seed, auto=bool(seed % 2), resizing=seed % 3 == 0)
    state = journal.state
    assert hand_problems(state) == [] and text_problems(state) == []
    assert stability_violations(journal.events, journal.rule) == []
    assert lay.render(fold(journal.events, journal.rule).city()) == lay.render(state.city())
    assert read_world(json.loads(dumps_world(world_document(journal)))).state.doc == state.doc


def test_the_random_player_makes_every_kind_of_thing_a_world_with_annexes_has():
    kinds = {"annex": 0, "absorbed": 0, "event": 0, "refused": 0, "waiting": 0}
    for seed in range(10):
        journal = play_annexes(seed, auto=bool(seed % 2), resizing=seed % 3 == 0)
        kinds["event"] += sum(1 for e in journal.events if e["kind"] == "annex")
        kinds["annex"] += len(entries_of(journal.state, "annex"))
        kinds["absorbed"] += len(entries_of(journal.state, "absorbed"))
        kinds["waiting"] += sum(1 for it in journal.state.items.values() if it.get("annex_of"))
    assert kinds["annex"] > 10 and kinds["absorbed"] > 20 and kinds["event"] > 3 and kinds["waiting"] > 3
