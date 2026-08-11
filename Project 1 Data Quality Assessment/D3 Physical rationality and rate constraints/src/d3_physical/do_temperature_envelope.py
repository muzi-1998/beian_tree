"""Frozen temperature-conditioned operational envelopes for aerobic DO."""

from __future__ import annotations

import numpy as np


def freshwater_do_saturation_mg_l(temperature_c) -> np.ndarray:
    """Reference freshwater DO saturation at standard atmospheric pressure.

    Uses the Benson-Krause freshwater equation adopted by USGS DOTABLES. In
    this project the covariate is influent temperature, so the result is only
    a monotonic temperature normalizer, not an in-basin thermodynamic
    saturation measurement or a hard physical limit.
    """
    temperature = np.asarray(temperature_c, dtype=float)
    result = np.full(temperature.shape, np.nan, dtype=float)
    valid = np.isfinite(temperature) & (temperature >= 0.0) & (temperature <= 40.0)
    kelvin = temperature[valid] + 273.15
    result[valid] = np.exp(
        -139.34411
        + 1.575701e5 / kelvin
        - 6.642308e7 / kelvin**2
        + 1.243800e10 / kelvin**3
        - 8.621949e11 / kelvin**4
    )
    return result


def temperature_conditioned_upper(
    temperature_c,
    sensor_meta: dict,
    contract: dict,
) -> tuple[np.ndarray | None, str]:
    """Return a frozen position-shared upper envelope for aerobic DO."""
    if sensor_meta.get("type") != "DO" or sensor_meta.get("process_zone") != "aerobic":
        return None, "not_applicable"
    if not contract.get("enabled", False):
        return None, "disabled"
    position = str(sensor_meta["position"])
    alpha = contract["calibration"]["alpha_by_position"].get(position)
    if alpha is None:
        raise KeyError(f"No frozen aerobic DO alpha for longitudinal position {position}")
    upper = float(alpha) * freshwater_do_saturation_mg_l(temperature_c)
    finite = np.isfinite(upper)
    status = (
        "evaluated"
        if finite.all()
        else "partially_evaluated"
        if finite.any()
        else "temperature_unavailable"
    )
    return upper, status
