"""A city file of a world built by hand is read by the same reader as any city file: no single wrong field in an entry of its chronicle gets past the reader to crash the
chronicle or the picture (the one-field break-in of tests/test_cityfile.py, on every kind of entry that a world built by hand writes)."""

import collections
import copy
import json

import pytest
from hand_support import every_entry
from test_cityfile import WRONG, at, fuzz

from bibliopolis import city, inputs, picture
from bibliopolis import layout as lay

KINDS = ("from", "filed", "renamed", "moved", "merged", "undone", "resized", "rule")  # the entries of a world built by hand: a road opened, and the six that only it writes


def base_city():
    """The city of a world with an entry of every kind, as it is read from its file."""
    return json.loads(lay.render(every_entry().state.city()))


def kind_of(entry):
    return next(k for k in KINDS if k in entry)


def break_in(base, reader):
    """Break each entry of the chronicle one field at a time (take a key away, or put each of WRONG there) and return what `reader` let through that then crashed the chronicle
    or the picture, with how many documents it refused and how many it took."""
    failures, tally = [], collections.Counter()
    for index, entry in enumerate(base["world"]["chronicle"]):
        paths = [["world", "chronicle", index]] + [["world", "chronicle", index, key] for key, value in entry.items() if isinstance(value, list) and value]
        for path in paths:
            node = at(base, path)
            for key in (list(node) if isinstance(node, dict) else range(len(node))):
                for wrong in ("take away", *WRONG):
                    doc = copy.deepcopy(base)
                    holder = at(doc, path)
                    if wrong == "take away":
                        holder.pop(key) if isinstance(holder, dict) else holder.pop()
                    else:
                        holder[key] = copy.deepcopy(wrong)
                    try:
                        reader(doc)
                    except inputs.InputError:
                        tally["refused"] += 1
                        continue
                    tally["accepted"] += 1
                    try:
                        city.chronicle_lines(doc)
                        picture.render(doc)
                    except Exception as exc:  # noqa: BLE001 - any exception at all is the finding
                        failures.append((kind_of(entry), path[3:], key, wrong, f"{type(exc).__name__}: {str(exc)[:60]}"))
    return failures, tally


def test_the_city_of_a_world_with_every_kind_of_entry_is_read_drawn_and_told():
    base = base_city()
    assert {kind_of(e) for e in base["world"]["chronicle"]} == set(KINDS)
    read = inputs.read_city(copy.deepcopy(base))
    assert len(city.chronicle_lines(read)) == len(base["world"]["chronicle"]) and picture.render(read).startswith("<svg")


def test_no_single_wrong_field_of_a_hand_built_city_gets_past_the_reader_to_crash_the_chronicle_or_the_picture():
    """The break-in of tests/test_cityfile.py as it is, on the city of a world built by hand: its places, roads, sectors and the rest, one field at a time."""
    failures, tally = fuzz(base_city(), inputs.read_city)
    assert failures == [], failures[:5]
    assert tally["refused"] > 1_000 and tally["accepted"] > 1_000


def test_no_single_wrong_field_of_a_chronicle_entry_gets_past_the_reader_to_crash_the_chronicle_or_the_picture():
    failures, tally = break_in(base_city(), inputs.read_city)
    assert failures == [], failures[:5]
    assert tally["refused"] > 300 and tally["accepted"] > 100  # (entries that are broken and refused, and keys that nothing reads)


def test_the_control_a_reader_that_lets_everything_through_is_caught_by_the_same_break_in():
    failures, tally = break_in(base_city(), lambda doc: doc)
    assert tally["refused"] == 0 and failures
    assert {"KeyError", "TypeError"} <= {f[4].split(":")[0] for f in failures}  # crashes ...
    assert {f[0] for f in failures} >= {"filed", "renamed", "moved", "merged", "undone", "resized", "rule"}  # ... in the entries that only a world built by hand writes, merges included


def test_a_merge_entry_with_a_wrong_field_is_refused_with_its_place_and_what_it_should_be():
    base = base_city()
    i = next(i for i, e in enumerate(base["world"]["chronicle"]) if kind_of(e) == "merged")
    for key, wrong, should in (("members", "x", "the list of the places that were merged"), ("members", [1, 2], "the list of the places that were merged"),
                               ("took", 5, "the place whose direction or place the new road took"), ("houses", None, "the list of the houses that were put again"),
                               ("below", 7, "the place the new road stands below"), ("label", 3, "the name of the new road"), ("merged", None, "a place id")):
        doc = copy.deepcopy(base)
        doc["world"]["chronicle"][i][key] = wrong
        with pytest.raises(inputs.InputError, match=rf"chronicle\[{i}\]\.{key}: must be {should}"):
            inputs.read_city(doc)
