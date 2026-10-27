"""The package itself: standard library only, Python 3.11 syntax, one version."""

import ast
import io
import sys
import tokenize
import tomllib
from pathlib import Path

import pytest

import bibliopolis

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "bibliopolis").glob("*.py"))


def test_the_package_has_its_modules():
    assert {p.stem for p in SOURCES} >= {"__init__", "__main__", "_version", "city", "cli", "coast", "coded", "cut", "document", "inputs", "layout", "picture", "plan", "tree",
                                         "world"}


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


def f_string_problems(source: str) -> list[str]:
    """What an f-string does that Python 3.11 cannot read, and only 3.12 and later can (PEP 701): inside the braces, a backslash, a comment, the quote of
    the f-string itself, a line break in a one-line f-string. `ast.parse(feature_version=(3, 11))` does not see these. Needs the tokens of 3.12."""
    problems = []
    stack: list[list] = []  # one entry per open f-string: [its quote, how many braces are open]
    for kind, text, (row, _col), _end, _line in tokenize.generate_tokens(io.StringIO(source).readline):
        open_field = bool(stack) and stack[-1][1] > 0
        if open_field:
            quote = stack[-1][0]
            same = (quote if len(quote) == 3 else quote[0]) in text
            if kind in (tokenize.STRING, tokenize.FSTRING_START) and "\\" in text:
                problems.append(f"line {row}: a backslash inside the braces of an f-string: {text[:30]!r}")
            elif kind in (tokenize.STRING, tokenize.FSTRING_START) and same:
                problems.append(f"line {row}: the quote of the f-string inside its braces: {text[:30]!r}")
            elif kind == tokenize.COMMENT or (kind == tokenize.NL and len(quote) == 1):
                problems.append(f"line {row}: a comment or a line break inside the braces of a one-line f-string")
        if kind == tokenize.FSTRING_START:
            stack.append([text.lstrip("rRfFbBuU"), 0])
        elif kind == tokenize.FSTRING_END:
            stack.pop()
        elif kind == tokenize.OP and stack and text in ("{", "}"):
            stack[-1][1] += 1 if text == "{" else -1
    return problems


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python 3.11 refuses such a file by itself")
def test_no_f_string_of_the_package_needs_python_3_12():
    for path in [*SOURCES, *sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "examples").glob("*.py"))]:
        assert f_string_problems(path.read_text(encoding="utf-8")) == [], path.name


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python 3.11 refuses such a file by itself")
@pytest.mark.parametrize("source, found", [
    ("x = f'{a[\"k\"]}'", 0),  # another quote: fine on 3.11
    ("x = f\"{a['k']}\"", 0),
    ('x = f"""{a["k"]}"""', 0),  # a single quote inside a triple-quoted f-string: fine
    ("x = f'{a:>{w}}' f\"{b['k']:.2f}\"", 0),  # a format spec with a field of its own; two f-strings side by side, each with its own quote
    ("x = f'{{a}} {b}\\n'", 0),  # a backslash and braces in the text of the f-string are fine
    ('x = f"{a["k"]}"', 1),  # the quote of the f-string inside the braces
    ('x = f"""{a["""k"""]}"""', 1),
    ("x = f\"{re.match(r'\\d', a)}\"", 1),  # a backslash inside the braces
    ('x = f"{\n a }"', 1),  # a line break inside the braces of a one-line f-string
    ('x = f"""{\n a }"""', 0),  # ... but not of a triple-quoted one
    ('x = f"{a # why\n}"', 1),  # a comment
    ("x = f'{f\"{a}\"}'", 0),  # an f-string in an f-string with another quote
    ("x = f'{f'{a}'}'", 1),  # ... and with the same quote
])
def test_the_f_string_check_sees_what_python_3_11_cannot_read(source, found):
    assert bool(f_string_problems(source)) is bool(found), f_string_problems(source)


def test_the_version_is_one_in_the_package_and_in_the_project_file():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == bibliopolis.__version__ and project["requires-python"] == ">=3.11" and project["license"] == "MIT"
    assert not project.get("dependencies")


def test_the_modules_say_what_they_are_for():
    for path in SOURCES:
        if path.stem != "__main__":
            assert ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))), f"{path.name} has no docstring"
