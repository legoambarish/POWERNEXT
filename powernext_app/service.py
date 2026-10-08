"""Thin application boundary around frozen optimizer and measured-data APIs."""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
import copy,json,os,subprocess,sys,time,threading,tempfile,uuid
import numpy as np
from . import __version__
from .common import PACKAGE,OPTIMIZER,ML,PHYSICS,read_json,write_json,file_hash,digest,safe_child,checked_id,now
from .fixtures import DEMOS,demo
from .store import RunStore
from .process import stream_process
from powernext_config import WORKERS, TIMEOUT_SECONDS, DEMOS as DEMO_DIR
from powernext_optimizer.catalog import Catalog,normalize_request
from powernext_optimizer.prediction import PredictionStack
from powernext_optimizer.storage import HistoryStore
from powernext_optimizer.assessment import rank_key
from powernext_ml.measured import ingest_measurement
from powernext_ml.screening import screen_batch
from physics_engine.target import nominal_target

@lru_cache(maxsize=64)
def _target(mode,crest,polarity):
    return nominal_target(mode,crest,polarity)

class Application:
    def __init__(self,data_dir,*,adapter='provisional',registry=None,selection=None,workers=WORKERS,timeout_seconds=TIMEOUT_SECONDS):
        if type(timeout_seconds) not in (int,float) or not np.isfinite(timeout_seconds) or timeout_seconds<=0:raise ValueError('Positive finite optimization timeout required')
        self.timeout_seconds=timeout_seconds
        self.store=RunStore(data_dir);self.store.recover_interrupted();self.adapter_name=adapter;self.workers=workers
        self.catalog=Catalog(adapter)
        self.stack=PredictionStack(registry,selection,None,adapter)
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='optimizer')
        self.guard=threading.Lock();self.active=None
        self._candidate_cache=OrderedDict();self._candidate_cache_lock=threading.Lock()
        self.history=HistoryStore(self.store.root/'optimizer_history.sqlite')

    def close(self):self.executor.shutdown(wait=True)

    def _compatible(self,result):
        if not result or result.get('stack_sha256')!=self.stack.fingerprint:return False
        current={p.name:file_hash(p) for p in sorted((OPTIMIZER/'powernext_optimizer').glob('*.py'))}
        return result.get('optimizer_source_hashes')==current

    def metadata(self):
        from .equipment import coverage
        return dict(application_version=__version__,profile=self.catalog.profile,physics_provenance=self.catalog.adapter.provenance,
            parameter_coverage=coverage(),technical_documents=['IEC_AND_PS_COMPLIANCE_VERIFICATION.md','IVG_PARAMETER_COVERAGE.md','INTEGRATION_AND_REGRESSION_REPORT.md','PERFORMANCE_REPORT.md'],
            stack_sha256=self.stack.fingerprint,model_selection=self.stack.models,demonstrations=DEMOS,
            default_request=read_json(DEMO_DIR/'SI_request.json'),
            data_directory=str(self.store.root),offline=True,hardware_control=False)

    def validate(self,request,annotations=None):
        request=normalize_request(request,self.catalog)
        annotations=annotations or {}
        if not isinstance(annotations,dict) or set(annotations)-{'value_provenance','notes'}:raise ValueError('Invalid application annotations')
        if not isinstance(annotations.get('notes',''),str):raise ValueError('Notes must be text')
        fields={'target_crest_V','dut_capacitance_F','divider_capacitance_F','stray_capacitance_F','loop_inductance_H','loop_resistance_ohm','load_resistance_ohm'}
        provenance=annotations.get('value_provenance',{})
        if not isinstance(provenance,dict) or set(provenance)-fields or any(v not in ['known','measured','estimated','assumed'] for v in provenance.values()):raise ValueError('Invalid value provenance')
        def electrical_identity(q):
            try:q=normalize_request(q,self.catalog)
            except (ValueError,KeyError,TypeError):q=copy.deepcopy(q)
            q.pop('request_id',None)
            q.get('setup',{}).pop('setup_id',None)
            return digest(q)
        matches=[dict(run_id=m['run_id'],created_at=m['created_at'],source=m['source'],same_stack=m.get('stack_sha256')==self.stack.fingerprint and self._compatible(self.store.result(m['run_id']))) for m in self.store.list() if m.get('status')=='COMPLETED' and electrical_identity(m.get('request',{}))==electrical_identity(request)]
        return dict(request=request,annotations=annotations,catalog_count=len(self.catalog.entries_for_request(request)),previous_exact_cases=matches)

    def optimize(self,request,annotations=None):
        validated=self.validate(request,annotations)
        with self.guard:
            if self.active and not self.active.done():raise ValueError('Another optimization is running; open it from Saved runs')
            data=self.store.create(validated['request'],validated['annotations'])
            self.active=self.executor.submit(self._run,data)
        return data

    def _run(self,data):
        folder=self.store.directory(data['run_id']);start=time.perf_counter()
        data.update(status='RUNNING',progress='Starting the versioned Physics + ML stack');self.store.update(data)
        # The final result already persists every evaluated waveform as hashed
        # NPZ evidence. Serializing both gain-probe and charged waveforms again
        # into a JSON cache made a cold one-worker UI search ~4x slower. Exact
        # request reuse is provided by immutable history; CLI caching remains
        # available explicitly for research workloads.
        command=[sys.executable,'-m','powernext_optimizer','recommend','--request',str(folder/'request.json'),'--output',str(folder/'result.json'),'--workers',str(self.workers),'--history',str(self.history.path),'--adapter',self.adapter_name,'--registry',str(self.stack.registry),'--selection',str(self.stack.selection)]
        env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
        try:
            with (folder/'execution.log').open('w',encoding='utf-8') as output:
                def progress(line):
                    if line.startswith('['):data['progress']=line.strip();data['elapsed_seconds']=time.perf_counter()-start;self.store.update(data)
                code=stream_process(command,cwd=OPTIMIZER,env=env,output=output,on_progress=progress,timeout_seconds=self.timeout_seconds)
            if code or not (folder/'result.json').exists():raise RuntimeError((folder/'execution.log').read_text(encoding='utf-8')[-3000:])
            self.store.finish(data,folder/'result.json',time.perf_counter()-start)
        except Exception as exc:
            data.update(status='FAILED',completed_at=now(),progress='Optimization failed',error=str(exc),elapsed_seconds=time.perf_counter()-start);self.store.update(data)

    def load_demo(self,identifier):
        d=demo(identifier)
        if not d:raise FileNotFoundError('Demo not found')
        data=self.store.import_demo(read_json(DEMO_DIR/d['request']),DEMO_DIR/d['result'],identifier)
        self.history.record(self.store.result_path(data['run_id']),self.store.result(data['run_id']))
        return data

    def get_run(self,identifier):
        meta=self.store.metadata(identifier)
        result=self.store.result(identifier) if meta['status']=='COMPLETED' else None
        return dict(run=meta,result=result,artifact_compatibility='MATCHES_CURRENT_STACK' if self._compatible(result) else 'RECORDED_ARTIFACT_DIFFERENT_OR_UNAVAILABLE_STACK')

    def candidate(self,run_id,candidate_id):
        # Expanded catalogs contain multi-megabyte JSON. Verify the actual file
        # on EVERY call, but parse/index an immutable verified snapshot only once.
        path=self.store.result_path(run_id)
        expected=self.store.metadata(run_id)['result_sha256'];key=(run_id,expected)
        with self._candidate_cache_lock:
            if key not in self._candidate_cache:
                result=read_json(path)
                if file_hash(path)!=expected:raise ValueError('Result changed while indexing')
                self._candidate_cache[key]=(result,{r['candidate_id']:r for r in result['candidates']})
                while len(self._candidate_cache)>2:self._candidate_cache.popitem(last=False)
            self._candidate_cache.move_to_end(key)
            result,index=self._candidate_cache[key];row=index.get(candidate_id)
        if not row:raise FileNotFoundError('Candidate not found')
        return result,copy.deepcopy(row)

    def waveform(self,run_id,candidate_id):
        result,row=self.candidate(run_id,candidate_id);ref=row.get('waveform_reference')
        if not ref:raise ValueError('No evaluable waveform artifact was produced')
        path=safe_child(self.store.directory(run_id),ref['path'])
        if file_hash(path)!=ref['sha256']:raise ValueError('Waveform integrity mismatch')
        with np.load(path,allow_pickle=False) as z:arrays={k:z[k].tolist() for k in ['time_s','voltage_V']}
        q=result['request'];same=result.get('provenance',{}).get('physics')==self.catalog.adapter.provenance
        target=copy.deepcopy(_target(q['impulse_type'],q['target_crest_V'],q['polarity'])) if same else None
        return dict(**arrays,metrics=row['prediction']['physics_reference']['metrics'],sha256=ref['sha256'],curve_id=ref['curve_id'],sample_count=len(arrays['time_s']),target=target,
                    target_unavailable_reason=None if same else 'Historical physics provenance differs; current target not attached.')

    def screen_scenarios(self,scenarios):
        with self.stack.batch():
            return screen_batch(scenarios,self.stack.registry,self.stack.selection,self.adapter_name)

    def evidence(self,run_id,candidate_id):
        result,row=self.candidate(run_id,candidate_id);prediction=row.get('prediction') or {}
        model_id=prediction.get('model_id') or result.get('provenance',{}).get('model_selection',{}).get(f"{result['request']['impulse_type']}:{row['topology_id']}")
        card=None;baseline=None;baseline_reason=None
        if model_id:
            path=self.stack.registry/checked_id(model_id)/'card.json'
            expected=result.get('provenance',{}).get('model_artifacts',{}).get(model_id,{}).get('card.json')
            if path.exists() and expected==file_hash(path):
                source=read_json(path)
                card={k:source.get(k) for k in ['model_id','model_family','formulation','domain','mode','topology_version','test_metrics','provenance','deployment_status','real_data_calibrated','uncertainty_status']}
                card['split_counts']={k:len(source['selection'][k]) for k in ['train_rows','validation_rows','test_rows']}
        # Serving hardening does not change an RC calculation. Recompute only
        # if the entire recorded Physics/profile/baseline provenance is equal.
        if result.get('provenance',{}).get('physics')==self.catalog.adapter.provenance:
            try:
                features=self.catalog.adapter.features(row['configuration'],result['request']['setup'])
                reference=prediction['physics_reference']
                baseline=dict(gain=features['baseline_gain'],crest_V=features['baseline_gain']*abs(reference['derived']['U0_V']),front_s=features['baseline_front_us']*1e-6,T2_s=features['baseline_tail_us']*1e-6,version=self.catalog.adapter.provenance['baseline_version'],label='Independent RC baseline (L = 0)')
            except (ValueError,KeyError,TypeError) as exc:baseline_reason=str(exc)
        else:baseline_reason='Stored Physics/profile/baseline provenance differs; baseline is not recomputed with a different version.'
        return dict(baseline=baseline,baseline_unavailable_reason=baseline_reason,model_card=card,prediction=prediction,
            final_authority='Saved reference waveform and original deterministic evaluator',evidence_domain='Simulation emulation; not CPRI laboratory accuracy')

    def compare(self,run_id,left_id,right_id):
        _,a=self.candidate(run_id,left_id);_,b=self.candidate(run_id,right_id)
        names=['validity / numerical compliance','reference conformity score J','minimum compliance margin','changed hardware fields','stored energy','active stages','front resistance','tail resistance','stable candidate ID']
        ka,kb=rank_key(a),rank_key(b)
        decisive=next((name for name,x,y in zip(names,ka,kb) if x!=y),'identical ranking keys')
        return dict(left_id=left_id,right_id=right_id,preferred_id=left_id if ka<kb else right_id if kb<ka else None,decisive_factor=decisive,policy='Original optimizer lexicographic ordering; no UI reranking')

    def import_measurement(self,run_id,raw_csv,metadata,metadata_text=None):
        self.store.result(run_id)
        if not isinstance(raw_csv,(str,bytes)) or not isinstance(metadata,dict):raise ValueError('CSV bytes/text and source metadata are required')
        measurement_id='shot_'+uuid.uuid4().hex[:20]
        folder=self.store.directory(run_id)/'measurements';folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.store.root) as temporary:
            temporary=Path(temporary);(temporary/'raw.csv').write_bytes(raw_csv if isinstance(raw_csv,bytes) else raw_csv.encode('utf-8'));write_json(temporary/'metadata.json',metadata)
            if metadata_text is not None:
                if not isinstance(metadata_text,str) or json.loads(metadata_text)!=metadata:raise ValueError('Metadata text and object differ')
                (temporary/'metadata.json').write_bytes(metadata_text.encode('utf-8'))
            record=ingest_measurement(temporary/'raw.csv',temporary/'metadata.json',folder/measurement_id)
        write_json(folder/measurement_id/'application_integrity.json',{name:file_hash(folder/measurement_id/name) for name in ['raw_export.csv','source_metadata.json','waveform_SI.npz','record.json']})
        return dict(measurement_id=measurement_id,record=record,source_identity_policy='User-declared evidence kind; not independently authenticated')

    def measurements(self,run_id):
        self.store.result(run_id)
        folder=self.store.directory(run_id)/'measurements'
        return [dict(measurement_id=p.parent.name,shot_id=read_json(p)['metadata']['shot_id']) for p in sorted(folder.glob('shot_*/record.json'))]

    def measured_waveform(self,run_id,measurement_id):
        folder=safe_child(self.store.directory(run_id)/'measurements',checked_id(measurement_id));record=read_json(folder/'record.json')
        for name,expected in read_json(folder/'application_integrity.json').items():
            if file_hash(safe_child(folder,name))!=expected:raise ValueError('Measured artifact integrity mismatch')
        if file_hash(folder/'raw_export.csv')!=record['raw_sha256'] or file_hash(folder/'source_metadata.json')!=record['metadata_sha256']:raise ValueError('Measured source integrity mismatch')
        with np.load(folder/'waveform_SI.npz',allow_pickle=False) as z:arrays={k:z[k].tolist() for k in ['time_s','voltage_V']}
        return dict(record=record,**arrays)
