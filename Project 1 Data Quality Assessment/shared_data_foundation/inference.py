"""Inference-only interface for the development-fitted D4 context asset."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .context import context_features, raw_hourly


def infer_context(raw: pd.DataFrame, asset: dict) -> pd.DataFrame:
    features = context_features(raw_hourly(raw)).reindex(columns=asset["feature_columns"])
    valid = features.notna().all(axis=1)
    scaled = (features.loc[valid].to_numpy() - np.asarray(asset["scaler_mean"])) / np.asarray(asset["scaler_scale"])
    centers = np.asarray(asset["centers"])
    labels = pd.Series(np.nan, index=features.index, name="regime_id")
    labels.loc[valid] = np.square(scaled[:, None, :] - centers[None, :, :]).sum(axis=2).argmin(axis=1)
    state = labels.to_frame()
    state["available_at"] = state.index + pd.Timedelta(hours=1)
    state["context_valid"] = valid
    state["window_purity"] = np.nan
    for value in range(len(centers)):
        mask = labels.eq(value)
        state.loc[mask, "window_purity"] = mask.rolling(24, min_periods=24).mean().loc[mask]
    state["context_24h_valid"] = valid.rolling(24, min_periods=24).sum().eq(24)
    state["context_model_id"] = asset["model_id"]
    return state
