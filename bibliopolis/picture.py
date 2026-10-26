"""A picture of a city: the plan view of a layout v4 document as one SVG (the pictures of docs/images/ are made with it).

    python -m bibliopolis picture --city city.json --out city.svg [--title ...]

Draws the coast, the roads by display class (大道 路 巷 弄), the houses (the lots), the plaza (市政廳) with the number of houses that lie underground in
the root zone (地下 n 棟), and the names of the roads where they fit; each district of ring 1 has its own colour. Units are cells; x east, z south, north
up. Pure text, standard library only; the same document gives the same bytes.

  render(city, title=None, size=1800)    one city, with a title, a line of numbers and a legend
  sheet(panels, columns=2, ...)          several cities in one picture on one frame (a replay of growth, two modes side by side), each with a caption

The houses of the root zone are not drawn as lots: they stand under the plaza, and the plaza says how many. A sector of ring 1 is named once a road
of it exists.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

CLASS_STROKE = {"大道": 2.6, "路": 1.7, "巷": 1.1, "弄": 0.8}
CLASS_COLOR = {"大道": "#3b3b45", "路": "#55556a", "巷": "#74748c", "弄": "#8f8fa3"}
CLASS_NAME = {"大道": "avenue", "路": "road", "巷": "lane", "弄": "alley"}
CLASS_ORDER = {"弄": 0, "巷": 1, "路": 2, "大道": 3}  # the minor roads are drawn first
FONT = "'Noto Sans CJK TC','Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif"
HUES = (205, 28, 145, 330, 265, 95, 55, 180)  # hues of the districts of ring 1, in the order of the document
SEA, LAND, SHORE = "#e9f1f5", "#f4efe2", "#b9ad8c"
INK, GREY = "#202028", "#4a4a55"
HIGHLIGHT = ("#e4572e", "#7a1f05")  # fill and edge of the houses a picture is about
PLAZA_INK = "#6b4f0f"
PLAZA = "place:plaza"
TITLE = "Bibliopolis 文獻城邦"
PAD = 24.0  # cells of sea round the land: room for the names of ring 1

Frame = tuple[float, float, float, float]  # (x0, x1, z0, z1) in cells
Box = tuple[float, float, float, float]


_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")  # what XML 1.0 cannot carry: a name with one still makes a valid picture


def esc(text: str) -> str:
    return _NOT_XML.sub("\ufffd", text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def num(v: float, digits: int = 2) -> str:
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def underground_count(city: dict) -> int:
    return sum(1 for p in city["places"].values() if p["kind"] == "lot" and p.get("underground"))


def ring1_place(places: dict[str, dict], pid: str) -> str:
    """The street of ring 1 that a place stands under. Parents that never lead to the plaza are an error (`ValueError`), not a loop."""
    for _ in range(len(places)):
        parent = places[pid].get("parent")
        if parent in (None, PLAZA):
            return pid
        pid = parent
    raise ValueError(f"the parents of {pid!r} lead round in a circle")


def cell_path(x: float, z: float, lane_radius: float, digits: int) -> str:
    """Path data of the polar cell of a lot on a band: one cell along the lane, one across it, centred at (x, z)."""
    rho, bearing = math.hypot(x, z), math.atan2(x, -z)
    half = 0.5 / lane_radius
    pts = [(rho - 0.5, bearing - half), (rho + 0.5, bearing - half), (rho + 0.5, bearing + half), (rho - 0.5, bearing + half)]
    return "M" + "L".join(f"{num(r * math.sin(b), digits)},{num(-r * math.cos(b), digits)}" for r, b in pts) + "Z"


def square_path(x: float, z: float, facing: float, digits: int) -> str:
    """Path data of the 1 x 1 cell centred at (x, z) whose front looks at bearing `facing` (a street along its own spoke)."""
    r = math.radians(facing)
    ux, uz = math.sin(r) * 0.5, -math.cos(r) * 0.5
    vx, vz = math.cos(r) * 0.5, math.sin(r) * 0.5
    pts = [(x - ux - vx, z - uz - vz), (x + ux - vx, z + uz - vz), (x + ux + vx, z + uz + vz), (x - ux + vx, z - uz + vz)]
    return "M" + "L".join(f"{num(a, digits)},{num(b, digits)}" for a, b in pts) + "Z"


def polyline(points: list[list[float]], digits: int = 2) -> str:
    return "M" + "L".join(f"{num(a, digits)},{num(b, digits)}" for a, b in points)


def extent(city: dict, pad: float = PAD) -> Frame:
    """(x0, x1, z0, z1) of everything drawn, with `pad` cells of sea round it for the names of ring 1."""
    xs: list[float] = [0.0]
    zs: list[float] = [0.0]
    for p in city["places"].values():
        if "position" in p and not p.get("underground"):
            xs.append(p["position"]["x"])
            zs.append(p["position"]["z"])
    for r in city["roads"].values():
        for x, z in r["points"]:
            xs.append(x)
            zs.append(z)
    for poly in city.get("coast", {}).get("polygons", []):
        for x, z in poly:
            xs.append(x)
            zs.append(z)
    return min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad


@dataclass(frozen=True)
class Look:
    """How a picture is drawn, in cells: the height of the names of ring 1 (`big`), of ring 2 (`small`; 0 draws none) and of the plaza (`plaza`), the
    width of the white edge of a name (`halo`), the decimals of a coordinate (`digits`: 2 suits a picture of 1800 pixels, 1 a panel of 400) and how thick
    the roads are (`line`, 1 for the widths of CLASS_STROKE)."""

    big: float = 7.0
    small: float = 3.4
    plaza: float = 3.4
    halo: float = 0.9
    digits: int = 2
    line: float = 1.0

    @staticmethod
    def of_pixels(scale: float, big: float, small: float, plaza: float, digits: int = 1) -> Look:
        """The look that makes the names `big`, `small` and `plaza` pixels high at `scale` pixels to the cell, and keeps a road from growing thicker than it
        is at 3.5 pixels to the cell (a picture of a small city is drawn at a large scale)."""
        return Look(big / scale, small / scale, plaza / scale, max(0.2, big / scale * 0.13), digits, min(1.0, 3.5 / scale))


# ------------------------------------------------------------------------------------------------------ the city ----
def draw_lots(city: dict, add, look: Look, highlight: set[str] | None = None) -> None:
    """Houses filled, empty lots outlined (a document that lists them). `highlight` (item ids) are drawn on top in the accent colour."""
    places = city["places"]
    index = {r["place"]: i for i, r in enumerate(city["composition"]["ring1"])}
    groups: dict[int, dict[str, list[str]]] = {}
    marked: list[str] = []
    for p in places.values():
        if p["kind"] not in ("lot", "reserved") or p.get("underground"):  # (the root zone is under the plaza: a count, not lots)
            continue
        g = groups.setdefault(index[ring1_place(places, p["parent"])], {"lot": [], "reserved": []})
        rib = places[p["parent"]].get("rib")
        pos = p["position"]
        if rib and rib.get("band") is not None:  # a cell of a band: the polar cell of its lane
            path = cell_path(pos["x"], pos["z"], rib["s"], look.digits)
        else:
            path = square_path(pos["x"], pos["z"], p.get("facing", 0.0), look.digits)
        if highlight and p["kind"] == "lot" and p["article"] in highlight:
            marked.append(path)
        else:
            g[p["kind"]].append(path)
    for i in sorted(groups):
        fill, edge = f"hsl({HUES[i % len(HUES)]},45%,72%)", f"hsl({HUES[i % len(HUES)]},40%,45%)"
        if groups[i]["reserved"]:
            add(f'<path d="{"".join(groups[i]["reserved"])}" fill="none" stroke="{edge}" stroke-width="0.12" opacity="0.8"/>')
        if groups[i]["lot"]:
            add(f'<path d="{"".join(groups[i]["lot"])}" fill="{fill}" stroke="{edge}" stroke-width="0.08"/>')
    if marked:
        add(f'<path d="{"".join(marked)}" fill="{HIGHLIGHT[0]}" stroke="{HIGHLIGHT[1]}" stroke-width="0.14"/>')


def draw_roads(city: dict, add, look: Look) -> None:
    for _rid, r in sorted(city["roads"].items(), key=lambda kv: (CLASS_ORDER[kv[1]["class"]], kv[0])):
        add(f'<path d="{polyline(r["points"], look.digits)}" fill="none" stroke="{CLASS_COLOR[r["class"]]}" '
            f'stroke-width="{num(CLASS_STROKE[r["class"]] * 0.5 * look.line, 3)}" stroke-linecap="round"/>')


def ring2_of(places: dict[str, dict], pid: str | None) -> str | None:
    """The street of ring 2 (not a continuation) that a place stands in or under, if any. A circle of parents is an error (`ValueError`), not a loop."""
    for _ in range(len(places)):
        if not pid or pid == PLAZA:
            return None
        q = places[pid]
        if q["kind"] == "street" and q.get("level") == 2 and "lane_of" not in q:
            return pid
        pid = q.get("parent")
    raise ValueError(f"the parents of {pid!r} lead round in a circle")


def ring2_centres(places: dict[str, dict]) -> dict[str, tuple[float, float]]:
    """Street of ring 2 -> the centroid of the lots of its subtree (its continuations and the streets below it)."""
    sums: dict[str, list[float]] = {}
    for p in places.values():
        if p["kind"] in ("lot", "reserved") and not p.get("underground"):
            top = ring2_of(places, p["parent"])
            if top is not None:
                acc = sums.setdefault(top, [0.0, 0.0, 0.0])
                acc[0] += p["position"]["x"]
                acc[1] += p["position"]["z"]
                acc[2] += 1
    return {pid: (acc[0] / acc[2], acc[1] / acc[2]) for pid, acc in sums.items()}


def text_width(text: str, size: float) -> float:
    """About how wide a name is: a wide glyph (Chinese, the Japanese middle dot) is one em, any other about half and a bit."""
    return sum(size if unicodedata.east_asian_width(c) in ("W", "F") else size * 0.56 for c in text)


def text_box(x: float, z: float, text: str, size: float) -> Box:
    """The box a name occupies, its baseline at z."""
    half = text_width(text, size) / 2
    return x - half, z - 0.9 * size, x + half, z + 0.2 * size


def overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def exists(city: dict, sector: dict) -> bool:
    """A sector of ring 1 is on the map once a road of it exists: the plan pins every sector before the first house, the town shows those it has."""
    return sector["place"] in city["places"]


def draw_labels(city: dict, add, look: Look, boxes: list[Box] | None = None) -> tuple[int, int]:
    """The plaza; ring 1 beyond the far edge of its district (so the names never crowd each other); ring 2 beside its spoke or in the middle of its
    houses, heaviest street first, each only where it fits. Returns (names of ring 2 drawn, streets of ring 2 that could be named). `boxes` gets the
    box of every name, so that a picture can make room for them."""
    places, roads = city["places"], city["roads"]
    taken: list[Box] = []
    halo = f'paint-order="stroke" stroke="#ffffff" stroke-width="{num(look.halo)}" stroke-linejoin="round"'

    def put(x: float, z: float, text: str, size: float, fill: str = INK) -> None:
        taken.append(text_box(x, z, text, size))
        add(f'<text x="{num(x, look.digits)}" y="{num(z, look.digits)}" font-size="{num(size)}" text-anchor="middle" fill="{fill}" {halo}>{esc(text)}</text>')

    unit = look.big / 7.0
    put(0.0, look.plaza * 0.35, places[PLAZA]["label"], look.plaza, PLAZA_INK)
    under = underground_count(city)
    if under:  # the root zone, under the town hall: how many houses lie there
        put(0.0, places[PLAZA]["radius"] + look.plaza * 1.15, f"地下 {under} 棟", look.plaza, PLAZA_INK)
    far: dict[str, float] = {}
    for p in places.values():
        if p["kind"] in ("lot", "reserved") and not p.get("underground"):
            top = ring1_place(places, p["parent"])
            far[top] = max(far.get(top, 0.0), math.hypot(p["position"]["x"], p["position"]["z"]))
    for sector in city["composition"]["ring1"]:
        if not exists(city, sector):
            continue
        place = places[sector["place"]]
        axis = math.radians((sector["from"] + sector["to"]) / 2)  # the bisector of the wedge: the direction of the spoke
        sin, cos = math.sin(axis), -math.cos(axis)
        name = sector["label"]
        # the name stands just beyond the farthest house of its district: the nearest corner of its box is `gap` cells from it
        base = far.get(sector["place"], place.get("s_end", 20.0)) + 2.5 * unit + text_width(name, look.big) / 2 * abs(sin) + look.big * 0.55 * abs(cos)
        reach = base
        for k in range(8):  # districts side by side: a name that would sit on another one stands farther out
            if not any(overlaps(text_box(sin * reach, cos * reach + 0.3 * look.big, name, look.big), box) for box in taken):
                break
            reach = base + 9.0 * unit * (k + 1)
        if reach > base:  # ... and a line from the land to it
            add(f'<line x1="{num(sin * (base - 4 * unit), look.digits)}" y1="{num(cos * (base - 4 * unit), look.digits)}" '
                f'x2="{num(sin * reach, look.digits)}" y2="{num(cos * reach, look.digits)}" stroke="#6b6b75" stroke-width="{num(max(0.15, look.big * 0.05))}"/>')
        put(sin * reach, cos * reach + 0.3 * look.big, name, look.big)
    wanted: list[tuple[int, str, float, float, str]] = []  # (weight, place, x, z, name)
    shown = 0
    if look.small > 0:
        centres = ring2_centres(places)
        for pid, p in places.items():
            if p["kind"] != "street" or p.get("level") != 2 or "lane_of" in p:
                continue
            if p["shape"] == "trunk" and p.get("road") in roads:  # beside its spoke
                (ax, az), (bx, bz) = roads[p["road"]]["points"][0], roads[p["road"]]["points"][-1]
                x, z = ax + (bx - ax) * 0.35, az + (bz - az) * 0.35 - 1.5
            elif pid in centres:  # a street on the bands of a trunk: the middle of its houses
                x, z = centres[pid]
            else:
                continue
            wanted.append((-p.get("weight", 0), pid, x, z, p.get("label") or p["address"][-1]))
        for _weight, _pid, x, z, name in sorted(wanted):
            if not any(overlaps(text_box(x, z, name, look.small), box) for box in taken):
                put(x, z, name, look.small)
                shown += 1
    if boxes is not None:
        boxes.extend(taken)
    return shown, len(wanted)


def draw_city(city: dict, add, look: Look, highlight: set[str] | None = None) -> tuple[int, int]:
    """Everything of one city, in cells: the land, the houses, the roads, the plaza and the names. Returns what `draw_labels` returns."""
    for poly in city.get("coast", {}).get("polygons", []):
        add(f'<path d="{polyline(poly, look.digits)}Z" fill="{LAND}" stroke="{SHORE}" stroke-width="0.6" stroke-linejoin="round"/>')
    draw_lots(city, add, look, highlight)
    draw_roads(city, add, look)
    add(f'<circle cx="0" cy="0" r="{num(city["places"][PLAZA]["radius"])}" fill="#fff7d6" stroke="#8a6d1f" stroke-width="0.9"/>')
    return draw_labels(city, add, look)


def fit(cities: list[dict], pixels: float, label_px: tuple[float, float, float], pad: float = PAD, digits: int = 1) -> tuple[Frame, float, Look]:
    """One frame for all `cities`, the scale (pixels to the cell) that fits it into a square of `pixels`, and the look of the names at that scale. The
    frame leaves room for every name: the names are sized at the scale the frame gives, so the frame grows until they stand inside it."""
    x0, x1, z0, z1 = _union([extent(c, pad) for c in cities])
    for _ in range(6):
        look = Look.of_pixels(pixels / max(x1 - x0, z1 - z0), *label_px, digits=digits)
        boxes: list[Box] = []
        for c in cities:
            draw_labels(c, lambda _line: None, look, boxes)
        n0, n1 = min([x0] + [b[0] - 1.0 for b in boxes]), max([x1] + [b[2] + 1.0 for b in boxes])
        m0, m1 = min([z0] + [b[1] - 1.0 for b in boxes]), max([z1] + [b[3] + 1.0 for b in boxes])
        if (n0, n1, m0, m1) == (x0, x1, z0, z1):
            break
        x0, x1, z0, z1 = n0, n1, m0, m1
    scale = pixels / max(x1 - x0, z1 - z0)
    return (x0, x1, z0, z1), scale, Look.of_pixels(scale, *label_px, digits=digits)


def _union(frames: list[Frame]) -> Frame:
    return min(f[0] for f in frames), max(f[1] for f in frames), min(f[2] for f in frames), max(f[3] for f in frames)


def draw_panel(add, city: dict, frame: Frame, scale: float, look: Look, x: float, y: float, highlight: set[str] | None = None) -> None:
    """The city on a box of the page: its top left corner at (x, y) pixels, `frame` (cells) shown at `scale` pixels to the cell, on the sea."""
    x0, x1, z0, z1 = frame
    add(f'<svg x="{num(x)}" y="{num(y)}" width="{num((x1 - x0) * scale)}" height="{num((z1 - z0) * scale)}" '
        f'viewBox="{num(x0)} {num(z0)} {num(x1 - x0)} {num(z1 - z0)}">')
    add(f'<rect x="{num(x0)}" y="{num(z0)}" width="{num(x1 - x0)}" height="{num(z1 - z0)}" fill="{SEA}"/>')
    draw_city(city, add, look, highlight)
    add("</svg>")


# ----------------------------------------------------------------------------------------------- the frame round it ----
def draw_legend(add, x: float, y: float, scale: float, cells: int = 50) -> None:
    """The classes of road with their names and a bar `cells` cells long, in a row that starts at (x, y)."""
    for name, color in CLASS_COLOR.items():
        word = f"{name} {CLASS_NAME[name]}"
        add(f'<line x1="{num(x)}" y1="{num(y)}" x2="{num(x + 26)}" y2="{num(y)}" stroke="{color}" stroke-width="{num(CLASS_STROKE[name] * 2.0)}" '
            f'stroke-linecap="round"/>')
        add(f'<text x="{num(x + 32)}" y="{num(y + 5)}" font-size="14" fill="{INK}">{word}</text>')
        x += 32 + text_width(word, 14) + 22
    bar = cells * scale
    add(f'<line x1="{num(x)}" y1="{num(y)}" x2="{num(x + bar)}" y2="{num(y)}" stroke="{INK}" stroke-width="2"/>')
    add(f'<text x="{num(x + bar + 6)}" y="{num(y + 5)}" font-size="14" fill="{INK}">{cells} cells 格</text>')


def stats_line(city: dict, labels: tuple[int, int]) -> str:
    """The line of numbers under the title. A measure is printed as the float it is (`55.0`), whether the file it was read from has `55.0` or `55` (the canonical form of a
    document writes the second): a picture drawn from a city file has the same bytes as the picture of the city."""
    comp, m = city["composition"], city["composition"]["measure"]
    text = (f'{comp["buildings"]} houses ({m.get("underground_lots", 0)} under the town hall) on {comp["streets"]["total"]} roads; '
            f'the farthest house is {float(m["max_radius"])} cells from the centre, the mean walk {float(m["walk_mean"])}, the longest {float(m["walk_longest"])}')
    if labels[1]:
        text += f"; road names drawn: {labels[0]} of {labels[1]}"
    return text


def render(city: dict, title: str | None = None, size: int = 1800, highlight: set[str] | None = None, label_scale: float = 1.0) -> str:
    """The plan view of one city: a title, a line of numbers, the city, and a legend. `size` is the longest side of the city in pixels; `label_scale`
    makes the names larger or smaller (1.0 suits a city of some hundred houses at 1800 pixels)."""
    look = Look(7.0 * label_scale, 3.4 * label_scale, 3.4 * label_scale, 0.9 * label_scale)
    boxes: list[Box] = []
    draw_labels(city, lambda _line: None, look, boxes)
    x0, x1, z0, z1 = extent(city)
    x0, x1 = min([x0] + [b[0] - 2.0 for b in boxes]), max([x1] + [b[2] + 2.0 for b in boxes])  # a name pushed out beyond the land stays in the picture
    z0, z1 = min([z0] + [b[1] - 2.0 for b in boxes]), max([z1] + [b[3] + 2.0 for b in boxes])
    w, h = x1 - x0, z1 - z0
    scale = size / max(w, h)
    head, foot = 60, 36
    height = h * scale + head + foot
    out: list[str] = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(w * scale)} {num(height)}" width="{num(w * scale)}" height="{num(height)}" '
        f'font-family="{FONT}">')
    add(f'<rect width="100%" height="100%" fill="{SEA}"/>')
    add(f'<g transform="translate({num(-x0 * scale)},{num(-z0 * scale + head)}) scale({num(scale)})">')
    labels = draw_city(city, add, look, highlight)
    add("</g>")
    add(f'<text x="14" y="26" font-size="22" fill="{INK}">{esc(title or TITLE)}</text>')
    add(f'<text x="14" y="50" font-size="15" fill="{GREY}">{esc(stats_line(city, labels))}</text>')
    draw_legend(add, 14, height - 18, scale)
    add("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------------- a sheet ----
@dataclass
class Panel:
    """One city of a sheet: its document, a caption of up to three lines and the houses to draw in the accent colour."""

    city: dict
    caption: list[str] = field(default_factory=list)
    highlight: set[str] | None = None


def sheet(panels: list[Panel], *, columns: int = 2, panel_px: int = 430, title: str | None = None, label_px: tuple[float, float, float] = (11.0, 0.0, 9.0),
          cells: int = 50, pad: float = 8.0) -> str:
    """Several cities in one picture, all on the frame of the largest, so that growth shows as growth: a caption above each map, an optional title above
    them all and one legend below. `label_px` are the heights of the names of ring 1, of ring 2 (0: none) and of the plaza, in pixels."""
    frame, scale, look = fit([p.city for p in panels], panel_px, label_px, pad)
    w, h = (frame[1] - frame[0]) * scale, (frame[3] - frame[2]) * scale
    lines = max([len(p.caption[:3]) for p in panels] + [1])
    gap, cap = 14.0, 8.0 + 19.0 * lines
    head = 44.0 if title else 0.0
    rows = -(-len(panels) // columns)
    width = columns * w + (columns + 1) * gap
    height = head + rows * (cap + h + gap) + gap + 34.0
    out: list[str] = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(width)} {num(height)}" width="{num(width)}" height="{num(height)}" font-family="{FONT}">')
    add('<rect width="100%" height="100%" fill="#ffffff"/>')
    if title:
        add(f'<text x="{num(gap)}" y="30" font-size="22" fill="{INK}">{esc(title)}</text>')
    for i, panel in enumerate(panels):
        row, col = divmod(i, columns)
        px, py = gap + col * (w + gap), head + gap + row * (cap + h + gap)
        for k, line in enumerate(panel.caption[:3]):
            add(f'<text x="{num(px + 2)}" y="{num(py + 17 + k * 19)}" font-size="{16 if k == 0 else 14}" fill="{INK if k == 0 else GREY}">{esc(line)}</text>')
        draw_panel(add, panel.city, frame, scale, look, px, py + cap, panel.highlight)
    draw_legend(add, gap + 2, height - 18, scale, cells)
    add("</svg>")
    return "\n".join(out) + "\n"
