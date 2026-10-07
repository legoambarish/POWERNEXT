"""Central portable application configuration. Engineering profiles stay versioned."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
PHYSICS = ROOT / 'powernext/physics'
ML = ROOT / 'powernext/ml'
OPTIMIZER = ROOT / 'powernext/optimizer'
UI = ROOT / 'ui'
PROFILE = PHYSICS / 'CPRI_EQUIPMENT_PROFILE.json'
REGISTRY = ML / 'registry/simulation_v2'
MODEL_SELECTION = ML / 'results/simulation_v2/selected_models.json'
DEMOS = OPTIMIZER / 'examples'
DATA = ROOT / 'data'
HOST = '127.0.0.1'
PORT = 8765
TIMEOUT_SECONDS = 360
WORKERS = 4
RUNTIME_MODE = 'OFFLINE_PROVISIONAL'

for path in (ROOT, PHYSICS, ML, OPTIMIZER):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('MPLCONFIGDIR', str(DATA / 'matplotlib'))
sys.dont_write_bytecode = True

def validate_assets():
    import json
    required=[PROFILE, MODEL_SELECTION, DEMOS/'SI_request.json']+[UI/name for name in ['index.html','app.js','app.css','views.js','format.js','charts.js','waveform.js','scenarios.js','imports.js']]
    missing=[str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing: raise RuntimeError('Incomplete release: missing '+', '.join(missing))
    selection=json.loads(MODEL_SELECTION.read_text(encoding='utf-8'))
    expected={f'{mode}:{top}' for mode in ('LI','SI') for top in ('GSHUNT_v0','OSHUNT_v0')}
    if set(selection)!=expected:raise RuntimeError('Incomplete model selection; four versioned routes are required')
    for route,model in selection.items():
        if not isinstance(model,str) or Path(model).name!=model:raise RuntimeError('Invalid model identifier')
        for name in ('card.json','model.joblib'):
            if not (REGISTRY/model/name).is_file():raise RuntimeError(f'Missing model asset: {route} / {name}')

def validate_models(app):
    from powernext_ml.registry import load_model
    for route,identifier in app.stack.models.items():
        _,card=load_model(app.stack.registry/identifier,app.catalog.adapter.provenance)
        mode,topology=route.split(':')
        if (card['domain'],card['mode'],card['topology_version'],card['model_id']) != ('simulation',mode,topology,identifier):
            raise RuntimeError('Model route/card mismatch: '+route)
    app.stack.assert_unchanged()

# Acceptance mode blocks outbound connections in the application and every spawned
# worker. It is opt-in solely so the report can state the exact tested boundary.
if os.environ.get('POWERNEXT_TEST_OFFLINE') == '1':
    import socket
    _connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex
    def _local(address):
        if isinstance(address, tuple) and str(address[0]) not in {'127.0.0.1','::1','localhost'}:
            raise OSError('PowerNext offline acceptance: outbound network disabled')
    def _offline_connect(sock,address):
        _local(address)
        return _connect(sock,address)
    def _offline_connect_ex(sock,address):
        _local(address)
        return _connect_ex(sock,address)
    socket.socket.connect, socket.socket.connect_ex = _offline_connect, _offline_connect_ex
