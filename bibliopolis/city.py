"""From a library and a topic tree to a city: the whole pipeline in three calls.

    build_city(library, tree, mode="grow") -> dict       the layout v4 document (bibliopolis.document), ready for `bibliopolis.layout.render`
    build_world(library, tree, mode="grow")              (plan, tree, world, items): the pieces, for a test or a picture
    summary(document) -> dict                            the numbers the command line reports
    chronicle_lines(document) -> list[str]               the chronicle of a city as plain sentences

The steps: check the two documents (bibliopolis.inputs), put the items in arrival order, build the plan from the whole library (directions,
bibliopolis.plan), fold the arrivals into a world one house at a time (bibliopolis.world), and write the world as a document
(bibliopolis.document). Same input, same bytes.
"""

from __future__ import annotations

import re

from . import document, inputs
from . import layout as lay
from . import plan as plan_mod
from . import world as world_mod
from .plan import GROW, MAX_HOUSES, MIN_HOUSES
from .tree import TreeView


def build_world(library: dict, tree: dict, *, mode: str = GROW, max_houses: int = MAX_HOUSES, min_houses: int = MIN_HOUSES,
                trunk_min: int = lay.TRUNK_MIN, first: int | None = None) -> tuple[dict, TreeView, dict, list[dict]]:
    """(plan, tree view, world, items in arrival order) for a library document and a tree document (both are checked first: `InputError`).

    Every chronicle entry of the world also says `at`, the `added_at` of the item whose arrival caused it.

    `first` replays the growth: the build stops after the first `first` items of the arrival order, but the plan still reads the whole library, so the
    world is the city that the whole library makes, at an earlier moment (its chronicle is the start of the full chronicle). `items` holds them all.
    The last step of a build, `complete` (a mirror city's roads that no house stands on or below), runs only when every item is placed: a replay is the
    build stopped early, so a road that the first `first` items have not reached is not there yet, and opens where the full build opens it."""
    if first is not None and (not isinstance(first, int) or isinstance(first, bool) or first < 0):
        raise ValueError(f"first must be a whole number >= 0, got {first!r}")
    tree_doc = inputs.read_tree(tree)
    items = inputs.read_library(library, tree_doc)
    tv = TreeView(tree_doc)
    plan = plan_mod.build_plan(tv, items, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    world = world_mod.new_world(plan)
    placed = items if first is None else items[:first]
    result = world_mod.assign(plan, tv, world, placed)
    world = world_mod.apply_delta(world, result["delta"])
    if len(placed) == len(items):  # the last step of a build; a replay stops before it
        world = world_mod.apply_delta(world, world_mod.complete(plan, tv, world)["delta"])  # a mirror city: the roads no house stands on or below
    for entry in world["chronicle"]:  # `seq` is the arrival counter: the n-th item in arrival order caused the entry
        entry["at"] = items[entry["seq"] - 1]["added_at"]
    return plan, tv, world, items


def build_city(library: dict, tree: dict, *, mode: str = GROW, max_houses: int = MAX_HOUSES, min_houses: int = MIN_HOUSES,
               trunk_min: int = lay.TRUNK_MIN, with_coast: bool = True, first: int | None = None) -> dict:
    """The layout v4 document of the city that `library` and `tree` make in `mode` ("grow" or "mirror"); `first` as in `build_world`."""
    _plan, _tv, world, _items = build_world(library, tree, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min, first=first)
    return document.world_layout(world, with_coast=with_coast)


def summary(doc: dict) -> dict:
    """The numbers of a city document: houses, roads (continuations are not counted twice), houses under the town hall, splits, and the streets that are
    over now (a road or the root zone that holds more than `max` houses and cannot split). The chronicle remembers every road that was ever over; a road
    that a later split brought back under `max` is in the chronicle and no longer counts here."""
    streets = doc["composition"]["streets"]
    chronicle = doc["world"]["chronicle"]
    return {"mode": doc["world"]["mode"], "houses": doc["world"]["houses"], "roads": streets["total"], "underground": doc["composition"]["measure"]["underground_lots"],
            "splits": sum(1 for e in chronicle if "from" in e), "over": sum(1 for p in doc["places"].values() if p["kind"] == "street" and p.get("over"))}


_DAY = re.compile(r"\d{4}-\d\d-\d\d")


def chronicle_lines(doc: dict, limit: int | None = None) -> list[str]:
    """The chronicle of a city document as sentences, oldest first, one per entry (the first `limit` of them if given): the house whose arrival caused it, the
    day it was added, and what happened. Every number comes from the entry or from the rule of the document. (In a world built by hand an entry says the event
    that wrote it, and there are entries for a house filed, a road renamed or moved, an undo and a change of rule.)"""
    places = doc["places"]
    rule = doc["world"]["districts"]

    def name(pid: str, lead: bool = True) -> str:  # the root zone, the town hall, or a road by the last word of its address (`lead`: the first word of a sentence)
        place = places.get(pid)
        if place is None:
            return pid
        if place.get("underground") or place.get("kind") == "plaza":
            words = "the root zone" if place.get("underground") else "the town hall"
            return words.capitalize() if lead else words
        return (place.get("address") or [pid])[-1]

    lines = []
    for e in doc["world"]["chronicle"][:limit]:
        at = e.get("at")
        when = f"house {e['seq']}" if e.get("event_id") is None else f"event {e['event_id']}"
        if isinstance(at, str) and at:
            when += ", " + (at[:10] if _DAY.match(at) else at)  # the day, when `at` starts with one
        if "from" in e:
            lines.append(f"{when}: {name(e['from'])} held {e['count_before']} houses. {e['label']} opens as a road with {len(e['houses'])} of them; "
                         f"{e['count_after']} stay.")
        elif "over" in e:
            lines.append(f"{when}: {name(e['over'])} holds {e['count']} houses, more than {rule['max']}, and no group of {rule['min']} or more can open a road. "
                         f"It is marked over.")
        elif "filed" in e:
            lines.append(f"{when}: the house {e['filed']} moves from {name(e['left'], False)} to {name(e['joined'], False)}.")
        elif "renamed" in e:
            lines.append(f"{when}: {e['was']} is renamed {e['label']}.")
        elif "moved" in e:
            lines.append(f"{when}: {name(e['moved'])} moves from below {name(e['was_below'], False)} to below {name(e['below'], False)}, with {len(e['houses'])} houses.")
        elif "undone" in e:
            lines.append(f"{when}: event {e['undone']} ({e['of']}) is undone.")
        else:
            r = e["rule"]
            lines.append(f"{when}: the rule is now {r['max']} houses at most and {r['min']} at least for a new road, auto {'on' if r.get('auto') else 'off'}.")
    return lines
