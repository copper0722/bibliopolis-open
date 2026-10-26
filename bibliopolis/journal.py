"""The journal of a hand-built world: its log of events and the world that the log folds to, kept together.

    journal = Journal()                                                      # the rule 40 / 10, `auto` off
    journal.append("add_item", {"item": {...}}, "2026-10-26T09:30:00Z")      # -> the event, with its `seq`; `Refusal` when the world does not take it
    journal.state.city()                                                     # the layout v4 document of the world now

`append` is the one way an event enters a world. It checks the shape of the event (bibliopolis.events), asks the world to take it (bibliopolis.hand) and only then
keeps it, so a log made by `append` folds again to the same world. An `undo` is held to two more rules, so that the player undoes from the end backwards:

  - the event it names counts, and no later event that counts depends on it: none names a road it opened, or a house it placed or moved;
  - the log without that event still folds: every later event that counts can be taken again (the check that sees what the rule above cannot say, for example the
    restoring of an event whose house a later event has taken away).
"""

from __future__ import annotations

from .events import DEFAULT_RULE, Refusal, check_event, check_rule, references, standing
from .hand import State, fold
from .inputs import _Problems


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
                raise Refusal(f"event {e['seq']} ({e['kind']}): {why}") from None
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
