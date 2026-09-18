from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


def raw_hourly(raw: pd.DataFrame, minimum_minutes: int = 30) -> pd.DataFrame:
    if raw.index.has_duplicates or not raw.index.is_monotonic_increasing:
        raise ValueError("Raw time base must be unique and ordered")
    return raw.resample("1h").mean().where(raw.resample("1h").count().ge(minimum_minutes))


def context_features(hourly: pd.DataFrame) -> pd.DataFrame:
    features = {}
    for name in hourly:
        features[f"{name}_mean"] = hourly[name].rolling(24, min_periods=24).mean()
        features[f"{name}_std"] = hourly[name].rolling(24, min_periods=24).std()
    for name, values, period in (("h", hourly.index.hour, 24),
                                 ("d", hourly.index.dayofweek, 7)):
        features[f"sin_{name}"] = np.sin(2 * np.pi * values / period)
        features[f"cos_{name}"] = np.cos(2 * np.pi * values / period)
    return pd.DataFrame(features, index=hourly.index)


def fit_context(raw: pd.DataFrame, fit_end: str, *, fit_start: str,
                n_regimes: int = 4) -> tuple[pd.DataFrame, dict]:
    features = context_features(raw_hourly(raw))
    eligible = features.notna().all(axis=1)
    training = features.loc[eligible & (features.index >= pd.Timestamp(fit_start))
                            & (features.index + pd.Timedelta(hours=1) <= pd.Timestamp(fit_end))]
    if len(training) < 10 * n_regimes:
        raise ValueError("Insufficient development context support")
    scaler = StandardScaler().fit(training)
    model = KMeans(n_clusters=n_regimes, n_init=10, random_state=42).fit(scaler.transform(training))
    labels = pd.Series(np.nan, index=features.index, name="regime_id")
    labels.loc[eligible] = model.predict(scaler.transform(features.loc[eligible]))
    state = labels.to_frame()
    state["available_at"] = state.index + pd.Timedelta(hours=1)
    state["context_valid"] = eligible
    state["window_purity"] = np.nan
    for label in range(n_regimes):
        purity = labels.eq(label).rolling(24, min_periods=24).mean()
        state.loc[labels.eq(label), "window_purity"] = purity.loc[labels.eq(label)]
    state["context_24h_valid"] = eligible.rolling(24, min_periods=24).sum().eq(24)
    asset = {"model_id": "shared-context-d4-development-kmeans-v1",
             "feature_columns": list(features), "fit_start": fit_start, "fit_end": fit_end,
             "fit_hours": len(training), "scaler_mean": scaler.mean_.tolist(),
             "scaler_scale": scaler.scale_.tolist(), "centers": model.cluster_centers_.tolist(),
             "missing_policy": "unknown_no_fill", "D1_D2_scores_consumed": False,
             "D5_model_replaced": False, "hour_label": "start_of_completed_hour"}
    asset["model_sha256"] = hashlib.sha256(json.dumps(asset, sort_keys=True).encode()).hexdigest()
    state["context_model_id"] = asset["model_id"]
    return state, asset


def pair_support(raw: pd.DataFrame, left: str, right: str, hours: int = 24) -> pd.DataFrame:
    # A constant observed signal remains present, including a frozen sensor.
    both = raw[[left, right]].notna().all(axis=1)
    minute_fraction = both.astype(float).rolling(hours * 60, min_periods=hours * 60).mean()
    hourly_fraction = both.resample("1h").mean()
    output = pd.DataFrame(index=hourly_fraction.index)
    endpoint = output.index + pd.Timedelta(minutes=59)
    output["raw_common_fraction_24h"] = minute_fraction.reindex(endpoint).to_numpy()
    output["raw_supported_hours_fraction"] = hourly_fraction.ge(.8).rolling(hours, min_periods=hours).mean()
    output["raw_complete_window"] = minute_fraction.reindex(endpoint).notna().to_numpy()
    return output


def build_foundation(project: Path, fit_start: str, fit_end: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    folder = project / "1.1 Decomposition/outputs/parquet"
    contract_path = folder / "time_base_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for audit in contract["timestamp_audit"].values():
        for key in ("invalid_timestamp_rows", "duplicate_timestamp_rows", "out_of_order_transitions"):
            if audit[key] != 0:
                raise ValueError("Nonzero source timestamp defects require row-level adjudication")
    raw_path = folder / contract["raw_values_file"]
    raw = pd.read_parquet(raw_path)
    expected = pd.date_range(contract["expected_start"], contract["expected_end"], freq="1min")
    if not raw.index.equals(expected):
        raise ValueError("Raw foundation clock differs from its contract")
    state, asset = fit_context(raw, fit_end, fit_start=fit_start)
    asset["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    asset["time_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    output = project / "shared_data_foundation/outputs"
    output.mkdir(parents=True, exist_ok=True)
    state.to_parquet(output / "D4_context_hourly.parquet")
    (output / "D4_context_manifest.json").write_text(json.dumps(asset, indent=2), encoding="utf-8")
    return raw, state, asset
