"""The cut: which topics are streets, read from the items a library holds.

The cut runs on the number of houses per topic, with no depth cap:

  address     the deepest topic of an item (a root is depth 1; ties in code-point order). An item with no topic of the tree has none.
  street      a topic with at most H houses below it is a LEAF street (its subtree is folded into it by house count and by nothing else); a
              topic above that holds a CONTAINER street, which also owns the houses whose address is the topic itself. A one-child chain
              (no house of its own, one child with houses) collapses into the address of its child. A street with more than H lots of its own
              opens overflow lanes of H lots each, oldest first. Depth is unbounded: the display class saturates (大道 ring 1, 路 ring 2, 巷
              ring 3, 弄 ring 4 and deeper).
  ring 1      the topic roots (the children of the centre when the tree has exactly one root, which then is the town hall itself).

The cut decides what the plan (bibliopolis.plan) pins before the first house arrives: the ring-1 sectors, their weights, and which topics are
collapsed into which street. With `whole_tree` every topic an item is filed under (any of the item's topics, not only the address), and every topic
above one, is a street of its own: nothing is folded into a leaf and no chain is collapsed (the `mirror` mode). An item still stands once, at its
address; a topic it is filed under without being its address is a street with no lots.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .layout import HOME_MAX, JOIN, LANE_FIRST, lane_place, rib_slots, tag_place
from .tree import TreeView, major_tag


@dataclass
class CutNode:
    """One topic of the tree as the cut sees it."""

    key: str  # the id of the topic
    place: str
    label: str
    parent: str | None
    kids: list[str] = field(default_factory=list)  # in code-point order of the key
    direct: list[str] = field(default_factory=list)  # ids of the items whose address is this topic
    cap: int = HOME_MAX  # lots of a street before it opens lanes
    tag: str | None = None


def topic_nodes(tree: TreeView, cap: int = HOME_MAX) -> dict[str, CutNode]:
    """The topics of the tree as nodes of the cut: children in code-point order, no items yet."""
    out: dict[str, CutNode] = {}
    for tid in tree.ids():
        out[tid] = CutNode(key=tid, place=tag_place(tid), label=tree.label(tid), parent=tree.parent(tid), cap=cap, tag=tid)
    for tid, node in out.items():
        if node.parent is not None:
            out[node.parent].kids.append(tid)
    for node in out.values():
        node.kids.sort()
    return out


@dataclass
class Rib:
    """A lane with a row of lots on each side: the lots of one street (its own rib) or of one overflow lane."""

    place: str  # the street or lane place that holds the lots
    key: str  # block key of the reserved ids
    label: str
    lots: list[str]  # item ids, in order
    street: "Street"
    lane: int | None = None  # None: the own rib of the street; k >= 2: the overflow lane number k

    @property
    def slots(self) -> int:
        return rib_slots(len(self.lots))


@dataclass
class Street:
    """A container (a trunk) or a leaf street (a rib) of the plan, with the ribs that carry its lots."""

    node: CutNode
    kind: str  # "container" | "leaf"
    ring: int  # street level: ring 1 is a child of the centre; a collapsed chain does not count
    label: str  # the address segment: the names of the chain collapsed into it, joined
    address: list[str]
    parent: "Street | None"
    collapsed: list[str] = field(default_factory=list)  # keys of the one-child chain above it, top first
    absorbed: list[str] = field(default_factory=list)  # keys of the nodes below a leaf street (their houses stand on it)
    ribs: list[Rib] = field(default_factory=list)  # the own rib first, then the lanes
    leaves: list["Street"] = field(default_factory=list)  # leaf children
    containers: list["Street"] = field(default_factory=list)  # container children (branches)
    weight: int = 0
    trunk: bool = False  # a street with a trunk of its own (a spoke and a wedge); the others hang on the bands of a trunk above
    carrier: "Street | None" = None  # the street whose trunk carries this street (itself when it has a trunk)
    order: int = 0  # position among the streets of the same parent, in the order of the cut

    @property
    def place(self) -> str:
        return self.node.place

    @property
    def key(self) -> str:
        return self.node.key


def classify(nodes: dict[str, CutNode], sub: dict[str, int], top: list[str], fold: int, collapse: bool = True) -> dict[str, str]:
    """key -> role: container | leaf | chain | interior | empty, for the nodes below the centre.

    A topic with `fold` houses or fewer below it is a leaf (everything below it is interior); `collapse` turns a container with no house of
    its own and one child with houses into a chain."""
    role: dict[str, str] = {}

    def mark(key: str, r: str) -> None:
        for kid in nodes[key].kids:
            role[kid] = r
            mark(kid, r)

    def cut(key: str) -> None:
        bearing = [k for k in nodes[key].kids if sub[k] > 0]
        if sub[key] == 0:
            role[key] = "empty"
            mark(key, "empty")
        elif sub[key] <= fold or not bearing:
            role[key] = "leaf"
            mark(key, "interior")
        else:
            role[key] = "container"
            for kid in nodes[key].kids:
                cut(kid)

    for key in top:
        cut(key)
    if collapse:
        for key, r in list(role.items()):  # a container with nothing of its own and one child with houses is not a street
            if r == "container" and not nodes[key].direct and len([k for k in nodes[key].kids if sub[k] > 0]) == 1:
                role[key] = "chain"
    return role


def lots_below(nodes: dict[str, CutNode], key: str) -> list[str]:
    out = list(nodes[key].direct)
    for kid in nodes[key].kids:
        out.extend(lots_below(nodes, kid))
    return out


def below(nodes: dict[str, CutNode], key: str) -> list[str]:
    out: list[str] = []
    for kid in nodes[key].kids:
        out.append(kid)
        out.extend(below(nodes, kid))
    return out


def make_ribs(street: Street, lots: list[str], cap: int) -> None:
    """The own rib of a street and, when it holds more than `cap` lots, its overflow lanes of `cap` lots each."""
    node = street.node
    if not lots:
        return
    street.ribs.append(Rib(node.place, node.key, street.label, lots[:cap], street))
    for k, start in enumerate(range(cap, len(lots), cap), start=LANE_FIRST):
        label = f"{street.label}{JOIN}{k}"
        street.ribs.append(Rib(lane_place(node.key, k), f"lane:{node.key}:{k}", label, lots[start:start + cap], street, lane=k))


def build_streets(nodes: dict[str, CutNode], role: dict[str, str], top: list[str]) -> list[Street]:
    """The streets of the cut, ring 1 first (a list of root streets); each carries its ribs and children."""

    def lay(key: str, parent: Street | None, pending: list[str], ring: int) -> list[Street]:
        r = role[key]
        if r == "empty":
            return []
        node = nodes[key]
        if r == "chain":
            bearing = [k for k in node.kids if role.get(k) not in (None, "empty")]
            return [s for k in bearing for s in lay(k, parent, pending + [key], ring)]
        label = JOIN.join(nodes[t].label for t in [*pending, key])
        base = parent.address if parent is not None else []
        street = Street(node, "container" if r == "container" else "leaf", ring, label, base + [label], parent, collapsed=list(pending))
        if r == "leaf":
            members = lots_below(nodes, key)
            street.absorbed = below(nodes, key)
            make_ribs(street, sorted(members), node.cap)
        else:
            make_ribs(street, sorted(node.direct), node.cap)
            for kid in node.kids:
                for child in lay(kid, street, [], ring + 1):
                    child.order = len(street.containers) + len(street.leaves)
                    (street.containers if child.kind == "container" else street.leaves).append(child)
        return [street]

    return [s for key in top for s in lay(key, None, [], 1)]


def weigh(street: Street) -> int:
    """Lots plus reserved lots of the subtree: what the wedge of a street is proportional to."""
    street.weight = sum(r.slots for r in street.ribs) + sum(weigh(c) for c in street.leaves) + sum(weigh(c) for c in street.containers)
    return street.weight


@dataclass
class Composition:
    """Everything decided before any coordinate: the streets, their ribs, weights and addresses."""

    home_max: int
    centre_tag: str | None  # the single real root, or None: a virtual root over the topic roots
    ring1: list[Street]  # the root streets, in the order of the cut
    nodes: dict[str, CutNode]
    role: dict[str, str]
    major: dict[str, str | None]
    streets: dict[str, Street]  # place -> street (lanes are ribs of their street, not streets)
    topic_roots: list[str]
    sub: dict[str, int]  # topic -> houses at or below it, by address (the centre's own houses are not counted)
    filed: set[str]  # the topics an item is filed under (any of its topics) and every topic above one

    def all_streets(self) -> list[Street]:
        out: list[Street] = []

        def walk(s: Street) -> None:
            out.append(s)
            for c in s.leaves + s.containers:
                walk(c)

        for s in self.ring1:
            walk(s)
        return out

    def filed_topics(self) -> list[str]:
        """The topics an item is filed under (any of its topics) and every topic above one, other than the centre, in code-point order: the roads of
        a `mirror` city."""
        return sorted(k for k in self.filed if k != self.centre_tag)


def compose(tree: TreeView, items: list[dict], home_max: int = HOME_MAX, *, whole_tree: bool = False) -> Composition:
    """The cut of the whole library: the topic tree around the centre. With `whole_tree` every topic an item is filed under, and every topic above
    one, is a street."""
    ordered = sorted(items, key=lambda a: a["id"])
    nodes = topic_nodes(tree, home_max)
    topic_roots = tree.roots()
    major = {a["id"]: major_tag(tree, a) for a in ordered}
    for a in ordered:
        m = major[a["id"]]
        if m is not None:
            nodes[m].direct.append(a["id"])
    for node in nodes.values():
        node.direct.sort()
    centre_tag = topic_roots[0] if len(topic_roots) == 1 else None
    top = list(nodes[centre_tag].kids) if centre_tag is not None else list(topic_roots)

    sub: dict[str, int] = {}

    def count(key: str) -> int:
        sub[key] = len(nodes[key].direct) + sum(count(k) for k in nodes[key].kids)
        return sub[key]

    for key in top:
        count(key)
    filed: set[str] = set()  # an item is filed under all its topics and stands once, at the deepest: the topics it is filed under are roads too
    for a in ordered:
        for t in a.get("topics", []):
            cur = t if t in tree else None
            while cur is not None and cur not in filed:
                filed.add(cur)
                cur = tree.parent(cur)
    role = classify(nodes, {k: int(k in filed) for k in nodes} if whole_tree else sub, top, 0 if whole_tree else home_max, collapse=not whole_tree)
    ring1 = build_streets(nodes, role, top)
    if centre_tag is not None and nodes[centre_tag].direct:  # the root itself carries houses: a ring-1 street of their own in the plan
        own = Street(nodes[centre_tag], "leaf", 1, nodes[centre_tag].label, [nodes[centre_tag].label], None)
        make_ribs(own, sorted(nodes[centre_tag].direct), home_max)
        ring1.insert(0, own)
    for k, s in enumerate(ring1):
        s.order = k
        weigh(s)
    streets = {}
    for s in ring1:
        stack = [s]
        while stack:
            cur = stack.pop()
            streets[cur.place] = cur
            stack.extend(cur.leaves + cur.containers)
    return Composition(home_max, centre_tag, ring1, nodes, role, major, streets, topic_roots, sub, filed)
