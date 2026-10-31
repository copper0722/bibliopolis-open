"""Libraries in which some items exist for other items, for the tests of annexes: a library with annexes made out of a library that has none, and the normal form that the
city of the one must share with the city of the other. Not collected by pytest (the name has no test_ prefix)."""

import copy
import random


def annexed(items, seed, share=0.25):
    """`items` (a library in arrival order, as `make_tree` and `random_world` make them) with about `share` of them made annexes, as (the new items, the ids of the annexes).
    An annex is of a house chosen from the items that are not annexes, whether that house arrives before it or after it, in a form chosen at random: never of an annex."""
    rng = random.Random(seed)
    out = [{**a, "topics": list(a["topics"])} for a in items]
    chosen = [i for i in range(len(out)) if rng.random() < share]
    pool = [i for i in range(len(out)) if i not in set(chosen)]
    if not pool:
        return out, []
    for i in chosen:
        parent = rng.choice(pool)
        out[i]["annex_of"], out[i]["annex_form"] = out[parent]["id"], rng.choice(["wing", "mailbox"])
    return out, [out[i]["id"] for i in chosen]


def houses_only(items):
    """The items that are houses: those with no `annex_of`."""
    return [a for a in items if "annex_of" not in a]


def without_annexes(doc):
    """The document of a city with what counts annexes taken out: their records, the entries of the chronicle that are theirs, the counts that include them and the notes that only a city
    with annexes has, and with the arrival numbers of the houses numbered 1, 2, ... in the order they arrived, as they are in a library that has no annex. What a city of a library with
    annexes must share, to the byte, with the city of the same library without them: the annexes never move a house."""
    doc = copy.deepcopy(doc)
    lots = sorted(p["seq"] for p in doc["places"].values() if p["kind"] == "lot")
    number = {seq: k for k, seq in enumerate(lots, start=1)}
    doc["places"] = {pid: p for pid, p in doc["places"].items() if p["kind"] != "annex"}
    for p in doc["places"].values():
        if p["kind"] == "lot":
            p["seq"] = number[p["seq"]]
    chronicle = [e for e in doc["world"]["chronicle"] if "annex" not in e]
    for n, e in enumerate(chronicle, start=1):
        e["n"], e["seq"] = n, number[e["seq"]]
    doc["world"]["chronicle"] = chronicle
    doc["world"]["seq"] = len(lots)
    doc["composition"]["articles"] = doc["composition"]["buildings"] = len(lots)
    doc["counts"].pop("annex", None)
    doc["kinds"].pop("annex", None)
    for note in ("composition.buildings", "world.chronicle.annex"):
        doc["world"]["notes"].pop(note, None)
    return doc
