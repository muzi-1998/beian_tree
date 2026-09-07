"""Prediction-only D5: immutable spatial templates, ECDF and support admission.

The reference implementation replays the past hysteresis journal. It never
re-estimates models or support from the supplied observations.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from frozen_context import FrozenContext
from runtime import D5_REFERENCE_END, DIMENSIONS, OUTPUT, PROJECT, content_hash

ROOT = PROJECT / DIMENSIONS["D5"]
sys.path.insert(0, str(ROOT / "src"))
from d5_common.math.calibration import empirical_quality_score
from d5_local.context import GlobalProcessContextBuilder, RegimeHysteresisController
from d5_local.data import SnapshotBuilder
from d5_local.evidence.engine import SpatialEvidenceEngine
from d5_local.pipeline.d5_pipeline import D5Pipeline
from d5_local.templates.builder import SpatialTemplate


class FrozenD5Mapper:
    def __init__(self, asset: dict):
        if pd.Timestamp(asset["fitted_until"]) != D5_REFERENCE_END:
            raise ValueError("Frozen D5 reference boundary mismatch")
        self.gamma = asset["gamma"]
        self.references = asset["references"]
        self.records = pd.DataFrame(asset["records"])

    def records_frame(self):
        return self.records.copy()

    def transform(self, frame):
        out = frame.copy()
        for risk, subscore in [("risk_profile", "Q_profile"), ("risk_gradient", "Q_gradient"),
                               ("risk_rank", "Q_rank"), ("risk_rep", "Q_rep")]:
            out[subscore] = np.nan
            for (analyte, regime, zone), rows in out.groupby(
                    ["analyte", "active_regime_id", "zone_id"], dropna=False):
                candidates = [entry for entry in self.references
                              if entry["risk_metric"] == risk and entry["analyte"] == analyte
                              and (entry["regime_id"] is None or entry["regime_id"] == regime)
                              and (entry["zone_id"] is None or entry["zone_id"] == zone)]
                candidates.sort(key=lambda e: (e["regime_id"] is not None,
                                               e["zone_id"] is not None), reverse=True)
                if candidates:
                    out.loc[rows.index, subscore] = empirical_quality_score(
                        rows[risk].to_numpy(float), candidates[0]["values"], gamma=self.gamma)
        return out


class FrozenD5:
    def __init__(self, *, stable_row_reduction=True):
        self.stable_row_reduction = stable_row_reduction
        self.pipeline = D5Pipeline()
        self.context_asset = json.loads((OUTPUT / "assets/D5_reconstructed_context_candidate.json").read_text())
        self.model = FrozenContext.from_dict(self.context_asset)
        asset = json.loads((OUTPUT / "assets/D5_frozen_inference.json").read_text())
        self.mapper = FrozenD5Mapper(asset)
        self.support = pd.DataFrame(asset["support"])
        templates = [SpatialTemplate(**row) for row in asset["templates"]]
        self.templates = {(t.target_sensor, t.regime_id): t for t in templates}
        self.asset_hash = content_hash(OUTPUT / "assets/D5_frozen_inference.json")

    def predict(self, observations: pd.DataFrame, run_id="HOLDOUT-T0-D5"):
        if observations.empty or not observations.index.is_unique:
            raise ValueError("Unique nonempty raw minute history required")
        if not observations.index.equals(pd.date_range(observations.index[0], observations.index[-1], freq="min")):
            raise ValueError("Explicit regular minute grid with missing values required")
        p = self.pipeline
        floors = p.topology.nodes.loc[p.topology.nodes.floor_flag, "sensor_id"].tolist()
        bundle = SnapshotBuilder(p.windows["snapshot_main_minutes"],
                                 p.windows["snapshot_min_observations"]).build(observations, floors)
        # Never publish an unfinished snapshot merely because it has >=5 values.
        closed = bundle.values.index + pd.Timedelta(minutes=10) <= observations.index[-1] + pd.Timedelta(minutes=1)
        snapshots = bundle.values.loc[closed]
        fraction = bundle.observed_fraction.loc[closed]
        features = GlobalProcessContextBuilder(p.topology).build(snapshots)
        probabilities, distance = self.model.predict(features)
        entropy = -(probabilities * np.log(np.maximum(probabilities, 1e-12))).sum(axis=1) / np.log(probabilities.shape[1])
        controller = RegimeHysteresisController(p.hysteresis_config)
        states = []
        for sensor in p.topology.node_ids():
            state = controller.replay(snapshots.index, probabilities, entropy, distance,
                                      self.model.ood_threshold, sensor, 10)
            state["template_id_used"] = state.active_regime_id.map(lambda r: f"D5-{sensor}-R{int(r)}")
            states.append(state)
        state = pd.concat(states, ignore_index=True)
        evidence = SpatialEvidenceEngine(p.topology, stable_row_reduction=self.stable_row_reduction).score(
            snapshots, state, self.templates)
        context_hash = content_hash(OUTPUT / "assets/D5_reconstructed_context_candidate.json")
        regime_assets = {s: {"model_asset_hash": context_hash} for s in p.topology.node_ids()}
        main, hourly = p._build_main_scores(
            snapshots, fraction, state, regime_assets, self.templates, self.support,
            evidence, D5_REFERENCE_END, run_id, frozen_mapper=self.mapper)
        main["context_observed"] = main.timestamp.map(features.notna().all(axis=1))
        main["current_observed"] = [pd.notna(snapshots.at[t, s])
                                     for t, s in zip(main.timestamp, main.sensor_id)]
        main["D5_for_validation"] = main.D5_report_score.where(
            main.context_observed & main.current_observed)
        main["available_at"] = main.timestamp + pd.Timedelta(minutes=10)
        main["interval_start"] = main.timestamp - pd.Timedelta(hours=23, minutes=50)
        main["interval_end_exclusive"] = main.available_at
        main["frozen_asset_sha256"] = self.asset_hash
        return main, state, hourly
