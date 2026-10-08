"""Complete, bounded evidence transfer. Imported records never load code/models."""
import io,json,zipfile,hashlib
from pathlib import PurePosixPath
from .common import read_json,write_json,file_hash,safe_child

def build_bundle(app,run_id,report):
    path=app.store.result_path(run_id);result=read_json(path);root=path.parent
    names={'result.json','request.json','run.json'}
    manifest=result.get('artifact_manifest')
    if manifest:
        m=safe_child(root,manifest['path'])
        if file_hash(m)!=manifest['sha256']:raise ValueError('Artifact manifest integrity mismatch')
        names.add(manifest['path'])
        for ref in read_json(m)['files']:
            if file_hash(safe_child(root,ref['path']))!=ref['sha256']:raise ValueError('Waveform integrity mismatch')
            names.add(ref['path'])
    for measurement in app.measurements(run_id):
        mid=measurement['measurement_id'];app.measured_waveform(run_id,mid)
        for name in ['raw_export.csv','source_metadata.json','waveform_SI.npz','record.json','application_integrity.json']:
            names.add(f'measurements/{mid}/{name}')
    payload={name:safe_child(root,name).read_bytes() for name in sorted(names)}
    payload['engineering_report.html']=report.encode('utf-8') if isinstance(report,str) else report
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}
    payload['bundle_manifest.json']=json.dumps(dict(schema_version='powernext_evidence_bundle_v2',files=hashes,source_identity='User supplied; integrity does not authenticate laboratory provenance'),indent=2).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
    return stream.getvalue()

def reopen_bundle(app,raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=200_000_000:raise ValueError('Evidence ZIP must be at most 200 MB')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=archive.infolist();names=[i.filename for i in infos]
            if len(names)>10000 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>400_000_000:
                raise ValueError('Duplicate members or excessive expanded bundle size')
            for name in names:
                p=PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not p.parts or str(p)!=name or p.suffix not in ('.json','.npz','.csv','.html'):
                    raise ValueError('Invalid evidence member path/type')
            if 'bundle_manifest.json' not in names:raise ValueError('Use a complete PowerNext evidence bundle v2')
            manifest=json.loads(archive.read('bundle_manifest.json'))
            if manifest.get('schema_version')!='powernext_evidence_bundle_v2' or set(manifest.get('files',{}))!=set(names)-{'bundle_manifest.json'}:raise ValueError('Incomplete bundle manifest')
            payload={name:archive.read(name) for name in names}
            for name,expected in manifest['files'].items():
                if hashlib.sha256(payload[name]).hexdigest()!=expected:raise ValueError('Bundle integrity mismatch')
    except (zipfile.BadZipFile,json.JSONDecodeError,KeyError) as exc:raise ValueError('Invalid evidence bundle') from exc
    if not {'result.json','request.json','run.json'}<=payload.keys():raise ValueError('Missing engineering record')
    result=json.loads(payload['result.json']);request=json.loads(payload['request.json']);prior=json.loads(payload['run.json'])
    def contained(original,normalized):
        return all(k in normalized and contained(v,normalized[k]) for k,v in original.items()) if isinstance(original,dict) and isinstance(normalized,dict) else original==normalized
    if result.get('schema_version')!='recommendation_result_v1' or not isinstance(result.get('candidates'),list) or not contained(request,result.get('request',{})) or prior.get('request')!=request:raise ValueError('Invalid recommendation record')
    # Browser views expect numeric engineering fields and identifier tokens.
    # Integrity is not authentication: reject data that could become markup.
    import math,re
    def validate_configuration(c):
        for key in ('stages','stage_charge_V','front_per_stage_ohm','tail_per_stage_ohm'):
            value=c.get(key)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<=0):raise ValueError('Invalid imported configuration value')
        for key in ('recipe_id','topology_id','impulse_type'):
            if not isinstance(c.get(key),str) or not re.fullmatch(r'[A-Za-z0-9_]+',c[key]):raise ValueError('Invalid configuration identifier')
    rows=result['candidates']+[r for r in [result.get('best_configuration'),result.get('closest_noncompliant')] if r]+result.get('ranked_alternatives',[])
    for row in rows:
        if not re.fullmatch(r'cfg_[a-f0-9]+',row.get('candidate_id','')):raise ValueError('Invalid candidate identifier')
        validate_configuration(row['configuration'])
        if type(row.get('rank')) is not int or type(row.get('ranking_tier')) is not int:raise ValueError('Invalid candidate rank')
    if result['request'].get('impulse_type') not in ('LI','SI'):raise ValueError('Invalid impulse type')
    if prior.get('result_sha256')!=hashlib.sha256(payload['result.json']).hexdigest():raise ValueError('Result identity mismatch')
    def verify_reference(ref):
        if ref['path'] not in payload or hashlib.sha256(payload[ref['path']]).hexdigest()!=ref['sha256']:raise ValueError('Missing or altered referenced waveform')
    if result.get('artifact_manifest'):
        verify_reference(result['artifact_manifest'])
        for ref in json.loads(payload[result['artifact_manifest']['path']])['files']:verify_reference(ref)
    for row in result['candidates']:
        if row.get('waveform_reference'):verify_reference(row['waveform_reference'])
    for name in names:
        if name.startswith('measurements/') and name.endswith('/record.json'):
            prefix=name.rsplit('/',1)[0];record=json.loads(payload[name]);index=json.loads(payload.get(prefix+'/application_integrity.json',b'{}'))
            if set(index)!={'raw_export.csv','source_metadata.json','waveform_SI.npz','record.json'}:raise ValueError('Incomplete measurement archive')
            for child,expected in index.items():
                if hashlib.sha256(payload.get(prefix+'/'+child,b'')).hexdigest()!=expected:raise ValueError('Measured archive integrity mismatch')
            if index['raw_export.csv']!=record['raw_sha256'] or index['source_metadata.json']!=record['metadata_sha256']:raise ValueError('Measured source identity mismatch')
    # All validation precedes writes. Imported HTML is retained as evidence, not
    # served as executable content. Reports are regenerated with escaped values.
    data=app.store.create(request,prior.get('annotations'),source='REOPENED_EVIDENCE')
    folder=app.store.directory(data['run_id'])
    for name,value in payload.items():
        destination='imported_run_metadata.json' if name=='run.json' else name
        target=safe_child(folder,destination);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
    data['original_run_id']=prior.get('run_id');data['source_bundle_sha256']=hashlib.sha256(raw).hexdigest()
    data['source_identity_policy']='USER_SUPPLIED_NOT_AUTHENTICATED'
    app.store.finish(data,folder/'result.json')
    return data
