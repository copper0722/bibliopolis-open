"""The pictures of the README (docs/images): the committed files are what examples/make_pictures.py makes today, byte for byte, so they cannot go stale."""

import importlib.util
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import bibliopolis
from bibliopolis import picture

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
SVG = "{http://www.w3.org/2000/svg}"
NAMES = ["concept.svg", "growth.svg", "modes.svg"]
MAKE = "python3 examples/make_pictures.py"


def load_script():
    spec = importlib.util.spec_from_file_location("make_pictures", ROOT / "examples" / "make_pictures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


@pytest.fixture(scope="module")
def made(script):
    return script.pictures()


def texts(name):
    """(text, x, y, font size, anchor) of every <text> of a picture."""
    root = ET.parse(IMAGES / name).getroot()
    return [(t.text, float(t.get("x")), float(t.get("y")), float(t.get("font-size")), t.get("text-anchor", "start")) for t in root.iter(f"{SVG}text")]


def test_the_script_makes_the_three_pictures_the_readme_shows(made):
    assert sorted(made) == NAMES


def test_the_committed_pictures_are_what_the_script_makes_byte_for_byte(made):
    for name, text in made.items():
        assert (IMAGES / name).read_bytes() == text.encode("utf-8"), f"{name} is stale: run `{MAKE}` and commit the result"
    assert sorted(p.name for p in IMAGES.glob("*.svg")) == NAMES  # no picture of an older script is left behind


def test_the_script_writes_the_same_bytes_to_any_directory_and_says_what_it_wrote(script, tmp_path, capsys):
    where = tmp_path / "new" / "images"  # (the directory is made)
    assert script.main(["--out", str(where)]) == 0
    said = capsys.readouterr().err
    for name in NAMES:
        assert (where / name).read_bytes() == (IMAGES / name).read_bytes()
        assert f"wrote {where / name}: {(IMAGES / name).stat().st_size} bytes" in said
    assert script.OUT == IMAGES  # with no option it writes where the README looks


@pytest.mark.parametrize("hashseed", ["0", "4242"])
def test_the_pictures_are_the_same_in_another_process_with_another_hash_seed(tmp_path, hashseed):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, str(ROOT / "examples" / "make_pictures.py"), "--out", str(tmp_path)], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    for name in NAMES:
        assert (tmp_path / name).read_bytes() == (IMAGES / name).read_bytes(), name


@pytest.mark.parametrize("name", NAMES)
def test_a_picture_is_valid_xml_small_and_made_of_shapes_and_text_only(name):
    data = (IMAGES / name).read_bytes()
    assert 1_000 < len(data) < 100_000
    root = ET.fromstring(data)
    assert root.tag == f"{SVG}svg" and root.get("viewBox") and float(root.get("width")) > 0 and float(root.get("height")) > 0
    assert {el.tag.rsplit("}", 1)[-1] for el in root.iter()} <= {"svg", "rect", "path", "line", "circle", "text"}  # no script, image, link or style sheet
    assert not any(key.endswith("href") for el in root.iter() for key in el.attrib)
    assert "http" not in data.decode("utf-8").replace('xmlns="http://www.w3.org/2000/svg"', "")  # nothing outside the file
    assert data.endswith(b"</svg>\n") and b"\r" not in data


def test_the_growth_picture_shows_the_town_hall_alone_then_the_first_road_then_the_splits(script):
    said = [t for t, *_ in texts("growth.svg")]
    for line in ("After 40 houses · 蓋到第 40 棟", "No road yet: all 40 are on the ring road.", "還沒有路：40 棟全在環形大道上。",
                 "After 41 houses · 蓋到第 41 棟", "The first road opens: Computing takes 15 (orange).",
                 "After 150 houses · 蓋到第 150 棟", "After 600 houses · 蓋到第 600 棟"):
        assert line in said, line
    assert said.count("Knowledge") == 4  # the ring road is named once in each of the four panels, at its north point
    tree, library = script.sample()
    for n in script.STEPS:  # every number of a caption is the number of the city it sits over
        city = bibliopolis.build_city(library, tree, first=n)
        assert [line for line in script.growth_caption(n, city) if line in said] == script.growth_caption(n, city)
    assert script.STEPS == (40, 41, 150, 600) and len(library["items"]) == 600


def test_the_modes_picture_puts_the_same_items_in_both_modes_on_one_frame(script):
    root = ET.parse(IMAGES / "modes.svg").getroot()
    panels = root.findall(f"{SVG}svg")
    assert len(panels) == 2 and len({p.get("viewBox") for p in panels}) == 1 and len({p.get("width") for p in panels}) == 1
    said = [t for t, *_ in texts("modes.svg")]
    tree, library = script.sample()
    mirror, grown = (bibliopolis.summary(bibliopolis.build_city(library, tree, mode=m)) for m in ("mirror", "grow"))
    assert f"mirror: {script.topic_roads(mirror)} roads, one for every topic that holds a house." in said
    assert f"grow: {script.topic_roads(grown)} roads, opened one by one as the houses arrived." in said
    assert (script.topic_roads(mirror), script.topic_roads(grown)) == (79, 22) and mirror["roads"] - 1 == 79  # (the ring road is a street of both cities and no topic's)
    assert mirror["houses"] == grown["houses"] == 600 and mirror["roads"] > grown["roads"]


def test_the_concept_picture_names_a_house_a_road_a_branch_road_the_town_hall_and_the_ring_road_in_two_languages(script):
    said = [t for t, *_ in texts("concept.svg")]
    for pair in (("an article = a house", "一篇文獻＝一棟房子"), ("a topic = a road", "主題＝路"), ("a sub-topic = a branch road", "子主題＝岔路"),
                 ("the town hall = the root", "市政廳＝根"), ("the ring road", "環形大道：還沒有主題的文獻")):
        assert all(line in said for line in pair), pair
    assert "市政廳" in said and "Knowledge" in said and "Networks" in said  # the plaza, the name of the ring road, the branch road named
    city = bibliopolis.build_city(script.concept_library(), script.CONCEPT_TREE, mode="mirror")
    assert bibliopolis.summary(city)["houses"] == 53 and bibliopolis.summary(city)["ring"] == 5 and len(city["composition"]["ring1"]) == 3


def test_no_two_labels_of_the_concept_picture_stand_on_each_other():
    labels = [(t, x, y, size, anchor) for t, x, y, size, anchor in texts("concept.svg") if anchor in ("start", "end") and size >= 15 and y > 80]
    assert len(labels) >= 10
    boxes = []
    for text, x, y, size, anchor in labels:
        width = picture.text_width(text, size)
        left = x if anchor == "start" else x - width
        boxes.append((left, y - 0.9 * size, left + width, y + 0.2 * size))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not picture.overlaps(a, b), (a, b)


# ---------------------------------------------------------------------------------- what may live in docs/images ----
PNG_LIMIT = 1_048_576  # 1 MiB: the most a PNG under docs/images/ may be


def ignore_lines():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_the_images_folder_holds_only_svg_pictures_and_png_images_of_at_most_1_mib_directly_in_it():
    entries = sorted(IMAGES.iterdir())
    assert entries and all(p.is_file() and not p.is_symlink() for p in entries)  # no folder below it: the exception is for files directly under docs/images/
    assert {p.suffix for p in entries} <= {".svg", ".png"}
    for p in entries:
        if p.suffix == ".png":
            data = p.read_bytes()
            assert data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= PNG_LIMIT, p.name


def test_the_ignore_file_lets_png_through_directly_under_docs_images_and_nothing_else():
    lines = ignore_lines()
    assert [line for line in lines if line.startswith("!")] == ["!docs/images/*.png"]
    assert lines.index("*.png") < lines.index("!docs/images/*.png")  # the later rule wins
    assert {"*.jpg", "*.jpeg", "*.webp", "*.avif"} <= set(lines)  # the other image formats stay ignored


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_ignores_every_image_but_a_png_directly_under_docs_images(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(ROOT / ".gitignore", tmp_path / ".gitignore")

    def ignored(path):
        return subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", path], check=False).returncode == 0

    assert not any(ignored(p) for p in ("docs/images/a.png", "docs/images/a.svg", "docs/a.svg"))
    assert all(ignored(p) for p in ("docs/images/a.jpg", "docs/images/a.jpeg", "docs/images/a.webp", "docs/images/a.avif", "docs/a.png", "docs/images/sub/a.png", "a.png"))


def test_the_card_and_both_halves_of_the_readme_say_what_the_ignore_file_lets_through():
    card = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").split())  # the card wraps its lines
    assert "PNG images directly under `docs/images/`, at most 1 MiB (1,048,576 bytes) each, pixels only" in card and str(PNG_LIMIT) == "1048576"
    assert "JPG, WebP and every other binary stay out" in card
    english, chinese = (ROOT / "README.md").read_text(encoding="utf-8").split("\n---\n", 1)
    assert "PNG images directly under `docs/images/` (pixels only, at most 1 MiB each)" in english
    assert "PNG" in chinese and "`docs/images/`" in chinese and "1 MiB" in chinese
    assert not any(word in text for text in (english, chinese) for word in ("JPG", "JPEG", "WebP"))
