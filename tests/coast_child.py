"""The child process of the memory tests of tests/test_budget.py (not collected: the name has no test_ prefix).

    python tests/coast_child.py engine|control MIB

Builds the sparse city of the review (the rule max 2400, 2000 houses all on one road: its farthest point is 1396 cells from the town hall, a grid of 7868025 cells, inside the budget of
8388608), under a limit of MIB mebibytes of address space, and draws its coast: `engine` with `bibliopolis.coast.coast_of`, `control` with the stack of tuples that it had
(`support.coast_with_tuple_stack`). Prints one line of JSON: the outcome, the cells of the grid, the number of polygons and a digest of them. A MemoryError is an outcome, not a crash."""

import hashlib
import json
import resource
import sys
from pathlib import Path

mode, mib = sys.argv[1], int(sys.argv[2])
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
resource.setrlimit(resource.RLIMIT_AS, (mib * 2**20, mib * 2**20))  # before the heavy imports: the limit counts all the address space of the process

from hand_support import Hand, houses, topic  # noqa: E402
from support import coast_with_tuple_stack  # noqa: E402

from bibliopolis import coast  # noqa: E402

result = {"mode": mode, "limit_mib": mib}
try:
    h = Hand({"max": 2400, "min": 1, "auto": False, "branches": 13})
    h.add(2000, topic(1, 1, 1, 1))
    h.open("a", "A", None, houses(1, 2000))
    layout = h.state.city(with_coast=False)
    draw = coast.coast_of if mode == "engine" else coast_with_tuple_stack
    polygons = draw(layout)["polygons"]
    result.update(outcome="ok", polygons=len(polygons), digest=hashlib.sha256(json.dumps(polygons).encode()).hexdigest())
except MemoryError:
    result.update(outcome="memory error")
print(json.dumps(result))
