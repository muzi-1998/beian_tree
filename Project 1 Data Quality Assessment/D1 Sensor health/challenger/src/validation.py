from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp, qmc

from .event_arbitration import (
    calibrate_event_threshold,
    extract_events,
    poisson_rate_interval,
)
from .innovation import (
    AR1InnovationModel,
    empirical_resolution,
    fit_ar1_innovation,
    minute_causal_innovation,
    robust_scale,
)
from .multiscale_glr import multiscale_glr


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hampel_score(series: pd.Series, window: int = 21) -> pd.Series:
    median = series.rolling(window, min_periods=max(5, window // 4)).median()
    mad = (series - median).abs().rolling(
        window, min_periods=max(5, window // 4)
    ).median()
    scale = 1.4826 * mad.replace(0, np.nan)
    return (series - median).abs() / scale


def _adjacent_ks_score(series: pd.Series, window: int, neff_ratio: float) -> pd.Series:
    values = series.to_numpy(dtype=float)
    score = np.full(len(values), np.nan)
    deflate = float(np.sqrt(np.clip(neff_ratio, 0.0, 1.0)))
    for position in range(2 * window, len(values)):
        earlier = values[position - 2 * window: position - window]
        later = values[position - window: position]
        earlier = earlier[np.isfinite(earlier)]
        later = later[np.isfinite(later)]
        if len(earlier) >= max(8, window // 3) and len(later) >= max(8, window // 3):
            score[position] = ks_2samp(earlier, later).statistic * deflate
    return pd.Series(score, index=series.index)


def _logistic_quality(values: pd.Series, k: float, x0: float) -> pd.Series:
    array = values.to_numpy(dtype=float)
    quality = 1.0 + 4.0 / (1.0 + np.exp(k * (array - x0)))
    return pd.Series(np.clip(quality, 1.0, 5.0), index=values.index)


def build_hourly_eligibility(state: dict[str, Any]) -> dict[str, pd.Series]:
    eligibility: dict[str, pd.Series] = {}
    for sensor in state["D1_v11"].columns:
        index = state["D1_v11"].index
        eligibility[sensor] = (
            state["D1_v11"][sensor].ge(4.5)
            & state["state_log_dict"][sensor]["state_name"].reindex(index).eq("Normal")
            & state["subs_v11"][sensor]["Q_freeze"].reindex(index).ge(3.0)
            & state["subs_v11"][sensor]["Q_regime"].reindex(index).ge(3.0)
        ).fillna(False)
    return eligibility


def _minute_mask(index: pd.DatetimeIndex, hourly: pd.Series) -> pd.Series:
    values = hourly.reindex(index.floor("h")).fillna(False).to_numpy(dtype=bool)
    return pd.Series(values, index=index, dtype=bool)


def _score_tracks(
    df_min: pd.DataFrame,
    state: dict[str, Any],
    eligibility_h: dict[str, pd.Series],
    development_end: pd.Timestamp,
    design: dict[str, Any],
) -> tuple[
    dict[str, dict[str, pd.Series]],
    dict[str, AR1InnovationModel],
    dict[str, dict[str, float]],
    pd.DataFrame,
]:
    minute_cfg = design["minute_innovation"]
    hourly_cfg = design["hourly_innovation"]
    excluded = {"DO_1_4", "DO_2_4"}
    tracks: dict[str, dict[str, pd.Series]] = {
        "minute_glr": {},
        "minute_baseline": {},
        "hourly_glr": {},
        "hourly_baseline": {},
    }
    model_rows: list[dict[str, Any]] = []
    models: dict[str, AR1InnovationModel] = {}
    minute_parameters: dict[str, dict[str, float]] = {}
    for sensor in state["D1_v11"].columns:
        development_resolution = empirical_resolution(
            df_min.loc[:development_end, sensor]
        )
        development_probe = minute_causal_innovation(
            df_min.loc[:development_end, sensor].rename(sensor),
            location_window=int(minute_cfg["location_window_minutes"]),
            scale_window=int(minute_cfg["scale_window_minutes"]),
            guard=int(minute_cfg["guard_minutes"]),
            min_location=int(minute_cfg["minimum_location_observations"]),
            min_scale=int(minute_cfg["minimum_scale_observations"]),
            resolution_floor_multiplier=float(minute_cfg["resolution_floor_multiplier"]),
            fixed_resolution=development_resolution,
        )
        development_scale_floor = float(
            development_probe["scale"].dropna().quantile(0.1)
        )
        minute_parameters[sensor] = {
            "resolution": float(development_resolution),
            "scale_floor": development_scale_floor,
        }
        minute_frame = minute_causal_innovation(
            df_min[sensor].rename(sensor),
            location_window=int(minute_cfg["location_window_minutes"]),
            scale_window=int(minute_cfg["scale_window_minutes"]),
            guard=int(minute_cfg["guard_minutes"]),
            min_location=int(minute_cfg["minimum_location_observations"]),
            min_scale=int(minute_cfg["minimum_scale_observations"]),
            resolution_floor_multiplier=float(minute_cfg["resolution_floor_multiplier"]),
            fixed_resolution=development_resolution,
            fixed_scale_floor=development_scale_floor,
        )
        tracks["minute_glr"][sensor] = multiscale_glr(
            minute_frame["innovation"], minute_cfg["glr_scales_minutes"]
        )["glr_score"]
        tracks["minute_baseline"][sensor] = _hampel_score(df_min[sensor].rename(sensor))
        model_rows.append(
            {
                "sensor_id": sensor,
                "track": "minute_glr",
                "status": "eligible",
                "empirical_resolution": float(development_resolution),
                "frozen_scale_floor": development_scale_floor,
            }
        )
        if sensor in excluded:
            model_rows.append(
                {
                    "sensor_id": sensor,
                    "track": "hourly_glr",
                    "status": "excluded_process_floor",
                    "reason": "no verified comparable excitation",
                }
            )
            continue
        series = state["whitened_input_h"][sensor].rename(sensor)
        fit_mask = eligibility_h[sensor] & series.index.to_series().le(development_end).to_numpy()
        model = fit_ar1_innovation(
            series,
            fit_mask,
            phi_clip=float(hourly_cfg["phi_clip"]),
        )
        models[sensor] = model
        tracks["hourly_glr"][sensor] = multiscale_glr(
            model.transform(series), hourly_cfg["glr_scales_hours"]
        )["glr_score"]
        tracks["hourly_baseline"][sensor] = 5.0 - state["subs_v11"][sensor]["Q_step"].reindex(series.index)
        model_rows.append(
            {
                "sensor_id": sensor,
                "track": "hourly_glr",
                "status": "eligible",
                **asdict(model),
                "scoring_route": state["scoring_mode"][sensor],
            }
        )
    return tracks, models, minute_parameters, pd.DataFrame(model_rows)


def _calibrate_tracks(
    tracks: dict[str, dict[str, pd.Series]],
    eligibility_h: dict[str, pd.Series],
    df_min: pd.DataFrame,
    development_end: pd.Timestamp,
    sap: dict[str, Any],
    design: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
    budgets = sap["threshold_selection"]["track_allocation_events_per_sensor_day"]
    records: list[dict[str, Any]] = []
    results: dict[str, dict[str, Any]] = {}
    definitions = [
        (
            "minute_glr",
            "minute_baseline",
            pd.Timedelta(minutes=int(design["minute_innovation"]["event_merge_minutes"])),
        ),
        (
            "hourly_glr",
            "hourly_baseline",
            pd.Timedelta(hours=int(design["hourly_innovation"]["event_merge_hours"])),
        ),
    ]
    for challenger_name, baseline_name, merge_gap in definitions:
        is_minute = challenger_name.startswith("minute")
        source = tracks[challenger_name]
        eligibility: dict[str, pd.Series] = {}
        for sensor, score in source.items():
            if is_minute:
                eligibility[sensor] = _minute_mask(score.index, eligibility_h[sensor]) & score.index.to_series().le(
                    development_end
                ).to_numpy()
            else:
                eligibility[sensor] = eligibility_h[sensor].reindex(score.index).fillna(False) & score.index.to_series().le(
                    development_end
                ).to_numpy()
        target = float(budgets[challenger_name])
        ci_target = float(sap["threshold_selection"]["far_ci95_upper_max"]) / 2.0
        for role, track_name in [("challenger", challenger_name), ("baseline_fixed_far", baseline_name)]:
            selection = calibrate_event_threshold(
                tracks[track_name],
                eligibility,
                merge_gap=merge_gap,
                target_far=target,
                far_ci_high_max=ci_target,
            )
            audit = selection.pop("audit")
            results[f"{challenger_name}:{role}"] = {**selection, "merge_gap": str(merge_gap)}
            for row in audit:
                records.append({"track": challenger_name, "role": role, **row})
    return results, pd.DataFrame(records)


def _lhs_values(count: int, low: float, high: float, seed: int) -> np.ndarray:
    sample = qmc.LatinHypercube(d=1, seed=seed).random(count).ravel()
    return low + sample * (high - low)


def _separated_candidates(
    candidates: pd.DatetimeIndex,
    used: list[pd.Timestamp],
    minimum_separation: pd.Timedelta,
) -> pd.DatetimeIndex:
    available = candidates
    for previous in used:
        available = available[np.abs(available - previous) >= minimum_separation]
    return available


def _trial_schedule(
    state: dict[str, Any],
    eligibility_h: dict[str, pd.Series],
    mechanism: dict[str, Any],
    design: dict[str, Any],
    sap: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(int(sap["random_seed"]))
    validation_end = pd.Timestamp(sap["chronological_split"]["internal_validation_end"])
    shadow_start = pd.Timestamp(sap["chronological_split"]["shadow_start"])
    development_end = pd.Timestamp(sap["chronological_split"]["development_end"])
    all_end = state["D1_v11"].index.max()
    exclusions: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    minimum_separation = pd.Timedelta(
        hours=float(design["base_window"]["minimum_onset_separation_hours_same_sensor"])
    )
    n_val = int(design["trial_split"]["internal_validation"])
    n_shadow = int(design["trial_split"]["terminal_shadow"])
    excluded_step = set(mechanism["excluded_from_ordinary_step"]["sensors"])
    for mechanism_index, (name, contract) in enumerate(mechanism["mechanisms"].items()):
        used_onsets: dict[str, list[pd.Timestamp]] = {
            sensor: [] for sensor in state["D1_v11"].columns
        }
        assignment_counts: dict[str, int] = {
            sensor: 0 for sensor in state["D1_v11"].columns
        }
        track = contract["detector_track"]
        sensors = list(state["D1_v11"].columns)
        if track.startswith("hourly"):
            sensors = [sensor for sensor in sensors if sensor not in excluded_step]
        for phase, count, start, end in [
            ("internal_validation", n_val, development_end + pd.Timedelta(seconds=1), validation_end),
            ("terminal_shadow", n_shadow, shadow_start, all_end),
        ]:
            if "duration_minutes" in contract:
                duration_low, duration_high = contract["duration_minutes"]
                durations = np.maximum(1, np.rint(_lhs_values(count, duration_low, duration_high, 10_000 + mechanism_index * 10 + (phase == "terminal_shadow"))).astype(int))
                unit = "minute"
            else:
                duration_low, duration_high = contract["duration_hours"]
                durations = np.maximum(1, np.rint(_lhs_values(count, duration_low, duration_high, 20_000 + mechanism_index * 10 + (phase == "terminal_shadow"))).astype(int))
                unit = "hour"
            amp_low, amp_high = contract["amplitude_sigma"]
            amplitudes = _lhs_values(count, amp_low, amp_high, 30_000 + mechanism_index * 10 + (phase == "terminal_shadow"))
            eligible_sensors = []
            candidates: dict[str, pd.DatetimeIndex] = {}
            for sensor in sensors:
                mask = eligibility_h[sensor].loc[start:end]
                candidate = mask.index[mask]
                if unit == "minute":
                    candidate = candidate + pd.Timedelta(minutes=30)
                    candidate = candidate[
                        (candidate >= start + pd.Timedelta(hours=30))
                        & (candidate <= end - pd.Timedelta(hours=1))
                    ]
                else:
                    candidate = candidate[
                        (candidate >= start + pd.Timedelta(hours=84))
                        & (candidate <= end - pd.Timedelta(hours=84))
                    ]
                if len(candidate):
                    eligible_sensors.append(sensor)
                    candidates[sensor] = candidate
                else:
                    exclusions.append(
                        {
                            "mechanism": name,
                            "phase": phase,
                            "sensor_id": sensor,
                            "reason": "no_eligible_onset",
                        }
                    )
            if not eligible_sensors:
                raise RuntimeError(f"No eligible onsets for {name} in {phase}")
            analyte_groups = {
                analyte: [sensor for sensor in eligible_sensors if sensor.startswith(analyte)]
                for analyte in ("DO", "ORP")
            }
            for trial_index in range(count):
                analyte = ("DO", "ORP")[trial_index % 2]
                available: dict[str, pd.DatetimeIndex] = {}
                for sensor in analyte_groups[analyte]:
                    candidate = _separated_candidates(
                        candidates[sensor], used_onsets[sensor], minimum_separation
                    )
                    if len(candidate):
                        available[sensor] = candidate
                if not available:
                    raise RuntimeError(
                        f"No {analyte} onset remains after the 24 h separation contract "
                        f"for {name} in {phase}"
                    )
                minimum_count = min(assignment_counts[sensor] for sensor in available)
                sensor_pool = sorted(
                    sensor
                    for sensor in available
                    if assignment_counts[sensor] == minimum_count
                )
                sensor = str(rng.choice(sensor_pool))
                onset = pd.Timestamp(rng.choice(available[sensor].to_numpy()))
                used_onsets[sensor].append(onset)
                assignment_counts[sensor] += 1
                duration = int(durations[trial_index])
                amplitude = float(amplitudes[trial_index])
                primary = amplitude >= float(contract["primary_region"]["amplitude_sigma_min"])
                if name == "short_burst":
                    primary &= duration >= int(contract["primary_region"]["duration_minutes_min"])
                if name == "temporary_shift":
                    primary &= duration >= int(contract["primary_region"]["duration_hours_min"])
                rows.append(
                    {
                        "trial_id": f"{name}-{phase[:1]}-{trial_index + 1:03d}",
                        "mechanism": name,
                        "phase": phase,
                        "sensor_id": sensor,
                        "analyte": sensor.split("_")[0],
                        "scoring_route": state["scoring_mode"][sensor],
                        "onset": onset,
                        "duration": duration,
                        "duration_unit": unit,
                        "amplitude_sigma": amplitude,
                        "direction": 1 if trial_index % 2 == 0 else -1,
                        "primary_region": bool(primary),
                        "base_block": f"{sensor}:{onset.floor('7D').date()}",
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(exclusions)


def _quantize(series: pd.Series, resolution: float) -> pd.Series:
    if not np.isfinite(resolution) or resolution <= 0:
        return series
    return (series / resolution).round() * resolution


def _baseline_step_score(
    series: pd.Series,
    *,
    neff_ratio: float,
) -> pd.Series:
    d1_root = Path(__file__).resolve().parents[2]
    mapping = _load_yaml(d1_root / "configs" / "mapping.yaml")["step"]
    q_values: list[pd.Series] = []
    for window in (24, 36):
        raw = _adjacent_ks_score(series, window=window, neff_ratio=neff_ratio)
        q_values.append(
            _logistic_quality(
                raw.fillna(0.08), float(mapping["k"]), float(mapping["x0"])
            )
        )
    q24, q36 = q_values
    final = q24.copy()
    mask = q24.le(2.5)
    final.loc[mask] = pd.concat([q24.loc[mask], q36.loc[mask]], axis=1).max(axis=1)
    return 5.0 - final.clip(1.0, 5.0)


def _evaluate_minute_trial(
    row: pd.Series,
    df_min: pd.DataFrame,
    design: dict[str, Any],
    thresholds: dict[str, dict[str, Any]],
    resolution_mode: str,
    frozen_parameters: dict[str, float],
) -> dict[str, Any]:
    onset = pd.Timestamp(row["onset"])
    duration = int(row["duration"])
    start = onset - pd.Timedelta(hours=30)
    end = onset + pd.Timedelta(minutes=duration + 20)
    raw = df_min.loc[start:end, row["sensor_id"]].copy()
    pre = raw.loc[onset - pd.Timedelta(hours=24): onset - pd.Timedelta(minutes=1)]
    scale = robust_scale(pre)
    resolution = float(frozen_parameters["resolution"])
    if not np.isfinite(scale):
        return {"evaluable": False, "exclusion_reason": "nonfinite_local_scale"}
    event_end = onset + pd.Timedelta(minutes=duration - 1)
    injected = raw.copy()
    injected.loc[onset:event_end] += float(row["direction"]) * float(row["amplitude_sigma"]) * scale
    if resolution_mode == "2x_resolution":
        injected = _quantize(injected, 2.0 * resolution)
    cfg = design["minute_innovation"]
    innovation = minute_causal_innovation(
        injected,
        location_window=int(cfg["location_window_minutes"]),
        scale_window=int(cfg["scale_window_minutes"]),
        guard=int(cfg["guard_minutes"]),
        min_location=int(cfg["minimum_location_observations"]),
        min_scale=int(cfg["minimum_scale_observations"]),
        resolution_floor_multiplier=float(cfg["resolution_floor_multiplier"]),
        fixed_resolution=resolution,
        fixed_scale_floor=float(frozen_parameters["scale_floor"]),
    )["innovation"]
    challenger = multiscale_glr(innovation, cfg["glr_scales_minutes"])["glr_score"]
    baseline = _hampel_score(injected.rename(row["sensor_id"]))
    evaluation_end = event_end + pd.Timedelta(minutes=5 if row["mechanism"] == "short_burst" else 1)
    window = slice(onset, evaluation_end)
    challenger_alarm = challenger.loc[window].ge(thresholds["minute_glr:challenger"]["threshold"])
    baseline_alarm = baseline.loc[window].ge(thresholds["minute_glr:baseline_fixed_far"]["threshold"])
    release_alarm = baseline.loc[window].gt(3.0)
    first = challenger_alarm.index[challenger_alarm][0] if challenger_alarm.any() else pd.NaT
    return {
        "evaluable": True,
        "exclusion_reason": "",
        "injection_domain": "raw_minute_measurement",
        "resolution_mode": resolution_mode,
        "local_scale": scale,
        "empirical_resolution": resolution,
        "challenger_detected": bool(challenger_alarm.any()),
        "baseline_fixed_far_detected": bool(baseline_alarm.any()),
        "baseline_release_detected": bool(release_alarm.any()),
        "challenger_delay_minutes": (first - onset).total_seconds() / 60.0 if pd.notna(first) else np.nan,
        "challenger_max_score": float(challenger.loc[window].max()),
        "baseline_max_score": float(baseline.loc[window].max()),
    }


def _evaluate_hourly_trial(
    row: pd.Series,
    state: dict[str, Any],
    model: AR1InnovationModel,
    design: dict[str, Any],
    thresholds: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    onset = pd.Timestamp(row["onset"]).floor("h")
    duration = int(row["duration"])
    start = onset - pd.Timedelta(hours=84)
    end = onset + pd.Timedelta(hours=duration + 84)
    sensor = row["sensor_id"]
    route = state["whitened_input_h"].loc[start:end, sensor].copy()
    local_route_scale = robust_scale(route.loc[onset - pd.Timedelta(hours=72): onset - pd.Timedelta(hours=1)])
    if not np.isfinite(local_route_scale):
        return {"evaluable": False, "exclusion_reason": "nonfinite_local_route_scale"}
    event_end = onset + pd.Timedelta(hours=duration - 1)
    injected = route.copy()
    injected.loc[onset:event_end] += float(row["direction"]) * float(row["amplitude_sigma"]) * local_route_scale
    innovation = model.transform(injected)
    challenger = multiscale_glr(innovation, design["hourly_innovation"]["glr_scales_hours"])["glr_score"]
    baseline = _baseline_step_score(injected.rename(sensor), neff_ratio=float(state["eff_neff"].get(sensor, 1.0)))
    evaluation_end = onset + pd.Timedelta(hours=3)
    challenger_alarm = challenger.loc[onset:evaluation_end].ge(thresholds["hourly_glr:challenger"]["threshold"])
    baseline_alarm = baseline.loc[onset:evaluation_end].ge(thresholds["hourly_glr:baseline_fixed_far"]["threshold"])
    release_alarm = baseline.loc[onset:evaluation_end].ge(2.5)
    first = challenger_alarm.index[challenger_alarm][0] if challenger_alarm.any() else pd.NaT
    persistence_confirmed = bool(baseline.loc[onset:end].ge(3.0).any()) if row["mechanism"] == "persistent_step" else np.nan
    return {
        "evaluable": True,
        "exclusion_reason": "",
        "injection_domain": "frozen_hourly_route_input",
        "resolution_mode": "original_resolution",
        "local_scale": local_route_scale,
        "empirical_resolution": np.nan,
        "challenger_detected": bool(challenger_alarm.any()),
        "baseline_fixed_far_detected": bool(baseline_alarm.any()),
        "baseline_release_detected": bool(release_alarm.any()),
        "challenger_delay_minutes": (first - onset).total_seconds() / 60.0 if pd.notna(first) else np.nan,
        "challenger_max_score": float(challenger.loc[onset:evaluation_end].max()),
        "baseline_max_score": float(baseline.loc[onset:evaluation_end].max()),
        "persistence_confirmed_by_released_ks": persistence_confirmed,
    }


def evaluate_trials(
    schedule: pd.DataFrame,
    df_min: pd.DataFrame,
    state: dict[str, Any],
    models: dict[str, AR1InnovationModel],
    minute_parameters: dict[str, dict[str, float]],
    design: dict[str, Any],
    thresholds: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, trial in schedule.iterrows():
        if trial["duration_unit"] == "minute":
            modes = ("original_resolution", "2x_resolution")
            for mode in modes:
                result = _evaluate_minute_trial(
                    trial,
                    df_min,
                    design,
                    thresholds,
                    mode,
                    minute_parameters[trial["sensor_id"]],
                )
                rows.append({**trial.to_dict(), **result})
        else:
            result = _evaluate_hourly_trial(trial, state, models[trial["sensor_id"]], design, thresholds)
            rows.append({**trial.to_dict(), **result})
    return pd.DataFrame(rows)


def _cluster_bootstrap_metrics(
    frame: pd.DataFrame,
    *,
    repetitions: int,
    seed: int,
) -> dict[str, float]:
    evaluable = frame.loc[frame["evaluable"]].copy()
    if evaluable.empty:
        return {"n_trials": 0, "n_clusters": 0}
    clusters = evaluable["base_block"].drop_duplicates().to_numpy()
    rng = np.random.default_rng(seed)
    estimates = np.empty((repetitions, 3), dtype=float)
    for index in range(repetitions):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        bootstrap = pd.concat([evaluable.loc[evaluable["base_block"].eq(cluster)] for cluster in sampled], ignore_index=True)
        challenger = bootstrap["challenger_detected"].mean()
        baseline = bootstrap["baseline_fixed_far_detected"].mean()
        estimates[index] = challenger, baseline, challenger - baseline
    point_challenger = float(evaluable["challenger_detected"].mean())
    point_baseline = float(evaluable["baseline_fixed_far_detected"].mean())
    return {
        "n_trials": int(len(evaluable)),
        "n_clusters": int(len(clusters)),
        "challenger_recall": point_challenger,
        "challenger_ci95_low": float(np.quantile(estimates[:, 0], 0.025)),
        "challenger_ci95_high": float(np.quantile(estimates[:, 0], 0.975)),
        "baseline_fixed_far_recall": point_baseline,
        "baseline_ci95_low": float(np.quantile(estimates[:, 1], 0.025)),
        "baseline_ci95_high": float(np.quantile(estimates[:, 1], 0.975)),
        "recall_delta": point_challenger - point_baseline,
        "delta_ci95_low": float(np.quantile(estimates[:, 2], 0.025)),
        "delta_ci95_high": float(np.quantile(estimates[:, 2], 0.975)),
        "released_recall": float(evaluable["baseline_release_detected"].mean()),
        "median_detection_delay_minutes": float(evaluable["challenger_delay_minutes"].median()),
    }


def summarize_trials(trials: pd.DataFrame, sap: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    groups = ["mechanism", "phase", "resolution_mode", "primary_region"]
    for keys, frame in trials.groupby(groups, dropna=False):
        metrics = _cluster_bootstrap_metrics(
            frame,
            repetitions=int(sap["inference"]["bootstrap_repetitions"]),
            seed=int(sap["random_seed"]) + len(rows),
        )
        rows.append({**dict(zip(groups, keys)), **metrics})
    return pd.DataFrame(rows)


def build_applicability_surface(trials: pd.DataFrame, minimum_clusters: int) -> pd.DataFrame:
    def bin_edges(values: pd.Series) -> np.ndarray:
        unique = np.sort(values.dropna().unique())
        if len(unique) == 1:
            padding = max(abs(float(unique[0])) * 0.01, 0.5)
            return np.array([float(unique[0]) - padding, float(unique[0]) + padding])
        return np.unique(np.quantile(values, np.linspace(0, 1, 4)))

    rows: list[dict[str, Any]] = []
    original = trials.loc[trials["resolution_mode"].eq("original_resolution") & trials["evaluable"]].copy()
    for (mechanism, analyte), frame in original.groupby(["mechanism", "analyte"]):
        amp_edges = bin_edges(frame["amplitude_sigma"])
        duration_edges = bin_edges(frame["duration"])
        if len(amp_edges) < 2 or len(duration_edges) < 2:
            continue
        frame["amplitude_bin"] = pd.cut(frame["amplitude_sigma"], amp_edges, include_lowest=True, duplicates="drop")
        frame["duration_bin"] = pd.cut(frame["duration"], duration_edges, include_lowest=True, duplicates="drop")
        for (amp_bin, duration_bin), cell in frame.groupby(["amplitude_bin", "duration_bin"], observed=True):
            n_clusters = cell["base_block"].nunique()
            rows.append(
                {
                    "mechanism": mechanism,
                    "analyte": analyte,
                    "amplitude_bin": str(amp_bin),
                    "amplitude_mid": float(amp_bin.mid),
                    "duration_bin": str(duration_bin),
                    "duration_mid": float(duration_bin.mid),
                    "n_trials": int(len(cell)),
                    "n_clusters": int(n_clusters),
                    "recall": float(cell["challenger_detected"].mean()) if n_clusters >= minimum_clusters else np.nan,
                    "meets_0_80": bool(cell["challenger_detected"].mean() >= 0.8) if n_clusters >= minimum_clusters else False,
                    "sparse": bool(n_clusters < minimum_clusters),
                }
            )
    return pd.DataFrame(rows)


def _shadow_events(
    tracks: dict[str, dict[str, pd.Series]],
    eligibility_h: dict[str, pd.Series],
    thresholds: dict[str, dict[str, Any]],
    sap: dict[str, Any],
    design: dict[str, Any],
) -> pd.DataFrame:
    start = pd.Timestamp(sap["chronological_split"]["shadow_start"])
    rows: list[pd.DataFrame] = []
    for track, merge_gap in [
        ("minute_glr", pd.Timedelta(minutes=int(design["minute_innovation"]["event_merge_minutes"]))),
        ("hourly_glr", pd.Timedelta(hours=int(design["hourly_innovation"]["event_merge_hours"]))),
    ]:
        for sensor, score in tracks[track].items():
            eligible = _minute_mask(score.index, eligibility_h[sensor]) if track == "minute_glr" else eligibility_h[sensor].reindex(score.index).fillna(False)
            eligible &= score.index.to_series().ge(start).to_numpy()
            events = extract_events(
                score,
                threshold=float(thresholds[f"{track}:challenger"]["threshold"]),
                eligible=eligible,
                merge_gap=merge_gap,
            )
            if len(events):
                events.insert(0, "sensor_id", sensor)
                events.insert(1, "track", track)
                events["analyte"] = sensor.split("_")[0]
                events["status"] = "shadow_unadjudicated"
                rows.append(events)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["sensor_id", "track", "onset", "end", "detection_time", "max_score", "analyte", "status"]
    )


def run(project_root: Path, output_dir: Path) -> dict[str, Any]:
    challenger_root = Path(__file__).resolve().parents[1]
    d1_root = challenger_root.parent
    configs = challenger_root / "configs"
    sap = _load_yaml(configs / "challenger_sap.yaml")
    design = _load_yaml(configs / "validation_design.yaml")
    mechanism = _load_yaml(configs / "mechanism_contract.yaml")
    with (d1_root / "v11_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    with (d1_root / "cache" / "df_min_aligned.pkl").open("rb") as handle:
        df_min = pickle.load(handle)
    eligibility_h = build_hourly_eligibility(state)
    development_end = pd.Timestamp(sap["chronological_split"]["development_end"])
    tracks, models, minute_parameters, model_registry = _score_tracks(
        df_min, state, eligibility_h, development_end, design
    )
    thresholds, threshold_audit = _calibrate_tracks(
        tracks, eligibility_h, df_min, development_end, sap, design
    )
    schedule, exclusions = _trial_schedule(state, eligibility_h, mechanism, design, sap)
    trials = evaluate_trials(
        schedule,
        df_min,
        state,
        models,
        minute_parameters,
        design,
        thresholds,
    )
    validation = summarize_trials(trials, sap)
    surface = build_applicability_surface(trials, int(sap["reporting"]["sparse_cell_min_clusters"]))
    shadow = _shadow_events(tracks, eligibility_h, thresholds, sap, design)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    tables = {
        "D1_challenger_trials.parquet": trials,
        "D1_challenger_validation.parquet": validation,
        "D1_challenger_threshold_audit.parquet": threshold_audit,
        "D1_challenger_shadow_events.parquet": shadow,
        "D1_challenger_exclusions.parquet": pd.concat([exclusions, trials.loc[~trials["evaluable"], ["mechanism", "phase", "sensor_id", "exclusion_reason"]].rename(columns={"exclusion_reason": "reason"})], ignore_index=True),
        "D1_challenger_model_registry.parquet": model_registry,
        "D1_challenger_applicability_surface.parquet": surface,
    }
    for filename, frame in tables.items():
        frame.to_parquet(data_dir / filename, index=False)
    with pd.ExcelWriter(data_dir / "D1_challenger_source_data.xlsx", engine="openpyxl") as writer:
        validation.to_excel(writer, sheet_name="validation", index=False)
        surface.to_excel(writer, sheet_name="applicability", index=False)
        shadow.to_excel(writer, sheet_name="shadow_events", index=False)
        model_registry.to_excel(writer, sheet_name="model_registry", index=False)
        pd.DataFrame([{key: value for key, value in payload.items() if key != "merge_gap"} | {"threshold_id": key} for key, payload in thresholds.items()]).to_excel(writer, sheet_name="thresholds", index=False)
    _atomic_write_json(data_dir / "D1_challenger_thresholds.json", thresholds)
    input_hashes = {
        str(path.relative_to(project_root)): _sha256(path)
        for path in [d1_root / "v11_state.pkl", d1_root / "cache" / "df_min_aligned.pkl"]
    }
    manifest = {
        "schema_version": "d1-challenger-run-v1.1",
        "scientific_status": sap["scientific_status"],
        "production_release_modified": False,
        "D1_D5_aggregation_inputs_modified": False,
        "random_seed": sap["random_seed"],
        "thresholds": thresholds,
        "input_sha256": input_hashes,
        "outputs": {},
    }
    for path in sorted(data_dir.iterdir()):
        manifest["outputs"][path.name] = _sha256(path)
    _atomic_write_json(output_dir / "run_manifest.json", manifest)
    return {
        "sap": sap,
        "design": design,
        "mechanism": mechanism,
        "thresholds": thresholds,
        "trials": trials,
        "validation": validation,
        "surface": surface,
        "shadow": shadow,
        "model_registry": model_registry,
        "output_dir": output_dir,
    }
