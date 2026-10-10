"""Versioned network-search extension; legacy scientific artifacts remain intact."""
from pathlib import Path
import os
import sys

__version__ = "3.0.0"
ROOT = Path(__file__).resolve().parent.parent
for _part in ("physics", "ml", "optimizer"):
    _path = str(ROOT / "powernext" / _part)
    if _path not in sys.path:
        sys.path.insert(0, _path)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

