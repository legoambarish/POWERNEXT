"""Request-scoped immutable bytes, with full SHA-256 checks at both boundaries.

No mtime-only trust: same-size/same-time replacements are detected. Models,
profiles and route selections are consumed from the bytes that were verified.
The caller must not publish a result until the context exits successfully.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import hashlib
import os

_snapshot=ContextVar('powernext_verified_artifacts',default=None)
IO={'reads':0,'bytes':0}

def _key(path):return os.path.normcase(os.path.abspath(path))

def _read(path):
    value=Path(path).read_bytes();IO['reads']+=1;IO['bytes']+=len(value)
    return value

def strong_hash(path):
    # Streaming boundary validation avoids a second simultaneous model copy.
    h=hashlib.sha256();IO['reads']+=1
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            IO['bytes']+=len(block);h.update(block)
    return h.hexdigest()

def artifact_bytes(path):
    snap=_snapshot.get();key=_key(path)
    return snap[key][1] if snap is not None and key in snap else _read(path)

def file_hash(path):
    snap=_snapshot.get();key=_key(path)
    return snap[key][0] if snap is not None and key in snap else strong_hash(path)

def active_for(expected):
    snap=_snapshot.get()
    return snap is not None and all(_key(p) in snap and snap[_key(p)][0]==h for p,h in expected.items() if h is not None)

@contextmanager
def verified_snapshot(expected):
    if active_for(expected):
        yield
        return
    snap={}
    for path,wanted in expected.items():
        if wanted is None:
            if Path(path).exists():raise ValueError('Prediction artifacts changed; restart the stack')
            continue
        value=_read(path);actual=hashlib.sha256(value).hexdigest()
        if actual!=wanted:raise ValueError('Prediction artifacts changed; restart the stack')
        snap[_key(path)]=(actual,value)
    token=_snapshot.set(snap)
    try:
        yield
        for path,wanted in expected.items():
            actual=strong_hash(path) if Path(path).exists() else None
            if actual!=wanted:raise ValueError('Prediction artifacts changed during calculation; result discarded')
    finally:
        _snapshot.reset(token)
