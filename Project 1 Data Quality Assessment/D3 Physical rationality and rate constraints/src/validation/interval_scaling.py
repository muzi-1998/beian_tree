"""Canonical interval-width perturbation for D3 sensitivity analyses."""

from __future__ import annotations

import numpy as np


INTERVAL_SCALING_VERSION = "interval-sensitivity@v1.0.0"


def scale_interval(
    low: float | None,
    high: float | None,
    multiplier: float,
    anchor: str,
) -> tuple[float | None, float | None]:
    """Scale interval width while preserving its registered anchor."""
    if multiplier <= 0:
        raise ValueError("Interval multiplier must be positive")
    if anchor == "none":
        return low, high
    if low is None or high is None:
        raise ValueError(f"Anchor '{anchor}' requires two finite interval bounds")
    if high <= low:
        raise ValueError("Interval high bound must exceed its low bound")
    width = high - low
    if anchor == "center":
        center = 0.5 * (low + high)
        half_width = 0.5 * width * multiplier
        return center - half_width, center + half_width
    if anchor == "lower":
        return low, low + width * multiplier
    if anchor == "upper":
        return high - width * multiplier, high
    raise ValueError(f"Unsupported interval anchor: {anchor}")


def interval_warning_mask(
    values: np.ndarray,
    low: float | None,
    high: float | None,
) -> np.ndarray:
    """Return out-of-interval flags without treating an absent side as failure."""
    values = np.asarray(values, dtype=float)
    warning = np.zeros(len(values), dtype=bool)
    finite = np.isfinite(values)
    if low is not None:
        warning |= finite & (values < low)
    if high is not None:
        warning |= finite & (values > high)
    return warning
