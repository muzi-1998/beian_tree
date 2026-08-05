"""End-to-end synthetic challenges for the D2 timestamp-to-score route."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .process_floor import route_availability_evidence
from .scorer import D2Aggregator, GapSeverityScorer, HardAvailabilityScorer, TemporalIntegrityScorer
from ..utils.config_loader import D2Config
from ..utils.timestamp_quality import classify_timestamp_series


def _run_length(flag: pd.Series) -> pd.Series:
    value = flag.astype(int)
    groups = value.ne(value.shift()).cumsum()
    return (value * (value.groupby(groups).cumcount() + 1)).astype(float)


def evaluate_raw_series(
    raw: pd.DataFrame,
    cfg: D2Config,
    *,
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
    sensor_id: str = "DO_1_1",
    qha_window_hours: int = 6,
    hard_stasis_min: int | None = None,
) -> dict[str, Any]:
    """Audit, align, route and score a two-column raw challenge.

    ``raw`` must contain ``timestamp`` and ``value`` in source order. Timestamp
    defects are classified before sorting; channel continuity and stasis are
    then evaluated on the canonical one-minute grid.
    """
    required = {"timestamp", "value"}
    if not required.issubset(raw.columns):
        raise ValueError(f"raw challenge requires columns {sorted(required)}")
    sensor = cfg.sensors[sensor_id]
    ts_cfg = cfg.mapping.timestamp_quality
    audit = classify_timestamp_series(
        raw["timestamp"],
        expected_interval_sec=float(ts_cfg["expected_interval_sec"]),
        jitter_tolerance_sec=float(ts_cfg["jitter_tolerance_sec"]),
        gap_interval_min_sec=float(ts_cfg["gap_interval_min_sec"]),
    )

    ordered = raw.copy()
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], errors="coerce")
    ordered["value"] = pd.to_numeric(ordered["value"], errors="coerce")
    ordered = ordered.dropna(subset=["timestamp"]).sort_values("timestamp")
    ordered = ordered.drop_duplicates("timestamp", keep="last").set_index("timestamp")
    grid = pd.date_range(expected_start, expected_end, freq=cfg.time_grid["freq"])
    aligned = ordered["value"].reindex(grid)
    present = aligned.notna()
    missing = ~present
    groups = missing.ne(missing.shift(fill_value=False)).cumsum()
    missing_run_size = missing.groupby(groups).transform("sum")
    short_gap = missing & missing_run_size.le(int(cfg.mapping.imputation["short_gap_max_min"]))
    long_gap = missing & ~short_gap
    imputed = aligned.copy()
    candidate = imputed.interpolate(method="time", limit_area="inside")
    imputed.loc[short_gap] = candidate.loc[short_gap]

    precision = float(sensor.precision)
    raw_diff = aligned.diff().abs().fillna(precision + 1.0)
    same_observed = raw_diff.lt(precision) & present & present.shift(1, fill_value=False)
    hard_rle = _run_length(same_observed)
    filled = imputed.ffill().bfill()
    filled_diff = filled.diff().abs().fillna(precision + 1.0)
    soft_rle = _run_length(filled_diff.lt(precision))
    threshold = float(cfg.mapping.freeze_detection[f"tau_iqr_{sensor.sensor_type}"])
    rolling_iqr = (
        filled.rolling("30min", min_periods=15).quantile(0.75)
        - filled.rolling("30min", min_periods=15).quantile(0.25)
    ).fillna(threshold + 1.0)
    hard_min = int(hard_stasis_min or cfg.mapping.freeze_detection["tau_rle_D1_min"])
    routed = route_availability_evidence(
        aligned_value=imputed,
        missing=missing,
        long_gap=long_gap,
        rle_run_min=soft_rle,
        hard_rle_run_min=hard_rle,
        rolling_iqr=rolling_iqr,
        low_iqr_threshold=threshold,
        lenient_rle_min=int(cfg.mapping.freeze_detection["tau_rle_D2_min"]),
        hard_rle_min=hard_min,
        availability_mode=sensor.availability_mode,
        process_floor_threshold=sensor.process_floor_threshold,
    )

    main_window = cfg.main_window.length
    main_minutes = int(pd.Timedelta(main_window) / pd.Timedelta("1min"))
    qha_window = f"{int(qha_window_hours)}h"
    qha_minutes = int(qha_window_hours * 60)
    missing_rate = missing.astype(float).rolling(main_window, min_periods=main_minutes).mean()
    rle_missing = _run_length(missing)
    lmax = rle_missing.rolling(main_window, min_periods=main_minutes).max()
    gap_starts = missing.astype(int).diff().gt(0).astype(float)
    gap_count = gap_starts.rolling(main_window, min_periods=main_minutes).sum()
    gap_ends = missing & ~missing.shift(-1, fill_value=False)
    p95_gap = rle_missing.where(gap_ends).rolling(main_window, min_periods=1).quantile(0.95).fillna(0)
    hard_count = routed["hard_availability_loss"].astype(float).rolling(
        qha_window, min_periods=qha_minutes
    ).sum()
    observed_count = present.astype(float).rolling(
        qha_window, min_periods=qha_minutes
    ).sum()
    hard_fraction = hard_count.div(observed_count.where(observed_count > 0))

    audit_hour = audit["timestamp"].dt.floor("h")
    audit_counts = audit.assign(_hour=audit_hour).groupby("_hour")[[
        "valid_transition", "true_irregular", "duplicate", "out_of_order"
    ]].sum()
    hour_grid = pd.date_range(grid.min().floor("h"), grid.max().floor("h"), freq="1h")
    audit_counts = audit_counts.reindex(hour_grid, fill_value=0)
    rolling_audit = audit_counts.rolling(24, min_periods=24).sum()
    denominator = rolling_audit["valid_transition"].replace(0, np.nan)

    stats = pd.DataFrame({
        "missing_rate": missing_rate,
        "L_max_min": lmax,
        "P95_gap_min": p95_gap,
        "gap_run_count": gap_count,
        "hard_stasis_fraction_observed": hard_fraction,
    }).resample("1h").last()
    for column in ("true_irregular", "duplicate", "out_of_order"):
        stats[f"{column}_rate"] = rolling_audit[column].div(denominator).reindex(stats.index)

    ti = TemporalIntegrityScorer(cfg).score(stats)
    gs = GapSeverityScorer(cfg).score(stats)
    zero_response = pd.Series(0.0, index=stats.index)
    ha, _ = HardAvailabilityScorer(cfg).score(
        stats, zero_response, allow_response_loss=False
    )
    scored = D2Aggregator(cfg, {"veto_thresholds": {}}).aggregate(ti, gs, ha, stats)
    scored["missing_rate"] = stats["missing_rate"]
    scored["L_max_min"] = stats["L_max_min"]
    scored["hard_stasis_fraction_observed"] = stats["hard_stasis_fraction_observed"]
    return {
        "audit": audit,
        "aligned": aligned,
        "routed": routed,
        "stats": stats,
        "scores": scored,
    }
