"""Numerical, gap, atomic-margin and dependence behavior of the limited pilot."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.archive_sensitivity.numerics import (
    EmpiricalMargin, block_slices, copula_logpdf, design_matrix, draw_copula,
    fit_temporal, inverse_transform, lagged_correlation, reconstruct, transform)
from project2_synthesis.archive_sensitivity.runner import ArchiveRun, copy_checkpoint, prepare_support
from project2_synthesis.runtime import sha256


class ReversibleTemporalTests(unittest.TestCase):
    def test_both_transforms_roundtrip(self):
        x = np.array([[0., 1.], [100., 20000.]])
        for kind in ["identity", "log1p"]:
            np.testing.assert_allclose(inverse_transform(transform(x, kind), kind), x, rtol=1e-12, atol=1e-12)
        with self.assertRaises(ValueError):
            transform(np.array([-1.]), "log1p")

    def test_harmonic_units_and_duplicate_rejection(self):
        minute = np.array([0., 360., 720., 1080., 1440.])
        t = np.array([10., 11., 12., 11., 10.])
        x, state = design_matrix(minute, t, [1440, 10080])
        self.assertAlmostEqual(x[1, 3], 1.)
        self.assertAlmostEqual(x[4, 3], 0., places=12)
        again, _ = design_matrix(minute, t, [1440, 10080], state)
        np.testing.assert_array_equal(x, again)
        with self.assertRaises(ValueError):
            design_matrix(minute, t, [1440, 1440])

    def test_inverse_recursion_and_block_initials(self):
        rng = np.random.default_rng(9)
        design = np.ones((100, 1))
        y = rng.normal(size=(100, 2))
        blocks = np.r_[np.zeros(50, int), np.ones(50, int)]
        for order in [0, 1]:
            fit = fit_temporal(y, design, blocks, order)
            np.testing.assert_allclose(reconstruct(fit, blocks), y, atol=1e-12)
            if order:
                self.assertTrue(np.isnan(fit["innovations"][[0, 50]]).all())
                self.assertFalse(fit["eligible"][50])

    def test_AR_fit_excludes_gap_transition(self):
        y = np.array([[1., 1.], [2., 2.], [-1., -1.], [-2., -2.]])
        with self.assertRaisesRegex(ValueError, "Unstable"):
            fit_temporal(y, np.ones((4, 1)), np.array([0, 0, 1, 1]), 1)

    def test_rank_deficiency_and_unsupported_order_rejected(self):
        y = np.arange(10.)[:, None] * np.ones((1, 2))
        with self.assertRaisesRegex(ValueError, "Rank"):
            fit_temporal(y, np.ones((10, 2)), np.zeros(10), 0)
        with self.assertRaises(ValueError):
            fit_temporal(y, np.ones((10, 1)), np.zeros(10), 2)

    def test_lag_correlation_does_not_bridge_gap(self):
        a = np.array([1., 2., 100., 200.])
        b = np.array([2., 4., 200., 400.])
        blocks = np.array([0, 0, 1, 1])
        corr, pairs = lagged_correlation(a, b, blocks, 1)
        self.assertEqual(pairs, 2)
        self.assertAlmostEqual(corr, 1.)
        self.assertEqual(lagged_correlation(a, b, blocks, 2), (None, 0))
        self.assertEqual([(s.start, s.stop) for s in block_slices(blocks)], [(0, 2), (2, 4)])


class MarginCopulaTests(unittest.TestCase):
    def test_atoms_randomized_PIT_and_generalized_inverse(self):
        values = np.array([0., 0., 0., 1., 7., 7.])
        margin = EmpiricalMargin.fit(values)
        u = margin.pit(values, np.random.default_rng(4))
        self.assertTrue(np.all((u > 0) & (u < 1)))
        np.testing.assert_array_equal(margin.ppf(u), values)
        self.assertGreater(np.std(u[:3]), 0)
        np.testing.assert_array_equal(margin.ppf(np.array([0., 1.])), [0., 7.])

    def test_quantile_outside_unit_interval_rejected(self):
        margin = EmpiricalMargin.fit(np.array([1., 2.]))
        for u in [np.array([-0.01]), np.array([1.01]), np.array([np.nan])]:
            with self.assertRaises(ValueError):
                margin.ppf(u)

    def test_gaussian_zero_correlation_is_independent_density(self):
        u = np.array([[.1, .2], [.5, .8], [.9, .7]])
        np.testing.assert_allclose(copula_logpdf(u, "Gaussian", 0.), 0., atol=1e-12)

    def test_student_density_agrees_with_installed_reference(self):
        from statsmodels.distributions.copula.api import StudentTCopula
        u = np.array([[.1, .2], [.5, .8], [.9, .7]])
        expected = StudentTCopula(corr=-.4, df=5).logpdf(u)
        np.testing.assert_allclose(copula_logpdf(u, "Student_t", -.4, 5), expected, atol=1e-12)

    def test_sampling_negative_dependence_reproducible_and_open_unit(self):
        model = {"family": "Gaussian", "rho": -.8, "df": None, "fit_status": "PASS"}
        first, _ = draw_copula(model, 10000, np.random.default_rng(8))
        again, _ = draw_copula(model, 10000, np.random.default_rng(8))
        np.testing.assert_array_equal(first, again)
        self.assertTrue(((first > 0) & (first < 1)).all())
        self.assertLess(stats.kendalltau(first[:, 0], first[:, 1]).statistic, -.5)

    def test_failed_copula_not_sampled(self):
        with self.assertRaises(ValueError):
            draw_copula({"fit_status": "FAIL"}, 10, np.random.default_rng(1))


class ArchiveScopeSupportTests(unittest.TestCase):
    def test_checkpoint_hash_verification_and_config_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "run_manifest/archive_sensitivity/runs/old_fixture"
            records = []
            for stage in ["M02", "M03", "M04", "M05", "M06"]:
                name = f"validation/{stage}.json"
                path = old / "artifacts/archive_sensitivity" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"fixture":true}', encoding="utf-8")
                records.append({"stage": stage, "status": "PASS", "objective": "fixture", "method": "fixture",
                                "metrics": {}, "output_hashes": {name: {"sha256": sha256(path)}},
                                "source_and_config_sha256": {"configs/archive_sensitivity.json": "same"}})
            (old / "manifest.json").write_text(json.dumps({"completed_stages": records}), encoding="utf-8")
            class FixtureRun:
                hashes = {"configs/archive_sensitivity.json": "same"}
                def __init__(self):
                    self.root = root
                def path(self, rel):
                    path = root / "new_outputs" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                def record(self, *args):
                    pass
            fixture = FixtureRun()
            copy_checkpoint(fixture, "old_fixture")
            self.assertTrue((root / "new_outputs/validation/M06.json").exists())
            fixture.hashes = {"configs/archive_sensitivity.json": "changed"}
            with self.assertRaisesRegex(ValueError, "Config changed"):
                copy_checkpoint(fixture, "old_fixture")
            fixture.hashes = {"configs/archive_sensitivity.json": "same"}
            (old / "artifacts/archive_sensitivity/validation/M02.json").write_text('tampered', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "output changed"):
                copy_checkpoint(fixture, "old_fixture")
            with self.assertRaisesRegex(ValueError, "identifier"):
                copy_checkpoint(fixture, "../outside")

    def test_validation_opening_rejected_before_run_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configs").mkdir()
            config = json.loads((ROOT / "configs/archive_sensitivity.json").read_text(encoding="utf-8"))
            config["open_validation"] = True
            (root / "configs/archive_sensitivity.json").write_text(json.dumps(config), encoding="utf-8")
            (root / "configs/study_design.json").write_text('{}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scope violated"):
                ArchiveRun(root)
            self.assertFalse((root / "run_manifest").exists())

    def test_cross_scale_same_minutes_integrals_and_gap_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "artifacts/data/02_model_frame.parquet"
            source.parent.mkdir(parents=True)
            index = pd.date_range("2025-08-01", periods=180, freq="min", tz="Asia/Shanghai")
            frame = pd.DataFrame({"timestamp": index, "Q": np.arange(180.) + 60,
                                  "COD": np.arange(180.) + 10, "T": 20., "split": "development",
                                  "native_refresh_status": "UNKNOWN", "technical_support_Q_COD_T": True})
            frame.loc[70, "technical_support_Q_COD_T"] = False
            frame.to_parquet(source, index=False)
            states = {"M02": {"manifest": {"result": {"status": "PARTIAL"},
                       "outputs": [{"path": "artifacts/data/02_model_frame.parquet", "sha256": sha256(source)}]}}}
            (root / "run_manifest").mkdir()
            (root / "run_manifest/module_states.json").write_text(json.dumps(states), encoding="utf-8")
            class FixtureRun:
                config = {"steps_minutes": [5, 15, 60]}
                numeric_tolerance = 1e-8
                def __init__(self):
                    self.root = root
                def path(self, rel):
                    path = root / "fixture_outputs" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                def annotate(self, frame):
                    return frame
                def record(self, *args, **kwargs):
                    pass
            tables = prepare_support(FixtureRun())
            self.assertEqual([len(tables[s]) for s in [5, 15, 60]], [24, 8, 2])
            self.assertTrue(all(table["block_id"].nunique() == 2 for table in tables.values()))
            np.testing.assert_allclose([table["COD_load_kg"].sum() for table in tables.values()], tables[5]["COD_load_kg"].sum())
            self.assertTrue(all(table["archive_rows"].sum() == 120 for table in tables.values()))


if __name__ == "__main__":
    unittest.main()
