"""What shows of an item that exists for another item: the picture (a wing on the side wall, a mailbox at the gate, a plate above four wings, nothing at a scale where they
merge into the house), the sentences of the chronicle, the numbers of the summary and the line the command prints."""

import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from support import T, art, make_tree

import bibliopolis
from bibliopolis import inputs, picture
from bibliopolis import layout as lay
from bibliopolis.city import chronicle_lines, summary

ROOT = Path(__file__).resolve().parents[1]
PATH = re.compile(r'<path d="([^"]*)" fill="([^"]*)" stroke="([^"]*)" stroke-width="([\d.]+)"/>')
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
MAILBOXES, PLATE = 'stroke-width="0.015"', 'font-size="0.16"'  # what only a mailbox and the number of a plate have in a picture (a plaza, a page and a halo are white and cream too)
TOL = 3e-3  # cells: a corner is written with three decimals, so a box in the frame of its house is as exact as that


def library(wings=0, mailboxes=0, house=2):
    """Seven houses of one topic and three more, a house `house` (its number) with `wings` wings and `mailboxes` mailboxes, in a library."""
    tree, items = make_tree({"med": T(3, a=T(2), b=T(2))})
    parent = items[house - 1]["id"]
    items += [art(20 + k, [], annex_of=parent, annex_form="wing") for k in range(wings)] + [art(40 + k, [], annex_of=parent, annex_form="mailbox") for k in range(mailboxes)]
    return tree, items


def city(wings=0, mailboxes=0, house=2, **kw):
    tree, items = library(wings, mailboxes, house)
    return json.loads(lay.render(bibliopolis.build_city({"items": items}, tree, **kw)))


def corners(path):
    """The boxes of a path as lists of four (x, z) corners."""
    points = [tuple(float(v) for v in NUMBER.findall(pair)) for pair in re.findall(r"[ML]([^MLZ]+)", path)]
    return [points[i:i + 4] for i in range(0, len(points), 4)]


def area(box):
    return abs(sum(box[i][0] * box[(i + 1) % 4][1] - box[(i + 1) % 4][0] * box[i][1] for i in range(4))) / 2


def frame(city_, house):
    """(a, b) of a point (x, z) in the frame of a house: `a` along its front, `b` to its right, from the centre of its cell."""
    lot = city_["places"][f"place:article:a{house:05d}"]
    r = math.radians(lot["facing"])
    x0, z0 = lot["position"]["x"], lot["position"]["z"]
    return lambda x, z: ((x - x0) * math.sin(r) - (z - z0) * math.cos(r), (x - x0) * math.cos(r) + (z - z0) * math.sin(r))


def drawn(doc, pixels=None):
    out: list[str] = []
    picture.draw_annexes(doc, out.append, picture.Look(pixels=pixels))
    return out


def wings_of(doc, house, pixels=None):
    """The boxes drawn as wings of the house, in its frame: [(a0, a1, b0, b1)]."""
    to = frame(doc, house)
    lines = drawn(doc, pixels)
    boxes = []
    for line in lines:
        m = PATH.match(line)
        if m and m.group(2) == m.group(3):  # a wing has the colour of its district for fill and edge; a plate and a mailbox do not
            for box in corners(m.group(1)):
                local = [to(x, z) for x, z in box]
                boxes.append((min(a for a, _ in local), max(a for a, _ in local), min(b for _, b in local), max(b for _, b in local)))
    return boxes


# ------------------------------------------------------------------------------------------------- the wings ----
@pytest.mark.parametrize("wings", [1, 2, 3, 4])
def test_a_wing_is_a_small_box_against_the_side_wall_of_its_house_and_the_wings_run_back_from_the_front(wings):
    doc = city(wings=wings)
    boxes = wings_of(doc, 2)
    assert len(boxes) == wings
    for a0, a1, b0, b1 in boxes:
        assert (a1 - a0) * (b1 - b0) <= 1 / 3 and -0.5 - TOL <= a0 < a1 <= 0.5 + TOL and 0.2 - TOL <= b0 < b1 <= 0.5 + TOL  # inside the cell, against the right wall
    fronts = [a1 for _a0, a1, _b0, _b1 in boxes]
    assert fronts == sorted(fronts, reverse=True) and fronts[0] > 0.4  # the first at the front, the others behind it
    assert sum((a1 - a0) * (b1 - b0) for a0, a1, b0, b1 in boxes) <= 1 / 3  # all of them together: a third of the footprint at most


def test_the_wings_of_a_house_do_not_overlap_each_other_and_the_first_to_arrive_is_at_the_front():
    boxes = wings_of(city(wings=4), 2)
    assert all(boxes[i][0] >= boxes[i + 1][1] for i in range(3))
    again = wings_of(city(wings=2), 2)
    assert again == boxes[:2]  # (the first two wings stand where they stand with four)


def test_above_four_wings_four_are_drawn_and_a_plate_shows_the_total():
    for wings, plated in ((4, False), (5, True), (6, True), (9, True)):
        doc = city(wings=wings)
        lines = drawn(doc)
        assert len(wings_of(doc, 2)) == min(wings, 4)
        texts = [m.group(1) for line in lines for m in [re.search(r">(\d+)</text>", line)] if m]
        assert texts == ([str(wings)] if plated else []), wings
        assert sum(1 for line in lines if line.startswith("<path") and 'fill="#ffffff"' in line) == int(plated)  # the plate itself


def test_the_plate_stands_inside_the_cell_clear_of_the_wings():
    doc = city(wings=5)
    to = frame(doc, 2)
    plate = next(PATH.match(line) for line in drawn(doc) if 'fill="#ffffff"' in line)
    local = [to(x, z) for x, z in corners(plate.group(1))[0]]
    a0, a1, b0, b1 = min(a for a, _ in local), max(a for a, _ in local), min(b for _, b in local), max(b for _, b in local)
    assert -0.5 - TOL <= a0 < a1 <= 0.5 + TOL and -0.5 - TOL <= b0 < b1 <= 0.5 + TOL
    assert len(wings_of(doc, 2)) == 4 and all(a1 <= box[0] + TOL or b1 <= box[2] + TOL for box in wings_of(doc, 2))


# ---------------------------------------------------------------------------------------------- the mailboxes ----
@pytest.mark.parametrize("mailboxes", [1, 2, 5, 6, 11])
def test_a_mailbox_is_a_small_mark_at_the_gate_one_for_each_letter_in_rows(mailboxes):
    doc = city(mailboxes=mailboxes)
    to = frame(doc, 2)
    (line,) = [m for m in drawn(doc) if "fff7d6" in m]
    marks = corners(PATH.match(line).group(1))
    assert len(marks) == mailboxes
    for mark in marks:
        local = [to(x, z) for x, z in mark]
        assert max(a for a, _ in local) <= 0.5 + TOL and min(a for a, _ in local) >= -0.5 - TOL and min(b for _, b in local) >= -0.5 - TOL and max(b for _, b in local) <= 0.2 + TOL  # in the cell, off the wing strip
        assert area(mark) < 0.02
    first_row = [max(to(x, z)[0] for x, z in mark) for mark in marks[:5]]
    assert max(first_row) - min(first_row) < TOL and first_row[0] > 0.4  # the first row stands at the gate, the front of the house
    assert len({tuple(round(v, 3) for point in mark for v in point) for mark in marks}) == mailboxes  # no two on one place


def test_mailboxes_and_wings_of_one_house_do_not_meet():
    doc = city(wings=4, mailboxes=10)
    to = frame(doc, 2)
    lines = drawn(doc)
    marks = [[to(x, z) for x, z in mark] for line in lines if "fff7d6" in line for mark in corners(PATH.match(line).group(1))]
    assert len(marks) == 10 and all(max(b for _, b in mark) <= min(box[2] for box in wings_of(doc, 2)) + TOL for mark in marks)


def test_at_most_thirty_five_mailboxes_are_drawn_and_all_of_them_stay_in_the_cell():
    doc = city(mailboxes=40)
    to = frame(doc, 2)
    (line,) = [m for m in drawn(doc) if "fff7d6" in m]
    marks = corners(PATH.match(line).group(1))
    assert len(marks) == picture.MAILS_PER_ROW * picture.MAIL_ROWS == 35
    assert all(-0.5 - TOL <= a <= 0.5 + TOL and -0.5 - TOL <= b <= 0.5 + TOL for mark in marks for a, b in (to(x, z) for x, z in mark))


# -------------------------------------------------------------------------------- the scale, the houses, the file ----
def test_below_the_readable_scale_annexes_are_not_drawn_and_above_it_they_are():
    doc = city(wings=2, mailboxes=2)
    assert drawn(doc, picture.ANNEX_PIXELS - 0.01) == [] and drawn(doc, 1.0) == []
    assert len(drawn(doc, picture.ANNEX_PIXELS)) == 2 and len(drawn(doc)) == 2  # (no scale given: they are drawn)
    assert drawn(city()) == []  # a city with no annex has nothing to draw


def test_a_picture_of_a_city_shows_the_annexes_at_a_large_scale_and_leaves_them_out_at_a_small_one():
    doc = city(wings=5, mailboxes=3)
    big, small = picture.render(doc, size=2400), picture.render(doc, size=100)
    assert MAILBOXES in big and PLATE in big and MAILBOXES not in small and PLATE not in small
    for text in (big, small):
        ET.fromstring(text)  # valid XML
    assert picture.render(doc, size=2400) == big  # the same document, the same bytes


def test_the_annexes_are_drawn_after_the_roads_which_are_wider_than_their_lanes_and_would_cover_a_gate():
    out: list[str] = []
    picture.draw_city(city(wings=2, mailboxes=2), out.append, picture.Look())
    last_road = max(i for i, line in enumerate(out) if 'stroke-linecap="round"' in line)
    annex = [i for i, line in enumerate(out) if MAILBOXES in line or 'stroke-width="0.03"' in line]
    assert len(annex) == 2 and min(annex) > last_road


def test_the_pixels_of_a_look_say_the_scale_of_the_picture_and_a_sheet_draws_at_its_own_scale():
    assert picture.Look().pixels is None and picture.Look.of_pixels(4.0, 12, 8, 10).pixels == 4.0
    doc = city(wings=6, mailboxes=2)
    frame_, scale, look = picture.fit([doc], 430, (11.0, 0.0, 9.0), 8.0)
    assert scale < picture.ANNEX_PIXELS and look.pixels == scale  # a panel of 430 pixels shows a city of ten houses and its ring road at a scale where annexes merge into their houses
    small = picture.sheet([picture.Panel(doc, ["a"])], panel_px=430)
    big = picture.sheet([picture.Panel(doc, ["a"])], panel_px=3000)
    assert MAILBOXES not in small and PLATE not in small and MAILBOXES in big and PLATE in big
    ET.fromstring(small), ET.fromstring(big)


def test_the_line_of_numbers_says_houses_and_annexes_and_a_city_without_annexes_says_what_it_said():
    doc = city(wings=2, mailboxes=1)
    line = picture.stats_line(inputs.read_city(doc), (0, 0))
    assert line.startswith("7 houses and 3 annexes (") and "on 1 roads" in line
    plain = city()
    assert picture.stats_line(inputs.read_city(plain), (0, 0)).startswith("7 houses (")


def test_a_city_with_annexes_is_read_drawn_and_told_and_a_picture_from_its_text_is_the_picture_of_the_city():
    tree, items = library(5, 2)
    doc = bibliopolis.build_city({"items": items}, tree)
    read = inputs.read_city(json.loads(lay.render(doc)))
    assert picture.render(read, size=2400) == picture.render(doc, size=2400)


# ---------------------------------------------------------------------------- the chronicle, the summary, the command ----
def test_the_chronicle_says_where_each_annex_stands():
    tree, items = library(2, 1)
    doc = bibliopolis.build_city({"items": items}, tree)
    lines = chronicle_lines(doc)
    assert lines == ["house 8, 2024-01-01: a00020 stands beside the house a00002 as a wing.", "house 9, 2024-01-01: a00021 stands beside the house a00002 as a wing.",
                     "house 10, 2024-01-01: a00040 stands beside the house a00002 as a mailbox."]


def test_an_annex_that_waits_for_its_house_is_told_in_the_day_of_the_house():
    tree, items = make_tree({"med": T(3)})
    items += [art(10, [], annex_of="a00012", annex_form="mailbox"), art(11, []), art(12, [])]
    (line,) = chronicle_lines(bibliopolis.build_city({"items": items}, tree))
    assert line == "house 6, 2024-01-01: a00010 stands beside the house a00012 as a mailbox."  # (the arrival of its house is the sixth)


def test_the_summary_counts_annexes_only_when_there_are_some():
    assert "annexes" not in summary(city()) and summary(city(wings=2, mailboxes=1))["annexes"] == 3 and summary(city(wings=2, mailboxes=1))["houses"] == 7


@pytest.mark.parametrize("annexes, said", [(0, "wrote {out}: 7 houses on 1 roads, 7 on the ring road, 0 splits, 0 over (mode grow)"),
                                           (3, "wrote {out}: 7 houses and 3 annexes on 1 roads, 7 on the ring road, 0 splits, 0 over (mode grow)")])
def test_the_command_says_how_many_annexes_and_a_library_with_none_is_told_as_it_was(tmp_path, annexes, said):
    tree, items = library(wings=annexes, house=2)
    (tmp_path / "library.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (tmp_path / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    out = tmp_path / "city.json"
    made = subprocess.run([sys.executable, "-m", "bibliopolis", "build", "--library", str(tmp_path / "library.json"), "--tree", str(tmp_path / "tree.json"), "--out", str(out)],
                          cwd=ROOT, capture_output=True, text=True)
    assert made.returncode == 0 and made.stderr.strip() == said.format(out=out)
    for command, extra in (("picture", ["--out", str(tmp_path / "city.svg")]), ("chronicle", [])):
        shown = subprocess.run([sys.executable, "-m", "bibliopolis", command, "--city", str(out), *extra], cwd=ROOT, capture_output=True, text=True)
        assert shown.returncode == 0, shown.stderr
        if command == "chronicle" and annexes:
            assert shown.stdout.count("stands beside the house a00002 as a wing.") == annexes
