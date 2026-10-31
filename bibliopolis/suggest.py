"""Suggestions for a hand-built world, made from the OpenAlex topics of its houses: no model, no network, and the same answer for the same world.

    suggest_road(world, at)       the houses to put on a new road opened at a road or the ring road, and the OpenAlex node to name it after
    suggest_file(world, house)    the road a house belongs on, with a confidence
    suggest_merge(world, at)      the roads below one road (the ring road: the avenues) to merge under a new road there, which makes room
    landing(world, item)          the road an arriving item stands on under the rule `auto`
    crowded(world)                the places that hold more houses than `max`

The OpenAlex topics are a tree of four levels (`ORDER`): domain, field, subfield and topic. An item carries up to three topics, each with the node of every level. A road may
stand for one node (`open_road` `topic`, `{id, level, name}`; the suggestions give it ready to be passed on), and then the tree of OpenAlex is the tree the suggestions follow,
one level at a time, as a grown city follows its topic tree: the ring road is split by domain, a domain road by field, a field road by subfield, a subfield road by topic. No road
is split further. Two roads never stand for the same node.

A suggestion is a dict that a page can show as it is; `world` is a `bibliopolis.hand.State`, the folded world (what `Journal.state` holds).
"""

from __future__ import annotations

from collections import Counter

from .events import LEVELS, MERGE_LEAST, ORDER, RING_LIMIT, Refusal, house_is_annex


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
    city, with the nodes of OpenAlex for the tree). Of two as deep, the one that the topic nearer the primary reaches. None, the ring road, when no road matches."""
    found = _descent(world, item["openalex"])
    return _best(found) if found else None


def _anchor(world, at: str | None, houses: list[str]) -> tuple[str, str] | None:
    """The node a place stands for, (level, id), or None.

    The ring road stands for no node. A road that carries a node stands for it. A category that carries none (a name the player chose) stands for the deepest node that its
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
    """The road to open at `at` (a road id, or None for the ring road): `{at, topic: {id, level, name}, name, houses}`, or None.

    The houses that stand directly at `at` are grouped by the OpenAlex level one below the level the place stands for (`_anchor`): the ring road by domain, a domain road by
    field, a field road by subfield, a subfield road by topic; a topic road is not split. Only the topics at or below the node of the place count. A house is in the group of
    each node it carries at that level, once; a house with no topic is in none. A node that a road stands for already is left out. The suggestion is the largest group of at
    least `min` houses (of two as large, the lower node id); `houses` are its members in arrival order, `topic` its node, ready to be the `topic` of `open_road`, and `name` the
    default name of the road (the name of the node, as the first house that carries it writes it). None where no road can be opened: a road in the last ring (`RING_LIMIT`) has no ring
    below it. `Refusal` for a road that is not there."""
    if at is not None and at not in world.nodes:
        raise Refusal(f"there is no road {at!r}", "no_road", road=at)
    if at is not None and world.ring(at) >= RING_LIMIT:
        return None
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
    if house in world.annexes:
        raise house_is_annex(house, world.annexes[house]["parent"], world.annexes[house]["form"])
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


def _profile(world, houses: list[str]) -> dict[str, Counter]:
    """For each level, how many of the houses carry each node (a house once for a node, however many of its topics lie under it)."""
    counts: dict[str, Counter] = {level: Counter() for level in LEVELS}
    for house in houses:
        for level in LEVELS:
            counts[level].update({t[level]["id"] for t in world.items[house]["openalex"]})
    return counts


def _likeness(a: dict[str, Counter], b: dict[str, Counter]) -> tuple[int, ...]:
    """How alike two avenues are: for each level, the most specific first, the houses they have in common under the same nodes (the smaller count of each node, summed)."""
    return tuple(sum(min(a[level][node], b[level][node]) for node in a[level].keys() & b[level].keys()) for level in LEVELS)


def suggest_merge(world, at: str | None = None) -> dict | None:
    """The roads to merge under a new road at `at` (a road id, or None for the ring road, where the roads are the avenues): `{members, topic, name, by, takes, frees}`, or None.
    The roads are those that stand directly below `at`. `Refusal` for a road that is not there.

    First, roads that stand for sibling nodes of OpenAlex (nodes with the same parent node, a level up): the group with the most roads (then the most houses, then the
    lower parent id) whose parent node no road stands for, and every house of whose roads, and of the roads below them, is under it. `topic` is that parent node
    (ready to be the `topic` of `merge_roads`), `name` its name, `by` is "parent_node". Failing that, the two roads whose houses are most alike (`_likeness`: the
    topics they have in common, the most specific level first; of two as alike the pair of lower road ids), when they have anything in common: `topic` is None, `name` the two
    names joined by " / ", `by` "similar_houses". `members` are in the order the roads were opened, `takes` is the member the new road takes the place of (at the ring road, the
    one whose sector is the widest, `bibliopolis.hand.State.widest_avenue`, whose direction the new avenue takes; below it, the one opened first) and `frees` how many places the
    merge makes at `at`. A merge that would put a road below the last ring (`RING_LIMIT`) is not suggested. Nothing is changed; the world takes the merge as it takes any event."""
    if at is not None and at not in world.nodes:
        raise Refusal(f"there is no road {at!r}", "no_road", road=at)
    avenues = world.children(at)
    if len(avenues) < MERGE_LEAST:
        return None
    houses = {road: world.houses_below(road) for road in avenues}
    taken = roads_by_node(world)
    siblings: dict[tuple[str, str], list[str]] = {}
    names: dict[tuple[str, str], str] = {}
    for road in avenues:
        node = world.nodes[road]["topic"]
        if node is None or node["level"] == ORDER[0]:
            continue
        up = ORDER[ORDER.index(node["level"]) - 1]
        parents: Counter = Counter()
        first: dict[str, str] = {}
        for item in world.items.values():
            for t in item["openalex"]:
                if t[node["level"]]["id"] == node["id"]:
                    parents[t[up]["id"]] += 1
                    first.setdefault(t[up]["id"], t[up]["name"])
        if parents:
            parent = min(parents, key=lambda i: (-parents[i], i))
            siblings.setdefault((up, parent), []).append(road)
            names[(up, parent)] = first[parent]
    groups = [(key, roads) for key, roads in siblings.items() if len(roads) >= MERGE_LEAST and key not in taken
              and all(descends(world.items[h]["openalex"], key[0], key[1]) for road in roads for h in houses[road]) and world.merge_reach(roads) <= RING_LIMIT]
    if groups:
        (level, parent), roads = min(groups, key=lambda g: (-len(g[1]), -sum(len(houses[r]) for r in g[1]), g[0][1], ORDER.index(g[0][0])))
        return {"members": roads, "topic": {"id": parent, "level": level, "name": names[(level, parent)]}, "name": names[(level, parent)], "by": "parent_node",
                "takes": world.widest_avenue(roads) if at is None else roads[0], "frees": len(roads) - 1}
    profiles = {road: _profile(world, houses[road]) for road in avenues}
    best, pair = None, None
    for i, a in enumerate(avenues):
        for b in avenues[i + 1:]:
            like = _likeness(profiles[a], profiles[b])
            key = (tuple(-n for n in like), *sorted((a, b)))
            if any(like) and (best is None or key < best) and world.merge_reach([a, b]) <= RING_LIMIT:
                best, pair = key, [a, b]
    if pair is None:
        return None
    return {"members": pair, "topic": None, "name": " / ".join(world.nodes[r]["name"] for r in pair), "by": "similar_houses",
            "takes": world.widest_avenue(pair) if at is None else min(pair, key=avenues.index), "frees": 1}


def crowded(world) -> list[dict]:
    """The places that hold more than `max` houses directly: `{at, name, houses}` (the ring road first, with `at` None and `name` None, then the roads in the order they
    were opened). The town hall tells the player; nothing in the world changes by itself."""
    held = Counter(world.road_of.values())
    top = world.rule["max"]
    return [{"at": road, "name": None if road is None else world.nodes[road]["name"], "houses": held[road]} for road in (None, *world.nodes) if held[road] > top]
