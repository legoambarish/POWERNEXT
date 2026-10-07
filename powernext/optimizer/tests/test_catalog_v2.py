import copy,json
import pytest
from powernext_optimizer.catalog import Catalog,normalize_request
from powernext_optimizer.common import PACKAGE

def request():return json.loads((PACKAGE/'examples/LI_parallel_request.json').read_text())

def test_default_is_single_recipe_only():
    catalog=Catalog()
    assert len(catalog.entries('LI','GSHUNT_v0'))==504
    assert {r['configuration']['recipe_id'] for r in catalog.entries('LI','GSHUNT_v0')}=={'DEV_UNIFORM_SINGLE_v2'}

def test_explicit_parallel_adds_only_84_meaningful_cases():
    c=Catalog();raw=request();req=normalize_request(raw,c);rows=c.entries_for_request(req)
    assert len(rows)==588 and len({x['candidate_id'] for x in rows})==588
    paired=[x for x in rows if x['configuration']['recipe_id']=='HYP_LI_TAIL_180_PAR_520_v1']
    assert len(paired)==84
    assert all(x['tail_recipe']['component_values_ohm']==[180,520] for x in paired)
    assert all(x['tail_recipe']['equivalent_per_stage_ohm']==pytest.approx(180*520/700) for x in paired)

def test_pair_requires_both_components_available():
    c=Catalog();raw=request();raw.update(recipe_ids=['HYP_LI_TAIL_180_PAR_520_v1'],available_tail_per_stage_ohm=[180])
    assert c.entries_for_request(normalize_request(raw,c))==[]
    raw['available_tail_per_stage_ohm']=[180,520];raw['available_front_per_stage_ohm']=[30]
    assert len(c.entries_for_request(normalize_request(raw,c)))==14

@pytest.mark.parametrize('field,value',[('impulse_type','SI'),('topology_id','OSHUNT_v0'),('recipe_ids',['invented']),('recipe_ids',['DEV_UNIFORM_SINGLE_v2','DEV_UNIFORM_SINGLE_v2'])])
def test_recipe_cannot_cross_its_declared_domain(field,value):
    raw=request();raw[field]=value
    with pytest.raises(ValueError) as caught:normalize_request(raw,Catalog())
    assert caught.value.code=='INVALID_RECIPE_SELECTION'

def test_empty_recipe_selection_is_explicitly_empty():
    raw=request();raw['recipe_ids']=[];c=Catalog()
    assert c.entries_for_request(normalize_request(raw,c))==[]

def test_value_availability_is_component_inventory_not_equivalent():
    raw=request();raw['available_tail_per_stage_ohm']=[180*520/700]
    with pytest.raises(ValueError) as caught:normalize_request(raw,Catalog())
    assert caught.value.code=='INVALID_RESISTOR_AVAILABILITY'

def test_catalog_bill_of_materials_accounts_for_overlap():
    c=Catalog();raw=request();raw.update(recipe_ids=['HYP_LI_TAIL_180_PAR_520_v1'],available_front_per_stage_ohm=[180])
    for row in c.entries_for_request(normalize_request(raw,c)):
        n=row['configuration']['stages'];parts={x['component_ohm']:x['required_count'] for x in row['component_bill_of_materials']}
        assert parts=={180:2*n,520:n}

def test_mutated_profile_cannot_keep_a_serving_identity(tmp_path,monkeypatch):
    import shutil
    import powernext_optimizer.prediction as serving
    from powernext_config import PHYSICS
    local=tmp_path/'physics';local.mkdir()
    for name in ['CPRI_EQUIPMENT_PROFILE.json','CIRCUIT_TOPOLOGY_SPEC.md']:
        shutil.copy2(PHYSICS/name,local/name)
    shutil.copytree(PHYSICS/'physics_engine',local/'physics_engine')
    monkeypatch.setattr(serving,'PHYSICS',local)
    stack=serving.PredictionStack()
    with (local/'CPRI_EQUIPMENT_PROFILE.json').open('a') as f:f.write('\n ')
    with pytest.raises(ValueError,match='changed'):
        stack.assert_unchanged()
