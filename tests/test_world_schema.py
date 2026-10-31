"""schema/world.schema.json says the shape of a world file. The program is held to it (what the program writes satisfies it), and it is held to the program (it names the same keys,
kinds and limits, and it never refuses a file that the program takes). The examples of docs/world.md satisfy it. What a schema cannot say is checked by the program, and is listed
here with the file that shows it."""

import copy
import functools
import json
import random
from pathlib import Path

import pytest
from hand_support import Hand, every_entry, hid, play, scripted, scripted_merge, scripted_nodes, topic
from refusal_cases import small_journal
from schema_support import faults, valid

from bibliopolis import events as ev
from bibliopolis import inputs
from bibliopolis.journal import FILE_KEYS, FORMAT, VERSION, Journal, WorldFileError, dumps_world, read_world, world_document

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "world.schema.json").read_text(encoding="utf-8"))
DEFS = SCHEMA["$defs"]
PAGE = (ROOT / "docs" / "world.md").read_text(encoding="utf-8")


def file_of(journal) -> dict:
    """The world file of a journal as the document a reader gets from the JSON text."""
    return json.loads(dumps_world(world_document(journal)))


def taken_world():
    """Twenty-four houses of one domain, twelve of them on a road that stands for it."""
    h = Hand()
    h.add(24, topic(1, 1, 1, 1))
    h.open("a", "Domain 1", None, [hid(i) for i in range(1, 13)], {"id": "ex:d1", "level": "domain", "name": "Domain 1"})
    return h.journal


@functools.lru_cache(maxsize=None)
def worlds():
    """Worlds that between them use every kind of event (the event `annex` and items that exist for another item in `entries`), the node of a road, the rule auto, undo, topics, and
    nothing at all. (Built once; a file is made from each as needed.)"""
    return {"empty": Journal(), "small": small_journal(), "scripted": scripted().journal, "nodes": scripted_nodes().journal, "merge": scripted_merge().journal,
            "taken": taken_world(), "random": play(3, steps=80, auto=True, suggested=True, arrivals=0.8, merging=True), "entries": every_entry().journal}


def accepted(doc) -> bool:
    try:
        read_world(copy.deepcopy(doc))
    except WorldFileError:
        return False
    return True


# ------------------------------------------------------------------------------------ the schema and the program ----
def test_the_schema_is_a_json_schema_document_and_the_page_and_the_card_name_it():
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema" and SCHEMA["type"] == "object" and SCHEMA["additionalProperties"] is False
    assert "schema/world.schema.json" in PAGE
    assert "schema/world.schema.json" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_the_schema_names_the_keys_the_kinds_and_the_limits_of_the_program():
    assert tuple(SCHEMA["required"]) == FILE_KEYS and set(SCHEMA["properties"]) == set(FILE_KEYS)
    assert SCHEMA["properties"]["format"]["const"] == FORMAT and SCHEMA["properties"]["version"]["const"] == VERSION
    assert tuple(DEFS["rule"]["required"]) == ev.RULE_KEYS and set(DEFS["rule"]["properties"]) == set(ev.RULE_KEYS)
    assert tuple(DEFS["start_rule"]["required"]) == tuple(k for k in ev.RULE_KEYS if k not in ev.START_OPTIONAL) and set(DEFS["start_rule"]["properties"]) == set(ev.RULE_KEYS)
    assert (DEFS["rule"]["properties"]["branches"]["minimum"], DEFS["rule"]["properties"]["branches"]["maximum"]) == (ev.BRANCHES_LEAST, ev.BRANCHES_LIMIT)
    assert (DEFS["limit"]["minimum"], DEFS["limit"]["maximum"]) == (1, ev.RULE_LIMIT) and DEFS["count"]["maximum"] == inputs.COUNT
    item = DEFS["item"]
    assert tuple(item["required"]) == ev.ITEM_REQUIRED and set(item["properties"]) == set(ev.ITEM_KEYS)
    assert (item["properties"]["year"]["minimum"], item["properties"]["year"]["maximum"]) == (-ev.YEAR_LIMIT, ev.YEAR_LIMIT)
    assert item["properties"]["openalex"]["maxItems"] == ev.MAX_TOPICS
    assert tuple(DEFS["openalex_topic"]["required"]) == ev.ORDER and set(DEFS["openalex_topic"]["properties"]) == set(ev.ORDER)
    assert tuple(DEFS["road_node"]["required"]) == ev.NODE_KEYS and tuple(DEFS["road_node"]["properties"]["level"]["enum"]) == ev.ORDER
    assert [ref["$ref"].rsplit("/", 1)[1] for ref in DEFS["event"]["oneOf"]] == list(ev.KINDS)
    for kind in ev.KINDS:
        event = DEFS[kind]
        assert tuple(event["required"]) == ("seq", "at", "kind", "payload") and set(event["properties"]) == {"seq", "at", "kind", "payload"}, kind
        assert event["properties"]["kind"]["const"] == kind
        payload = event["properties"]["payload"]
        if kind == "set_rule":
            assert payload == {"$ref": "#/$defs/rule"}
            continue
        optional = ev.OPTIONAL_KEYS.get(kind, ())
        assert set(payload["properties"]) == set(ev.PAYLOAD_KEYS[kind]) and set(payload["required"]) == set(ev.PAYLOAD_KEYS[kind]) - set(optional), kind
        assert payload["additionalProperties"] is False


def test_the_schema_is_a_valid_schema_that_jsonschema_accepts_where_it_is_installed():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


# -------------------------------------------------------------------------------------- what the program writes ----
@pytest.mark.parametrize("name", list(worlds()))
def test_the_world_file_the_program_writes_satisfies_the_schema(name):
    doc = file_of(worlds()[name])
    assert faults(doc, SCHEMA) == []
    assert accepted(doc)


def test_the_files_cover_every_kind_of_event_and_a_road_for_a_node_and_one_with_none():
    kinds, nodes = set(), []
    for journal in worlds().values():
        kinds |= {e["kind"] for e in journal.events}
        nodes += [e["payload"]["topic"] for e in journal.events if e["kind"] == "open_road"]
    assert kinds == set(ev.KINDS) and None in nodes and any(n is not None for n in nodes)


def test_the_examples_of_the_page_satisfy_the_schema():
    import re

    values = []
    for block in re.findall(r"^```json\n(.*?)^```", PAGE, flags=re.S | re.M):
        decoder, i = json.JSONDecoder(), 0
        while i < len(block):
            if block[i].isspace():
                i += 1
                continue
            value, i = decoder.raw_decode(block, i)
            values.append(value)
    assert len(values) >= 3
    for value in values:
        which = "event" if "kind" in value else "item"
        assert faults(value, DEFS[which], SCHEMA) == [], value
    assert {"event", "item"} == {"event" if "kind" in v else "item" for v in values}


# ----------------------------------------------------------------------------------------- a wrong file is wrong ----
def mutated(world, change):
    doc = file_of(worlds()[world])
    change(doc)
    return doc


WRONG = [
    ("a key left out", "nodes", lambda d: d.pop("rule"), "missing rule"),
    ("a key too many", "nodes", lambda d: d.update(extra=1), "unknown extra"),
    ("another format", "nodes", lambda d: d.update(format="x"), "not 'bibliopolis.world'"),
    ("another version", "nodes", lambda d: d.update(version=2), "not 1"),
    ("a rule with min 0", "nodes", lambda d: d["rule"].update(min=0), "less than 1"),
    ("a rule with a text for auto", "nodes", lambda d: d["rule"].update(auto="yes"), "not of type"),
    ("a rule with a key too many", "nodes", lambda d: d["rule"].update(x=1), "unknown x"),
    ("an item with a key too many", "nodes", lambda d: d["items"][0].update(colour="red"), "unknown colour"),
    ("an item with no title", "nodes", lambda d: d["items"][0].pop("title"), "missing title"),
    ("an item with a year as text", "nodes", lambda d: d["items"][0].update(year="2020"), "not of type"),
    ("an item with a year out of range", "nodes", lambda d: d["items"][0].update(year=10**7), "more than"),
    ("an item with four topics", "nodes", lambda d: d["items"][0].update(openalex=[topic(1, 1, 1, k) for k in range(1, 5)]), "more than 3 items"),
    ("a topic with no subfield", "nodes", lambda d: d["items"][0].update(openalex=[{k: v for k, v in topic(1, 1, 1, 1).items() if k != "subfield"}]), "missing subfield"),
    ("an id with a control character", "nodes", lambda d: d["items"][0].update(id="a\nb"), "forbids"),
    ("a kind that is not one", "small", lambda d: d["events"][0].update(kind="sweep"), "matches 0 of oneOf"),
    ("an event with a key too many", "small", lambda d: d["events"][0].update(x=1), "matches 0 of oneOf"),
    ("an event with no payload", "small", lambda d: d["events"][0].pop("payload"), "matches 0 of oneOf"),
    ("a seq of 0", "small", lambda d: d["events"][0].update(seq=0), "matches 0 of oneOf"),
    ("an open_road with no houses", "small", lambda d: d["events"][14]["payload"].update(houses=[]), "matches 0 of oneOf"),
    ("an open_road with a house twice", "small", lambda d: d["events"][14]["payload"].update(houses=["h0001", "h0001"]), "matches 0 of oneOf"),
    ("an open_road with a road of the rule", "small", lambda d: d["events"][14]["payload"].update(road="auto:7"), "matches 0 of oneOf"),
    ("an open_road with a road like a rib", "small", lambda d: d["events"][14]["payload"].update(road="lane:x:2"), "matches 0 of oneOf"),
    ("an open_road with a node of another level", "nodes", lambda d: next(e for e in d["events"] if e["kind"] == "open_road" and e["payload"]["topic"])["payload"]["topic"].update(level="planet"),
     "matches 0 of oneOf"),
    ("an open_road with a node of two keys", "nodes", lambda d: next(e for e in d["events"] if e["kind"] == "open_road" and e["payload"]["topic"])["payload"]["topic"].pop("name"),
     "matches 0 of oneOf"),
    ("a merge with one member", "merge", lambda d: next(e for e in d["events"] if e["kind"] == "merge_roads")["payload"].update(members=["f0"]), "matches 0 of oneOf"),
    ("a merge with a member twice", "merge", lambda d: next(e for e in d["events"] if e["kind"] == "merge_roads")["payload"].update(members=["f0", "f0"]), "matches 0 of oneOf"),
    ("a merge below something that is no road id", "merge", lambda d: next(e for e in d["events"] if e["kind"] == "merge_roads")["payload"].update(parent=5), "matches 0 of oneOf"),
    ("a merge with a road of the rule", "merge", lambda d: next(e for e in d["events"] if e["kind"] == "merge_roads")["payload"].update(road="auto:9"), "matches 0 of oneOf"),
    ("a merge with no members", "merge", lambda d: next(e for e in d["events"] if e["kind"] == "merge_roads")["payload"].pop("members"), "matches 0 of oneOf"),
    ("a move_road to the town hall", "scripted", lambda d: next(e for e in d["events"] if e["kind"] == "move_road")["payload"].update(parent=None), "matches 0 of oneOf"),
    ("an undo of event 0", "scripted", lambda d: next(e for e in d["events"] if e["kind"] == "undo")["payload"].update(seq=0), "matches 0 of oneOf"),
    ("a set_rule with a rule too many", "scripted", lambda d: next(e for e in d["events"] if e["kind"] == "set_rule")["payload"].update(x=1), "matches 0 of oneOf"),
    ("an item that exists for another item with no form", "entries", lambda d: next(i for i in d["items"] if "annex_of" in i).pop("annex_form"), "annex_of needs annex_form"),
    ("an item with a form and no house", "entries", lambda d: next(i for i in d["items"] if "annex_of" in i).pop("annex_of"), "annex_form needs annex_of"),
    ("an item that exists for another item in a form that is not one", "entries", lambda d: next(i for i in d["items"] if "annex_of" in i).update(annex_form="shed"), "not one of"),
    ("an item that exists for something that is no id", "entries", lambda d: next(i for i in d["items"] if "annex_of" in i).update(annex_of=5), "not of type"),
    ("an annex event with a form that is not one", "entries", lambda d: next(e for e in d["events"] if e["kind"] == "annex")["payload"].update(form="shed"), "matches 0 of oneOf"),
    ("an annex event with no parent", "entries", lambda d: next(e for e in d["events"] if e["kind"] == "annex")["payload"].pop("parent"), "matches 0 of oneOf"),
    ("an annex event with a key too many", "entries", lambda d: next(e for e in d["events"] if e["kind"] == "annex")["payload"].update(x=1), "matches 0 of oneOf"),
]


@pytest.mark.parametrize("what, world, change, fragment", WRONG, ids=[w for w, *_ in WRONG])
def test_a_wrong_file_does_not_satisfy_the_schema_and_the_program_refuses_it_too(what, world, change, fragment):
    assert faults(file_of(worlds()[world]), SCHEMA) == []  # (the same file before the fault)
    doc = mutated(world, change)
    found = faults(doc, SCHEMA)
    assert found and any(fragment in line for line in found), (what, found)
    assert not accepted(doc), what


# ------------------------------------------------------------------------------------ what a schema cannot say ----
CANNOT = [
    ("min more than max", "small", lambda d: d["rule"].update(min=9, max=5), "min (9) is more than max (5)"),
    ("events out of order", "small", lambda d: d["events"][3].update(seq=40), "numbered 1, 2, 3"),
    ("a road opened twice under one id", "small", lambda d: d["events"].append({**copy.deepcopy(d["events"][14]), "seq": len(d["events"]) + 1}), "there is a road 'a' already"),
    ("items that are not those of the events", "small", lambda d: d["items"].pop(), "items are those of the add_item events"),
    ("an item whose topic is named twice", "small", lambda d: d["items"][0].update(openalex=[topic(1, 1, 1, 1), topic(1, 1, 1, 1)]), "is the topic of"),
    ("an id of white space", "small", lambda d: d["items"][0].update(id="   "), "must not be empty"),
    ("a filing onto a road that is not there", "small", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "file",
                                                                                      "payload": {"house": "h0001", "road": "nowhere"}}), "there is no road 'nowhere'"),
    ("an undo of an event that is not earlier", "small", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "undo",
                                                                                       "payload": {"seq": 99}}), "names an earlier event"),
    ("a date that is not a date", "small", lambda d: d["events"][0].update(at="yesterday"), "is not an ISO 8601 date"),
    ("a merge of a road that is below another road", "merge", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "merge_roads", "payload": {
        "road": "again", "name": "Again", "parent": None, "members": ["f0", "f5"]}}), "does not stand directly below the ring road"),
    ("a merge of a road that is not there", "merge", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "merge_roads", "payload": {
        "road": "again", "name": "Again", "parent": None, "members": ["f5", "ghost"]}}), "there is no road 'ghost'"),
    ("an annex of itself", "entries", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "annex", "payload": {
        "house": "h0001", "parent": "h0001", "form": "wing"}}), "cannot be an annex of itself"),
    ("an annex of a house that is not there", "entries", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "annex", "payload": {
        "house": "h0001", "parent": "ghost", "form": "wing"}}), "there is no house 'ghost'"),
    ("an annex of an annex", "entries", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "annex", "payload": {
        "house": "h0001", "parent": "h0041", "form": "wing"}}), "is an annex of 'h0040'"),
    ("a house that is an annex again", "entries", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "annex", "payload": {
        "house": "h0041", "parent": "h0001", "form": "wing"}}), "is a wing of the house 'h0040'"),
    ("a node that another road stands for", "taken", lambda d: d["events"].append({"seq": len(d["events"]) + 1, "at": "2026-01-01", "kind": "open_road", "payload": {
        "road": "again", "name": "Again", "parent": None, "houses": [hid(i) for i in range(13, 23)], "topic": {"id": "ex:d1", "level": "domain", "name": "Domain 1"}}}), "stands for"),
]


@pytest.mark.parametrize("what, world, change, fragment", CANNOT, ids=[w for w, *_ in CANNOT])
def test_what_the_schema_cannot_say_is_checked_by_the_program(what, world, change, fragment):
    doc = mutated(world, change)
    assert faults(doc, SCHEMA) == [], what  # the schema takes it ...
    with pytest.raises(WorldFileError) as why:  # ... and the program does not
        read_world(doc)
    assert fragment in str(why.value), (what, str(why.value))


# --------------------------------------------------------------- the schema never refuses what the program takes ----
def locations(value):
    """Every place in a document where a fault can be planted: (the container, the key or index)."""
    if isinstance(value, dict):
        for key in list(value):
            yield value, key
            yield from locations(value[key])
    elif isinstance(value, list):
        for i in range(len(value)):
            yield value, i
            yield from locations(value[i])


REPLACEMENTS = [None, True, False, 0, 1, -1, 2, 1.5, "", " ", "x", "a\x01b", "domain", "planet", [], {}, 10**13, 10**400, [None], {"a": 1}]


def mutate(doc, rng):
    """One fault planted somewhere in a copy of the document: a key or an item deleted, a key added, a value replaced by something else, an event's kind changed."""
    doc = copy.deepcopy(doc)
    places = list(locations(doc))
    container, key = rng.choice(places)
    how = rng.choice(["delete", "delete", "add", "replace", "replace", "replace", "kind"])
    if how == "delete":
        del container[key]
    elif how == "add" and isinstance(container[key], dict):
        container[key]["zzz"] = 1
    elif how == "kind" and isinstance(container, dict) and "kind" in container:
        container["kind"] = rng.choice(ev.KINDS)
    else:
        container[key] = copy.deepcopy(rng.choice(REPLACEMENTS))
    return doc


def benign(doc, rng):
    """A change that leaves the file right: an optional key left out, a date, a title or a year (changed where the item is written twice), the largest `max` of the start."""
    doc = copy.deepcopy(doc)
    how = rng.choice(["doi", "openalex", "topic", "at", "title", "year", "max"])
    adds = [e for e in doc["events"] if e["kind"] == "add_item"]
    if how == "topic":
        roads = [e for e in doc["events"] if e["kind"] in ("open_road", "merge_roads")]
        if roads:
            rng.choice(roads)["payload"].pop("topic", None)
    elif how == "at":
        rng.choice(doc["events"])["at"] = rng.choice(["2026-01-02", "2026-01-02T03:04:05Z", "2026-01-02T03:04:05+09:00", "2026-01-02 03:04:05"]) if doc["events"] else None
    elif how == "max":
        doc["rule"]["max"] = rng.choice([doc["rule"]["max"], 50, 99])
    elif adds:
        event = rng.choice(adds)
        twin = next(i for i in doc["items"] if i["id"] == event["payload"]["item"]["id"])
        for item in (event["payload"]["item"], twin):
            if how in ("doi", "openalex"):
                item.pop(how, None)
            elif how == "title":
                item["title"] = "A new title"
            else:
                item["year"] = rng.choice([None, 1999, -500, 2026])
    return doc


@functools.lru_cache(maxsize=None)
def corpus():
    rng = random.Random(20261026)
    docs = []
    for name in ("small", "nodes", "merge", "random"):
        base = file_of(worlds()[name])
        docs += [mutate(base, rng) for _ in range(110)] + [benign(base, rng) for _ in range(30)]
    return docs


def test_the_schema_never_refuses_a_file_that_the_program_takes():
    """A fault planted at random: if the program takes the file the schema takes it too (the schema is the weaker of the two), and both refuse most of them."""
    both_refuse = schema_takes_program_refuses = both_take = 0
    for doc in corpus():
        schema, program = valid(doc, SCHEMA), accepted(doc)
        assert schema or not program, faults(doc, SCHEMA)
        both_refuse += not schema and not program
        schema_takes_program_refuses += schema and not program
        both_take += schema and program
    assert both_refuse > 150 and schema_takes_program_refuses > 40 and both_take > 60  # (the corpus is not a corpus of one kind)


def test_the_validator_agrees_with_jsonschema_on_the_files_and_the_faults_where_it_is_installed():
    jsonschema = pytest.importorskip("jsonschema")
    checker = jsonschema.Draft202012Validator(SCHEMA)
    docs = [file_of(j) for j in worlds().values()] + list(corpus()[::2]) + [mutated(w, c) for _, w, c, _ in WRONG] + [mutated(w, c) for _, w, c, _ in CANNOT]
    for doc in docs:
        assert valid(doc, SCHEMA) == checker.is_valid(doc), faults(doc, SCHEMA)


def test_the_validator_does_not_pass_a_schema_it_does_not_understand():
    with pytest.raises(ValueError, match="does not know"):
        faults({}, {"type": "object", "dependentSchemas": {"a": {"required": ["b"]}}})
    assert faults({"a": 1}, {"type": "object", "dependentRequired": {"a": ["b"]}}) == ["$: a needs b"] and faults({"b": 1}, {"type": "object", "dependentRequired": {"a": ["b"]}}) == []
    assert faults(1, {"type": "integer"}) == [] and faults(True, {"type": "integer"}) and faults("a\nb", {"not": {"pattern": "[\\u0000-\\u001f]"}})
    assert faults({"a": 1}, {"type": "object", "additionalProperties": False})
