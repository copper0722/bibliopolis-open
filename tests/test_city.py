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


# ------------------------------------------------------------------------------------------ the chronicle ----
def chronicle_doc(*entries, places=None):
    return {"places": places or {}, "world": {"districts": {"max": 40, "min": 10}, "chronicle": list(entries)}}


def test_the_chronicle_of_the_sample_reads_as_sentences_one_per_entry():
    tree, library = sample()
    doc = bibliopolis.build_city(library, tree)
    lines = bibliopolis.city.chronicle_lines(doc)
    assert len(lines) == len(doc["world"]["chronicle"]) == 23
    assert lines[:4] == [
        "house 41, 2019-06-26: The root zone held 41 houses. Computing opens as a road with 15 of them; 26 stay.",
        "house 62, 2019-10-15: The root zone held 41 houses. Physical sciences opens as a road with 12 of them; 29 stay.",
        "house 85, 2020-01-26: The root zone held 41 houses. Life sciences opens as a road with 17 of them; 24 stay.",
        "house 130, 2020-08-12: Computing held 41 houses. Systems opens as a road with 20 of them; 21 stay.",
    ]
    assert lines[18] == "house 575, 2026-06-02: Networks holds 41 houses, more than 40, and no group of 10 or more can open a road. It is marked over."
    assert bibliopolis.city.chronicle_lines(doc, 2) == lines[:2] and bibliopolis.city.chronicle_lines(doc, 0) == []


def test_every_number_of_a_sentence_comes_from_its_entry_or_the_rule_of_the_document():
    tree, library = sample()
    doc = bibliopolis.build_city(library, tree, max_houses=30, min_houses=6)
    for line, entry in zip(bibliopolis.city.chronicle_lines(doc), doc["world"]["chronicle"]):
        if "from" in entry:
            assert f"held {entry['count_before']} houses" in line and f"with {len(entry['houses'])} of them" in line and f"{entry['count_after']} stay" in line
        else:
            assert f"holds {entry['count']} houses, more than 30, and no group of 6 or more" in line
    assert any("more than 30" in line for line in bibliopolis.city.chronicle_lines(doc))


def test_the_day_is_the_date_part_of_at_whatever_the_library_wrote_and_is_left_out_when_there_is_none():
    base = {"n": 1, "seq": 7, "from": "place:root", "to": "place:tag:a", "label": "Alpha", "houses": ["h1"], "count_before": 41, "count_after": 40}
    places = {"place:root": {"underground": True, "address": ["根區"]}}
    cases = [("2026-06-02", ", 2026-06-02"), ("2026-06-02T09:30:00+08:00", ", 2026-06-02"), ("2026-06-02 09:30:00", ", 2026-06-02"), ("last week", ", last week"),
             ("", ""), (None, "")]
    for at, shown in cases:
        entry = {**base, **({"at": at} if at is not None else {})}
        assert bibliopolis.city.chronicle_lines(chronicle_doc(entry, places=places))[0].startswith(f"house 7{shown}: The root zone held 41 houses.")


def test_a_road_is_named_by_its_address_the_root_zone_by_its_flag_and_a_place_the_document_lacks_by_its_id():
    places = {"place:root": {"underground": True, "address": ["根區"]}, "place:tag:a": {"address": ["Alpha", "Beta"]}}
    split = {"seq": 3, "from": "place:tag:a", "to": "place:tag:b", "label": "Gamma", "houses": ["h1", "h2"], "count_before": 41, "count_after": 39}
    over = {"seq": 4, "over": "place:tag:zzz", "count": 44}
    root = {"seq": 5, "over": "place:root", "count": 41}
    lines = bibliopolis.city.chronicle_lines(chronicle_doc(split, over, root, places=places))
    assert lines == ["house 3: Beta held 41 houses. Gamma opens as a road with 2 of them; 39 stay.",
                     "house 4: place:tag:zzz holds 44 houses, more than 40, and no group of 10 or more can open a road. It is marked over.",
                     "house 5: The root zone holds 41 houses, more than 40, and no group of 10 or more can open a road. It is marked over."]


def test_the_chronicle_of_a_mirror_city_is_the_roads_that_became_crowded():
    tree = forest("a", "b")
    items = [art(k + 1, ["a"], added_at=stamp(k)) for k in range(45)] + [art(100, ["b"], added_at=stamp(60))]
    doc = bibliopolis.build_city({"items": items}, tree, mode="mirror")
    lines = bibliopolis.city.chronicle_lines(doc)
    assert len(lines) == 1 and lines[0].startswith("house 41") and "A holds 41 houses, more than 40" in lines[0] and "marked over" in lines[0]
    assert bibliopolis.city.chronicle_lines(bibliopolis.build_city({"items": items[:5]}, tree, mode="mirror")) == []


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_a_replay_keeps_the_bearing_and_the_start_of_every_road_which_then_only_grows_longer(mode):
    tree, library = sample()
    full = bibliopolis.build_city(library, tree, mode=mode)
    for n in (41, 150, 300):
        part = bibliopolis.build_city(library, tree, mode=mode, first=n)
        axes = {pid: p["axis"] for pid, p in part["places"].items() if p["kind"] == "street" and p.get("axis") is not None}
        assert axes and all(full["places"][pid]["axis"] == axis for pid, axis in axes.items()), (mode, n)
        spokes = [(rid, road) for rid, road in part["roads"].items() if road["kind"] == "spoke"]
        assert spokes
        for rid, road in spokes:
            later = full["roads"][rid]
            assert later["axis"] == road["axis"] and later["points"][0] == road["points"][0] and later["length"] >= road["length"], (mode, n, rid)
    if mode == "grow":  # the first road of the sample is 9.67 cells long at house 41, and longer in the whole city
        assert bibliopolis.build_city(library, tree, first=41)["roads"]["road:place:tag:computing"]["length"] < full["roads"]["road:place:tag:computing"]["length"]
