"""Meaningful failure checks for leakage, units and artifact provenance."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.contracts import validate_design


class DesignContractTests(unittest.TestCase):
    def setUp(self):
        self.study = json.loads((ROOT / "configs/study_design.json").read_text(encoding="utf-8"))
        self.contracts = json.loads((ROOT / "configs/module_contracts.json").read_text(encoding="utf-8"))
        self.protocol = json.loads((ROOT / "configs/experiment_protocol.json").read_text(encoding="utf-8"))
        self.candidates = json.loads((ROOT / "configs/model_candidates.json").read_text(encoding="utf-8"))

    def check(self):
        return validate_design(self.study, self.contracts, ROOT, check_paths=False,
                               protocol=self.protocol, candidates=self.candidates)

    def test_valid_design_retains_missing_day_and_pending_status(self):
        result = self.check()
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("2026-07-30" in x for x in result.notes))
        self.assertFalse(self.study["ready_for_model_execution"])

    def test_reject_overlapping_holdout(self):
        self.study["splits"][2]["start"] = "2026-05-31"
        self.assertTrue(any("Overlapping" in x for x in self.check().errors))

    def test_reject_terminal_data_in_fit(self):
        self.study["fit_split_ids"].append("terminal_test")
        self.assertFalse(self.check().ok)

    def test_reject_cumulative_flow(self):
        self.study["flow_semantics"] = "daily_cumulative_volume"
        self.study["flow_unit"] = "m3"
        self.assertFalse(self.check().ok)

    def test_reject_output_path_escape(self):
        self.contracts["modules"][0]["outputs"][0]["path"] = "../../raw data/replaced.csv"
        self.assertTrue(any("namespace" in x for x in self.check().errors))

    def test_reject_forward_dependency_and_unproduced_input(self):
        self.contracts["modules"][0]["depends_on"] = ["M12"]
        self.contracts["modules"][0]["inputs"].append("never_produced")
        errors = self.check().errors
        self.assertTrue(any("dependency" in x for x in errors))
        self.assertTrue(any("producer" in x for x in errors))

    def test_reject_duplicate_output_provenance(self):
        first = deepcopy(self.contracts["modules"][0]["outputs"][0])
        self.contracts["modules"][1]["outputs"].append(first)
        self.assertTrue(any("Duplicate output" in x for x in self.check().errors))

    def test_reject_one_minute_without_native_information(self):
        self.study["main_step_minutes"] = 1
        self.study["one_minute_model_admission"]["coarser_loss_status"] = "passed"
        self.assertTrue(any("native information" in x for x in self.check().errors))

    def test_reject_preset_five_minute_priority(self):
        self.study["priority_candidate_step_minutes"] = 5
        self.assertTrue(any("preselect" in x for x in self.check().errors))

    def test_reject_time_weighted_as_equivalent_load_boundary(self):
        self.study["concentration_views"]["sumo_boundary"] = "time_weighted"
        self.assertTrue(any("same flow-weighted view" in x for x in self.check().errors))

    def test_reject_load_identity_on_unmatched_support(self):
        self.study["concentration_views"]["load_identity_requires_common_support"] = False
        self.assertTrue(any("common Q/concentration" in x for x in self.check().errors))

    def test_reject_same_metric_matched_and_manipulated(self):
        self.protocol["experiments"]["E2"]["manipulated_metric_ids"].append("daily_TN_load")
        self.assertTrue(any("both matched and manipulated" in x for x in self.check().errors))

    def test_reject_passed_gate_with_null_unfrozen_tolerance(self):
        self.protocol["experiments"]["E2"]["matching_metrics"][0]["status"] = "passed"
        self.assertTrue(any("unfrozen/null" in x for x in self.check().errors))

    def test_reject_input_pair_selection_using_response(self):
        self.protocol["experiments"]["E2"]["candidate_selection_uses_response_or_field_TN"] = True
        self.assertTrue(any("cannot select candidates" in x for x in self.check().errors))

    def test_reject_synthetic_response_as_field_prediction_truth(self):
        self.protocol["experiments"]["E2"]["synthetic_input_vs_field_kind"] = "prediction_error"
        self.assertTrue(any("not a prediction error" in x for x in self.check().errors))

    def test_reject_different_initial_states_after_separate_warmup(self):
        self.protocol["experiments"]["E2"]["same_process_and_controller_initial_state"] = False
        self.protocol["experiments"]["E2"]["warmup_protocol"] = "separate_inputs_before_comparison"
        self.assertTrue(any("cloned process/controller" in x for x in self.check().errors))

    def test_reject_terminal_ratio_selection(self):
        self.protocol["experiments"]["E3"]["ratio_selection_split"] = "terminal_test"
        self.assertTrue(any("E3 source/ratio" in x for x in self.check().errors))

    def test_reject_mandatory_threshold_research(self):
        self.protocol["evt_tiers"]["threshold_research"]["decision"] = "always_required"
        self.assertTrue(any("EQD research is conditional" in x for x in self.check().errors))

    def test_reject_extended_EVT_in_mainline(self):
        self.protocol["evt_tiers"]["extension"]["enabled_in_mainline"] = True
        self.assertTrue(any("extended EVT" in x for x in self.check().errors))


if __name__ == "__main__":
    unittest.main()
