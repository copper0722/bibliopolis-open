"""Test setup: the repository root on sys.path, so that `import bibliopolis` works without installing the package."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
