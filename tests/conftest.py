"""Test setup: the repository root on sys.path, so that `import bibliopolis` works without installing the package; and a home folder of its own for every test."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def a_home_of_its_own(tmp_path_factory, monkeypatch):
    """No test reaches the real home folder of the player's worlds: BIBLIOPOLIS_HOME points into a folder of the test (which is not made until something asks for
    it), so a command that forgets `--world` writes there. Subprocesses inherit it."""
    monkeypatch.setenv("BIBLIOPOLIS_HOME", str(tmp_path_factory.mktemp("home") / "Bibliopolis"))
