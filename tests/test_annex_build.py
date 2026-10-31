"""An item that exists for another item in a city that `build` makes (both modes) and in a world made by `assign`: where it stands, what counts it and what never does.

An annex has an arrival number like any item and is no house: no lot, no road, no rib, no address. It stands where its house stands, a wing on its side wall or a mailbox at its gate,
and a road that holds `max` houses holds them whatever annexes they have. Without its house an annex waits and is placed when the house arrives."""

import json
import random

import pytest
from annex_support import annexed, houses_only, without_annexes
from support import T, Town, art, make_tree, random_world, sample, stamp

import bibliopolis
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.tree import TreeView

MODES = ["grow", "mirror"]


def small():
    """Seven houses of one topic (a1 .. a7) and three more topics: the arrival numbers are the numbers of the ids."""
    tree, items = make_tree({"med": T(3, a=T(2), b=T(2))})
    return tree, items


def city(items, tree, **kw):
    return json.loads(lay.render(bibliopolis.build_city({"items": items}, tree, **kw)))


def annexes_of(doc):
    return {p["article"]: p for p in doc["places"].values() if p["kind"] == "annex"}


# ------------------------------------------------------------------------------------------ where an annex stands ----
def test_an_annex_stands_beside_its_house_with_no_lot_of_its_own():
    tree, items = small()
    items.append(art(8, ["a"], annex_of="a00002", annex_form="wing"))
    doc = city(items, tree)
    assert annexes_of(doc) == {"a00008": {"kind": "annex", "article": "a00008", "parent": "place:article:a00002", "form": "wing", "rank": 1, "seq": 8}}
    assert list(doc["places"]["place:article:a00008"]) == ["kind", "article", "parent", "form", "rank", "seq"]  # (the order the keys are written in)
    assert doc["places"]["place:article:a00002"]["kind"] == "lot" and "place:article:a00008" in doc["places"]
    assert [p["article"] for p in doc["places"].values() if p["kind"] == "lot"] == [f"a{i:05d}" for i in range(1, 8)]  # seven houses: the annex has no lot
    assert doc["counts"]["annex"] == 1 and doc["counts"]["lot"] == 7
    assert "annex" in doc["kinds"] and "composition.buildings" in doc["world"]["notes"] and "world.chronicle.annex" in doc["world"]["notes"]


def test_the_numbers_of_a_city_with_annexes_are_houses_for_lots_and_houses_and_annexes_for_buildings():
    tree, items = small()
    items += [art(8, [], annex_of="a00002", annex_form="wing"), art(9, [], annex_of="a00002", annex_form="mailbox"), art(10, ["a"], annex_of="a00004", annex_form="wing")]
    doc = city(items, tree)
    assert doc["world"]["houses"] == doc["composition"]["measure"]["lots"] == 7 and doc["world"]["seq"] == 10  # (the annexes arrived: three arrival numbers)
    assert doc["composition"]["articles"] == doc["composition"]["buildings"] == 10 and sum(1 for p in doc["places"].values() if p["kind"] == "lot") == 7
    assert bibliopolis.summary(doc)["houses"] == 7


def test_a_city_with_no_annex_has_none_of_the_keys_that_are_for_annexes():
    tree, items = small()
    doc = city(items, tree)
    assert "annex" not in doc["counts"] and "annex" not in doc["kinds"] and not any("annex" in note for note in doc["world"]["notes"])
    assert all(p["kind"] != "annex" for p in doc["places"].values()) and doc["composition"]["articles"] == doc["composition"]["buildings"] == doc["world"]["houses"] == 7


def test_the_annexes_of_one_house_are_ranked_by_arrival_in_each_form_apart_and_five_wings_have_five_ranks():
    tree, items = small()
    forms = ["wing", "mailbox", "wing", "wing", "mailbox", "wing", "wing", "wing"]
    items += [art(8 + k, [], annex_of="a00003", annex_form=form) for k, form in enumerate(forms)]
    mine = annexes_of(city(items, tree))
    assert [(a, p["form"], p["rank"], p["seq"]) for a, p in sorted(mine.items(), key=lambda kv: kv[1]["seq"])] == [
        ("a00008", "wing", 1, 8), ("a00009", "mailbox", 1, 9), ("a00010", "wing", 2, 10), ("a00011", "wing", 3, 11), ("a00012", "mailbox", 2, 12), ("a00013", "wing", 4, 13),
        ("a00014", "wing", 5, 14), ("a00015", "wing", 6, 15)]
    assert {p["parent"] for p in mine.values()} == {"place:article:a00003"}


def test_a_wing_may_be_of_a_house_that_arrives_after_it_and_the_house_stands_first_in_the_chronicle_of_its_arrival():
    tree, items = small()
    items += [art(8, [], annex_of="a00010", annex_form="mailbox"), art(9, [], annex_of="a00010", annex_form="wing"), art(10, ["b"])]
    doc = city(items, tree)
    assert {a: (p["parent"], p["form"], p["rank"], p["seq"]) for a, p in annexes_of(doc).items()} == {
        "a00008": ("place:article:a00010", "mailbox", 1, 8), "a00009": ("place:article:a00010", "wing", 1, 9)}
    entries = [e for e in doc["world"]["chronicle"] if "annex" in e]
    assert [(e["annex"], e["parent"], e["form"], e["seq"], e["trigger"], e["event_id"], e["at"]) for e in entries] == [
        ("a00008", "a00010", "mailbox", 10, "arrival", None, stamp(10)), ("a00009", "a00010", "wing", 10, "arrival", None, stamp(10))]  # the arrival that caused it is the house's
    assert [e["n"] for e in doc["world"]["chronicle"]] == list(range(1, len(doc["world"]["chronicle"]) + 1))


def test_an_annex_that_arrives_after_its_house_has_the_entry_of_its_own_arrival():
    tree, items = small()
    items.append(art(8, [], annex_of="a00001", annex_form="wing"))
    (entry,) = [e for e in city(items, tree)["world"]["chronicle"] if "annex" in e]
    assert (entry["seq"], entry["at"], list(entry)) == (8, stamp(8), ["n", "event_id", "seq", "trigger", "annex", "parent", "form", "at"])


@pytest.mark.parametrize("mode", MODES)
def test_a_replay_before_the_house_arrives_has_no_record_of_its_annex_and_one_after_it_has(mode):
    tree, items = small()
    items += [art(8, [], annex_of="a00010", annex_form="wing"), art(9, ["b"]), art(10, ["b"])]
    before, after = city(items, tree, mode=mode, first=9), city(items, tree, mode=mode, first=10)
    assert annexes_of(before) == {} and "annex" not in before["counts"] and before["world"]["seq"] == 9 and before["composition"]["buildings"] == before["world"]["houses"] == 8
    assert list(annexes_of(after)) == ["a00008"] and after["world"]["seq"] == 10 and after["composition"]["buildings"] == 10 and after["world"]["houses"] == 9


# ----------------------------------------------------------------------------------- what never counts an annex ----
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", range(10))
def test_the_city_of_a_library_with_annexes_is_the_city_of_the_houses_to_the_byte(mode, seed):
    """The annexes move no house: take the annex records out of the document, number the houses in the order they arrived, and it is the document that the library without the annexes makes (the
    roads, the ribs, the lots, the sectors, the coast, the measures, and the chronicle of the splits)."""
    tree, items = random_world(seed)
    rule = {} if seed % 2 == 0 else {"max_houses": 15, "min_houses": 5, "trunk_min": 40}
    with_annexes, ids = annexed(items, seed, share=0.2 + 0.1 * (seed % 3))
    assert ids and len(ids) < len(items)
    here, there = city(with_annexes, tree, mode=mode, **rule), city(houses_only(with_annexes), tree, mode=mode, **rule)
    assert len(annexes_of(here)) == len(ids) and annexes_of(there) == {}
    assert without_annexes(here) == there
    assert lay.render(without_annexes(here)) == lay.render(there)


@pytest.mark.parametrize("mode", MODES)
def test_the_topics_of_an_annex_give_it_no_address_and_no_road(mode):
    tree, items = make_tree({"r": T(0, a=T(25), b=T(25), c=T(0))})
    items += [art(100 + k, ["c"], annex_of=items[k]["id"], annex_form="wing") for k in range(30)]  # thirty items filed under c, a topic that no house names
    doc = city(items, tree, mode=mode)
    roads = {p["address"][-1] for p in doc["places"].values() if p["kind"] == "street" and p.get("shape") != "ring"}
    assert "C" not in roads and len(annexes_of(doc)) == 30
    assert doc["composition"]["ring1"] == city(houses_only(items), tree, mode=mode)["composition"]["ring1"]  # the cut and the sectors read the houses only


def test_a_road_holds_max_houses_whatever_annexes_they_have_and_the_next_house_splits_it():
    tree, items = make_tree({"r": T(0, a=T(7), b=T(5))})
    rule = {"max_houses": 12, "min_houses": 4}
    n = len(items)
    items += [art(n + 1 + k, [], annex_of=items[k % 12]["id"], annex_form="wing" if k % 3 else "mailbox") for k in range(30)]
    doc = city(items, tree, **rule)
    assert doc["composition"]["measure"]["ring_lots"] == 12 and not [e for e in doc["world"]["chronicle"] if "from" in e or "over" in e]  # thirty annexes, twelve houses: no split, no over
    assert not any(p.get("over") for p in doc["places"].values())
    items.append(art(n + 31, ["a"]))
    again = city(items, tree, **rule)
    assert [e["label"] for e in again["world"]["chronicle"] if "from" in e] == ["A"] and len(annexes_of(again)) == 30  # the thirteenth house splits it


# ------------------------------------------------------------------------- calls: what a world does not depend on ----
def world_for(items, tree, mode="grow", **rule):
    tv = TreeView(tree)
    plan = plan_mod.build_plan(tv, houses_only(items), mode=mode, max_houses=rule.get("max_houses", 12), min_houses=rule.get("min_houses", 4), trunk_min=20)
    return plan, tv, zw.new_world(plan)


def run(plan, tv, doc, items, cuts):
    """The arrivals in calls of the given sizes (and the last call whatever is left), the world after each."""
    out, start = [], 0
    for size in [*cuts, len(items)]:
        if start >= len(items):
            break
        result = zw.assign(plan, tv, doc, items[start:start + size])
        doc, start = zw.apply_delta(doc, result["delta"]), start + size
        out.append(doc)
    return out


def comparable(doc):
    return json.dumps({k: doc[k] for k in ("places", "roads", "lines", "seq", "chronicle")}, sort_keys=True)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", range(6))
def test_a_world_does_not_depend_on_how_its_arrivals_are_cut_into_calls_annexes_that_wait_included(seed, mode):
    tree, items = random_world(seed)
    items, ids = annexed(items, seed, share=0.3)
    plan, tv, empty = world_for(items, tree, mode)
    (whole,) = run(plan, tv, empty, items, [])
    rng = random.Random(seed)
    for _ in range(4):
        cuts = [rng.randint(1, 25) for _ in range(rng.randint(2, 12))]
        final = run(plan, tv, empty, items, cuts)[-1]
        assert comparable(final) == comparable(whole), cuts
        assert final.get("waiting", {}) == {} and not zw.annexes(final).keys() ^ set(ids)


def test_an_annex_that_waits_for_its_house_across_two_calls_has_no_record_until_the_house_arrives():
    tree, items = small()
    items += [art(8, [], annex_of="a00010", annex_form="wing"), art(9, ["b"]), art(10, ["b"])]
    plan, tv, empty = world_for(items, tree)
    first, second = run(plan, tv, empty, items, [8])[0], None
    assert first["seq"] == 8 and zw.annexes(first) == {} and first["waiting"] == {"a00010": [{"article": "a00008", "form": "wing", "seq": 8}]}
    assert "place:article:a00008" not in first["places"] and not any(p["kind"] == "reserved" for p in first["places"].values())
    second = run(plan, tv, first, items[8:], [1])[0]
    assert zw.annexes(second) == {} and second["waiting"] == first["waiting"]  # a house that is not the one it waits for does not release it
    final = run(plan, tv, second, items[9:], [])[0]
    assert list(zw.annexes(final)) == ["a00008"] and final["waiting"] == {}
    assert [e["annex"] for e in final["chronicle"] if "annex" in e] == ["a00008"] and final["chronicle"][-1]["seq"] == 10
    assert not zw.annexes(final).keys() - {"a00008"}


def test_the_key_of_the_waiting_annexes_is_in_the_delta_only_when_a_call_changes_who_waits():
    tree, items = small()
    items += [art(8, [], annex_of="a00010", annex_form="wing"), art(9, ["b"]), art(10, ["b"])]
    plan, tv, empty = world_for(items, tree)
    deltas = []
    doc = empty
    for part in (items[:7], items[7:8], items[8:9], items[9:]):
        result = zw.assign(plan, tv, doc, part)
        deltas.append(result["delta"])
        doc = zw.apply_delta(doc, result["delta"])
    assert ["waiting" in d for d in deltas] == [False, True, False, True] and deltas[3]["waiting"] == {}
    assert "waiting" not in zw.new_world(plan)


def test_an_annex_of_itself_or_of_an_annex_is_a_mistake_of_the_caller_and_an_id_that_waits_is_taken():
    tree, items = small()
    plan, tv, empty = world_for(items, tree)
    with pytest.raises(ValueError, match="annex of itself"):
        zw.assign(plan, tv, empty, [art(8, [], annex_of="a00008", annex_form="wing")])
    with pytest.raises(ValueError, match="an annex itself"):  # (the house of the second stands as an annex)
        zw.assign(plan, tv, empty, [*items, art(8, [], annex_of="a00001", annex_form="wing"), art(9, [], annex_of="a00008", annex_form="mailbox")])
    with pytest.raises(ValueError, match="an annex itself"):  # (... and here the house of the second is an annex that waits for its own house)
        zw.assign(plan, tv, empty, [art(8, [], annex_of="zz", annex_form="wing"), art(9, [], annex_of="a00008", annex_form="mailbox")])
    waiting = zw.apply_delta(empty, zw.assign(plan, tv, empty, [art(8, [], annex_of="zz", annex_form="wing")])["delta"])
    with pytest.raises(ValueError, match="already placed"):
        zw.assign(plan, tv, waiting, [art(8, [], annex_of="a00001", annex_form="mailbox")])
    with pytest.raises(ValueError, match="an annex itself"):  # (the house of the new annex waits as an annex in the world already)
        zw.assign(plan, tv, waiting, [art(9, [], annex_of="a00008", annex_form="mailbox")])


@pytest.mark.parametrize("mode", MODES)
def test_the_same_library_gives_the_same_bytes_in_separate_processes_with_other_hash_seeds(mode, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    tree, items = random_world(4)
    items, _ids = annexed(items, 4, share=0.3)
    (tmp_path / "library.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (tmp_path / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    made = []
    for k, hash_seed in enumerate(("1", "2", "3")):
        out = tmp_path / f"city{k}.json"
        run_ = subprocess.run([sys.executable, "-m", "bibliopolis", "build", "--library", str(tmp_path / "library.json"), "--tree", str(tmp_path / "tree.json"), "--mode", mode,
                               "--out", str(out)], cwd=root, env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
        assert run_.returncode == 0, run_.stderr
        made.append(out.read_bytes())
    assert made[0] == made[1] == made[2] and b'"kind":"annex"' in made[0]


# ------------------------------------------------------------------------------------------ the world, checked ----
@pytest.mark.parametrize("mode", MODES)
def test_the_checks_of_the_tests_find_nothing_wrong_in_a_world_with_annexes_after_every_call_and_see_a_planted_fault(mode):
    import checks
    from support import district_problems

    tree, items = random_world(2)
    items, _ids = annexed(items, 2, share=0.3)
    plan, tv, doc = world_for(items, tree, mode)
    for step in run(plan, tv, doc, items, [30] * 20):
        assert checks.all_problems(step) == {} and district_problems(step, plan, tv) == []
    step = zw.apply_delta(step, zw.complete(plan, tv, step)["delta"])
    assert checks.all_problems(step) == {} and district_problems(step, plan, tv) == []
    broken = json.loads(json.dumps(step))
    annex = next(p for p in broken["places"].values() if p["kind"] == "annex")
    annex["parent"] = "place:article:nobody"
    assert "annex_problems" in checks.all_problems(broken)
    for change, what in ((lambda p: p.update(rank=9), "ranked"), (lambda p: p.update(form="shed"), "form"), (lambda p: p.update(slot=3), "keys")):
        broken = json.loads(json.dumps(step))
        change(next(p for p in broken["places"].values() if p["kind"] == "annex"))
        assert any(what in text for _pid, text in checks.annex_problems(broken)), what


def test_the_town_of_the_tests_takes_annexes_as_arrivals_and_checks_the_world_after_each_call():
    town = Town({"r": T(0, a=T(15), b=T(15))}, max_houses=12, min_houses=4)
    houses = town.items
    town.send(houses[:20])
    town.send([art(500, ["a"], annex_of=houses[3]["id"], annex_form="wing"), art(501, ["b"], annex_of=houses[25]["id"], annex_form="mailbox")])
    assert zw.annexes(town.doc).keys() == {"a00500"} and town.doc["waiting"] == {"a00026": [{"article": "a00501", "form": "mailbox", "seq": 22}]}
    town.send(houses[20:])
    assert zw.annexes(town.doc).keys() == {"a00500", "a00501"} and town.doc["waiting"] == {}
