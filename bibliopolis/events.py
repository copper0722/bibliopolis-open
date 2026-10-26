"""The event log of a hand-built world: what an event is, which kinds there are, what each carries, and which of them count.

A world built by hand is an append-only log of events, and its city and its chronicle are the fold of that log (bibliopolis.hand). An event is

    {"seq": 7, "at": "2026-10-26T09:30:00Z", "kind": "file", "payload": {"house": "item-12", "road": "r1"}}

`seq` runs 1, 2, 3, ... in log order. Log order is arrival order: the fold reads `at` from the event and never the clock, and `at` does not have to grow.

  add_item     {item}                         an item (its metadata, and its OpenAlex topics when they are known) becomes a house in the root zone, under the town hall
  open_road    {road, name, parent, houses, topic}
                                              the player opens a road, a named category, below a road or (parent null) the root zone, and moves the chosen houses onto it;
                                              the place it opens from holds at least `min` houses directly and at least `min` of them are chosen. `topic` is the OpenAlex
                                              node the road stands for, `{id, level, name}` (a suggestion carries one), or null for a category the player named; it may be left out
  file         {house, road}                  a house moves, from the root zone or another road, onto a road
  rename_road  {road, name}
  move_road    {road, parent}                 a road, with the roads and houses below it, stands again below another road
  merge_roads  {road, name, parent, members, topic}
                                              a full first ring is the moment to group upward: a new avenue (a road of the first ring; `parent` is null, the town hall)
                                              takes the direction of the member with the widest sector among the `members`, avenues of the first ring, and they stand below it
                                              as roads of the second ring, with the roads and houses below them; the directions of the other members are free again. `topic` as for open_road
  undo         {seq}                          the named event no longer counts; an undo of an undo restores it
  set_rule     {max, min, auto}               the rule from here on; `auto` applies the district rule after each arrival (bibliopolis.hand)

Every check here is about the shape of one event, and is made before the world is asked. What the world refuses (a house that is not there, a road that exists
already, ...) is `Refusal`, raised by the fold. Every refusal, every problem of shape and every error of a world file has an id and params (`CODES`, `Refusal`), so
that a page can translate it into any language without reading the English text.
"""

from __future__ import annotations

from .inputs import _CONTROL, _LANE_LIKE, MAX_PROBLEMS, _Problems, _shown, _whole, parse_added_at
from .plan import MAX_HOUSES, MIN_HOUSES

KINDS = ("add_item", "open_road", "file", "rename_road", "move_road", "merge_roads", "undo", "set_rule")
ORDER = ("domain", "field", "subfield", "topic")  # the four levels of an OpenAlex topic, the widest first (the order the keys are written in)
LEVELS = ORDER[::-1]  # ... and the most specific first (the order a filing suggestion scores them in)
MAX_TOPICS = 3  # the primary topic of an item and up to two more
RULE_KEYS = ("max", "min", "auto")
DEFAULT_RULE = {"max": MAX_HOUSES, "min": MIN_HOUSES, "auto": False}
RULE_LIMIT = 100_000  # the largest `max`: far beyond any road, and a number that every language writes the same
AUTO_PREFIX = "auto:"  # the ids of the roads that the rule opens by itself; a player's road id never starts with it
ITEM_KEYS = ("id", "title", "authors", "year", "doi", "type", "openalex")
ITEM_REQUIRED = ("id", "title", "authors", "year", "type")
YEAR_LIMIT = 10**6
PAYLOAD_KEYS = {"add_item": ("item",), "open_road": ("road", "name", "parent", "houses", "topic"), "file": ("house", "road"), "rename_road": ("road", "name"),
                "move_road": ("road", "parent"), "merge_roads": ("road", "name", "parent", "members", "topic"), "undo": ("seq",), "set_rule": RULE_KEYS}
OPTIONAL_KEYS = {"open_road": ("topic",), "merge_roads": ("topic",)}  # left out, they are null (the event is kept with every key, in the order of PAYLOAD_KEYS)
MERGE_LEAST = 2  # the fewest avenues a merge takes
NODE_KEYS = ("id", "level", "name")  # the OpenAlex node a road carries: the id of the node, its level (one of ORDER) and its name

# The ids of every refusal, problem of shape and error of a world file, with the names of their params: the one list (docs/world.md, "Refusals" says when each comes).
# A page translates from the id and the params. A place is a road id, or None for the root zone; a `got` is the name of a type or a short text of the value.
CODES = {
    # ---- the world refuses an event (Refusal)
    "ring1_full": ("limit", "number", "remedy"),
    "house_exists": ("house",),
    "not_a_house": ("house",),
    "road_exists": ("road",),
    "no_road": ("road",),
    "parent_missing": ("parent",),
    "move_parent_missing": ("parent",),
    "too_few_here": ("road", "held", "least"),
    "too_few_chosen": ("chosen", "least"),
    "house_elsewhere": ("house", "road", "on"),
    "node_taken": ("level", "topic", "road"),
    "house_not_under_node": ("house", "level", "topic"),
    "not_an_avenue": ("road",),
    "already_there": ("house", "road"),
    "same_name": ("road", "name"),
    "move_into_itself": ("road", "parent"),
    "already_below": ("road", "parent"),
    "rule_unchanged": ("max", "min", "auto"),
    # ---- an undo is refused
    "undo_not_earlier": ("target", "seq"),
    "undo_not_counting": ("target",),
    "undo_depends": ("target", "later", "kind"),
    "undo_unfoldable": ("target", "later", "kind", "cause", "cause_params"),
    # ---- a log or a store is not taken
    "event_out_of_place": ("seq", "place"),
    "world_exists": ("path",),
    "not_next_event": ("path", "held", "next", "seq"),
    # ---- the shape of an event, a rule or a world file is wrong: `invalid` holds the problems, each `{where, code, params}` with one of the codes that follow
    "invalid": ("problems", "more"),
    "keys_missing": ("keys",),
    "keys_unknown": ("keys", "allowed"),
    "not_an_object": ("got",),
    "not_a_list": ("got",),
    "not_text": ("got",),
    "text_empty": (),
    "text_not_utf8": (),
    "text_control": (),
    "authors_not_a_list": ("got",),
    "year_bad": ("limit", "got"),
    "topics_not_a_list": ("max", "got"),
    "topics_too_many": ("count", "max"),
    "topic_not_an_object": (),
    "level_not_an_object": (),
    "topic_twice": ("topic", "first"),
    "rule_not_an_object": ("got",),
    "rule_number_bad": ("name", "limit", "got"),
    "not_a_boolean": ("got",),
    "rule_min_over_max": ("min", "max"),
    "road_id_lane_like": ("road",),
    "road_id_reserved": ("road", "prefix"),
    "undo_seq_bad": ("got",),
    "houses_empty": (),
    "house_chosen_twice": ("house",),
    "node_not_an_object": ("got",),
    "node_level_bad": ("got", "levels"),
    "members_too_few": ("count", "least"),
    "member_chosen_twice": ("road",),
    "parent_not_root": ("got",),
    "event_seq_bad": ("got",),
    "date_bad": ("at",),
    "kind_unknown": ("kind", "kinds"),
    # ---- a world file or a store is not a world (WorldFileError)
    "not_a_world_file": ("got",),
    "file_keys": ("missing", "unknown", "expected"),
    "format_wrong": ("format", "expected"),
    "version_wrong": ("version", "expected"),
    "events_not_numbered": ("index", "seq", "expected"),
    "items_differ": ("index", "derived", "given"),
    "no_world": ("path",),
    "not_a_world": ("path", "reason"),
    "world_table_wrong": ("path", "format", "version"),
    "row_not_json": ("path", "reason"),
    "item_table_differs": ("path",),
}


class Coded:
    """What a refusal and an error of a world file share: the message (English text) and, for a page that translates it, an id and the values the message is made of.

    `code` is the id (one of `CODES`) and `params` its values, in the names `CODES` gives, all of them plain JSON values. `event` is `{seq, kind}` when the reason is about an event
    of a log that was replayed or folded, and `where` the file, or the place in a file, when it is about one. `as_dict()` is all of it as a JSON object."""

    def __init__(self, message: str, code: str, **params):
        super().__init__(message)
        self.code = code
        self.params = params
        self.event: dict | None = None
        self.where: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "params": self.params, "event": self.event, "where": self.where, "message": str(self)}


class Refusal(Coded, ValueError):
    """The world does not take this event: the message says why, the id and the params say it for a page. The world is as it was."""

    def within(self, seq: int, kind: str) -> "Refusal":
        """The same refusal as a new exception that says which event of a log it is about: `event 7 (file): ...`, with `event` set. The id and the params stay."""
        out = Refusal(f"event {seq} ({kind}): {self}", self.code, **self.params)
        out.event, out.where = {"seq": seq, "kind": kind}, self.where
        return out


class Problems(_Problems):
    """The problems of the shape of a document, as `_Problems` keeps them (English lines in `found`) and with an id and params each (`items`: `{where, code, params}`)."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict] = []

    def add(self, where: str, what: str, code: str, **params) -> None:  # type: ignore[override]
        if len(self.found) < MAX_PROBLEMS:
            self.items.append({"where": where, "code": code, "params": params})
        super().add(where, what)


def text(problems: Problems, where: str, value, *, nonempty: bool = True, plain: bool = False) -> bool:
    """Whether `value` is a string that can be written as UTF-8; `nonempty` refuses text of white space only and `plain` also control characters (ids and names are written into
    place ids). The same checks as the readers of the library and the tree, with an id for each fault."""
    if not isinstance(value, str):
        problems.add(where, f"must be a string, got {type(value).__name__}", "not_text", got=type(value).__name__)
        return False
    if nonempty and not value.strip():
        problems.add(where, "must not be empty", "text_empty")
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        problems.add(where, "contains a character that cannot be written as UTF-8 (a lone surrogate)", "text_not_utf8")
        return False
    if plain and _CONTROL.search(value):
        problems.add(where, "must not contain control characters", "text_control")
        return False
    return True


# ------------------------------------------------------------------------------------------------------ items ----
def _count(problems: Problems) -> int:
    return len(problems.found) + problems.more


def _keys(problems: Problems, where: str, value: dict, required: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    """Whether `value` has every key of `required` and none beyond `allowed`; a problem for each fault."""
    missing = [k for k in required if k not in value]
    extra = [k for k in value if k not in allowed]
    if missing:
        problems.add(where, f"missing {', '.join(missing)}", "keys_missing", keys=missing)
    if extra:
        problems.add(where, f"unknown {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(allowed)})", "keys_unknown", keys=sorted(map(str, extra)), allowed=list(allowed))
    return not missing and not extra


def check_topics(value, where: str, problems: Problems) -> list[dict] | None:
    """The OpenAlex topics of an item: a list of up to 3, the primary topic first, each with all four levels `{id, name}`, no topic twice."""
    if not isinstance(value, list):
        problems.add(where, f"must be a list of up to {MAX_TOPICS} topics, got {type(value).__name__}", "topics_not_a_list", max=MAX_TOPICS, got=type(value).__name__)
        return None
    start, out, seen = _count(problems), [], {}
    if len(value) > MAX_TOPICS:
        problems.add(where, f"holds {len(value)} topics; the most an item carries is {MAX_TOPICS} (its primary topic and two more)", "topics_too_many",
                     count=len(value), max=MAX_TOPICS)
    for i, entry in enumerate(value[:MAX_TOPICS]):
        here = f"{where}[{i}]"
        if not isinstance(entry, dict):
            problems.add(here, "must be an object with domain, field, subfield and topic", "topic_not_an_object")
            continue
        if not _keys(problems, here, entry, ORDER, ORDER):
            continue
        topic = {}
        for level in ORDER:
            node = entry[level]
            if not isinstance(node, dict):
                problems.add(f"{here}.{level}", "must be an object {id, name}", "level_not_an_object")
                continue
            if not _keys(problems, f"{here}.{level}", node, ("id", "name"), ("id", "name")):
                continue
            ok = text(problems, f"{here}.{level}.id", node["id"], plain=True)
            ok = text(problems, f"{here}.{level}.name", node["name"], plain=True) and ok
            if ok:
                topic[level] = {"id": node["id"], "name": node["name"]}
        if len(topic) == len(ORDER):
            tid = topic["topic"]["id"]
            if tid in seen:
                problems.add(f"{here}.topic.id", f"{tid!r} is the topic of {where}[{seen[tid]}] already", "topic_twice", topic=tid, first=seen[tid])
            else:
                seen[tid] = i
            out.append(topic)
    return out if _count(problems) == start else None


def check_item(item, where: str, problems: Problems) -> dict | None:
    """The metadata of an item as a world keeps it, or None with the problems added. `id`, `title`, `authors`, `year` (a whole number or null) and `type` are
    there; `doi` (null when it has none) and `openalex` (the topics, none when unknown) may be left out. Any other key is refused, so that nothing is dropped
    in silence. The result has every key, in the order of ITEM_KEYS."""
    if not isinstance(item, dict):
        problems.add(where, f"must be an object, got {type(item).__name__}", "not_an_object", got=type(item).__name__)
        return None
    start = _count(problems)
    if not _keys(problems, where, item, ITEM_REQUIRED, ITEM_KEYS):
        return None
    text(problems, f"{where}.id", item["id"], plain=True)
    text(problems, f"{where}.title", item["title"], nonempty=False)
    text(problems, f"{where}.type", item["type"])
    authors = item["authors"]
    if not isinstance(authors, list):
        problems.add(f"{where}.authors", f"must be a list of strings, got {type(authors).__name__}", "authors_not_a_list", got=type(authors).__name__)
    else:
        for j, name in enumerate(authors):
            text(problems, f"{where}.authors[{j}]", name, nonempty=False)
    year = item["year"]
    if year is not None and (not _whole(year) or abs(year) > YEAR_LIMIT):
        problems.add(f"{where}.year", f"must be a whole number (at most {YEAR_LIMIT} either way) or null, got {_shown(year)}", "year_bad", limit=YEAR_LIMIT, got=_shown(year))
    doi = item.get("doi")
    if doi is not None:
        text(problems, f"{where}.doi", doi)
    topics = check_topics(item.get("openalex", []), f"{where}.openalex", problems)
    if _count(problems) != start or topics is None:
        return None
    return {"id": item["id"], "title": item["title"], "authors": list(authors), "year": year, "doi": doi, "type": item["type"], "openalex": topics}


# ------------------------------------------------------------------------------------------------------ rules ----
def check_rule(rule, where: str, problems: Problems) -> dict | None:
    """A rule `{max, min, auto}`: whole numbers 1 <= min <= max, and a boolean."""
    if not isinstance(rule, dict):
        problems.add(where, f"must be an object {{max, min, auto}}, got {type(rule).__name__}", "rule_not_an_object", got=type(rule).__name__)
        return None
    start = _count(problems)
    if not _keys(problems, where, rule, RULE_KEYS, RULE_KEYS):
        return None
    for name in ("max", "min"):
        if not _whole(rule[name]) or not 1 <= rule[name] <= RULE_LIMIT:
            problems.add(f"{where}.{name}", f"must be a whole number from 1 to {RULE_LIMIT}, got {_shown(rule[name])}", "rule_number_bad",
                         name=name, limit=RULE_LIMIT, got=_shown(rule[name]))
    if not isinstance(rule["auto"], bool):
        problems.add(f"{where}.auto", f"must be true or false, got {_shown(rule['auto'])}", "not_a_boolean", got=_shown(rule["auto"]))
    if _count(problems) == start and rule["min"] > rule["max"]:
        problems.add(where, f"min ({rule['min']}) is more than max ({rule['max']})", "rule_min_over_max", min=rule["min"], max=rule["max"])
    return {k: rule[k] for k in RULE_KEYS} if _count(problems) == start else None


# ----------------------------------------------------------------------------------------------------- events ----
def check_node(value, where: str, problems: Problems) -> tuple[bool, dict | None]:
    """The OpenAlex node that a road carries: null (a category the player named) or `{id, level, name}`, the level one of ORDER. Returns (whether it is right, the node with its
    keys in that order, or None). Whether the houses of the road are under the node, and whether another road carries it already, is for the world to say."""
    if value is None:
        return True, None
    if not isinstance(value, dict):
        problems.add(where, f"must be null or an object {{id, level, name}}, got {type(value).__name__}", "node_not_an_object", got=type(value).__name__)
        return False, None
    start = _count(problems)
    if not _keys(problems, where, value, NODE_KEYS, NODE_KEYS):
        return False, None
    text(problems, f"{where}.id", value["id"], plain=True)
    text(problems, f"{where}.name", value["name"], plain=True)
    if value["level"] not in ORDER:
        problems.add(f"{where}.level", f"must be one of {', '.join(ORDER)}, got {_shown(value['level'])}", "node_level_bad", got=_shown(value["level"]), levels=list(ORDER))
    return _count(problems) == start, {k: value[k] for k in NODE_KEYS}


def _road_id(problems: Problems, where: str, value, *, new: bool = False) -> bool:
    """A road id: text without control characters. A new road may not look like the id of a continuation rib (lane:<id>:<n>) nor start with `auto:`."""
    if not text(problems, where, value, plain=True):
        return False
    if new and _LANE_LIKE.match(value):
        problems.add(where, f"{value!r} looks like the block key of a continuation rib (lane:<id>:<n>); use another id", "road_id_lane_like", road=value)
        return False
    if new and value.startswith(AUTO_PREFIX):
        problems.add(where, f"{value!r} starts with {AUTO_PREFIX!r}, which is for the roads that the rule opens by itself", "road_id_reserved", road=value, prefix=AUTO_PREFIX)
        return False
    return True


def _payload(kind: str, payload, where: str, problems: Problems) -> dict | None:
    if not isinstance(payload, dict):
        problems.add(where, f"must be an object, got {type(payload).__name__}", "not_an_object", got=type(payload).__name__)
        return None
    keys = PAYLOAD_KEYS[kind]
    required = tuple(k for k in keys if k not in OPTIONAL_KEYS.get(kind, ()))
    start = _count(problems)
    if not _keys(problems, where, payload, required, keys):
        return None
    if kind == "add_item":
        item = check_item(payload["item"], f"{where}.item", problems)
        return {"item": item} if item is not None else None
    if kind == "set_rule":
        return check_rule(payload, where, problems)
    node = None
    if kind == "undo":
        if not _whole(payload["seq"]) or payload["seq"] < 1:
            problems.add(f"{where}.seq", f"must be the number of an event (1 or more), got {_shown(payload['seq'])}", "undo_seq_bad", got=_shown(payload["seq"]))
    elif kind == "open_road":
        _road_id(problems, f"{where}.road", payload["road"], new=True)
        text(problems, f"{where}.name", payload["name"], plain=True)
        if payload["parent"] is not None:
            _road_id(problems, f"{where}.parent", payload["parent"])
        houses = payload["houses"]
        if not isinstance(houses, list) or not houses:
            problems.add(f"{where}.houses", "must be a list of house ids, not empty", "houses_empty")
        else:
            for j, h in enumerate(houses):
                if text(problems, f"{where}.houses[{j}]", h, plain=True) and h in houses[:j]:
                    problems.add(f"{where}.houses[{j}]", f"{h!r} is chosen twice", "house_chosen_twice", house=h)
        _, node = check_node(payload.get("topic"), f"{where}.topic", problems)
    elif kind == "merge_roads":
        _road_id(problems, f"{where}.road", payload["road"], new=True)
        text(problems, f"{where}.name", payload["name"], plain=True)
        if payload["parent"] is not None:
            problems.add(f"{where}.parent", f"must be null, the town hall: avenues are merged under a new avenue of the first ring, got {_shown(payload['parent'])}",
                         "parent_not_root", got=_shown(payload["parent"]))
        members = payload["members"]
        if not isinstance(members, list):
            problems.add(f"{where}.members", f"must be a list of at least {MERGE_LEAST} road ids, got {type(members).__name__}", "not_a_list", got=type(members).__name__)
        else:
            if len(members) < MERGE_LEAST:
                problems.add(f"{where}.members", f"holds {len(members)} {'road' if len(members) == 1 else 'roads'}; a merge takes at least {MERGE_LEAST}", "members_too_few",
                             count=len(members), least=MERGE_LEAST)
            for j, m in enumerate(members):
                if _road_id(problems, f"{where}.members[{j}]", m) and m in members[:j]:
                    problems.add(f"{where}.members[{j}]", f"{m!r} is chosen twice", "member_chosen_twice", road=m)
        _, node = check_node(payload.get("topic"), f"{where}.topic", problems)
    elif kind == "file":
        text(problems, f"{where}.house", payload["house"], plain=True)
        _road_id(problems, f"{where}.road", payload["road"])
    elif kind == "rename_road":
        _road_id(problems, f"{where}.road", payload["road"])
        text(problems, f"{where}.name", payload["name"], plain=True)
    elif kind == "move_road":
        _road_id(problems, f"{where}.road", payload["road"])
        _road_id(problems, f"{where}.parent", payload["parent"])
    if _count(problems) != start:
        return None
    out = {k: payload.get(k) for k in keys}
    if kind in ("open_road", "merge_roads"):
        out["topic"] = node
    return out


def check_event(event, where: str, problems: Problems) -> dict | None:
    """One event as the log keeps it (keys in the order seq, at, kind, payload; the payload in the order of its kind), or None with the problems added."""
    if not isinstance(event, dict):
        problems.add(where, f"must be an object, got {type(event).__name__}", "not_an_object", got=type(event).__name__)
        return None
    start = _count(problems)
    if not _keys(problems, where, event, ("seq", "at", "kind", "payload"), ("seq", "at", "kind", "payload")):
        return None
    if not _whole(event["seq"]) or event["seq"] < 1:
        problems.add(f"{where}.seq", f"must be a whole number, 1 or more, got {_shown(event['seq'])}", "event_seq_bad", got=_shown(event["seq"]))
    if text(problems, f"{where}.at", event["at"]):
        try:
            parse_added_at(event["at"])
        except (ValueError, OverflowError):
            problems.add(f"{where}.at", f"{event['at']!r} is not an ISO 8601 date or date and time", "date_bad", at=event["at"])
    kind = event["kind"]
    if kind not in KINDS:
        problems.add(f"{where}.kind", f"{_shown(kind)} is not a kind of event ({', '.join(KINDS)})", "kind_unknown", kind=_shown(kind), kinds=list(KINDS))
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
    if kind == "merge_roads":
        return set(p["members"]), set()
    return set(), set()
