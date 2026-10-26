"""Worlds built by hand for the tests: invented items with invented OpenAlex-shaped topics, a clock that counts, a random player, and the checks of a hand-built
world (the geometry and bookkeeping of the engine, the roads and houses it must agree with, the stability of the lots).

Nothing here is an identifier of a real database: the topics are `ex:d1.f2.s3.t4` and the names `Domain 1`, `Field 1.2`, ... Not collected by pytest (the name has no
test_ prefix)."""

import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

import checks

from bibliopolis import inputs
from bibliopolis import layout as lay
from bibliopolis import world as zw
from bibliopolis.events import Refusal, standing
from bibliopolis.hand import SECTORS, State, bearing, fold
from bibliopolis.journal import Journal
from bibliopolis.suggest import landing, suggest_merge, suggest_road

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

    def merge(self, road: str, name: str, members: list[str], topic: dict | None = None) -> dict:
        return self.event("merge_roads", {"road": road, "name": name, "parent": None, "members": members, "topic": topic})

    def take_merge(self, suggestion: dict, road: str) -> dict:
        """Merge the avenues of a suggestion (`suggest_merge`) as it stands, under the id `road`."""
        return self.merge(road, suggestion["name"], suggestion["members"], suggestion["topic"])

    def undo(self, seq: int | None = None) -> dict:
        return self.event("undo", {"seq": len(self.journal.events) if seq is None else seq})

    def rule(self, max_houses: int, min_houses: int, auto: bool = False) -> dict:
        return self.event("set_rule", {"max": max_houses, "min": min_houses, "auto": auto})


def houses(first: int, last: int) -> list[str]:
    return [hid(i) for i in range(first, last + 1)]


def scripted():
    """A log in which every kind of event leaves holes in front of houses that stay: roads opened from the middle of the root zone, houses filed out of a road and out
    of the root zone, a road with roads below it moved, a rename, a rule, and an undo from the middle."""
    h = Hand()
    h.add(60)
    h.open("a", "A", None, houses(3, 20))  # holes at the front of the root zone
    h.open("b", "B", None, [hid(i) for i in range(21, 41) if i % 2])  # ... and in the middle of it
    h.add(20)
    h.file(hid(1), "a")
    h.file(hid(30), "b")  # (house 30 is in the root zone: b took the odd ones)
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
    `auto` on (an arrival that lands on a road and splits it three levels down in one event, arrivals that stay underground), a rename, a filing, a move of a road with a node,
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


def every_entry():
    """A world whose chronicle has an entry of each kind: a road opened, a house filed, a road renamed, a road moved, avenues merged, a change of rule and an undo."""
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
    h.add(1)
    h.undo()
    return h


# ------------------------------------------------------------------------------------------ a random player ----
def play(seed: int, steps: int = 120, *, auto: bool = False, rule: dict | None = None, suggested: bool = False, arrivals: float = 0.46, merging: bool = False) -> Journal:
    """A random player: items arrive, roads open below the root zone and below roads, houses are filed, roads renamed and moved, the rule changes, events are undone.
    Every act goes through `Journal.append`; the ones the world refuses are the player's mistakes and are left out of the log. With `suggested`, a road is often opened
    as a suggestion has it (`suggest_road` at a random place: it carries its OpenAlex node), and otherwise as before: a random choice of houses, a category with no node.
    `arrivals` is the part of the steps that bring an item (0.46 by default); the other acts keep their shares of the rest. With `merging`, now and then two to four
    avenues are merged (by `suggest_merge` or at random)."""
    rng = random.Random(seed)
    top = rng.choice([8, 12, 20, 40])
    hand = Hand(rule or {"max": top, "min": min(top, rng.choice([3, 4, 6, 10])), "auto": auto})
    road_no = merge_no = 0
    for step in range(steps):
        state, r = hand.state, rng.random()
        if arrivals != 0.46:
            r = r * 0.46 / arrivals if r < arrivals else 0.46 + (r - arrivals) * 0.54 / (1 - arrivals)
        try:
            avenues = [k for k, n in state.nodes.items() if n["parent"] is None]
            if merging and len(avenues) >= 2 and rng.random() < 0.08:
                merge_no += 1
                suggestion = suggest_merge(state) if suggested and rng.random() < 0.6 else None
                if suggestion is not None:
                    hand.take_merge(suggestion, f"m{merge_no}")
                else:
                    hand.merge(f"m{merge_no}", f"Merged {merge_no}", rng.sample(avenues, rng.randint(2, min(4, len(avenues)))))
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
                top = rng.choice([8, 12, 20, 40])
                hand.rule(top, min(top, rng.choice([2, 3, 5])), rng.choice([False, auto]))
            else:
                keep = sorted(standing(hand.journal.events))
                if keep:
                    hand.undo(rng.choice(keep[-8:]))
        except Refusal:
            pass
    return hand.journal


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
        if bool(lot.get("underground")) != (key is None):
            bad.append((h, "underground when and only when it is in the root zone"))
        if key is not None and places[lot["parent"]].get("lane_of", lot["parent"]) != place_of(key):
            bad.append((h, "stands in a rib that is not of its road"))
    under = sorted((p for p in lots.values() if p["street"] == ROOT), key=lambda p: p["slot"])
    if len({p["slot"] for p in under}) != len(under):
        bad.append((ROOT, "two houses in one slot"))
    for p in under:
        x, z = zw.underground_cell(p["slot"])
        if (p["position"]["x"], p["position"]["z"]) != (x, z) or p["order"] != p["slot"]:
            bad.append((p["article"], "an underground house is not on the cell of its slot"))
    if ROOT in places and places[ROOT]["lots"] != len(under):
        bad.append((ROOT, "the counter of the root zone"))
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
    want = [{"place": r["place"], "label": r["label"], "weight": r["weight"], "from": r["wedge"][0], "to": r["wedge"][1], "span": round(r["wedge"][1] - r["wedge"][0], 3)}
            for r in ring1]
    if doc["composition"]["ring1"] != want or city["composition"]["ring1"] != want:
        bad.append(("ring1", "composition.ring1 is not the sectors of the ring-1 roads"))
    avenues = [k for k, n in state.nodes.items() if n["parent"] is None]
    holders = list(state.held.values())
    if len(holders) != len(set(holders)) or not set(state.held) <= set(range(len(SECTORS))):
        bad.append(("held", "a road holds two directions, or there is a direction that is not in the table"))
    if sorted(holders) != sorted(avenues):
        bad.append(("held", "the roads that hold a direction are not the roads of the first ring"))
    for k, holder in state.held.items():
        lo, hi = SECTORS[k]
        if not lo <= bearing(k) <= hi and not lo <= bearing(k) - 36000 <= hi:
            bad.append(("held", f"the bearing of direction {k} is not in its sector"))
    for r in ring1:
        k = state.direction_of(r["name"])
        if k is None or [round(r["wedge"][0] * 100), round(r["wedge"][1] * 100)] != list(SECTORS[k]):
            bad.append((r["place"], "the sector of a ring-1 road is not the sector of the direction it holds"))
        rec = places.get(r["place"])
        if rec is not None and rec["wedge"] != r["wedge"]:
            bad.append((r["place"], "the wedge of the street is not its sector"))
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
        try:
            state.apply(e)
        except Refusal as why:
            bad.append(f"event {e['seq']} ({e['kind']}) was refused: {why}")
            return bad
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
            expected = expected | changed
        elif e["kind"] in ("open_road", "file"):
            if changed != expected:
                bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed ^ expected)}, which it should not")
        elif changed:
            bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed)}")
        for h, lot in before_lots.items():
            if h not in expected and after_lots[h] != lot:
                bad.append(f"event {e['seq']} ({e['kind']}) moved the house {h}, which it did not move: {lot['parent']}/{lot['slot']} -> {after_lots[h]['parent']}/{after_lots[h]['slot']}")
    return bad


def landing_violations(events: list[dict], rule: dict) -> list[str]:
    """Replay the log one event at a time and check where each arrival stands under the rule `auto`: on the road `bibliopolis.suggest.landing` names in the world before it
    (the root zone when none), or on a road that the same event opened out of the place it landed on (the group of a split goes down, level by level)."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        item, auto = (e["payload"]["item"], state.rule["auto"]) if e["kind"] == "add_item" else (None, False)
        want, before_nodes = (landing(state, item) if auto else None), set(state.nodes)
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
    """Replay the log one event at a time and check which avenue holds which direction, from the event and the world before it (not from what the engine says): a new
    avenue (an `open_road` below the town hall, an avenue that the rule `auto` opens, in the order it opens them) takes the lowest direction that no avenue holds; a merge
    gives the new avenue the direction of the member whose sector is the widest (of two as wide, the one with the most houses on it and below it, then the lower number) and
    frees the directions of the other members; an avenue that moves below another road frees its direction; no other event changes who holds a direction. An undo is
    excepted: the world is folded again."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        held, before_nodes = dict(state.held), list(state.nodes)
        free = [k for k in range(len(SECTORS)) if k not in held]
        want, p = dict(held), e["payload"]
        if e["kind"] == "open_road" and p["parent"] is None:
            want[free[0]] = p["road"]
        elif e["kind"] == "move_road" and state.nodes[p["road"]]["parent"] is None:
            del want[next(k for k, road in held.items() if road == p["road"])]
        elif e["kind"] == "merge_roads":
            direction = {m: next(k for k, road in held.items() if road == m) for m in p["members"]}
            size = {m: sum(1 for h in state.items if state.road_of[h] in set(state.subtree(m))) for m in p["members"]}
            width = {m: SECTORS[direction[m]][1] - SECTORS[direction[m]][0] for m in p["members"]}
            took = min(p["members"], key=lambda m: (-width[m], -size[m], direction[m]))
            for m in p["members"]:
                del want[direction[m]]
            want[direction[took]] = p["road"]
        try:
            state.apply(e)
        except Refusal as why:
            return [*bad, f"event {e['seq']} ({e['kind']}) was refused: {why}"]
        if e["kind"] == "add_item":
            roots = [k for k in state.nodes if k not in before_nodes and state.nodes[k]["parent"] is None]
            want.update(zip(free, roots))
        if state.held != want:
            bad.append(f"event {e['seq']} ({e['kind']}): the directions are {dict(sorted(state.held.items()))}, they should be {dict(sorted(want.items()))}")
    return bad
