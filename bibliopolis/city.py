"""From a library and a topic tree to a city: the whole pipeline in three calls.

    build_city(library, tree, mode="grow") -> dict       the layout v4 document (bibliopolis.document), ready for `bibliopolis.layout.render`
    build_world(library, tree, mode="grow")              (plan, tree, world, items): the pieces, for a test or a picture
    summary(document) -> dict                            the numbers the command line reports

The steps: check the two documents (bibliopolis.inputs), put the items in arrival order, build the plan from the whole library (directions,
bibliopolis.plan), fold the arrivals into a world one house at a time (bibliopolis.world), and write the world as a document
(bibliopolis.document). Same input, same bytes.
"""

from __future__ import annotations

from . import document, inputs
from . import layout as lay
from . import plan as plan_mod
from . import world as world_mod
from .plan import GROW, MAX_HOUSES, MIN_HOUSES
from .tree import TreeView


def build_world(library: dict, tree: dict, *, mode: str = GROW, max_houses: int = MAX_HOUSES, min_houses: int = MIN_HOUSES,
                trunk_min: int = lay.TRUNK_MIN) -> tuple[dict, TreeView, dict, list[dict]]:
    """(plan, tree view, world, items in arrival order) for a library document and a tree document (both are checked first: `InputError`).

    Every chronicle entry of the world also says `at`, the `added_at` of the item whose arrival caused it."""
    tree_doc = inputs.read_tree(tree)
    items = inputs.read_library(library, tree_doc)
    tv = TreeView(tree_doc)
    plan = plan_mod.build_plan(tv, items, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    world = world_mod.new_world(plan)
    result = world_mod.assign(plan, tv, world, items)
    world = world_mod.apply_delta(world, result["delta"])
    world = world_mod.apply_delta(world, world_mod.complete(plan, tv, world)["delta"])  # a mirror city: the roads no house stands on or below
    for entry in world["chronicle"]:  # `seq` is the arrival counter: the n-th item in arrival order caused the entry
        entry["at"] = items[entry["seq"] - 1]["added_at"]
    return plan, tv, world, items


def build_city(library: dict, tree: dict, *, mode: str = GROW, max_houses: int = MAX_HOUSES, min_houses: int = MIN_HOUSES,
               trunk_min: int = lay.TRUNK_MIN, with_coast: bool = True) -> dict:
    """The layout v4 document of the city that `library` and `tree` make in `mode` ("grow" or "mirror")."""
    _plan, _tv, world, _items = build_world(library, tree, mode=mode, max_houses=max_houses, min_houses=min_houses, trunk_min=trunk_min)
    return document.world_layout(world, with_coast=with_coast)


def summary(doc: dict) -> dict:
    """The numbers of a city document: houses, roads (continuations are not counted twice), houses under the town hall, splits and over roads."""
    streets = doc["composition"]["streets"]
    chronicle = doc["world"]["chronicle"]
    return {"mode": doc["world"]["mode"], "houses": doc["world"]["houses"], "roads": streets["total"], "underground": doc["composition"]["measure"]["underground_lots"],
            "splits": sum(1 for e in chronicle if "from" in e), "over": sum(1 for e in chronicle if "over" in e)}
