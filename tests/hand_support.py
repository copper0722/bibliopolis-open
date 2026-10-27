"""Worlds built by hand for the tests: invented items with invented OpenAlex-shaped topics, a clock that counts, a random player, and the checks of a hand-built
world (the geometry and bookkeeping of the engine, the roads and houses it must agree with, the stability of the lots).

Nothing here is an identifier of a real database: the topics are `ex:d1.f2.s3.t4` and the names `Domain 1`, `Field 1.2`, ... Not collected by pytest (the name has no
test_ prefix)."""

import copy
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

import checks

from bibliopolis import inputs
from bibliopolis import layout as lay
from bibliopolis import world as zw
from bibliopolis.events import Refusal, standing
from bibliopolis.hand import State, fold
from support import bearing_of_direction, capacity, cells_table, gates_of, radius_for
from bibliopolis.journal import Journal
from bibliopolis.suggest import suggest_merge, suggest_road

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
ROOT = zw.ROOT_PLACE


def stamp(i: int) -> str:
    """An `at` that grows with `i`: ten seconds apart."""
    return (START + timedelta(seconds=10 * i)).isoformat().replace("+00:00", "Z")


# ----------------------------------------------------------------------------------------------- the items ----
def topic(d: int, f: int, s: int, t: int) -> dict:
    """An invented OpenAlex-shaped topic with all four levels."""
    return {"domain": {"id": f"ex:d{d}", "name": f"Domain {d}"}, "field": {"id": f"ex:d{d}.f{f}", "name": f"Field {d}.{f}"},
            "subfield": {"id": f"ex:d{d}.f{f}.s{s}", "name": f"Subfield {d}.{f}.{s}"}, "topic": {"id": f"ex:d{d}.f{f}.s{s}.t{t}", "name": f"Topic {d}.{f}.{s}.{t}"}}


def item(i: int, *topics: dict, **extra) -> dict:
    """The metadata of item number `i` (`h0001`), with the topics given (the primary one first)."""
    out = {"id": f"h{i:04d}", "title": f"Title {i}", "authors": ["A. Author"], "year": 2020, "doi": f"10.0000/h.{i:04d}", "type": "article", "openalex": list(topics)}
    out.update(extra)
    return out


def hid(i: int) -> str:
    return f"h{i:04d}"


def sample_world_items() -> list[dict]:
    """The 600 items of the sample as items of a world, in arrival order, with invented OpenAlex-shaped topics made from the nodes they are filed under (the deepest first, up to
    three): the root of the sample tree is the domain, its child the field, and so on; a node that is not deep enough is its own subfield and topic."""
    from support import sample

    from bibliopolis.tree import TreeView, major_tag

    tree, library = sample()
    checked = inputs.read_tree(tree)
    items = inputs.read_library(library, checked)
    view = TreeView(checked)

    def path(node_id):
        out = []
        while node_id is not None:
            out.append(node_id)
            node_id = view.parent(node_id)
        return out[::-1]

    def oa_of(nodes):
        pick = lambda i: nodes[min(i, len(nodes) - 1)]  # noqa: E731
        return {"domain": {"id": f"ex:domain:{pick(0)}", "name": f"Domain {pick(0)}"}, "field": {"id": f"ex:field:{pick(1)}", "name": f"Field {pick(1)}"},
                "subfield": {"id": f"ex:subfield:{pick(2)}", "name": f"Subfield {pick(2)}"}, "topic": {"id": f"ex:topic:{nodes[-1]}", "name": f"Topic {nodes[-1]}"}}

    out = []
    for it in items:
        main = major_tag(view, it)
        order = ([main] if main else []) + [t for t in it["topics"] if t != main]
        out.append({"id": it["id"], "title": it["title"], "authors": it["authors"], "year": it["year"], "doi": it["doi"], "type": it["type"],
                    "openalex": [oa_of(path(t)) for t in order[:3]]})
    return out


def random_item(rng: random.Random, i: int) -> dict:
    """An item whose topics cluster: 2 domains, 2 fields each, 2 subfields each, 3 topics each, so that groups of a size appear at every level."""
    pick = lambda: topic(rng.choice([1, 2]), rng.choice([1, 2]), rng.choice([1, 2]), rng.choice([1, 2, 3]))  # noqa: E731
    topics, ids = [], set()
    for _ in range(rng.choice([0, 1, 1, 1, 2, 3])):
        t = pick()
        if t["topic"]["id"] not in ids:
            ids.add(t["topic"]["id"])
            topics.append(t)
    return item(i, *topics)


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return stamp(self.n)


class Hand:
    """A journal with a clock: `hand.add(n)` brings n items, `hand.open(...)`, `hand.file(...)`, ... append one event each and return it."""

    def __init__(self, rule=None):
        self.journal = Journal(rule)
        self.clock = Clock()
        self.count = 0

    @property
    def state(self) -> State:
        return self.journal.state

    def event(self, kind: str, payload: dict) -> dict:
        return self.journal.append(kind, payload, self.clock())

    def add(self, n: int = 1, *topics: dict, **extra) -> list[str]:
        out = []
        for _ in range(n):
            self.count += 1
            self.event("add_item", {"item": item(self.count, *topics, **extra)})
            out.append(hid(self.count))
        return out

    def add_items(self, items: list[dict]) -> None:
        for it in items:
            self.count += 1
            self.event("add_item", {"item": it})

    def open(self, road: str, name: str, parent: str | None, houses: list[str], topic: dict | None = None) -> dict:
        return self.event("open_road", {"road": road, "name": name, "parent": parent, "houses": houses, "topic": topic})

    def take(self, suggestion: dict, road: str) -> dict:
        """Open the road of a suggestion (`suggest_road`) as it stands, under the id `road`."""
        return self.open(road, suggestion["name"], suggestion["at"], suggestion["houses"], suggestion["topic"])

    def file(self, house: str, road: str) -> dict:
        return self.event("file", {"house": house, "road": road})

    def rename(self, road: str, name: str) -> dict:
        return self.event("rename_road", {"road": road, "name": name})

    def move(self, road: str, parent: str) -> dict:
        return self.event("move_road", {"road": road, "parent": parent})

    def merge(self, road: str, name: str, members: list[str], topic: dict | None = None, parent: str | None = None) -> dict:
        return self.event("merge_roads", {"road": road, "name": name, "parent": parent, "members": members, "topic": topic})

    def take_merge(self, suggestion: dict, road: str, parent: str | None = None) -> dict:
        """Merge the roads of a suggestion (`suggest_merge`) as it stands, under the id `road` and below `parent` (None: the ring road, so avenues)."""
        return self.merge(road, suggestion["name"], suggestion["members"], suggestion["topic"], parent)

    def undo(self, seq: int | None = None) -> dict:
        return self.event("undo", {"seq": len(self.journal.events) if seq is None else seq})

    def rule(self, max_houses: int, min_houses: int, auto: bool = False, branches: int | None = None) -> dict:
        """A new rule; `branches` stays what it is unless it is given."""
        return self.event("set_rule", {"max": max_houses, "min": min_houses, "auto": auto, "branches": self.state.rule["branches"] if branches is None else branches})


def houses(first: int, last: int) -> list[str]:
    return [hid(i) for i in range(first, last + 1)]


def scripted():
    """A log in which every kind of event leaves holes in front of houses that stay: roads opened from the middle of the ring road, houses filed out of a road and out
    of the ring road, a road with roads below it moved, a rename, a rule, and an undo from the middle."""
    h = Hand()
    h.add(60)
    h.open("a", "A", None, houses(3, 20))  # holes at the front of the ring road
    h.open("b", "B", None, [hid(i) for i in range(21, 41) if i % 2])  # ... and in the middle of it
    h.add(20)
    h.file(hid(1), "a")
    h.file(hid(30), "b")  # (house 30 is on the ring road: b took the odd ones)
    h.file(hid(5), "b")  # out of a road, with houses after it
    h.open("a1", "A one", "a", houses(6, 17))
    h.rename("a", "Alpha")
    h.rule(30, 5)
    h.move("a1", "b")
    h.add(5)
    h.undo(len(h.journal.events) - 3)  # from the middle: nothing names the house it added
    h.file(hid(2), "a1")
    h.move("b", "a")
    return h


def scripted_nodes():
    """A log with OpenAlex topics, for the roads that stand for a node: a suggestion taken as it stands, a house with topics in two domains, a category with no node, the rule
    `auto` on (an arrival that lands on a road and splits it three levels down in one event, arrivals that stay on the ring road), a rename, a filing, a move of a road with a node,
    and an undo from the middle."""
    h = Hand({"max": 12, "min": 5, "auto": False})
    h.add(8, topic(1, 1, 1, 1))
    h.add(7, topic(1, 2, 1, 1))
    h.add(6, topic(2, 1, 1, 1), topic(1, 1, 1, 2))  # primary in domain 2, a second topic in domain 1
    h.add(3)
    h.take(suggest_road(h.state, None), "d1")  # domain 1: 21 houses, the six too
    h.add(5, topic(3, 1, 1, 1))
    h.open("mine", "My three", None, [hid(22), hid(23), hid(24), hid(25), hid(26)])  # a category with no node
    h.rule(12, 5, True)
    h.add(1, topic(1, 1, 1, 1))  # lands on d1 (22 houses): field 1.1 takes 15, then its subfield, then its topic 1.1.1.1 (9)
    h.add(1, topic(2, 1, 1, 1))  # no road for domain 2
    h.add(1)  # no topic
    first = next(k for k in h.state.nodes if k.startswith("auto:"))
    h.rename(first, "Field one")
    h.add(1, topic(1, 2, 1, 1))  # lands on d1 (the field 1.2 has no road)
    h.file(hid(30), "mine")
    h.add(2, topic(1, 1, 1, 2))  # topic 1.1.1.2: the road of its subfield
    leaf = next(k for k, n in h.state.nodes.items() if n["topic"] and n["topic"]["level"] == "topic")
    h.move(leaf, "mine")  # a road for a node moves, with its houses
    h.add(1, topic(1, 1, 1, 1))  # lands on it, wherever it stands now
    h.add(1, topic(3, 1, 1, 1))
    h.add(1, topic(2, 1, 1, 1))
    h.undo(len(h.journal.events) - 1)  # the arrival before the last: nothing names the house it added
    return h


def node(level: str, d: int, f: int = 1, s: int = 1, t: int = 1) -> dict:
    """The OpenAlex node of `topic(d, f, s, t)` at `level`, as a road carries it (`open_road` and `merge_roads`)."""
    return {"id": topic(d, f, s, t)[level]["id"], "level": level, "name": topic(d, f, s, t)[level]["name"]}


def scripted_merge():
    """A log in which the first ring fills and is merged: twelve avenues for fields of OpenAlex domains and one category of the player's (the ring is full), a merge by
    suggestion (the three fields of one domain, under the domain), the avenues of the next categories in the directions it freed, a merge by hand (two fields, under their
    domain), more avenues in the freed directions, a rename of a merged avenue, a house filed onto a merged field, an avenue moved below another (its direction is free
    and the next avenue takes it), and an undo from the middle."""
    h = Hand({"max": 30, "min": 5, "auto": False})
    fields = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1)]
    for k, (d, f) in enumerate(fields):
        h.add(6 + k % 3, topic(d, f, 1, 1))
        h.open(f"f{k}", f"Field {d}.{f}", None, h.state.houses_at(None), node("field", d, f))
    h.add(8)
    h.open("mine", "My collection", None, h.state.houses_at(None))  # the 13th avenue: a category with no node
    h.take_merge(suggest_merge(h.state), "d1")  # the fields of domain 1 under the domain: the new avenue holds the direction of the largest, the other two are free
    h.add(6, topic(10, 1, 1, 1))
    h.open("n1", "Field 10.1", None, h.state.houses_at(None), node("field", 10, 1))  # the 14th category: the lowest free direction
    h.merge("d2", "Domain 2", ["f3", "f4"], node("domain", 2))  # by hand
    for i, d in enumerate((11, 12), start=2):
        h.add(6, topic(d, 1, 1, 1))
        h.open(f"n{i}", f"Field {d}.1", None, h.state.houses_at(None), node("field", d, 1))
    h.rename("d1", "Domain one")
    h.add(2, topic(1, 2, 1, 1))
    h.file(hid(h.count), "f1")  # onto a field that is a road of ring 2 now
    h.move("n3", "n2")  # an avenue below another road: it is no avenue any more, and its direction is free ...
    h.add(6, topic(13, 1, 1, 1))
    h.open("n4", "Field 13.1", None, houses(h.count - 5, h.count), node("field", 13, 1))  # ... for the next one
    h.add(3)
    h.undo(len(h.journal.events) - 1)  # from the middle: nothing names the house it added
    return h


def scripted_branches():
    """A log for the branches: a ring of five (`branches` 5) on which the rule `auto` opens an avenue for each of eight domains of OpenAlex and, when the ring is full and a domain
    needs its avenue, merges two avenues first and then splits (a merge and a split of one event); the ring road renamed; two roads below a road merged by hand (a merge below a road);
    the branches raised to 8 and to 21 (the expansion: the whole world laid out again on the wider table), a larger `max` (a larger ring), the branches lowered to 8 again (the sectors
    widen), and an undo from the middle."""
    h = Hand({"max": 12, "min": 5, "auto": True, "branches": 5})
    for i in range(1, 161):  # eight domains; most items carry a second topic in another domain
        d = 1 + (i * 5) % 8
        topics = [topic(d, 1 + i % 2, 1 + i % 3, 1 + i % 2)]
        if i % 4:
            topics.append(topic(1 + (d + i % 7) % 8, 1, 1, 1))
        h.add(1, *topics)
    h.rename(None, "Inbox")
    parent = next(k for k in h.state.nodes if len(h.state.children(k)) >= 2)
    h.merge("under", "Merged below a road", h.state.children(parent)[:2], parent=parent)
    h.rule(12, 5, True, 8)
    for i in range(161, 191):
        d = 1 + (i * 3) % 8
        h.add(1, topic(d, 1 + i % 2, 1 + i % 3, 1 + i % 2), topic(1 + (d + i % 5) % 8, 1, 1, 1))
    h.rule(12, 5, True, 21)
    h.rule(120, 5, True, 21)
    h.rule(120, 5, True, 8)
    h.add(2, topic(3, 1, 1, 1))
    h.undo(len(h.journal.events) - 1)  # from the middle: nothing names the house it added
    return h


def every_entry():
    """A world whose chronicle has an entry of each kind: a road opened, a house filed, a road renamed, a road moved, avenues merged, a change of rule, a new radius of
    the ring road (a `max` that the first lap cannot hold) and an undo."""
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
    h.rule(200, 5)  # the ring road must hold 200 houses between its gates now: radius 19.5, not 12.5
    h.add(1)
    h.undo()
    return h


# ------------------------------------------------------------------------------------------ a random player ----
def play(seed: int, steps: int = 120, *, auto: bool = False, rule: dict | None = None, suggested: bool = False, arrivals: float = 0.46, merging: bool = False,
         resizing: bool = False, branches: int | None = None, below_roads: float = 0.4) -> Journal:
    """A random player: items arrive, roads open below the ring road and below roads, houses are filed, roads renamed and moved, the rule changes, events are undone.
    Every act goes through `Journal.append`; the ones the world refuses are the player's mistakes and are left out of the log. With `suggested`, a road is often opened
    as a suggestion has it (`suggest_road` at a random place: it carries its OpenAlex node), and otherwise as before: a random choice of houses, a category with no node.
    `arrivals` is the part of the steps that bring an item (0.46 by default); the other acts keep their shares of the rest. With `merging`, now and then two to four
    avenues are merged (by `suggest_merge` or at random), and with the chance `below_roads` the roads below a road instead. With `resizing`, a change of rule may ask for a `max` that the first lap of the
    ring road cannot hold and for another number of branches (the world is laid out again on the new ring road). `branches` is the number of branches the world starts with."""
    rng = random.Random(seed)
    top = rng.choice([8, 12, 20, 40])
    hand = Hand(rule or {"max": top, "min": min(top, rng.choice([3, 4, 6, 10])), "auto": auto, **({} if branches is None else {"branches": branches})})
    road_no = merge_no = 0
    for step in range(steps):
        state, r = hand.state, rng.random()
        if arrivals != 0.46:
            r = r * 0.46 / arrivals if r < arrivals else 0.46 + (r - arrivals) * 0.54 / (1 - arrivals)
        try:
            avenues = [k for k, n in state.nodes.items() if n["parent"] is None]
            parents = [None, *state.nodes]
            if merging and rng.random() < 0.08 and any(len(state.children(q)) >= 2 for q in parents):
                merge_no += 1
                below = [q for q in parents if len(state.children(q)) >= 2]
                parent = rng.choice(below if rng.random() < below_roads or len(avenues) < 2 else [None])
                members = state.children(parent)
                suggestion = suggest_merge(state, parent) if suggested and rng.random() < 0.6 else None
                if suggestion is not None:
                    hand.take_merge(suggestion, f"m{merge_no}", parent)
                elif len(members) >= 2:
                    hand.merge(f"m{merge_no}", f"Merged {merge_no}", rng.sample(members, rng.randint(2, min(4, len(members)))), parent=parent)
            elif r < 0.46 or len(state.items) < 6:
                hand.add_items([random_item(rng, hand.count + 1)])
            elif r < 0.62:  # open a road: from a place that holds enough, with a random choice of its houses
                places = [None, *state.nodes]
                rng.shuffle(places)
                taken = False
                for parent in places if suggested and rng.random() < 0.6 else ():
                    suggestion = suggest_road(state, parent)
                    if suggestion is not None:
                        road_no += 1
                        hand.take(suggestion, f"r{road_no}")
                        taken = True
                        break
                for parent in places if not taken else ():
                    held = state.houses_at(parent)
                    if len(held) >= state.rule["min"]:
                        k = rng.randint(state.rule["min"], len(held))
                        road_no += 1
                        hand.open(f"r{road_no}", f"Road {road_no}", parent, rng.sample(held, k))
                        break
            elif r < 0.76 and state.nodes:
                hand.file(rng.choice(list(state.items)), rng.choice(list(state.nodes)))
            elif r < 0.82 and state.nodes:
                hand.rename(rng.choice(list(state.nodes)), f"Name {step}")
            elif r < 0.89 and len(state.nodes) > 1:
                hand.move(rng.choice(list(state.nodes)), rng.choice(list(state.nodes)))
            elif r < 0.92:
                top = rng.choice([8, 12, 20, 40, 150, 300, 600] if resizing else [8, 12, 20, 40])
                wanted = max(state.least_branches()[0], rng.choice([2, 3, 5, 8, 13, 21, 34])) if resizing and rng.random() < 0.5 else None  # (never below what stands)
                hand.rule(top, min(top, rng.choice([2, 3, 5])), rng.choice([False, auto]), wanted)
            else:
                keep = sorted(standing(hand.journal.events))
                if keep:
                    hand.undo(rng.choice(keep[-8:]))
        except Refusal:
            pass
    return hand.journal


def journal_value(journal: Journal):
    """All that an event may change in a journal and its world, as a value (a deep copy) to compare before and after: the log, and every attribute of the State but the live tree."""
    s = journal.state
    return copy.deepcopy((journal.events, s.rule, s.nodes, s.items, s.road_of, s.held, s.kinds, s.effects, s.plan, s.doc))


# --------------------------------------------------------------------------------------- the checks of a world ----
def place_of(key: str | None) -> str:
    return ROOT if key is None else lay.tag_place(key)


def hand_problems(state: State, *, coast: bool = False) -> list:
    """What is wrong with a world built by hand, read from its document and checked against the roads and houses its State holds. Empty: sound."""
    bad = []
    doc, places = state.doc, state.doc["places"]
    found = checks.all_problems(doc)
    if found:
        bad.append(("geometry", {k: v[:3] for k, v in found.items()}))
    city = state.city(with_coast=coast)
    found = checks.document_problems(city)
    if found:
        bad.append(("document", {k: v[:3] for k, v in found.items()}))
    found = checks.ring_problems(city)
    if found:
        bad.append(("ring", found[:3]))
    lots = {p["article"]: p for p in places.values() if p["kind"] == "lot"}
    if set(lots) != set(state.items):
        bad.append(("houses", "the houses with a lot are not the houses of the world"))
    for h in state.items:
        lot = lots.get(h)
        key = state.road_of[h]
        if lot is None:
            bad.append((h, "a house with no lot"))
            continue
        if lot["street"] != place_of(key) or lot["tag"] != key:
            bad.append((h, f"stands on {lot['street']} (tag {lot['tag']!r}) but its road is {key!r}"))
        if "underground" in lot:
            bad.append((h, "a house of a world with the ring road is not underground"))
        if places[lot["parent"]].get("lane_of", lot["parent"]) != place_of(key):
            bad.append((h, "stands in a rib (or a lap) that is not of its road"))
    # the ring road: what the rule says of it (stated apart from the engine), and its laps count the houses that stand on them
    plan_ring, ring = state.plan["params"]["ring"], places[ROOT]
    gates = gates_of(state.plan)
    n = state.rule["branches"]
    table = cells_table(n)
    if ring["label"] != plan_ring["label"] or ring["address"] != [plan_ring["label"]]:
        bad.append((ROOT, "the ring road does not carry the name the plan holds"))
    if [(round(lo * 100), round(hi * 100)) for lo, hi in plan_ring["sectors"]] != [(lo, hi) for lo, hi, _ in table] or [round(a * 100) for a in plan_ring["axes"]] != [a for *_, a in table]:
        bad.append((ROOT, f"the plan does not hold the sectors and the spoke axes of the table of {n} directions"))
    if gates != sorted(set(gates)) or len(gates) != n:
        bad.append((ROOT, "the gates are not as many as the directions, or not distinct"))
    land = min(2 * min(axis - lo, hi - axis) for lo, hi, axis in table) / 100  # the narrowest LAND: an avenue builds within the narrower side of its spoke
    if ring["ring"]["gaps"] != gates or ring["ring"]["radius"] != plan_ring["radius"] or plan_ring["radius"] != radius_for(gates, state.rule["max"], land):
        bad.append((ROOT, "the ring road is not the one the rule asks for: its gates are the spoke axes of all the directions and its radius R(N) for the rule"))
    if ring["ring"]["slots"] != capacity(ring["ring"]["radius"], gates):
        bad.append((ROOT, "the ring road holds another number of houses than its cells say"))
    # the roads: every road the player opened is a node; a record, when there is one, follows the tree
    held = Counter(state.road_of.values())
    for key, node in state.nodes.items():
        place = lay.tag_place(key)
        rec = places.get(place)
        if rec is None:
            if held[key]:
                bad.append((key, "a road with houses and no street record"))
            continue
        path, cur = [], key
        while cur is not None:
            path.append(state.nodes[cur]["name"])
            cur = state.nodes[cur]["parent"]
        path.reverse()
        parent = place_of(node["parent"]) if node["parent"] is not None else lay.PLAZA_PLACE
        if rec["tag"] != key or rec["address"] != path or rec["level"] != len(path) or rec["parent"] != parent:
            bad.append((key, f"record {rec['tag']!r} {rec['address']} level {rec['level']} parent {rec['parent']} does not follow the tree {path}"))
        if (rec.get("label") or rec["address"][-1]) != node["name"]:
            bad.append((key, "the label of the record is not the name of the road"))
        carriers = ([place] if "rib" in rec else []) + list(rec.get("lanes", []))
        if sum(places[c]["lots"] for c in carriers) != held[key]:
            bad.append((key, "the lots of the ribs are not the houses of the road"))
        for lane in rec.get("lanes", []):
            if places[lane]["address"] != path or places[lane]["label"] != node["name"]:
                bad.append((lane, "a continuation does not carry the name and address of its road"))
        if (rec["shape"] == "trunk") != (node["parent"] is None):
            bad.append((key, f"a road is a trunk when and only when it is a ring-1 road, and this one is a {rec['shape']}"))
    for pid, rec in places.items():  # no street record of a road that is not in the tree
        if rec["kind"] == "street" and pid != ROOT and "lane_of" not in rec and rec.get("tag") not in state.nodes:
            bad.append((pid, "a street record of no road"))
    # the sectors of the ring-1 roads: the ones that stand, in the order they were given; each is the sector of the direction its avenue holds
    ring1 = [r for r in state.plan["ring1"] if state.nodes[r["name"]]["parent"] is None]
    want = [{"place": r["place"], "label": r["label"], "weight": r["weight"], "from": r["wedge"][0], "to": r["wedge"][1], "span": round(r["wedge"][1] - r["wedge"][0], 3), "axis": r["axis"]}
            for r in ring1]
    if doc["composition"]["ring1"] != want or city["composition"]["ring1"] != want:
        bad.append(("ring1", "composition.ring1 is not the sectors of the ring-1 roads"))
    avenues = [k for k, n in state.nodes.items() if n["parent"] is None]
    holders = list(state.held.values())
    if len(holders) != len(set(holders)) or not set(state.held) <= set(range(n)):
        bad.append(("held", "a road holds two directions, or there is a direction that is not in the table"))
    if sorted(holders) != sorted(avenues):
        bad.append(("held", "the roads that hold a direction are not the roads of the first ring"))
    for k, holder in state.held.items():
        lo, hi, axis = table[k]
        if not lo <= axis <= hi or axis % 36000 != bearing_of_direction(k):
            bad.append(("held", f"the spoke of direction {k} is not on its bearing inside its sector"))
    for r in ring1:
        k = state.direction_of(r["name"])
        if k is None or ([round(r["wedge"][0] * 100), round(r["wedge"][1] * 100), round(r["axis"] * 100)] != list(table[k])):
            bad.append((r["place"], "the sector and the axis of a ring-1 road are not those of the direction it holds"))
            continue
        lo, hi, axis = table[k]
        side = min(axis - lo, hi - axis)  # the land of an avenue: the part of its sector within the narrower side of the spoke (the engine lays lots the same distance either side)
        rec = places.get(r["place"])
        if rec is not None and ([round(v * 100) for v in rec["wedge"]] != [axis - side, axis + side] or round(rec["axis"] * 100) != axis):
            bad.append((r["place"], "the wedge of the street is not the land of its sector, or its axis is not the bearing of the direction"))
    # the lines: one for each avenue that holds a direction, and no road of any other line - an avenue that gives its direction up (it moves below a road, or is merged) takes its line
    # away, so that no ghost of it lies under the line of the next avenue of that direction
    standing = {lay.tag_place(k) for k in state.held.values()}
    if not set(doc["lines"]) <= standing:
        bad.append(("lines", f"lines of roads that hold no direction: {sorted(set(doc['lines']) - standing)}"))
    for rid, road in doc["roads"].items():
        if road["kind"] in ("spoke", "arc") and road["street"] not in standing:
            bad.append(("lines", f"{rid} is the {road['kind']} of {road['street']}, which holds no direction"))
        if road["kind"] == "lane" and road.get("trunk") not in standing:
            bad.append(("lines", f"{rid} is a lane of the line {road.get('trunk')!r}, which is no line of an avenue"))
    for parent in (None, *state.nodes):  # a road holds at most `branches` roads directly, at every level
        if len(state.children(parent)) > n:
            bad.append((parent, f"holds {len(state.children(parent))} roads directly, more than the {n} branches of the rule"))
    # the chronicle
    chron = doc["chronicle"]
    if [e["n"] for e in chron] != list(range(1, len(chron) + 1)):
        bad.append(("chronicle", "numbers are not 1..n"))
    if any(e["event_id"] is None or "at" not in e for e in chron) or [e["event_id"] for e in chron] != sorted(e["event_id"] for e in chron):
        bad.append(("chronicle", "an entry without its event or its date, or out of the order of the log"))
    if doc["districts"]["max"] != state.rule["max"] or doc["districts"]["min"] != state.rule["min"]:
        bad.append(("districts", "the document does not hold the rule in force"))
    if state.doc["mode"] != "hand" or city["world"]["mode"] != "hand":
        bad.append(("mode", "not the hand mode"))
    return bad


def text_problems(state: State) -> list:
    """The city as it is written and read again: the text parses, the reader of `picture` and `chronicle` accepts it, and a picture can be drawn."""
    from bibliopolis import picture
    from bibliopolis.city import chronicle_lines

    city = state.city()
    text = lay.render(city)
    bad = []
    try:
        read = inputs.read_city(json.loads(text))
        picture.render(read)
        chronicle_lines(read)
    except Exception as exc:  # noqa: BLE001 - whatever it is, it is a problem
        bad.append(("text", f"{type(exc).__name__}: {exc}"))
    return bad


def order_along(state: State) -> dict[str, list[str]]:
    """place -> the houses that stand on it, in the order they stand along it, read from the document of the world apart from the engine: on the ring road the laps in
    turn and on a road its ribs in turn, a slot at a time (a hole is no part of the order)."""
    places = state.doc["places"]
    out: dict[str, list[str]] = {}
    for place in (ROOT, *(lay.tag_place(k) for k in state.nodes)):
        rec = places.get(place)
        if rec is None:
            continue
        carriers = ([place] if "rib" in rec or place == ROOT else []) + list(rec.get("lanes", []))
        lots = [p for p in places.values() if p["kind"] == "lot" and p["street"] == place]
        if lots:
            out[place] = [p["article"] for p in sorted(lots, key=lambda p: (carriers.index(p["parent"]), p["slot"]))]
    return out


def radius_of(state: State) -> float:
    return state.plan["params"]["ring"]["radius"]


def ring_of(state: State) -> tuple:
    """What a new radius or a new number of directions changes in the ring road of the plan: (the radius, the number of branches)."""
    return radius_of(state), state.rule["branches"]


def ring_snapshot(state: State) -> tuple:
    """What a new radius or a new number of branches must leave as it is, read before it: (the order along each place, the road of each house, the directions held, the sector and
    the spoke axis of each avenue, the branches)."""
    return order_along(state), dict(state.road_of), dict(state.held), {r["place"]: (r["from"], r["to"], r["axis"]) for r in state.sectors()}, state.rule["branches"]


def expansion_violations(before: tuple, after: State) -> list[str]:
    """What an event that lays the world out again on another ring road must keep (docs/world.md, "A new radius"), read from the world as it was (`ring_snapshot`) and as it is
    now: every house on the road it was on, no house passed by another along its street, no avenue in another direction, no spoke turned, and the sector of an avenue narrower
    or the same when the branches grow, wider or the same when they fall."""
    order, roads, held, sectors, branches = before
    bad = []
    if dict(after.road_of) != roads:
        bad.append("a house changed road")
    if dict(after.held) != held:
        bad.append(f"the directions changed: {held} -> {dict(after.held)}")
    now = order_along(after)
    if set(now) != set(order):
        bad.append(f"the places that hold houses changed: {sorted(set(order) ^ set(now))}")
    for place, ids in order.items():
        if now.get(place) != ids:
            bad.append(f"the houses of {place} do not stand along it in the order they did")
    here = {r["place"]: (r["from"], r["to"], r["axis"]) for r in after.sectors()}
    if set(here) != set(sectors):
        bad.append(f"the avenues changed: {sorted(set(here) ^ set(sectors))}")
    for place, (lo, hi, axis) in sectors.items():
        if place not in here:
            continue
        lo2, hi2, axis2 = here[place]
        if axis2 != axis:
            bad.append(f"the spoke of {place} turned from {axis} to {axis2}")
        if after.rule["branches"] > branches and not (lo2 >= lo and hi2 <= hi):
            bad.append(f"the sector of {place} did not narrow or stay when the branches grew: {(lo, hi)} -> {(lo2, hi2)}")
        if after.rule["branches"] < branches and not (lo2 <= lo and hi2 >= hi):
            bad.append(f"the sector of {place} did not widen or stay when the branches fell: {(lo, hi)} -> {(lo2, hi2)}")
    return bad


def lot_snapshot(state: State) -> dict[str, dict]:
    """house id -> the lot as the city document shows it."""
    return {p["article"]: p for p in state.city(with_coast=False)["places"].values() if p["kind"] == "lot"}


def moved_by(event: dict, before: State) -> set[str]:
    """The houses that the event moves, read from the event and the world before it (not from the engine's own account of what it did)."""
    p = event["payload"]
    if event["kind"] == "open_road":
        return set(p["houses"])
    if event["kind"] == "file":
        return {p["house"]}
    if event["kind"] == "move_road":
        below = set(before.subtree(p["road"]))
        return {h for h in before.items if before.road_of[h] in below}
    if event["kind"] == "merge_roads":
        below = {road for m in p["members"] for road in before.subtree(m)}
        return {h for h in before.items if before.road_of[h] in below}
    return set()


def stability_violations(events: list[dict], rule: dict) -> list[str]:
    """Replay the log one event at a time: after each event that is not an undo, every house that the event did not move has the lot it had before it. An undo is
    excepted (it may re-place what came after the event it takes back): the world is folded again, and the replay goes on from there.
    Also: the roads of the houses change exactly as the event says. The one event that moves houses the payload does not name is an arrival under the rule `auto`: it
    may open roads of its own (`auto:<seq>`, `auto:<seq>.2`, ...) for groups of the place where the house landed, and then those houses (and no others) are moved, each from
    the place the road was opened from (or, when that road was split in turn, from the place the first of them was opened from) onto a road that the event opened."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        before_lots, before_roads, auto, before_nodes = lot_snapshot(state), dict(state.road_of), state.rule["auto"], set(state.nodes)
        expected = moved_by(e, state)
        kept, was_ring, chron = ring_snapshot(state), ring_of(state), len(state.doc["chronicle"])
        try:
            state.apply(e)
        except Refusal as why:
            bad.append(f"event {e['seq']} ({e['kind']}) was refused: {why}")
            return bad
        if e["kind"] == "set_rule" and ring_of(state) != was_ring:  # the one event that may put every house again: it keeps the order, the roads and the directions
            bad += [f"event {e['seq']} (set_rule) put the world out again and {why}" for why in expansion_violations(kept, state)]
            continue
        after_lots = lot_snapshot(state)
        changed = {h for h, road in before_roads.items() if state.road_of[h] != road}
        if e["kind"] == "add_item":
            new = [k for k in state.nodes if k not in before_nodes]
            if not auto and new:
                bad.append(f"event {e['seq']} (add_item) opened roads without the rule auto: {new}")
            if any(not k.startswith("auto:") for k in new):
                bad.append(f"event {e['seq']} (add_item) opened a road that is not an auto road: {new}")
            for h in changed:
                road = state.road_of[h]
                while road is not None and road in new and state.nodes[road]["parent"] in new:  # (up the roads that this event opened, to the one opened from an old place)
                    road = state.nodes[road]["parent"]
                if road not in new or state.nodes[road]["parent"] != before_roads[h]:
                    bad.append(f"event {e['seq']} (add_item) moved the house {h} from {before_roads[h]!r} to {state.road_of[h]!r}, which is not a road opened from where it stood")
            merged = {m.removeprefix("place:tag:") for entry in state.doc["chronicle"][chron:] if "merged" in entry for m in entry["members"]}  # roads the rule merged: their houses are put again
            expected = expected | changed | set(state.houses_under(sorted(merged)))
        elif e["kind"] in ("open_road", "file"):
            if changed != expected:
                bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed ^ expected)}, which it should not")
        elif changed:
            bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed)}")
        for h, lot in before_lots.items():
            if h not in expected and after_lots[h] != lot:
                bad.append(f"event {e['seq']} ({e['kind']}) moved the house {h}, which it did not move: {lot['parent']}/{lot['slot']} -> {after_lots[h]['parent']}/{after_lots[h]['slot']}")
    return bad


def expected_landing(state: State, item: dict) -> str | None:
    """Where an item that arrives stands under the rule `auto`, written out again from docs/world.md and not by asking `bibliopolis.suggest.landing`, the function that the engine asks (an
    oracle that asked it would agree with it whatever it said): of the roads whose node one of the topics of the item has, at the level of the node, the deepest; of two as deep, the one
    that the topic nearer the primary one reaches. None, the ring road, when there is none."""
    best = None
    for order, topics in enumerate(item["openalex"]):
        for depth, level in enumerate(("domain", "field", "subfield", "topic")):
            for road, node in state.nodes.items():
                if node["topic"] is not None and (node["topic"]["level"], node["topic"]["id"]) == (level, topics[level]["id"]) and (best is None or (-depth, order) < best[0]):
                    best = ((-depth, order), road)
    return None if best is None else best[1]


def landing_violations(events: list[dict], rule: dict) -> list[str]:
    """Replay the log one event at a time and check where each arrival stands under the rule `auto`: on the road `expected_landing` names in the world before it (the ring road when
    none), or on a road that the same event opened out of the place it landed on (the group of a split goes down, level by level)."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        item, auto = (e["payload"]["item"], state.rule["auto"]) if e["kind"] == "add_item" else (None, False)
        want, before_nodes = (expected_landing(state, item) if auto else None), set(state.nodes)
        state.apply(e)
        if item is None:
            continue
        road = state.road_of[item["id"]]
        while road is not None and road not in before_nodes:  # up the roads that this event opened, to the place the house landed on
            road = state.nodes[road]["parent"]
        if road != want:
            bad.append(f"event {e['seq']}: the house {item['id']} stands on {state.road_of[item['id']]!r}, which does not come of {want!r}, the road it lands on")
    return bad


def direction_violations(events: list[dict], rule: dict) -> list[str]:
    """Replay the log one event at a time and check which avenue holds which direction, from the entries the event wrote in the chronicle and the world before it (the numbers are
    worked out here, not read from the engine): a new avenue (a road opened from the ring road, by `open_road` or by the rule `auto`) takes the lowest direction that no avenue holds;
    a merge of avenues gives the new avenue the direction of the member whose sector is the widest in the table of the rule, the widths compared in whole tenths of a degree rounded
    half up (of two as wide, the one with the most houses on it and below it, then the lower number) and frees the directions of the other members; an avenue that moves below
    another road frees its direction; nothing else, a change of the rule included, changes who holds a direction. An undo is excepted: the world is folded again."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        held, before = dict(state.held), len(state.doc["chronicle"])
        table = cells_table(state.rule["branches"])
        try:
            state.apply(e)
        except Refusal as why:
            return [*bad, f"event {e['seq']} ({e['kind']}) was refused: {why}"]
        want = dict(held)
        for entry in state.doc["chronicle"][before:]:
            if "from" in entry and entry["from"] == "place:root":  # a road opened from the ring road: a new avenue
                free = [k for k in range(state.rule["branches"]) if k not in want]
                want[free[0]] = entry["to"].removeprefix("place:tag:")
            elif "moved" in entry and entry["was_below"] == "place:plaza":  # an avenue moved below another road
                del want[next(k for k, road in want.items() if road == entry["moved"].removeprefix("place:tag:"))]
            elif "merged" in entry and all(m.removeprefix("place:tag:") in want.values() for m in entry["members"]):  # a merge of avenues
                members = [m.removeprefix("place:tag:") for m in entry["members"]]
                direction = {m: next(k for k, road in want.items() if road == m) for m in members}
                size = {m: len(state.houses_below(m)) for m in members}
                width = {m: (table[direction[m]][1] - table[direction[m]][0] + 5) // 10 for m in members}  # in whole tenths of a degree, rounded half up
                took = min(members, key=lambda m: (-width[m], -size[m], direction[m]))
                for m in members:
                    del want[direction[m]]
                want[direction[took]] = entry["merged"].removeprefix("place:tag:")
        if state.held != want:
            bad.append(f"event {e['seq']} ({e['kind']}): the directions are {dict(sorted(state.held.items()))}, they should be {dict(sorted(want.items()))}")
    return bad