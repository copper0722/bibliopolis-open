"""The one number form of every document the package writes.

A document that the package writes spells a number the way JavaScript's `JSON.stringify` does, so that a port in another language can match the bytes:

  an integral value has no fraction     40, not 40.0   (and -0.0 is 0)
  any other value is its shortest text  12.345, the text `repr` gives, which JavaScript gives too

The text of a string, the order of the keys and the layout of the lines are those of `json.dumps(..., ensure_ascii=False)`; only the numbers are
written here. The documents in memory keep their Python floats (the engine computes with them); the form is applied when a document is written.

A number that the two languages would write differently is refused, not written: the exponent forms (`1e-05`, which JavaScript writes `0.00001`),
and any value of 10**15 or more. The engine rounds every coordinate to three decimals, so a document of the package never meets either.
"""

from __future__ import annotations

import json
import math

LIMIT = 10**15  # from here on a float or an integer is not written: JavaScript reads it back to another number, or spells it with an exponent


def number(value: int | float) -> str:
    """The text of one number in the canonical form; `ValueError` for a value that cannot be written the same everywhere."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{value!r} is not a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{value!r} cannot be written in JSON")
    if abs(value) >= LIMIT:
        raise ValueError(f"{value!r} is too large to be written the same everywhere (the limit is {LIMIT})")
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    text = repr(value)
    if "e" in text or "E" in text:
        raise ValueError(f"{value!r} would be written with an exponent, which another language spells differently")
    return text


def dumps(value, *, indent: int | None = None) -> str:
    """The JSON text of `value`: `json.dumps(value, ensure_ascii=False)` with the numbers of `number`. `indent=None` is the compact form (separators
    `,` and `:`), a whole number is the pretty form `json.dumps(indent=n)` writes (`,` and `: `, one item to a line, `{}` and `[]` for an empty one)."""
    out: list[str] = []
    _write(value, out, indent, 0)
    return "".join(out)


def _write(value, out: list[str], indent: int | None, level: int) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, (int, float)):
        out.append(number(value))
    elif isinstance(value, dict):
        _container(out, "{", "}", [(k, v) for k, v in value.items()], indent, level, True)
    elif isinstance(value, (list, tuple)):
        _container(out, "[", "]", [(None, v) for v in value], indent, level, False)
    else:
        raise TypeError(f"{type(value).__name__} cannot be written in JSON")


def _container(out: list[str], open_: str, close: str, rows: list[tuple], indent: int | None, level: int, keyed: bool) -> None:
    if not rows:
        out.append(open_ + close)
        return
    colon = ": " if indent is not None else ":"
    inner = "\n" + " " * (indent * (level + 1)) if indent is not None else ""
    out.append(open_ + inner)
    for i, (key, item) in enumerate(rows):
        if i:
            out.append("," + inner)
        if keyed:
            if not isinstance(key, str):
                raise TypeError(f"a key of a JSON object must be a string, got {key!r}")
            out.append(json.dumps(key, ensure_ascii=False) + colon)
        _write(item, out, indent, level + 1)
    out.append(("\n" + " " * (indent * level) if indent is not None else "") + close)
