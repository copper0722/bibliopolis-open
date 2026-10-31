"""What docs/world.md says is true of the program: its examples load through the readers, its tables are the program's tables, its commands parse, its Python runs."""

import json
import re
import shlex
from pathlib import Path

import pytest
import refusal_cases as rc
from hand_support import Hand, every_entry, hid, item, sample_world_items, stamp, topic
from support import cells_table, sample

import bibliopolis
from bibliopolis import cli, hand
from bibliopolis.document import NOTES_DISTRICTS
from bibliopolis.suggest import suggest_file, suggest_road
from bibliopolis import events as ev

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "world.md").read_text(encoding="utf-8")


def blocks(language):
    return re.findall(rf"^```{language}\n(.*?)^```", PAGE, flags=re.S | re.M)


def json_values(block):
    decoder, i, out = json.JSONDecoder(), 0, []
    while True:
        while i < len(block) and block[i].isspace():
            i += 1
        if i >= len(block):
            return out
        value, i = decoder.raw_decode(block, i)
        out.append(value)


def test_every_json_example_of_the_page_is_an_item_or_an_event_that_the_readers_take():
    values = [v for block in blocks("json") for v in json_values(block)]
    assert len(values) >= 2
    for value in values:
        problems = ev.Problems()
        if "kind" in value:
            assert ev.check_event(value, "example", problems) == value, problems.found
        else:
            assert "openalex" in value and ev.check_item(value, "example", problems) == value, problems.found
        assert problems.found == []


def test_the_sector_table_is_the_table_of_the_program():
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*(-?[\d.]+) \.\. (-?[\d.]+)\s*\|\s*([\d.]+)\s*\|$", PAGE, flags=re.M)
    assert sorted(int(k) for k, *_ in rows) == list(range(13))
    table = cells_table(13)  # found by looking at every other bearing, not by the program's own function
    assert table == list(hand.sector_table(13))
    for k, bearing, lo, hi, width in rows:
        k = int(k)
        assert round(float(bearing) * 100) == hand.bearing(k), k
        assert (round(float(lo) * 100), round(float(hi) * 100)) == table[k][:2], k
        assert round(float(width) * 100) == table[k][1] - table[k][0], k
    assert "bearing(k) = (k * 13750776405003785 + 500000000000) // 10**12 % 36000" in PAGE and "[b - min(2000, before // 2), b + min(2000, (after + 1) // 2)]" in PAGE
    assert "A road holds at most N = `branches` roads directly, at every level" in PAGE and "`branches_full`" in PAGE and "The bearings **do not depend on how many directions there are**" in PAGE
    assert str(hand.GOLDEN) in PAGE and "% 36000" in PAGE and "// 10**12" in PAGE


def test_the_radii_the_page_gives_are_the_radii_of_the_program():
    page = " ".join(PAGE.split())
    assert "With a `max` of 40 it is 8.5 for 5 and for 13 branches, 12.5 for 21, 21.5 for 34 and 57.5 for 89 (the narrowest land is 40.00, 20.06, 12.38, 7.66 and 2.92 degrees" in page
    for n, radius, land in ((5, 8.5, 40.0), (13, 8.5, 20.06), (21, 12.5, 12.38), (34, 21.5, 7.66), (89, 57.5, 2.92)):
        assert hand.ring_radius({"max": 40, "branches": n}) == radius
        assert min(2 * min(axis - lo, hi - axis) for lo, hi, axis in cells_table(n)) / 100 == land  # (the land is found from the independent table)


def test_the_tables_of_refusal_ids_are_the_ids_the_params_and_the_messages_of_the_program(tmp_path):
    """Every id of `events.CODES`, once and in the order of the list, with its params and the message that its scenario (tests/refusal_cases.py) makes."""
    section = PAGE.split("## Refusals")[1].split("## Suggestions")[0]
    rows = re.findall(r"^\| `(\w+)` \| (.+?) \| (.+?) \| (.+) \|$", section, flags=re.M)
    assert [code for code, *_ in rows] == list(ev.CODES)
    for code, params, when, message in rows:
        assert (() if params == "none" else tuple(re.findall(r"`(\w+)`", params))) == ev.CODES[code], code
        assert when.strip(), code
        folder = tmp_path / code
        folder.mkdir()
        made = rc.CASES[code](folder)
        shown = made["text"] if isinstance(made, dict) else str(made).replace(str(folder), "<folder>")
        assert message == shown.splitlines()[0], code
    assert "tests/refusal_cases.py" in PAGE and "bibliopolis.events.CODES" in PAGE


def test_the_table_of_events_names_the_kinds_and_the_payloads_of_the_program():
    rows = re.findall(r"^\| `(\w+)` \| `\{([\w, ]+)\}` \|", PAGE, flags=re.M)
    assert [kind for kind, _ in rows] == list(ev.KINDS)
    for kind, keys in rows:
        assert tuple(k.strip() for k in keys.split(",")) == ev.PAYLOAD_KEYS[kind], kind


def entries_of_a_world():
    return {tuple(sorted(set(e) - {"n", "event_id", "seq", "trigger", "at"})): e for e in every_entry().state.city()["world"]["chronicle"]}


def test_the_table_of_chronicle_entries_has_the_keys_the_engine_writes_in_that_order():
    rows = re.findall(r"^\| (?:a |an )(.+?) \| (.+?) \|$", PAGE.split("The chronicle.")[1].split("An event that an undo")[0], flags=re.M)
    assert len(rows) == 10
    entries = list(entries_of_a_world().values())
    kinds = {"road opened": "from", "house filed": "filed", "road renamed": "renamed", "road moved": "moved", "merge of roads": "merged", "undo": "undone", "change of rule": "rule",
             "new radius": "resized", "annex placed": "annex", "house absorbed": "absorbed"}
    for what, cell in rows:
        shown = re.findall(r"`(\w+)`", cell)
        marker = next(v for k, v in kinds.items() if what.startswith(k))
        entry = next(e for e in entries if marker in e)
        assert list(entry) == ["n", "event_id", "seq", "trigger", *shown, "at"], what


def test_the_commands_of_the_page_are_commands_of_the_program():
    lines = [line.strip() for block in blocks("") for line in block.splitlines() if line.strip().startswith("python3 -m bibliopolis ")]
    assert len(lines) == 5
    parser = cli.build_parser()
    for line in lines:
        words = shlex.split(line.split("   ")[0])
        args = parser.parse_args(words[3:])
        assert args.command in ("world", "picture"), line
    assert {shlex.split(line.split("   ")[0])[4] for line in lines if " world " in line} == {"new", "import", "export", "fold"}


def test_the_python_of_the_page_runs():
    (code,) = blocks("python")
    scope = {"item": item(1, topic(1, 1, 1, 1))}
    exec(compile(code, "docs/world.md", "exec"), scope)  # noqa: S102 - the page is the repository's own
    assert scope["journal"].state.items and scope["suggest_road"]


def test_the_help_of_new_auto_says_what_the_page_says_the_rule_does(capsys):
    """An arrival stands on the deepest road whose node it is under, and a place that then holds more than `max` houses opens a road for its largest group, one level of OpenAlex below it:
    the help of `world new --auto` once said the ring road only."""
    rule = " ".join(PAGE.split("**The rule `auto`.**")[1].split("**Numbers.**")[0].split())
    with pytest.raises(SystemExit):
        cli.main(["world", "new", "--help"])
    shown = " ".join(capsys.readouterr().out.split())
    for phrase in ("the deepest road whose node it is under", "for the largest group of its houses one level below the place"):
        assert phrase in rule and phrase in shown, phrase


def test_the_notes_of_a_city_say_that_the_rule_auto_splits_a_road_by_itself_and_that_nothing_else_does():
    h = Hand({"max": 5, "min": 2, "auto": True})
    h.add(8, topic(1, 1, 1, 1))  # the sixth house takes the ring road over 5: a road for the domain, which splits by field, by subfield and by topic in the same event
    h.add(2, topic(1, 1, 1, 1))
    state = h.state
    assert list(state.nodes) == ["auto:6", "auto:6.2", "auto:6.3", "auto:6.4"] and [n["parent"] for n in state.nodes.values()] == [None, "auto:6", "auto:6.2", "auto:6.3"]
    mode = state.city()["world"]["notes"]["world.mode"]
    assert "nothing splits by itself except under `auto`" in mode and "under the rule `auto`, a road that the rule opened for a node of OpenAlex" in mode
    assert "nothing splits by itself, except under `auto`" in PAGE and "nothing is marked over" in mode  # (the page says it in its Limits)


def test_the_note_on_the_rule_of_a_hand_city_says_what_the_page_says_and_a_grown_city_keeps_its_own():
    """The note `world.districts` said, for a city of a world built by hand too, that a crowded road opens a road for its largest group: only the rule `auto` does, and `max` and `min`
    are what the page says they are."""
    rule = " ".join(PAGE.split("### The rule")[1].split("## What the fold does")[0].split())
    note = Hand({"max": 5, "min": 2, "auto": False}).state.city()["world"]["notes"]["world.districts"]
    for phrase in ("is how many houses a road is meant to hold", "is the least a new road takes"):
        assert phrase in rule and phrase in note, phrase
    assert "a crowded road opens a road" not in note and "only under the rule `auto` does a place that holds more than `max` open a road" in note
    tree, library = sample()
    grown = bibliopolis.build_city(library, tree)["world"]["notes"]["world.districts"]
    assert grown == NOTES_DISTRICTS["world.districts"] and "a crowded road opens a road for its largest group" in grown  # (a grown city is as it was)


def test_the_threat_model_of_the_files_is_on_the_page_and_in_the_card():
    """What the publishing of a file defends against, and what it does not (a hostile process in the same folder), is said in one way on the page and in the card; the tests of publishing follow it."""
    page = " ".join(PAGE.split("## The files")[1].split("## In Python")[0].split())
    card = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    for phrase in ("several runs of this tool by one user at once", "a hostile process with write access to the same folder", "no way of publishing"):
        assert phrase in page and phrase in card, phrase
    assert "(`no_hard_links`" in page and "no_hard_links" not in card and "refused where there are no hard links" in card


def test_the_page_states_the_scope_of_the_restore_in_place_that_the_journal_tests_pin():
    page = " ".join(PAGE.split())
    for phrase in ("the State, its live tree and its main dictionaries (`nodes`, `items`, `road_of`, `annexes`, `plan`, `held`, `kinds`, `effects`) are the same objects afterwards",
                   "`rule`, the document and the record of each road are replaced by the copies taken before", "The copy of the event that `append` gives back is made before anything changes"):
        assert phrase in page, phrase


def test_the_page_says_what_survives_a_crash_and_what_is_left_behind():
    page = " ".join(PAGE.split("## The files")[1].split("## In Python")[0].split())
    for phrase in ("synced to the disk (`fsync`) before it is published, and the folder is synced after the link", "never half a file", "`.<name>.<random>.part`", "the `-journal` of a world that was being built",
                   "a second name for the finished file", "Nothing removes them later"):
        assert phrase in page, phrase


def test_the_limits_the_page_states_are_the_limits_of_the_program():
    h = Hand()
    h.add(10)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    with pytest.raises(ev.Refusal):
        h.journal.append("move_road", {"road": "a", "parent": None}, stamp(99))  # a road is not made a ring-1 road by a move
    assert "A road never becomes a ring-1 road by moving" in PAGE and "No trunk is promoted" in PAGE
    assert f"No road stands deeper than ring {ev.RING_LIMIT} (an avenue is ring 1)" in PAGE and f"Ring {ev.RING_LIMIT} is the last" in PAGE and ev.RING_LIMIT == 64
    assert "never marked over" in PAGE and "A road for a topic is not split" in PAGE
    assert (ROOT / "docs" / "engine.md").is_file() and "[engine.md](engine.md)" in PAGE


def test_the_numbers_the_page_gives_for_the_sample_are_the_numbers_of_the_program():
    found = re.search(r"the rule makes (\d+) roads \(domains (\d+), fields (\d+), subfields (\d+), topics (\d+)\), and (\d+) houses stay on the ring road", PAGE)
    assert found, "the sentence about the sample is not on the page"
    h = Hand({"max": 40, "min": 10, "auto": True})
    h.add_items(sample_world_items())
    levels = [sum(1 for n in h.state.nodes.values() if n["topic"]["level"] == level) for level in ev.ORDER]
    assert [int(x) for x in found.groups()] == [len(h.state.nodes), *levels, h.state.count(None)]


# ------------------------------------------------------------------------------------------ for a port ----
def test_the_widths_of_the_sectors_the_page_gives_for_the_merge_are_the_widths_of_the_table_in_whole_tenths_of_a_degree():
    spans = [hi - lo for lo, hi, _ in hand.sector_table(13)]
    assert [f"{n / 100:.2f}" for n in spans] == ["26.26", "26.26", "26.26", "26.27", "26.26", "32.46", "32.46", "32.47"] + ["26.26"] * 5
    assert [hand.tenths(n) / 10 for n in spans] == [26.3] * 5 + [32.5] * 3 + [26.3] * 5
    page = " ".join(PAGE.split())
    assert "26.3 for the numbers 0 to 4 and 8 to 12 (26.26 and 26.27) and 32.5 for 5 to 7 (32.46, 32.46 and 32.47)" in page
    assert "whole tenths of a degree, rounded half up (`(span + 5) // 10` for a span in units of 1/100 degree)" in page and "so 26.26 and 26.27 are both 263 and 32.46 and 32.47 both 325" in page


def test_the_check_the_page_names_for_a_port_is_in_the_repository():
    import hand_support

    section = PAGE.split("## For a port")[1].split("## Limits")[0]
    for name in ("scripted", "scripted_nodes", "scripted_merge", "scripted_branches"):
        assert f"`{name}`" in section and callable(getattr(hand_support, name)), name
    pins = (ROOT / "tests" / "test_world_file.py").read_text(encoding="utf-8")
    assert all(pin in pins for pin in ("PIN_WORLD", "PIN_CITY", "PIN_NODES_WORLD", "PIN_NODES_CITY", "PIN_MERGE_WORLD", "PIN_MERGE_CITY", "PIN_BRANCHES_WORLD", "PIN_BRANCHES_CITY"))


def test_a_tie_by_code_point_is_not_a_tie_by_utf_16_unit():
    """U+E000 is below U+10000 by code point (Python) and above it by UTF-16 unit (D800 DC00 < E000): the page says a port must compare code points."""
    low, high = "\ue000", "\U00010000"
    assert low < high and low.encode("utf-16-be") > high.encode("utf-16-be")
    h = Hand({"max": 40, "min": 5, "auto": False})
    for name in (high, low):  # the one that comes first by UTF-16 unit arrives first
        top = topic(1, 1, 1, 1)
        top["domain"] = {"id": name, "name": f"Domain {name!r}"}
        for _ in range(5):
            h.add(1, top)
    suggestion = suggest_road(h.state, None)
    assert suggestion["topic"]["id"] == low and len(suggestion["houses"]) == 5  # a group of 5 each: the lower code point wins
    assert "compares Unicode code points" in PAGE and "UTF-16 units" in PAGE


def test_the_road_ids_of_the_line_an_avenue_gave_up_are_free_again_and_the_next_road_of_that_name_takes_them():
    h = Hand({"max": 40, "min": 5, "auto": False})
    for k, size in enumerate((6, 30, 6)):  # (r1 is long: on the new line its spoke rib leaves r2 no spoke rib nearer than a band)
        h.add(size)
        h.open(f"r{k}", f"Road {k}", None, h.state.houses_at(None))
    assert h.state.doc["roads"]["road:place:tag:r2"]["kind"] == "spoke" and "road:place:tag:r2@1" not in h.state.doc["roads"]
    h.merge("m", "M", ["r1", "r2"])
    roads = h.state.doc["roads"]
    assert roads["road:place:tag:r2"]["kind"] == "lane" and "road:place:tag:r2@1" not in roads  # the id of the spoke that was taken away is the id of the first road of r2 now
    assert roads["road:place:tag:r0"]["kind"] == "spoke"  # the avenue that is not a member keeps its own
    assert set(h.state.doc["lines"]) == {"place:tag:r0", "place:tag:m"}  # (the lines of r1 and r2 are gone; the one of r0 stands, and the new avenue has its own)
    h.move("r0", "m")  # an avenue that moves below a road gives its line up too
    assert h.state.doc["roads"]["road:place:tag:r0"]["kind"] == "lane" and set(h.state.doc["lines"]) == {"place:tag:m"} and h.state.held == {1: "m"}


def test_the_confidence_is_rounded_as_python_rounds_a_half_to_the_even_digit():
    h = Hand({"max": 40, "min": 1, "auto": False})
    for k in range(8):
        h.add(1, topic(1, 1, 1, 1))
        h.open(f"r{k}", f"Road {k}", None, [hid(k + 1)])
    h.add(1, topic(1, 1, 1, 1))
    found = suggest_file(h.state, hid(9))
    assert found["confidence"] == 0.12 and 1 / 8 == 0.125  # one of the eight matches, which Math.round would make 0.13
    assert "1/8 is 0.12, not 0.13" in PAGE
