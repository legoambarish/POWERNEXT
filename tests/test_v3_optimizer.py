import copy
import json
from pathlib import Path
import unittest
import numpy as np
from powernext_v3 import ROOT
from powernext_v3.catalog import Catalog
from powernext_v3.optimizer import recommend, normalize_request


def request(mode="SI", **updates):
    old=json.loads((ROOT/f"powernext/optimizer/examples/{mode}_request.json").read_text())
    result=dict(domain_id="cpri_0p5uf",impulse_type=mode,topology_id=old["topology_id"],
        setup=old["setup"],target_crest_V=old["target_crest_V"],max_modules=1,
        priority="complete_physics",budget_seconds=90)
    result.update(updates)
    return result


class DeliberatelyWrongModel:
    domain_id="cpri_0p5uf"
    mode="LI"
    topology="GSHUNT_v0"
    def predict(self,x):
        # Every predicted response fails timing; this must not prune Physics.
        return np.tile([.5,10.,200.],(len(x),1))
    def ood(self,x):return np.zeros(len(x),dtype=bool)


class CatalogTests(unittest.TestCase):
    def test_four_module_catalog_count_without_pair_materialization(self):
        c=Catalog(4)
        self.assertEqual(c.width,4080)
        self.assertEqual(len(c.recipes),4192)
        self.assertEqual(c.count,233049600)
        self.assertEqual(c.recipe_count,14*4192**2)
        self.assertEqual(c.decode([0,c.count-1])[0].tolist(),[2,15])

    def test_progressive_coverage_unique_complete_reproducible(self):
        c=Catalog(2,stages=[2,15]);q=request()
        first=list(c.progressive_ids(q["setup"],q["domain_id"],q["impulse_type"]))
        second=list(c.progressive_ids(q["setup"],q["domain_id"],q["impulse_type"]))
        self.assertEqual(first,second)
        self.assertEqual(len(first),c.count)
        self.assertEqual(set(first),set(range(c.count)))

    def test_inventory_unknown_is_not_unlimited_approval(self):
        c=Catalog(1,stages=[2]);entry=c.physical(0)
        self.assertTrue(entry["known_inventory_valid"])
        self.assertTrue(all(r["availability_status"]=="UNKNOWN" for r in entry["bill_of_materials"]))
        short=c.physical(0,{"30":3})
        self.assertFalse(short["known_inventory_valid"])
        self.assertEqual(short["bill_of_materials"][0]["required_count"],4)


class OptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.si,cls.waves=recommend(request())

    def test_complete_physics_matches_legacy_golden(self):
        result=self.si
        self.assertTrue(result["search"]["catalog_complete"])
        self.assertEqual(result["search"]["passing_count"],14)
        self.assertEqual(result["search"]["unsupported_count"],27)
        best=result["best_configuration"]
        self.assertEqual(best["configuration"]["stages"],9)
        self.assertEqual(best["configuration"]["front_per_stage_ohm"],3700)
        self.assertAlmostEqual(best["configuration"]["stage_charge_V"],164366.2942328,places=5)
        self.assertTrue(all(r["compliant"] for r in result["ranked_alternatives"]))
        self.assertTrue(all(not r["compliant"] for r in result["failed_alternatives"]))
        self.assertEqual(len(result["candidates"]),504)

    def test_rare_feasible_survives_wrong_ml_in_small_complete_fallback(self):
        old=json.loads((ROOT/"powernext/optimizer/examples/LI_rare_timing_pass_recommendation.json").read_text())
        q=request("LI",setup=old["request"]["setup"],target_crest_V=1e6,priority="combined")
        result,_=recommend(q,model=DeliberatelyWrongModel())
        self.assertEqual(result["search"]["passing_count"],1)
        self.assertEqual(result["search"]["ml_predicted_count"],504)
        self.assertTrue(result["search"]["catalog_complete"])
        best=result["best_configuration"]
        self.assertEqual(best["configuration"]["stages"],7)
        self.assertEqual(best["configuration"]["front_per_stage_ohm"],30)
        self.assertEqual(best["configuration"]["tail_per_stage_ohm"],180)
        self.assertGreater(best["ml_prediction"]["tail_us"],60)

    def test_four_module_budget_reports_partial_not_no_solution(self):
        result,_=recommend(request("LI",max_modules=4,stages=[2],priority="analytical",max_ml_candidates=64,max_physics_evaluations=5))
        self.assertEqual(result["search"]["distinct_response_candidates"],4080**2)
        self.assertEqual(result["search"]["considered_count"],64)
        self.assertEqual(result["search"]["physics_evaluated_count"],5)
        self.assertFalse(result["search"]["catalog_complete"])
        self.assertIsNone(result["best_configuration"])
        self.assertEqual(result["status"],"NO_COMPLIANT_CONFIGURATION_YET")

    def test_known_inventory_failure_is_never_recommended(self):
        result,_=recommend(request(inventory={},stages=[2]))
        self.assertTrue(result["search"]["catalog_complete"])
        self.assertEqual(result["search"]["physics_evaluated_count"],0)
        self.assertEqual(result["search"]["known_constraint_excluded_count"],36)
        self.assertIsNone(result["best_configuration"])

    def test_research_result_unambiguously_separate(self):
        result,_=recommend(request(domain_id="research_3uf",stages=[2]))
        self.assertEqual(result["profile"]["stage_capacitance_F"],3e-6)
        self.assertTrue(result["profile"]["research_only"])
        self.assertFalse(result["eligible_for_hardware_recommendation"])

    def test_wrong_route_fails_closed(self):
        with self.assertRaises(ValueError):recommend(request(),model=DeliberatelyWrongModel())

    def test_fixed_setup_not_changed_and_invalid_input_rejected(self):
        q=request();before=copy.deepcopy(q)
        normalize_request(q)
        self.assertEqual(q,before)
        for changes in (dict(target_crest_V=400),dict(max_modules=5),dict(max_modules=True),dict(stages=[2,2])):
            with self.assertRaises(ValueError):normalize_request(dict(q,**changes))


if __name__=="__main__":unittest.main()
