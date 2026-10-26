#!/usr/bin/env python3
"""The golden files of the engine: three world files and their index.

    python3 examples/make_worlds.py [--out examples]

`scripted.world.json`, `scripted_nodes.world.json` and `scripted_merge.world.json` are logs of events (docs/world.md) that the helpers of `tests/hand_support.py` build: every
kind of event; OpenAlex topics, the node of a road and the rule `auto`; the first ring filled and merged. `worlds.json` is their index: for each file, the sha256 of the file and the
sha256 of the city that it folds to, as `python3 -m bibliopolis world fold` writes it. A port in another language folds the files and compares what it writes with those numbers.

Nothing in them is typed by hand. The tests make the files again and compare them with the committed ones byte for byte, and fold each to the pinned city: when the engine changes
on purpose, run this script, change the pins of tests/test_world_file.py, and commit the result. No city is committed: a derived city is rebuilt from its log.

Same input, same bytes. Standard library and the package only (and the helpers of the tests).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))  # the helpers that build the logs

from hand_support import scripted, scripted_merge, scripted_nodes  # noqa: E402

from bibliopolis import layout  # noqa: E402
from bibliopolis.canonical import dumps  # noqa: E402
from bibliopolis.journal import dumps_world, world_document  # noqa: E402

OUT = ROOT / "examples"
ABOUT = ("The golden files of the engine for a port (docs/world.md, 'For a port'). Each world file is a log of events; folding it gives a city whose text, as 'python3 -m bibliopolis "
         "world fold' writes it, has the sha256 below. tests/test_world_examples.py keeps these files, this index and the engine equal.")
WORLDS = (
    ("scripted.world.json", "scripted", scripted, "every kind of event but a merge: roads opened from the middle of the root zone, houses filed out of roads and out of the root zone, a road "
                                                 "with roads below it moved, a rename, a rule, an undo from the middle; items with no topic"),
    ("scripted_nodes.world.json", "scripted_nodes", scripted_nodes, "OpenAlex topics: a suggestion taken as it stands, roads that stand for nodes, a house with topics in two domains, "
                                                                    "the rule auto splitting a road three levels down in one event, a move of a road for a node, an undo"),
    ("scripted_merge.world.json", "scripted_merge", scripted_merge, "the first ring filled (13 avenues) and merged: a merge by suggestion and one by hand, avenues in the freed "
                                                                    "directions, an avenue moved below another road (its direction is free for the next), a rename, a filing, an undo"),
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def worlds() -> dict[str, str]:
    """file name -> its text: the three world files, then the index."""
    out: dict[str, str] = {}
    rows = []
    for name, helper, build, what in WORLDS:
        journal = build().journal
        text = dumps_world(world_document(journal))
        out[name] = text
        rows.append({"file": name, "helper": helper, "what": what, "events": len(journal.events), "world_sha256": sha256(text),
                     "city_sha256": sha256(layout.render(journal.state.city()))})
    lines = ["{", f' "about": {dumps(ABOUT)},', ' "worlds": [', ",\n".join("  " + dumps(row) for row in rows), " ]", "}"]
    out["worlds.json"] = "\n".join(lines) + "\n"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make the golden world files and their index.")
    ap.add_argument("--out", default=str(OUT), help="the directory to write into (default: examples)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in worlds().items():
        with open(out / name, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {out / name}: {len(text.encode('utf-8'))} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
