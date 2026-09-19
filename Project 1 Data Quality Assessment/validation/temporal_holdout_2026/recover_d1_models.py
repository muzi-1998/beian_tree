"""Recover D1 PLS and regime assets on old data; check archived detector outputs."""
from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd

from runtime import DIMENSIONS, OFFICIAL, OUTPUT, PROJECT, START, sha256, write_json

D1 = PROJECT / DIMENSIONS["D1"]
sys.path.insert(0, str(D1))
from src.baseline.regime_clustering import build_regime_features
from src.detectors.drift_pls import PLSVirtualSensorDetector


def main() -> None:
    source = OFFICIAL / DIMENSIONS["D1"] / "v11_state.pkl"
    if sha256(source) != "6aaede79b37d64c5af627364cc98b8fa1344b05f1ff37524a68d8732c3889a96":
        raise ValueError("D1 state does not match the published release state hash")
    with source.open("rb") as handle:
        state = pickle.load(handle)
    residual = state["resid_h"]
    if residual.index.max() >= START:
        raise ValueError("PLS reconstruction includes held-out time")
    peer_audit = state["detectors_raw"]["pls_peer_selection_audit"]
    assets, rows = {}, []
    for sensor in state["scored_channels"]:
        record = peer_audit.loc[sensor]
        peers = record.selected_peers
        if isinstance(peers, str):
            peers = peers.split(";")
        model = PLSVirtualSensorDetector(n_components=int(record.selected_n_components), train_days=21)
        model.fit(residual.iloc[:504], sensor, list(peers))
        prediction = model.score(residual, sensor, list(peers)).raw_score
        old = state["detectors_raw"]["pls_residual_z_hourly"][sensor].reindex(prediction.index)
        difference = (prediction - old).abs()
        pls, sx, sy, scale, medians, selected, components = model._models[sensor]
        assets[sensor] = {
            "peers": selected, "n_components": components,
            "x_mean": sx.mean_.tolist(), "x_scale": sx.scale_.tolist(),
            "y_mean": sy.mean_.tolist(), "y_scale": sy.scale_.tolist(),
            "pls_x_mean": pls._x_mean.tolist(), "pls_y_mean": pls._y_mean.tolist(),
            "pls_coefficient": pls.coef_.tolist(), "pls_intercept": pls.intercept_.tolist(),
            "sigma_residual": scale, "fill_values": medians.to_dict(),
            "fit_end": str(residual.index[503]), "training_rows": 504,
            "prediction_missing_policy": "legacy_ffill_then_training_median; observational_eligibility_separate",
        }
        rows.append({"sensor_id": sensor, "peers": ",".join(selected),
                     "n_components": components, "n_hours": len(prediction),
                     "max_abs_residual_z_difference": float(difference.max()),
                     "na_mismatches": int((prediction.isna() != old.isna()).sum()),
                     "n_mismatches_1e_8": int((difference > 1e-8).sum())})
    info = state["regime_info"]
    features = build_regime_features(state["df_h"], window_h=24)
    valid = features.dropna()
    labels = info["kmeans"].predict(info["scaler"].transform(valid.to_numpy()))
    label_mismatch = int((labels != state["regime_labels"].reindex(valid.index).to_numpy()).sum())
    write_json(OUTPUT / "assets/D1_reconstructed_pls_candidates.json", {
        "source_state_sha256": sha256(source), "models": assets,
        "reconstruction_only_old_data": True,
    })
    write_json(OUTPUT / "assets/D1_frozen_regime.json", {
        "source_state_sha256": sha256(source), "feature_names": info["feature_names"],
        "mean": info["scaler"].mean_.tolist(), "scale": info["scaler"].scale_.tolist(),
        "centers": info["kmeans"].cluster_centers_.tolist(),
        "fit_end": str(features.index.max()), "post_fit_inference": "predict_only",
        "initial_invalid_feature_rows": int(features.isna().any(axis=1).sum()),
        "new_initialization_backfill": "prohibited; inherit_verified_last_historical_state",
    })
    table = pd.DataFrame(rows)
    (OUTPUT / "audit").mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT / "audit/D1_pls_historical_replay.csv", index=False)
    write_json(OUTPUT / "audit/D1_model_recovery_qa.json", {
        "source_state_hash_verified": True, "regime_evaluable_hours": len(valid),
        "regime_label_mismatches": label_mismatch,
        "pls_all_equal_1e_8": bool(table.n_mismatches_1e_8.sum() == 0 and table.na_mismatches.sum() == 0),
        "scope": "PLS_detector_and_context_only_not_end_to_end_D1",
        "heldout_scores_computed": False,
    })
    print(table.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
