"""Raw detector-input fault injection for calibrating the Step score mapping."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

import numpy as np
import pandas as pd

from src.detectors.step_adjacent_ks import AdjacentKSStepDetector


@dataclass(frozen=True)
class StepCalibrationConfig:
    window_h: int = 192
    event_h: int = 72
    evaluation_start_h: int = 12
    evaluation_end_h: int = 60
    windows_per_channel: int = 6
    amplitudes_sigma: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
    k_grid: tuple[float, ...] = (4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0)
    x0_grid: tuple[float, ...] = (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55)
    max_null_warning_rate: float = 0.05
    max_small_hard_rate: float = 0.05
    max_material_miss_rate: float = 0.20
    min_normal_fraction: float = 0.95
    calibration_scoring_modes: tuple[str, ...] = ("iid",)


TARGET_Q = {
    0.0: 4.5,
    0.5: 4.0,
    1.0: 3.5,
    1.5: 3.0,
    2.0: 2.5,
    3.0: 1.5,
    4.0: 1.0,
}


def logistic_quality(x, k: float, x0: float) -> np.ndarray:
    values = np.asarray(x, dtype=float)
    return np.clip(1.0 + 4.0 / (1.0 + np.exp(k * (values - x0))), 1.0, 5.0)


def confirmation_gate(q24: np.ndarray, q36: np.ndarray) -> np.ndarray:
    result = np.asarray(q24, dtype=float).copy()
    mask = result <= 2.5
    result[mask] = np.maximum(result[mask], np.asarray(q36, dtype=float)[mask])
    return np.clip(result, 1.0, 5.0)


def _robust_scale(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.nan
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale <= 1e-9:
        scale = float(np.std(finite))
    return scale if np.isfinite(scale) and scale > 1e-9 else np.nan


def _window_starts(
    series: pd.Series,
    normal_mask: pd.Series,
    cfg: StepCalibrationConfig,
) -> list[int]:
    valid = series.notna() & normal_mask.reindex(series.index).fillna(False)
    candidates = []
    for start in range(0, len(series) - cfg.window_h + 1, 24):
        segment = valid.iloc[start : start + cfg.window_h]
        if float(segment.mean()) < cfg.min_normal_fraction:
            continue
        pre = series.iloc[start : start + cfg.event_h].to_numpy(dtype=float)
        if np.isfinite(_robust_scale(pre)):
            candidates.append(start)
    if len(candidates) <= cfg.windows_per_channel:
        return candidates
    positions = np.linspace(0, len(candidates) - 1, cfg.windows_per_channel)
    return [candidates[int(round(position))] for position in positions]


def _detector_outputs(series: pd.Series, neff_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    ks24 = AdjacentKSStepDetector(win_h=24, alpha=0.001, neff_ratio=neff_ratio).score(
        series
    ).raw_score.to_numpy(dtype=float)
    ks36 = AdjacentKSStepDetector(win_h=36, alpha=0.001, neff_ratio=neff_ratio).score(
        series
    ).raw_score.to_numpy(dtype=float)
    return ks24, ks36


def build_injection_library(
    routed_input: pd.DataFrame,
    normal_masks: dict[str, pd.Series],
    neff_ratio: dict[str, float],
    scoring_mode: dict[str, str],
    cfg: StepCalibrationConfig,
) -> pd.DataFrame:
    """Create channel-balanced sustained-step scenarios in the valid mapping domain.

    The logistic Step mapping is calibrated only where the adjacent-window KS
    statistic retains its i.i.d. interpretation. Autocorrelation-aware and
    process-floor routes remain part of the applicability audit, but must not
    distort the global mapping parameters.
    """
    rows = []
    for channel in routed_input.columns:
        mode = str(scoring_mode.get(channel, "unknown"))
        if mode not in cfg.calibration_scoring_modes:
            continue
        neff = float(neff_ratio.get(channel, 1.0))
        if neff <= 0:
            continue
        series = routed_input[channel]
        starts = _window_starts(series, normal_masks[channel], cfg)
        for window_id, start in enumerate(starts):
            base = series.iloc[start : start + cfg.window_h].copy()
            pre = base.iloc[: cfg.event_h].to_numpy(dtype=float)
            scale = _robust_scale(pre)
            if not np.isfinite(scale):
                continue
            for amplitude in cfg.amplitudes_sigma:
                for direction in ((1,) if amplitude == 0 else (-1, 1)):
                    injected = base.copy()
                    injected.iloc[cfg.event_h :] += direction * amplitude * scale
                    ks24, ks36 = _detector_outputs(injected.rename(channel), neff)
                    lo = cfg.event_h + cfg.evaluation_start_h
                    hi = min(cfg.event_h + cfg.evaluation_end_h + 1, len(injected))
                    rows.append({
                        "sensor_id": channel,
                        "window_id": window_id,
                        "window_start": base.index[0],
                        "event_time": base.index[cfg.event_h],
                        "amplitude_sigma": float(amplitude),
                        "direction": int(direction),
                        "target_q": float(TARGET_Q[float(amplitude)]),
                        "local_scale": float(scale),
                        "neff_ratio": neff,
                        "scoring_mode": mode,
                        "ks24_window": ks24[lo:hi],
                        "ks36_window": ks36[lo:hi],
                    })
    if not rows:
        raise RuntimeError("No eligible clean windows were found for Step calibration")
    return pd.DataFrame(rows)


def _score_scenarios(library: pd.DataFrame, k: float, x0: float) -> pd.DataFrame:
    records = []
    for row in library.itertuples(index=False):
        q24 = logistic_quality(row.ks24_window, k, x0)
        q36 = logistic_quality(row.ks36_window, k, x0)
        qfinal = confirmation_gate(q24, q36)
        finite = qfinal[np.isfinite(qfinal)]
        min_q = float(np.min(finite)) if finite.size else np.nan
        records.append({
            "sensor_id": row.sensor_id,
            "window_id": row.window_id,
            "amplitude_sigma": row.amplitude_sigma,
            "direction": row.direction,
            "target_q": row.target_q,
            "min_q_final": min_q,
        })
    return pd.DataFrame(records)


def injection_library_sha256(library: pd.DataFrame) -> str:
    """Hash scenario metadata and detector responses in a stable row order."""
    sort_columns = ["sensor_id", "window_id", "amplitude_sigma", "direction"]
    ordered = library.sort_values(sort_columns).reset_index(drop=True)
    response_columns = ["ks24_window", "ks36_window"]
    metadata = ordered.drop(columns=response_columns).copy()
    for column in ["window_start", "event_time"]:
        if column in metadata:
            metadata[column] = metadata[column].astype(str)
    digest = hashlib.sha256(
        metadata.to_csv(index=False, float_format="%.12g").encode("utf-8")
    )
    for column in response_columns:
        for values in ordered[column]:
            array = np.nan_to_num(
                np.asarray(values, dtype="<f8"),
                nan=np.inf,
                posinf=np.finfo("<f8").max,
                neginf=np.finfo("<f8").min,
            )
            digest.update(array.tobytes())
    return digest.hexdigest()


def _balanced_metrics(scored: pd.DataFrame) -> dict[str, float]:
    channel_rmse = scored.groupby("sensor_id").apply(
        lambda frame: float(np.sqrt(np.nanmean((frame["min_q_final"] - frame["target_q"]) ** 2))),
        include_groups=False,
    )
    null = scored[scored["amplitude_sigma"] == 0.0]
    small = scored[scored["amplitude_sigma"] == 0.5]
    material = scored[scored["amplitude_sigma"] >= 2.0]
    return {
        "rmse_channel_balanced": float(channel_rmse.mean()),
        "null_warning_rate": float((null["min_q_final"] < 3.0).mean()),
        "small_hard_rate": float((small["min_q_final"] <= 2.0).mean()),
        "material_miss_rate": float((material["min_q_final"] > 2.5).mean()),
        "material_detection_rate": float((material["min_q_final"] <= 2.5).mean()),
    }


def evaluate_parameter_grid(
    library: pd.DataFrame,
    cfg: StepCalibrationConfig,
    channels: Iterable[str] | None = None,
) -> pd.DataFrame:
    subset = library if channels is None else library[library["sensor_id"].isin(set(channels))]
    rows = []
    for k in cfg.k_grid:
        for x0 in cfg.x0_grid:
            metrics = _balanced_metrics(_score_scenarios(subset, k, x0))
            penalty = (
                4.0 * max(0.0, metrics["null_warning_rate"] - cfg.max_null_warning_rate)
                + 3.0 * max(0.0, metrics["small_hard_rate"] - cfg.max_small_hard_rate)
                + 4.0 * max(0.0, metrics["material_miss_rate"] - cfg.max_material_miss_rate)
            )
            rows.append({"k": k, "x0": x0, **metrics,
                         "constraint_penalty": penalty,
                         "objective": metrics["rmse_channel_balanced"] + penalty})
    return pd.DataFrame(rows).sort_values(
        ["objective", "constraint_penalty", "rmse_channel_balanced", "x0", "k"]
    ).reset_index(drop=True)


def select_step_mapping(library: pd.DataFrame, cfg: StepCalibrationConfig) -> dict:
    channels = sorted(library["sensor_id"].unique())
    grid = evaluate_parameter_grid(library, cfg)
    selected = grid.iloc[0]
    loo_rows = []
    for held_out in channels:
        train_channels = [channel for channel in channels if channel != held_out]
        fold_grid = evaluate_parameter_grid(library, cfg, train_channels)
        fold_selected = fold_grid.iloc[0]
        held_scored = _score_scenarios(
            library[library["sensor_id"] == held_out],
            float(fold_selected["k"]),
            float(fold_selected["x0"]),
        )
        loo_rows.append({
            "held_out_sensor": held_out,
            "selected_k": float(fold_selected["k"]),
            "selected_x0": float(fold_selected["x0"]),
            **_balanced_metrics(held_scored),
        })
    scenario_export = _score_scenarios(library, float(selected["k"]), float(selected["x0"]))
    library_sha256 = injection_library_sha256(library)
    hash_payload = {
        "config": cfg.__dict__,
        "selected_k": float(selected["k"]),
        "selected_x0": float(selected["x0"]),
        "n_scenarios": len(library),
        "channels": channels,
        "library_sha256": library_sha256,
    }
    calibration_id = "step-injection-" + hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "calibration_id": calibration_id,
        "library_sha256": library_sha256,
        "selected": selected.to_dict(),
        "grid": grid,
        "leave_one_channel_out": pd.DataFrame(loo_rows),
        "scenario_scores": scenario_export,
    }
