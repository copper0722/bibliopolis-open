"""Items that exist for another item in a world built by hand (docs/world.md, "An item that exists for another item"): an item whose house stands is an annex at once; one whose house has
not arrived waits as an ordinary house and is absorbed when the house arrives; the event `annex` links two houses later. An annex has no lot and counts for nothing against `max` or
`min`; every other house keeps its lot, byte for byte; an undo is the fold of the log without the event."""

import json

import pytest
import refusal_cases as rc
from hand_support import (Hand, every_entry, hand_problems, hid, houses, item, journal_value, lap_slots, lot_snapshot, node, play_annexes, ring_cells, stability_violations, stamp,
                          text_problems, topic)
from support import first_free, laps_of

from bibliopolis import events as ev
from bibliopolis import layout as lay
from bibliopolis.events import Refusal
from bibliopolis.hand import State, fold
from bibliopolis.journal import Journal, dumps_world, read_world, world_document
from bibliopolis.suggest import crowded, landing, suggest_file, suggest_merge, suggest_road
from bibliopolis.world import ROOT_PLACE


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


def test_the_house_takes_the_slot_that_a_house_that_waited_for_it_leaves_when_that_is_the_first_free_slot_of_the_ring_in_fill_order():
    h = town(5)
    h.add(1, annex_of=hid(8), annex_form="wing")  # h0006 waits
    h.add(1)
    before = ring_cells(h.state)
    freed = before[hid(6)]
    h.add(1)  # h0008 arrives: h0006 leaves its slot first, and h0008 takes the first free slot in fill order, which is that one
    cells = ring_cells(h.state)
    assert hid(6) not in cells and cells[hid(8)] == freed
    assert {k: v for k, v in cells.items() if k != hid(8)} == {k: v for k, v in before.items() if k != hid(6)}  # every other house stands where it stood
    want = first_free(lap_slots(h.state), set(cells.values()))
    h.add(1)
    assert ring_cells(h.state)[hid(9)] == want and want[0] == 0 and want != freed
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


# --------------------------------------------------------------------------- the order of an arrival that absorbs ----
real_add_item = State.do_add_item


def placed_first(self, e, p):
    """`State.do_add_item` for an item with no `annex_of`, in the order of the version before the fix: the house is placed FIRST, and only then do the houses that waited for it leave their
    lots. The control of the tests below, which it must make fail: a road that is full grows for the house, and a ring that is full opens a lap, for a house that only takes the place of
    one that leaves (and the roads beyond move for it)."""
    it = p["item"]
    if it.get("annex_of") is not None or it["id"] in self.items or it["id"] in self.annexes:
        return real_add_item(self, e, p)
    land = landing(self, it) if self.rule["auto"] else None
    waited = self.waiting_for(it)
    w, before = self.world(e), len(self.doc["chronicle"])
    w.seq += 1
    w.arrival_ids.add(it["id"])
    w.add_houses(ROOT_PLACE if land is None else lay.tag_place(land), [{"article": it["id"], "tag": land, "seq": w.seq}], "add_item")  # the house first ...
    for h in waited:  # ... and then each house that waited leaves its lot
        form = self.items[h]["annex_form"]
        w.stand_beside(h, it["id"], form, w.leave(h), "add_item")
        del self.items[h], self.road_of[h]
        self.annexes[h] = {"parent": it["id"], "form": form}
    self.items[it["id"]] = it
    self.road_of[it["id"]] = land
    touched, opened = [it["id"], *waited], []
    self.settle(w, e, land, touched, opened)
    self.commit(w, e, before)
    self.effects[e["seq"]] = {"houses": touched, "roads": opened}


def road_a_is_full(waiting=(3,), parent=10):
    """Rule max 6, min 3. An avenue t (domain 1) with two roads below it, on its line: a (field 1.1) holds six houses, which are all the six lots of its rib, and b (field 1.2) holds three. The
    houses of a whose numbers are in `waiting` wait for the house number `parent`, which has not arrived. The rule auto is on at the end, so that the next house of field 1.1 lands on a."""
    h = Hand({"max": 6, "min": 3, "auto": False})
    for k in range(1, 7):
        h.add(1, topic(1, 1, 1, 1), **({"annex_of": hid(parent), "annex_form": "wing" if k % 2 else "mailbox"} if k in waiting else {}))
    h.add(3, topic(1, 2, 1, 1))
    h.open("t", "T", None, houses(1, 9), node("domain", 1))
    h.open("a", "A", "t", houses(1, 6), node("field", 1, 1))
    h.open("b", "B", "t", houses(7, 9), node("field", 1, 2))
    h.rule(6, 3, True)
    return h


def lot_records(state):
    """house id -> the full record of its lot in the world, as text (its rib, slot, position, facing, road, topic and arrival number: all of it)."""
    return {p["article"]: json.dumps(p, sort_keys=True) for p in state.doc["places"].values() if p["kind"] == "lot"}


def road(state, key):
    return state.doc["places"][lay.tag_place(key)]


def test_a_full_road_does_not_grow_for_a_house_that_takes_the_place_of_one_that_leaves_and_no_other_lot_moves():
    h = road_a_is_full()
    before, left = lot_records(h.state), dict(h.state.doc["places"][lay.article_place(hid(3))])
    assert (road(h.state, "a")["lots"], road(h.state, "a")["reserved"], road(h.state, "a")["rib"]["slots"]) == (6, 0, 6)  # no empty lot on a
    h.add(1, topic(1, 1, 1, 1))  # h0010 lands on a, and h0003, which waited for it, is absorbed
    state, event = h.state, len(h.journal.events)
    assert state.road_of[hid(10)] == "a" and state.annexes == {hid(3): {"parent": hid(10), "form": "wing"}}
    assert (road(state, "a")["lots"], road(state, "a")["reserved"], road(state, "a")["rib"]["slots"]) == (6, 0, 6)  # six houses on six lots: the rib did not grow
    after = lot_records(state)
    assert {k: v for k, v in after.items() if k != hid(10)} == {k: v for k, v in before.items() if k != hid(3)}  # every other house: its full record, byte for byte
    taken = state.doc["places"][lay.article_place(hid(10))]
    assert {k: taken[k] for k in ("parent", "slot", "position", "facing", "street")} == {k: left[k] for k in ("parent", "slot", "position", "facing", "street")}  # it stands where h0003 stood
    assert [{k: e[k] for k in e if k in ("absorbed", "left", "from", "over")} for e in state.doc["chronicle"] if e["event_id"] == event] == [{"absorbed": hid(3), "left": "place:tag:a"}]
    assert hand_problems(state) == [] and text_problems(state) == [] and stability_violations(h.journal.events, h.journal.rule) == []


def test_the_old_order_grows_the_road_and_moves_lots_that_have_nothing_to_do_with_the_house_the_control_of_the_test_above(monkeypatch):
    """The same arrival with the house placed first (`placed_first`, which gives the bytes of the version before the fix): the road grows to twelve lots for a seventh house that is not
    there at the end, the three houses of the road beyond it are farther out, and so are the houses of the road itself; the end state is six houses on the road and no split."""
    before = lot_records(road_a_is_full().state)
    kept, moved = road_a_is_full(), road_a_is_full()
    kept.add(1, topic(1, 1, 1, 1))
    with monkeypatch.context() as old:
        old.setattr(State, "do_add_item", placed_first)
        moved.add(1, topic(1, 1, 1, 1))
    changed = {k for k, v in lot_records(moved.state).items() if k in before and k != hid(3) and v != before[k]}
    assert {k for k, v in lot_records(kept.state).items() if k in before and k != hid(3) and v != before[k]} == set()  # the new order moves nothing
    assert road(moved.state, "a")["rib"]["slots"] == 12 and {hid(7), hid(8), hid(9)} <= changed and len(changed) == 8  # a grew by six lots, and the lots beyond it moved out
    assert (road(moved.state, "a")["lots"], road(moved.state, "a")["reserved"]) == (6, 6) and moved.state.annexes == kept.state.annexes
    assert not [e for e in moved.state.doc["chronicle"] if "from" in e and e["event_id"] == len(moved.journal.events)]  # six houses, no split: the growth was for nothing


def test_the_house_takes_the_lowest_empty_lot_of_its_road_so_the_other_lots_that_were_freed_stay_reserved():
    h = road_a_is_full(waiting=(2, 5))  # h0002 (a mailbox) and h0005 (a wing) wait for h0010: slots 1 and 4 of a
    slots = {k: h.state.doc["places"][lay.article_place(hid(k))]["slot"] for k in (2, 5)}
    before = lot_records(h.state)
    h.add(1, topic(1, 1, 1, 1))
    state, event = h.state, len(h.journal.events)
    assert slots == {2: 1, 5: 4} and state.doc["places"][lay.article_place(hid(10))]["slot"] == 1  # the lowest of the two lots that were freed
    assert state.doc["places"][lay.reserved_place(road(state, "a")["rib"]["block"], 4)]["kind"] == "reserved"  # ... and the other one stays reserved
    assert (road(state, "a")["lots"], road(state, "a")["reserved"], road(state, "a")["rib"]["slots"]) == (5, 1, 6)
    assert {k: v for k, v in lot_records(state).items() if k != hid(10)} == {k: v for k, v in before.items() if k not in (hid(2), hid(5))}
    entries = [e for e in state.doc["chronicle"] if e["event_id"] == event]
    assert [(e["absorbed"], e["form"], e["left"]) for e in entries] == [(hid(2), "mailbox", "place:tag:a"), (hid(5), "wing", "place:tag:a")]  # in the order they arrived
    assert [(annex_record(state, a)["form"], annex_record(state, a)["rank"]) for a in state.annexes] == [("mailbox", 1), ("wing", 1)] and hand_problems(state) == []


def test_the_house_takes_an_earlier_hole_of_its_road_before_the_lot_that_a_house_that_waited_leaves():
    h = road_a_is_full()
    h.file(hid(1), "b")  # h0001 leaves slot 0 of a: a has an empty lot at the front, and h0003 stands on slot 2
    before = lot_records(h.state)
    assert (road(h.state, "a")["lots"], road(h.state, "a")["reserved"]) == (5, 1)
    h.add(1, topic(1, 1, 1, 1))
    state = h.state
    assert state.doc["places"][lay.article_place(hid(10))]["slot"] == 0  # the lowest empty lot of the road, which is not the one that h0003 left
    assert state.doc["places"][lay.reserved_place(road(state, "a")["rib"]["block"], 2)]["kind"] == "reserved"
    assert (road(state, "a")["lots"], road(state, "a")["reserved"], road(state, "a")["rib"]["slots"]) == (5, 1, 6)
    assert {k: v for k, v in lot_records(state).items() if k != hid(10)} == {k: v for k, v in before.items() if k != hid(3)} and hand_problems(state) == []


@pytest.mark.parametrize("hole", [None, 4])
@pytest.mark.parametrize("waiting", [(1,), (3,), (6,), (2, 5), (1, 6), (1, 2, 3)])
def test_whichever_houses_of_the_road_wait_and_wherever_its_holes_are_the_house_takes_the_lowest_empty_lot_and_nothing_else_moves(waiting, hole):
    h = road_a_is_full(waiting=waiting)
    if hole is not None:
        h.file(hid(hole), "b")  # a house that does not wait leaves a, which has an empty lot in front of the lots that will be freed
    before, rib = lot_records(h.state), road(h.state, "a")["rib"]["slots"]
    reserved = {q["slot"] for q in h.state.doc["places"].values() if q["kind"] == "reserved" and q["parent"] == "place:tag:a"}
    freed = {h.state.doc["places"][lay.article_place(hid(k))]["slot"] for k in waiting}
    h.add(1, topic(1, 1, 1, 1))
    state = h.state
    assert state.doc["places"][lay.article_place(hid(10))]["slot"] == min(reserved | freed) and road(state, "a")["rib"]["slots"] == rib == 6
    assert {k: v for k, v in lot_records(state).items() if k != hid(10)} == {k: v for k, v in before.items() if k not in {hid(n) for n in waiting}}
    assert set(state.annexes) == {hid(n) for n in waiting} and hand_problems(state) == [] and stability_violations(h.journal.events, h.journal.rule) == []


def test_a_full_ring_does_not_open_a_lap_for_a_house_that_takes_the_place_of_one_that_leaves(monkeypatch):
    def run(old):
        h = Hand()
        slots = h.state.doc["places"]["place:root"]["ring"]["slots"]
        h.add(10)
        h.add(1, annex_of=hid(slots + 1), annex_form="mailbox")  # h0011 waits for the house that comes after the ring is full
        h.add(slots - 11)
        full = (h, ring_cells(h.state), lot_records(h.state))
        assert len(full[1]) == slots and laps_of(h.state.doc) == ["place:root"] and not [c for c in full[1].values() if c[0] != 0]  # the first lap is full
        with monkeypatch.context() as patch:
            if old:
                patch.setattr(State, "do_add_item", placed_first)
            h.add(1)
        return full, h.state

    (h, cells, before), state = run(old=False)
    assert laps_of(state.doc) == ["place:root"] and ring_cells(state)[hid(len(cells) + 1)] == cells[hid(11)]  # no lap: the house stands in the slot of h0011
    assert {k: v for k, v in lot_records(state).items() if k != hid(len(cells) + 1)} == {k: v for k, v in before.items() if k != hid(11)}
    assert hand_problems(state) == [] and stability_violations(h.journal.events, h.journal.rule) == []
    (_h, cells, _before), state = run(old=True)
    assert len(laps_of(state.doc)) == 2 and ring_cells(state)[hid(len(cells) + 1)] == (1, 0)  # the control: a lap opens for a house that only takes the place of one that leaves


def test_the_order_changes_nothing_when_the_house_that_waited_is_not_on_the_road_the_house_lands_on(monkeypatch):
    def run(old):
        h = road_a_is_full(waiting=())
        h.add(1, topic(2, 1, 1, 1), annex_of=hid(11), annex_form="wing")  # h0010 waits on the ring road, where no road takes it
        with monkeypatch.context() as patch:
            if old:
                patch.setattr(State, "do_add_item", placed_first)
            h.add(1, topic(1, 1, 1, 1))  # h0011 lands on a, which is full, and h0010 is absorbed
        return h.state

    new, old = run(old=False), run(old=True)
    assert lay.render(new.city()) == lay.render(old.city())
    assert road(new, "a")["rib"]["slots"] == 12 and new.annexes == {hid(10): {"parent": hid(11), "form": "wing"}}  # (a grows for the seventh house, as it always did)
    absorbed = next(e for e in new.doc["chronicle"] if "absorbed" in e)
    opened = [e for e in new.doc["chronicle"] if "from" in e and e["event_id"] == absorbed["event_id"]]
    assert opened and all(e["n"] > absorbed["n"] for e in opened)  # the roads that the rule opens for the seven houses of a are entries after the absorption: it is part of the arrival


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
