"""The command line, four commands:

    python -m bibliopolis build --library L.json --tree T.json --mode grow|mirror --out city.json    build a city
    python -m bibliopolis picture --city city.json --out city.svg                                     draw it
    python -m bibliopolis chronicle --city city.json                                                  read what happened in it
    python -m bibliopolis world new|import|export|fold                                                a world built by hand (docs/world.md)

Exit status: 0 done; 2 an input document or an option is wrong, or the world refuses (the message says where); 1 a file could not be read or written.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from . import inputs, picture, store
from ._version import __version__
from .city import build_city, chronicle_lines, summary
from .journal import dumps_world, load_world_file, world_document
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
    w = sub.add_parser("world", help="a world built by hand: a log of events in a SQLite file, a world file (JSON) to move it, and the city that the log folds to")
    ws = w.add_subparsers(dest="world_command", required=True)
    where = f"the SQLite file of the world (default: {store.WORLD_NAME} in the home folder, $BIBLIOPOLIS_HOME or ~/Bibliopolis, made on first use)"
    n = ws.add_parser("new", help="make a new, empty world")
    n.add_argument("--world", metavar="PATH", help=where)
    n.add_argument("--max-houses", type=int, default=MAX_HOUSES, metavar="N", help="the most a road is meant to hold; `crowded` lists what holds more (default: %(default)s)")
    n.add_argument("--min-houses", type=int, default=MIN_HOUSES, metavar="N", help="the least a new road takes (default: %(default)s)")
    n.add_argument("--auto", action="store_true", help="open a road by itself for the largest group of the root zone after each arrival that leaves it above the most")
    i = ws.add_parser("import", help="read a world file into a new SQLite world (an existing world is never overwritten)")
    i.add_argument("file", metavar="FILE", help="the world file (JSON)")
    i.add_argument("--world", metavar="PATH", help=where)
    e = ws.add_parser("export", help="write the world as a world file (JSON): the same bytes that `import` would read (never over a SQLite file, so never over the world itself)")
    e.add_argument("file", metavar="FILE", help="where to write the world file")
    e.add_argument("--world", metavar="PATH", help=where)
    f = ws.add_parser("fold", help="fold the log of the world into its city and write it as `build` does (the layout v4 document; never over a SQLite file)")
    f.add_argument("--out", required=True, metavar="city.json", help="where to write the city")
    f.add_argument("--world", metavar="PATH", help=where)
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


def world_path(args: argparse.Namespace) -> Path:
    """The SQLite file a `world` command works on: `--world`, else the file of the home folder (which is made, and said, on first use)."""
    if args.world:
        return Path(args.world)
    folder, created = store.home()
    print(f"home: {folder}" + (" (made now)" if created else ""), file=sys.stderr)
    return folder / store.WORLD_NAME


def world_command(args: argparse.Namespace) -> int:
    path = world_path(args)
    if args.world_command == "new":
        made = store.Store.create(path, {"max": args.max_houses, "min": args.min_houses, "auto": args.auto})
        rule = made.journal().rule
        print(f"made {path}: a world with no house yet (at most {rule['max']}, at least {rule['min']}, auto {'on' if rule['auto'] else 'off'})", file=sys.stderr)
    elif args.world_command == "import":
        journal = load_world_file(args.file)
        store.Store.import_journal(path, journal)
        print(f"read {args.file} into {path}: {len(journal.events)} events, {len(journal.state.items)} houses", file=sys.stderr)
    elif args.world_command == "export":
        store.check_output(args.file, path)
        journal = store.Store(path).journal()
        write_text_atomically(Path(args.file), dumps_world(world_document(journal)))
        print(f"wrote {args.file}: {len(journal.events)} events, {len(journal.items())} items", file=sys.stderr)
    else:
        store.check_output(args.out, path)
        journal = store.Store(path).journal()
        doc = journal.state.city()
        write_text_atomically(Path(args.out), render(doc))
        s = summary(doc)
        print(f"wrote {args.out}: {s['houses']} houses on {s['roads']} roads, {s['underground']} under the town hall, "
              f"{s['splits']} splits, {s['over']} over (mode {s['mode']})", file=sys.stderr)
    return 0


COMMANDS = {"build": build_command, "picture": picture_command, "chronicle": chronicle_command, "world": world_command}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (inputs.InputError, ValueError) as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error) as exc:
        print(f"bibliopolis: {exc}", file=sys.stderr)
        return 1
