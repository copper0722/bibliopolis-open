"""The command line: `python -m bibliopolis build --library L.json --tree T.json --mode grow|mirror --out city.json`.

Exit status: 0 the city was written; 2 an input document or an option is wrong (the message says where); 1 a file could not be read or written.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import inputs
from ._version import __version__
from .city import build_city, summary
from .layout import render
from .plan import GROW, MAX_HOUSES, MIN_HOUSES, MODES


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m bibliopolis", description="Turn a literature collection into a city-state.")
    ap.add_argument("--version", action="version", version=f"bibliopolis {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build a city from a library and a topic tree and write it as a layout v4 document (JSON)")
    b.add_argument("--library", required=True, metavar="L.json", help='the library: {"items": [...]} (docs/format.md)')
    b.add_argument("--tree", required=True, metavar="T.json", help='the topic tree: {"nodes": [...]} (docs/format.md)')
    b.add_argument("--mode", choices=MODES, default=GROW,
                   help="grow: the roads open from the root zone by the district rule as the houses arrive; mirror: every topic that holds a "
                        "house is a road from the start (default: %(default)s)")
    b.add_argument("--out", required=True, metavar="city.json", help="where to write the city")
    b.add_argument("--max-houses", type=int, default=MAX_HOUSES, metavar="N", help="a road holds this many houses directly (default: %(default)s)")
    b.add_argument("--min-houses", type=int, default=MIN_HOUSES, metavar="N",
                   help="the least size of a group of houses that opens a road of its own (grow mode; default: %(default)s)")
    b.add_argument("--first", type=int, default=None, metavar="N",
                   help="a replay: place only the first N items in arrival order. The plan still reads the whole library, so this is the same city at an "
                        "earlier moment")
    return ap


def write_text_atomically(path: Path, text: str) -> None:
    """Write `text` to `path` (UTF-8, \\n line ends on every system) so that a reader never sees half a file. The file gets the permissions any
    file made by this user gets (the umask decides), not the private ones of a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        library = inputs.load_json(args.library)
        tree = inputs.load_json(args.tree)
        doc = build_city(library, tree, mode=args.mode, max_houses=args.max_houses, min_houses=args.min_houses, first=args.first)
        write_text_atomically(Path(args.out), render(doc))
    except (inputs.InputError, ValueError) as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 1
    s = summary(doc)
    print(f"wrote {args.out}: {s['houses']} houses on {s['roads']} roads, {s['underground']} under the town hall, "
          f"{s['splits']} splits, {s['over']} over (mode {s['mode']})", file=sys.stderr)
    return 0
