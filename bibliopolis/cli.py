"""The command line, three commands:

    python -m bibliopolis build --library L.json --tree T.json --mode grow|mirror --out city.json    build a city
    python -m bibliopolis picture --city city.json --out city.svg                                     draw it
    python -m bibliopolis chronicle --city city.json                                                  read what happened in it

Exit status: 0 done; 2 an input document or an option is wrong (the message says where); 1 a file could not be read or written.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import inputs, picture
from ._version import __version__
from .city import build_city, chronicle_lines, summary
from .layout import render
from .plan import GROW, MAX_HOUSES, MIN_HOUSES, MODES

MIN_PICTURE = 100  # pixels: smaller than this is a mistake, not a picture


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
    p = sub.add_parser("picture", help="draw a city as one SVG picture: the plan view, with the town hall, the roads, the houses and the names")
    p.add_argument("--city", required=True, metavar="city.json", help="a city that `build` wrote")
    p.add_argument("--out", required=True, metavar="city.svg", help="where to write the picture")
    p.add_argument("--title", default=None, help=f"the title above the picture (default: {picture.TITLE})")
    p.add_argument("--size", type=int, default=1800, metavar="PIXELS", help="the longest side of the map in pixels (default: %(default)s)")
    c = sub.add_parser("chronicle", help="print the chronicle of a city, one sentence per entry: every split and every road that became over")
    c.add_argument("--city", required=True, metavar="city.json", help="a city that `build` wrote")
    c.add_argument("--limit", type=int, default=None, metavar="N", help="print only the first N entries")
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


def build_command(args: argparse.Namespace) -> int:
    library = inputs.load_json(args.library)
    tree = inputs.load_json(args.tree)
    doc = build_city(library, tree, mode=args.mode, max_houses=args.max_houses, min_houses=args.min_houses, first=args.first)
    write_text_atomically(Path(args.out), render(doc))
    s = summary(doc)
    print(f"wrote {args.out}: {s['houses']} houses on {s['roads']} roads, {s['underground']} under the town hall, "
          f"{s['splits']} splits, {s['over']} over (mode {s['mode']})", file=sys.stderr)
    return 0


def picture_command(args: argparse.Namespace) -> int:
    if args.size < MIN_PICTURE:
        raise ValueError(f"--size must be at least {MIN_PICTURE} pixels, got {args.size}")
    city = inputs.read_city(inputs.load_json(args.city))
    text = picture.render(city, args.title, size=args.size)
    write_text_atomically(Path(args.out), text)
    print(f"wrote {args.out}: {len(text.encode('utf-8'))} bytes", file=sys.stderr)
    return 0


def chronicle_command(args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit < 1:
        raise ValueError(f"--limit must be at least 1, got {args.limit}")
    city = inputs.read_city(inputs.load_json(args.city))
    lines = chronicle_lines(city, args.limit)
    if not lines:
        print("the chronicle is empty: it has no split and no over entry", file=sys.stderr)
    for line in lines:
        print(line)
    return 0


COMMANDS = {"build": build_command, "picture": picture_command, "chronicle": chronicle_command}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (inputs.InputError, ValueError) as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 1
