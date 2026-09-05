"""Explicit clock conversion candidates. Upstream delays must be added separately."""
from __future__ import annotations

import pandas as pd


def interval_contract(dimension: str, labels: pd.DatetimeIndex) -> pd.DataFrame:
    if not isinstance(labels, pd.DatetimeIndex) or not labels.is_unique:
        raise ValueError("Unique datetime labels required")
    if dimension in {"D1", "D2"}:
        # D1 mixes longer trailing detectors; this is the reporting-hour interval,
        # not a claim that every detector has a one-hour lookback.
        start, end = labels, labels + pd.Timedelta(hours=1)
    elif dimension == "D3":
        start, end = labels - pd.Timedelta(hours=2), labels
    elif dimension == "D4":
        start, end = labels - pd.Timedelta(hours=23), labels + pd.Timedelta(hours=1)
    elif dimension == "D5":
        # 144 left-labelled 10-minute snapshots including the one at label time.
        start, end = labels - pd.Timedelta(hours=23, minutes=50), labels + pd.Timedelta(minutes=10)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")
    return pd.DataFrame({"dimension": dimension, "timestamp_label": labels,
                         "interval_start": start, "interval_end_exclusive": end,
                         "base_available_at": end,
                         "upstream_and_processing_latency_included": False})


def select_known(evidence: pd.DataFrame, decision_at: pd.Timestamp) -> pd.DataFrame:
    required = {"available_at", "valid_until"}
    if not required.issubset(evidence):
        raise ValueError("Explicit availability and expiry required; do not ffill blindly")
    available = pd.to_datetime(evidence.available_at)
    expiry = pd.to_datetime(evidence.valid_until)
    if (expiry < available).any():
        raise ValueError("Evidence expiry precedes availability")
    return evidence.loc[available.le(decision_at) & expiry.gt(decision_at)].copy()
