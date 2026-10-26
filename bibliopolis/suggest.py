"""Suggestions for a hand-built world, made from the OpenAlex topics of its houses: no model, no network, and the same answer for the same world.

    suggest_road(world, at)       the houses to put on a new road opened at a road or the root zone, and the OpenAlex node to name it after
    suggest_file(world, house)    the road a house belongs on, with a confidence
    landing(world, item)          the road an arriving item stands on under the rule `auto`
    crowded(world)                the places that hold more houses than `max`

The OpenAlex topics are a tree of four levels (`ORDER`): domain, field, subfield and topic. An item carries up to three topics, each with the node of every level. A road may
stand for one node (`open_road` `topic`, `{id, level, name}`; the suggestions give it ready to be passed on), and then the tree of OpenAlex is the tree the suggestions follow,
one level at a time, as a grown city follows its topic tree: the root zone is split by domain, a domain road by field, a field road by subfield, a subfield road by topic. No road
is split further. Two roads never stand for the same node.

A suggestion is a dict that a page can show as it is; `world` is a `bibliopolis.hand.State`, the folded world (what `Journal.state` holds).
"""

from __future__ import annotations

from collections import Counter

from .events import LEVELS, ORDER, Refusal


def roads_by_node(world) -> dict[tuple[str, str], str]:
    """(level, id) of every OpenAlex node that a road stands for -> the id of that road."""
    return {(n["topic"]["level"], n["topic"]["id"]): key for key, n in world.nodes.items() if n["topic"] is not None}


def descends(topics: list[dict], level: str, node_id: str) -> bool:
    """Whether one of the topics of an item is at or below the node `node_id` of `level`."""
    return any(t[level]["id"] == node_id for t in topics)


def _under(topics: list[dict], anchor: tuple[str, str] | None) -> list[dict]:
    """The topics that are at or below the node `anchor` (level, id); all of them when there is none."""
    return topics if anchor is None else [t for t in topics if t[anchor[0]]["id"] == anchor[1]]


def _descent(world, topics: list[dict]) -> dict[str, tuple[int, int]]:
    """road id -> (depth, order) for every road whose node is at or above one of the topics: the depth of the node (0 for a domain ... 3 for a topic) and the place, in the
    list of topics, of the first topic that reaches it (the primary topic is 0)."""
    by_node, found = roads_by_node(world), {}
    for order, t in enumerate(topics):
        for depth, level in enumerate(ORDER):
            road = by_node.get((level, t[level]["id"]))
            if road is not None and road not in found:
                found[road] = (depth, order)
    return found


def _best(found: dict[str, tuple[int, int]]) -> str:
    """The deepest road of `_descent`; of two as deep the one the topic nearer the primary reaches (a road is one node, so that settles it)."""
    return min(found, key=lambda road: (-found[road][0], found[road][1]))


def landing(world, item: dict) -> str | None:
    """The road that an arriving item stands on under the rule `auto`: the deepest road whose node is at or above one of its topics (the nearest open ancestor of a grown
    city, with the nodes of OpenAlex for the tree). Of two as deep, the one that the topic nearer the primary reaches. None, the root zone, when no road matches."""
    found = _descent(world, item["openalex"])
    return _best(found) if found else None


def _anchor(world, at: str | None, houses: list[str]) -> tuple[str, str] | None:
    """The node a place stands for, (level, id), or None.

    The root zone stands for no node. A road that carries a node stands for it. A category that carries none (a name the player chose) stands for the deepest node that its
    houses share: of the houses that carry a topic at all, a node is shared when all but fewer than `min` of them carry it (the few that do not could not make a road of their
    own), and the nodes are taken from the domain down, each below the one before it, the largest first and of two as large the lower id. None when not even a domain is shared."""
    if at is not None and world.nodes[at]["topic"] is not None:
        node = world.nodes[at]["topic"]
        return node["level"], node["id"]
    if at is None:
        return None
    entries = [t for t in (world.items[h]["openalex"] for h in houses) if t]
    need = len(entries) - (world.rule["min"] - 1)
    anchor = None
    for level in (ORDER if need > 0 else ()):
        counts = Counter(node for topics in entries for node in {t[level]["id"] for t in _under(topics, anchor)})
        if not counts:
            break
        node, count = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if count < need:
            break
        anchor = (level, node)
    return anchor


def suggest_road(world, at: str | None) -> dict | None:
    """The road to open at `at` (a road id, or None for the root zone): `{at, topic: {id, level, name}, name, houses}`, or None.

    The houses that stand directly at `at` are grouped by the OpenAlex level one below the level the place stands for (`_anchor`): the root zone by domain, a domain road by
    field, a field road by subfield, a subfield road by topic; a topic road is not split. Only the topics at or below the node of the place count. A house is in the group of
    each node it carries at that level, once; a house with no topic is in none. A node that a road stands for already is left out. The suggestion is the largest group of at
    least `min` houses (of two as large, the lower node id); `houses` are its members in arrival order, `topic` its node, ready to be the `topic` of `open_road`, and `name` the
    default name of the road (the name of the node, as the first house that carries it writes it). `Refusal` for a road that is not there."""
    if at is not None and at not in world.nodes:
        raise Refusal(f"there is no road {at!r}", "no_road", road=at)
    houses = world.houses_at(at)
    anchor = _anchor(world, at, houses)
    below = 0 if anchor is None else ORDER.index(anchor[0]) + 1
    if below == len(ORDER):
        return None
    level, taken = ORDER[below], roads_by_node(world)
    groups: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for house in houses:
        mine: dict[str, dict] = {}
        for t in _under(world.items[house]["openalex"], anchor):
            mine.setdefault(t[level]["id"], t[level])  # (the first topic that names a node writes its name)
        for node_id, node in mine.items():
            if (level, node_id) not in taken:
                groups.setdefault(node_id, []).append(house)
                names.setdefault(node_id, node["name"])
    if not groups:
        return None
    node_id, members = min(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if len(members) < world.rule["min"]:
        return None
    return {"at": at, "topic": {"id": node_id, "level": level, "name": names[node_id]}, "name": names[node_id], "houses": members}


def _shared(mine: dict[str, set[str]], theirs: dict[str, set[str]]) -> list[int]:
    return [len(mine[level] & theirs[level]) for level in LEVELS]


def _ids(topics: list[dict]) -> dict[str, set[str]]:
    return {level: {t[level]["id"] for t in topics} for level in LEVELS}


def suggest_file(world, house: str) -> dict | None:
    """The road that `house` belongs on: `{house, road, name, level, shared, confidence}`, or None.

    A road that stands for a node (`open_road` `topic`) at or above one of the topics of the house is the first choice: the deepest one wins, and of two as deep the one the
    topic nearer the primary reaches. `level` is the level of its node, `shared` the houses of the road (the house itself left out) that are under the same node, and `confidence`
    one over the number of roads as deep as the winner, in hundredths: 1 when the hierarchy leaves no doubt. A house that stands on such a road gets a suggestion only for a
    deeper one.

    With no such road, a road scores one count for each level, the most specific first: the topics that the house shares with the houses of the road, summed over those houses
    (a topic that three houses of the road also carry counts three). The road with the best score, topic level first, wins; of two with the same score the one opened first.
    `level` is the most specific level at which it shares anything, `shared` the count there, and `confidence` that count as a part of the same count over every road that
    could take the house, from 0 to 1 in hundredths: 1 when no other road shares a topic at that level. A house that stands on a road gets a suggestion only for a road that
    scores better than the one it stands on. None when the house has no topic, no road fits, or the road it stands on is as good. `Refusal` for a house that is not there."""
    if house not in world.items:
        raise Refusal(f"{house!r} is not a house", "not_a_house", house=house)
    here = world.road_of[house]
    found = _descent(world, world.items[house]["openalex"])
    if found:
        best = _best(found)
        depth = found[best][0]
        if here in found and found[here][0] >= depth:
            return None
        node = world.nodes[best]["topic"]
        shared = sum(1 for other in world.houses_at(best) if other != house and descends(world.items[other]["openalex"], node["level"], node["id"]))
        peers = sum(1 for road in found if found[road][0] == depth)
        return {"house": house, "road": best, "name": world.nodes[best]["name"], "level": node["level"], "shared": shared, "confidence": round(1 / peers, 2)}
    mine = _ids(world.items[house]["openalex"])
    scores: dict[str, list[int]] = {}
    for road in world.nodes:
        total = [0] * len(LEVELS)
        for other in world.houses_at(road):
            if other != house:
                total = [a + b for a, b in zip(total, _shared(mine, _ids(world.items[other]["openalex"])))]
        scores[road] = total
    candidates = {road: s for road, s in scores.items() if road != here}
    if not candidates:
        return None
    opened = {road: i for i, road in enumerate(world.nodes)}
    best = max(candidates, key=lambda road: (candidates[road], -opened[road]))  # (the road opened first wins a tie)
    if not any(candidates[best]) or (here is not None and candidates[best] <= scores[here]):
        return None
    at = next(i for i, n in enumerate(candidates[best]) if n)
    count = candidates[best][at]
    whole = sum(s[at] for s in candidates.values())
    return {"house": house, "road": best, "name": world.nodes[best]["name"], "level": LEVELS[at], "shared": count, "confidence": round(count / whole, 2)}


def crowded(world) -> list[dict]:
    """The places that hold more than `max` houses directly: `{at, name, houses}` (the root zone first, with `at` None and `name` None, then the roads in the order they
    were opened). The town hall tells the player; nothing in the world changes by itself."""
    held = Counter(world.road_of.values())
    top = world.rule["max"]
    return [{"at": road, "name": None if road is None else world.nodes[road]["name"], "houses": held[road]} for road in (None, *world.nodes) if held[road] > top]
