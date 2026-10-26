"""The event log of a hand-built world: what an event is, which kinds there are, what each carries, and which of them count.

A world built by hand is an append-only log of events, and its city and its chronicle are the fold of that log (bibliopolis.hand). An event is

    {"seq": 7, "at": "2026-10-26T09:30:00Z", "kind": "file", "payload": {"house": "item-12", "road": "r1"}}

`seq` runs 1, 2, 3, ... in log order. Log order is arrival order: the fold reads `at` from the event and never the clock, and `at` does not have to grow.

  add_item     {item}                         an item (its metadata, and its OpenAlex topics when they are known) becomes a house in the root zone, under the town hall
  open_road    {road, name, parent, houses}   the player opens a road, a named category, below a road or (parent null) the root zone, and moves the chosen houses onto it;
                                              the place it opens from holds at least `min` houses directly and at least `min` of them are chosen
  file         {house, road}                  a house moves, from the root zone or another road, onto a road
  rename_road  {road, name}
  move_road    {road, parent}                 a road, with the roads and houses below it, stands again below another road
  undo         {seq}                          the named event no longer counts; an undo of an undo restores it
  set_rule     {max, min, auto}               the rule from here on; `auto` applies the district rule after each arrival (bibliopolis.hand)

Every check here is about the shape of one event, and is made before the world is asked. What the world refuses (a house that is not there, a road that exists
already, ...) is `Refusal`, raised by the fold.
"""

from __future__ import annotations

from .inputs import _LANE_LIKE, _Problems, _shown, _text, _whole, parse_added_at
from .plan import MAX_HOUSES, MIN_HOUSES

KINDS = ("add_item", "open_road", "file", "rename_road", "move_road", "undo", "set_rule")
ORDER = ("domain", "field", "subfield", "topic")  # the four levels of an OpenAlex topic, the widest first (the order the keys are written in)
LEVELS = ORDER[::-1]  # ... and the most specific first (the order a suggestion tries them in)
MAX_TOPICS = 3  # the primary topic of an item and up to two more
RULE_KEYS = ("max", "min", "auto")
DEFAULT_RULE = {"max": MAX_HOUSES, "min": MIN_HOUSES, "auto": False}
RULE_LIMIT = 100_000  # the largest `max`: far beyond any road, and a number that every language writes the same
AUTO_PREFIX = "auto:"  # the ids of the roads that the rule opens by itself; a player's road id never starts with it
ITEM_KEYS = ("id", "title", "authors", "year", "doi", "type", "openalex")
ITEM_REQUIRED = ("id", "title", "authors", "year", "type")
YEAR_LIMIT = 10**6
PAYLOAD_KEYS = {"add_item": ("item",), "open_road": ("road", "name", "parent", "houses"), "file": ("house", "road"), "rename_road": ("road", "name"),
                "move_road": ("road", "parent"), "undo": ("seq",), "set_rule": RULE_KEYS}


CODES = {"ring1_full": ("limit", "number")}  # the ids of the refusals that have one, with the names of their params (docs/world.md, "Refusals")


class Refusal(ValueError):
    """The world does not take this event: the message (English text) says why. The world is as it was.

    `code` is a stable id of the reason, for a page that translates the message from the id and the `params` (None for a reason that has no id yet; the ids are `CODES`).
    A refusal that is passed on with the place it came from (`within`) keeps its id and params."""

    def __init__(self, message: str, code: str | None = None, **params):
        super().__init__(message)
        self.code = code
        self.params = params

    def within(self, where: str) -> "Refusal":
        """The same refusal with `where` in front of its message (the event it came from), as a new exception: the id and the params stay."""
        return Refusal(f"{where}: {self}", self.code, **self.params)


# ------------------------------------------------------------------------------------------------------ items ----
def _count(problems: _Problems) -> int:
    return len(problems.found) + problems.more


def _keys(problems: _Problems, where: str, value: dict, required: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    """Whether `value` has every key of `required` and none beyond `allowed`; a problem for each fault."""
    missing = [k for k in required if k not in value]
    extra = [k for k in value if k not in allowed]
    if missing:
        problems.add(where, f"missing {', '.join(missing)}")
    if extra:
        problems.add(where, f"unknown {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(allowed)})")
    return not missing and not extra


def check_topics(value, where: str, problems: _Problems) -> list[dict] | None:
    """The OpenAlex topics of an item: a list of up to 3, the primary topic first, each with all four levels `{id, name}`, no topic twice."""
    if not isinstance(value, list):
        problems.add(where, f"must be a list of up to {MAX_TOPICS} topics, got {type(value).__name__}")
        return None
    start, out, seen = _count(problems), [], {}
    if len(value) > MAX_TOPICS:
        problems.add(where, f"holds {len(value)} topics; the most an item carries is {MAX_TOPICS} (its primary topic and two more)")
    for i, entry in enumerate(value[:MAX_TOPICS]):
        here = f"{where}[{i}]"
        if not isinstance(entry, dict):
            problems.add(here, "must be an object with domain, field, subfield and topic")
            continue
        if not _keys(problems, here, entry, ORDER, ORDER):
            continue
        topic = {}
        for level in ORDER:
            node = entry[level]
            if not isinstance(node, dict):
                problems.add(f"{here}.{level}", "must be an object {id, name}")
                continue
            if not _keys(problems, f"{here}.{level}", node, ("id", "name"), ("id", "name")):
                continue
            ok = _text(problems, f"{here}.{level}.id", node["id"], plain=True)
            ok = _text(problems, f"{here}.{level}.name", node["name"], plain=True) and ok
            if ok:
                topic[level] = {"id": node["id"], "name": node["name"]}
        if len(topic) == len(ORDER):
            tid = topic["topic"]["id"]
            if tid in seen:
                problems.add(f"{here}.topic.id", f"{tid!r} is the topic of {where}[{seen[tid]}] already")
            else:
                seen[tid] = i
            out.append(topic)
    return out if _count(problems) == start else None


def check_item(item, where: str, problems: _Problems) -> dict | None:
    """The metadata of an item as a world keeps it, or None with the problems added. `id`, `title`, `authors`, `year` (a whole number or null) and `type` are
    there; `doi` (null when it has none) and `openalex` (the topics, none when unknown) may be left out. Any other key is refused, so that nothing is dropped
    in silence. The result has every key, in the order of ITEM_KEYS."""
    if not isinstance(item, dict):
        problems.add(where, f"must be an object, got {type(item).__name__}")
        return None
    start = _count(problems)
    if not _keys(problems, where, item, ITEM_REQUIRED, ITEM_KEYS):
        return None
    _text(problems, f"{where}.id", item["id"], plain=True)
    _text(problems, f"{where}.title", item["title"], nonempty=False)
    _text(problems, f"{where}.type", item["type"])
    authors = item["authors"]
    if not isinstance(authors, list):
        problems.add(f"{where}.authors", f"must be a list of strings, got {type(authors).__name__}")
    else:
        for j, name in enumerate(authors):
            _text(problems, f"{where}.authors[{j}]", name, nonempty=False)
    year = item["year"]
    if year is not None and (not _whole(year) or abs(year) > YEAR_LIMIT):
        problems.add(f"{where}.year", f"must be a whole number (at most {YEAR_LIMIT} either way) or null, got {_shown(year)}")
    doi = item.get("doi")
    if doi is not None:
        _text(problems, f"{where}.doi", doi)
    topics = check_topics(item.get("openalex", []), f"{where}.openalex", problems)
    if _count(problems) != start or topics is None:
        return None
    return {"id": item["id"], "title": item["title"], "authors": list(authors), "year": year, "doi": doi, "type": item["type"], "openalex": topics}


# ------------------------------------------------------------------------------------------------------ rules ----
def check_rule(rule, where: str, problems: _Problems) -> dict | None:
    """A rule `{max, min, auto}`: whole numbers 1 <= min <= max, and a boolean."""
    if not isinstance(rule, dict):
        problems.add(where, f"must be an object {{max, min, auto}}, got {type(rule).__name__}")
        return None
    start = _count(problems)
    if not _keys(problems, where, rule, RULE_KEYS, RULE_KEYS):
        return None
    for name in ("max", "min"):
        if not _whole(rule[name]) or not 1 <= rule[name] <= RULE_LIMIT:
            problems.add(f"{where}.{name}", f"must be a whole number from 1 to {RULE_LIMIT}, got {_shown(rule[name])}")
    if not isinstance(rule["auto"], bool):
        problems.add(f"{where}.auto", f"must be true or false, got {_shown(rule['auto'])}")
    if _count(problems) == start and rule["min"] > rule["max"]:
        problems.add(where, f"min ({rule['min']}) is more than max ({rule['max']})")
    return {k: rule[k] for k in RULE_KEYS} if _count(problems) == start else None


# ----------------------------------------------------------------------------------------------------- events ----
def _road_id(problems: _Problems, where: str, value, *, new: bool = False) -> bool:
    """A road id: text without control characters. A new road may not look like the id of a continuation rib (lane:<id>:<n>) nor start with `auto:`."""
    if not _text(problems, where, value, plain=True):
        return False
    if new and _LANE_LIKE.match(value):
        problems.add(where, f"{value!r} looks like the block key of a continuation rib (lane:<id>:<n>); use another id")
        return False
    if new and value.startswith(AUTO_PREFIX):
        problems.add(where, f"{value!r} starts with {AUTO_PREFIX!r}, which is for the roads that the rule opens by itself")
        return False
    return True


def _payload(kind: str, payload, where: str, problems: _Problems) -> dict | None:
    if not isinstance(payload, dict):
        problems.add(where, f"must be an object, got {type(payload).__name__}")
        return None
    keys = PAYLOAD_KEYS[kind]
    start = _count(problems)
    if not _keys(problems, where, payload, keys, keys):
        return None
    if kind == "add_item":
        item = check_item(payload["item"], f"{where}.item", problems)
        return {"item": item} if item is not None else None
    if kind == "set_rule":
        return check_rule(payload, where, problems)
    if kind == "undo":
        if not _whole(payload["seq"]) or payload["seq"] < 1:
            problems.add(f"{where}.seq", f"must be the number of an event (1 or more), got {_shown(payload['seq'])}")
    elif kind == "open_road":
        _road_id(problems, f"{where}.road", payload["road"], new=True)
        _text(problems, f"{where}.name", payload["name"], plain=True)
        if payload["parent"] is not None:
            _road_id(problems, f"{where}.parent", payload["parent"])
        houses = payload["houses"]
        if not isinstance(houses, list) or not houses:
            problems.add(f"{where}.houses", "must be a list of house ids, not empty")
        else:
            for j, h in enumerate(houses):
                if _text(problems, f"{where}.houses[{j}]", h, plain=True) and h in houses[:j]:
                    problems.add(f"{where}.houses[{j}]", f"{h!r} is chosen twice")
    elif kind == "file":
        _text(problems, f"{where}.house", payload["house"], plain=True)
        _road_id(problems, f"{where}.road", payload["road"])
    elif kind == "rename_road":
        _road_id(problems, f"{where}.road", payload["road"])
        _text(problems, f"{where}.name", payload["name"], plain=True)
    elif kind == "move_road":
        _road_id(problems, f"{where}.road", payload["road"])
        _road_id(problems, f"{where}.parent", payload["parent"])
    return {k: payload[k] for k in keys} if _count(problems) == start else None


def check_event(event, where: str, problems: _Problems) -> dict | None:
    """One event as the log keeps it (keys in the order seq, at, kind, payload; the payload in the order of its kind), or None with the problems added."""
    if not isinstance(event, dict):
        problems.add(where, f"must be an object, got {type(event).__name__}")
        return None
    start = _count(problems)
    if not _keys(problems, where, event, ("seq", "at", "kind", "payload"), ("seq", "at", "kind", "payload")):
        return None
    if not _whole(event["seq"]) or event["seq"] < 1:
        problems.add(f"{where}.seq", f"must be a whole number, 1 or more, got {_shown(event['seq'])}")
    if _text(problems, f"{where}.at", event["at"]):
        try:
            parse_added_at(event["at"])
        except (ValueError, OverflowError):
            problems.add(f"{where}.at", f"{event['at']!r} is not an ISO 8601 date or date and time")
    kind = event["kind"]
    if kind not in KINDS:
        problems.add(f"{where}.kind", f"{_shown(kind)} is not a kind of event ({', '.join(KINDS)})")
        return None
    payload = _payload(kind, event["payload"], f"{where}.payload", problems)
    if _count(problems) != start or payload is None:
        return None
    return {"seq": event["seq"], "at": event["at"], "kind": kind, "payload": payload}


def standing(events: list[dict]) -> set[int]:
    """The `seq` of the events that count: those that no standing undo names. An undo may name an earlier event only, so the last event is settled first and
    each earlier one from the undos after it; an undo of an undo gives the first one back."""
    named: dict[int, list[int]] = {}
    for e in events:
        if e["kind"] == "undo":
            named.setdefault(e["payload"]["seq"], []).append(e["seq"])
    counts: dict[int, bool] = {}
    for e in reversed(events):
        counts[e["seq"]] = not any(counts.get(u, False) for u in named.get(e["seq"], ()))
    return {seq for seq, yes in counts.items() if yes}


def references(event: dict) -> tuple[set[str], set[str]]:
    """(the roads, the houses) that an event names in its payload, other than the road it creates: what a later event can depend on."""
    p = event["payload"]
    kind = event["kind"]
    if kind == "open_road":
        return ({p["parent"]} if p["parent"] is not None else set()), set(p["houses"])
    if kind == "file":
        return {p["road"]}, {p["house"]}
    if kind == "rename_road":
        return {p["road"]}, set()
    if kind == "move_road":
        return {p["road"], p["parent"]}, set()
    return set(), set()
