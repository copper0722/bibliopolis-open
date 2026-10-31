"""Reading and checking the input documents: the library and the topic tree (docs/format.md, schema/), and the city that `picture` and `chronicle` read.

    library  {"items": [{"id", "title", "authors", "year", "doi"?, "added_at", "type", "tags", "topics", "annex_of"?, "annex_form"?}, ...]}
    tree     {"nodes": [{"id", "label", "parent"}, ...], "bucket"?: <id of a root node>}
    city     the layout v4 document that `build` writes (docs/format.md, The city): only what a picture and the chronicle read is checked

`topics` are ids of tree nodes. The address of a house is its item's deepest topic (ties in code-point order of the id); an item with no
topic lives on the ring road, and so does an item filed only under the root bucket of the tree (the root node that `bucket` names, and everything below it: they are nodes of the
file and no places of the tree, see bibliopolis.tree). Items arrive in `added_at` order, ties by id.

An item that exists for another item carries `annex_of` (the id of that item, which is a house: it has no `annex_of` itself) and `annex_form` (`wing` or `mailbox`), both or
neither. It is no house of its own: it stands where the item it is of stands (docs/format.md, "An item that exists for another item"). The engine reads no `type`: the caller says which
form an item takes.

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
LIBRARY_OPTIONAL = ("doi", "annex_of", "annex_form")
ANNEX_FORMS = ("wing", "mailbox")  # the forms of an item that exists for another item: a wing beside the house, a mailbox at its gate
ANNEX_KEYS = ("annex_of", "annex_form")  # both or neither
TREE_REQUIRED = ("id", "label", "parent")
TREE_OPTIONAL = ("bucket",)  # a key of the tree document itself, beside "nodes"

# an id that looks like the block key of a continuation rib (`lane:<id>:<n>`: only a city file from before version 0.4 has such ribs) would share reserved ids with that rib
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
    except RecursionError as exc:
        raise InputError(f"{path}: nested too deeply to read") from exc


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
    """The tree document, checked and reduced to `{"nodes": [{"id", "label", "parent"}, ...]}` (input order kept, other keys dropped), plus `"bucket": <id>` when the document
    names a root bucket: the id of a node that is a root (null, like no key, is no bucket)."""
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
            problems.add(f"{where}.id", f"{n['id']!r} looks like the block key of a continuation rib (lane:<id>:<n>), which only a city file from before version 0.4 has; use another id")
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
    parent_of = {n["id"]: n["parent"] for n in nodes}
    bucket = doc.get("bucket")
    if bucket is not None and _text(problems, "tree.bucket", bucket, plain=True):
        if bucket not in ids:
            problems.add("tree.bucket", f"{bucket!r} is not the id of a node")
        elif parent_of[bucket] is not None:
            problems.add("tree.bucket", f"{bucket!r} is not a root (its parent is {parent_of[bucket]!r}): the bucket is a root of the tree")
    problems.raise_if_any()
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
    return {"nodes": nodes, **({"bucket": bucket} if bucket is not None else {})}


# ------------------------------------------------------------------------------------------------- library ----
def parse_added_at(value: str) -> datetime:
    """`added_at` as an instant (UTC). ISO 8601: a date, or a date and time with or without an offset (a time without one is read as UTC)."""
    moment = datetime.fromisoformat(value.strip())
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _annex_keys(problems: _Problems, where: str, it: dict) -> bool:
    """Whether the annex keys of one item are right: both or neither, `annex_of` an id (text without control characters), `annex_form` one of ANNEX_FORMS. Whether `annex_of` names an item
    of the library is for `_annex_links`, which sees them all."""
    present = [k for k in ANNEX_KEYS if k in it]
    if not present:
        return True
    if len(present) == 1:
        missing = next(k for k in ANNEX_KEYS if k not in it)
        problems.add(where, f"{present[0]} comes with {missing}: an item that exists for another item has both, and any other has neither; {missing} is missing")
        return False
    ok = _text(problems, f"{where}.annex_of", it["annex_of"], plain=True)
    if it["annex_form"] not in ANNEX_FORMS:
        problems.add(f"{where}.annex_form", f"must be one of {', '.join(ANNEX_FORMS)}, got {_shown(it['annex_form'])}")
        ok = False
    return ok


def _annex_links(problems: _Problems, items: list, seen: dict[str, int]) -> None:
    """The item that an annex is of is another item of the library, and a house: it has no `annex_of` itself (no item is of itself, and no annex is of an annex). `seen` is the place
    of the first item of each id."""
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not isinstance(it.get("id"), str) or seen.get(it["id"]) != i or not all(k in it for k in ANNEX_KEYS) or not isinstance(it["annex_of"], str):
            continue
        parent, here = it["annex_of"], f"library.items[{i}] ({it['id']!r}).annex_of"
        if parent == it["id"]:
            problems.add(here, f"{parent!r} is the item itself: an item that exists for another item is of another one")
        elif parent not in seen:
            problems.add(here, f"{parent!r} is not the id of an item of the library")
        elif ANNEX_KEYS[0] in items[seen[parent]]:
            problems.add(here, f"{parent!r} exists for another item itself (it has annex_of): an item is of a house, not of another annex")


def read_library(doc, tree: dict) -> list[dict]:
    """The items of a library document, checked against the (checked) `tree`, in arrival order: by `added_at`, ties by id.

    Each item comes back as `{"id", "title", "authors", "year", "doi", "added_at", "type", "tags", "topics"}` (`doi` None when the item has none;
    `topics` without repeats, in the order given; other keys dropped); an item that exists for another item has `annex_of` and `annex_form` as well, last, and any other has neither."""
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
        ok = _annex_keys(problems, where, it) and ok
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
            read = {"id": it["id"], "title": it["title"], "authors": list(it["authors"]), "year": year, "doi": doi,
                    "added_at": it["added_at"], "type": it["type"], "tags": list(it["tags"]), "topics": clean}
            if ANNEX_KEYS[0] in it:
                read.update({k: it[k] for k in ANNEX_KEYS})
            keyed.append((moment, it["id"], read))
    _annex_links(problems, doc["items"], seen)
    problems.raise_if_any()
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in keyed]


# ----------------------------------------------------------------------------------------------------- city ----
ROAD_CLASSES = ("大道", "路", "巷", "弄")
PLACE_KINDS = ("plaza", "street", "lot", "reserved", "annex")
PLAZA = "place:plaza"
REACH = 1e7  # cells: far beyond any city, and small enough that the arithmetic of a picture stays finite
COUNT = 10**12  # houses, arrivals, levels: far beyond any library
LANE_LEAST = 1.0  # cells: the least radius of a lane (a band, the ring road or a lap of it). A house of a lane is a polar cell of it and stands one cell inside or outside it, so a lane has an
# inside; and `picture` takes half a cell as the angle 0.5 / radius, which is infinity for the smallest number above 0 (1e323), and the sine of infinity a ValueError
LANE_WANTED = f"a number of at least {LANE_LEAST:g} (the radius of the lane)"


def _number(value, limit: float = REACH) -> bool:
    """A number (not a bool) of magnitude at most `limit`. The range comes first: `math.isfinite` raises OverflowError on an integer too large for a float
    (a JSON file can hold one), while the comparison is exact for any integer and false for NaN and infinity."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= limit and math.isfinite(value)


def _whole(value) -> bool:
    """A whole number (not a bool) of magnitude at most COUNT."""
    return isinstance(value, int) and not isinstance(value, bool) and abs(value) <= COUNT


def _shown(value) -> str:
    """`value` as it goes into a message: its repr cut at 40 characters, and for an integer of more than 64 bits only its size (an integer can have thousands
    of digits, and `repr` refuses more than 4300 of them)."""
    if isinstance(value, int) and abs(value).bit_length() > 64:
        return f"an integer of about {int(abs(value).bit_length() * 0.30103) + 1} digits"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _pair(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(_number(v) for v in value)


def _typed(problems: _Problems, where: str, record: dict, key: str, test, wanted: str, *, required: bool = True) -> None:
    """Add a problem unless `record[key]` passes `test`; a missing key is a problem only when it is `required`."""
    if key not in record:
        if required:
            problems.add(where, f"{key} is missing ({wanted})")
    elif not test(record[key]):
        problems.add(f"{where}.{key}", f"must be {wanted}, got {_shown(record[key])}")


def _is_text(value) -> bool:
    return isinstance(value, str)


def _check_street(problems: _Problems, where: str, p: dict) -> None:
    _typed(problems, where, p, "shape", _is_text, "a string")
    _typed(problems, where, p, "parent", _is_text, "the id of the street above, or of the plaza")
    _typed(problems, where, p, "address", lambda v: isinstance(v, list) and bool(v) and all(isinstance(x, str) for x in v), "a list of names, the last one the name of the road")
    _typed(problems, where, p, "level", _whole, "a whole number", required=False)
    _typed(problems, where, p, "weight", lambda v: _number(v, 1e12), "a number", required=False)
    _typed(problems, where, p, "road", _is_text, "a road id (a string)", required=False)
    _typed(problems, where, p, "label", _is_text, "a string", required=False)
    _typed(problems, where, p, "s_end", _number, "a number", required=False)
    rib = p.get("rib")
    if rib is not None:
        if not isinstance(rib, dict):
            problems.add(f"{where}.rib", f"must be an object, got {_shown(rib)}")
        elif rib.get("band") is not None:  # a cell of a band is the polar cell of its lane: `s`, the radius of the lane, divides
            _typed(problems, f"{where}.rib", rib, "band", _whole, "a whole number or null")
            _typed(problems, f"{where}.rib", rib, "s", lambda v: _number(v) and v >= LANE_LEAST, LANE_WANTED)
    if p.get("shape") == "ring":  # the ring road or a lap of it: a house on it is the polar cell of its lane, the radius of the lane divides
        ring = p.get("ring")
        if not isinstance(ring, dict):
            problems.add(f"{where}.ring", f"must be an object {{radius, ...}} for a street of shape ring, got {_shown(ring)}")
        else:
            _typed(problems, f"{where}.ring", ring, "radius", lambda v: _number(v) and v >= LANE_LEAST, LANE_WANTED)


def _check_house(problems: _Problems, where: str, p: dict) -> None:
    _typed(problems, where, p, "parent", _is_text, "the id of the street it stands on")
    if p["kind"] == "lot":
        _typed(problems, where, p, "article", _is_text, "the item id (a string)")
    _typed(problems, where, p, "facing", _number, "a bearing in degrees", required=False)


def _check_annex(problems: _Problems, where: str, p: dict) -> None:
    """An item that exists for another item: the place of the house it stands beside (a lot: the links say so), how it stands there, and its number among those of that house and form."""
    _typed(problems, where, p, "parent", _is_text, "the id of the house it stands beside (the place of its lot)")
    _typed(problems, where, p, "form", lambda v: isinstance(v, str) and v in ANNEX_FORMS, f"one of {', '.join(ANNEX_FORMS)}")
    _typed(problems, where, p, "rank", lambda v: _whole(v) and v >= 1, "a whole number, 1 or more")
    _typed(problems, where, p, "article", _is_text, "the item id (a string)")


def _check_places(problems: _Problems, name: str, places: dict) -> None:
    plaza = places.get(PLAZA)
    if not isinstance(plaza, dict) or plaza.get("kind") != "plaza":
        problems.add(f"{name}.places[{PLAZA!r}]", "the town hall plaza is missing (a place of kind plaza)")
    else:
        where = f"{name}.places[{PLAZA!r}]"
        _typed(problems, where, plaza, "label", _is_text, "a string")
        _typed(problems, where, plaza, "radius", lambda v: _number(v) and v >= 0, "a number, 0 or more")
        _typed(problems, where, plaza, "position", lambda v: isinstance(v, dict), "{x, z}")
    for pid, p in places.items():
        where = f"{name}.places[{pid!r}]"
        if not isinstance(p, dict) or p.get("kind") not in PLACE_KINDS:
            problems.add(where, f"must be an object whose kind is one of {', '.join(PLACE_KINDS)}")
            continue
        if "position" in p or p["kind"] in ("lot", "reserved"):
            pos = p.get("position")
            if not isinstance(pos, dict) or not _number(pos.get("x")) or not _number(pos.get("z")):
                problems.add(f"{where}.position", "must be {x, z}: two numbers")
        if p["kind"] == "street":
            _check_street(problems, where, p)
        elif p["kind"] in ("lot", "reserved"):
            _check_house(problems, where, p)
        elif p["kind"] == "annex":
            _check_annex(problems, where, p)


def _check_roads(problems: _Problems, name: str, roads: dict) -> None:
    for rid, r in roads.items():
        where = f"{name}.roads[{rid!r}]"
        if not isinstance(r, dict) or r.get("class") not in ROAD_CLASSES:
            problems.add(where, f"must be an object whose class is one of {', '.join(ROAD_CLASSES)}")
        elif not isinstance(r.get("points"), list) or len(r["points"]) < 2 or not all(_pair(q) for q in r["points"]):
            problems.add(f"{where}.points", "must be a list of at least two [x, z] pairs")


def _check_composition(problems: _Problems, name: str, comp: dict) -> None:
    where = f"{name}.composition"
    ring1 = comp.get("ring1")
    if not isinstance(ring1, list):
        problems.add(f"{where}.ring1", "must be a list of sectors {place, label, from, to}")
    else:
        for i, sector in enumerate(ring1):
            here = f"{where}.ring1[{i}]"
            if not isinstance(sector, dict):
                problems.add(here, "must be an object {place, label, from, to}")
                continue
            _typed(problems, here, sector, "place", _is_text, "a place id (a string)")
            _typed(problems, here, sector, "label", _is_text, "a string")
            _typed(problems, here, sector, "from", _number, "a bearing in degrees")
            _typed(problems, here, sector, "to", _number, "a bearing in degrees")
            _typed(problems, here, sector, "axis", _number, "a bearing in degrees", required=False)  # (a world built by hand: the bearing of the spoke, which need not be the middle)
    _typed(problems, where, comp, "buildings", _number, "a number")
    for key in ("measure", "streets"):
        if not isinstance(comp.get(key), dict):
            problems.add(f"{where}.{key}", "must be an object")
    if isinstance(comp.get("measure"), dict):
        for key in ("max_radius", "walk_mean", "walk_longest", "ring_lots"):
            _typed(problems, f"{where}.measure", comp["measure"], key, _number, "a number")
    if isinstance(comp.get("streets"), dict):
        _typed(problems, f"{where}.streets", comp["streets"], "total", _number, "a number")


def _check_coast(problems: _Problems, name: str, coast) -> None:
    if not isinstance(coast, dict):
        problems.add(f"{name}.coast", "must be an object {polygons: [...]}")
        return
    polygons = coast.get("polygons", [])
    if not isinstance(polygons, list):
        problems.add(f"{name}.coast.polygons", "must be a list of polygons")
        return
    for i, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or len(polygon) < 3 or not all(_pair(q) for q in polygon):
            problems.add(f"{name}.coast.polygons[{i}]", "must be a list of at least three [x, z] corners")


HAND_ENTRIES = ("filed", "renamed", "moved", "merged", "undone", "resized", "rule")  # the keys that tell the entries of a world built by hand from a split and an over


def _check_world(problems: _Problems, name: str, world: dict) -> None:
    where = f"{name}.world"
    rule = world.get("districts")
    if not isinstance(rule, dict) or not _whole(rule.get("max")) or not _whole(rule.get("min")):
        problems.add(f"{where}.districts", "must be an object with whole numbers max and min")
    chronicle = world.get("chronicle")
    if not isinstance(chronicle, list):
        problems.add(f"{where}.chronicle", "must be a list of entries")
        return
    for i, e in enumerate(chronicle):
        here = f"{where}.chronicle[{i}]"
        if not isinstance(e, dict):
            problems.add(here, "must be an object")
            continue
        by_hand = any(k in e for k in HAND_ENTRIES)  # (an entry of a world built by hand may come before the first house)
        _typed(problems, here, e, "seq", lambda v: _whole(v) and v >= (0 if by_hand else 1),
               "a whole number, 0 or more (the arrivals so far)" if by_hand else "a whole number, 1 or more (the arrival that caused it)")
        if "from" in e:  # a split
            _typed(problems, here, e, "from", _is_text, "a place id (a string)")
            _typed(problems, here, e, "label", _is_text, "the name of the new road (a string)")
            _typed(problems, here, e, "houses", lambda v: isinstance(v, list), "the list of the houses that moved")
            _typed(problems, here, e, "count_before", _whole, "a whole number")
            _typed(problems, here, e, "count_after", _whole, "a whole number")
        elif "over" in e:  # a road that became over
            _typed(problems, here, e, "over", _is_text, "a place id (a string)")
            _typed(problems, here, e, "count", _whole, "a whole number")
        elif "filed" in e:  # a house filed onto a road
            _typed(problems, here, e, "filed", _is_text, "the id of the house (a string)")
            _typed(problems, here, e, "left", _is_text, "the place it left (a string)")
            _typed(problems, here, e, "joined", _is_text, "the place it joined (a string)")
        elif "renamed" in e:  # a road renamed
            _typed(problems, here, e, "renamed", _is_text, "a place id (a string)")
            _typed(problems, here, e, "was", _is_text, "the old name (a string)")
            _typed(problems, here, e, "label", _is_text, "the new name (a string)")
        elif "moved" in e:  # a road moved with the roads and houses below it
            _typed(problems, here, e, "moved", _is_text, "a place id (a string)")
            _typed(problems, here, e, "below", _is_text, "the place it stands below now (a string)")
            _typed(problems, here, e, "was_below", _is_text, "the place it stood below (a string)")
            _typed(problems, here, e, "houses", lambda v: isinstance(v, list), "the list of the houses that were put again")
        elif "merged" in e:  # roads merged under a new road (avenues: under a new avenue)
            _typed(problems, here, e, "merged", _is_text, "a place id (a string)")
            _typed(problems, here, e, "label", _is_text, "the name of the new road (a string)")
            _typed(problems, here, e, "members", lambda v: isinstance(v, list) and all(_is_text(x) for x in v), "the list of the places that were merged (strings)")
            _typed(problems, here, e, "below", _is_text, "the place the new road stands below, the town hall for an avenue (a string)")
            _typed(problems, here, e, "took", _is_text, "the place whose direction or place the new road took (a string)")
            _typed(problems, here, e, "houses", lambda v: isinstance(v, list), "the list of the houses that were put again")
        elif "undone" in e:  # an event taken back
            _typed(problems, here, e, "undone", lambda v: _whole(v) and v >= 1, "the number of the event (a whole number, 1 or more)")
            _typed(problems, here, e, "of", _is_text, "the kind of that event (a string)")
        elif "resized" in e:  # the ring road has another radius and the world was laid out again
            _typed(problems, here, e, "resized", _is_text, "a place id (a string)")
            _typed(problems, here, e, "was_radius", lambda v: _number(v) and v > 0, "the radius before (a number above 0)")
            _typed(problems, here, e, "radius", lambda v: _number(v) and v > 0, "the radius now (a number above 0)")
            _typed(problems, here, e, "was_branches", lambda v: _whole(v) and v >= 1, "the branches before (a whole number)")
            _typed(problems, here, e, "branches", lambda v: _whole(v) and v >= 1, "the branches now (a whole number)")
            _typed(problems, here, e, "houses", lambda v: isinstance(v, list), "the list of the houses that were put again")
        elif "rule" in e:  # the district rule changed
            _typed(problems, here, e, "rule", lambda v: isinstance(v, dict) and _whole(v.get("max")) and _whole(v.get("min")) and _whole(v.get("branches")),
                   "an object with whole numbers max, min and branches")
        elif "annex" in e:  # an item that exists for another item stands beside its house
            _typed(problems, here, e, "annex", _is_text, "the id of the item (a string)")
            _typed(problems, here, e, "parent", _is_text, "the id of its house (a string)")
            _typed(problems, here, e, "form", lambda v: isinstance(v, str) and v in ANNEX_FORMS, f"one of {', '.join(ANNEX_FORMS)}")
        elif "absorbed" in e:  # a house that stood on a lot of its own is an annex now
            _typed(problems, here, e, "absorbed", _is_text, "the id of the house (a string)")
            _typed(problems, here, e, "parent", _is_text, "the id of the house it is beside now (a string)")
            _typed(problems, here, e, "form", lambda v: isinstance(v, str) and v in ANNEX_FORMS, f"one of {', '.join(ANNEX_FORMS)}")
            _typed(problems, here, e, "left", _is_text, "the place it left (a string)")
        else:
            problems.add(here, "must be a split (from, label, houses, count_before, count_after) or an over (over, count), or an annex (annex, parent, form) or an absorbed house "
                               f"(absorbed, parent, form, left), or one of the entries of a world built by hand ({', '.join(HAND_ENTRIES)})")


def _check_links(problems: _Problems, name: str, doc: dict) -> None:
    """The places point at each other: a street at the street above it or at the plaza, a house at the street it stands on. Follow every street up to the
    plaza (a street that is its own ancestor would make a picture loop for ever), and find the street of ring 1 that each house on the surface stands under."""
    places = doc["places"]
    sectors = doc["composition"]["ring1"]
    for i, sector in enumerate(sectors):
        place = places.get(sector["place"])
        if place is not None and place["kind"] != "street":
            problems.add(f"{name}.composition.ring1[{i}].place", f"{sector['place']!r} is a place of kind {place['kind']}, not a street")
    top: dict[str, str | None] = {}  # street -> the street of ring 1 above it (itself, when its parent is the plaza); None: its line of parents is broken
    for start, p in places.items():
        if p["kind"] != "street" or start in top:
            continue
        line: list[str] = []
        on_line: set[str] = set()
        cur, found = start, None
        while True:
            if cur in top:
                found = top[cur]
                break
            if cur in on_line:
                problems.add(f"{name}.places[{cur!r}].parent", "the parents lead round in a circle")
                break
            line.append(cur)
            on_line.add(cur)
            parent = places[cur]["parent"]
            if parent == PLAZA:
                found = cur
                break
            above = places.get(parent)
            if above is None or above["kind"] != "street":
                problems.add(f"{name}.places[{cur!r}].parent", f"{parent!r} is not a street, and not the plaza")
                break
            cur = parent
        for pid in line:
            top[pid] = found
    ring1 = {sector["place"] for sector in sectors}
    rings = {pid for pid, p in places.items() if p["kind"] == "street" and p.get("shape") == "ring" and p["parent"] == PLAZA}  # the ring road is a root of its own
    ring1 |= rings
    outside: dict[str, str] = {}  # a street that houses stand on, under a street that is no sector of ring 1 -> the first of those houses
    astray: dict[str, str] = {}  # a street that houses stand on, under the ring road, that is no lap of it -> the first of those houses
    for pid, p in places.items():
        if p["kind"] not in ("lot", "reserved"):
            continue
        above = places.get(p["parent"])
        if above is None or above["kind"] != "street":
            problems.add(f"{name}.places[{pid!r}].parent", f"{p['parent']!r} is not a street")
        elif top.get(p["parent"]) is not None and top[p["parent"]] not in ring1:
            outside.setdefault(p["parent"], pid)
        elif top.get(p["parent"]) in rings and above.get("shape") != "ring":  # a house of the ring road stands in a lap of it, the polar cell of the lane of the lap
            astray.setdefault(p["parent"], pid)
    for pid, p in places.items():  # an annex stands beside a house: its parent is the place of a lot
        if p["kind"] == "annex":
            above = places.get(p["parent"])
            if above is None or above["kind"] != "lot":
                problems.add(f"{name}.places[{pid!r}].parent", f"{p['parent']!r} is not a house (the place of a lot)")
    for street, house in outside.items():
        problems.add(f"{name}.places[{street!r}]", f"it stands under {top[street]!r}, which is not a sector in composition.ring1 (a house on it: {house!r})")
    for street, house in astray.items():
        problems.add(f"{name}.places[{street!r}]", f"it stands under the ring road {top[street]!r} and is no lap of it, a street of shape ring (a house on it: {house!r})")


def read_city(doc, name: str = "city") -> dict:
    """The city document, if it is the layout v4 file that `build` writes and every field that `picture` and `chronicle` read is there and of the right type;
    else `InputError` with the place of each problem. First the shapes (every place, road, sector, measure, coast polygon and chronicle entry), then the links:
    the parent of a street or a house is a place that exists, the parents of a street lead to the plaza without a circle, and every house on the surface
    stands under a sector of ring 1. The geometry itself is not re-checked: a city edited by hand can still be wrong in ways this does not see."""
    if not isinstance(doc, dict):
        raise InputError(f"{name}: not a city document: the file does not hold a JSON object")
    if doc.get("layout_version") != "v4":
        raise InputError(f"{name}: not a city document: expected the layout v4 file that `bibliopolis build` writes "
                         f"(layout_version is {doc.get('layout_version')!r}, not 'v4'); a library or a tree file is not a city")
    problems = _Problems()
    for key in ("places", "roads", "composition", "world"):
        if not isinstance(doc.get(key), dict):
            problems.add(f"{name}.{key}", "must be an object")
    problems.raise_if_any()
    _check_places(problems, name, doc["places"])
    _check_roads(problems, name, doc["roads"])
    _check_composition(problems, name, doc["composition"])
    if "coast" in doc:
        _check_coast(problems, name, doc["coast"])
    _check_world(problems, name, doc["world"])
    problems.raise_if_any()
    _check_links(problems, name, doc)
    problems.raise_if_any()
    return doc
