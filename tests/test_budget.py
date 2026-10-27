"""The budget of the coast and the range of the rule (bibliopolis.coast, bibliopolis.plan.RULE_LIMIT).

The coast of a city is rasterised on a grid of one cell, so what it costs, in memory and in time, is the area of the city. A valid rule must always give a city that can be drawn, so the
range of the rule is cut where the widest ring road it can ask for still fits the grid with room to spare; a city that does not fit is refused, with an id, before the grid is made.
Not stated from the engine: the cells of the lane are counted here by `support.capacity`, the sectors by `support.cells_table` and the grid by the formula of the docs."""

import json
import math
import os
import random
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pytest
from hand_support import Hand, houses, play, topic
from support import T, capacity, cells_table, coast_with_tuple_stack, make_tree, sea_with_tuple_stack

from bibliopolis import cli, coast, hand, ring
from bibliopolis import layout as lay
from bibliopolis.coast import COAST_GRID_BUDGET, CityTooLarge, coast_of
from bibliopolis.events import BRANCHES_LIMIT, RULE_LIMIT, Refusal
from bibliopolis.journal import Journal

ROOT = Path(__file__).resolve().parents[1]
CODEX = {"max": 100_000, "min": 10, "auto": False, "branches": 13}  # the rule of the review: a ring road of radius 7961.5, a grid of 254 million cells
WIDEST = {"max": RULE_LIMIT, "min": 10, "auto": False, "branches": BRANCHES_LIMIT}


def grid_cells(radius):
    """The cells of the grid of the coast of a city that is nothing but a ring road of lane radius `radius`: the farthest point is the lane itself, the land reaches COAST_BUFFER and
    2 cells more, and the grid is a square of 2 * reach + 1 cells."""
    reach = math.ceil(radius + coast.COAST_BUFFER + 2)
    return (2 * reach + 1) ** 2


def gates_of_n(n):
    return sorted({round((axis / 100) % 360, 3) for _, _, axis in cells_table(n)})


def a_ring_road(radius):
    return {"places": {}, "roads": {"road:place:root": {"points": ring.ring_points(radius)}}, "centre": {"radius": 6.0}}


# ----------------------------------------------------------------------------------------- the numbers ----
def test_the_widest_ring_road_a_rule_can_ask_for_is_the_one_of_the_most_branches_whatever_the_max_up_to_the_range_of_the_rule():
    """1000 branches make the narrowest land 0.16 degrees, and the ring road must be 1073.5 cells out for an avenue to have its three cells there: its first lap then holds 10686 houses.
    So no `max` of the range asks for a larger ring. And the radius only grows with the branches (the gates of N directions are among those of N + 1, and the lands only narrow),
    so no valid rule has a ring road larger than this one."""
    narrowest = min(2 * min(axis - lo, hi - axis) for lo, hi, axis in cells_table(BRANCHES_LIMIT)) / 100
    assert narrowest == 0.16
    assert (1073.5 + lay.BAND / 2) * math.radians(narrowest) >= 3.0 > (1072.5 + lay.BAND / 2) * math.radians(narrowest)  # the arc of 3 cells: the least radius is 1073.5
    assert capacity(1073.5, gates_of_n(BRANCHES_LIMIT)) == 10686 >= RULE_LIMIT
    assert hand.ring_radius({"max": 1, "branches": BRANCHES_LIMIT}) == hand.ring_radius(WIDEST) == 1073.5
    for n in (2, 13, 89):
        assert hand.ring_radius({"max": RULE_LIMIT, "branches": n}) <= 1073.5, n


def test_the_grid_of_the_widest_valid_city_is_a_little_over_half_of_the_budget_and_the_rule_of_the_review_is_far_over_it():
    assert grid_cells(1073.5) == 2161**2 == 4_669_921 and COAST_GRID_BUDGET == 2**23 == 8_388_608
    assert 1.7 < COAST_GRID_BUDGET / grid_cells(1073.5) < 1.9
    assert grid_cells(7961.5) > 250_000_000 > COAST_GRID_BUDGET  # (the 254 million cells of the review)
    edge = lambda farthest: (2 * math.ceil(farthest + coast.COAST_BUFFER + 2) + 1) ** 2  # noqa: E731
    assert edge(1441) <= COAST_GRID_BUDGET < edge(1441.01)  # the budget is a city whose farthest lot or road is 1441 cells from the town hall


def test_the_pages_give_the_budget_and_the_range_of_the_rule_that_the_program_has():
    world = " ".join((ROOT / "docs" / "world.md").read_text(encoding="utf-8").split())
    engine = " ".join((ROOT / "docs" / "engine.md").read_text(encoding="utf-8").split())
    assert f"the budget of **{COAST_GRID_BUDGET} cells** (a square of 2895 by 2895" in world and "at most 1441 cells from the town hall" in world
    assert f"whatever `max` is up to {RULE_LIMIT}, the most" in world and "needs 2161 by 2161 cells" in world and "a radius of 1073.5 cells" in world
    assert "1.7 seconds and 57 MiB at the peak" in world and "took 487 MiB on that city" in world and "exhausted a limit of 384 MiB" in world and "an avenue of 2000 houses 1396 cells out (a grid of 7868025 cells)" in world
    assert f"to `limit` ({RULE_LIMIT}; {BRANCHES_LIMIT} for `branches`)" in world
    assert f"`1 <= min <= max <= {RULE_LIMIT}`" in engine


# ----------------------------------------------------------------------------------- the range of the rule ----
def test_the_rule_of_the_review_is_refused_by_the_rule_and_not_by_the_memory():
    with pytest.raises(Refusal) as why:
        Journal(CODEX)
    (problem,) = why.value.params["problems"]
    assert (why.value.code, problem["where"], problem["code"], problem["params"]["name"], problem["params"]["limit"]) == ("invalid", "rule.max", "rule_number_bad", "max", RULE_LIMIT)
    with pytest.raises(Refusal):
        Journal({**CODEX, "max": RULE_LIMIT + 1})
    assert Journal({**CODEX, "max": RULE_LIMIT}).state.plan["params"]["ring"]["radius"] == 799.5


@pytest.mark.parametrize("branches", [2, 13, 89, BRANCHES_LIMIT])
def test_a_valid_rule_at_the_edge_of_the_range_gives_a_city_that_is_drawn_with_its_coast(branches):
    """The default city, coast included: the world of a rule with nothing in it, at the largest `max`."""
    rule = {"max": RULE_LIMIT, "min": 10, "auto": False, "branches": branches}
    state = Journal(rule).state
    radius = hand.ring_radius(rule)
    assert state.plan["params"]["ring"]["radius"] == radius <= 1073.5
    start = time.perf_counter()
    doc = state.city()
    took = time.perf_counter() - start
    assert doc["coast"]["polygons"] and took < 30.0, took
    assert max(math.hypot(x, z) for x, z in doc["coast"]["polygons"][0]) >= radius  # the land holds the ring road
    assert grid_cells(radius) <= COAST_GRID_BUDGET


# -------------------------------------------------------------------------------------------- the refusal ----
def test_a_city_beyond_the_budget_is_refused_before_the_grid_is_made_and_with_an_id():
    layout = a_ring_road(7961.5)  # the ring road of the rule of the review
    tracemalloc.start()
    start = time.perf_counter()
    with pytest.raises(CityTooLarge) as why:
        coast_of(layout)
    took, (_, peak) = time.perf_counter() - start, tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert (why.value.code, why.value.params) == ("city_too_large", {"cells": grid_cells(7961.5), "budget": COAST_GRID_BUDGET}) and isinstance(why.value, ValueError)
    assert "the city is too large to draw its coast: the grid would hold" in str(why.value) and why.value.as_dict()["params"] == why.value.params
    assert peak < 20 * 2**20 and took < 2.0, (peak, took)  # (the points of the polyline: the grid would have been 254 MB)


def test_the_budget_is_the_cells_of_the_grid_to_the_cell():
    layout = {"places": {"p": {"kind": "lot", "position": {"x": 0.0, "z": 60.0}}}, "roads": {}, "centre": {"radius": 6.0}}  # reach 66, a grid of 133 by 133 cells
    assert coast_of(layout, budget=17_689)["polygons"]
    with pytest.raises(CityTooLarge) as why:
        coast_of(layout, budget=17_688)
    assert why.value.params == {"cells": 17_689, "budget": 17_688}
    assert coast_of(layout) == coast_of(layout, budget=COAST_GRID_BUDGET)


def test_a_world_beyond_the_budget_is_refused_by_the_city_and_by_the_command_and_is_still_a_document_without_its_coast(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(coast, "COAST_GRID_BUDGET", 1_000_000)
    h = Hand({"max": RULE_LIMIT, "min": 10, "auto": False, "branches": 13})  # a ring road of radius 799.5: a grid of 2.6 million cells
    h.add(3, topic(1, 1, 1, 1))
    with pytest.raises(CityTooLarge) as why:
        h.state.city()
    assert why.value.params == {"cells": grid_cells(799.5), "budget": 1_000_000}
    assert "coast" not in h.state.city(with_coast=False) and len(h.state.houses_at(None)) == 3  # the world is as it was
    path, out = tmp_path / "w.sqlite", tmp_path / "city.json"
    assert cli.main(["world", "new", "--world", str(path), "--max-houses", str(RULE_LIMIT)]) == 0
    capsys.readouterr()
    assert cli.main(["world", "fold", "--world", str(path), "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("bibliopolis: the city is too large to draw its coast: the grid would hold") and "Traceback" not in err and not out.exists()


def test_a_grown_city_beyond_the_budget_is_refused_by_the_command_build_the_same_way(monkeypatch, tmp_path, capsys):
    tree, items = make_tree({"med": T(0, a=T(25), b=T(16)), "pub": T(14)})
    (tmp_path / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    (tmp_path / "library.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    out = tmp_path / "city.json"
    argv = ["build", "--library", str(tmp_path / "library.json"), "--tree", str(tmp_path / "tree.json"), "--out", str(out)]
    assert cli.main(argv) == 0 and out.exists()  # the default rule: a city of a few hundred cells fits
    out.unlink()
    capsys.readouterr()
    monkeypatch.setattr(coast, "COAST_GRID_BUDGET", 500)  # (the town hall and the ring road alone need 31 by 31 cells)
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("bibliopolis: the city is too large to draw its coast: the grid would hold") and "and the most is 500" in err and not out.exists()


# ------------------------------------------------------------------------------------- the flood of the sea ----
def random_land(size, density, rng):
    """A bitmap of `size` by `size` cells of which a share `density` is land, with the corner (0, 0) sea; walls and blobs for the shapes that a flood meets."""
    land = bytearray(1 if rng.random() < density else 0 for _ in range(size * size))
    for _ in range(max(1, size // 6)):  # a wall, and the gap that lets the flood round it or not
        x, z, length, horizontal = rng.randrange(size), rng.randrange(size), rng.randrange(1, size + 1), rng.random() < 0.5
        for k in range(length):
            xx, zz = (x + k, z) if horizontal else (x, z + k)
            if xx < size and zz < size:
                land[zz * size + xx] = 1
    land[0] = 0
    return land


class Recording(list):
    """A list that notes, in `order`, the cell index of everything that is taken from it: the stand-in for the array of the stack."""

    order = []

    def pop(self):
        i = super().pop()
        self.order.append(i)
        return i


@pytest.mark.parametrize("size, density", [(1, 0.0), (2, 0.3), (7, 0.0), (7, 0.35), (13, 0.5), (24, 0.45), (40, 0.3), (61, 0.55)])
def test_the_stack_of_indices_floods_the_same_cells_in_the_same_order_as_the_stack_of_tuples(monkeypatch, size, density):
    rng = random.Random(size * 1000 + int(density * 100))
    for _ in range(12):
        land = random_land(size, density, rng)
        old_order = []
        old = sea_with_tuple_stack(land, size, old_order)
        recording = Recording()
        Recording.order = recording.order = []
        monkeypatch.setattr(coast, "array", lambda _typecode, start: Recording(start))  # the engine's stack, in plain sight
        new = coast.sea_of(land, size)
        assert new == old  # the same sea, to the byte
        assert [divmod(i, size)[::-1] for i in Recording.order] == old_order  # and the cells taken in the same order: (x, z) of each index
        assert len(Recording.order) == sum(new)  # every cell of the sea is put on the stack once, and taken once


@pytest.mark.parametrize("name, build", [
    ("a sparse city: one avenue of 600 houses far out", lambda: Hand({"max": 1200, "min": 1, "auto": False, "branches": 13})),
    ("the ring road of radius 1000 and nothing else", None),
    ("a world played at random", None),
])
def test_the_coast_of_a_city_is_the_same_to_the_byte_with_the_stack_of_indices_and_with_the_stack_of_tuples(name, build):
    if name.startswith("a sparse"):
        h = build()
        h.add(600, topic(1, 1, 1, 1))
        h.open("a", "A", None, houses(1, 600))
        layout = h.state.city(with_coast=False)
    elif name.startswith("the ring"):
        layout = a_ring_road(1000.0)
    else:
        layout = play(5, steps=120, auto=True, rule={"max": 15, "min": 3, "auto": True, "branches": 5}).state.city(with_coast=False)
    assert coast_of(layout) == coast_with_tuple_stack(layout) and coast_of(layout)["polygons"]


# ----------------------------------------------------------------------------------- the memory of the flood ----
CHILD = ROOT / "tests" / "coast_child.py"
LIMIT_MIB = 300  # of address space: the engine needs 85 (measured on Python 3.14 and 3.11, the interpreter and the world included), the stack of tuples needs more than 450


def in_a_child(mode, mib):
    done = subprocess.run([sys.executable, str(CHILD), mode, str(mib)], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS limits the address space of a process on Linux only")
def test_a_sparse_city_inside_the_budget_is_drawn_in_300_mib_and_the_stack_of_tuples_it_replaced_is_not():
    """The city of the review: the rule max 2400, 2000 houses all on one road, the farthest point 1396 cells from the town hall, a grid of 7868025 cells (the budget is 8388608). The stack
    of (x, z) tuples that the flood of the sea had took 487 MiB there and raised a MemoryError under 384 MiB; the stack of indices takes 4 bytes a cell at most and 57 MiB in all."""
    engine = in_a_child("engine", LIMIT_MIB)
    assert engine["outcome"] == "ok" and engine["polygons"] == 1
    control = in_a_child("control", LIMIT_MIB)
    assert control["outcome"] == "memory error"  # the limit bites: the old stack does not fit in it
    roomy = in_a_child("control", 900)
    assert roomy["outcome"] == "ok" and roomy["digest"] == engine["digest"]  # and with room it draws the very same coast, to the byte
