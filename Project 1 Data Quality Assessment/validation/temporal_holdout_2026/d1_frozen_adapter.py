"""D1 detector continuation with frozen peers, mappings and historical state.

New observations never revise published state-machine history. Detector scales
with an explicitly inherited trailing update rule can advance; no model or
threshold is selected using the new period.
"""
from __future__ import annotations

import json
import pickle
import sys

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance

from runtime import DIMENSIONS, OFFICIAL, OUTPUT, PROJECT, START, sha256
from d1_recovery_adapter import FIELDS, score_recovery
from d1_scheduled_changepoints import scheduled_candidates

ROOT = PROJECT / DIMENSIONS["D1"]
sys.path.insert(0, str(ROOT))
from src.config.loader import load_project_config
from src.detectors import HampelSpikeDetector, CompositeFreezeDetector, AdjacentKSStepDetector
from src.mapping.mapper import apply_mapping, combine_freeze_subscores
from src.baseline.regime_clustering import build_regime_features


def read_state():
    path = OFFICIAL / DIMENSIONS["D1"] / "v11_state.pkl"
    if sha256(path) != "6aaede79b37d64c5af627364cc98b8fa1344b05f1ff37524a68d8732c3889a96":
        raise ValueError("Unverified historical D1 state")
    with path.open("rb") as handle:
        return pickle.load(handle)


def frozen_pls(residual, sensor, asset):
    frame = residual[[sensor, *asset["peers"]]].ffill().fillna(pd.Series(asset["fill_values"])).fillna(0.)
    x = (frame[asset["peers"]].to_numpy(float)-asset["x_mean"]) / asset["x_scale"]
    coefficient = np.asarray(asset["pls_coefficient"]).reshape(-1)
    prediction_s = np.einsum("ij,j->i", x-np.asarray(asset["pls_x_mean"]), coefficient, optimize=False) + asset["pls_intercept"][0]
    prediction = prediction_s * asset["y_scale"][0] + asset["y_mean"][0]
    return pd.Series(np.abs(frame[sensor].to_numpy()-prediction) / asset["sigma_residual"], index=frame.index)


def frozen_regime(series, reference, baseline, neff):
    x, n = series.to_numpy(float), len(series)
    ref = np.asarray(reference)
    w1, ks = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(168, n, 6):
        part = x[i-168:i]
        part = part[np.isfinite(part)]
        if len(part) >= 24:
            w1[i] = wasserstein_distance(part, ref) / baseline * np.sqrt(neff)
    for i in range(336, n, 24):
        a, b = x[i-336:i-168], x[i-168:i]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if min(len(a), len(b)) >= 48:
            ks[i] = ks_2samp(a, b).statistic * np.sqrt(neff)
    w = pd.Series(w1, index=series.index).ffill()
    tier2 = pd.Series(ks, index=series.index).ffill().gt(1.95*np.sqrt(2./168))
    return w * (1.+.5*tier2), w


class FrozenD1:
    def __init__(self):
        self.state = read_state()
        self.cfg = load_project_config(ROOT / "configs")
        self.models = json.loads((OUTPUT / "assets/D1_reconstructed_pls_candidates.json").read_text())["models"]
        self.references = json.loads((OUTPUT / "assets/D1_frozen_detector_references.json").read_text())
        self.recovery = json.loads((OUTPUT / "assets/D1_frozen_recovery_contract.json").read_text())

    def regime_labels(self, raw_hourly):
        asset = json.loads((OUTPUT / "assets/D1_frozen_regime.json").read_text())
        # Historical context values remain exactly those used by the release.
        history = self.state["df_h"]
        appended = raw_hourly.loc[raw_hourly.index > history.index[-1], history.columns]
        source = pd.concat([history, appended])
        features = build_regime_features(source).reindex(columns=asset["feature_names"])
        valid = features.notna().all(axis=1)
        x = (features.loc[valid].to_numpy()-asset["mean"]) / asset["scale"]
        distance = ((x[:, None, :]-np.asarray(asset["centers"])[None, :, :])**2).sum(axis=2)
        labels = pd.Series(np.nan, index=source.index, name="regime_id")
        labels.loc[valid] = distance.argmin(axis=1)
        labels.loc[history.index] = self.state["regime_labels"].reindex(history.index)
        # Missing exogenous evidence selects the frozen missing-context fallback,
        # never a backward-filled future regime.
        return labels

    def predict(self, raw, processed, residual_min, innovation_min, *, continue_state=True, journal_end=None):
        state = self.state
        residual = residual_min[state["scored_channels"]].resample("h").mean()
        innovation = innovation_min[state["scored_channels"]].resample("h").mean()
        complete = residual.index + pd.Timedelta(hours=1) <= residual_min.index[-1] + pd.Timedelta(minutes=1)
        residual, innovation = residual.loc[complete], innovation.loc[complete]
        index = residual.index
        frozen_end = state["resid_h"].index[-1] if journal_end is None else pd.Timestamp(journal_end)
        # Preserve the published transform journal, including its explicitly
        # disclosed historical bridge fills; new hours do not use those fills.
        history_index = state["resid_h"].index.intersection(index)
        residual.loc[history_index] = state["resid_h"].reindex(history_index)[residual.columns]
        routed = pd.DataFrame({s: innovation[s] if state["scoring_mode"][s] == "iid" else residual[s]
                               for s in residual}, index=index)
        routed.loc[history_index] = state["whitened_input_h"].reindex(history_index).reindex(columns=routed.columns)
        outputs, detectors, transitions = [], [], []
        for sensor in state["scored_channels"]:
            neff = float(state["eff_neff"][sensor])
            spike = HampelSpikeDetector(window_min=21, k=3.).score(processed[sensor])
            spike_rate = spike.aux_flag.astype(float).rolling("360min", min_periods=60).mean().resample("h").mean().reindex(index)
            freeze = CompositeFreezeDetector().score(processed[sensor]).metadata["components"].resample("h").max().reindex(index)
            a = AdjacentKSStepDetector(win_h=24, alpha=.001, neff_ratio=neff).score(routed[sensor]).raw_score
            b = AdjacentKSStepDetector(win_h=36, alpha=.001, neff_ratio=neff).score(routed[sensor]).raw_score
            q24, q36 = apply_mapping(a, self.cfg.mapping.step), apply_mapping(b, self.cfg.mapping.step)
            qstep = q24.copy()
            mask = q24.le(2.5)
            qstep.loc[mask] = pd.concat([q24, q36], axis=1).max(axis=1).loc[mask]
            z = frozen_pls(residual, sensor, self.models[sensor])
            ref = self.references[sensor]
            regime, w1 = frozen_regime(routed[sensor], ref["reference"], ref["baseline"], neff)
            qfreeze, mode = combine_freeze_subscores(
                apply_mapping(freeze.rle_run_min, self.cfg.mapping.freeze.rle),
                apply_mapping(freeze.rel_var, self.cfg.mapping.freeze.low_var),
                apply_mapping(freeze.unique_ratio, self.cfg.mapping.freeze.unique),
                self.cfg.mapping.freeze.combined_weights, scoring_mode=state["scoring_mode"][sensor],
                floor_policy=self.cfg.rules.get("freeze_floor_policy"))
            evidence = pd.DataFrame(dict(Q_spike=apply_mapping(spike_rate, self.cfg.mapping.spike),
                Q_step=qstep, Q_regime=apply_mapping(regime, self.cfg.mapping.regime),
                Q_drift=apply_mapping(z, self.cfg.mapping.drift), Q_freeze=qfreeze,
                ks_stat=a, w1_norm=w1, resid_h=residual[sensor], step_confirmed=qstep.le(2.).astype(float),
                peer_residual_z=z), index=index)[FIELDS]
            diagnostic = evidence.copy()
            if continue_state:
                from replay_d1_recovery import evidence_from_state
                old = evidence_from_state(state, sensor).loc[:frozen_end]
                evidence.loc[old.index.intersection(index)] = old.reindex(index).loc[old.index.intersection(index)]
            events = scheduled_candidates(routed[sensor], neff_ratio=neff)
            result, emitted = score_recovery(sensor, evidence, events,
                self.recovery["cooldown_by_sensor"][sensor], self.recovery["aggregation"])
            observed = raw[[sensor, *self.models[sensor]["peers"]]].notna().resample("h").sum().reindex(index)
            result["current_observation_support"] = observed.gt(0).all(axis=1)
            result["D1_for_validation"] = result.D1_for_validation.where(result.current_observation_support)
            result["sensor_id"] = sensor
            result["available_at"] = index + pd.Timedelta(hours=1, minutes=3)
            for column in FIELDS[:5]:
                result[column] = evidence[column]
            result["freeze_mode"] = mode
            outputs.append(result.rename_axis("timestamp").reset_index())
            diagnostic["sensor_id"] = sensor
            detectors.append(diagnostic.rename_axis("timestamp").reset_index())
            transitions.extend(emitted)
            print("Frozen D1 detectors + recovery", sensor, len(index), flush=True)
        return pd.concat(outputs, ignore_index=True), pd.concat(detectors, ignore_index=True), transitions
