"""The picture (bibliopolis.picture): what is drawn, what is left out, and that the same city gives the same bytes."""

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import bibliopolis
from bibliopolis import picture

ROOT = Path(__file__).resolve().parents[1]
SVG = "{http://www.w3.org/2000/svg}"
TEXT = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="([\d.]+)"[^>]*>([^<]*)</text>')


@pytest.fixture(scope="module")
def sample():
    return (json.loads((ROOT / "examples" / "tree.json").read_text(encoding="utf-8")),
            json.loads((ROOT / "examples" / "library.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def cities(sample):
    """The sample at the moments the README shows, and as a mirror."""
    tree, library = sample
    return {**{n: bibliopolis.build_city(library, tree, first=n) for n in (0, 40, 41, 150, 600)},
            "mirror": bibliopolis.build_city(library, tree, mode="mirror")}


def drawn(city, look=None, highlight=None):
    """Every element `draw_city` adds for `city`, as text."""
    out: list[str] = []
    picture.draw_city(city, out.append, look or picture.Look(), highlight)
    return out


def names(city, look=None):
    """(text, x, z, size) of every name `draw_labels` puts down."""
    out: list[str] = []
    picture.draw_labels(city, out.append, look or picture.Look())
    return [(m.group(4), float(m.group(1)), float(m.group(2)), float(m.group(3))) for line in out for m in [TEXT.search(line)] if m]


def sector_names(city):
    return {r["label"] for r in city["composition"]["ring1"]}


# ------------------------------------------------------------------------------------------- small helpers ----
def test_esc_leaves_nothing_that_xml_cannot_carry():
    assert picture.esc('a\x01b\ud800 & <c> "d"') == "a�b� &amp; &lt;c&gt; &quot;d&quot;"
    assert picture.esc("市政廳\tok\n") == "市政廳\tok\n"  # tab and line feed are fine


def test_num_rounds_and_has_no_negative_zero():
    assert [picture.num(v) for v in (-0.001, 1.5, 2.0, 3.14159, 100.0)] == ["0", "1.5", "2", "3.14", "100"]
    assert picture.num(3.14159, 3) == "3.142" and picture.num(-0.04, 1) == "0"


def test_a_wide_glyph_is_one_em_and_any_other_a_bit_more_than_half():
    assert picture.text_width("市政廳", 10) == 30
    assert picture.text_width("abc", 10) == pytest.approx(16.8)
    assert picture.text_width("Humanities・History", 10) == pytest.approx(10 + 17 * 5.6)  # the middle dot is a wide glyph


def test_a_road_is_never_drawn_thicker_than_it_is_at_3_and_a_half_pixels_to_the_cell():
    assert picture.Look.of_pixels(3.0, 11, 0, 10).line == 1.0
    assert picture.Look.of_pixels(10.0, 11, 0, 10).line == pytest.approx(0.35)
    look = picture.Look.of_pixels(4.0, 12, 8, 10)
    assert (look.big, look.small, look.plaza) == (3.0, 2.0, 2.5) and look.digits == 1 and picture.Look().digits == 2


# ---------------------------------------------------------------------------------------------- what is drawn ----
def test_a_city_of_forty_houses_is_the_town_hall_and_the_ring_road_with_its_forty_houses_and_nothing_else(cities):
    city = cities[40]
    lines = "\n".join(drawn(city))
    assert [t for t, *_ in names(city)] == ["市政廳", "Knowledge"]  # the plaza, and the ring road at its north point
    assert "hsl(" not in lines  # no house in the colour of a district of ring 1: the ring is no sector
    assert picture.RING_COLOR[0] in lines and lines.count(picture.RING_COLOR[0]) == 1 and lines.count("M") > 40  # one path of forty cells, in the colour of the ring
    assert picture.CLASS_COLOR["大道"] in lines and not any(color in lines for name, color in picture.CLASS_COLOR.items() if name != "大道")  # no road but the ring road
    assert lines.count("<circle") == 1 and "<path" in lines  # the plaza, and the coast round it


def test_the_first_road_names_its_own_sector_and_no_other(cities):
    city = cities[41]
    shown = {t for t, *_ in names(city)}
    assert shown == {"市政廳", "Knowledge", "Computing"}
    assert sector_names(city) > shown & sector_names(city)  # the plan has more sectors: they have no road yet


def test_every_sector_with_a_road_is_named_once(cities):
    for key in (150, 600, "mirror"):
        city = cities[key]
        sectors = [r["label"] for r in city["composition"]["ring1"] if r["place"] in city["places"]]
        assert sorted(t for t, *_ in names(city) if t in sector_names(city)) == sorted(sectors), key
    assert len(sector_names(cities[600])) == 6


def test_the_houses_of_a_step_are_drawn_on_top_in_the_accent_colour_and_only_those(cities):
    city = cities[41]
    moved = set(city["world"]["chronicle"][0]["houses"])
    assert len(moved) == 15
    plain = "\n".join(drawn(city))
    marked = [line for line in drawn(city, highlight=moved) if picture.HIGHLIGHT[0] in line]
    assert picture.HIGHLIGHT[0] not in plain
    assert len(marked) == 1 and marked[0].count("M") == 15  # one path of 15 cells
    # the other houses of the road keep their district colour (the road holds exactly the 15)
    assert "hsl(" not in "\n".join(line for line in drawn(city, highlight=moved) if "hsl(" in line and picture.HIGHLIGHT[0] in line)


def test_a_name_of_a_sector_stands_clear_of_the_houses_of_that_sector(cities):
    for key in (41, 150, 600, "mirror"):
        city = cities[key]
        places = city["places"]
        housed: dict[str, list[tuple[float, float]]] = {}
        for p in places.values():
            if p["kind"] == "lot":
                housed.setdefault(picture.ring1_place(places, p["parent"]), []).append((p["position"]["x"], p["position"]["z"]))
        for sector in city["composition"]["ring1"]:
            if sector["place"] not in places:
                continue
            (text, x, z, size), = [n for n in names(city) if n[0] == sector["label"]]
            x0, z0, x1, z1 = picture.text_box(x, z, text, size)
            inside = [h for h in housed.get(sector["place"], []) if x0 < h[0] < x1 and z0 < h[1] < z1]
            assert not inside, (key, text, inside[:3])


def test_a_sector_name_that_would_sit_on_another_name_stands_farther_out_with_a_line_to_the_land():
    sector = {"place": "place:a", "label": "Alpha", "from": -90.0, "to": 90.0}
    sector2 = {"place": "place:b", "label": "Alpha", "from": -90.0, "to": 90.0}  # the same direction and the same name: they would be one on the other
    city = {"places": {"place:plaza": {"kind": "plaza", "label": "市政廳", "radius": 6.0, "position": {"x": 0, "z": 0}},
                       "place:a": {"kind": "street", "s_end": 20.0}, "place:b": {"kind": "street", "s_end": 20.0}},
            "roads": {}, "composition": {"ring1": [sector, sector2]}}
    out: list[str] = []
    picture.draw_labels(city, out.append, picture.Look())
    lines = [line for line in out if line.startswith("<line")]
    assert len(lines) == 1  # only the second name was pushed out
    zs = [float(m.group(2)) for line in out for m in [TEXT.search(line)] if m and m.group(4) == "Alpha"]  # both point north: they differ in z
    assert len(zs) == 2 and zs[1] < zs[0] < 0  # north is up: the second stands farther from the centre


def test_the_town_hall_label_and_the_name_of_the_ring_follow_the_plaza_and_the_ring_not_the_look(cities):
    for look in (picture.Look(), picture.Look.of_pixels(3.2, 11, 0, 11)):
        by_text = {t: (x, z, size) for t, x, z, size in names(cities[150], look)}
        assert by_text["市政廳"][0] == 0 and by_text["Knowledge"][0] == 0
        assert by_text["Knowledge"][1] < -cities[150]["places"]["place:root"]["ring"]["radius"]  # north of the ring (north is up), outside its outer row


# ---------------------------------------------------------------------------------------------- render ----
@pytest.mark.parametrize("key", [0, 40, 41, 150, 600, "mirror"])
def test_render_is_valid_xml_the_same_bytes_every_time(cities, key):
    city = cities[key]
    text = picture.render(city)
    root = ET.fromstring(text)
    assert root.tag == f"{SVG}svg" and text.endswith("</svg>\n") and "\r" not in text
    assert picture.render(copy.deepcopy(city)) == text


def test_render_has_a_title_a_line_of_numbers_and_a_legend(cities):
    text = picture.render(cities[600])
    assert picture.TITLE in text
    assert "600 houses (15 on the ring road) on 23 roads" in text
    for word in ("大道 avenue", "路 road", "巷 lane", "弄 alley", "50 cells 格"):
        assert word in text
    assert "My <city> & more" not in picture.render(cities[40], title="My <city> & more")
    assert "My &lt;city&gt; &amp; more" in picture.render(cities[40], title="My <city> & more")


def test_a_control_character_in_a_title_or_a_name_cannot_make_the_file_invalid(cities):
    city = copy.deepcopy(cities[150])
    city["composition"]["ring1"][0]["label"] = "Bad\x01Name"
    ET.fromstring(picture.render(city, title="T\x0b"))


def test_size_is_the_longest_side_of_the_map(cities):
    for size in (900, 1800):
        root = ET.fromstring(picture.render(cities[600], size=size))
        width, height = float(root.get("width")), float(root.get("height"))
        assert width == pytest.approx(size, abs=1) or height - 96 == pytest.approx(size, abs=1)


def test_a_city_without_a_coast_is_still_drawn(cities):
    city = {k: v for k, v in cities[150].items() if k != "coast"}
    ET.fromstring(picture.render(city))
    assert picture.extent(city) != picture.extent(cities[150])  # the frame follows the roads and the houses instead


# ---------------------------------------------------------------------------------------------- sheet ----
def sheet_of(cities, keys, **kw):
    return picture.sheet([picture.Panel(cities[k], [f"after {k}"]) for k in keys], **kw)


def test_a_sheet_puts_every_city_on_one_frame_at_one_scale(cities):
    root = ET.fromstring(sheet_of(cities, [40, 150, 600]))
    panels = root.findall(f"{SVG}svg")
    assert len(panels) == 3
    assert len({(p.get("viewBox"), p.get("width"), p.get("height")) for p in panels}) == 1
    assert len({p.get("x") for p in panels}) == 2 and len({p.get("y") for p in panels}) == 2  # two columns, two rows (the third panel starts the second row)


def test_a_sheet_makes_room_for_every_name(cities):
    keys = [40, 41, 150, 600]
    frame, scale, look = picture.fit([cities[k] for k in keys], 430, (11.0, 0.0, 11.0), 8.0)
    x0, x1, z0, z1 = frame
    for k in keys:
        for text, x, z, size in names(cities[k], look):
            bx0, bz0, bx1, bz1 = picture.text_box(x, z, text, size)
            assert x0 <= bx0 and bx1 <= x1 and z0 <= bz0 and bz1 <= z1, (k, text)
    assert scale == pytest.approx(430 / max(x1 - x0, z1 - z0))


def test_a_sheet_says_its_captions_and_title_and_is_the_same_bytes_twice(cities):
    panels = [picture.Panel(cities[41], ["one", "two", "three", "four is dropped"], {"item-0001"}), picture.Panel(cities[600], ["x & y"])]
    text = picture.sheet(panels, title="Both <ways>")
    root = ET.fromstring(text)
    shown = [t.text for t in root.iter(f"{SVG}text")]
    assert "Both <ways>" in shown and "x & y" in shown and {"one", "two", "three"} <= set(shown) and "four is dropped" not in shown
    assert picture.sheet(panels, title="Both <ways>") == text


def test_a_sheet_of_one_city_and_of_an_odd_number_is_laid_out(cities):
    for keys, columns in (([600], 2), ([40, 41, 150], 2), ([40, 41, 150], 3), ([41, 150], 1)):
        root = ET.fromstring(sheet_of(cities, keys, columns=columns))
        assert len(root.findall(f"{SVG}svg")) == len(keys)
        assert float(root.get("width")) > 0 and float(root.get("height")) > 0


def test_a_picture_is_small_enough_to_sit_in_a_readme(cities):
    assert len(picture.render(cities[600]).encode("utf-8")) < 100_000
    assert len(sheet_of(cities, [600, "mirror"], panel_px=500).encode("utf-8")) < 100_000


def test_a_circle_of_parents_is_an_error_and_not_a_loop():
    for parents in ({"a": "a"}, {"a": "b", "b": "a"}, {"a": "b", "b": "c", "c": "a"}):
        places = {"place:plaza": {"kind": "plaza"}, **{pid: {"kind": "street", "parent": parent} for pid, parent in parents.items()}}
        with pytest.raises(ValueError, match="round in a circle"):
            picture.ring1_place(places, "a")
        with pytest.raises(ValueError, match="round in a circle"):
            picture.ring2_of(places, "a")
    places = {"place:plaza": {"kind": "plaza"}, "a": {"kind": "street", "parent": "place:plaza", "level": 2}}  # the ways out stay what they were
    assert picture.ring1_place(places, "a") == "a" and picture.ring2_of(places, "a") == "a" and picture.ring2_of(places, None) is None
