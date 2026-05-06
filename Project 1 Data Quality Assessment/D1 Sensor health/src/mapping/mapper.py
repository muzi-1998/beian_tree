"""src/mapping/mapper.py
ScoreMapper — convert detector raw score to a 1-5 quality score per spec §3, §4.4.

Functions: logistic / piecewise / stepwise_duration.
Direction: anomaly larger ⇒ score lower.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Optional


def map_logistic(x, k: float, x0: float, low: float = 1.0, high: float = 5.0) -> np.ndarray:
    """Q(x) = low + (high-low) / (1 + exp(k·(x - x0)))
    Larger x ⇒ Q closer to low.
    """
    x = np.asarray(x, dtype=float)
    out = low + (high - low) / (1.0 + np.exp(k * (x - x0)))
    return np.clip(out, low, high)


def map_piecewise_decreasing(x, thresholds, scores) -> np.ndarray:
    """Equal-length convention: thresholds and scores both length k.
    Convention: smaller x → higher score.
        if x <= thresholds[0]:   score = scores[0]
        elif x <= thresholds[1]: score = scores[1]
        ...
        else:                    score = scores[-1] (worst)
    Thresholds must be ascending; scores typically descending (5→1).
    NaN preserved.
    """
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, np.nan)
    masked = ~np.isnan(x)
    xm = x[masked]
    # searchsorted with side='left' returns index i where xm <= thresholds[i]
    # If xm > all thresholds, idx = k.  Cap at k-1 (= last/worst score).
    idx = np.searchsorted(np.asarray(thresholds), xm, side="left")
    idx = np.clip(idx, 0, len(scores) - 1)
    out[masked] = np.asarray(scores)[idx]
    return out


def map_stepwise_duration(x, breaks, scores) -> np.ndarray:
    """Convention: breaks ascending (k items), scores has k+1 items.
        x <= breaks[0]:               scores[0]   (best)
        breaks[0] < x <= breaks[1]:   scores[1]
        ...
        x > breaks[-1]:               scores[-1]  (worst)
    """
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, np.nan)
    masked = ~np.isnan(x)
    xm = x[masked]
    idx = np.searchsorted(np.asarray(breaks), xm, side="right")
    out[masked] = np.asarray(scores)[idx]
    return out


def apply_mapping(metric: pd.Series, mapping_entry) -> pd.Series:
    """Dispatch to the right mapping function based on entry.function."""
    fn = mapping_entry.function
    vals = metric.values
    if fn == "logistic":
        out = map_logistic(vals, k=mapping_entry.k, x0=mapping_entry.x0)
    elif fn == "piecewise":
        out = map_piecewise_decreasing(vals,
                                       thresholds=mapping_entry.thresholds,
                                       scores=mapping_entry.scores)
    elif fn == "stepwise_duration":
        out = map_stepwise_duration(vals,
                                    breaks=mapping_entry.breaks,
                                    scores=mapping_entry.scores)
    else:
        raise ValueError(f"Unknown mapping function: {fn}")
    return pd.Series(out, index=metric.index, name=f"Q_{mapping_entry.metric}")


def export_mapping_params(mapping_cfg) -> pd.DataFrame:
    """Build the D1_mapping_params table per output spec §4.1."""
    rows = []
    def _row(subscore, entry, detector_name):
        return {
            "mapping_id": f"{subscore}_{detector_name}",
            "subscore_name": subscore,
            "detector_name": detector_name,
            "input_metric": entry.metric,
            "mapping_type": entry.function,
            "direction": entry.direction,
            "k": entry.k, "x0": entry.x0,
            "thresholds": str(entry.thresholds) if entry.thresholds else None,
            "scores": str(entry.scores) if entry.scores else None,
            "breaks": str(entry.breaks) if entry.breaks else None,
            "rate_floor": entry.rate_floor,
            "version": "v1.0",
            "source": "expert_calibrated",
        }
    rows.append(_row("D1_spike",  mapping_cfg.spike,  "hampel"))
    rows.append(_row("D1_step",   mapping_cfg.step,   "adjacent_ks"))
    rows.append(_row("D1_drift",  mapping_cfg.drift,  "pls_virtual"))
    rows.append(_row("D1_freeze_rle",      mapping_cfg.freeze.rle,      "rle"))
    rows.append(_row("D1_freeze_low_var",  mapping_cfg.freeze.low_var,  "low_var"))
    rows.append(_row("D1_freeze_unique",   mapping_cfg.freeze.unique,   "unique_ratio"))
    rows.append(_row("D1_regime", mapping_cfg.regime, "w1"))
    return pd.DataFrame(rows)
