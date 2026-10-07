"""Local immutable artifact store; app metadata stays outside optimizer JSON."""
import sqlite3,uuid,copy,shutil
from .common import now,read_json,write_json,file_hash,safe_child,checked_id
from . import __version__

class RunStore:
    def __init__(self,root):
        from pathlib import Path
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.runs=self.root/'runs';self.runs.mkdir(exist_ok=True)
        self.database=self.root/'application.sqlite'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, metadata TEXT NOT NULL)')

    def db(self):return sqlite3.connect(self.database,timeout=30)

    def directory(self,run_id):return safe_child(self.runs,checked_id(run_id))

    def create(self,request,annotations=None,source='LIVE_OPTIMIZATION',demo_id=None):
        run_id='run_'+uuid.uuid4().hex[:20];folder=self.directory(run_id);folder.mkdir()
        data=dict(run_id=run_id,application_version=__version__,created_at=now(),status='QUEUED',source=source,demo_id=demo_id,request=request,annotations=annotations or {},elapsed_seconds=None,progress='Queued',result_sha256=None)
        write_json(folder/'request.json',request);self.update(data)
        return data

    def update(self,data):
        import json,os
        folder=self.directory(data['run_id']);temp=folder/'run.json.tmp'
        write_json(temp,data);os.replace(temp,folder/'run.json')
        with self.db() as db:db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',(data['run_id'],data['created_at'],data['status'],json.dumps(data)))

    def metadata(self,run_id):
        import json
        with self.db() as db:row=db.execute('SELECT metadata FROM runs WHERE id=?',(checked_id(run_id),)).fetchone()
        if not row:raise FileNotFoundError('Run not found')
        return json.loads(row[0])

    def list(self):
        import json
        with self.db() as db:rows=db.execute('SELECT metadata FROM runs ORDER BY created_at DESC, rowid DESC LIMIT 500').fetchall()
        return [json.loads(r[0]) for r in rows]

    def result_path(self,run_id):
        m=self.metadata(run_id)
        if m['status']!='COMPLETED':raise ValueError('Run has no completed result')
        p=self.directory(run_id)/'result.json'
        if file_hash(p)!=m['result_sha256']:raise ValueError('Result integrity mismatch')
        return p

    def result(self,run_id):return read_json(self.result_path(run_id))

    def recover_interrupted(self):
        for data in self.list():
            if data['status'] in ('QUEUED','RUNNING'):
                data.update(status='FAILED',completed_at=now(),progress='Interrupted before completion',error='The prior application process stopped. Partial files are retained; start a new run to recompute.')
                self.update(data)

    def finish(self,data,path,elapsed=None):
        result=read_json(path)
        data.update(status='COMPLETED',completed_at=now(),elapsed_seconds=elapsed,progress='Complete',result_sha256=file_hash(path),result_id=result.get('result_id'),request_sha256=result.get('request_sha256'),stack_sha256=result.get('stack_sha256'),result_status=result['status'],optimizer_version=result.get('optimizer_version'))
        self.update(data)

    def import_demo(self,request,source,identifier):
        data=self.create(request,source='SYNTHETIC_DEMO',demo_id=identifier)
        folder=self.directory(data['run_id']);result=read_json(source)
        # Keep the source JSON and every relative reference byte-for-byte intact.
        manifest=result.get('artifact_manifest')
        if manifest:
            source_manifest=safe_child(source.parent,manifest['path'])
            if file_hash(source_manifest)!=manifest['sha256']:raise ValueError('Demo manifest integrity mismatch')
            assets=source_manifest.parent;target=safe_child(folder,assets.name)
            shutil.copytree(assets,target)
            for ref in read_json(source_manifest)['files']:
                if file_hash(safe_child(folder,ref['path']))!=ref['sha256']:raise ValueError('Demo waveform integrity mismatch')
        shutil.copyfile(source,folder/'result.json')
        data['source_artifact_sha256']=file_hash(source)
        self.finish(data,folder/'result.json')
        return data
