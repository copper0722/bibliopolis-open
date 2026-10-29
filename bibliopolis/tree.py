"""The topic tree as the engine reads it: parent links, labels and depths.

A tree is `{"nodes": [{"id": ..., "label": ..., "parent": <id or null>}, ...]}`, and may name a root bucket with `"bucket": <id of a root>` (see docs/format.md). The
engine reads trees through a TreeView, so the same code serves a hand-made tree in a test and a validated one from a file (bibliopolis.inputs).

The root bucket is where a library keeps what it has not sorted yet. It and everything below it are not places: a TreeView does not hold them (they are not in it, have no parent,
no depth and no children there), so no road, no street, no sector and no mirror road is ever made for them. An item filed only under the bucket stands on the ring road (`address_of`).
"""

from __future__ import annotations


class TreeView:
    """Parent links, labels and depths of a topic tree. A parent the tree does not hold, or a node that is its own parent, is a root."""

    def __init__(self, tree: dict):
        self.names: dict[str, str] = {}
        self._parent: dict[str, str | None] = {}
        for n in tree["nodes"]:
            self.names[n["id"]] = n["label"]
            self._parent[n["id"]] = n["parent"] if n["parent"] != n["id"] else None
        for tid, p in list(self._parent.items()):
            if p is not None and p not in self._parent:
                self._parent[tid] = None
        # the root bucket (docs/format.md): the node `tree["bucket"]` names, if it is a root of this tree, and everything below it. They are not places, so they are taken out of
        # the maps below; `names` keeps them (the label of the bucket is its name). A name that is no root of the tree names no bucket (inputs.read_tree refuses it in a file).
        named = tree.get("bucket")
        self.bucket: str | None = named if named in self._parent and self._parent[named] is None else None
        self._in_bucket: frozenset[str] = frozenset()
        if self.bucket is not None:
            kids: dict[str, list[str]] = {}
            for tid, p in self._parent.items():
                if p is not None:
                    kids.setdefault(p, []).append(tid)
            below, stack = {self.bucket}, [self.bucket]
            while stack:
                for k in kids.get(stack.pop(), ()):
                    if k not in below:
                        below.add(k)
                        stack.append(k)
            self._in_bucket = frozenset(below)
            for tid in below:
                del self._parent[tid]
        self._depth: dict[str, int] = {}
        self._kids: dict[str, list[str]] | None = None

    def __contains__(self, tag: str) -> bool:
        return tag in self._parent

    def in_bucket(self, tag: str) -> bool:
        """Whether `tag` is the root bucket or a node below it: a node of the tree document that is no place of the tree."""
        return tag in self._in_bucket

    def __len__(self) -> int:
        return len(self._parent)

    def ids(self) -> list[str]:
        """Every topic id, in code-point order."""
        return sorted(self._parent)

    def roots(self) -> list[str]:
        """The topics that have no parent, in code-point order."""
        return sorted(tid for tid, p in self._parent.items() if p is None)

    def parent(self, tag: str) -> str | None:
        return self._parent.get(tag)

    def label(self, tag: str) -> str:
        return self.names.get(tag) or tag

    def depth(self, tag: str) -> int:
        """Depth from the real root (a root is 1); a cycle counts as unreachable (raises)."""
        if tag in self._depth:
            return self._depth[tag]
        chain, cur = [], tag
        while cur is not None and cur not in self._depth:
            if cur in chain:
                raise ValueError(f"cycle in the topic tree at {cur}")
            chain.append(cur)
            cur = self._parent[cur]
        base = self._depth[cur] if cur is not None else 0
        for t in reversed(chain):
            base += 1
            self._depth[t] = base
        return self._depth[tag]

    def kids(self, tag: str) -> list[str]:
        """The children of a topic in code-point order."""
        if self._kids is None:
            self._kids = {}
            for tid, p in self._parent.items():
                if p is not None:
                    self._kids.setdefault(p, []).append(tid)
            for v in self._kids.values():
                v.sort()
        return self._kids.get(tag, [])


def major_tag(tree: TreeView, item: dict) -> str | None:
    """The topic of the tree that is the place of an item: its deepest topic from the real root (ties in code-point order); None when it has no topic of the tree. A topic
    in the root bucket is no place of the tree and never counts here (`address_of` gives the bucket)."""
    inside = [t for t in item.get("topics", []) if t in tree]
    return min(inside, key=lambda t: (-tree.depth(t), t)) if inside else None


def address_of(tree: TreeView, item: dict) -> str | None:
    """The address of an item: the topic that is its place (`major_tag`); with none, the id of the root bucket when the item is filed under it or under a node below it;
    else None. One topic of the tree settles it, whatever else the item is filed under: the bucket is only where an item stands that has no place yet. A house whose
    address is the bucket (or None) stands on the ring road: the bucket is no road, so no group of houses of the bucket ever opens one."""
    place = major_tag(tree, item)
    if place is None and tree.bucket is not None and any(tree.in_bucket(t) for t in item.get("topics", ())):
        return tree.bucket
    return place
