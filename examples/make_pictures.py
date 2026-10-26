#!/usr/bin/env python3
"""The pictures of the README: `concept.svg`, `growth.svg` and `modes.svg`, made from the synthetic sample.

    python3 examples/make_pictures.py [--out docs/images]

Nothing in them is drawn by hand. `growth.svg` and `modes.svg` are the sample of `examples/` (80 topics, 600 items) built by the engine and drawn by
`bibliopolis.picture`; `concept.svg` is a tiny invented city (4 topics, about 50 items, defined below) built the same way, with labels laid over it at
places the document gives. The numbers in the captions come from the cities, so a picture cannot say something the engine does not do. The tests make the files
again and compare them with the committed ones byte for byte: when the engine or the sample changes, run this script and commit the result.

Same input, same bytes. Standard library and the package only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bibliopolis import build_city, picture, summary  # noqa: E402

OUT = ROOT / "docs" / "images"
STEPS = (40, 41, 150, 600)  # the growth sheet: the ring road alone, the first road, a few roads, the whole sample


def sample() -> tuple[dict, dict]:
    """(tree, library) of examples/."""
    return (json.loads((ROOT / "examples" / "tree.json").read_text(encoding="utf-8")),
            json.loads((ROOT / "examples" / "library.json").read_text(encoding="utf-8")))


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def topic_roads(s: dict) -> int:
    """The roads of a city that stand for topics: the streets of its summary but the ring road, which is the root of them all and no topic's."""
    return s["roads"] - 1


def latest_split(city: dict) -> dict | None:
    splits = [e for e in city["world"]["chronicle"] if "from" in e]
    return splits[-1] if splits else None


# ------------------------------------------------------------------------------------------------------- growth ----
def growth_caption(n: int, city: dict) -> list[str]:
    """Three lines for the panel of the city after `n` houses: what the picture shows, in English and in Traditional Chinese, from the city itself."""
    s = summary(city)
    split = latest_split(city)
    head = f"After {n} houses · 蓋到第 {n} 棟"
    if split is None:
        return [head, f"No road yet: all {s['ring']} are on the ring road.", f"還沒有路：{s['ring']} 棟全在圓環上。"]
    moved = len(split["houses"])
    if s["splits"] == 1:  # (the ring road is a road too: the first road that opens from it is the first split)
        return [head, f"The first road opens: {split['label']} takes {moved} (orange).", f"第一條路開出來：{split['label']} 搬走 {moved} 棟（橘色）。"]
    roads = topic_roads(s)
    return [head, f"{plural(roads, 'road', 'roads')}; newest: {split['label']}, {moved} houses (orange).",
            f"{roads} 條路；最新的 {split['label']} 搬走 {moved} 棟（橘色）。"]


def growth() -> str:
    """The `grow` city of the sample at four moments, one frame: the ring road alone with its houses at first, then the first road, then the splits."""
    tree, library = sample()
    panels = []
    for n in STEPS:
        city = build_city(library, tree, mode="grow", first=n)
        split = latest_split(city)
        panels.append(picture.Panel(city, growth_caption(n, city), set(split["houses"]) if split else None))
    return picture.sheet(panels, columns=2, panel_px=430, label_px=(11.0, 0.0, 11.0))


# -------------------------------------------------------------------------------------------------------- modes ----
def modes() -> str:
    """The same 600 items as a city from zero (`grow`) and as the street plan of the tree (`mirror`), on one frame."""
    tree, library = sample()
    mirror, grown = build_city(library, tree, mode="mirror"), build_city(library, tree, mode="grow")
    m, g = summary(mirror), summary(grown)
    panels = [
        picture.Panel(mirror, ["Your library as a city · 把你的文獻庫變成城邦", f"mirror: {topic_roads(m)} roads, one for every topic that holds a house.",
                               f"mirror：{topic_roads(m)} 條路，有文獻的主題，每一個都是路。"]),
        picture.Panel(grown, ["A city from zero · 從零開始建城邦", f"grow: {topic_roads(g)} roads, opened one by one as the houses arrived.",
                              f"grow：{topic_roads(g)} 條路，隨文獻抵達，一條一條開出來。"]),
    ]
    return picture.sheet(panels, columns=2, panel_px=500, label_px=(12.0, 0.0, 12.0))


# ------------------------------------------------------------------------------------------------------- concept ----
CONCEPT_TREE = {"nodes": [
    {"id": "computing", "label": "Computing", "parent": None},
    {"id": "networks", "label": "Networks", "parent": "computing"},
    {"id": "life", "label": "Life sciences", "parent": None},
    {"id": "history", "label": "History", "parent": None},
]}
CONCEPT_HOUSES = (("computing", 12), ("networks", 12), ("life", 16), ("history", 8), (None, 5))  # (topic, articles); None: no topic yet


def concept_library() -> dict:
    items = []
    for topic, count in CONCEPT_HOUSES:
        for _ in range(count):
            n = len(items) + 1
            items.append({"id": f"article-{n:02d}", "title": f"Sample article {n}", "authors": ["A. Writer"], "year": 2024,
                          "added_at": f"2024-{1 + (n - 1) // 28:02d}-{1 + (n - 1) % 28:02d}", "type": "article", "tags": [], "topics": [topic] if topic else []})
    return {"items": items}


def along(points: list[list[float]], fraction: float) -> tuple[float, float]:
    """The point at `fraction` of the length of a polyline."""
    legs = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    want = sum(legs) * fraction
    for (ax, az), (bx, bz), leg in zip(points, points[1:], legs):
        if want <= leg or leg == 0:
            t = want / leg if leg else 0.0
            return ax + (bx - ax) * t, az + (bz - az) * t
        want -= leg
    return points[-1][0], points[-1][1]


def concept() -> str:
    """A small city with its parts named: a house, a road, a branch road, the town hall and the ring road round it."""
    city = build_city(concept_library(), CONCEPT_TREE, mode="mirror")
    places, roads = city["places"], city["roads"]
    frame, scale, look = picture.fit([city], 500, (15.0, 12.0, 17.0), pad=7.0)
    x0, z0 = frame[0], frame[2]
    w, h = (frame[1] - frame[0]) * scale, (frame[3] - frame[2]) * scale
    left, right, top, bottom = 300.0, 250.0, 78.0, 18.0
    width, height = left + w + right, top + h + bottom

    def px(point: tuple[float, float]) -> tuple[float, float]:
        return left + (point[0] - x0) * scale, top + (point[1] - z0) * scale

    radius = places[picture.PLAZA]["radius"]
    ring_radius = places["place:root"]["ring"]["radius"]
    life = [p for p in places.values() if p["kind"] == "lot" and picture.ring1_place(places, p["parent"]) == "place:tag:life"]
    east = max(life, key=lambda p: (p["position"]["x"], p["article"]))  # the house farthest east: no name stands on it
    notes = [  # (the place it names, in cells; the side of the picture; the words: English, Chinese, ...)
        (along(roads["road:place:lane:networks:2"]["points"], 0.9), "left", ["a sub-topic = a branch road", "子主題＝岔路"]),
        ((-radius * 0.72, -radius * 0.72), "left", ["the town hall = the root", "市政廳＝根"]),
        ((0.0, ring_radius), "left", ["the ring road", "articles with no topic yet", "圓環：還沒有主題的文獻"]),
        (along(roads["road:place:tag:history"]["points"], 0.45), "right", ["a topic = a road", "主題＝路"]),
        ((east["position"]["x"], east["position"]["z"]), "right", ["an article = a house", "一篇文獻＝一棟房子"]),
    ]
    out: list[str] = []
    add = out.append
    num, esc = picture.num, picture.esc
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(width)} {num(height)}" width="{num(width)}" height="{num(height)}" '
        f'font-family="{picture.FONT}">')
    add('<rect width="100%" height="100%" fill="#ffffff"/>')
    add(f'<text x="18" y="32" font-size="24" fill="{picture.INK}">{esc(picture.TITLE)}</text>')
    add(f'<text x="18" y="58" font-size="16" fill="{picture.GREY}">A collection of articles becomes a city-state. 把收藏的文獻蓋成一座城邦。</text>')
    picture.draw_panel(add, city, frame, scale, look, left, top)
    leading = 21.0
    for where in ("left", "right"):
        mine = sorted(((px(anchor), words) for anchor, side_of, words in notes if side_of == where), key=lambda note: note[0][1])
        spots, floor = [], top + 20.0  # each set of words stands level with the place it names, pushed down where two would overlap
        for (_ax, az), words in mine:
            spots.append(max(floor, az - 10.0 * (len(words) - 1)))
            floor = spots[-1] + leading * len(words) + 8.0
        overflow = spots[-1] + leading * (len(mine[-1][1]) - 1) - (top + h - 10.0) if spots else 0.0
        if overflow > 0:  # ... and the whole column is lifted when it runs past the bottom
            spots = [max(top + 20.0, y - overflow) for y in spots]
        for ((ax, az), words), y in zip(mine, spots):
            lx = left - 16.0 if where == "left" else left + w + 16.0
            sign = -1.0 if where == "left" else 1.0
            mid = y + 10.0 * (len(words) - 1) - 5.0  # where the leader leaves the words: a short run level with them, then straight to the place
            leader = f"M{num(lx - sign * 8.0)},{num(mid)}L{num(lx - sign * 24.0)},{num(mid)}L{num(ax)},{num(az)}"
            add(f'<path d="{leader}" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
            add(f'<path d="{leader}" fill="none" stroke="{picture.INK}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>')
            add(f'<circle cx="{num(ax)}" cy="{num(az)}" r="4.5" fill="#ffffff" stroke="{picture.INK}" stroke-width="1.6"/>')
            for k, line in enumerate(words):
                weight = ' font-weight="600"' if k == 0 else ""
                add(f'<text x="{num(lx)}" y="{num(y + k * leading)}" font-size="{16 if k == 0 else 15}" text-anchor="{"end" if where == "left" else "start"}" '
                    f'fill="{picture.INK if k == 0 else picture.GREY}"{weight}>{esc(line)}</text>')
    add("</svg>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------- all ----
def pictures() -> dict[str, str]:
    """File name -> the text of the picture."""
    return {"concept.svg": concept(), "growth.svg": growth(), "modes.svg": modes()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make the pictures of the README from the synthetic sample.")
    ap.add_argument("--out", default=str(OUT), help="the directory to write into (default: docs/images)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in pictures().items():
        with open(out / name, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {out / name}: {len(text.encode('utf-8'))} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
