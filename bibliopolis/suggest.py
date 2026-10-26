"""Suggestions for a hand-built world, made from the OpenAlex topics of its houses: no model, no network, and the same answer for the same world.

    suggest_road(state, at)       the houses to put on a new road opened at a road or the root zone, and the name to give it
    suggest_file(state, house)    the road a house belongs on, with a confidence
    crowded(state)                the places that hold more houses than `max`

An item carries up to three OpenAlex topics (the primary one and two more), each with four levels: domain, field, subfield and topic. Two houses share a topic at
a level when a topic of the one and a topic of the other have the same id there. A house with no topic is shared with nobody.

A suggestion is a dict that a page can show as it is; `state` is a `bibliopolis.hand.State` (what `Journal.state` holds).
"""

from __future__ import annotations

from collections import Counter
from typing import NamedTuple

from .events import LEVELS, Refusal


class Group(NamedTuple):
    level: str  # the level of the shared topic: topic, subfield, field or domain
    id: str  # the id of the topic the houses share, at that level
    name: str  # its name
    houses: list[str]  # house ids, in arrival order


def largest_group(houses: dict[str, list[dict]], least: int) -> Group | None:
    """The largest group of houses that share an OpenAlex topic at the most specific level that still gives a group of at least `least` houses. `houses` maps a house id
    to its topics, in arrival order. A house is in the group of each topic it carries (up to three), once. At one level the largest group wins, and of two as large the
    one with the lower topic id (code-point order). The name is that of the topic at that level, as the first house that carries it writes it. None when no level gives a group."""
    for level in LEVELS:
        groups: dict[str, list[str]] = {}
        names: dict[str, str] = {}
        for house, topics in houses.items():
            for node in {t[level]["id"]: t[level] for t in topics}.values():
                groups.setdefault(node["id"], []).append(house)
                names.setdefault(node["id"], node["name"])
        if groups:
            tid, members = min(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            if len(members) >= least:
                return Group(level, tid, names[tid], members)
    return None


def suggest_road(state, at: str | None) -> dict | None:
    """The road to open at `at` (a road id, or None for the root zone): `{at, level, topic: {id, name}, name, houses}`, or None when the houses that stand there directly
    share no topic in a group of at least `min`. `houses` are the houses of the largest group at the most specific level that gives one (see `largest_group`), `name`
    the default name for the road (the name of that topic). `Refusal` for a road that is not there."""
    if at is not None and at not in state.nodes:
        raise Refusal(f"there is no road {at!r}")
    group = largest_group({h: state.items[h]["openalex"] for h in state.houses_at(at)}, state.rule["min"])
    if group is None:
        return None
    return {"at": at, "level": group.level, "topic": {"id": group.id, "name": group.name}, "name": group.name, "houses": group.houses}


def _shared(mine: dict[str, set[str]], theirs: dict[str, set[str]]) -> list[int]:
    return [len(mine[level] & theirs[level]) for level in LEVELS]


def _ids(topics: list[dict]) -> dict[str, set[str]]:
    return {level: {t[level]["id"] for t in topics} for level in LEVELS}


def suggest_file(state, house: str) -> dict | None:
    """The road that `house` belongs on: `{house, road, name, level, shared, confidence}`, or None.

    A road scores one count for each level, the most specific first: the topics that the house shares with the houses of the road, summed over those houses (a topic
    that three houses of the road also carry counts three). The road with the best score, topic level first, wins; of two with the same score the one opened first. `level`
    is the most specific level at which it shares anything, `shared` the count there, and `confidence` that count as a part of the same count over every road that
    could take the house, from 0 to 1 in hundredths: 1 when no other road shares a topic at that level. A house that stands on a road gets a suggestion only
    for a road that scores better than the one it stands on. None when the house has no topic, no road shares one, or the road it stands on is as good.
    `Refusal` for a house that is not there."""
    if house not in state.items:
        raise Refusal(f"{house!r} is not a house")
    mine = _ids(state.items[house]["openalex"])
    scores: dict[str, list[int]] = {}
    for road in state.nodes:
        total = [0] * len(LEVELS)
        for other in state.houses_at(road):
            if other != house:
                total = [a + b for a, b in zip(total, _shared(mine, _ids(state.items[other]["openalex"])))]
        scores[road] = total
    here = state.road_of[house]
    candidates = {road: s for road, s in scores.items() if road != here}
    if not candidates:
        return None
    opened = {road: i for i, road in enumerate(state.nodes)}
    best = max(candidates, key=lambda road: (candidates[road], -opened[road]))  # (the road opened first wins a tie)
    if not any(candidates[best]) or (here is not None and candidates[best] <= scores[here]):
        return None
    at = next(i for i, n in enumerate(candidates[best]) if n)
    count = candidates[best][at]
    whole = sum(s[at] for s in candidates.values())
    return {"house": house, "road": best, "name": state.nodes[best]["name"], "level": LEVELS[at], "shared": count, "confidence": round(count / whole, 2)}


def crowded(state) -> list[dict]:
    """The places that hold more than `max` houses directly: `{at, name, houses}` (the root zone first, with `at` None and `name` None, then the roads in the order they
    were opened). The town hall tells the player; nothing in the world changes by itself."""
    held = Counter(state.road_of.values())
    top = state.rule["max"]
    return [{"at": road, "name": None if road is None else state.nodes[road]["name"], "houses": held[road]} for road in (None, *state.nodes) if held[road] > top]
