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
from bibliopolis import canonical
from bibliopolis import layout as lay

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# (value, text): the texts are what JavaScript's JSON.stringify writes for the same numbers
TABLE = [(0, "0"), (-0.0, "0"), (1, "1"), (-1, "-1"), (40, "40"), (6.0, "6"), (1.5, "1.5"), (-2.5, "-2.5"), (0.1, "0.1"), (0.001, "0.001"), (-0.001, "-0.001"),
         (12.345, "12.345"), (137.51, "137.51"), (-104.98, "-104.98"), (0.25, "0.25"), (100.0, "100"), (12345678.125, "12345678.125"),
         (999999999999999.0, "999999999999999"), (0.0001, "0.0001"), (50.4, "50.4"), (3.14159, "3.14159"), (123456789.001, "123456789.001"), (600, "600"),
         (2026, "2026"), (-189.97, "-189.97"), (0.30000000000000004, "0.30000000000000004")]

# the sha256 of the text of the city that the sample makes (examples/tree.json + library.json); change them on purpose, with the engine
PINS = {"grow": "7709df8ca630267167758a083321d13720cd9c981f7e06343da666c35e24260d",
        "mirror": "dccf46c97cc888a9629b9d20a80d2d88d6bc1a6cf76a2650d6b15eab2e732424",
        "grow, first 41": "66786136f586a2cb0643f61367fd60666de808aa819f09cb996a679fa969634f"}


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
