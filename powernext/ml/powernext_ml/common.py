from __future__ import annotations
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone
import platform

from powernext_config import ML as PACKAGE, ROOT as WORKSPACE, PHYSICS


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


from powernext_integrity import file_hash


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False), encoding="utf-8")


def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def runtime_versions():
    import numpy, scipy, pandas, sklearn, openpyxl
    return dict(python=platform.python_version(), platform=platform.platform(), numpy=numpy.__version__, scipy=scipy.__version__, pandas=pandas.__version__, sklearn=sklearn.__version__, openpyxl=openpyxl.__version__)


def source_hashes():
    return {str(p.relative_to(PACKAGE)): file_hash(p) for p in sorted((PACKAGE / "powernext_ml").glob("*.py"))}
