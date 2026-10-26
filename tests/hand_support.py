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
from bibliopolis.hand import State, fold
from bibliopolis.journal import Journal

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

    def open(self, road: str, name: str, parent: str | None, houses: list[str]) -> dict:
        return self.event("open_road", {"road": road, "name": name, "parent": parent, "houses": houses})

    def file(self, house: str, road: str) -> dict:
        return self.event("file", {"house": house, "road": road})

    def rename(self, road: str, name: str) -> dict:
        return self.event("rename_road", {"road": road, "name": name})

    def move(self, road: str, parent: str) -> dict:
        return self.event("move_road", {"road": road, "parent": parent})

    def undo(self, seq: int | None = None) -> dict:
        return self.event("undo", {"seq": len(self.journal.events) if seq is None else seq})

    def rule(self, max_houses: int, min_houses: int, auto: bool = False) -> dict:
        return self.event("set_rule", {"max": max_houses, "min": min_houses, "auto": auto})


# ------------------------------------------------------------------------------------------ a random player ----
def play(seed: int, steps: int = 120, *, auto: bool = False, rule: dict | None = None) -> Journal:
    """A random player: items arrive, roads open below the root zone and below roads, houses are filed, roads renamed and moved, the rule changes, events are undone.
    Every act goes through `Journal.append`; the ones the world refuses are the player's mistakes and are left out of the log."""
    rng = random.Random(seed)
    top = rng.choice([8, 12, 20, 40])
    hand = Hand(rule or {"max": top, "min": min(top, rng.choice([3, 4, 6, 10])), "auto": auto})
    road_no = 0
    for step in range(steps):
        state, r = hand.state, rng.random()
        try:
            if r < 0.46 or len(state.items) < 6:
                hand.add_items([random_item(rng, hand.count + 1)])
            elif r < 0.62:  # open a road: from a place that holds enough, with a random choice of its houses
                places = [None, *state.nodes]
                rng.shuffle(places)
                for parent in places:
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
    # the sectors of the ring-1 roads: the ones that stand, in the order they were given, never over one another
    ring1 = [r for r in state.plan["ring1"] if state.nodes[r["name"]]["parent"] is None]
    want = [{"place": r["place"], "label": r["label"], "weight": r["weight"], "from": r["wedge"][0], "to": r["wedge"][1], "span": round(r["wedge"][1] - r["wedge"][0], 3)}
            for r in ring1]
    if doc["composition"]["ring1"] != want or city["composition"]["ring1"] != want:
        bad.append(("ring1", "composition.ring1 is not the sectors of the ring-1 roads"))
    given = [(round(r["wedge"][0] * 100), round(r["wedge"][1] * 100)) for r in state.plan["ring1"]]
    for i, (lo, hi) in enumerate(given):
        for lo2, hi2 in given[:i]:
            if 0 < (lo - lo2) % 36000 < hi2 - lo2 or 0 < (lo2 - lo) % 36000 < hi - lo or (lo - lo2) % 36000 == 0:
                bad.append(("wedges", f"sectors {i} and an earlier one overlap"))
        if hi - lo > 4000:
            bad.append(("wedges", f"sector {i} is wider than 40 degrees"))
    for r in ring1:
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
    return set()


def stability_violations(events: list[dict], rule: dict) -> list[str]:
    """Replay the log one event at a time: after each event that is not an undo, every house that the event did not move has the lot it had before it. An undo is
    excepted (it may re-place what came after the event it takes back): the world is folded again, and the replay goes on from there.
    Also: the roads of the houses change exactly as the event says, except under `auto`, where an arrival may move the houses of a new road."""
    bad = []
    state, seen = State(rule), []
    for e in events:
        seen.append(e)
        if e["kind"] == "undo":
            state = fold(seen, rule)
            continue
        before_lots, before_roads = lot_snapshot(state), dict(state.road_of)
        expected = moved_by(e, state)
        try:
            state.apply(e)
        except Refusal as why:
            bad.append(f"event {e['seq']} ({e['kind']}) was refused: {why}")
            return bad
        after_lots = lot_snapshot(state)
        for h, lot in before_lots.items():
            if h not in expected and after_lots[h] != lot:
                bad.append(f"event {e['seq']} ({e['kind']}) moved the house {h}, which it did not move: {lot['parent']}/{lot['slot']} -> {after_lots[h]['parent']}/{after_lots[h]['slot']}")
        changed = {h for h, road in before_roads.items() if state.road_of[h] != road}
        if e["kind"] in ("open_road", "file") and changed != expected:
            bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed ^ expected)}, which it should not")
        if e["kind"] in ("rename_road", "set_rule", "move_road") and changed:
            bad.append(f"event {e['seq']} ({e['kind']}) changed the road of {sorted(changed)}")
        if e["kind"] == "add_item" and not state.rule["auto"] and changed:
            bad.append(f"event {e['seq']} (add_item) changed the road of {sorted(changed)} with the rule `auto` off")
    return bad
