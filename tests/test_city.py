"""The pipeline in three calls (bibliopolis.city): what `build_world` hands back and the numbers `summary` reports."""

import json

import pytest
from support import ROOT, art, stamp

import bibliopolis
from bibliopolis import cli


def forest(*names):
    return {"nodes": [{"id": n, "label": n.upper(), "parent": None} for n in names]}


# the root zone fills up to 41 houses with no group of 10 (over), a tenth house of t0 opens its road (not over any more), nine more roots of one house
# each fill the root zone up to 41 again (over a second time)
TREE = forest(*[f"t{i}" for i in range(5)], *[f"s{i}" for i in range(9)])
ARRIVALS = [f"t{i // 8}" for i in range(40)] + ["t0"] + ["t0"] + [f"s{i}" for i in range(9)]


def city(n, **kw):
    items = [art(k + 1, [topic], added_at=stamp(k)) for k, topic in enumerate(ARRIVALS[:n])]
    return bibliopolis.build_city({"items": items}, TREE, max_houses=40, min_houses=10, **kw)


def overs(doc):
    return [e for e in doc["world"]["chronicle"] if "over" in e]


def test_the_summary_counts_the_streets_that_are_over_now_not_the_times_one_went_over():
    first = city(41)  # the 41st house: the root zone holds 41 and no group has 10
    assert [e["seq"] for e in overs(first)] == [41] and first["places"]["place:root"]["over"] is True
    assert bibliopolis.summary(first) == {"mode": "grow", "houses": 41, "roads": 0, "underground": 41, "splits": 0, "over": 1}
    second = city(42)  # the 42nd house gives t0 its tenth: the road opens, the root zone drops to 32 and is not over any more
    assert [e["seq"] for e in overs(second)] == [41] and [e["to"] for e in second["world"]["chronicle"] if "from" in e] == ["place:tag:t0"]
    assert "over" not in second["places"]["place:root"]
    assert bibliopolis.summary(second) == {"mode": "grow", "houses": 42, "roads": 1, "underground": 32, "splits": 1, "over": 0}  # the chronicle still has the old entry
    third = city(51)  # nine houses more: over a second time
    assert [e["seq"] for e in overs(third)] == [41, 51] and third["places"]["place:root"]["over"] is True
    assert bibliopolis.summary(third) == {"mode": "grow", "houses": 51, "roads": 1, "underground": 41, "splits": 1, "over": 1}  # two entries, one street over


def test_the_command_line_reports_the_streets_that_are_over_now(tmp_path, capsys):
    items = [art(k + 1, [topic], added_at=stamp(k)) for k, topic in enumerate(ARRIVALS[:42])]
    (tmp_path / "t.json").write_text(json.dumps(TREE), encoding="utf-8")
    (tmp_path / "l.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    out = tmp_path / "city.json"
    assert cli.main(["build", "--library", str(tmp_path / "l.json"), "--tree", str(tmp_path / "t.json"), "--out", str(out)]) == 0
    assert capsys.readouterr().err.strip() == f"wrote {out}: 42 houses on 1 roads, 32 under the town hall, 1 splits, 0 over (mode grow)"
    assert len(overs(json.loads(out.read_text(encoding="utf-8")))) == 1  # (the chronicle remembers it)


def test_a_road_that_stays_over_is_counted_once_in_both_modes():
    items = [art(k + 1, ["t0"], added_at=stamp(k)) for k in range(45)]
    for mode in ("grow", "mirror"):
        doc = bibliopolis.build_city({"items": items}, TREE, mode=mode)
        assert bibliopolis.summary(doc)["over"] == 1 and doc["places"]["place:tag:t0"]["over"] is True and len(overs(doc)) == 1


def test_build_world_hands_back_the_plan_the_tree_the_world_and_the_items_in_arrival_order():
    items = [art(k + 1, [topic], added_at=stamp(40 - k)) for k, topic in enumerate(ARRIVALS[:42])]  # the later the id, the earlier the item
    plan, tv, world, ordered = bibliopolis.build_world({"items": items}, TREE)
    assert plan["mode"] == "grow" and "t0" in tv and [a["id"] for a in ordered] == [a["id"] for a in reversed(items)]
    assert world["seq"] == 42 and world["mode"] == "grow" and ROOT in world["places"]
    assert all(e["at"] == ordered[e["seq"] - 1]["added_at"] for e in world["chronicle"])  # the date of the item whose arrival caused the entry


def test_a_document_can_be_made_without_its_coast():
    assert "coast" not in city(42, with_coast=False) and "coast" in city(42)


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_the_summary_of_a_town_hall_with_nothing_else_is_zeros(mode):
    doc = bibliopolis.build_city({"items": []}, TREE, mode=mode)
    assert bibliopolis.summary(doc) == {"mode": mode, "houses": 0, "roads": 0, "underground": 0, "splits": 0, "over": 0}


# ----------------------------------------------------------------------------------------------- a replay ----
def sample():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "examples"
    return json.loads((root / "tree.json").read_text(encoding="utf-8")), json.loads((root / "library.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_first_replays_the_growth_the_plan_still_reads_the_whole_library(mode):
    tree, library = sample()
    full = bibliopolis.build_city(library, tree, mode=mode)
    for n in (0, 1, 40, 41, 150, 599):
        part = bibliopolis.build_city(library, tree, mode=mode, first=n)
        assert part["world"]["houses"] == n and part["world"]["seq"] == n
        assert part["composition"]["ring1"] == full["composition"]["ring1"]  # the directions are pinned by the whole library: the same sectors at every moment
        assert part["world"]["chronicle"] == [e for e in full["world"]["chronicle"] if e["seq"] <= n]  # the chronicle so far is the start of the chronicle
    assert bibliopolis.render(bibliopolis.build_city(library, tree, mode=mode, first=600)) == bibliopolis.render(full)  # 600 = all of them
    assert bibliopolis.render(bibliopolis.build_city(library, tree, mode=mode, first=10_000)) == bibliopolis.render(full)  # more than there are: all of them


def test_the_first_forty_items_of_the_sample_are_all_under_the_town_hall_and_the_41st_opens_the_first_road():
    tree, library = sample()
    forty = bibliopolis.build_city(library, tree, first=40)
    assert bibliopolis.summary(forty) == {"mode": "grow", "houses": 40, "roads": 0, "underground": 40, "splits": 0, "over": 0} and forty["roads"] == {}
    forty_one = bibliopolis.build_city(library, tree, first=41)
    (entry,) = forty_one["world"]["chronicle"]
    assert (entry["seq"], entry["from"], entry["to"]) == (41, "place:root", "place:tag:computing") and bibliopolis.summary(forty_one)["roads"] == 1


def test_a_mirror_replay_of_no_items_is_the_street_plan_alone():
    tree, library = sample()
    plan = bibliopolis.build_city(library, tree, mode="mirror", first=0)
    assert plan["world"]["houses"] == 0 and bibliopolis.summary(plan)["roads"] == 79 and all(p["lots"] == 0 for p in plan["places"].values() if p["kind"] == "street")


@pytest.mark.parametrize("first", [-1, 1.5, True, "3"])
def test_first_must_be_a_whole_number_of_items(first):
    tree, library = sample()
    with pytest.raises(ValueError, match="first"):
        bibliopolis.build_city(library, tree, first=first)


def test_the_command_line_replays_with_first(tmp_path, capsys):
    tree, library = sample()
    (tmp_path / "t.json").write_text(json.dumps(tree), encoding="utf-8")
    (tmp_path / "l.json").write_text(json.dumps(library), encoding="utf-8")
    out = tmp_path / "city41.json"
    assert cli.main(["build", "--library", str(tmp_path / "l.json"), "--tree", str(tmp_path / "t.json"), "--first", "41", "--out", str(out)]) == 0
    assert capsys.readouterr().err.strip() == f"wrote {out}: 41 houses on 1 roads, 26 under the town hall, 1 splits, 0 over (mode grow)"
    assert cli.main(["build", "--library", str(tmp_path / "l.json"), "--tree", str(tmp_path / "t.json"), "--first", "-3", "--out", str(tmp_path / "x.json")]) == 2
    assert "first must be a whole number" in capsys.readouterr().err and not (tmp_path / "x.json").exists()
