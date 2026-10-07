from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

from powernext_config import OPTIMIZER as PACKAGE, ROOT as WORKSPACE, ML, PHYSICS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def log(text):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {text}", file=sys.stderr, flush=True)


class RequestError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)
