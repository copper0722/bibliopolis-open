"""The README does not drift from the program: its commands run, and the lines it shows are the lines the commands print."""

import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bibliopolis
from bibliopolis import picture

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
ENGLISH, CHINESE = README.split("\n---\n", 1)


def commands(text):
    return [line.strip() for line in text.splitlines() if line.strip().startswith("python -m bibliopolis ")]


def run(argv, cwd):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, *argv], cwd=cwd, env=env, capture_output=True, text=True, check=False)


def argv_of(command):
    """The arguments of a README command (without `python`), the sample files by absolute path: the command is run where the reader stands."""
    argv = shlex.split(command)[1:]
    for flag in ("--library", "--tree"):
        if flag in argv:
            argv[argv.index(flag) + 1] = str(ROOT / argv[argv.index(flag) + 1])
    return argv


def build_on_the_sample(cwd, *extra):
    return run(["-m", "bibliopolis", "build", "--library", str(ROOT / "examples/library.json"), "--tree", str(ROOT / "examples/tree.json"), *extra], cwd)


def test_the_two_halves_show_the_same_commands_in_the_same_order():
    english, chinese = commands(ENGLISH), commands(CHINESE)
    assert english == chinese and len(english) == 7
    assert {shlex.split(c)[3] for c in english} == {"build", "chronicle", "picture"}
    builds = [shlex.split(c) for c in english if shlex.split(c)[3] == "build"]
    assert {b[b.index("--mode") + 1] for b in builds} == {"grow", "mirror"} and sum("--first" in b for b in builds) == 1


def test_the_commands_of_the_readme_run_in_order_on_the_files_of_the_repository_in_each_half(tmp_path):
    for name, half in (("english", ENGLISH), ("chinese", CHINESE)):
        where = tmp_path / name
        where.mkdir()
        for command in commands(half):
            argv = argv_of(command)
            done = run(argv, where)
            assert done.returncode == 0, (command, done.stderr)
            if "--out" in argv:
                out = argv[argv.index("--out") + 1]
                assert not Path(out).is_absolute() and (where / out).is_file(), command  # it writes where the reader stands
        assert ET.parse(where / "city.svg").getroot().tag.endswith("svg") and ET.parse(where / "city-41.svg").getroot().tag.endswith("svg")


def test_the_readme_shows_the_line_the_build_command_prints_on_the_sample(tmp_path):
    shown = re.findall(r"^wrote city\.json: .*$", README, flags=re.MULTILINE)
    assert len(shown) == 2 and shown[0] == shown[1]
    done = build_on_the_sample(tmp_path, "--mode", "grow", "--out", "city.json")
    assert done.returncode == 0 and done.stderr.strip() == shown[0]


def test_the_readme_shows_the_chronicle_the_command_prints_on_the_sample(tmp_path):
    limits = set(re.findall(r"chronicle --city city\.json --limit (\d+)", README))
    assert len(limits) == 1
    limit = int(limits.pop())
    shown = re.findall(r"^house \d+, .*$", README, flags=re.MULTILINE)
    assert limit >= 3 and len(shown) == 2 * limit and shown[:limit] == shown[limit:]
    assert build_on_the_sample(tmp_path, "--mode", "grow", "--out", "city.json").returncode == 0
    done = run(["-m", "bibliopolis", "chronicle", "--city", "city.json", "--limit", str(limit)], tmp_path)
    assert done.returncode == 0 and done.stdout.splitlines() == shown[:limit] and done.stderr == ""
    assert shown[0].startswith("house 41,")  # the first road opens at the 41st item


def test_the_readme_replay_is_the_city_at_house_41_and_the_picture_command_draws_it(tmp_path):
    done = build_on_the_sample(tmp_path, "--mode", "grow", "--first", "41", "--out", "city-41.json")
    assert done.returncode == 0 and done.stderr.strip() == "wrote city-41.json: 41 houses on 1 roads, 26 under the town hall, 1 splits, 0 over (mode grow)"
    assert run(["-m", "bibliopolis", "picture", "--city", "city-41.json", "--out", "city-41.svg"], tmp_path).returncode == 0
    city = json.loads((tmp_path / "city-41.json").read_text(encoding="utf-8"))
    assert (tmp_path / "city-41.svg").read_text(encoding="utf-8") == picture.render(city)
    assert bibliopolis.summary(city)["houses"] == 41


def test_the_two_halves_of_the_readme_say_the_same_numbers():
    for number in ("40", "10", "41", "150", "600", "80"):
        assert number in ENGLISH and number in CHINESE, number
    assert ENGLISH.count("```") == CHINESE.count("```")  # the same code blocks in both languages


def test_each_half_leads_with_the_concept_picture_then_shows_the_growth_and_the_modes_with_a_caption_under_each():
    for half, heads in ((ENGLISH, ("## How a city grows", "## Two modes")), (CHINESE, ("## 城邦怎麼長大", "## 兩種模式"))):
        found = [(m.start(), m.group(1), m.group(2)) for m in re.finditer(r"!\[([^\]]+)\]\(docs/images/([\w.-]+)\)", half)]
        assert [name for _, _, name in found] == ["concept.svg", "growth.svg", "modes.svg"]
        assert all(alt.strip() for _, alt, _ in found)
        assert found[0][0] < half.index(heads[0]) < found[1][0] < half.index(heads[1]) < found[2][0]  # the concept first, then a section each
        for start, _alt, name in found:  # the caption: an italic paragraph right under the picture
            after = half[start:].split("\n", 3)
            assert after[1] == "" and after[2].startswith("*") and not after[2].startswith("**"), name
            assert (ROOT / "docs" / "images" / name).is_file()
    shown = sorted(set(re.findall(r"\]\(docs/images/([\w.-]+)\)", README)))
    assert shown == sorted(p.name for p in (ROOT / "docs" / "images").glob("*.svg"))  # every picture of the folder is shown, and nothing else is
