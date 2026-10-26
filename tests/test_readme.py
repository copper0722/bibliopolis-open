"""The README does not drift from the program: its commands run, and the lines it shows are the lines the commands print."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import bibliopolis
from bibliopolis import picture

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
ENGLISH, CHINESE = README.split("\n---\n", 1)
HALVES = ((ENGLISH, "## Set up", "## How a city grows", "## Try it"), (CHINESE, "## 安裝與設定", "## 城邦怎麼長大", "## 試試看"))

# The lines of the code blocks that the test does not run, and why. Every other line of a code block must be a bibliopolis command (run below), the version
# command (run below) or a line that a command printed (compared with the real output below).
NOT_RUN = {
    "git clone https://github.com/copper0722/bibliopolis-open.git": "downloads the repository from GitHub",
    "python3 -m pip install pytest": "installs from the internet",
    "python3 -m pytest": "is the test run itself",
}
# The same for a command inside a sentence.
NOT_RUN_INLINE = {
    "brew install python": "installs Python with Homebrew",
    "git clone": "the name of the command, with the line of NOT_RUN above",
    "cd bibliopolis-open": "moves into the folder that `git clone` makes",
    "cd ": "the first word of a command that the reader completes",
    "python3 -m pip install pytest": "installs from the internet",
    "python3 examples/make_pictures.py": "makes the pictures of docs/images/; tests/test_images.py runs the script into a temporary folder",
}
OUTPUT = ("wrote ", "house ")


def commands(text):
    return [line.strip() for line in text.splitlines() if line.strip().startswith("python3 -m bibliopolis ")]


def fenced_lines(text):
    """Every non-empty line of every code block, in order."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
        elif inside and line.strip():
            lines.append(line.strip())
    return lines


def inline_commands(text):
    """The commands inside sentences: the `code` spans (outside the code blocks) that start like one."""
    prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return [span for span in re.findall(r"`([^`\n]+)`", prose) if span.startswith(("python3 ", "py ", "git ", "brew ", "pip ", "cd "))]


def section(text, head, next_head="\n## "):
    """From `head` to the next heading (or to `next_head`, the text of one)."""
    start = text.index(head)
    return text[start:text.index(next_head, start + len(head))]


def run(argv, cwd):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, *argv], cwd=cwd, env=env, capture_output=True, text=True, check=False)


def argv_of(command):
    """The arguments of a README command (without `python3`), the sample files by absolute path: the command is run where the reader stands."""
    argv = shlex.split(command)[1:]
    for flag in ("--library", "--tree"):
        if flag in argv:
            argv[argv.index(flag) + 1] = str(ROOT / argv[argv.index(flag) + 1])
    return argv


def build_on_the_sample(cwd, *extra):
    return run(["-m", "bibliopolis", "build", "--library", str(ROOT / "examples/library.json"), "--tree", str(ROOT / "examples/tree.json"), *extra], cwd)


def test_the_two_halves_show_the_same_commands_in_the_same_order():
    english, chinese = commands(ENGLISH), commands(CHINESE)
    assert english == chinese and len(english) == 9  # two in Set up, four in How a city grows, three in Try it
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


def test_every_command_the_readme_shows_is_run_by_the_test_or_is_on_the_list_of_those_that_are_not():
    for half, *_heads in HALVES:
        for line in fenced_lines(half):
            assert line.startswith("python3 -m bibliopolis ") or line == "python3 --version" or line in NOT_RUN or line.startswith(OUTPUT), line
        for span in inline_commands(half):
            assert span in NOT_RUN_INLINE, span
    assert all(reason for reason in [*NOT_RUN.values(), *NOT_RUN_INLINE.values()])


def test_the_version_command_of_the_readme_runs_and_the_version_it_asks_for_is_the_one_the_project_needs(tmp_path):
    assert all(fenced_lines(half).count("python3 --version") == 1 for half, *_heads in HALVES)
    done = run(["--version"], tmp_path)  # the interpreter of this run stands in for `python3`
    assert done.returncode == 0 and re.match(r"Python 3\.\d+", done.stdout)
    needs = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    assert needs == ">=3.11"
    version = needs.removeprefix(">=")  # the README asks for the version the project needs: 3.11
    for half, head, next_head, _try_head in HALVES:
        words = (f"Python {version} or newer", f"Python {version} or higher") if half is ENGLISH else (f"Python {version} 或更新", f"Python {version} 或更高")
        text = section(half, head, next_head)
        assert all(phrase in text for phrase in words), head
        assert {m for m in re.findall(r"Python 3\.(\d+)", text)} == {version.split(".")[1], "9"}  # and 3.9 only as the example of an old one on a Mac


def test_each_half_has_a_set_up_section_before_how_a_city_grows_for_a_reader_who_does_not_program():
    for half, head, next_head, try_head in HALVES:
        assert half.index(head) < half.index(next_head)
        text = section(half, head, next_head)
        for needle in ("python.org/downloads", "Homebrew", "`py`", "`python3`", "git clone https://github.com/copper0722/bibliopolis-open.git", "Download ZIP",
                       "`cmd`", "city.svg", "pytest"):
            assert needle in text, (head, needle)
        try_it = section(half, try_head)  # up to the next heading
        assert commands(text) == [commands(try_it)[0], commands(try_it)[2]]  # the two example commands of Set up: the grow build and the picture


def test_the_readme_shows_the_line_the_build_command_prints_on_the_sample(tmp_path):
    shown = re.findall(r"^wrote city\.json: .*$", README, flags=re.MULTILINE)
    assert len(shown) == 4 and len(set(shown)) == 1  # in Set up and in Try it, in both halves
    done = build_on_the_sample(tmp_path, "--mode", "grow", "--out", "city.json")
    assert done.returncode == 0 and done.stderr.strip() == shown[0]


def test_the_readme_shows_the_line_the_picture_command_prints_after_that_build(tmp_path):
    shown = re.findall(r"^wrote city\.svg: .*$", README, flags=re.MULTILINE)
    assert len(shown) == 2 and shown[0] == shown[1]  # in Set up, in both halves
    assert build_on_the_sample(tmp_path, "--mode", "grow", "--out", "city.json").returncode == 0
    done = run(["-m", "bibliopolis", "picture", "--city", "city.json", "--out", "city.svg"], tmp_path)
    assert done.returncode == 0 and done.stderr.strip() == shown[0]
    assert shown[0] == f"wrote city.svg: {(tmp_path / 'city.svg').stat().st_size} bytes"


def test_the_picture_of_set_up_is_the_size_the_readme_says_it_is(tmp_path):
    assert build_on_the_sample(tmp_path, "--mode", "grow", "--out", "city.json").returncode == 0
    assert run(["-m", "bibliopolis", "picture", "--city", "city.json", "--out", "city.svg"], tmp_path).returncode == 0
    root = ET.parse(tmp_path / "city.svg").getroot()
    assert float(root.get("width")) == 1800 and float(root.get("height")) < 1800  # the longest side is 1800 pixels: wider than most laptop windows
    assert "1800 pixels wide" in ENGLISH and "寬 1800 像素" in CHINESE


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_files_the_readme_tells_the_reader_to_make_are_ignored_by_git_in_the_folder_of_the_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(ROOT / ".gitignore", tmp_path / ".gitignore")
    made = {shlex.split(c)[shlex.split(c).index("--out") + 1] for half in (ENGLISH, CHINESE) for c in commands(half) if "--out" in shlex.split(c)}
    assert made == {"city.json", "city.svg", "city-mirror.json", "city-41.json", "city-41.svg"}
    for name in sorted(made):
        assert subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", name], check=False).returncode == 0, name  # `git status` stays clean
    assert subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", "docs/images/concept.svg"], check=False).returncode == 1  # the pictures of the page are not


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
    for half, _set_up, grows, _try_it in HALVES:
        heads = (grows, "## Two modes" if half is ENGLISH else "## 兩種模式")
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
