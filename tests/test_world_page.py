"""What docs/world.md says is true of the program: its examples load through the readers, its tables are the program's tables, its commands parse, its Python runs."""

import json
import re
import shlex
from pathlib import Path

import pytest
import refusal_cases as rc
from hand_support import Hand, every_entry, hid, item, sample_world_items, stamp, topic

from bibliopolis import cli, hand
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
    rows = re.findall(r"\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*(-?[\d.]+) \.\. (-?[\d.]+)\s*(?=\|)", PAGE)  # (two roads to a line: the left half, then the right half)
    assert sorted(int(k) for k, *_ in rows) == list(range(13))
    given = []
    for k in range(13):
        given.append(hand.ring1_wedge(given, k))
    for k, bearing, lo, hi in rows:
        k = int(k)
        assert round(float(bearing) * 100) == hand.bearing(k), k
        assert (round(float(lo) * 100), round(float(hi) * 100)) == given[k], k
    assert "| 13 | 347.60 | none: inside the sector of k = 0 |" in PAGE and f"{hand.bearing(13) / 100:.2f}" == "347.60"
    assert "**a town has at most 13 avenues**" in PAGE and "**the 14th category goes below an avenue**" in PAGE and hand.AVENUES == 13
    assert str(hand.GOLDEN) in PAGE and "% 36000" in PAGE and "// 10**12" in PAGE


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
    assert len(rows) == 7
    entries = list(entries_of_a_world().values())
    kinds = {"road opened": "from", "house filed": "filed", "road renamed": "renamed", "road moved": "moved", "merge of avenues": "merged", "undo": "undone", "change of rule": "rule"}
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


def test_the_limits_the_page_states_are_the_limits_of_the_program():
    h = Hand()
    h.add(10)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    with pytest.raises(ev.Refusal):
        h.journal.append("move_road", {"road": "a", "parent": None}, stamp(99))  # a road is not made a ring-1 road by a move
    assert "A road never becomes a ring-1 road by moving" in PAGE and "No trunk is promoted" in PAGE
    assert "never marked over" in PAGE and "A road for a topic is not split" in PAGE
    assert (ROOT / "docs" / "engine.md").is_file() and "[engine.md](engine.md)" in PAGE


def test_the_numbers_the_page_gives_for_the_sample_are_the_numbers_of_the_program():
    found = re.search(r"the rule makes (\d+) roads \(domains (\d+), fields (\d+), subfields (\d+), topics (\d+)\), and (\d+) houses stay underground", PAGE)
    assert found, "the sentence about the sample is not on the page"
    h = Hand({"max": 40, "min": 10, "auto": True})
    h.add_items(sample_world_items())
    levels = [sum(1 for n in h.state.nodes.values() if n["topic"]["level"] == level) for level in ev.ORDER]
    assert [int(x) for x in found.groups()] == [len(h.state.nodes), *levels, h.state.count(None)]


# ------------------------------------------------------------------------------------------ for a port ----
def test_the_widths_of_the_sectors_the_page_gives_for_the_merge_are_the_widths_of_the_table_in_whole_tenths_of_a_degree():
    spans = [hi - lo for lo, hi in hand.SECTORS]
    assert [f"{n / 100:.2f}" for n in spans] == ["40.00"] * 5 + ["32.46", "32.46", "32.47"] + ["12.52", "12.52", "12.52", "12.53", "12.52"]
    assert [hand.tenths(n) / 10 for n in spans] == [40.0] * 5 + [32.5] * 3 + [12.5] * 5
    page = " ".join(PAGE.split())
    assert "40.0 for the numbers 0 to 4, 32.5 for 5 to 7 (32.46, 32.46 and 32.47) and 12.5 for 8 to 12 (12.52, 12.52, 12.52, 12.53 and 12.52)" in page
    assert "whole tenths of a degree, rounded half up (`(span + 5) // 10` for a span in units of 1/100 degree)" in page and "so 32.46 and 32.47 are both 325 and 12.52 and 12.53 both 125" in page


def test_the_check_the_page_names_for_a_port_is_in_the_repository():
    import hand_support

    section = PAGE.split("## For a port")[1].split("## Limits")[0]
    for name in ("scripted", "scripted_nodes", "scripted_merge"):
        assert f"`{name}`" in section and callable(getattr(hand_support, name)), name
    pins = (ROOT / "tests" / "test_world_file.py").read_text(encoding="utf-8")
    assert all(pin in pins for pin in ("PIN_WORLD", "PIN_CITY", "PIN_NODES_WORLD", "PIN_NODES_CITY", "PIN_MERGE_WORLD", "PIN_MERGE_CITY"))


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
    for k in range(3):
        h.add(6)
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
