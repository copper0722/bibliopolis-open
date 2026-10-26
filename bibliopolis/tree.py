"""The topic tree as the engine reads it: parent links, labels and depths.

A tree is `{"nodes": [{"id": ..., "label": ..., "parent": <id or null>}, ...]}` (see docs/format.md). The engine reads trees through a
TreeView, so the same code serves a hand-made tree in a test and a validated one from a file (bibliopolis.inputs).
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
        self._depth: dict[str, int] = {}
        self._kids: dict[str, list[str]] | None = None

    def __contains__(self, tag: str) -> bool:
        return tag in self._parent

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
    """The address of an item: its deepest topic from the real root (ties in code-point order); None when it has no topic of the tree."""
    inside = [t for t in item.get("topics", []) if t in tree]
    return min(inside, key=lambda t: (-tree.depth(t), t)) if inside else None
