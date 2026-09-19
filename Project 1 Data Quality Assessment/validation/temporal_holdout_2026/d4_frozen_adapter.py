"""Residual minutes -> common-support risks -> frozen public mappings.

D1 supplies only the frozen process-regime label, not a numeric score fuse.
D2 is an evaluability gate. CP candidates use a strictly as-of evidence clock.
"""
from __future__ import annotations

import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

from causal_change_points import causal_change_timeline
from runtime import DIMENSIONS, OUTPUT, PROJECT, content_hash

ROOT = PROJECT / DIMENSIONS["D4"]
sys.path.insert(0, str(ROOT / "src"))
from d4.config import load_config
from d4.scoring import compute_window_metrics, compare_change_points, score_from_quantiles, aggregate_scores


class FrozenD4:
    def __init__(self):
        self.cfg = load_config(ROOT / "configs/d4.yaml", PROJECT)
        self.mapping_path = OUTPUT / "assets/D4_frozen_production_mapping.csv"
        self.mapping = pd.read_csv(self.mapping_path)
        if self.mapping.duplicated(["variable", "regime_id", "subscore"]).any():
            raise ValueError("Ambiguous frozen D4 map")

    def risks(self, minute_residuals, *, last_closed_hour=None):
        cfg = self.cfg
        interval = cfg.analysis_interval_minutes
        residuals = minute_residuals.resample(f"{interval}min").median()
        if last_closed_hour is not None:
            residuals = residuals.loc[residuals.index < last_closed_hour + pd.Timedelta(hours=1)]
        width = cfg.window_hours * 60 // interval
        ends = np.arange(width, len(residuals) + 1, cfg.step_hours * 60 // interval)
        labels = pd.DatetimeIndex([residuals.index[e - 1].floor("h") for e in ends])
        scan = {k: cfg.change_point[k] for k in ["auxiliary_window_days", "adjacent_segment_hours",
                "candidate_step_hours", "ks_stat_min", "pvalue_max"]}
        scan["min_valid_fraction"] = cfg.min_valid_fraction
        rows = []
        for pair in cfg.pairs:
            a = residuals[pair.target].to_numpy(float)
            b = residuals[pair.reference].to_numpy(float)
            # The residual-hour values are complete at the next hour; external
            # short-gap latency is added only after this source clock closes.
            t = causal_change_timeline(residuals[pair.target].resample("h").median(), labels + pd.Timedelta(hours=1), **scan)
            r = causal_change_timeline(residuals[pair.reference].resample("h").median(), labels + pd.Timedelta(hours=1), **scan)
            cp = compare_change_points(t, r).reset_index(drop=True)
            for i, end in enumerate(ends):
                values = asdict(compute_window_metrics(
                    a[end-width:end], b[end-width:end], deadband=cfg.deadband[pair.variable],
                    points_per_hour=60 // interval,
                    min_common_hour_fraction=float(cfg.common_support["min_hour_fraction"]),
                    distribution_weights=cfg.distribution["weights"]))
                values.pop("q_cp_rule")
                values.update(cp.iloc[i].to_dict())
                values.update(timestamp=labels[i], pair_id=pair.pair_id, sensor_id=pair.target,
                              pair_sensor_id=pair.reference, variable=pair.variable, zone=pair.zone)
                rows.append(values)
            print("Frozen D4 risks", pair.pair_id, len(ends), flush=True)
        return pd.DataFrame(rows)

    def score(self, risks, regime, d2):
        out = risks.copy()
        out["regime_id"] = out.timestamp.map(regime)
        for q in ["Q_dist", "Q_trend", "Q_var"]:
            out[q] = np.nan
            for row in self.mapping.loc[self.mapping.subscore.eq(q)].to_dict("records"):
                rm = out.regime_id.eq(row["regime_id"]) if pd.notna(row["regime_id"]) else out.regime_id.isna()
                mask = out.variable.eq(row["variable"]) & rm
                out.loc[mask, q] = score_from_quantiles(out.loc[mask, row["risk_metric"]].to_numpy(float),
                    np.array([row[k] for k in ["q50", "q75", "q90", "q97_5"]]))
                for source, dest in [("mapping_scope", "calibration_scope"),
                                      ("calibration_quality", "calibration_quality"),
                                      ("mapping_evidence_quality", "calibration_evidence_quality"),
                                      ("independent_blocks", f"{q}_calibration_independent_blocks"),
                                      ("percentile_precision_grade", f"{q}_tail_precision_grade")]:
                    out.loc[mask, dest] = row[source]
        out.loc[out.deadband_active.astype(bool), "Q_var"] = 5.
        out["D4_base"], out["D4_raw"] = aggregate_scores(
            *[out[c].to_numpy(float) for c in ["Q_dist", "Q_trend", "Q_var", "Q_cp"]],
            weights=self.cfg.weights, lambda_blend=self.cfg.lambda_blend)
        lookup = d2.set_index(["timestamp", "sensor_id"])
        if not lookup.index.is_unique:
            raise ValueError("D2 must be unique per hour/sensor")
        for role, column in [("target", "sensor_id"), ("reference", "pair_sensor_id")]:
            aligned = lookup.reindex(pd.MultiIndex.from_arrays([out.timestamp, out[column]]))
            out[f"D2_{role}_veto"] = aligned.veto_flag.to_numpy()
        data_ok = out.valid_fraction_common.ge(self.cfg.common_support["min_fraction"]) & out.valid_fraction_common_hours.ge(
            self.cfg.common_support["trend_min_common_hour_fraction"])
        out["usable_for_D4"] = data_ok & out.D2_target_veto.eq(0) & out.D2_reference_veto.eq(0) & out.D4_raw.notna()
        out["D4_for_validation"] = out.D4_raw.where(out.usable_for_D4)
        out["calibration_independent_blocks"] = out[[f"{q}_calibration_independent_blocks"
            for q in ["Q_dist", "Q_trend", "Q_var"]]].min(axis=1)
        out["calibration_tail_precision_grade"] = out[[f"{q}_tail_precision_grade"
            for q in ["Q_dist", "Q_trend", "Q_var"]]].apply(
                lambda row: "|".join(sorted(set(row.dropna().astype(str)))), axis=1)
        out["available_at"] = out.timestamp + pd.Timedelta(hours=1, minutes=3)
        out["interval_start"] = out.timestamp - pd.Timedelta(hours=23)
        out["interval_end_exclusive"] = out.timestamp + pd.Timedelta(hours=1)
        out["mapping_sha256"] = content_hash(self.mapping_path)
        out["D1_numeric_score_consumed"] = False
        out["run_id"] = "HOLDOUT-T0-D4-CAUSAL"
        return out
