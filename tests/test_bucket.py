"""The root bucket (docs/format.md, docs/engine.md): a tree may name a root node, with everything below it, as the home of what a library has not sorted yet. It and what is
below it are nodes of the file and no places of the tree: no road, no street, no sector and no mirror road is ever made for them, and an item filed only there stands on the ring
road, however many there are. An item filed under a topic of the tree and under the bucket stands at the topic.

Synthetic trees and items, no file, no network. What is checked: the tree document (the key is kept, a wrong one is refused with its place), the tree view (the bucket is not held
by it), the address of an item, the cut (the bucket weighs nothing), the world in both modes (the ring, slot for slot as an item with no topic, the split at the 41st house, a ring of
bucket houses alone, the laps), the command line, and that no name of a bucket is written into the package: the name is data, and the tests run with three.
"""

import ast
import json
import random
from pathlib import Path

import pytest
from support import T, art, first_free, laps_of, make_tree, on_ring, roads_of, stamp

import bibliopolis
from bibliopolis import cli, inputs
from bibliopolis import layout as lay
from bibliopolis import plan as plan_mod
from bibliopolis import world as zw
from bibliopolis.city import build_world
from bibliopolis.document import world_layout
from bibliopolis.tree import TreeView, address_of, major_tag

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["unclassified", "inbox", "未分類"]  # the bucket of a player is called what the player calls it
BELOW = ("maybe", "maybe-deeper")  # the nodes below the bucket that `with_bucket` adds: one level down, two levels down
SPEC = {"med": T(0, a=T(25), b=T(16)), "pub": T(14), "x": T(3)}


def with_bucket(tree, name="unclassified"):
    """The tree document with a root bucket called `name`, a node one level below it ('maybe') and one two levels below it ('maybe-deeper')."""
    return {"nodes": [*tree["nodes"], {"id": name, "label": "To sort", "parent": None}, {"id": "maybe", "label": "Maybe", "parent": name},
                      {"id": "maybe-deeper", "label": "Deeper", "parent": "maybe"}], "bucket": name}


def bucket_items(n, name="unclassified", *, early=False, base=9000):
    """`n` items filed only under the bucket: in turn under the bucket itself, a node one level below it and one two levels below it. `early`: they arrive before every other item."""
    topics = [[name], [BELOW[0]], [BELOW[1]]]
    return [art(base + i, topics[i % 3], **({"added_at": stamp(-1000 + i)} if early else {})) for i in range(n)]


def library(*groups):
    return {"items": [item for group in groups for item in group]}


def city(items, tree, **kw):
    return build_world(library(items), tree, **kw)


def lots(world):
    return {p["article"]: p for p in world["places"].values() if p["kind"] == "lot"}


def streets_with_key(world, keys):
    return [pid for pid, p in world["places"].items() if p["kind"] == "street" and p.get("tag") in keys]


# ----------------------------------------------------------------------------------------- the tree document ----
def test_a_tree_may_name_a_root_bucket_and_the_reader_keeps_the_name_and_nothing_else_changes():
    tree = with_bucket(make_tree(SPEC)[0])
    got = inputs.read_tree(tree)
    assert got["bucket"] == "unclassified" and got["nodes"] == tree["nodes"], "the nodes of the bucket are nodes of the file"
    plain = make_tree(SPEC)[0]
    assert inputs.read_tree(plain) == plain, "no key: the tree as it always was"
    assert inputs.read_tree({**plain, "bucket": None}) == plain, "null is no bucket either"


@pytest.mark.parametrize("bucket, why", [
    (5, "tree.bucket: must be a string, got int"),
    ("", "tree.bucket: must not be empty"),
    ("a\nb", "tree.bucket: must not contain control characters"),
    ("nowhere", "tree.bucket: 'nowhere' is not the id of a node"),
    ("a", "tree.bucket: 'a' is not a root (its parent is 'med'): the bucket is a root of the tree"),
    ("maybe", "tree.bucket: 'maybe' is not a root (its parent is 'unclassified'): the bucket is a root of the tree"),
], ids=["a number", "empty", "a control character", "no such node", "a node below a topic", "a node below the bucket"])
def test_a_bucket_that_is_not_the_id_of_a_root_node_is_refused_with_its_place(bucket, why):
    tree = {**with_bucket(make_tree(SPEC)[0]), "bucket": bucket}
    with pytest.raises(inputs.InputError) as caught:
        inputs.read_tree(tree)
    assert why in str(caught.value).splitlines()


def test_the_nodes_of_the_bucket_are_topics_an_item_may_name_and_a_topic_the_file_lacks_is_still_a_mistake():
    tree = inputs.read_tree(with_bucket(make_tree(SPEC)[0]))
    items = inputs.read_library(library(bucket_items(3), [art(1, ["a"])]), tree)
    assert sorted(i["topics"][0] for i in items) == ["a", "maybe", "maybe-deeper", "unclassified"]
    with pytest.raises(inputs.InputError, match="'nowhere' is not the id of a node of the tree"):
        inputs.read_library(library([art(1, ["nowhere"])]), tree)


# ------------------------------------------------------------------------------------------- the tree view ----
@pytest.mark.parametrize("name", NAMES)
def test_the_bucket_and_what_is_below_it_are_not_places_of_the_tree(name):
    tv = TreeView(inputs.read_tree(with_bucket(make_tree(SPEC)[0], name)))
    plain = TreeView(make_tree(SPEC)[0])
    assert tv.bucket == name and plain.bucket is None
    assert tv.ids() == plain.ids() and tv.roots() == plain.roots() and len(tv) == len(plain), "a tree view with a bucket is the tree view without it"
    for node in (name, *BELOW):
        assert node not in tv and tv.in_bucket(node) and tv.parent(node) is None and tv.kids(node) == []
    assert not any(tv.in_bucket(n) for n in plain.ids()) and not tv.in_bucket("nowhere")
    assert tv.label(name) == "To sort", "the name of the bucket is the label of its node"


def test_a_name_that_is_no_root_of_a_tree_view_names_no_bucket():
    """The reader refuses such a name in a file; a hand-made tree handed to the view straight is read as the tree it has, with no bucket."""
    tree = make_tree(SPEC)[0]
    for named in ("nowhere", "a", None):
        tv = TreeView({**tree, "bucket": named})
        assert tv.bucket is None and tv.ids() == TreeView(tree).ids() and not tv.in_bucket("a")


# --------------------------------------------------------------------------------------------- the address ----
@pytest.mark.parametrize("name", NAMES)
def test_an_item_filed_only_under_the_bucket_has_the_bucket_for_its_address(name):
    tv = TreeView(with_bucket(make_tree(SPEC)[0], name))
    for topics in ([name], ["maybe"], ["maybe-deeper"], ["maybe", "maybe-deeper"], ["maybe-deeper", "nowhere"]):
        assert address_of(tv, {"topics": topics}) == name, topics
        assert major_tag(tv, {"topics": topics}) is None, "no place of the tree"


def test_one_topic_of_the_tree_settles_the_address_whatever_else_the_item_is_filed_under():
    """The confusable negatives of the positive: a topic of depth one beats a node two levels below the bucket, and the deepest topic still wins among topics."""
    tv = TreeView(with_bucket(make_tree(SPEC)[0]))
    assert address_of(tv, {"topics": ["pub", "maybe-deeper"]}) == "pub"
    assert address_of(tv, {"topics": ["maybe-deeper", "x"]}) == "x"
    assert address_of(tv, {"topics": ["unclassified", "a", "med"]}) == "a" and address_of(tv, {"topics": ["a", "b"]}) == "a", "the deepest, then the lower id"
    assert address_of(tv, {"topics": ["maybe", "med"]}) == major_tag(tv, {"topics": ["maybe", "med"]}) == "med"


def test_without_a_bucket_the_address_is_what_it_was_and_an_item_with_no_topic_has_none():
    plain = TreeView(make_tree(SPEC)[0])
    assert address_of(plain, {"topics": []}) is None and address_of(plain, {}) is None
    for topics in (["a"], ["a", "b"], ["pub", "med"], ["nowhere"], []):
        assert address_of(plain, {"topics": topics}) == major_tag(plain, {"topics": topics})
    assert address_of(TreeView(with_bucket(make_tree(SPEC)[0])), {"topics": []}) is None, "a bucket gives no address to an item that is not filed under it"


# ------------------------------------------------------------------------------------------ cut and plan ----
@pytest.mark.parametrize("mode", [plan_mod.GROW, plan_mod.MIRROR])
def test_the_bucket_weighs_nothing_so_the_plan_of_a_library_is_the_same_with_any_number_of_houses_in_it(mode):
    tree, items = make_tree(SPEC)
    tv, plain = TreeView(with_bucket(tree)), TreeView(tree)
    want = plan_mod.build_plan(plain, items, mode=mode)
    for n in (0, 7, 300):
        assert plan_mod.build_plan(tv, [*items, *bucket_items(n)], mode=mode) == want, n


def test_a_tree_with_one_real_root_and_a_bucket_still_has_that_root_for_its_centre():
    tree, items = make_tree({"only": T(5, left=T(30), right=T(12))})
    plan = plan_mod.build_plan(TreeView(with_bucket(tree)), [*items, *bucket_items(20)])
    assert plan["params"]["centre_tag"] == "only" == plan_mod.build_plan(TreeView(tree), items)["params"]["centre_tag"]


# ------------------------------------------------------------------------------------ the world: grow ----
@pytest.mark.parametrize("name", NAMES)
def test_a_house_whose_only_topic_is_the_bucket_stands_on_the_ring_road_with_the_bucket_for_its_address(name):
    tree, items = make_tree(SPEC)
    mine = bucket_items(30, name)
    _plan, _tv, world, _items = city([*items, *mine], with_bucket(tree, name))
    standing = lots(world)
    assert len(standing) == len(items) + 30
    for a in mine:
        lot = standing[a["id"]]
        assert (lot["street"], lot["parent"], lot["tag"]) == (zw.ROOT_PLACE, zw.ROOT_PLACE, name), "on lap 1 of the ring road, and the address is the bucket"
    assert streets_with_key(world, {name, *BELOW}) == [], "the bucket has no road, and nothing below it either"
    assert bibliopolis.build_city(library(items, mine), with_bucket(tree, name))["composition"]["measure"]["ring_lots"] >= 30


@pytest.mark.parametrize("mode", [plan_mod.GROW, plan_mod.MIRROR])
def test_a_house_of_the_bucket_is_placed_exactly_like_an_item_with_no_topic_the_documents_are_the_same_bytes(mode):
    """The bucket is only the name of where an item with no place stands: the city a library with a bucket makes is the city of the same library with those items filed under nothing."""
    tree, items = make_tree(SPEC)
    mine = bucket_items(45)
    filed = bibliopolis.build_city(library(items, mine), with_bucket(tree), mode=mode)
    unfiled = bibliopolis.build_city(library(items, [{**a, "topics": []} for a in mine]), tree, mode=mode)
    assert lay.render(filed) == lay.render(unfiled)
    assert filed["composition"]["measure"]["ring_lots"] >= 45


def test_an_item_filed_under_a_topic_and_under_the_bucket_stands_at_the_topic():
    tree, items = make_tree(SPEC)
    both = [{**a, "topics": [*a["topics"], "maybe-deeper"]} for a in items]
    assert lay.render(bibliopolis.build_city(library(both), with_bucket(tree))) == lay.render(bibliopolis.build_city(library(items), tree))


def test_past_the_rule_the_topic_group_opens_a_road_and_the_bucket_houses_that_stay_keep_their_lots():
    """The ring holds `max` houses and the 41st makes the largest group of at least `min` open a road; the houses that stay do not move. The bucket houses can never be
    that group: they have no topic of the tree, so the group that leaves is the one of the topic houses."""
    tree, items = make_tree(SPEC)
    mine = bucket_items(30, early=True)
    marked = with_bucket(tree)
    _p, _tv, at_forty, _i = city([*items, *mine], marked, first=40)
    _p, _tv, at_41, _i = city([*items, *mine], marked, first=41)
    assert at_forty["chronicle"] == [] and lots(at_forty).keys() == {a["id"] for a in mine} | {a["id"] for a in items[:10]}
    assert {lot["street"] for lot in lots(at_forty).values()} == {zw.ROOT_PLACE}
    (entry,) = at_41["chronicle"]
    assert (entry["seq"], entry["from"], entry["count_before"], entry["count_after"]) == (41, zw.ROOT_PLACE, 41, 30), "the 41st house opened one road, from the ring"
    before, after = lots(at_forty), lots(at_41)
    assert {after[a["id"]]["street"] for a in mine} == {zw.ROOT_PLACE} and {after[a["id"]]["tag"] for a in mine} == {"unclassified"}
    assert all(after[a["id"]] == before[a["id"]] for a in mine), "the houses that stay keep their lots"
    assert {aid for aid in before if after[aid]["street"] != before[aid]["street"]} == {a["id"] for a in items[:10]}, "the topic houses of the ring are the group that left"
    assert after[items[10]["id"]]["street"] == entry["to"], "and the 41st house stands on the new road with them"


def test_a_ring_of_bucket_houses_alone_cannot_split_it_goes_over_once_and_goes_on_as_a_lap():
    """The bucket has no road to open and no child to make a group of, so past `max` the ring is over (the chronicle says so once) and a house never loses its address: when
    lap 1 is full the road goes on as lap 2."""
    tree, items = make_tree({"med": T(0, a=T(3), b=T(2))})
    mine = bucket_items(400)
    marked = with_bucket(tree)
    _p, _tv, empty, _i = city([*items, *mine], marked, first=0)
    assert empty["places"][zw.ROOT_PLACE]["ring"]["slots"] < 400, "the test needs more houses than lap 1 holds"
    _p, _tv, world, _i = city([*items, *mine], marked)
    assert [(e["over"], e["count"]) for e in world["chronicle"]] == [(zw.ROOT_PLACE, 41)], "over once, at the 41st house: nothing was split"
    assert world["places"][zw.ROOT_PLACE].get("over") is True
    assert {p["street"] for p in on_ring(world)} == {zw.ROOT_PLACE} and len(on_ring(world)) == len(items) + 400
    assert len(laps_of(world)) >= 2 and {p["parent"] for p in on_ring(world)} == set(laps_of(world)), "the next houses stand on lap 2 of the same road"
    assert roads_of(world) == {}, "no road opened: the topics are too thin and the bucket is no road"


# ----------------------------------------------------------------------------------- the world: mirror ----
def test_in_mirror_mode_the_bucket_is_no_road_and_a_topic_the_item_is_also_filed_under_still_is():
    tree, items = make_tree(SPEC)
    both = [{**a, "topics": [*a["topics"], "maybe"]} for a in items[:5]] + items[5:]
    mine = bucket_items(12)
    plan, _tv, world, _i = city([*both, *mine], with_bucket(tree), mode="mirror")
    assert not {"unclassified", *BELOW} & set(plan["roads"]), "a mirror road for every topic an item is filed under: the bucket is no topic of the tree"
    assert streets_with_key(world, {"unclassified", *BELOW}) == []
    want, _tv, _world, _i = city(items, tree, mode="mirror")
    assert plan["roads"] == want["roads"]
    assert {a["id"] for a in mine} <= {p["article"] for p in on_ring(world)}


# ---------------------------------------------------------------------------------------- the command ----
def test_the_build_command_reads_a_tree_that_names_a_bucket_and_refuses_one_that_names_nothing(tmp_path, capsys):
    tree, items = make_tree(SPEC)
    files = {"tree.json": with_bucket(tree, "inbox"), "library.json": library(items, bucket_items(25, "inbox"))}
    for name, doc in files.items():
        (tmp_path / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "city.json"
    assert cli.main(["build", "--library", str(tmp_path / "library.json"), "--tree", str(tmp_path / "tree.json"), "--mode", "grow", "--out", str(out)]) == 0
    summary = bibliopolis.summary(json.loads(out.read_text(encoding="utf-8")))
    assert summary["houses"] == len(items) + 25 and summary["ring"] >= 25
    (tmp_path / "bad.json").write_text(json.dumps({**files["tree.json"], "bucket": "nowhere"}), encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["build", "--library", str(tmp_path / "library.json"), "--tree", str(tmp_path / "bad.json"), "--out", str(tmp_path / "x.json")]) == 2
    assert "tree.bucket: 'nowhere' is not the id of a node" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


# ------------------------------------------------------------------ cities the first tests do not reach ----
@pytest.mark.parametrize("mode", [plan_mod.GROW, plan_mod.MIRROR])
def test_a_tree_whose_only_root_is_the_bucket_holds_no_place_and_the_city_is_the_ring_road_alone(mode):
    tree = {"nodes": [{"id": "inbox", "label": "To sort", "parent": None}, {"id": "later", "label": "Later", "parent": "inbox"}], "bucket": "inbox"}
    tv = TreeView(inputs.read_tree(tree))
    assert (tv.ids(), tv.roots(), len(tv), tv.bucket) == ([], [], 0, "inbox"), "nothing is held: every node of the file is the bucket or below it"
    items = [art(i, ["inbox"] if i % 2 else ["later"]) for i in range(1, 61)]
    filed = bibliopolis.build_city(library(items), tree, mode=mode)
    unfiled = bibliopolis.build_city(library([{**a, "topics": []} for a in items]), {"nodes": []}, mode=mode)
    assert lay.render(filed) == lay.render(unfiled), "the city of a tree with nothing in it but the bucket is the city of a tree with nothing in it"
    assert filed["composition"]["measure"]["ring_lots"] == filed["world"]["houses"] == 60 and filed["composition"]["streets"]["total"] == 1
    assert plan_mod.build_plan(tv, inputs.read_library(library(items), inputs.read_tree(tree)), mode=mode)["params"]["centre_tag"] is None


def test_the_city_does_not_depend_on_the_order_of_the_files_or_on_how_the_arrivals_are_cut_into_calls():
    """Every topic is too thin to open a road, so only the ring is used and the world cannot depend on the size of a call (a rib that opens is sized to its call; the ring has none)."""
    tree, items = make_tree({"med": T(0, a=T(4), b=T(3)), "x": T(3)})
    marked = with_bucket(tree)
    everyone = [*items, *bucket_items(70)]
    want = lay.render(bibliopolis.build_city(library(everyone), marked, with_coast=False))
    rng = random.Random(34)
    orders = [list(reversed(marked["nodes"]))]  # the children of the bucket before their parents, then three shuffles
    for _ in range(3):
        orders.append(list(marked["nodes"]))
        rng.shuffle(orders[-1])
    for nodes in orders:  # the order of the items and of the nodes in the files does not matter
        files = list(everyone)
        rng.shuffle(files)
        assert lay.render(bibliopolis.build_city(library(files), {**marked, "nodes": nodes}, with_coast=False)) == want
    checked = inputs.read_tree(marked)
    arrivals, tv = inputs.read_library(library(everyone), checked), TreeView(checked)
    plan = plan_mod.build_plan(tv, arrivals)
    for size in (1, 7, 40, len(arrivals)):  # the arrivals as calls of one, of seven, of forty, and one call
        world = zw.new_world(plan)
        for start in range(0, len(arrivals), size):
            world = zw.apply_delta(world, zw.assign(plan, tv, world, arrivals[start:start + size])["delta"])
        for entry in world["chronicle"]:  # (what build_world adds)
            entry["at"] = arrivals[entry["seq"] - 1]["added_at"]
        assert lay.render(world_layout(world, with_coast=False)) == want, size
    assert [e["over"] for e in json.loads(want)["world"]["chronicle"]] == [zw.ROOT_PLACE], "the ring was over, and nothing opened"


def test_a_later_bucket_house_takes_the_first_free_slot_in_fill_order_and_the_first_slots_are_the_ones_the_split_freed():
    """The ring keeps the houses that stay where they are and frees only the lots of the group that leaves; a slot a split freed is taken again in the fill order, here by the houses
    that arrive after the 41st, filed only under the bucket."""
    tree, items = make_tree(SPEC)
    early = bucket_items(30, early=True)
    late = [art(9500 + k, ["maybe"], added_at=stamp(11 + (k + 1) / 10)) for k in range(5)]  # after the 41st house (the 11th item of the topic `a`), before the 12th
    marked, everyone = with_bucket(tree), [*items, *early, *late]
    _p, _tv, at_forty, _i = city(everyone, marked, first=40)
    _p, _tv, at_41, _i = city(everyone, marked, first=41)
    freed = {lots(at_forty)[a["id"]]["slot"] for a in items[:10]}
    taken = {lot["slot"] for lot in lots(at_41).values() if lot["street"] == zw.ROOT_PLACE}
    assert len(freed) == 10 and not freed & taken and len(taken) == 30, "ten slots stand free on lap 1 after the split"
    slots = at_41["places"][zw.ROOT_PLACE]["ring"]["slots"]
    took = []
    for k, a in enumerate(late):
        _p, _tv, world, _i = city(everyone, marked, first=42 + k)
        want = first_free([slots], {(0, s) for s in taken})[1]  # stated apart from the engine (tests/support.py)
        got = lots(world)[a["id"]]
        assert (got["street"], got["parent"], got["slot"], got["tag"]) == (zw.ROOT_PLACE, zw.ROOT_PLACE, want, "unclassified"), k
        taken.add(want)
        took.append(want)
    assert set(took) <= freed and len(set(took)) == 5, "the five houses stand in five of the ten slots the topic houses left"


@pytest.mark.parametrize("mode", [plan_mod.GROW, plan_mod.MIRROR])
def test_a_bucket_of_null_makes_the_same_city_as_no_key_whole_city_in_every_replay(mode):
    tree, items = make_tree(SPEC)
    everyone = library(items, [{**a, "topics": []} for a in bucket_items(40)])
    for first in (None, 0, 41, 60):
        kept = bibliopolis.build_city(everyone, tree, mode=mode, first=first)
        null = bibliopolis.build_city(everyone, {**tree, "bucket": None}, mode=mode, first=first)
        assert lay.render(kept) == lay.render(null), first


def test_the_format_page_limits_the_address_and_the_mirror_road_to_the_topics_outside_the_bucket():
    row = next(line for line in (ROOT / "docs" / "format.md").read_text(encoding="utf-8").splitlines() if line.startswith("| `topics` |"))
    assert "the deepest of the topics outside the root bucket" in row and "every topic outside the root bucket" in row


# ----------------------------------------------------------------------------------- the name is data ----
def test_no_name_of_a_bucket_is_written_into_the_package():
    """The bucket is called what the tree says: a string constant of the package equal to a name a player might give it would be a name written in."""
    found = []
    for path in sorted((ROOT / "bibliopolis").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() in {"unclassified", "inbox", "unsorted", "to sort", "未分類"}:
                found.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert found == []
