from pathlib import Path
from datetime import datetime, timezone
import sys,json,re

from powernext_config import ROOT as PACKAGE, ROOT as WORKSPACE, OPTIMIZER
from powernext_optimizer.common import file_hash,digest,write_json,ML,PHYSICS

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def safe_child(root,relative):
    root=Path(root).resolve();p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ValueError('Artifact path escapes its bundle')
    return p

def checked_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',value):raise ValueError('Invalid identifier')
    return value
