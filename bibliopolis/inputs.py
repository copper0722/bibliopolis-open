"""Reading and checking the input documents: the library and the topic tree (docs/format.md, schema/), and the city that `picture` and `chronicle` read.

    library  {"items": [{"id", "title", "authors", "year", "doi"?, "added_at", "type", "tags", "topics"}, ...]}
    tree     {"nodes": [{"id", "label", "parent"}, ...]}
    city     the layout v4 document that `build` writes (docs/format.md, The city): only what a picture and the chronicle read is checked

`topics` are ids of tree nodes. The address of a house is its item's deepest topic (ties in code-point order of the id); an item with no
topic lives in the root zone. Items arrive in `added_at` order, ties by id.

The checks are strict on purpose: a library that names a topic the tree does not have is a mistake worth stopping for, not a house to place
somewhere. Every problem found is reported at once (up to MAX_PROBLEMS), each with the place it was found at.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_PROBLEMS = 20
MAX_DEPTH = 64  # the engine walks the tree recursively; a tree deeper than this is a mistake, not a topic structure

LIBRARY_REQUIRED = ("id", "title", "authors", "year", "added_at", "type", "tags", "topics")
LIBRARY_OPTIONAL = ("doi",)
TREE_REQUIRED = ("id", "label", "parent")

# an id that looks like the block key of a continuation rib (`lane:<id>:<n>`) would share reserved ids with that rib
_LANE_LIKE = re.compile(r"^lane:.*:\d+$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class InputError(ValueError):
    """The library or the tree is not what docs/format.md describes. The message lists the problems, one per line."""


class _Problems:
    def __init__(self) -> None:
        self.found: list[str] = []
        self.more = 0

    def add(self, where: str, what: str) -> None:
        if len(self.found) < MAX_PROBLEMS:
            self.found.append(f"{where}: {what}")
        else:
            self.more += 1

    def raise_if_any(self) -> None:
        if self.found:
            tail = [f"... and {self.more} more"] if self.more else []
            raise InputError("\n".join([*self.found, *tail]))


def load_json(path: str | Path):
    """A JSON document from a file (UTF-8, a byte order mark is tolerated)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{path}: not valid JSON ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{path}: not UTF-8 text ({exc})") from exc


def _encodable(s: str) -> bool:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _text(problems: _Problems, where: str, value, *, nonempty: bool = True, plain: bool = False) -> bool:
    """Whether `value` is a string that can be written as UTF-8; `plain` also refuses control characters (ids and labels are written into place ids)."""
    if not isinstance(value, str):
        problems.add(where, f"must be a string, got {type(value).__name__}")
        return False
    if nonempty and not value.strip():
        problems.add(where, "must not be empty")
        return False
    if not _encodable(value):
        problems.add(where, "contains a character that cannot be written as UTF-8 (a lone surrogate)")
        return False
    if plain and _CONTROL.search(value):
        problems.add(where, "must not contain control characters")
        return False
    return True


# ---------------------------------------------------------------------------------------------------- tree ----
def read_tree(doc) -> dict:
    """The tree document, checked and reduced to `{"nodes": [{"id", "label", "parent"}, ...]}` (input order kept, other keys dropped)."""
    problems = _Problems()
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), list):
        raise InputError('tree: must be an object with a list "nodes"')
    nodes: list[dict] = []
    ids: dict[str, int] = {}
    for i, n in enumerate(doc["nodes"]):
        where = f"tree.nodes[{i}]"
        if not isinstance(n, dict):
            problems.add(where, "must be an object")
            continue
        missing = [k for k in TREE_REQUIRED if k not in n]
        if missing:
            problems.add(where, f"missing {', '.join(missing)}")
            continue
        ok = _text(problems, f"{where}.id", n["id"], plain=True)
        ok = _text(problems, f"{where}.label", n["label"], plain=True) and ok
        parent = n["parent"]
        if parent is not None and not isinstance(parent, str):
            problems.add(f"{where}.parent", f"must be a node id or null, got {type(parent).__name__}")
            ok = False
        if not ok:
            continue
        if _LANE_LIKE.match(n["id"]):
            problems.add(f"{where}.id", f"{n['id']!r} looks like the block key of a continuation rib (lane:<id>:<n>); use another id")
            continue
        if n["id"] in ids:
            problems.add(f"{where}.id", f"{n['id']!r} is used twice (first at tree.nodes[{ids[n['id']]}])")
            continue
        ids[n["id"]] = i
        nodes.append({"id": n["id"], "label": n["label"], "parent": parent})
    for i, n in enumerate(doc["nodes"]):
        if isinstance(n, dict) and isinstance(n.get("parent"), str) and isinstance(n.get("id"), str) and n["id"] in ids:
            if n["parent"] not in ids:
                problems.add(f"tree.nodes[{i}].parent", f"{n['parent']!r} is not the id of a node")
    problems.raise_if_any()
    parent_of = {n["id"]: n["parent"] for n in nodes}
    depth: dict[str, int] = {}
    for n in nodes:
        chain: list[str] = []
        cur: str | None = n["id"]
        while cur is not None and cur not in depth:
            if cur in chain:
                problems.add("tree", f"the parents of {n['id']!r} lead round in a circle at {cur!r}")
                break
            chain.append(cur)
            cur = parent_of[cur]
        else:
            base = depth[cur] if cur is not None else 0
            for t in reversed(chain):
                base += 1
                depth[t] = base
            if depth[n["id"]] > MAX_DEPTH:
                problems.add("tree", f"{n['id']!r} is {depth[n['id']]} levels deep; the most the engine takes is {MAX_DEPTH}")
    problems.raise_if_any()
    return {"nodes": nodes}


# ------------------------------------------------------------------------------------------------- library ----
def parse_added_at(value: str) -> datetime:
    """`added_at` as an instant (UTC). ISO 8601: a date, or a date and time with or without an offset (a time without one is read as UTC)."""
    moment = datetime.fromisoformat(value.strip())
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def read_library(doc, tree: dict) -> list[dict]:
    """The items of a library document, checked against the (checked) `tree`, in arrival order: by `added_at`, ties by id.

    Each item comes back as `{"id", "title", "authors", "year", "doi", "added_at", "type", "tags", "topics"}` (`doi` None when the item has none;
    `topics` without repeats, in the order given; other keys dropped)."""
    problems = _Problems()
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        raise InputError('library: must be an object with a list "items"')
    topic_ids = {n["id"] for n in tree["nodes"]}
    seen: dict[str, int] = {}
    keyed: list[tuple[datetime, str, dict]] = []
    for i, it in enumerate(doc["items"]):
        where = f"library.items[{i}]"
        if not isinstance(it, dict):
            problems.add(where, "must be an object")
            continue
        missing = [k for k in LIBRARY_REQUIRED if k not in it]
        if missing:
            problems.add(where, f"missing {', '.join(missing)}")
            continue
        ok = _text(problems, f"{where}.id", it["id"], plain=True)
        if ok:
            where = f"library.items[{i}] ({it['id']!r})"
            if it["id"] in seen:
                problems.add(f"{where}.id", f"used twice (first at library.items[{seen[it['id']]}])")
                ok = False
            else:
                seen[it["id"]] = i
        ok = _text(problems, f"{where}.title", it["title"], nonempty=False) and ok
        ok = _text(problems, f"{where}.type", it["type"]) and ok
        year = it["year"]
        if year is not None and (not isinstance(year, int) or isinstance(year, bool)):
            problems.add(f"{where}.year", f"must be a whole number or null, got {type(year).__name__}")
            ok = False
        doi = it.get("doi")
        if doi is not None:
            ok = _text(problems, f"{where}.doi", doi) and ok
        for name in ("authors", "tags"):
            value = it[name]
            if not isinstance(value, list):
                problems.add(f"{where}.{name}", f"must be a list of strings, got {type(value).__name__}")
                ok = False
                continue
            for j, s in enumerate(value):
                ok = _text(problems, f"{where}.{name}[{j}]", s, nonempty=False) and ok
        topics = it["topics"]
        clean: list[str] = []
        if not isinstance(topics, list):
            problems.add(f"{where}.topics", f"must be a list of topic ids, got {type(topics).__name__}")
            ok = False
        else:
            for j, t in enumerate(topics):
                if not isinstance(t, str):
                    problems.add(f"{where}.topics[{j}]", f"must be a topic id (a string), got {type(t).__name__}")
                    ok = False
                elif t not in topic_ids:
                    problems.add(f"{where}.topics[{j}]", f"{t!r} is not the id of a node of the tree")
                    ok = False
                elif t not in clean:
                    clean.append(t)
        moment = None
        if _text(problems, f"{where}.added_at", it["added_at"]):
            try:
                moment = parse_added_at(it["added_at"])
            except (ValueError, OverflowError):
                problems.add(f"{where}.added_at", f"{it['added_at']!r} is not an ISO 8601 date or date and time")
                ok = False
        else:
            ok = False
        if ok and moment is not None:
            keyed.append((moment, it["id"], {"id": it["id"], "title": it["title"], "authors": list(it["authors"]), "year": year, "doi": doi,
                                             "added_at": it["added_at"], "type": it["type"], "tags": list(it["tags"]), "topics": clean}))
    problems.raise_if_any()
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in keyed]


# ----------------------------------------------------------------------------------------------------- city ----
ROAD_CLASSES = ("大道", "路", "巷", "弄")
PLACE_KINDS = ("plaza", "street", "lot", "reserved")


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_city(doc, name: str = "city") -> dict:
    """The city document, if it is the layout v4 file that `build` writes and has what `picture` and `chronicle` read; else `InputError` with the places of
    the problems. It does not re-check the geometry: a city that was edited by hand can still be wrong in ways this does not see."""
    problems = _Problems()
    if not isinstance(doc, dict):
        raise InputError(f"{name}: not a city document: the file does not hold a JSON object")
    if doc.get("layout_version") != "v4":
        raise InputError(f"{name}: not a city document: expected the layout v4 file that `bibliopolis build` writes "
                         f"(layout_version is {doc.get('layout_version')!r}, not 'v4'); a library or a tree file is not a city")
    for key in ("places", "roads", "composition", "world"):
        if not isinstance(doc.get(key), dict):
            problems.add(f"{name}.{key}", "must be an object")
    problems.raise_if_any()
    places, roads, comp, world = doc["places"], doc["roads"], doc["composition"], doc["world"]
    plaza = places.get("place:plaza")
    if not isinstance(plaza, dict) or not isinstance(plaza.get("label"), str) or not _number(plaza.get("radius")):
        problems.add(f"{name}.places.place:plaza", "must be an object with a label and a radius")
    for pid, p in places.items():
        where = f"{name}.places[{pid!r}]"
        if not isinstance(p, dict) or p.get("kind") not in PLACE_KINDS:
            problems.add(where, f"must be an object whose kind is one of {', '.join(PLACE_KINDS)}")
        elif p["kind"] in ("lot", "reserved") and not p.get("underground"):
            pos = p.get("position")
            if not isinstance(pos, dict) or not _number(pos.get("x")) or not _number(pos.get("z")) or p.get("parent") not in places:
                problems.add(where, "a house on the surface needs a position {x, z} and a parent that is a place")
    for rid, r in roads.items():
        where = f"{name}.roads[{rid!r}]"
        points = r.get("points") if isinstance(r, dict) else None
        if not isinstance(r, dict) or r.get("class") not in ROAD_CLASSES:
            problems.add(where, f"must be an object whose class is one of {', '.join(ROAD_CLASSES)}")
        elif not isinstance(points, list) or len(points) < 2 or not all(isinstance(q, list) and len(q) == 2 and all(_number(v) for v in q) for q in points):
            problems.add(where, "points must be a list of at least two [x, z] pairs")
    ring1 = comp.get("ring1")
    if not isinstance(ring1, list) or not all(isinstance(r, dict) and isinstance(r.get("place"), str) and isinstance(r.get("label"), str)
                                              and _number(r.get("from")) and _number(r.get("to")) for r in ring1):
        problems.add(f"{name}.composition.ring1", "must be a list of {place, label, from, to}")
    if not isinstance(comp.get("measure"), dict) or not isinstance(comp.get("streets"), dict) or not _number(comp.get("buildings")):
        problems.add(f"{name}.composition", "needs buildings, measure and streets")
    chronicle, districts = world.get("chronicle"), world.get("districts")
    if not isinstance(chronicle, list) or not all(isinstance(e, dict) and _number(e.get("seq")) for e in chronicle):
        problems.add(f"{name}.world.chronicle", "must be a list of entries that have a seq")
    if not isinstance(districts, dict) or not _number(districts.get("max")) or not _number(districts.get("min")):
        problems.add(f"{name}.world.districts", "must be an object with max and min")
    problems.raise_if_any()
    return doc
