#!/usr/bin/env python3
"""The synthetic sample: a topic tree of 80 nodes and a library of 600 items, made from a seed.

    python3 examples/make_example.py [--seed 7] [--out examples]

Writes `tree.json` and `library.json` (the formats of docs/format.md) into the output directory. Everything in them is invented: the DOIs are
`10.0000/ex.<number>` (a prefix no registry hands out), the titles are made of word lists and the authors of initials and common family names.
The library is written in id order, not in arrival order: the engine sorts by `added_at` (ties by id), so the order of the file does not matter.

The counts are chosen to show what the engine does with a library of this size: a root zone that fills up to 40 houses, splits at the 41st, roads that
split again, one topic that holds more than 40 houses of its own and so is over (Networks), a chain of topics that collapse into one road
(Humanities, History), topics too thin to open a road (they stay under the town hall), and a handful of items that have no topic at all.

Same seed, same bytes: the generator uses nothing but `random.Random(seed).random()`, which Python keeps the same from version to version.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 7

# (id, label, houses of its own, children): 80 topics, 585 items with a topic
TREE = ("computing", "Computing", 0, [
    ("algorithms", "Algorithms", 2, [
        ("graph-algorithms", "Graph algorithms", 10, []), ("approximation", "Approximation", 6, []),
        ("streaming", "Streaming algorithms", 5, []), ("string-matching", "String matching", 4, [])]),
    ("systems", "Systems", 3, [
        ("databases", "Databases", 21, []), ("operating-systems", "Operating systems", 6, []), ("networks", "Networks", 44, []),
        ("distributed-systems", "Distributed systems", 9, []), ("compilers", "Compilers", 4, [])]),
    ("intelligence", "Artificial intelligence", 3, [
        ("machine-learning", "Machine learning", 5, [
            ("deep-learning", "Deep learning", 20, []), ("reinforcement-learning", "Reinforcement learning", 8, []),
            ("kernel-methods", "Kernel methods", 3, [])]),
        ("knowledge-graphs", "Knowledge graphs", 6, []), ("planning", "Planning", 4, []),
        ("vision", "Computer vision", 2, [("segmentation", "Segmentation", 6, []), ("detection", "Object detection", 4, [])])]),
    ("security", "Security", 2, [("cryptography", "Cryptography", 8, []), ("privacy", "Privacy", 5, [])]),
]), ("life", "Life sciences", 0, [
    ("ecology", "Ecology", 3, [("marine-ecology", "Marine ecology", 18, []), ("forest-ecology", "Forest ecology", 9, []),
                               ("urban-ecology", "Urban ecology", 5, [])]),
    ("genetics", "Genetics", 2, [("genomics", "Genomics", 26, []), ("epigenetics", "Epigenetics", 8, []),
                                 ("population-genetics", "Population genetics", 11, [])]),
    ("neuroscience", "Neuroscience", 4, [("cognition", "Cognition", 15, []), ("neural-circuits", "Neural circuits", 12, []),
                                         ("brain-imaging", "Brain imaging", 10, [])]),
    ("microbiology", "Microbiology", 2, [("bacteria", "Bacteria", 12, []), ("viruses", "Viruses", 9, []), ("fungi", "Fungi", 4, [])]),
]), ("physical", "Physical sciences", 0, [
    ("physics", "Physics", 2, [("optics", "Optics", 14, []), ("condensed-matter", "Condensed matter", 11, []), ("astrophysics", "Astrophysics", 9, []),
                               ("quantum-information", "Quantum information", 10, [])]),
    ("chemistry", "Chemistry", 1, [("catalysis", "Catalysis", 12, []), ("polymers", "Polymers", 8, []),
                                   ("analytical-chemistry", "Analytical chemistry", 6, [])]),
    ("earth", "Earth science", 1, [("climate", "Climate", 16, []), ("geology", "Geology", 5, []), ("oceanography", "Oceanography", 5, [])]),
]), ("social", "Social sciences", 3, [
    ("economics", "Economics", 2, [("labour-markets", "Labour markets", 11, []), ("trade", "Trade", 7, []),
                                   ("behavioural-economics", "Behavioural economics", 9, [])]),
    ("psychology", "Psychology", 1, [("child-development", "Child development", 9, []), ("social-psychology", "Social psychology", 10, [])]),
    ("education", "Education", 1, [("assessment", "Assessment", 7, []), ("teaching-methods", "Teaching methods", 10, [])]),
]), ("humanities", "Humanities", 0, [
    ("history", "History", 2, [("ancient-history", "Ancient history", 5, []), ("medieval-history", "Medieval history", 4, []),
                               ("modern-history", "Modern history", 11, []), ("history-of-science", "History of science", 13, [])]),
    ("literature", "Literature", 0, []),
]), ("methods", "Methods", 8, [
    ("statistics", "Statistics", 3, [("bayesian", "Bayesian methods", 9, []), ("causal-inference", "Causal inference", 7, [])]),
    ("qualitative-methods", "Qualitative methods", 6, []), ("simulation", "Simulation", 7, []),
])

NO_TOPIC = 15  # items that belong to no topic yet: they live under the town hall

TITLE_PATTERNS = ("A survey of {t}", "Notes on {t}", "{T}: methods and results", "Measuring {t} at scale", "Towards a theory of {t}",
                  "On the limits of {t}", "{T} revisited", "Case studies in {t}", "A short history of {t}", "Rethinking {t}", "{T} in practice",
                  "Open problems in {t}")
ADJECTIVES = ("adaptive", "robust", "scalable", "empirical", "formal", "comparative", "longitudinal", "exploratory", "applied", "critical", "modular", "sparse")
INITIALS = "ABCDEFGHIJKLMNOPRSTVWYZ"
SURNAMES = ("Adler", "Bianchi", "Chen", "Dubois", "Eriksen", "Farouk", "Garcia", "Haddad", "Ivanova", "Jensen", "Kowalski", "Lindgren", "Mbeki", "Nakamura",
            "Okafor", "Petrov", "Quist", "Rossi", "Silva", "Tanaka", "Usman", "Varga", "Weber", "Xu", "Yilmaz", "Zhou", "Almeida", "Bauer", "Costa", "Demir",
            "Evans", "Fischer", "Gupta", "Hansen", "Ito", "Jovanovic", "Khan", "Lopez", "Moreau", "Novak", "Olsen", "Park", "Reyes", "Sato", "Torres")
TYPES = (("article", 62), ("review", 12), ("preprint", 6), ("editorial", 5), ("letter", 5), ("news", 4), ("book chapter", 3), ("erratum", 2),
         ("retraction notice", 1))
TAGS = ("to-read", "methods", "dataset", "benchmark", "survey", "theory", "case-study", "open-access", "classic", "reproduction")
FIRST_DAY, LAST_DAY = date(2019, 2, 1), date(2026, 9, 30)


class Rng:
    """The few draws the generator needs, all made from `random()` so that the sequence is the same in every Python version."""

    def __init__(self, seed: int):
        self._r = random.Random(seed)

    def below(self, n: int) -> int:
        return int(self._r.random() * n)

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def shuffle(self, items: list) -> None:
        for i in range(len(items) - 1, 0, -1):  # Fisher-Yates
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]

    def weighted(self, pairs):
        total = sum(w for _v, w in pairs)
        x = self.below(total)
        for value, w in pairs:
            if x < w:
                return value
            x -= w
        raise AssertionError("unreachable")

    def chance(self, p: float) -> bool:
        return self._r.random() < p


def flatten(node, parent=None, out=None):
    """The tree as the nodes of `tree.json`, parents before children, and {id: (own items, ancestors from the nearest)}."""
    nodes, own, ancestors = out if out is not None else ([], {}, {})
    tid, label, n, kids = node
    nodes.append({"id": tid, "label": label, "parent": parent})
    own[tid] = n
    ancestors[tid] = ([parent] + ancestors[parent]) if parent else []
    for kid in kids:
        flatten(kid, tid, (nodes, own, ancestors))
    return nodes, own, ancestors


def make_tree() -> tuple[list[dict], dict[str, int], dict[str, list[str]], dict[str, str]]:
    nodes, own, ancestors, labels = [], {}, {}, {}
    for root in TREE:
        flatten(root, None, (nodes, own, ancestors))
    for n in nodes:
        labels[n["id"]] = n["label"]
    return nodes, own, ancestors, labels


def title_of(rng: Rng, label: str) -> str:
    phrase = f"{rng.pick(ADJECTIVES)} {label.lower()}"
    return rng.pick(TITLE_PATTERNS).format(t=phrase, T=phrase.capitalize())


def authors_of(rng: Rng) -> list[str]:
    n = 1 + rng.below(3) + (2 if rng.chance(0.15) else 0)
    names: list[str] = []
    while len(names) < n:
        name = f"{rng.pick(INITIALS)}. {rng.pick(SURNAMES)}"
        if name not in names:
            names.append(name)
    return names


def make_items(seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """(nodes, items): the tree of `tree.json` and the items of `library.json`, in id order."""
    nodes, own, ancestors, labels = make_tree()
    rng = Rng(seed)
    slots: list[str | None] = [tid for tid in own for _ in range(own[tid])] + [None] * NO_TOPIC
    rng.shuffle(slots)  # the topic of each item, in the order the items will arrive
    span = (LAST_DAY - FIRST_DAY).days
    days = sorted(rng.below(span + 1) for _ in slots)
    ids = list(range(1, len(slots) + 1))
    rng.shuffle(ids)  # the ids do not follow the arrival order
    items = []
    for n, (topic, day, num) in enumerate(zip(slots, days, ids), start=1):
        added = FIRST_DAY + timedelta(days=day)
        stamp = added.isoformat()
        if rng.chance(0.4):  # a time of day: items of one day then arrive in the order of their times
            stamp += f"T{rng.below(24):02d}:{rng.below(60):02d}:{rng.below(60):02d}Z"
        label = labels[topic] if topic else rng.pick(("Reading list", "Loose notes", "Conference talk", "Grey literature"))
        topics: list[str] = []
        if topic:
            topics = [topic]
            if ancestors[topic] and rng.chance(0.12):  # also filed under a broader topic: the address is still the deepest one
                topics.append(rng.pick(ancestors[topic]))
            rng.shuffle(topics)
        kind = rng.weighted(TYPES)
        year = max(1998, added.year - int(rng.below(1000) ** 2 / 1000 ** 2 * 14))
        item = {"id": f"item-{num:04d}", "title": title_of(rng, label), "authors": authors_of(rng), "year": year}
        if not (kind in ("news", "editorial", "erratum") and rng.chance(0.5)) and rng.chance(0.93):
            item["doi"] = f"10.0000/ex.{num:04d}"
        item.update({"added_at": stamp, "type": kind, "tags": sorted({rng.pick(TAGS) for _ in range(rng.below(4))}), "topics": topics})
        items.append(item)
    items.sort(key=lambda it: it["id"])
    return nodes, items


def dumped(key: str, rows: list[dict]) -> str:
    """One row per line: stable text that a diff can read."""
    lines = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows)
    return f'{{"{key}": [\n{lines}\n]}}\n'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make the synthetic sample: tree.json and library.json")
    ap.add_argument("--seed", type=int, default=SEED, help="the seed (default: %(default)s)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent), help="the directory to write to (default: this directory)")
    args = ap.parse_args(argv)
    nodes, items = make_items(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, key, rows in (("tree.json", "nodes", nodes), ("library.json", "items", items)):
        with open(out / name, "w", encoding="utf-8", newline="\n") as f:
            f.write(dumped(key, rows))
    print(f"wrote {out}/tree.json ({len(nodes)} nodes) and {out}/library.json ({len(items)} items)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
