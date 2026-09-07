"""Recover only historically selected minute whitening routes and coefficients."""
from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from runtime import LEGACY, OFFICIAL, OUTPUT, PROJECT, START, sha256, write_json

DECOMP = PROJECT / "1.1 Decomposition"
sys.path.insert(0, str(DECOMP))
from src.config.loader import load_configs
from src.whiten import model_selection as ms, online_whitener as ow, diagnostics as dg


def main() -> None:
    config = load_configs(DECOMP / "configs")["whiten"]
    path = LEGACY / "1.1 Decomposition/outputs/_pipeline_state.pkl"
    with path.open("rb") as handle:
        old = pickle.load(handle)
    residuals = pd.DataFrame(old["resid_min"])
    target = pd.DataFrame(old["std_min"])
    official_residual = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/residual_min.parquet")
    official_innovation = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/innovation_min.parquet")
    pd.testing.assert_frame_equal(residuals, official_residual, check_freq=False, check_names=False)
    pd.testing.assert_frame_equal(target, official_innovation, check_freq=False, check_names=False)
    if residuals.index.max() >= START:
        raise ValueError("Whitening reconstruction crossed the holdout cutoff")
    raw = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min.parquet")
    orders = old["arma_df"].set_index("channel")
    assets, rows = {}, []
    for sensor in residuals:
        row = orders.loc[sensor]
        s = residuals[sensor]
        if bool(row.fallback):
            base = s
            if row.family == "floor":
                non = s.loc[raw[sensor] > config["floor_route"]["near_floor_value"]]
                if non.dropna().size >= 20:
                    base = non
            center = float(base.median())
            scale = float(1.4826 * (base - center).abs().median() + 1e-9)
            reconstructed = (s - center) / scale
            asset = {"route": str(row.family) if row.family == "floor" else "robust_z",
                     "center": center, "scale": scale, "fit_end": str(s.index.max())}
        else:
            if row.family != "arma" or row.d != 0 or row.D != 0:
                raise ValueError(f"Unsupported historical route requires explicit implementation: {sensor}")
            reference = s.iloc[:config["cold_start_reference_days"] * 1440]
            reference_values = reference.dropna().to_numpy()
            candidate = ms.fit_candidate(
                reference_values, np.array([1.0]),
                {"p": [int(row.p)], "q": [int(row.q)]}, config["use_garch"],
                1440, config["ljungbox_lags"]["min"], "arma")
            if candidate is None:
                raise RuntimeError(f"Historical selected model did not fit: {sensor}")
            model = ms._to_model(candidate, reference_values, f"{sensor}_recovered",
                                 config["ljungbox_lags"]["min"], 1440, {})
            reconstruction = ow.whiten_series(s, model)
            reconstructed = reconstruction["std_innovation"]
            asset = {"route": "arma", "ar": model.ar.tolist(), "ma": model.ma.tolist(),
                     "intercept": model.intercept, "garch": model.garch,
                     "initial_variance": float(model.warmup_state["sigma2"]),
                     "fixed_non_garch_variance": float(reconstruction["sigma2"].iloc[0]) if not model.garch else None,
                     "coefficient_fit_end": str(reference.index.max()),
                     "scaling_fit_end": str(s.index.max()) if not model.garch else str(reference.index.max()),
                     "missing_policy": "legacy_batch_zero_filter_input_and_NA_output; not_observation_imputation"}
        diff = (reconstructed - target[sensor]).abs()
        same_na = reconstructed.isna().eq(target[sensor].isna())
        assets[sensor] = asset
        rows.append({"sensor_id": sensor, "route": asset["route"],
                     "n_minutes": len(s), "max_abs_error": float(diff.max()),
                     "na_mismatches": int((~same_na).sum()),
                     "n_mismatches_1e_7": int((diff > 1e-7).sum())})
        print(sensor, asset["route"], "maximum historical error", diff.max(), flush=True)
        write_json(OUTPUT / "assets/whitening_reconstruction_candidates.json", {
            "source_state_sha256": sha256(path), "models": assets,
            "status": "historical_reconstruction_pending_full_route_validation"})
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/whitening_historical_replay.csv", index=False)
    write_json(OUTPUT / "audit/whitening_recovery_qa.json", {
        "archived_residual_and_innovation_exact": True,
        "reconstructed_whitening_equal_1e_7": bool(table.n_mismatches_1e_7.sum() == 0 and table.na_mismatches.sum() == 0),
        "n_channels": len(table), "new_period_scores_computed": False,
        "decomposition_frozen_policy_replay": "pending",
    })


if __name__ == "__main__":
    main()
