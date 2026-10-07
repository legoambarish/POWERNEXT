import copy
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from powernext_ml.common import PACKAGE,PHYSICS,digest,file_hash
from powernext_ml.physics_adapter import ProvisionalAdapter
from powernext_ml.features import SIM_DIRECT,SIM_GUIDED,LEGACY_DIRECT
from powernext_ml.splits import connected_groups,make_splits
from powernext_ml.training import load_frame
from powernext_ml.registry import load_model
from powernext_ml.inference import predict
from powernext_ml.legacy import exact_predict,score
from powernext_ml.measured import ingest_measurement,adaptation_readiness
from physics_engine.network import PhysicsError


@pytest.fixture
def case_request():
    return dict(configuration=dict(impulse_type="SI",stages=10,stage_charge_V=150000.,front_per_stage_ohm=3700,tail_per_stage_ohm=5000,topology_id="GSHUNT_v0",recipe_id="DEV_UNIFORM_SINGLE_v2",polarity=1),
                setup=dict(dut_capacitance_F=850e-12,divider_capacitance_F=500e-12,stray_capacitance_F=150e-12,loop_inductance_H=18.5e-6,basic_coverage_assumption="ADDITIONAL_DISJOINT",setup_id="TEST"),target_crest_V=1300000.)


def test_workbook_exact_reproduction():
    a=json.loads((PACKAGE/"evidence/legacy/exact_baseline_results.json").read_text())
    assert a["max_pooled_difference"]<1e-12
    assert a["helper_training_match"] and not a["helper_formula_mismatches"]
    assert max(a["helper_cached_max_errors"].values())<1e-12
    assert all((value is True) if isinstance(value,bool) else value<1e-9 for value in a["calculator_errors"].values())


def test_no_outcome_features():
    for columns in [SIM_DIRECT,SIM_GUIDED,LEGACY_DIRECT]:
        assert not any(x.startswith(("Observed","Residual")) or x in ["Test_kV","target_crest_V","ID","setup_id","compliance_status"] for x in columns)


def test_gain_features_invariant_to_requested_crest_and_charge(case_request):
    a=ProvisionalAdapter();r=copy.deepcopy(case_request)
    f=a.features(r["configuration"],r["setup"])
    r["configuration"]["stage_charge_V"]=75000.;r["configuration"]["polarity"]=-1;r["target_crest_V"]=900000.
    assert f==a.features(r["configuration"],r["setup"])
    assert a.shape_identity(case_request["configuration"],case_request["setup"])==a.shape_identity(r["configuration"],r["setup"])


def test_equivalent_capacitance_partitions_group_together(case_request):
    a=ProvisionalAdapter();s=copy.deepcopy(case_request["setup"])
    s["dut_capacitance_F"]+=100e-12;s["divider_capacitance_F"]-=100e-12
    assert a.shape_identity(case_request["configuration"],s)==a.shape_identity(case_request["configuration"],case_request["setup"])


@pytest.mark.parametrize("field,value,code",[("stages",1,"STAGE_COUNT_LIMIT"),("stages",16,"STAGE_COUNT_LIMIT"),("stage_charge_V",201000,"STAGE_VOLTAGE_LIMIT"),("front_per_stage_ohm",50,"COMPONENT_NOT_CONFIRMED"),("tail_per_stage_ohm",521,"COMPONENT_NOT_CONFIRMED"),("topology_id","CPRI_VERIFIED","UNKNOWN_TOPOLOGY_OR_RECIPE")])
def test_hardware_rules_before_ml(case_request,field,value,code):
    case_request["configuration"][field]=value
    with pytest.raises(PhysicsError,match=code):ProvisionalAdapter().validate(case_request["configuration"],case_request["setup"])


def test_union_group_transitivity():
    df=pd.DataFrame(dict(row_id=["a","b","c","d"],shape=["1","1","2","3"],setup=["x","y","y","z"]))
    g=connected_groups(df,["shape","setup"])
    assert g[0]==g[1]==g[2] and g[2]!=g[3]


def test_all_new_splits_are_disjoint():
    for domain,path in [("legacy",PACKAGE/"evidence/legacy/legacy.csv"),("simulation",PACKAGE/"data/clarification_v2")]:
        frame,_=load_frame(domain,path)
        for _,part in frame.groupby(["mode","topology_version"]):
            for name,labels in make_splits(part,domain).items():
                if name=="provided":continue
                assert pd.DataFrame(dict(g=part.group_id.to_numpy(),s=labels)).groupby("g").s.nunique().max()==1


def test_null_targets_for_every_unevaluable_case():
    rows=[json.loads(l) for l in (PACKAGE/"data/clarification_v2/rows.jsonl").read_text().splitlines()]
    assert len(rows)==18339
    for r in rows:
        assert r["topology_status"]=="PROVISIONAL_TOPOLOGY" and not r["hardware_verified"]
        if not r["regression_eligible"]:
            assert all(r[x] is None for x in ["gain","front_us","tail_us","crest_V","T1_s","Tp_s","T2_s"])


def test_registry_roundtrip_and_provenance_rejection():
    ids=json.loads((PACKAGE/"results/simulation_v2/selected_models.json").read_text())
    frame,provenance=load_frame("simulation",PACKAGE/"data/clarification_v2")
    for key,model_id in ids.items():
        model,card=load_model(PACKAGE/"registry/simulation_v2"/model_id,provenance)
        part=frame[(frame["mode"]==card["mode"])&(frame.topology_version==card["topology_version"])]
        test=part[part.row_id.isin(card["selection"]["test_rows"])]
        from powernext_ml.evaluation import metrics
        from powernext_ml.features import labels
        result=metrics(test,labels(test,"simulation"),model.predict(test),"simulation",card["mode"])
        assert result["selection_score"]==pytest.approx(card["test_metrics"]["selection_score"],rel=1e-12)
        altered=dict(provenance,simulator_version="changed")
        with pytest.raises(ValueError,match="provenance"):load_model(PACKAGE/"registry/simulation_v2"/model_id,altered)


def test_inference_real_ml_and_curve_separation(case_request):
    out=predict(case_request,PACKAGE/"registry/simulation_v2",PACKAGE/"results/simulation_v2/selected_models.json")
    assert out["status"]=="ML_WITH_PHYSICS_VERIFICATION"
    assert out["ml_prediction"] and out["model_id"]
    assert out["physics_reference"]["metrics"]["evaluation_curve_id"]=="raw_clean"
    assert out["eligible_for_hardware_recommendation"] is False
    assert out["standards_certified"] is False
    assert out["ml_prediction"]["T1_s"] is None


def test_inference_ood_fallback(case_request):
    case_request["setup"]["dut_capacitance_F"]=50e-9
    out=predict(case_request,PACKAGE/"registry/simulation_v2",PACKAGE/"results/simulation_v2/selected_models.json")
    assert out["status"]=="PHYSICS_FALLBACK"
    assert "OUTSIDE_TRAINING_SUPPORT" in out["reason_codes"]
    assert out["ml_prediction"] is None


def test_missing_model_fallback(case_request,tmp_path):
    out=predict(case_request,tmp_path)
    assert out["status"]=="PHYSICS_FALLBACK" and out["physics_reference"]


def test_raw_measured_data_not_auto_qualified(case_request,tmp_path):
    # Mathematical unit-test fixture only. Never saved to the measured corpus.
    from physics_engine.analytic import double_exponential_metrics
    t=np.linspace(0,.02,5000);v=np.exp(-300*t)-np.exp(-16000*t)
    raw=tmp_path/"raw.csv";pd.DataFrame(dict(t=t*1e6,v=v)).to_csv(raw,index=False)
    m=dict(shot_id="UNIT_TEST_ONLY",setup_id="UNIT_TEST_ONLY",shot_series_id="UNIT_TEST_ONLY",acquisition_time_utc="2026-10-02T00:00:00Z",source_organization="CPRI",
           configuration=case_request["configuration"],setup=case_request["setup"],provenance=dict(evidence_kind="ACTUAL_LABORATORY_EXPORT",source_reference="UNIT_TEST_FIXTURE_NOT_CPRI_DATA"),
           measurement=dict(time_column="t",voltage_column="v",time_unit="us",voltage_unit="V",voltage_scale_to_DUT=1.,divider_id="TEST",digitizer_id="TEST",channel_id="1",measurement_plane="DUT",baseline_V=0.,beginning_s=0.,polarity=1,calibration_reference="TEST"))
    meta=tmp_path/"meta.json";meta.write_text(json.dumps(m))
    imported=ingest_measurement(raw,meta,tmp_path/"archive")
    assert imported["local_evaluation"]["compliance_status"]=="INDETERMINATE"
    assert not imported["regression_eligible"]
    assert file_hash(raw)==file_hash(tmp_path/"archive/raw_export.csv")
    assert not adaptation_readiness([imported])["ready"]


def test_no_real_data_readiness():
    assert "NO_REAL_DATA" in adaptation_readiness([])["reason_codes"]
    with pytest.raises(ValueError,match="mix"):adaptation_readiness([dict(evidence_domain="PROVISIONAL_TOPOLOGY_SYNTHETIC")])


def test_no_fabricated_failure_rate_denominator():
    from powernext_ml.evaluation import confusion
    m=confusion(np.array([True,True]),np.array([True,False]))
    assert m["false_accept_rate"] is None and m["false_reject_rate"]==.5


def test_future_adapter_recipe_enumeration(case_request):
    from powernext_ml.generate import design
    class Adapter:
        def design_requests(self, samples_per_stratum, seed):
            return [dict(case_request, setup_family_id="FUTURE_CONTRACT_FIXTURE", case_kind="unit_test")]
    requests=design(Adapter(), samples_per_stratum=1, seed=12)
    assert len(requests)==1 and requests[0]["row_id"]=="case_000000"
    class InvalidAdapter:
        def design_requests(self, **kwargs):
            return [dict(configuration={})]
    with pytest.raises(ValueError, match="envelope"):
        design(InvalidAdapter())


def test_predict_cli_uses_explicit_selection(tmp_path):
    import subprocess
    output=tmp_path/"prediction.json"
    result=subprocess.run([sys.executable,"-m","powernext_ml","predict","--registry",str(PACKAGE/"registry/simulation_v2"),
        "--selection",str(PACKAGE/"results/simulation_v2/selected_models.json"),
        "--request",str(PACKAGE/"examples/SI_request.json"),"--output",str(output)],cwd=PACKAGE,capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    prediction=json.loads(output.read_text())
    assert prediction["status"]=="ML_WITH_PHYSICS_VERIFICATION" and prediction["model_id"]
