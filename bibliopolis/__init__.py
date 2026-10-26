"""Bibliopolis: turn a literature collection into a city-state.

Every item of a library is a house. Topics are roads that radiate from the town hall at the centre. Two modes: `grow` (the roads open as the
houses arrive: a road holds 10 to 40 houses and a crowded one opens a road for its largest group) and `mirror` (the topic tree is the street plan).

    from bibliopolis import build_city, render
    document = build_city(library, tree, mode="grow")    # a layout v4 document (dict)
    text = render(document)                              # the stable text it is written as

The command line is `python -m bibliopolis build --help`.
"""

from ._version import __version__
from .city import build_city, build_world, summary
from .inputs import InputError
from .layout import render
from .plan import GROW, MIRROR, MODES

__all__ = ["__version__", "build_city", "build_world", "summary", "render", "InputError", "GROW", "MIRROR", "MODES"]
