"""The log of a line and the laying that derives the rest from it (bibliopolis.world, "the log of a line").

A line keeps what was DECIDED in a log, in radial order: its members, their branch circles, its bands (with the ribs of each side in order and their widths) and the ribs
along its spoke. Every radius, every road and every lot is derived from it by `World.lay_line`. These tests hold the log to the world: it names every span once, in radial
order, and a world laid again from its log is the world, byte for byte (the instrument of that proof is tested too: it finds a world that is not what its log lays).
"""

import copy
import math

import checks
import pytest
from hand_support import play, scripted, scripted_branches, scripted_merge, scripted_nodes
from support import lay_problems, sample, simulate_districts

from bibliopolis import city
from bibliopolis import world as zw
from bibliopolis.hand import HandWorld
from bibliopolis.world import BAND, BRANCH_CLEAR, EPS, LEAD


def ribs_in(entry):
    """The rib entries of one entry of a log: the ribs of both sides of a band in order, the rib along the spoke, none for a member or a circle."""
    if entry["kind"] == "band":
        return [r for side in entry["ribs"] for r in side]
    return [entry["rib"]] if entry["kind"] == "spoke" else []


def span_of(line, entry):
    """(lo, hi) of a span of a line as the line holds it now; None for a member, which is a point and a lead."""
    if entry["kind"] == "band":
        s = line["bands"][entry["band"]]["s"]
        return s - BAND / 2, s + BAND / 2
    if entry["kind"] == "spoke":
        return tuple(line["spokes"][entry["spoke"]])
    if entry["kind"] == "branch":
        r1 = next(m for m in line["members"] if m["place"] == entry["place"])["r1"]
        return r1 - BRANCH_CLEAR, r1 + BRANCH_CLEAR
    return None


# ------------------------------------------------------------------------------------------ the log is the line ----
def test_the_log_of_a_line_names_every_member_circle_band_and_spoke_rib_once():
    for seed in (3, 7):
        _problems, doc, _steps, _plan, _tv = simulate_districts(seed)
        for lid, line in doc["lines"].items():
            log = line["log"]
            assert log and log[0]["kind"] == "member" and {e["kind"] for e in log} <= {"member", "branch", "band", "spoke"}
            assert [e["place"] for e in log if e["kind"] == "member"] == [m["place"] for m in line["members"]], lid
            assert [e["place"] for e in log if e["kind"] == "branch"] == [m["place"] for m in line["members"] if m["r1"] is not None], lid
            assert sorted(e["band"] for e in log if e["kind"] == "band") == list(range(len(line["bands"]))), lid
            assert sorted(e["spoke"] for e in log if e["kind"] == "spoke") == list(range(len(line["spokes"]))), lid
            for i, e in enumerate(log):  # a circle is drawn when its member opens: it follows it at once
                if e["kind"] == "branch":
                    assert log[i - 1] == {"kind": "member", "place": e["place"]}


def test_the_entries_of_the_log_are_in_radial_order_whatever_the_order_the_ribs_opened_in():
    """Inner to outer, for every two entries: a span ends at or below the start of one after it; a member opens at the frontier of what lies before it, so every span before
    a member ends at or below its start; a member lies before a span when it starts below the end of the span (the lead of a member is no span: a span that starts in the lead of
    a member and ends beyond it is laid after the member). Seeds 1 and 7 hold such spans; seed 3 holds bands that sit in a gap inward of a band that opened before them."""
    in_a_gap = 0
    for seed in (1, 3, 7, 12):
        _problems, doc, _steps, _plan, _tv = simulate_districts(seed)
        for lid, line in doc["lines"].items():
            log, members = line["log"], {m["place"]: m for m in line["members"]}
            for i, e in enumerate(log):
                for f in log[i + 1:]:
                    if e["kind"] == "member" and f["kind"] == "member":
                        assert members[e["place"]]["s0"] < members[f["place"]]["s0"], (lid, e, f)
                    elif e["kind"] == "member":
                        assert members[e["place"]]["s0"] < span_of(line, f)[1] - EPS, (lid, e, f)
                    elif f["kind"] == "member":
                        assert span_of(line, e)[1] <= members[f["place"]]["s0"] + EPS, (lid, e, f)
                    else:
                        assert span_of(line, e)[1] <= span_of(line, f)[0] + EPS, (lid, e, f)
            opened = [e["band"] for e in log if e["kind"] == "band"]
            in_a_gap += opened != sorted(opened)
    assert in_a_gap


def test_a_rib_of_the_log_is_the_rib_of_its_street_and_a_band_lists_its_roads_in_order_along_each_side():
    _problems, doc, _steps, _plan, _tv = simulate_districts(3)
    places, roads = doc["places"], doc["roads"]
    live = {pid for pid, p in places.items() if p["kind"] == "street" and "rib" in p}
    seen = set()
    for lid, line in doc["lines"].items():
        for e in line["log"]:
            for r in ribs_in(e):
                assert r["place"] in live and not r.get("ghost"), r
                rib = places[r["place"]]["rib"]
                assert r["width"] == math.ceil(rib["slots"] / 2) and r["carrier"] == rib["trunk"] and rib["line"] == lid
                assert (r["road"] is None) == (rib["mode"] == "spoke")
                seen.add(r["place"])
            if e["kind"] == "band":
                band = line["bands"][e["band"]]
                for i, (side, rib_side) in enumerate(zip((-1, 1), e["ribs"])):
                    offs = [roads[r["road"]]["off"] for r in rib_side]
                    assert offs == sorted(offs) and band["last"][i] == (rib_side[-1]["road"] if rib_side else None)
                    assert {places[r["place"]]["rib"]["side"] for r in rib_side} <= {side}
    assert seen == live


# ---------------------------------------------------------------------------- a world laid again is the world ----
CONFIGS = [{}, {"max_houses": 8, "min_houses": 3, "trunk_min": 10}, {"max_houses": 20, "min_houses": 5, "trunk_min": 120, "batch_max": 5}, {"mode": "mirror"},
           {"max_houses": 12, "min_houses": 12, "order": "by_tag"}]


@pytest.mark.parametrize("kw", CONFIGS)
def test_a_random_world_laid_again_from_its_log_is_the_world_to_the_last_lot(kw):
    for seed in (0, 1, 7, 12):
        problems, doc, _steps, plan, tv = simulate_districts(seed, check_every=1000, **kw)
        assert problems == []
        assert lay_problems(doc, plan, tv, full=True) == [], (kw, seed)


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_the_sample_laid_again_from_its_log_is_the_sample(mode):
    tree, library = sample()
    plan, tv, world, _items = city.build_world(library, tree, mode=mode)
    assert len(world["lines"]) > 5 and lay_problems(world, plan, tv, full=True) == []


@pytest.mark.parametrize("build", [scripted, scripted_nodes, scripted_merge, scripted_branches])
def test_the_golden_worlds_built_by_hand_laid_again_from_their_logs_are_themselves(build):
    state = build().journal.state
    again = HandWorld(zw.PlanView(state.plan), state.tree, state.doc, event_id=0)
    assert state.doc["lines"] and lay_problems(state.doc, state.plan, state.tree, world=again, full=True) == []


@pytest.mark.parametrize("seed", [0, 4])
def test_the_ghosts_of_roads_that_moved_and_merged_lay_as_they_stood(seed):
    """A road that moves leaves its rib in the log as a ghost with its width and its road: the ground it claimed stays claimed."""
    state = play(seed, steps=150, merging=True).state
    ghosts = [(lid, r) for lid, line in state.doc["lines"].items() for e in line["log"] for r in ribs_in(e) if r.get("ghost")]
    assert len(ghosts) > 10
    for lid, r in ghosts:
        assert r["road"] is None or r["road"] in state.doc["roads"]
        assert r["width"] >= 1 and r["carrier"] in state.plan["trunks"]
    again = HandWorld(zw.PlanView(state.plan), state.tree, state.doc, event_id=0)
    assert lay_problems(state.doc, state.plan, state.tree, world=again, full=True) == []


def test_a_span_that_starts_in_the_lead_of_a_member_is_laid_after_the_member_and_neither_moves_when_the_line_is_laid_again():
    """Seed 7 has a band, seed 1 a rib along the spoke, that starts below the start of a member and overlaps its lead: the member opened at the frontier of what stood, the
    span came later, so it is laid after the member. A line laid with the span before the member would open the member beyond the span."""
    for seed, kind in ((7, "band"), (1, "spoke")):
        _problems, doc, _steps, plan, tv = simulate_districts(seed, check_every=1000)
        found = []
        for lid, line in doc["lines"].items():
            members = {m["place"]: m for m in line["members"]}
            for i, e in enumerate(line["log"]):
                for f in line["log"][i + 1:]:
                    if e["kind"] == "member" and f["kind"] == kind and span_of(line, f)[0] < members[e["place"]]["s0"] - EPS:
                        found.append((lid, e["place"], f))
        assert found, (seed, kind)
        assert lay_problems(doc, plan, tv, full=True) == []
        lid, place, f = found[0]
        line = copy.deepcopy(doc["lines"][lid])  # the same entries with that span moved before the member: the member would open beyond it
        i, j = line["log"].index({"kind": "member", "place": place}), line["log"].index(f)
        line["log"].insert(i, line["log"].pop(j))
        w = zw.World(zw.PlanView(plan), tv, doc)
        wrong, right = w.derive(line), w.derive(doc["lines"][lid])
        assert [m["s0"] for m in wrong["members"]] != [m["s0"] for m in right["members"]]


# ---------------------------------------------------------------------------- the instrument can fail ----
def first(doc, store, test):
    return next(key for key, rec in doc[store].items() if test(rec))


def mutations(doc):
    """(what, a function that damages a copy of the world in one record): each is a world that is not what its log lays."""
    line_id, line = next((k, rec) for k, rec in doc["lines"].items()
                         if rec["bands"] and rec["spokes"] and len(rec["members"]) > 1 and any(m["r1"] is not None for m in rec["members"]))
    circle = next(k for k, m in enumerate(line["members"]) if m["r1"] is not None)
    arc = next(a["road"] for m in line["members"] for a in m["arcs"].values() if a)
    lot = first(doc, "places", lambda p: p["kind"] == "lot" and not p["parent"].startswith("place:root"))
    empty = first(doc, "places", lambda p: p["kind"] == "reserved")
    on_band = first(doc, "places", lambda p: p["kind"] == "street" and "rib" in p and p["rib"]["mode"] == "band")
    on_spoke = first(doc, "places", lambda p: p["kind"] == "street" and "rib" in p and p["rib"]["mode"] == "spoke")
    lane = first(doc, "roads", lambda r: r["kind"] == "lane")

    def bump(path, delta):
        def make(d):
            node = d
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = node[path[-1]] + delta
        return make

    yield "the start of a member", bump(("lines", line_id, "members", 1, "s0"), 0.001)
    yield "a branch circle", bump(("lines", line_id, "members", circle, "r1"), 0.001)
    yield "the radius of a band", bump(("lines", line_id, "bands", 0, "s"), 0.001)
    yield "how far a side of a band is used", bump(("lines", line_id, "bands", 0, "used", 1), 0.5)
    yield "the span of a rib along the spoke", bump(("lines", line_id, "spokes", 0, 0), 0.001)
    yield "the start of a rib on a band", bump(("places", on_band, "rib", "x0"), 0.5)
    yield "the end of a rib on a band", bump(("places", on_band, "rib", "x1"), 0.5)
    yield "the reach of a rib on a band", bump(("places", on_band, "rib", "reach"), 0.001)
    yield "the start of a rib along the spoke", bump(("places", on_spoke, "rib", "s"), 0.001)
    yield "the position of a house", bump(("places", lot, "position", "x"), 0.001)
    yield "the position of an empty lot", bump(("places", empty, "position", "z"), 0.001)
    yield "the length of a road on a band", bump(("roads", lane, "length"), 0.001)
    yield "the radius of a road on a band", bump(("roads", lane, "radius"), 0.001)
    yield "where a spoke ends", bump(("roads", line["members"][-1]["road"], "s_end"), 0.001)
    yield "an arc", bump(("roads", arc, "length"), 0.001)

    def widen(d):
        rib = next(e for e in d["lines"][line_id]["log"] if e["kind"] == "band")["ribs"][0][0]
        rib["width"] += 1
    yield "the width of a rib in the log", widen

    def drop_point(d):
        d["roads"][lane]["points"] = d["roads"][lane]["points"][:-1]
    yield "a point of a road", drop_point


def test_the_instrument_finds_a_world_that_is_not_what_its_log_lays():
    """The proof that a world is laid by its log is only worth something if the check can fail: every damage to one record of a sound world is found."""
    _problems, doc, _steps, plan, tv = simulate_districts(7, check_every=1000)
    assert lay_problems(doc, plan, tv) == [] and checks.all_problems(doc) == {}
    made = 0
    for what, damage in mutations(doc):
        bad = copy.deepcopy(doc)
        damage(bad)
        assert lay_problems(bad, plan, tv), what
        made += 1
    assert made == 17
