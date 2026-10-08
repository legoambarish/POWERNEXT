"""Use the unchanged ML serving function, including its physical/OOD gates."""
from pathlib import Path
import copy
import json
import os
from .common import ML, PHYSICS, digest, file_hash, write_json
from powernext_config import REGISTRY, MODEL_SELECTION
from powernext_ml.inference import predict
from powernext_ml.physics_adapter import load_adapter
from powernext_ml.common import runtime_versions
from powernext_integrity import verified_snapshot,active_for


def serving_files():
    """Transitive forward-serving dependencies, excluding training/import tools.

    Measured-data archival and offline training do not participate in this
    prediction path. Their edits must not relabel or invalidate its results.
    """
    names=['__init__.py','common.py','features.py','inference.py','models.py','physics_adapter.py','registry.py']
    from powernext_config import ROOT
    return [ROOT/'powernext_integrity.py']+[ML/'powernext_ml'/name for name in names]+sorted((PHYSICS/'physics_engine').glob('*.py'))


class PredictionStack:
    def __init__(self, registry=None, selection=None, cache=None, adapter_name="provisional"):
        self.registry = Path(registry) if registry else REGISTRY
        self.selection = Path(selection) if selection else MODEL_SELECTION
        self.cache = Path(cache) if cache else None
        self.adapter_name = adapter_name
        self.adapter = load_adapter(adapter_name)
        self.models = json.loads(self.selection.read_text()) if self.selection.exists() else {}
        artifacts = {}
        for model_id in sorted(set(self.models.values())):
            artifacts[model_id] = {name:file_hash(self.registry/model_id/name) if (self.registry/model_id/name).exists() else None
                                  for name in ["card.json","model.joblib"]}
        self.provenance = dict(physics=self.adapter.provenance, model_selection=self.models, model_artifacts=artifacts,
            serving_source_hashes={(f"application/{p.name}" if p.name=='powernext_integrity.py' else f"{p.parent.name}/{p.name}"):file_hash(p) for p in serving_files()},
            fingerprint_policy='TRANSITIVE_FORWARD_SERVING_v2',runtime=runtime_versions(), adapter_name=adapter_name)
        self.fingerprint = digest(self.provenance)
        self._tracked = {self.selection: file_hash(self.selection) if self.selection.exists() else None}
        for model_id in artifacts:
            for name in ['card.json','model.joblib']:
                path=self.registry/model_id/name
                self._tracked[path]=file_hash(path) if path.exists() else None
        for path in serving_files()+[PHYSICS/'CPRI_EQUIPMENT_PROFILE.json',PHYSICS/'CIRCUIT_TOPOLOGY_SPEC.md']:
            self._tracked[path]=file_hash(path)

    def assert_unchanged(self):
        """Never serve mutable artifacts under the identity captured at startup."""
        if active_for(self._tracked):return
        for path,expected in self._tracked.items():
            current=file_hash(path) if path.exists() else None
            if current!=expected:raise ValueError('Prediction artifacts changed; restart the stack before another request')

    def batch(self):
        return verified_snapshot(self._tracked)

    def call(self, configuration, setup, target=None, use_cache=True):
        if not active_for(self._tracked):
            with self.batch():
                return self.call(configuration,setup,target,use_cache)
        self.assert_unchanged()
        request=dict(configuration=configuration,setup=setup,target_crest_V=target)
        key=digest(dict(request=request,stack=self.fingerprint))
        path=self.cache/(key+".json") if self.cache and use_cache else None
        if path and path.exists():
            stored=json.loads(path.read_text(encoding="utf-8"))
            if stored["key"]!=key or digest(stored["response"])!=stored["response_sha256"]:
                raise ValueError("Cached prediction integrity mismatch")
            return copy.deepcopy(stored["response"])
        response=predict(request,self.registry,self.selection,self.adapter_name)
        self.assert_unchanged()
        # Latency is recorded by the runner, never allowed into result identity.
        response.pop("end_to_end_ms",None)
        if path:
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix(f".{os.getpid()}.tmp")
            write_json(temp,dict(key=key,response=response,response_sha256=digest(response)))
            os.replace(temp,path)
        return response

    def options(self):
        self.assert_unchanged()
        return dict(registry=str(self.registry),selection=str(self.selection),cache=str(self.cache) if self.cache else None,adapter_name=self.adapter_name)
