"""The one number form of every document the package writes (bibliopolis.canonical): an integral value has no fraction, any other value is its shortest
text; the layout of the text is that of `json.dumps`. The sample's city documents are pinned by their sha256, so a change of the engine, the form or the
text shows as a changed hash that a reviewer reads (and a port in another language has the bytes to match)."""

import hashlib
import json
import random
import re
from pathlib import Path

import pytest

import bibliopolis
from bibliopolis import canonical, inputs, picture
from bibliopolis import layout as lay

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# (value, text): the texts are what JavaScript's JSON.stringify writes for the same numbers
TABLE = [(0, "0"), (-0.0, "0"), (1, "1"), (-1, "-1"), (40, "40"), (6.0, "6"), (1.5, "1.5"), (-2.5, "-2.5"), (0.1, "0.1"), (0.001, "0.001"), (-0.001, "-0.001"),
         (12.345, "12.345"), (137.51, "137.51"), (-104.98, "-104.98"), (0.25, "0.25"), (100.0, "100"), (12345678.125, "12345678.125"),
         (999999999999999.0, "999999999999999"), (0.0001, "0.0001"), (50.4, "50.4"), (3.14159, "3.14159"), (123456789.001, "123456789.001"), (600, "600"),
         (2026, "2026"), (-189.97, "-189.97"), (0.30000000000000004, "0.30000000000000004")]

# the sha256 of the text of the city that the sample makes (examples/tree.json + library.json); change them on purpose, with the engine
PINS = {"grow": "8e3d6772298d46693a6cde120b5a12f298789fa7c43c4d15bef121ee71b4fcd9",
        "mirror": "7de26c35417f179a0079c66b54848cd77c3be035e44346c2a7d8c5b3e6b0613b",
        "grow, first 41": "d4fc5d402bd3a1b33b9250d406076981370e64473785977facf97eb2da834215"}


@pytest.fixture(scope="module")
def sample():
    return json.loads((EXAMPLES / "tree.json").read_text(encoding="utf-8")), json.loads((EXAMPLES / "library.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("value, text", TABLE)
def test_a_number_is_written_as_javascript_writes_it(value, text):
    assert canonical.number(value) == text
    assert json.loads(text) == value  # ... and reads back as the same value


def test_an_integral_float_loses_its_fraction_and_minus_zero_is_zero():
    assert canonical.number(40.0) == "40" and canonical.number(-0.0) == "0" and canonical.number(6.0) == canonical.number(6)
    assert canonical.dumps({"radius": 6.0, "x": -0.0, "y": 1.5}) == '{"radius":6,"x":0,"y":1.5}'


@pytest.mark.parametrize("value", [1e-05, 1.5e-07, 1e15, -1e15, 1e21, 123456789012345680000.0, 10**15, float("nan"), float("inf"), -float("inf")])
def test_a_number_that_another_language_would_spell_differently_is_refused(value):
    with pytest.raises(ValueError):
        canonical.number(value)


@pytest.mark.parametrize("value", [True, False, "1", None, [1]])
def test_only_numbers_are_numbers(value):
    with pytest.raises(TypeError):
        canonical.number(value)


def random_value(rng, depth=0):
    kind = rng.randrange(8 if depth < 3 else 5)
    if kind == 0:
        return rng.choice([None, True, False])
    if kind == 1:
        return rng.randrange(-10**6, 10**6)
    if kind == 2:
        return rng.choice(["", "a", "市政廳", 'quote " and \\ slash', "tab\tnew\nline", "\x01\x1f", "ünï", "  sep"])
    if kind == 3:
        return round(rng.uniform(-500, 500), rng.choice([1, 2, 3]))
    if kind == 4:
        return rng.choice([[], {}])
    if kind in (5, 6):
        return [random_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {f"k{rng.randrange(20)}-{rng.choice(['a', 'é', 'z'])}": random_value(rng, depth + 1) for _ in range(rng.randrange(4))}


def integral_as_int(x):
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, dict):
        return {k: integral_as_int(v) for k, v in x.items()}
    if isinstance(x, list):
        return [integral_as_int(v) for v in x]
    return x


@pytest.mark.parametrize("indent", [None, 1, 2])
def test_the_layout_of_the_text_is_that_of_json_dumps(indent):
    rng = random.Random(5)
    for _ in range(400):
        value = integral_as_int(random_value(rng))  # (a float with a fraction is written by `repr`, as json.dumps does; an integral one is the case that differs)
        want = json.dumps(value, ensure_ascii=False, indent=indent, separators=(",", ":") if indent is None else None)
        assert canonical.dumps(value, indent=indent) == want


def test_a_key_of_an_object_is_a_string_and_a_value_is_json():
    with pytest.raises(TypeError):
        canonical.dumps({1: 2})
    with pytest.raises(TypeError):
        canonical.dumps({"a": {1, 2}})
    assert canonical.dumps((1, 2.0)) == "[1,2]" and canonical.dumps({}, indent=1) == "{}" and canonical.dumps([], indent=1) == "[]"


# ---------------------------------------------------------------------------------- the documents of the package ----
def old_render(layout):
    """The writer of the package before the one number form: json.dumps all the way (the reference for the layout of the text)."""
    head = {k: v for k, v in layout.items() if k not in ("roads", "coast", "places")}
    head_text = json.dumps(head, ensure_ascii=False, indent=1)[:-2]

    def lines(d):
        return ",\n".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, separators=(',', ':'))}" for k, v in d.items())

    parts = [head_text, ',\n "roads": {\n' + lines(layout["roads"]) + "\n }"]
    if "coast" in layout:
        c = layout["coast"]
        polys = ",\n".join("   " + json.dumps(p, separators=(",", ":")) for p in c["polygons"])
        parts.append(',\n "coast": {' + ",".join(f"{json.dumps(k)}:{json.dumps(v)}" for k, v in c.items() if k != "polygons")
                     + ',"polygons":[\n' + polys + "\n  ]}")
    parts.append(',\n "places": {\n' + lines(layout["places"]) + "\n }\n}\n")
    return "".join(parts)


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_render_is_the_old_text_with_the_integral_numbers_written_without_a_fraction(sample, mode):
    tree, library = sample
    doc = bibliopolis.build_city(library, tree, mode=mode)
    text = lay.render(doc)
    assert text == old_render(integral_as_int(doc))
    assert text != old_render(doc)  # (the sample has integral floats: radius 6.0 is the first)
    assert json.loads(text) == json.loads(old_render(doc))  # ... the same document for a reader


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_every_number_the_city_document_holds_is_in_the_canonical_form(sample, mode):
    tree, library = sample
    seen = []

    def check(token):
        seen.append(token)
        assert "e" not in token.lower() and not re.search(r"\.0$|^-?0\d", token) and abs(float(token)) < canonical.LIMIT, token
        return float(token)

    json.loads(lay.render(bibliopolis.build_city(library, tree, mode=mode)), parse_float=check, parse_int=check)
    assert len(seen) > 3_000 and any("." in t for t in seen) and any("." not in t for t in seen)


def test_the_sample_documents_are_pinned_by_their_sha256(sample):
    tree, library = sample
    made = {"grow": lay.render(bibliopolis.build_city(library, tree, mode="grow")),
            "mirror": lay.render(bibliopolis.build_city(library, tree, mode="mirror")),
            "grow, first 41": lay.render(bibliopolis.build_city(library, tree, mode="grow", first=41))}
    assert {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in made.items()} == PINS


# ------------------------------------------------------------------------- a picture from a file ----
def city_from_text(city):
    return inputs.read_city(json.loads(lay.render(city)))


@pytest.mark.parametrize("mode", ["grow", "mirror"])
def test_a_picture_drawn_from_the_text_of_a_city_is_the_picture_of_the_city(sample, mode):
    """The text of a city has `55` where the city has `55.0`; the picture must not show the difference (the caption prints a measure as the float it is)."""
    tree, library = sample
    city = bibliopolis.build_city(library, tree, mode=mode)
    assert picture.render(city_from_text(city)) == picture.render(city)


def a_replay_with_a_whole_measure(sample):
    """The first replay of the grown sample (from 41 houses on) whose picture line has a measure that is a whole number, as (the city, the key of the measure). The grown
    sample itself has none since the ribs grow in place: its farthest house, its mean walk and its longest walk all have a fraction."""
    tree, library = sample
    for n in range(41, 400):
        measure = bibliopolis.build_city(library, tree, first=n, with_coast=False)["composition"]["measure"]
        whole = [k for k in ("max_radius", "walk_mean", "walk_longest") if float(measure[k]).is_integer()]
        if whole:
            return bibliopolis.build_city(library, tree, first=n), whole[0]
    raise AssertionError("no replay of the sample has a whole measure in its picture line")


def test_a_picture_drawn_from_the_text_of_a_replay_with_a_whole_measure_is_the_picture_of_the_city(sample):
    city, _key = a_replay_with_a_whole_measure(sample)
    assert picture.render(city_from_text(city)) == picture.render(city)


def test_a_replay_of_the_grown_sample_has_a_measure_that_is_a_whole_number_so_that_the_check_above_means_something(sample):
    city, key = a_replay_with_a_whole_measure(sample)
    value = city["composition"]["measure"][key]
    assert isinstance(value, float) and value == int(value) and f"{value}" in picture.stats_line(city, (0, 0)) and f"{value}" in picture.render(city)
    text = lay.render(city)
    assert f'"{key}": {int(value)},' in text and f'"{key}": {value},' not in text  # (the text of the city has 34, where the city has 34.0)


def test_a_picture_drawn_from_the_text_of_a_hand_built_city_is_the_picture_of_the_city():
    from hand_support import play

    city = play(3, steps=120).state.city()
    assert picture.render(city_from_text(city)) == picture.render(city)


def test_the_line_of_numbers_of_a_picture_is_the_same_for_a_measure_that_is_a_whole_number_or_a_float():
    city = {"composition": {"buildings": 3, "streets": {"total": 1}, "measure": {"ring_lots": 0, "max_radius": 8, "walk_mean": 4.5, "walk_longest": 55}}}
    other = json.loads(json.dumps(city))
    other["composition"]["measure"].update(max_radius=8.0, walk_longest=55.0)
    want = "3 houses (0 on the ring road) on 1 roads; the farthest house is 8.0 cells from the centre, the mean walk 4.5, the longest 55.0"
    assert picture.stats_line(city, (0, 0)) == picture.stats_line(other, (0, 0)) == want
