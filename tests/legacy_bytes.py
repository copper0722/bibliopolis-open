"""The texts that inputs with no annex key gave in version 0.4.0, made again: `artifacts()` builds them, tests/test_legacy_bytes.py holds their sha256.

The hashes were made by running this module on a snapshot of the commit of version 0.4.0, before the engine knew annexes, so that "no annex key, the same bytes" is proved against
the old code and not against the new code itself. The cases are written out here and do not call a helper that a later change may make richer (`every_entry` has a copy of its own,
and `play` is used as it was). Every city document names the version of the generator, and a new version changes that one word in every city on purpose: `artifacts()` reads the version a
city names as 0.4.0 (`as_made_by_the_old_version`), so the pins stay what the old code made and nothing else is hidden. Not collected by pytest (the name has no test_ prefix)."""

import hashlib
import json

from hand_support import Hand, hid, houses, play, scripted, scripted_branches, scripted_merge, scripted_nodes, topic
from support import random_world, sample

import bibliopolis
from bibliopolis import __version__, inputs, picture
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.city import chronicle_lines, summary
from bibliopolis.journal import dumps_world, world_document
from bibliopolis.tree import TreeView


LEGACY_VERSION = "0.4.0"  # the version that made the pins


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def as_made_by_the_old_version(text: str) -> str:
    """`text` with the version of the generator that a city document names (`"version": "<the version of the package>"`) read as the old version's: the one word that a new version changes in every city, and
    that is re-pinned with the version (tests/test_canonical.py, tests/test_world_file.py). Nothing else is read back, so any other difference is not what the old version made."""
    return text.replace(f'"version": "{__version__}"', f'"version": "{LEGACY_VERSION}"')


def log_every_entry() -> Hand:
    """A log whose chronicle has an entry of each kind that the version of 0.4.0 wrote: a road opened, a house filed, renamed, moved, avenues merged, a change of rule, a new
    radius of the ring road and an undo (a copy of the helper `every_entry` as it was)."""
    h = Hand()
    h.add(30, topic(1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 12))
    h.open("b", "B", None, houses(13, 24))
    h.file(hid(26), "a")
    h.rename("a", "Alpha")
    h.open("a1", "A one", "a", houses(1, 10))
    h.move("a1", "b")
    h.merge("m", "M", ["a", "b"])
    h.rule(30, 5)
    h.rule(200, 5)
    h.add(1)
    h.undo()
    return h


def built() -> dict[str, str]:
    """The cities that `build` makes, as the text a file holds, and what is made from them."""
    out: dict[str, str] = {}
    tree, library = sample()
    for mode in ("grow", "mirror"):
        for first in (None, 0, 41, 150):
            out[f"sample {mode} first={first}"] = lay.render(bibliopolis.build_city(library, tree, mode=mode, first=first))
        out[f"sample {mode} without a coast"] = lay.render(bibliopolis.build_city(library, tree, mode=mode, with_coast=False))
        doc = bibliopolis.build_city(library, tree, mode=mode)
        out[f"sample {mode} picture"] = picture.render(doc)
        out[f"sample {mode} chronicle"] = "\n".join(chronicle_lines(doc))
        out[f"sample {mode} summary"] = json.dumps(summary(doc), sort_keys=True)
    doc = bibliopolis.build_city(library, tree, first=150)
    out["sample grow picture of the first 150"] = picture.render(doc)
    out["sample items as the reader gives them"] = json.dumps(inputs.read_library(library, inputs.read_tree(tree)))
    for seed in range(8):
        random_tree, items = random_world(seed)
        rule = {} if seed % 2 == 0 else {"max_houses": 15, "min_houses": 5, "trunk_min": 40}
        for mode in ("grow", "mirror"):
            out[f"random world {seed} {mode}"] = lay.render(bibliopolis.build_city({"items": items}, random_tree, mode=mode, **rule))
    return out


def batched() -> dict[str, str]:
    """A world made by `assign` in calls of seventeen arrivals: every delta, and the world document that the deltas make."""
    random_tree, items = random_world(3)
    tv = TreeView(random_tree)
    plan = plan_mod.build_plan(tv, items, max_houses=15, min_houses=5, trunk_min=40)
    doc, deltas = zw.new_world(plan), []
    for start in range(0, len(items), 17):
        result = zw.assign(plan, tv, doc, items[start:start + 17], event_id=start)
        deltas.append(json.dumps(result["delta"], sort_keys=True))
        doc = zw.apply_delta(doc, result["delta"])
    doc = zw.apply_delta(doc, zw.complete(plan, tv, doc)["delta"])
    return {"batched deltas": "\n".join(deltas), "batched world document": json.dumps(doc, sort_keys=True)}


def by_hand() -> dict[str, str]:
    """The worlds built by hand: the four scripted logs and one with an entry of each kind, as a world file, as a city, as the document of the world and as the chronicle; and
    random players (the rule `auto`, merging, a new radius of the ring road), as a world file and as a city."""
    out: dict[str, str] = {}
    for name, make in (("scripted", scripted), ("scripted_nodes", scripted_nodes), ("scripted_merge", scripted_merge), ("scripted_branches", scripted_branches),
                       ("every entry", log_every_entry)):
        h = make()
        city = h.state.city()
        out[f"hand {name} world file"] = dumps_world(world_document(h.journal))
        out[f"hand {name} city"] = lay.render(city)
        out[f"hand {name} world document"] = json.dumps(h.state.doc, sort_keys=True)
        out[f"hand {name} chronicle"] = "\n".join(chronicle_lines(city))
    out["hand scripted picture"] = picture.render(scripted().state.city())
    for seed, options in ((3, {"steps": 120}), (5, {"steps": 100, "auto": True, "suggested": True, "arrivals": 0.8, "merging": True}),
                          (7, {"steps": 100, "resizing": True, "merging": True}), (11, {"steps": 140, "auto": True, "suggested": True, "resizing": True, "merging": True, "branches": 5})):
        journal = play(seed, **options)
        out[f"hand play {seed} world file"] = dumps_world(world_document(journal))
        out[f"hand play {seed} city"] = lay.render(journal.state.city())
    return out


def artifacts() -> dict[str, str]:
    return {name: as_made_by_the_old_version(text) for name, text in {**built(), **batched(), **by_hand()}.items()}
