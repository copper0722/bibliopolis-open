"""The package itself: standard library only, Python 3.11 syntax, one version."""

import ast
import sys
import tomllib
from pathlib import Path

import bibliopolis

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "bibliopolis").glob("*.py"))


def test_the_package_has_its_modules():
    assert {p.stem for p in SOURCES} >= {"__init__", "__main__", "_version", "city", "cli", "coast", "cut", "document", "inputs", "layout", "plan", "tree", "world"}


def test_the_package_imports_nothing_but_the_standard_library_and_itself():
    stdlib = set(sys.stdlib_module_names)
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                assert name.split(".")[0] in stdlib, f"{path.name} imports {name}, which is not in the standard library"


def test_every_source_file_parses_as_python_3_11():
    for path in [*SOURCES, *sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "examples").glob("*.py"))]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))


def test_the_version_is_one_in_the_package_and_in_the_project_file():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == bibliopolis.__version__ and project["requires-python"] == ">=3.11" and project["license"] == "MIT"
    assert not project.get("dependencies")


def test_the_modules_say_what_they_are_for():
    for path in SOURCES:
        if path.stem != "__main__":
            assert ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))), f"{path.name} has no docstring"
