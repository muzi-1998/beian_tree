"""Nominal archive quadrature on explicit common technical support."""
from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_common_support(frame: pd.DataFrame, valid: pd.Series, variables: list[str], step: int,
                             profile: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """No extrapolation: unknown sensor support remains unknown after arithmetic."""
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates:
        raise ValueError("A unique DatetimeIndex is required.")
    if len(frame) == 0 or step <= 0 or 1440 % step:
        raise ValueError("Nonempty input and a positive day-dividing step are required.")
    if not frame.index.is_monotonic_increasing or not frame.index.equals(frame.index.floor("min")):
        raise ValueError("Archive support must be ordered and minute-aligned.")
    if not valid.index.equals(frame.index) or valid.isna().any():
        raise ValueError("Common support must align with the input and contain explicit booleans.")
    if not np.isfinite(frame.loc[valid, ["Q"] + variables].to_numpy(dtype=float)).all():
        raise ValueError("Admitted technical support contains nonfinite values.")
    if (frame.loc[valid, "Q"] <= 0).any():
        raise ValueError("Common support requires strictly positive instantaneous Q.")
    rule = f"{step}min"
    count = valid.astype(int).resample(rule, origin="start_day").sum()
    q = frame["Q"].where(valid)
    qsum = q.resample(rule, origin="start_day").sum(min_count=1)
    duration = count / 60.0
    volume = qsum / 60.0
    qbar = qsum / count.replace(0, np.nan)
    views, ledger = [], []
    for variable in variables:
        c = frame[variable].where(valid)
        csum = c.resample(rule, origin="start_day").sum(min_count=1)
        qcsum = (q * c).resample(rule, origin="start_day").sum(min_count=1)
        c_tw = csum / count.replace(0, np.nan)
        c_fw = qcsum / qsum
        load = qcsum / 60.0 / 1000.0
        reconstruction = c_fw * volume / 1000.0
        error = (reconstruction - load).abs() / load.abs().clip(lower=1.0)
        base = pd.DataFrame({"bin_start": count.index, "bin_end": count.index + pd.Timedelta(minutes=step),
                             "step_minutes": step, "variable": variable, "support_profile": profile,
                             "support_id": [f"{profile}_{step}m_{x.isoformat()}" for x in count.index],
                             "split": "development", "valid_archive_rows": count.to_numpy(),
                             "valid_duration_hours": duration.to_numpy(), "nominal_archive_coverage": (count / step).to_numpy(),
                             "missing_exposure_minutes": (step - count).to_numpy(),
                             "full_technical_archive_bin": count.eq(step).to_numpy(),
                             "fresh_count": None, "max_age_minutes": None,
                             "measurement_support_status": "UNKNOWN", "model_admitted": False,
                             "support_basis": "nominal_1min_aligned_archive_not_native_measurement_support",
                             "unit_status": "nitrogen_basis_pending" if variable in {"TN", "NH4_N"} else "source_header"})
        view = base.copy()
        view["C_TW"] = c_tw.to_numpy()
        view["C_FW"] = c_fw.to_numpy()
        view["Qbar_on_same_support_m3_h"] = qbar.to_numpy()
        view["concentration_unit"] = "mg/L_source_header"
        views.append(view)
        account = base.copy()
        account["V_m3"] = volume.to_numpy()
        account["L_kg"] = load.to_numpy()
        account["FW_times_V_reconstructed_kg"] = reconstruction.to_numpy()
        account["roundtrip_error_scaled"] = error.to_numpy()
        account["load_status"] = "provisional_archive_quadrature_not_verified_native_boundary"
        ledger.append(account)
    return pd.concat(views, ignore_index=True), pd.concat(ledger, ignore_index=True)
