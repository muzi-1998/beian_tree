"""Behavior checks for unknown provenance, gaps and common-support arithmetic."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.intake.native_frequency import archive_frequency_diagnostics
from project2_synthesis.intake.source_audit import parse_archive_clock, run_intake, technical_valid
from project2_synthesis.preparation.aggregation import aggregate_common_support
from project2_synthesis.preparation.scale_selection import run_preparation, verify_intake
from project2_synthesis.preparation.splitting import contiguous_blocks, split_ids
from project2_synthesis.runtime import Execution, initialize, publish, sha256


class ArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.date_range("2025-08-01", periods=10, freq="min", tz="Asia/Shanghai")
        self.frame = pd.DataFrame({"Q": [60.] * 5 + [120.] * 5,
                                   "COD": [10., 20., 30., 40., 50.] * 2}, index=self.index)

    def test_constant_flow_means_equal(self):
        views, ledger = aggregate_common_support(self.frame, self.frame["Q"].gt(0), ["COD"], 5, "x")
        np.testing.assert_allclose(views["C_TW"], views["C_FW"])
        np.testing.assert_allclose(ledger["L_kg"], [.15, .30])
        self.assertTrue(ledger["roundtrip_error_scaled"].le(1e-8).all())

    def test_variable_flow_means_differ_and_load_is_preserved(self):
        frame = self.frame.iloc[:2].copy()
        frame["Q"] = [60., 120.]
        frame["COD"] = [10., 40.]
        views, ledger = aggregate_common_support(frame, frame["Q"].gt(0), ["COD"], 5, "x")
        self.assertAlmostEqual(views.loc[0, "C_TW"], 25.)
        self.assertAlmostEqual(views.loc[0, "C_FW"], 30.)
        self.assertAlmostEqual(ledger.loc[0, "V_m3"], 3.)
        self.assertAlmostEqual(ledger.loc[0, "L_kg"], .09)
        self.assertEqual(ledger.loc[0, "missing_exposure_minutes"], 3)

    def test_missing_concentration_restricts_Q_to_same_support(self):
        frame = self.frame.iloc[:2].copy()
        frame["Q"] = [60., 120.]
        frame["COD"] = [10., np.nan]
        views, ledger = aggregate_common_support(frame, frame["COD"].notna(), ["COD"], 5, "x")
        self.assertAlmostEqual(ledger.loc[0, "V_m3"], 1.)
        self.assertAlmostEqual(ledger.loc[0, "L_kg"], .01)
        self.assertEqual(views.loc[0, "valid_archive_rows"], 1)
        self.assertIsNone(views.loc[0, "fresh_count"])

    def test_no_support_is_nan_not_zero_volume_or_load(self):
        valid = pd.Series(False, index=self.index)
        _, ledger = aggregate_common_support(self.frame, valid, ["COD"], 5, "x")
        self.assertTrue(ledger["V_m3"].isna().all())
        self.assertTrue(ledger["L_kg"].isna().all())

    def test_unknown_flags_and_no_model_admission_after_aggregation(self):
        views, _ = aggregate_common_support(self.frame, self.frame["Q"].gt(0), ["COD"], 5, "x")
        self.assertTrue(views["measurement_support_status"].eq("UNKNOWN").all())
        self.assertFalse(views["model_admitted"].any())

    def test_daily_integral_not_extrapolated_across_gap(self):
        valid = self.frame["Q"].gt(0)
        valid.iloc[2] = False
        _, fine = aggregate_common_support(self.frame, valid, ["COD"], 5, "x")
        _, daily = aggregate_common_support(self.frame, valid, ["COD"], 1440, "x")
        self.assertAlmostEqual(fine["L_kg"].sum(), daily.loc[0, "L_kg"])
        self.assertEqual(daily.loc[0, "valid_archive_rows"], 9)
        self.assertEqual(daily.loc[0, "missing_exposure_minutes"], 1431)

    def test_reject_duplicated_or_wrong_common_support(self):
        duplicate = pd.concat([self.frame.iloc[:1], self.frame.iloc[:1]])
        with self.assertRaises(ValueError):
            aggregate_common_support(duplicate, duplicate["Q"].gt(0), ["COD"], 5, "x")
        with self.assertRaises(ValueError):
            aggregate_common_support(self.frame, self.frame["Q"].gt(0).iloc[1:], ["COD"], 5, "x")


class ProvenanceTests(unittest.TestCase):
    def test_constant_values_do_not_identify_fresh_or_held(self):
        index = pd.date_range("2025-08-01", periods=100, freq="min", tz="Asia/Shanghai")
        values = pd.Series(7., index=index)
        info = archive_frequency_diagnostics(values, values.notna())
        self.assertEqual(info["unchanged_adjacent_fraction"], 1.)
        self.assertEqual(info["native_status"], "UNKNOWN")
        self.assertIsNone(info["native_interval_minutes"])
        self.assertIsNone(info["fresh_count"])

    def test_clock_gap_breaks_constant_run_and_blocks(self):
        index = pd.DatetimeIndex(["2025-08-01 00:00", "2025-08-01 00:01", "2025-08-01 00:05"], tz="Asia/Shanghai")
        values = pd.Series(7., index=index)
        info = archive_frequency_diagnostics(values, values.notna())
        self.assertEqual(info["constant_run_max_archive_rows"], 2)
        ids, blocks = contiguous_blocks(index, np.ones(3, dtype=bool), "x")
        self.assertEqual(len(blocks), 2)
        self.assertNotEqual(ids[1], ids[2])

    def test_invalid_minute_breaks_block(self):
        index = pd.date_range("2025-08-01", periods=5, freq="min", tz="Asia/Shanghai")
        ids, blocks = contiguous_blocks(index, np.array([True, True, False, True, True]), "x")
        self.assertEqual([x["archive_rows"] for x in blocks], [2, 2])
        self.assertIsNone(ids[2])

    def test_parse_mixed_clock_but_reject_duplicates_and_disorder(self):
        clock = parse_archive_clock(pd.Series(["2025/8/1 0:00", "2025-08-01 00:01:00"]), "Asia/Shanghai")
        self.assertEqual(str(clock.tz), "Asia/Shanghai")
        for rows in [["2025-08-01", "2025-08-01"], ["2025-08-02", "2025-08-01"]]:
            with self.assertRaises(ValueError):
                parse_archive_clock(pd.Series(rows), "Asia/Shanghai")

    def test_calendar_split_boundaries(self):
        study = json.loads((ROOT / "configs/study_design.json").read_text(encoding="utf-8"))
        index = pd.DatetimeIndex(["2026-04-30 23:59", "2026-05-01", "2026-06-01"], tz="Asia/Shanghai")
        self.assertEqual(list(split_ids(index, study)), ["development", "validation", "terminal_test"])

    def test_only_minimal_technical_rules_no_temperature_clipping(self):
        values = pd.Series([-2., 0., 1., np.inf, np.nan])
        self.assertEqual(list(technical_valid(values, "Q")), [False, False, True, False, False])
        self.assertEqual(list(technical_valid(values, "TN")), [False, True, True, False, False])
        self.assertEqual(list(technical_valid(values, "T")), [True, True, True, False, False])


class PipelineFixtureTests(unittest.TestCase):
    def test_initialize_captures_exact_configuration_and_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configs").mkdir()
            (root / "src").mkdir()
            (root / "configs/study_design.json").write_text('{}', encoding="utf-8")
            (root / "configs/module_contracts.json").write_text('{}', encoding="utf-8")
            source = root / "src/fixture.py"
            source.write_text('VALUE = 3\n', encoding="utf-8")
            ctx = initialize(root, "M01")
            saved = ctx.run_dir / "source_snapshot/src/fixture.py"
            source.write_text('VALUE = 4\n', encoding="utf-8")
            self.assertEqual(saved.read_text(encoding="utf-8"), 'VALUE = 3\n')
            self.assertEqual(sha256(ctx.run_dir / "source_snapshot/configs/study_design.json"), ctx.config_hashes["configs/study_design.json"])

    def test_end_to_end_raw_preservation_reports_and_no_step_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            study = deepcopy(json.loads((ROOT / "configs/study_design.json").read_text(encoding="utf-8")))
            contracts = deepcopy(json.loads((ROOT / "configs/module_contracts.json").read_text(encoding="utf-8")))
            contracts["external_inputs"]["raw_data"]["path"] = "raw"
            mappings = study["variable_mapping"]
            dates = pd.date_range("2025-08-01", periods=12, freq="min")
            quality = pd.DataFrame({"日期": dates.astype(str)})
            for name, mapping in mappings.items():
                if name != "Q":
                    quality[mapping["column"]] = "10.00"
            quality.loc[2, mappings["COD"]["column"]] = "not_numeric"
            quality["出水总氮（mg/L）"] = "3.00"
            quality["出水氨氮（mg/L）"] = "1.00"
            quality_path = raw / mappings["COD"]["file"]
            quality.to_csv(quality_path, index=False, encoding="utf-8-sig")
            flow_path = raw / mappings["Q"]["file"]
            pd.DataFrame({"日期": dates.astype(str), mappings["Q"]["column"]: "60.0"}).to_csv(flow_path, index=False, encoding="utf-8-sig")
            hashes = {p.name: sha256(p) for p in raw.iterdir()}
            config_hashes = {"configs/study_design.json": "fixture-study", "configs/experiment_protocol.json": "fixture-protocol"}
            run_dir = root / "run_manifest/runs/fixture_M01"
            run_dir.mkdir(parents=True)
            plan = root / "plan and report/04_第二章大纲与2.3研究方案_v3_20261020.md"
            plan.parent.mkdir()
            plan.write_text("fixture plan", encoding="utf-8")
            ctx = Execution(root, "fixture_M01", run_dir, study, contracts, config_hashes)
            result = run_intake(ctx)
            self.assertEqual(result["status"], "PARTIAL")
            flags = pq.read_table(ctx.output_dir / "data/01_observation_flags.parquet").to_pandas()
            self.assertEqual(len(flags), 12 * 7)
            self.assertTrue(flags[["observed", "held", "imputed", "available_at"]].isna().all().all())
            cod = flags[flags["variable"] == "COD"]
            self.assertEqual(cod.iloc[0]["raw_value"], "10.00")
            self.assertEqual(cod.iloc[2]["raw_value"], "not_numeric")
            self.assertFalse(cod.iloc[2]["technical_valid"])
            self.assertEqual({p.name: sha256(p) for p in raw.iterdir()}, hashes)
            tests = {"status": "PASS", "log": "fixture_tests.log"}
            publish(ctx, "M01", result, tests)
            with self.assertRaisesRegex(ValueError, "immutable run"):
                publish(ctx, "M01", result, tests)
            self.assertTrue((root / "reports/M12_执行报告.md").exists())
            self.assertIn("PENDING", (root / "reports/M12_执行报告.md").read_text(encoding="utf-8"))
            for i in range(1, 9):
                self.assertIn(f"## {i}.", (root / "reports/M01_执行报告.md").read_text(encoding="utf-8"))
            prep_dir = root / "run_manifest/runs/fixture_M02"
            prep_dir.mkdir()
            prep = Execution(root, "fixture_M02", prep_dir, study, contracts, config_hashes)
            result2 = run_preparation(prep)
            self.assertEqual(result2["status"], "PARTIAL")
            decision = json.loads((prep.output_dir / "validation/02_scale_decision.json").read_text(encoding="utf-8"))
            self.assertIsNone(decision["main_step_minutes"])
            self.assertFalse(decision["one_minute_admitted"])
            self.assertEqual(decision["numerical_identity"]["status"], "PASS")
            path = root / "artifacts/data/01_input_audit.json"
            path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_intake(prep)


if __name__ == "__main__":
    unittest.main()
