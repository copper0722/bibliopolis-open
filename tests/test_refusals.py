"""Every refusal and every error of a world file has an id and params (bibliopolis.events.CODES): the source gives each one, a scenario makes each one, and the params are plain
JSON. A page translates the message from the id and the params, so none may be left without."""

import ast
import json
from pathlib import Path

import pytest
import refusal_cases as rc
from hand_support import Hand, hid, stamp

from bibliopolis import events as ev
from bibliopolis.events import Refusal
from bibliopolis.hand import fold
from bibliopolis.journal import Journal, WorldFileError, dumps_world, read_world, world_document
from bibliopolis.store import Store
from bibliopolis.suggest import suggest_file, suggest_road

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("events", "journal", "hand", "suggest", "store")
ERRORS = ("Refusal", "WorldFileError")
BUILDERS = ("branches_full", "too_deep", "output_taken", "database_taken")  # functions of the modules that build a `Refusal` (with a literal id and its params) for a raise statement


# --------------------------------------------------------------------------------- the list and its scenarios ----
def test_the_list_of_ids_is_one_list_of_names_each_with_the_names_of_its_params():
    assert len(ev.CODES) == 77 and all(code.isidentifier() and code == code.lower() for code in ev.CODES)
    for code, params in ev.CODES.items():
        assert isinstance(params, tuple) and len(set(params)) == len(params) and all(isinstance(p, str) and p.isidentifier() for p in params), code


def test_there_is_a_scenario_for_each_id_and_for_nothing_else():
    assert list(rc.CASES) == list(ev.CODES)


@pytest.mark.parametrize("code", list(ev.CODES))
def test_a_scenario_makes_its_id_with_the_params_of_the_list_and_only_plain_json(code, tmp_path):
    made = rc.CASES[code](tmp_path)
    if isinstance(made, dict):  # a problem of shape
        shown, found, params = "problem", made["code"], made["params"]
        assert made["where"] and made["text"].startswith(made["where"] + ": ")
    else:
        shown, found, params = type(made).__name__, made.code, made.params
        assert isinstance(made, (Refusal, WorldFileError)) and json.loads(json.dumps(made.as_dict())) == made.as_dict()
        assert made.as_dict()["message"] == str(made) and (made.event is None or set(made.event) == {"seq", "kind"})
    assert found == code, (shown, found)
    assert set(params) == set(ev.CODES[code]) and json.loads(json.dumps(params)) == params, code


def test_each_id_is_made_as_a_refusal_a_file_error_or_a_problem_of_shape_and_the_kinds_are_these_many(tmp_path):
    kinds = {"Refusal": set(), "WorldFileError": set(), "problem": set()}
    for code, case in rc.CASES.items():
        folder = tmp_path / code
        folder.mkdir()
        made = case(folder)
        kinds["problem" if isinstance(made, dict) else type(made).__name__].add(code)
    assert kinds["Refusal"] | kinds["WorldFileError"] | kinds["problem"] == set(ev.CODES)
    assert (len(kinds["Refusal"]), len(kinds["WorldFileError"]), len(kinds["problem"])) == (34, 12, 31)


def test_the_problems_of_an_invalid_refusal_have_each_an_id_of_the_list_and_a_place():
    made = rc.invalid(None)
    assert made.code == "invalid" and set(made.params) == {"problems", "more"} and made.params["more"] == 0
    assert made.params["problems"] == [{"where": "event.payload.item.id", "code": "not_text", "params": {"got": "int"}}]
    for entry in made.params["problems"]:
        assert set(entry) == {"where", "code", "params"} and set(entry["params"]) == set(ev.CODES[entry["code"]])
    assert str(made) == "event.payload.item.id: must be a string, got int"


def test_an_invalid_refusal_lists_twenty_problems_and_counts_the_rest():
    many = {"item": {"id": "a", "title": "", "authors": [1] * 25, "year": None, "type": "article"}}  # twenty-five authors that are not text
    with pytest.raises(Refusal) as why:
        Journal().append("add_item", many, stamp(1))
    assert why.value.code == "invalid" and len(why.value.params["problems"]) == 20 and why.value.params["more"] == 5
    assert str(why.value).splitlines()[-1] == "... and 5 more" and len(str(why.value).splitlines()) == 21
    assert {p["code"] for p in why.value.params["problems"]} == {"not_text"} and why.value.params["problems"][19]["where"] == "event.payload.item.authors[19]"


def test_several_kinds_of_problem_of_one_item_are_listed_each_with_its_id():
    bad = {"item": {"id": 1, "title": 2, "authors": 3, "year": "x", "type": 4, "openalex": [5, 6, 7], "doi": 8}}
    with pytest.raises(Refusal) as why:
        Journal().append("add_item", bad, stamp(1))
    listed = why.value.params["problems"]
    assert len(listed) == len(str(why.value).splitlines()) and {p["code"] for p in listed} == {"not_text", "authors_not_a_list", "year_bad", "topic_not_an_object"}


# ----------------------------------------------------------------------------- a refusal in a log or a file ----
def test_a_refusal_of_an_event_in_a_log_names_the_event_and_keeps_its_id_and_params():
    h = Hand()
    h.add(14)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    bad = [*h.journal.events, {"seq": 16, "at": stamp(99), "kind": "file", "payload": {"house": hid(12), "road": "nowhere"}}]
    for refuse in (lambda: Journal.replay(h.journal.rule, bad), lambda: fold(bad, h.journal.rule)):
        with pytest.raises(Refusal) as why:
            refuse()
        assert (why.value.code, why.value.params, why.value.event) == ("no_road", {"road": "nowhere"}, {"seq": 16, "kind": "file"})
        assert str(why.value) == "event 16 (file): there is no road 'nowhere'"


def test_a_world_file_that_holds_a_refused_event_says_the_same_id_with_the_place_in_the_file():
    h = Hand()
    h.add(14)
    h.open("a", "A", None, [hid(i) for i in range(1, 11)])
    doc = json.loads(dumps_world(world_document(h.journal)))
    doc["events"].append({"seq": 16, "at": stamp(99), "kind": "file", "payload": {"house": hid(12), "road": "nowhere"}})
    with pytest.raises(WorldFileError) as why:
        read_world(doc)
    assert (why.value.code, why.value.params, why.value.event, why.value.where) == ("no_road", {"road": "nowhere"}, {"seq": 16, "kind": "file"}, "world.events[15]")
    assert str(why.value) == "world.events[15] (file): there is no road 'nowhere'"


def test_a_store_that_holds_a_refused_event_says_the_same_id_with_the_file(tmp_path):
    import sqlite3

    path = tmp_path / "w.sqlite"
    Store.import_journal(path, rc.small_journal())  # 17 events
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO event VALUES (18, '2026-01-01', 'file', '{\"house\":\"h0012\",\"road\":\"gone\"}')")
    with pytest.raises(WorldFileError) as why:
        Store(path).journal()
    assert (why.value.code, why.value.params, why.value.event, why.value.where) == ("no_road", {"road": "gone"}, {"seq": 18, "kind": "file"}, str(path))


def test_the_suggestions_refuse_with_the_same_ids_as_the_events_do():
    h = Hand()
    h.add(3)
    for act, code, params in ((lambda: suggest_road(h.state, "x"), "no_road", {"road": "x"}), (lambda: suggest_file(h.state, "nobody"), "not_a_house", {"house": "nobody"})):
        made = rc.raised(act)
        assert (made.code, made.params) == (code, params)


def test_an_undo_that_cannot_be_taken_says_which_event_fails_and_with_which_refusal():
    made = rc.undo_unfoldable(None)
    assert made.code == "undo_unfoldable" and (made.params["target"], made.params["later"], made.params["kind"]) == (43, 44, "open_road")
    assert (made.params["cause"], made.params["cause_params"]) == ("house_elsewhere", {"house": "h0011", "road": None, "on": "a"})
    assert made.params["cause"] in ev.CODES and set(made.params["cause_params"]) == set(ev.CODES["house_elsewhere"])


# ------------------------------------------------------------------------------------- the source gives every refusal an id ----
def id_problems(source: str, name: str = "source") -> list[str]:
    """What is wrong in `source` with the ids of the refusals it raises and the problems of shape it adds: every `Refusal(...)` and `WorldFileError(...)` has a literal id of the list
    as its second argument and exactly the params of the list as keywords (or passes an id and params on: `x.code` and `**x.params`), and every `problems.add(...)` has a literal id of
    the list as its third argument and the params of the list."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        is_add = called == "add" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "problems"
        if called not in ERRORS and not is_add:
            continue
        place = f"{name}:{node.lineno} {called}"
        position = 1 if called in ERRORS else 2
        if len(node.args) <= position:
            bad.append(f"{place} has no id")
            continue
        code = node.args[position]
        splat = [k for k in node.keywords if k.arg is None]
        if isinstance(code, ast.Constant) and isinstance(code.value, str):
            if code.value not in ev.CODES:
                bad.append(f"{place}: {code.value!r} is not in CODES")
            elif splat or {k.arg for k in node.keywords} != set(ev.CODES[code.value]):
                bad.append(f"{place}: the params of {code.value!r} are {sorted(k.arg or '**' for k in node.keywords)}, not {sorted(ev.CODES[code.value])}")
        elif not (isinstance(code, ast.Attribute) and code.attr == "code" and len(splat) == 1 and isinstance(splat[0].value, ast.Attribute) and splat[0].value.attr == "params"
                  and len(node.keywords) == 1):
            bad.append(f"{place}: the id is not a literal of CODES, nor a `.code` passed on with `**.params`")
    return bad


@pytest.mark.parametrize("module", MODULES)
def test_every_refusal_and_every_problem_in_the_source_has_an_id_of_the_list_and_its_params(module):
    path = ROOT / "bibliopolis" / f"{module}.py"
    assert id_problems(path.read_text(encoding="utf-8"), path.name) == []


def test_the_check_of_the_source_sees_a_refusal_with_no_id_a_wrong_id_and_wrong_params():
    good = ("raise Refusal('x', 'no_road', road=1)\nproblems.add(w, 'x', 'text_empty')\nraise WorldFileError('x', why.code, **why.params)\n"
            "problems.add(w, 'x', 'keys_missing', keys=[])\nraise Refusal('x', 'branches_full', road=None, limit=1, number=2, remedy='merge_roads')")
    assert id_problems(good) == []
    cases = {"no id": "raise Refusal('x')", "no id in an add": "problems.add(w, 'x')", "an id that is not listed": "raise Refusal('x', 'nonsense')",
             "a variable id": "raise Refusal('x', code, road=1)", "a param too few": "raise Refusal('x', 'no_road')", "a param too many": "raise Refusal('x', 'no_road', road=1, more=2)",
             "a wrong param": "raise Refusal('x', 'no_road', house=1)", "a splat": "raise Refusal('x', 'no_road', **p)", "a problem with wrong params": "problems.add(w, 'x', 'text_empty', got=1)",
             "an id passed on without its params": "raise WorldFileError('x', why.code)"}
    for what, source in cases.items():
        assert id_problems(source), what


def test_no_other_class_of_the_package_is_raised_for_a_refusal_of_a_world():
    """The refusals of a world are `Refusal` and `WorldFileError` and nothing else: no `raise ValueError(...)` of text without an id in the modules that make a world."""
    for module in MODULES:
        tree = ast.parse((ROOT / "bibliopolis" / f"{module}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
                assert node.exc.func.id in (*ERRORS, *BUILDERS), f"{module}.py:{node.lineno} raises {node.exc.func.id}"
        for node in ast.walk(tree):  # a builder makes its refusal itself, from an id of the list: the scan above has checked that call
            if isinstance(node, ast.FunctionDef) and node.name in BUILDERS:
                assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Refusal" for n in ast.walk(node)), node.name
