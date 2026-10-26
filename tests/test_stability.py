"""Stability: replay a log one event at a time, and every house that an event did not move keeps the identical lot it had before it. An undo is the one exception
(it may re-place what came after the event it takes back).

The check itself is `stability_violations` of hand_support. It reads what an event moves from the event and the world before it, never from what the engine says it did,
so a fault that moves one house too many shows. The mutation controls below plant such faults in the engine and see that the check turns red."""

import pytest
from hand_support import Hand, hid, play, stability_violations

from bibliopolis import hand
from bibliopolis import layout as lay
from bibliopolis.events import standing


def houses(first, last):
    return [hid(i) for i in range(first, last + 1)]


def scripted():
    """A log in which every kind of event leaves holes in front of houses that stay: roads opened from the middle of the root zone, houses filed out of a road and out
    of the root zone, a road with roads below it moved, a rename, a rule, and an undo from the middle."""
    h = Hand()
    h.add(60)
    h.open("a", "A", None, houses(3, 20))  # holes at the front of the root zone
    h.open("b", "B", None, [hid(i) for i in range(21, 41) if i % 2])  # ... and in the middle of it
    h.add(20)
    h.file(hid(1), "a")
    h.file(hid(30), "b")  # (house 30 is in the root zone: b took the odd ones)
    h.file(hid(5), "b")  # out of a road, with houses after it
    h.open("a1", "A one", "a", houses(6, 17))
    h.rename("a", "Alpha")
    h.rule(30, 5)
    h.move("a1", "b")
    h.add(5)
    h.undo(len(h.journal.events) - 3)  # from the middle: nothing names the house it added
    h.file(hid(2), "a1")
    h.move("b", "a")
    return h


def test_a_scripted_log_with_every_kind_of_event_is_stable():
    h = scripted()
    kinds = {e["kind"] for e in h.journal.events}
    assert kinds == {"add_item", "open_road", "file", "rename_road", "move_road", "undo", "set_rule"}
    assert stability_violations(h.journal.events, h.journal.rule) == []


@pytest.mark.parametrize("seed", range(40))
def test_a_random_log_is_stable(seed):
    j = play(seed, steps=150)
    assert len(j.events) > 100
    assert stability_violations(j.events, j.rule) == []


def test_the_replay_ends_in_the_world_the_journal_holds():
    """The incremental replay of the check (apply, apply, ...) and the fold of the whole log are the same world."""
    j = play(8, steps=150)
    state, seen = hand.State(j.rule), []
    for e in j.events:
        seen.append(e)
        if e["kind"] == "undo":
            state = hand.fold(seen, j.rule)
        else:
            state.apply(e)
    assert lay.render(state.city()) == lay.render(j.state.city())


# ------------------------------------------------------------------------------------- the mutation controls ----
def repack(world, place, trigger):
    """The fault: put the houses that stand on `place` again, in arrival order, onto its first lots (what a split of the grown city does to the houses that stay)."""
    lots = world.lots_on(place)
    for lot in lots:
        world.free_lot(lot)
    world.add_houses(place, [{"article": lot["article"], "tag": lot["tag"], "seq": lot["seq"]} for lot in lots], trigger)


def test_the_check_is_red_when_opening_a_road_packs_the_houses_that_stay_onto_the_first_lots(monkeypatch):
    h = scripted()
    original = hand.HandWorld.open_road

    def packing(self, key, label, parent_place, ids, trigger):
        original(self, key, label, parent_place, ids, trigger)
        repack(self, parent_place, trigger)

    monkeypatch.setattr(hand.HandWorld, "open_road", packing)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and all("(open_road)" in line and "moved the house" in line for line in found), found
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_the_check_is_red_when_filing_a_house_closes_the_gap_it_leaves(monkeypatch):
    h = scripted()
    original = hand.HandWorld.file_house

    def closing(self, house, key, trigger):
        source = self.places.get(lay.article_place(house))["street"]
        original(self, house, key, trigger)
        repack(self, source, trigger)

    monkeypatch.setattr(hand.HandWorld, "file_house", closing)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and all("(file)" in line for line in found), found
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_the_check_is_red_when_moving_a_road_also_puts_a_house_of_another_road_again(monkeypatch):
    h = scripted()
    original = hand.HandWorld.move_subtree

    def careless(self, key, keys, was_below, below, trigger):
        out = original(self, key, keys, was_below, below, trigger)
        repack(self, "place:root", trigger)  # the root zone has nothing to do with the move
        return out

    monkeypatch.setattr(hand.HandWorld, "move_subtree", careless)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and all("(move_road)" in line for line in found), found
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_the_check_is_red_when_a_rename_moves_a_house(monkeypatch):
    h = scripted()
    original = hand.HandWorld.relabel

    def shifting(self, keys):
        original(self, keys)
        repack(self, lay.tag_place(keys[0]), "rename_road")

    monkeypatch.setattr(hand.HandWorld, "relabel", shifting)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and any("(rename_road)" in line for line in found), found


def test_the_check_is_red_when_an_arrival_swaps_two_houses_that_were_there(monkeypatch):
    h = scripted()
    original = hand.HandWorld.add_houses

    def swapping(self, road, pending, trigger):
        original(self, road, pending, trigger)
        if trigger == "add_item" and len(self.lots_on(road)) > 3:
            first, second = self.lots_on(road)[:2]  # the first two houses of the road change places
            self.free_lot(first)
            self.free_lot(second)
            original(self, road, [{"article": second["article"], "tag": second["tag"], "seq": second["seq"]}], trigger)
            original(self, road, [{"article": first["article"], "tag": first["tag"], "seq": first["seq"]}], trigger)

    monkeypatch.setattr(hand.HandWorld, "add_houses", swapping)
    found = stability_violations(h.journal.events, h.journal.rule)
    assert found and any("(add_item)" in line for line in found), found
    monkeypatch.undo()
    assert stability_violations(h.journal.events, h.journal.rule) == []


def test_the_check_reads_what_an_event_moves_from_the_event_and_not_from_the_engine():
    """A house that the event names is excused whatever the engine did with it; one that it does not name is not. So the oracle is not the engine's own report."""
    from hand_support import moved_by

    h = scripted()
    state = hand.State(h.journal.rule)
    for e in h.journal.events:
        if e["kind"] == "undo":
            break
        moved = moved_by(e, state)
        if e["kind"] == "open_road":
            assert moved == set(e["payload"]["houses"])
        elif e["kind"] == "file":
            assert moved == {e["payload"]["house"]}
        elif e["kind"] == "move_road":
            assert moved and moved <= set(state.items) and all(state.road_of[x] in state.subtree(e["payload"]["road"]) for x in moved)
        else:
            assert moved == set()
        state.apply(e)
    assert standing(h.journal.events)  # (the script has events that count)
