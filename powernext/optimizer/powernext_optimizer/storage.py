"""Immutable result bundles and a minimal exact-case history index."""
from dataclasses import dataclass
from pathlib import Path
import copy
import json
import sqlite3
import os
import numpy as np
from .common import digest, file_hash, write_json


@dataclass
class RecommendationResult:
    payload: dict
    waveforms: dict

    def save(self, output, history=None):
        output=Path(output)
        assets=output.parent/(output.stem+".assets")
        if output.exists() or assets.exists():
            raise FileExistsError("Recommendation artifacts are immutable; use a new output name")
        output.parent.mkdir(parents=True,exist_ok=True)
        assets.mkdir()
        data=copy.deepcopy(self.payload)
        write_json(assets/"manifest.json",dict(status="IN_PROGRESS"))
        files=[]
        for candidate_id,wave in sorted(self.waveforms.items()):
            path=assets/"waveforms"/(candidate_id+".npz")
            path.parent.mkdir(exist_ok=True)
            np.savez_compressed(path,**{k:np.asarray(v,dtype=np.float64) for k,v in wave.items()})
            reference=dict(path=path.relative_to(output.parent).as_posix(),sha256=file_hash(path),
                           curve_id="raw_clean",array_units={"time_s":"s","voltage_V":"V"})
            files.append(reference)
            for row in data.get("candidates",[])+data.get("ranked_alternatives",[])+[data.get("best_configuration"),data.get("closest_noncompliant")]:
                if row and row["candidate_id"]==candidate_id:
                    row["waveform_reference"]=reference
        write_json(assets/"manifest.json",dict(status="COMPLETE",result_id=data.get("result_id"),files=files,
            semantic_result_sha256=digest(self.payload)))
        data["artifact_manifest"]=dict(path=(assets/"manifest.json").relative_to(output.parent).as_posix(),sha256=file_hash(assets/"manifest.json"))
        # Commit point: a visible JSON result only exists after its assets finish.
        with output.open("x",encoding="utf-8") as stream:
            json.dump(data,stream,indent=2,allow_nan=False)
        if history:
            history.record(output,data)
        return data


class HistoryStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS recommendations (result_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, stack_hash TEXT NOT NULL, output_path TEXT NOT NULL, output_hash TEXT NOT NULL, numerical_pass INTEGER NOT NULL)")

    def record(self,path,result):
        if not result.get("result_id"):
            return
        with sqlite3.connect(self.path) as db:
            # App-owned results move with the database. Preserve explicit external
            # developer paths on a different Windows drive for backward compatibility.
            try:stored_path=os.path.relpath(Path(path).resolve(),self.path.resolve().parent)
            except ValueError:stored_path=str(Path(path).resolve())
            db.execute("INSERT OR IGNORE INTO recommendations VALUES (?,?,?,?,?,?)",(result["result_id"],result["request_sha256"],result["stack_sha256"],stored_path,file_hash(path),int(result["best_configuration"] is not None)))

    def lookup(self,request_hash,stack_hash):
        with sqlite3.connect(self.path) as db:
            records=db.execute("SELECT result_id,output_path,output_hash FROM recommendations WHERE request_hash=? AND stack_hash=? AND numerical_pass=1 ORDER BY result_id",(request_hash,stack_hash)).fetchall()
        valid=[]
        for result_id,path,sha in records:
            p=Path(path)
            if not p.is_absolute():p=self.path.resolve().parent/p
            if not p.exists() or file_hash(p)!=sha:
                continue
            saved=json.loads(p.read_text())
            valid.append(dict(result_id=result_id,candidate_id=saved["best_configuration"]["candidate_id"],
                configuration=saved["best_configuration"]["configuration"],evidence="PREVIOUS_NUMERICAL_PASS_NOT_A_MEASURED_SHOT",
                policy="Candidate is enumerated and evaluated again; history never bypasses checks"))
        return valid
