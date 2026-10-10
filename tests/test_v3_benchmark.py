import hashlib
import json
import numpy as np
import pytest

from powernext_v3 import benchmark


def _oracles(tmp_path):
    request=benchmark.frozen_requests(cases_per_route=1)[0]
    request["target_crest_V"]=1000000.
    request.update(max_modules=1,stages=[9])
    catalog=benchmark.Catalog(1,[9])
    rows=[]
    # Stored truth order deliberately has the passing candidate first.
    for index in [10]+[i for i in range(catalog.count) if i!=10]:
        passing=index==10
        n,rf,rt=catalog.decode([index])
        rows.append(dict(catalog_index=index,compliant=passing,score={"J":0 if passing else 10},
            configuration=dict(stages=int(n[0]),front_per_stage_ohm=float(rf[0]),tail_per_stage_ohm=float(rt[0]))))
    content=json.dumps(dict(request=request,candidates=rows,search=catalog.info())).encode()
    (tmp_path/"case.json").write_bytes(content)
    requests=json.dumps([request]).encode()
    (tmp_path/"requests.json").write_bytes(requests)
    manifest=dict(purpose="validation",status="COMPLETE",physics=benchmark.source_fingerprint(),execution_contract=benchmark.execution_contract(),
        requests_sha256=hashlib.sha256(requests).hexdigest(),cases=[dict(path="case.json",
            route="cpri_0p5uf:LI:GSHUNT_v0",sha256=hashlib.sha256(content).hexdigest())])
    (tmp_path/"manifest.json").write_text(json.dumps(manifest))


class ConstantModel:
    domain_id="cpri_0p5uf"
    mode="LI"
    topology="GSHUNT_v0"
    def predict(self,x):
        return np.tile([.8,1.2,50.],(len(x),1))


def test_oracle_ml_score_ties_do_not_inherit_physics_answer_order(tmp_path):
    _oracles(tmp_path)
    result=benchmark.OracleValidation(tmp_path)(ConstantModel())
    assert result["cases"][0]["first_feasible_rank"]==11
    assert result["cases"][0]["hit_at_k"]["1"] is False


def test_frozen_oracle_request_tamper_rejected(tmp_path):
    _oracles(tmp_path)
    (tmp_path/"requests.json").write_text("[]")
    with pytest.raises(ValueError,match="requests changed"):
        benchmark.OracleValidation(tmp_path)


def test_oracle_candidate_tamper_rejected(tmp_path):
    _oracles(tmp_path)
    validator=benchmark.OracleValidation(tmp_path)
    (tmp_path/"case.json").write_text("{}")
    with pytest.raises(ValueError,match="Oracle changed"):
        validator(ConstantModel())


def test_final_test_cases_cannot_be_model_selection_oracles(tmp_path):
    _oracles(tmp_path)
    path=tmp_path/"manifest.json"
    manifest=json.loads(path.read_text());manifest["purpose"]="test"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="validation-only"):
        benchmark.OracleValidation(tmp_path)


def test_frozen_validation_and_test_setups_are_distinct():
    validation=benchmark.frozen_requests("validation")
    test=benchmark.frozen_requests("test")
    assert len(validation)==len(test)==16
    assert {q["setup"]["dut_capacitance_F"] for q in validation}.isdisjoint(
        q["setup"]["dut_capacitance_F"] for q in test)


def test_oracle_execution_contract_is_required(tmp_path):
    _oracles(tmp_path)
    path=tmp_path/"manifest.json";manifest=json.loads(path.read_text())
    del manifest["execution_contract"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="execution contract"):
        benchmark.OracleValidation(tmp_path)


def test_attested_case_with_wrong_catalog_configuration_is_rejected(tmp_path):
    _oracles(tmp_path)
    path=tmp_path/"case.json";case=json.loads(path.read_text())
    case["candidates"][0]["configuration"]["front_per_stage_ohm"]+=1
    payload=json.dumps(case).encode();path.write_bytes(payload)
    manifest=json.loads((tmp_path/"manifest.json").read_text())
    manifest["cases"][0]["sha256"]=hashlib.sha256(payload).hexdigest()
    (tmp_path/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="configurations disagree"):
        benchmark.OracleValidation(tmp_path)(ConstantModel())
