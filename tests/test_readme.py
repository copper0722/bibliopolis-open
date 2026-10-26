"""The README does not drift from the program: its commands run, and the line it shows is the line the command prints."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def commands():
    return [line.strip() for line in README.splitlines() if line.strip().startswith("python -m bibliopolis build")]


def run(argv, cwd):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, *argv], cwd=cwd, env=env, capture_output=True, text=True, check=False)


def test_the_commands_of_the_readme_run_on_the_files_of_the_repository(tmp_path):
    found = commands()
    assert len(found) == 4 and {"grow", "mirror"} == {shlex.split(c)[shlex.split(c).index("--mode") + 1] for c in found}  # English and Traditional Chinese
    for command in found:
        argv = shlex.split(command)[1:]  # without `python`
        for flag in ("--library", "--tree"):
            argv[argv.index(flag) + 1] = str(ROOT / argv[argv.index(flag) + 1])
        out = argv[argv.index("--out") + 1]
        assert not Path(out).is_absolute()  # the command writes where the reader stands
        done = run(argv, tmp_path)
        assert done.returncode == 0, done.stderr
        assert (tmp_path / out).is_file()


def test_the_readme_shows_the_line_the_command_prints_on_the_sample(tmp_path):
    shown = re.findall(r"^wrote city\.json: .*$", README, flags=re.M)
    assert len(shown) == 2 and shown[0] == shown[1]
    done = run(["-m", "bibliopolis", "build", "--library", str(ROOT / "examples/library.json"), "--tree", str(ROOT / "examples/tree.json"),
                "--mode", "grow", "--out", "city.json"], tmp_path)
    assert done.returncode == 0 and done.stderr.strip() == shown[0]


def test_the_two_halves_of_the_readme_say_the_same_numbers():
    english, chinese = README.split("\n---\n", 1)
    for number in ("40", "10", "41", "600", "80"):
        assert number in english and number in chinese, number
    assert english.count("```") == chinese.count("```")  # the same code blocks in both languages
