"""The journal of a hand-built world: its log of events and the world that the log folds to, kept together; and the world file it is written to and read from.

    journal = Journal()                                                      # the rule 40 / 10, `auto` off
    journal.append("add_item", {"item": {...}}, "2026-10-26T09:30:00Z")      # -> the event, with its `seq`; `Refusal` when the world does not take it
    journal.state.city()                                                     # the layout v4 document of the world now
    text = dumps_world(world_document(journal))                              # the world file: JSON, one item and one event to a line, the canonical number form
    journal = read_world(json.loads(text))                                   # ... and back: every event is appended again, under the rules of `append`

`append` is the one way an event enters a world. It checks the shape of the event (bibliopolis.events), asks the world to take it (bibliopolis.hand) and only then
keeps it, so a log made by `append` folds again to the same world. An `undo` is held to two more rules, so that the player undoes from the end backwards:

  - the event it names counts, and no later event that counts depends on it: none names a road it opened, or a house it placed or moved;
  - the log without that event still folds: every later event that counts can be taken again (the check that sees what the rule above cannot say, for example the
    restoring of an event whose house a later event has taken away).
"""

from __future__ import annotations

from .canonical import dumps
from .events import DEFAULT_RULE, Refusal, check_event, check_item, check_rule, references, standing
from .hand import State, fold
from .inputs import InputError, _Problems, _shown, load_json

FORMAT = "bibliopolis.world"
VERSION = 1
FILE_KEYS = ("format", "version", "rule", "items", "events")


class WorldFileError(InputError):
    """A world file (or a store) is not what docs/world.md describes. The message lists the problems, one per line, each with its place."""


def _refuse(problems: _Problems) -> None:
    if problems.found:
        raise Refusal("\n".join([*problems.found, *([f"... and {problems.more} more"] if problems.more else [])]))


class Journal:
    """A log of events and the `State` it folds to. `rule` is the rule the world starts with; `set_rule` events change it from their place in the log on."""

    def __init__(self, rule: dict | None = None):
        problems = _Problems()
        checked = check_rule(dict(DEFAULT_RULE) if rule is None else rule, "rule", problems)
        _refuse(problems)
        self.rule: dict = checked  # type: ignore[assignment]
        self.events: list[dict] = []
        self.state = State(self.rule)

    @classmethod
    def replay(cls, rule: dict | None, events: list[dict]) -> "Journal":
        """The journal of a log made elsewhere: every event is appended in turn, so it is held to the rules of `append`. `Refusal` names the first event that is not."""
        journal = cls(rule)
        for e in events:
            if e["seq"] != len(journal.events) + 1:
                raise Refusal(f"event {e['seq']} comes in place {len(journal.events) + 1}: the events are numbered 1, 2, 3, ... in order")
            try:
                journal.append(e["kind"], e["payload"], e["at"])
            except Refusal as why:
                raise why.within(f"event {e['seq']} ({e['kind']})") from None
        return journal

    def items(self) -> list[dict]:
        """The item of every add_item event, in log order (an undone one too): the `items` of a world file."""
        return [e["payload"]["item"] for e in self.events if e["kind"] == "add_item"]

    def append(self, kind: str, payload: dict, at: str) -> dict:
        """Append an event. Returns it as the log keeps it. `Refusal`, and no change, when its shape is wrong or the world does not take it."""
        problems = _Problems()
        event = check_event({"seq": len(self.events) + 1, "at": at, "kind": kind, "payload": payload}, "event", problems)
        _refuse(problems)
        assert event is not None
        if kind == "undo":
            self.state = self.undone(event)
        else:
            try:
                self.state.apply(event)
            except Refusal:
                raise
            except Exception:  # a fault in the engine, with the world half changed: fold the log again, so that the journal is not left in a state no log gives
                self.state = fold(self.events, self.rule)
                raise
        self.events.append(event)
        return event

    def undone(self, event: dict) -> State:
        """The world after the undo `event`, if it may be taken."""
        target = event["payload"]["seq"]
        keep = standing(self.events)
        if target >= event["seq"]:
            raise Refusal(f"an undo names an earlier event; event {target} is not earlier than event {event['seq']}")
        if target not in keep:
            raise Refusal(f"event {target} does not count (there is no such event, or it is undone already)")
        effect = self.state.effects[target]
        for later in self.events[target:]:
            if later["seq"] in keep:
                roads, houses = references(later)
                if roads & set(effect["roads"]) or houses & set(effect["houses"]):
                    raise Refusal(f"event {target} cannot be undone: event {later['seq']} ({later['kind']}) depends on it; undo that one first")
        try:
            return fold([*self.events, event], self.rule)
        except Refusal as why:
            raise Refusal(f"event {target} cannot be undone: {why}") from None


# ------------------------------------------------------------------------------------------------ the world file ----
def world_document(journal: Journal) -> dict:
    """The world file of a journal as a document: `{format, version, rule, items, events}`. `rule` is the rule the world started with; `items` is the item of every add_item
    event in log order (the metadata, for a reader that does not fold; it is written from the events and checked against them when a file is read); `events` is the log."""
    return {"format": FORMAT, "version": VERSION, "rule": dict(journal.rule), "items": journal.items(), "events": list(journal.events)}


def dumps_world(doc: dict) -> str:
    """The text of a world file: the header, then one item and one event to a line, in the canonical number form (bibliopolis.canonical). The same journal gives the
    same bytes, and a file read and written again is the same bytes (a file that came from elsewhere is made canonical)."""

    def block(rows: list) -> str:
        return "[]" if not rows else "[\n" + ",\n".join("  " + dumps(row) for row in rows) + "\n ]"

    return ("{\n" + f' "format": {dumps(doc["format"])},\n "version": {dumps(doc["version"])},\n "rule": {dumps(doc["rule"])},\n'
            + f' "items": {block(doc["items"])},\n "events": {block(doc["events"])}\n' + "}\n")


def read_world(doc) -> Journal:
    """The journal of a world file read as JSON. Every problem of shape is reported at once with its place (`WorldFileError`); then the events are appended in turn, so
    each is held to the rules of `append`, and the first that the world does not take is named; last, `items` must be what the add_item events carry."""
    problems = _Problems()
    if not isinstance(doc, dict):
        raise WorldFileError(f"world: not a world file: it must be a JSON object, got {type(doc).__name__}")
    missing = [k for k in FILE_KEYS if k not in doc]
    extra = [k for k in doc if k not in FILE_KEYS]
    if missing or extra:
        raise WorldFileError("world: not a world file" + (f": missing {', '.join(missing)}" if missing else "") + (f": unknown {', '.join(sorted(map(str, extra)))}" if extra else "")
                             + f" (it has {', '.join(FILE_KEYS)})")
    if doc["format"] != FORMAT:
        raise WorldFileError(f"world.format: must be {FORMAT!r}, got {_shown(doc['format'])}")
    if doc["version"] != VERSION or isinstance(doc["version"], bool):
        raise WorldFileError(f"world.version: this program reads version {VERSION}, got {_shown(doc['version'])}")
    rule = check_rule(doc["rule"], "world.rule", problems)
    items, events = [], []
    for name, rows, check in (("items", doc["items"], check_item), ("events", doc["events"], check_event)):
        if not isinstance(rows, list):
            problems.add(f"world.{name}", f"must be a list, got {type(rows).__name__}")
            continue
        for i, row in enumerate(rows):
            checked = check(row, f"world.{name}[{i}]", problems)
            if checked is not None:
                (items if name == "items" else events).append(checked)
    if problems.found:
        raise WorldFileError("\n".join([*problems.found, *([f"... and {problems.more} more"] if problems.more else [])]))
    for i, e in enumerate(events):
        if e["seq"] != i + 1:
            raise WorldFileError(f"world.events[{i}].seq: must be {i + 1}: the events are numbered 1, 2, 3, ... in order, got {e['seq']}")
    journal = Journal(rule)
    for i, e in enumerate(events):
        try:
            journal.append(e["kind"], e["payload"], e["at"])
        except Refusal as why:
            raise WorldFileError(f"world.events[{i}] ({e['kind']}): {why}") from None
    derived = journal.items()
    if items != derived:
        place = next((i for i, (a, b) in enumerate(zip(items, derived)) if a != b), min(len(items), len(derived)))
        raise WorldFileError(f"world.items[{place}]: the items are those of the add_item events, in order ({len(derived)} of them), and the file says otherwise ({len(items)})")
    return journal


def load_world_file(path) -> Journal:
    """The journal of the world file at `path` (`read_world` of its JSON; `InputError` when the file is not JSON)."""
    return read_world(load_json(path))
