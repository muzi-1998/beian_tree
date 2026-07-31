from __future__ import annotations

import json
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import qmc
from sklearn.metrics import average_precision_score, roc_auc_score

from .common import (
    CONFIG_ROOT,
    PROJECT_ROOT,
    cluster_bootstrap_proportion,
    expand_window_end_gate,
    read_yaml,
    sha256_file,
    wilson_interval,
)


D1_ROOT = PROJECT_ROOT / "D1 Sensor health"


def _load_d1_api():
    import src

    d1_source = str(D1_ROOT / "src")
    if d1_source not in src.__path__:
        src.__path__.append(d1_source)
    from src.calibration.step_injection import confirmation_gate, logistic_quality
    from src.detectors.drift_pls import PLSVirtualSensorDetector
    from src.detectors.spike_hampel import HampelSpikeDetector
    from src.detectors.step_adjacent_ks import AdjacentKSStepDetector

    return (
        confirmation_gate,
        logistic_quality,
        PLSVirtualSensorDetector,
        HampelSpikeDetector,
        AdjacentKSStepDetector,
    )


def _load_decomposition_api():
    source_root = PROJECT_ROOT / "1.1 Decomposition" / "src"
    import src

    if str(source_root) not in src.__path__:
        src.__path__.append(str(source_root))
    from src.whiten.model_selection import select_model
    from src.whiten.online_whitener import whiten_series

    return select_model, whiten_series


def _robust_scale(values: pd.Series) -> float:
    finite = values.dropna().to_numpy(dtype=float)
    if not len(finite):
        return np.nan
    median = float(np.median(finite))
    scale = 1.4826 * float(np.median(np.abs(finite - median)))
    if not np.isfinite(scale) or scale <= 1e-9:
        scale = float(np.std(finite))
    return max(scale, 1e-9)


def _consecutive_alarm(values: np.ndarray, duration: int) -> tuple[bool, float]:
    active = np.asarray(values, dtype=bool)
    if len(active) < duration:
        return False, np.nan
    run = np.convolve(active.astype(int), np.ones(duration, dtype=int), mode="valid")
    hits = np.flatnonzero(run >= duration)
    return bool(len(hits)), float(hits[0]) if len(hits) else np.nan


def _quantize(series: pd.Series, step: float | None) -> pd.Series:
    if step is None or not np.isfinite(step) or step <= 0:
        return series
    return (series / step).round() * step


def _empirical_resolution(series: pd.Series) -> float:
    values = np.sort(series.dropna().unique().astype(float))
    if len(values) < 2:
        return np.nan
    increments = np.diff(values)
    increments = increments[increments > 1e-12]
    return float(np.quantile(increments, 0.10)) if len(increments) else np.nan


def _finite_max(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(finite.max()) if len(finite) else np.nan


def _finite_min(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(finite.min()) if len(finite) else np.nan


def _finite_median(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(np.median(finite)) if len(finite) else np.nan


def _prepare_clean_hours(
    state: dict,
    d2_state: dict,
    d3_gate: pd.DataFrame,
) -> dict[str, pd.DatetimeIndex]:
    d3 = expand_window_end_gate(d3_gate)
    fail = {
        sensor: set(frame.loc[frame["D3_gate_status"].eq("Fail"), "timestamp"])
        for sensor, frame in d3.groupby("sensor_id")
    }
    clean: dict[str, pd.DatetimeIndex] = {}
    for sensor in state["scored_channels"]:
        d1 = state["D1_v11"][sensor]
        d2 = d2_state["all_D2"][sensor]["usable_tag"].reindex(d1.index)
        mask = d1.ge(4.5) & d2.eq("train_ok")
        mask &= d1.index >= pd.Timestamp("2025-11-01")
        mask &= d1.index <= pd.Timestamp("2026-04-06")
        if sensor in fail:
            mask &= ~pd.Series(d1.index.isin(fail[sensor]), index=d1.index)
        clean[sensor] = pd.DatetimeIndex(d1.index[mask])
    return clean


def _pick_onsets(
    clean: dict[str, pd.DatetimeIndex],
    state: dict,
    *,
    analyte: str,
    n: int,
    rng: np.random.Generator,
) -> list[tuple[str, pd.Timestamp, int]]:
    sensors = [sensor for sensor in state["scored_channels"] if sensor.startswith(analyte)]
    choices = []
    for sensor in sensors:
        index = clean[sensor]
        for timestamp in index[::24]:
            regime = int(state["regime_labels"].reindex([timestamp]).iloc[0])
            choices.append((sensor, pd.Timestamp(timestamp), regime))
    if not choices:
        raise RuntimeError(f"No clean D1 validation hours are available for {analyte}")
    selected = rng.integers(0, len(choices), size=n)
    return [choices[index] for index in selected]


def _fit_pls_models(state: dict) -> tuple[dict[str, object], dict[str, list[str]]]:
    _, _, PLSVirtualSensorDetector, _, _ = _load_d1_api()
    audit = state["detectors_raw"]["pls_peer_selection_audit"].copy()
    models = {}
    peers: dict[str, list[str]] = {}
    for sensor in state["scored_channels"]:
        raw = audit.loc[sensor, "selected_peers"]
        selected = [value for value in str(raw).split(";") if value]
        detector = PLSVirtualSensorDetector(
            n_components=int(audit.loc[sensor, "selected_n_components"]),
            train_days=21,
        )
        detector.fit(state["df_h"], target=sensor, peer_cols=selected)
        models[sensor] = detector
        peers[sensor] = selected
    return models, peers


def _pls_z(detector, frame: pd.DataFrame, target: str) -> np.ndarray:
    model, sx, sy, sigma_residual, medians, peers, _ = detector._models[target]
    prepared = frame.loc[:, [target, *peers]].copy().ffill().fillna(medians).fillna(0.0)
    prediction_s = model.predict(sx.transform(prepared[peers].to_numpy(dtype=float))).ravel()
    prediction = sy.inverse_transform(prediction_s.reshape(-1, 1)).ravel()
    return np.abs(prepared[target].to_numpy(dtype=float) - prediction) / sigma_residual


def _spike_trial(
    residual: pd.Series,
    onset: pd.Timestamp,
    amplitude: float,
    duration_min: int,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float]:
    _, _, _, HampelSpikeDetector, _ = _load_d1_api()
    start = onset - pd.Timedelta(minutes=90)
    end = onset + pd.Timedelta(minutes=duration_min + 90)
    blank = residual.loc[start:end].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(minutes=1)])
    blank = _quantize(blank, resolution_step)
    injected = blank.copy()
    event_end = onset + pd.Timedelta(minutes=duration_min - 1)
    injected.loc[onset:event_end] += direction * amplitude * scale
    injected = _quantize(injected, resolution_step)
    detector = HampelSpikeDetector(window_min=21, k=3.0)
    blank_score = detector.score(blank.rename(residual.name)).raw_score
    injected_score = detector.score(injected.rename(residual.name)).raw_score
    evaluation_end = event_end + pd.Timedelta(minutes=10)
    blank_eval = blank_score.loc[onset:evaluation_end]
    injected_eval = injected_score.loc[onset:evaluation_end]
    hits = np.flatnonzero(injected_eval.to_numpy(dtype=float) > 3.0)
    delay = float(hits[0]) if len(hits) else np.nan
    return (
        _finite_max(blank_eval),
        _finite_max(injected_eval),
        bool((blank_eval > 3.0).any()),
        bool((injected_eval > 3.0).any()),
        delay,
    )


def _step_quality(
    series: pd.Series,
    *,
    neff_ratio: float,
    mapping: dict,
) -> pd.Series:
    confirmation_gate, logistic_quality, _, _, AdjacentKSStepDetector = _load_d1_api()
    q24 = logistic_quality(
        AdjacentKSStepDetector(24, 0.001, neff_ratio).score(series).raw_score,
        float(mapping["k"]),
        float(mapping["x0"]),
    )
    q36 = logistic_quality(
        AdjacentKSStepDetector(36, 0.001, neff_ratio).score(series).raw_score,
        float(mapping["k"]),
        float(mapping["x0"]),
    )
    return pd.Series(confirmation_gate(q24, q36), index=series.index)


def _step_pair_metrics(
    blank: pd.Series,
    injected: pd.Series,
    *,
    onset: pd.Timestamp,
    event_end: pd.Timestamp,
    neff_ratio: float,
    mapping: dict,
) -> tuple[float, float, bool, bool, float]:
    blank_q = _step_quality(blank, neff_ratio=neff_ratio, mapping=mapping)
    injected_q = _step_quality(injected, neff_ratio=neff_ratio, mapping=mapping)
    evaluation_end = event_end + pd.Timedelta(hours=48)
    blank_eval = blank_q.loc[onset:evaluation_end]
    injected_eval = injected_q.loc[onset:evaluation_end]
    hits = np.flatnonzero(injected_eval.to_numpy(dtype=float) <= 2.5)
    return (
        float(5.0 - _finite_min(blank_eval)),
        float(5.0 - _finite_min(injected_eval)),
        bool((blank_eval <= 2.5).any()),
        bool((injected_eval <= 2.5).any()),
        float(hits[0]) if len(hits) else np.nan,
    )


def _step_trial(
    routed: pd.Series,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    neff_ratio: float,
    mapping: dict,
    degraded_resolution: bool,
) -> tuple[float, float, bool, bool, float]:
    start = onset - pd.Timedelta(hours=72)
    end = onset + pd.Timedelta(hours=max(72, int(np.ceil(duration_h)) + 48))
    blank = routed.loc[start:end].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(hours=1)])
    resolution_step = _empirical_resolution(blank) * 2.0 if degraded_resolution else None
    blank = _quantize(blank, resolution_step)
    injected = blank.copy()
    event_end = onset + pd.Timedelta(hours=max(1, int(np.ceil(duration_h))) - 1)
    injected.loc[onset:event_end] += direction * amplitude * scale
    injected = _quantize(injected, resolution_step)
    return _step_pair_metrics(
        blank,
        injected,
        onset=onset,
        event_end=event_end,
        neff_ratio=neff_ratio,
        mapping=mapping,
    )


def _drift_trial(
    state: dict,
    detector,
    peer_columns: list[str],
    sensor: str,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float, float]:
    hours = max(12, int(np.ceil(duration_h)))
    start = onset - pd.Timedelta(hours=48)
    end = onset + pd.Timedelta(hours=hours + 24)
    blank = state["df_h"].loc[start:end, [sensor, *peer_columns]].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(hours=1), sensor])
    profile = np.linspace(0.0, direction * amplitude * scale, hours)
    event_index = pd.date_range(onset, periods=hours, freq="1h")
    if resolution_step is not None:
        blank.loc[:, sensor] = _quantize(blank[sensor], resolution_step)
    injected = blank.copy()
    injected.loc[event_index, sensor] += profile
    injected.loc[:, sensor] = _quantize(injected[sensor], resolution_step)
    blank_z = _pls_z(detector, blank, sensor)
    injected_z = _pls_z(detector, injected, sensor)
    local_index = blank.index
    evaluation = (local_index >= onset) & (
        local_index <= event_index[-1] + pd.Timedelta(hours=12)
    )
    blank_alarm, _ = _consecutive_alarm(blank_z[evaluation] >= 3.0, 3)
    injected_alarm, delay = _consecutive_alarm(injected_z[evaluation] >= 3.0, 3)

    common = blank.copy()
    common.loc[event_index, sensor] += profile
    common.loc[:, sensor] = _quantize(common[sensor], resolution_step)
    for peer in peer_columns:
        peer_scale = _robust_scale(
            blank.loc[: onset - pd.Timedelta(hours=1), peer]
        )
        peer_profile = np.linspace(
            0.0,
            direction * amplitude * peer_scale,
            hours,
        )
        common.loc[event_index, peer] += peer_profile
    common_z = _pls_z(detector, common, sensor)
    common_alarm, _ = _consecutive_alarm(common_z[evaluation] >= 3.0, 3)
    return (
        _finite_max(blank_z[evaluation]),
        _finite_max(injected_z[evaluation]),
        blank_alarm,
        injected_alarm,
        delay,
        float(common_alarm),
    )


def _freeze_trial(
    raw: pd.Series,
    onset: pd.Timestamp,
    duration_min: int,
    precision: float,
    degraded_resolution: bool,
) -> tuple[float, float, bool, bool, float]:
    start = onset - pd.Timedelta(minutes=60)
    end = onset + pd.Timedelta(minutes=duration_min + 30)
    blank = raw.loc[start:end].copy()
    effective_precision = precision * 2.0 if degraded_resolution else precision
    blank = _quantize(blank, effective_precision if degraded_resolution else None)
    injected = blank.copy()
    event_index = pd.date_range(onset, periods=duration_min, freq="1min")
    injected.loc[event_index] = float(blank.loc[: onset - pd.Timedelta(minutes=1)].iloc[-1])

    def run_lengths(series: pd.Series) -> pd.Series:
        equal = series.diff().abs().le(max(effective_precision * 0.25, 1e-9)).fillna(False)
        groups = (~equal).cumsum()
        return equal.groupby(groups).cumsum()

    blank_run = run_lengths(blank).loc[event_index]
    injected_run = run_lengths(injected).loc[event_index]
    blank_alarm = bool(blank_run.ge(15).any())
    injected_alarm = bool(injected_run.ge(15).any())
    hits = np.flatnonzero(injected_run.to_numpy(dtype=float) >= 15)
    return (
        float(blank_run.max()),
        float(injected_run.max()),
        blank_alarm,
        injected_alarm,
        float(hits[0] + 1) if len(hits) else np.nan,
    )


def _fit_frozen_whiteners(
    decomposition: dict,
    state: dict,
    sensors: list[str],
    *,
    fit_end: pd.Timestamp,
) -> tuple[dict[str, object], pd.DataFrame]:
    select_model, _ = _load_decomposition_api()
    config = yaml.safe_load(
        (
            PROJECT_ROOT / "1.1 Decomposition" / "configs" / "whiten.yaml"
        ).read_text(encoding="utf-8")
    )
    cold_days = int(config["cold_start_reference_days"])
    grid_lags = int(config["ljungbox_lags"]["min"])
    models: dict[str, object] = {}
    rows = []
    for sensor in sorted(set(sensors)):
        mode = str(state["scoring_mode"].get(sensor, "autocorr_aware"))
        if mode != "iid":
            rows.append(
                {
                    "sensor_id": sensor,
                    "scoring_mode": mode,
                    "model_fitted": False,
                    "fit_end": fit_end,
                    "fit_rows": 0,
                    "model_family": "not_required_residual_route",
                    "fit_warning_count": 0,
                    "fit_warning_messages": "",
                }
            )
            continue
        residual = decomposition["resid_min"][sensor].loc[:fit_end].dropna()
        reference = residual.iloc[: cold_days * 1440]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model, selection = select_model(
                reference,
                config,
                version=f"{sensor}_D1V2_frozen_raw_audit",
                track="min",
                lb_lags=grid_lags,
            )
        if model is None:
            raise RuntimeError(
                f"Unable to fit the prespecified frozen whitening route for {sensor}"
            )
        models[sensor] = model
        rows.append(
            {
                "sensor_id": sensor,
                "scoring_mode": mode,
                "model_fitted": True,
                "fit_end": fit_end,
                "fit_rows": len(reference),
                "model_family": selection.get("family", "unknown"),
                "p": selection.get("p_arma"),
                "q": selection.get("q"),
                "d": selection.get("d"),
                "D": selection.get("D"),
                "fractional_d": selection.get("fd"),
                "fit_warning_count": len(caught),
                "fit_warning_messages": " | ".join(
                    sorted({str(item.message) for item in caught})
                ),
            }
        )
    return models, pd.DataFrame(rows)


def _raw_spike_trial(
    raw: pd.Series,
    trend: pd.Series,
    seasonal: pd.Series,
    onset: pd.Timestamp,
    amplitude: float,
    duration_min: int,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float]:
    _, _, _, HampelSpikeDetector, _ = _load_d1_api()
    start = onset - pd.Timedelta(minutes=90)
    end = onset + pd.Timedelta(minutes=duration_min + 90)
    blank_raw = _quantize(raw.loc[start:end].copy(), resolution_step)
    frozen_baseline = trend.reindex(blank_raw.index) + seasonal.reindex(blank_raw.index)
    blank = blank_raw - frozen_baseline
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(minutes=1)])
    injected_raw = blank_raw.copy()
    event_end = onset + pd.Timedelta(minutes=duration_min - 1)
    injected_raw.loc[onset:event_end] += direction * amplitude * scale
    injected_raw = _quantize(injected_raw, resolution_step)
    injected = injected_raw - frozen_baseline
    detector = HampelSpikeDetector(window_min=21, k=3.0)
    blank_score = detector.score(blank.rename(raw.name)).raw_score
    injected_score = detector.score(injected.rename(raw.name)).raw_score
    evaluation_end = event_end + pd.Timedelta(minutes=10)
    blank_eval = blank_score.loc[onset:evaluation_end]
    injected_eval = injected_score.loc[onset:evaluation_end]
    hits = np.flatnonzero(injected_eval.to_numpy(dtype=float) > 3.0)
    return (
        _finite_max(blank_eval),
        _finite_max(injected_eval),
        bool((blank_eval > 3.0).any()),
        bool((injected_eval > 3.0).any()),
        float(hits[0]) if len(hits) else np.nan,
    )


def _raw_step_trial(
    raw: pd.Series,
    trend: pd.Series,
    seasonal: pd.Series,
    model: object | None,
    *,
    scoring_mode: str,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    neff_ratio: float,
    mapping: dict,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float]:
    _, whiten_series = _load_decomposition_api()
    event_hours = max(1, int(np.ceil(duration_h)))
    start = onset - pd.Timedelta(days=7)
    end = onset + pd.Timedelta(hours=event_hours + 48)
    blank_raw = _quantize(raw.loc[start:end].copy(), resolution_step)
    frozen_baseline = trend.reindex(blank_raw.index) + seasonal.reindex(blank_raw.index)
    blank_residual = blank_raw - frozen_baseline
    scale = _robust_scale(blank_residual.loc[: onset - pd.Timedelta(minutes=1)])
    injected_raw = blank_raw.copy()
    event_end_min = onset + pd.Timedelta(hours=event_hours) - pd.Timedelta(minutes=1)
    injected_raw.loc[onset:event_end_min] += direction * amplitude * scale
    injected_raw = _quantize(injected_raw, resolution_step)
    injected_residual = injected_raw - frozen_baseline
    if scoring_mode == "iid":
        if model is None:
            return (np.nan, np.nan, False, False, np.nan)
        blank_min = whiten_series(blank_residual, model)["std_innovation"]
        injected_min = whiten_series(injected_residual, model)["std_innovation"]
    else:
        blank_min = blank_residual
        injected_min = injected_residual
    blank_hourly = blank_min.resample("1h").mean()
    injected_hourly = injected_min.resample("1h").mean()
    event_end_hour = onset + pd.Timedelta(hours=event_hours - 1)
    return _step_pair_metrics(
        blank_hourly,
        injected_hourly,
        onset=onset,
        event_end=event_end_hour,
        neff_ratio=neff_ratio,
        mapping=mapping,
    )


def _raw_drift_trial(
    raw: pd.Series,
    state: dict,
    detector,
    peer_columns: list[str],
    sensor: str,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float]:
    hours = max(12, int(np.ceil(duration_h)))
    start = onset - pd.Timedelta(hours=48)
    end = onset + pd.Timedelta(hours=hours + 24)
    blank_raw = _quantize(raw.loc[start:end].copy(), resolution_step)
    blank_hourly = blank_raw.resample("1h").mean()
    frame_index = state["df_h"].loc[start:end].index
    blank = state["df_h"].loc[frame_index, [sensor, *peer_columns]].copy()
    blank.loc[:, sensor] = blank_hourly.reindex(frame_index).to_numpy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(hours=1), sensor])
    injected_raw = blank_raw.copy()
    event_index_min = pd.date_range(onset, periods=hours * 60, freq="1min")
    profile = np.linspace(
        0.0,
        direction * amplitude * scale,
        len(event_index_min),
    )
    injected_raw.loc[event_index_min] += profile
    injected_raw = _quantize(injected_raw, resolution_step)
    injected = blank.copy()
    injected.loc[:, sensor] = (
        injected_raw.resample("1h").mean().reindex(frame_index).to_numpy()
    )
    blank_z = _pls_z(detector, blank, sensor)
    injected_z = _pls_z(detector, injected, sensor)
    event_end = onset + pd.Timedelta(hours=hours - 1)
    evaluation = (frame_index >= onset) & (
        frame_index <= event_end + pd.Timedelta(hours=12)
    )
    blank_alarm, _ = _consecutive_alarm(blank_z[evaluation] >= 3.0, 3)
    injected_alarm, delay = _consecutive_alarm(injected_z[evaluation] >= 3.0, 3)
    return (
        _finite_max(blank_z[evaluation]),
        _finite_max(injected_z[evaluation]),
        blank_alarm,
        injected_alarm,
        delay,
    )


def _raw_endpoint_audit(
    trials: pd.DataFrame,
    *,
    raw: pd.DataFrame,
    decomposition: dict,
    decomposition_components: dict,
    state: dict,
    models: dict[str, object],
    peers: dict[str, list[str]],
    sensor_cfg: dict,
    mapping: dict,
    design: dict,
    repetitions: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    audit_design = design["raw_domain_frozen_transform_audit"]
    count = int(audit_design["scenarios_per_fault"])
    selected_frames = []
    original = trials[
        trials["resolution_mode"].eq("original") & trials["valid_evaluation"]
    ]
    for fault, fault_frame in original.groupby("fault_type", sort=False):
        parts = []
        for _, analyte_frame in fault_frame.groupby("analyte", sort=False):
            n = min(count // 2, len(analyte_frame))
            positions = np.linspace(0, len(analyte_frame) - 1, n, dtype=int)
            parts.append(analyte_frame.iloc[positions])
        selected_frames.append(pd.concat(parts, ignore_index=True).iloc[:count])
    selected = pd.concat(selected_frames, ignore_index=True)
    fit_end = pd.Timestamp(audit_design["preprocessing_fit_end"])
    step_iid_sensors = selected.loc[
        selected["fault_type"].eq("step")
        & selected["sensor_id"].map(state["scoring_mode"]).eq("iid"),
        "sensor_id",
    ].unique().tolist()
    frozen_models, model_audit = _fit_frozen_whiteners(
        decomposition,
        state,
        step_iid_sensors,
        fit_end=fit_end,
    )
    rows = []
    for row in selected.itertuples(index=False):
        sensor = row.sensor_id
        resolution_step = None
        if row.fault_type == "spike":
            components = decomposition_components["decomp"][sensor]
            result = _raw_spike_trial(
                raw[sensor],
                components["trend"],
                components["seasonal"],
                pd.Timestamp(row.onset),
                float(row.amplitude_sigma),
                int(row.duration),
                int(row.direction),
                resolution_step,
            )
        elif row.fault_type == "step":
            components = decomposition_components["decomp"][sensor]
            result = _raw_step_trial(
                raw[sensor],
                components["trend"],
                components["seasonal"],
                frozen_models.get(sensor),
                scoring_mode=str(state["scoring_mode"][sensor]),
                onset=pd.Timestamp(row.onset),
                amplitude=float(row.amplitude_sigma),
                duration_h=float(row.duration),
                direction=int(row.direction),
                neff_ratio=float(state["eff_neff"].get(sensor, 1.0)),
                mapping=mapping,
                resolution_step=resolution_step,
            )
        elif row.fault_type == "linear_drift":
            result = _raw_drift_trial(
                raw[sensor],
                state,
                models[sensor],
                peers[sensor],
                sensor,
                pd.Timestamp(row.onset),
                float(row.amplitude_sigma),
                float(row.duration),
                int(row.direction),
                resolution_step,
            )
        else:
            result = _freeze_trial(
                raw[sensor],
                pd.Timestamp(row.onset),
                int(row.duration),
                float(sensor_cfg[sensor]["precision"]),
                False,
            )
        rows.append(
            {
                "source_trial_id": row.trial_id,
                "scenario_id": row.scenario_id,
                "fault_type": row.fault_type,
                "sensor_id": sensor,
                "analyte": row.analyte,
                "route": row.route,
                "base_window_onset": row.base_window_onset,
                "onset": row.onset,
                "amplitude_sigma": row.amplitude_sigma,
                "duration": row.duration,
                "duration_unit": row.duration_unit,
                "route_detected": bool(row.detected),
                "raw_domain_detected": bool(result[3]),
                "blank_statistic": result[0],
                "injected_statistic": result[1],
                "blank_alarm": result[2],
                "detection_delay": result[4],
                "valid_evaluation": bool(
                    np.isfinite(result[0]) and np.isfinite(result[1])
                ),
                "injection_domain": "raw_minute_measurement",
                "transform_policy": (
                    "pre_injection_fitted_or_saved_components_then_frozen"
                ),
                "preprocessing_fit_end": fit_end,
                "refit_on_contaminated_window": False,
                "resolution_mode": "original",
            }
        )
    audit = pd.DataFrame(rows)
    summary_rows = []
    concordance_rows = []
    for fault, frame in audit[audit["valid_evaluation"]].groupby(
        "fault_type", sort=False
    ):
        low, high = cluster_bootstrap_proportion(
            frame,
            outcome_column="raw_domain_detected",
            cluster_columns=["sensor_id", "base_window_onset"],
            repetitions=repetitions,
            rng=rng,
        )
        summary_rows.append(
            {
                "fault_type": fault,
                "n_scenarios": len(frame),
                "raw_domain_recall": float(frame["raw_domain_detected"].mean()),
                "recall_ci_low": low,
                "recall_ci_high": high,
                "route_level_recall_same_scenarios": float(
                    frame["route_detected"].mean()
                ),
                "detection_agreement": float(
                    frame["raw_domain_detected"].eq(frame["route_detected"]).mean()
                ),
                "analysis_unit": "sensor_onset_cluster",
            }
        )
        for keys, group in frame.groupby(["analyte", "route"], sort=False):
            concordance_rows.append(
                {
                    "fault_type": fault,
                    "analyte": keys[0],
                    "route": keys[1],
                    "n_scenarios": len(group),
                    "raw_domain_recall": float(
                        group["raw_domain_detected"].mean()
                    ),
                    "route_level_recall": float(group["route_detected"].mean()),
                    "detection_agreement": float(
                        group["raw_domain_detected"]
                        .eq(group["route_detected"])
                        .mean()
                    ),
                }
            )
    return (
        audit,
        pd.DataFrame(summary_rows),
        pd.DataFrame(concordance_rows),
        model_audit,
    )


def _summaries(
    trials: pd.DataFrame,
    *,
    repetitions: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    stratified = []
    for fault, attempted in trials.groupby("fault_type"):
        primary_attempted = attempted[attempted["resolution_mode"].eq("original")]
        frame = primary_attempted[primary_attempted["valid_evaluation"]].copy()
        if frame.empty:
            continue
        successes = int(frame["detected"].sum())
        cluster_low, cluster_high = cluster_bootstrap_proportion(
            frame,
            outcome_column="detected",
            cluster_columns=["sensor_id", "base_window_onset"],
            repetitions=repetitions,
            rng=rng,
        )
        wilson_low, wilson_high = wilson_interval(successes, len(frame))
        labels = np.r_[np.zeros(len(frame)), np.ones(len(frame))]
        scores = np.r_[frame["blank_statistic"], frame["injected_statistic"]]
        rows.append(
            {
                "fault_type": fault,
                "n_trials": len(frame),
                "n_attempted": len(primary_attempted),
                "n_excluded_not_evaluable": len(primary_attempted) - len(frame),
                "event_recall": successes / len(frame),
                "recall_ci_low": cluster_low,
                "recall_ci_high": cluster_high,
                "wilson_ci_low_supplementary": wilson_low,
                "wilson_ci_high_supplementary": wilson_high,
                "AUROC": float(roc_auc_score(labels, scores)),
                "AUPRC": float(average_precision_score(labels, scores)),
                "false_alarms_per_sensor_day": float(
                    frame["blank_alarm"].sum()
                    / np.maximum(frame["evaluation_hours"].sum() / 24.0, 1e-9)
                ),
                "median_detection_delay": _finite_median(frame["detection_delay"]),
                "common_process_conditional_new_far": float(
                    frame.loc[
                        ~frame["blank_alarm"], "common_process_alarm"
                    ].dropna().mean()
                )
                if frame.loc[
                    ~frame["blank_alarm"], "common_process_alarm"
                ].notna().any()
                else np.nan,
                "analysis_unit": "sensor_onset_cluster",
                "ci_method": "cluster_bootstrap_sensor_plus_base_window",
                "resolution_role": "original_primary",
            }
        )
        for keys, group in attempted[
            attempted["valid_evaluation"]
        ].groupby(["analyte", "route", "resolution_mode"]):
            success = int(group["detected"].sum())
            ci_low, ci_high = cluster_bootstrap_proportion(
                group,
                outcome_column="detected",
                cluster_columns=["sensor_id", "base_window_onset"],
                repetitions=repetitions,
                rng=rng,
            )
            stratified.append(
                {
                    "fault_type": fault,
                    "analyte": keys[0],
                    "route": keys[1],
                    "resolution_mode": keys[2],
                    "n_trials": len(group),
                    "event_recall": success / len(group),
                    "recall_ci_low": ci_low,
                    "recall_ci_high": ci_high,
                    "median_detection_delay": _finite_median(group["detection_delay"]),
                    "ci_method": "cluster_bootstrap_sensor_plus_base_window",
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(stratified)


def _applicability_outputs(
    trials: pd.DataFrame,
    *,
    design: dict,
    repetitions: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    map_rows = []
    high_rows = []
    duration_rows = []
    valid = trials[trials["valid_evaluation"]].copy()
    high_threshold = float(
        read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")[
            "locked_decision_thresholds"
        ]["D1_high_amplitude_sigma"]
    )
    surface_config = design["detection_surface"]
    minimum_clusters = int(
        surface_config["minimum_independent_clusters_per_cell"]
    )
    target_recall = float(surface_config["target_recall"])
    for fault in ("spike", "step", "linear_drift"):
        fault_frame = valid[valid["fault_type"].eq(fault)].copy()
        specification = design["core_faults"][fault]
        amplitude_edges = np.linspace(
            float(specification["amplitude_sigma"][0]),
            float(specification["amplitude_sigma"][1]),
            int(surface_config["amplitude_bins"]) + 1,
        )
        duration_limits = next(
            value
            for key, value in specification.items()
            if key.startswith("duration_")
        )
        duration_edges = np.geomspace(
            float(duration_limits[0]),
            float(duration_limits[1]),
            int(surface_config["duration_bins"]) + 1,
        )
        expanded = pd.concat(
            [
                fault_frame.assign(route_scope=fault_frame["route"]),
                fault_frame.assign(route_scope="all_routes"),
            ],
            ignore_index=True,
        )
        expanded["amplitude_bin"] = pd.cut(
            expanded["amplitude_sigma"],
            bins=amplitude_edges,
            include_lowest=True,
            labels=False,
        )
        expanded["duration_bin"] = pd.cut(
            expanded["duration"],
            bins=duration_edges,
            include_lowest=True,
            labels=False,
        )
        dimensions = expanded[
            ["analyte", "route_scope", "resolution_mode"]
        ].drop_duplicates()
        for dimension in dimensions.itertuples(index=False):
            subset = expanded[
                expanded["analyte"].eq(dimension.analyte)
                & expanded["route_scope"].eq(dimension.route_scope)
                & expanded["resolution_mode"].eq(dimension.resolution_mode)
            ]
            duration_unit = str(subset["duration_unit"].iloc[0])
            for amp_index in range(len(amplitude_edges) - 1):
                for duration_index in range(len(duration_edges) - 1):
                    group = subset[
                        subset["amplitude_bin"].eq(amp_index)
                        & subset["duration_bin"].eq(duration_index)
                    ]
                    n_clusters = len(
                        group[
                            ["sensor_id", "base_window_onset"]
                        ].drop_duplicates()
                    )
                    if group.empty:
                        recall = low = high = np.nan
                    else:
                        recall = float(group["detected"].mean())
                        low, high = cluster_bootstrap_proportion(
                            group,
                            outcome_column="detected",
                            cluster_columns=["sensor_id", "base_window_onset"],
                            repetitions=repetitions,
                            rng=rng,
                        )
                    sufficient = n_clusters >= minimum_clusters
                    if not sufficient:
                        target_status = "insufficient"
                        ci_target_status = "insufficient"
                    else:
                        target_status = (
                            "meets_0.80" if recall >= target_recall else "below_0.80"
                        )
                        if low >= target_recall:
                            ci_target_status = "ci_supports_0.80"
                        elif high < target_recall:
                            ci_target_status = "ci_excludes_0.80"
                        else:
                            ci_target_status = "ci_inconclusive"
                    map_rows.append(
                        {
                            "fault_type": fault,
                            "analyte": dimension.analyte,
                            "route": dimension.route_scope,
                            "resolution_mode": dimension.resolution_mode,
                            "amplitude_bin": amp_index,
                            "amplitude_low_sigma": amplitude_edges[amp_index],
                            "amplitude_high_sigma": amplitude_edges[amp_index + 1],
                            "amplitude_center_sigma": float(
                                np.mean(
                                    amplitude_edges[amp_index : amp_index + 2]
                                )
                            ),
                            "duration_bin": duration_index,
                            "duration_low": duration_edges[duration_index],
                            "duration_high": duration_edges[duration_index + 1],
                            "duration_center": float(
                                np.sqrt(
                                    duration_edges[duration_index]
                                    * duration_edges[duration_index + 1]
                                )
                            ),
                            "duration_unit": duration_unit,
                            "n_scenarios": len(group),
                            "n_independent_clusters": n_clusters,
                            "minimum_independent_clusters": minimum_clusters,
                            "detection_probability": recall,
                            "ci95_low": low,
                            "ci95_high": high,
                            "cell_support": (
                                "sufficient" if sufficient else "insufficient"
                            ),
                            "target_recall": target_recall,
                            "target_status": target_status,
                            "ci_target_status": ci_target_status,
                            "display_policy": (
                                "numeric"
                                if sufficient
                                else "gray_hatch_no_interpolation"
                            ),
                            "ci_method": (
                                "cluster_bootstrap_sensor_plus_base_window"
                            ),
                        }
                    )
        high_frame = expanded[
            expanded["amplitude_sigma"].ge(high_threshold)
        ]
        for keys, group in high_frame.groupby(
            ["analyte", "route_scope", "resolution_mode"],
            sort=False,
        ):
            low, high = cluster_bootstrap_proportion(
                group,
                outcome_column="detected",
                cluster_columns=["sensor_id", "base_window_onset"],
                repetitions=repetitions,
                rng=rng,
            )
            high_rows.append(
                {
                    "fault_type": fault,
                    "analyte": keys[0],
                    "route": keys[1],
                    "resolution_mode": keys[2],
                    "amplitude_threshold_sigma": high_threshold,
                    "n_scenarios": len(group),
                    "event_recall": float(group["detected"].mean()),
                    "ci95_low": low,
                    "ci95_high": high,
                    "locked_target": target_recall,
                    "target_passed": (
                        float(group["detected"].mean()) >= target_recall
                    ),
                }
            )
    for fault in ("spike", "hard_freeze"):
        fault_frame = valid[valid["fault_type"].eq(fault)].copy()
        limits = next(
            value
            for key, value in design["core_faults"][fault].items()
            if key.startswith("duration_")
        )
        edges = np.geomspace(float(limits[0]), float(limits[1]), 7)
        fault_frame["duration_bin"] = pd.cut(
            fault_frame["duration"],
            bins=edges,
            include_lowest=True,
            labels=False,
        )
        expanded = pd.concat(
            [
                fault_frame.assign(route_scope=fault_frame["route"]),
                fault_frame.assign(route_scope="all_routes"),
            ],
            ignore_index=True,
        )
        dimensions = expanded[
            ["analyte", "route_scope", "resolution_mode"]
        ].drop_duplicates()
        for dimension in dimensions.itertuples(index=False):
            subset = expanded[
                expanded["analyte"].eq(dimension.analyte)
                & expanded["route_scope"].eq(dimension.route_scope)
                & expanded["resolution_mode"].eq(dimension.resolution_mode)
            ].copy()
            subset["duration_bin"] = pd.cut(
                subset["duration"],
                bins=edges,
                include_lowest=True,
                labels=False,
            )
            for bin_index in range(len(edges) - 1):
                group = subset[subset["duration_bin"].eq(bin_index)]
                n_clusters = len(
                    group[
                        ["sensor_id", "base_window_onset"]
                    ].drop_duplicates()
                )
                if group.empty:
                    recall = low = high = np.nan
                else:
                    recall = float(group["detected"].mean())
                    low, high = cluster_bootstrap_proportion(
                        group,
                        outcome_column="detected",
                        cluster_columns=["sensor_id", "base_window_onset"],
                        repetitions=repetitions,
                        rng=rng,
                    )
                sufficient = n_clusters >= minimum_clusters
                duration_rows.append(
                    {
                        "fault_type": fault,
                        "analyte": dimension.analyte,
                        "route": dimension.route_scope,
                        "resolution_mode": dimension.resolution_mode,
                        "duration_bin": bin_index,
                        "duration_low": edges[bin_index],
                        "duration_high": edges[bin_index + 1],
                        "duration_center": float(
                            np.sqrt(edges[bin_index] * edges[bin_index + 1])
                        ),
                        "duration_unit": (
                            str(subset["duration_unit"].iloc[0])
                            if not subset.empty
                            else "unknown"
                        ),
                        "n_scenarios": len(group),
                        "n_independent_clusters": n_clusters,
                        "minimum_independent_clusters": minimum_clusters,
                        "event_recall": recall,
                        "ci95_low": low,
                        "ci95_high": high,
                        "cell_support": (
                            "sufficient" if sufficient else "insufficient"
                        ),
                        "target_recall": target_recall,
                        "target_status": (
                            "insufficient"
                            if not sufficient
                            else (
                                "meets_0.80"
                                if recall >= target_recall
                                else "below_0.80"
                            )
                        ),
                        "amplitude_axis": (
                            "not_defined_for_hard_freeze"
                            if fault == "hard_freeze"
                            else "marginalized_over_injected_amplitude"
                        ),
                        "ci_method": (
                            "cluster_bootstrap_sensor_plus_base_window"
                        ),
                    }
                )
    return (
        pd.DataFrame(map_rows),
        pd.DataFrame(high_rows),
        pd.DataFrame(duration_rows),
    )


def _reuse_locked_trial_outputs(
    output_dir: Path,
    *,
    design: dict,
    repetitions: int,
) -> dict[str, pd.DataFrame]:
    registry = read_yaml(PROJECT_ROOT / "dimension_registry.yaml")
    source_relative = registry["aggregation_contract"][
        "confirmatory_run_location"
    ]
    source_dir = PROJECT_ROOT / source_relative
    if source_dir.resolve() == output_dir.resolve():
        raise RuntimeError("Locked D1 trial source cannot be the active output directory")
    manifest_path = source_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        design["trial_reuse"]["require_completed_manifest"]
        and not str(manifest.get("status", "")).startswith("completed")
    ):
        raise RuntimeError("Locked D1 trial source manifest is not completed")
    manifest_artifacts = {
        row["relative_path"]: row["sha256"]
        for row in manifest["artifacts"]
    }
    required_names = [
        "D1_injection_trials",
        "D1_injection_summary",
        "D1_injection_stratified",
        "D1_raw_endpoint_trials",
        "D1_raw_endpoint_summary",
        "D1_raw_route_concordance",
        "D1_frozen_whitener_audit",
        "D1_design_audit",
        "D1_excluded_injection_trials",
        "D1_existing_peer_model_audit",
        "D1_existing_DO24_peer_controls",
        "D1_existing_DO24_peer_control_summary",
    ]
    outputs: dict[str, pd.DataFrame] = {}
    audit_rows = []
    for name in required_names:
        relative_path = f"{name}.parquet"
        path = source_dir / relative_path
        observed_hash = sha256_file(path)
        expected_hash = manifest_artifacts.get(relative_path)
        verified = observed_hash == expected_hash
        if design["trial_reuse"]["require_sha256_match"] and not verified:
            raise RuntimeError(f"Locked D1 source hash mismatch: {relative_path}")
        outputs[name] = pd.read_parquet(path)
        audit_rows.append(
            {
                "source_run_id": manifest["run_id"],
                "source_relative_path": relative_path,
                "expected_sha256": expected_hash,
                "observed_sha256": observed_hash,
                "sha256_verified": verified,
                "regenerated": False,
                "postprocessing_role": (
                    "frozen_existing_trial_source"
                    if name == "D1_injection_trials"
                    else "frozen_existing_validation_evidence"
                ),
            }
        )
    trials = outputs["D1_injection_trials"].copy()
    applicability, high_amplitude, duration_response = _applicability_outputs(
        trials,
        design=design,
        repetitions=repetitions,
        rng=np.random.default_rng(20260729),
    )
    outputs.update(
        {
            "D1_applicability_map": applicability,
            "D1_detection_surface": applicability,
            "D1_high_amplitude_summary": high_amplitude,
            "D1_duration_response": duration_response,
            "D1_trial_reuse_audit": pd.DataFrame(audit_rows),
        }
    )
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    excluded = outputs["D1_excluded_injection_trials"]
    with pd.ExcelWriter(
        output_dir / "D1_detection_surface_source.xlsx",
        engine="openpyxl",
    ) as writer:
        applicability.to_excel(
            writer,
            sheet_name="detection_surface",
            index=False,
        )
        duration_response.to_excel(
            writer,
            sheet_name="freeze_duration",
            index=False,
        )
        outputs["D1_raw_route_concordance"].to_excel(
            writer,
            sheet_name="route_raw_agreement",
            index=False,
        )
        outputs["D1_raw_endpoint_summary"].to_excel(
            writer,
            sheet_name="raw_endpoint_summary",
            index=False,
        )
        excluded.to_excel(writer, sheet_name="exclusions", index=False)
        outputs["D1_trial_reuse_audit"].to_excel(
            writer,
            sheet_name="trial_reuse_audit",
            index=False,
        )
    excluded.to_excel(
        output_dir / "D1_exclusions_detail.xlsx",
        index=False,
    )
    return outputs


def run_d1_validation(output_dir: Path, d3_gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D1"]
    sap = read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")
    repetitions = int(sap["uncertainty"]["repetitions"])
    if design["trial_reuse"]["enabled"]:
        return _reuse_locked_trial_outputs(
            output_dir,
            design=design,
            repetitions=repetitions,
        )
    with (D1_ROOT / "v11_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    with (
        PROJECT_ROOT
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "d2_state.pkl"
    ).open("rb") as handle:
        d2_state = pickle.load(handle)
    with (
        PROJECT_ROOT / "1.1 Decomposition" / "outputs" / "_pipeline_state.pkl"
    ).open("rb") as handle:
        decomposition = pickle.load(handle)
    with (
        PROJECT_ROOT / "1.1 Decomposition" / "outputs" / "_w2_checkpoint.pkl"
    ).open("rb") as handle:
        decomposition_components = pickle.load(handle)["out"]
        raw = decomposition_components["df_min"]

    clean = _prepare_clean_hours(state, d2_state, d3_gate)
    models, peers = _fit_pls_models(state)
    sensor_cfg = yaml.safe_load(
        (
            PROJECT_ROOT
            / "D2 Temporal Continuity & Information Availability"
            / "configs"
            / "d2_sensors.yaml"
        ).read_text(encoding="utf-8")
    )["sensors"]
    mapping = yaml.safe_load((D1_ROOT / "configs" / "mapping.yaml").read_text(encoding="utf-8"))[
        "step"
    ]
    rng_design = np.random.default_rng(20260727)
    rng_summary = np.random.default_rng(20260728)
    rng_applicability = np.random.default_rng(20260729)
    rng_raw_audit = np.random.default_rng(20260730)
    rows = []
    fault_specs = [
        ("spike", int(design["core_faults"]["spike"]["target_trials"])),
        ("step", int(design["core_faults"]["step"]["target_trials"])),
        ("linear_drift", int(design["core_faults"]["linear_drift"]["target_trials"])),
        ("hard_freeze", int(design["core_faults"]["hard_freeze"]["target_trials"])),
    ]
    for fault, total in fault_specs:
        sampler = qmc.LatinHypercube(
            d=2, seed=int(rng_design.integers(0, 2**31 - 1))
        )
        lhs = sampler.random(total)
        per_analyte = {"DO": total // 2, "ORP": total - total // 2}
        schedule = []
        for analyte, count in per_analyte.items():
            schedule.extend(
                _pick_onsets(
                    clean,
                    state,
                    analyte=analyte,
                    n=count,
                    rng=rng_design,
                )
            )
        rng_design.shuffle(schedule)
        for trial_no, ((sensor, base_onset, regime), point) in enumerate(
            zip(schedule, lhs), 1
        ):
            analyte = sensor.split("_")[0]
            route = state["scoring_mode"][sensor]
            direction = -1 if trial_no % 2 else 1
            sensor_precision = float(sensor_cfg[sensor]["precision"])
            scenario_amplitude = (
                np.nan if fault == "hard_freeze" else 0.5 + 2.5 * float(point[0])
            )
            if fault == "spike":
                duration = 1 + int(np.floor(9 * point[1]))
                injection_onset = base_onset + pd.Timedelta(minutes=30)
                evaluation_hours = max(1.0, (duration + 10) / 60.0)
                duration_value, duration_unit = duration, "min"
            elif fault == "step":
                duration = 0.5 + 47.5 * float(point[1])
                injection_onset = base_onset
                evaluation_hours = duration + 48.0
                duration_value, duration_unit = duration, "h"
            elif fault == "linear_drift":
                duration = 12.0 + 156.0 * float(point[1])
                injection_onset = base_onset
                evaluation_hours = duration + 12.0
                duration_value, duration_unit = duration, "h"
            else:
                duration = 15 + int(np.floor((1440 - 15) * point[1]))
                injection_onset = base_onset + pd.Timedelta(minutes=15)
                evaluation_hours = duration / 60.0
                duration_value, duration_unit = duration, "min"
            scenario_id = f"D1V2-{fault}-{trial_no:04d}"
            for resolution_mode in ("original", "degraded_2x"):
                degraded_resolution = resolution_mode == "degraded_2x"
                common_process_alarm = np.nan
                if fault == "spike":
                    result = _spike_trial(
                        decomposition["resid_min"][sensor],
                        injection_onset,
                        scenario_amplitude,
                        duration,
                        direction,
                        sensor_precision * 2.0 if degraded_resolution else None,
                    )
                elif fault == "step":
                    result = _step_trial(
                        state["whitened_input_h"][sensor],
                        injection_onset,
                        scenario_amplitude,
                        duration,
                        direction,
                        float(state["eff_neff"].get(sensor, 1.0)),
                        mapping,
                        degraded_resolution,
                    )
                elif fault == "linear_drift":
                    drift_result = _drift_trial(
                        state,
                        models[sensor],
                        peers[sensor],
                        sensor,
                        injection_onset,
                        scenario_amplitude,
                        duration,
                        direction,
                        sensor_precision * 2.0 if degraded_resolution else None,
                    )
                    result = drift_result[:5]
                    common_process_alarm = drift_result[5]
                else:
                    result = _freeze_trial(
                        raw[sensor],
                        injection_onset,
                        duration,
                        sensor_precision,
                        degraded_resolution,
                    )
                rows.append(
                    {
                        "trial_id": (
                            f"{scenario_id}-"
                            f"{'R0' if resolution_mode == 'original' else 'R2X'}"
                        ),
                        "scenario_id": scenario_id,
                        "fault_type": fault,
                        "sensor_id": sensor,
                        "analyte": analyte,
                        "regime_id": regime,
                        "route": route,
                        "resolution_mode": resolution_mode,
                        "resolution_role": (
                            "primary"
                            if resolution_mode == "original"
                            else "exploratory_sensitivity"
                        ),
                        "base_window_onset": base_onset,
                        "onset": injection_onset,
                        "amplitude_sigma": scenario_amplitude,
                        "direction": direction,
                        "duration": duration_value,
                        "duration_unit": duration_unit,
                        "blank_statistic": result[0],
                        "injected_statistic": result[1],
                        "blank_alarm": result[2],
                        "detected": result[3],
                        "detection_delay": result[4],
                        "common_process_alarm": common_process_alarm,
                        "evaluation_hours": evaluation_hours,
                        "injection_domain": design["route_domains"][fault],
                        "validation_layer": "detector_route_level",
                        "preprocessing_refit_on_fault": False,
                        "analysis_unit": (
                            "sensor_onset_clustered_injection_episode"
                        ),
                        "valid_evaluation": bool(
                            np.isfinite(result[0]) and np.isfinite(result[1])
                        ),
                    }
                )
    trials = pd.DataFrame(rows)
    summary, stratified = _summaries(
        trials,
        repetitions=repetitions,
        rng=rng_summary,
    )
    applicability, high_amplitude, duration_response = _applicability_outputs(
        trials,
        design=design,
        repetitions=repetitions,
        rng=rng_applicability,
    )
    (
        raw_audit,
        raw_summary,
        raw_concordance,
        whitener_audit,
    ) = _raw_endpoint_audit(
        trials,
        raw=raw,
        decomposition=decomposition,
        decomposition_components=decomposition_components,
        state=state,
        models=models,
        peers=peers,
        sensor_cfg=sensor_cfg,
        mapping=mapping,
        design=design,
        repetitions=repetitions,
        rng=rng_raw_audit,
    )
    design_audit = (
        trials.groupby(
            ["fault_type", "analyte", "regime_id", "route", "resolution_mode"],
            as_index=False,
        )
        .agg(
            n_trials=("trial_id", "size"),
            n_scenarios=("scenario_id", "nunique"),
            distinct_sensors=("sensor_id", "nunique"),
            distinct_onsets=("base_window_onset", "nunique"),
            amplitude_min=("amplitude_sigma", "min"),
            amplitude_max=("amplitude_sigma", "max"),
            duration_min=("duration", "min"),
            duration_max=("duration", "max"),
            n_evaluable=("valid_evaluation", "sum"),
        )
    )
    excluded = trials.loc[~trials["valid_evaluation"]].copy()
    if not excluded.empty:
        excluded["exclusion_reason"] = "nonfinite_local_evaluation_statistic"
    outputs = {
        "D1_injection_trials": trials,
        "D1_injection_summary": summary,
        "D1_injection_stratified": stratified,
        "D1_applicability_map": applicability,
        "D1_detection_surface": applicability,
        "D1_high_amplitude_summary": high_amplitude,
        "D1_duration_response": duration_response,
        "D1_raw_endpoint_trials": raw_audit,
        "D1_raw_endpoint_summary": raw_summary,
        "D1_raw_route_concordance": raw_concordance,
        "D1_frozen_whitener_audit": whitener_audit,
        "D1_design_audit": design_audit,
        "D1_excluded_injection_trials": excluded,
        "D1_existing_peer_model_audit": state["detectors_raw"][
            "pls_peer_selection_audit"
        ].reset_index(),
        "D1_existing_DO24_peer_controls": state["detectors_raw"][
            "pls_do24_injection_scenarios"
        ].copy(),
        "D1_existing_DO24_peer_control_summary": state["detectors_raw"][
            "pls_do24_injection_summary"
        ].copy(),
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    with pd.ExcelWriter(
        output_dir / "D1_detection_surface_source.xlsx",
        engine="openpyxl",
    ) as writer:
        applicability.to_excel(writer, sheet_name="detection_surface", index=False)
        duration_response.to_excel(
            writer,
            sheet_name="freeze_duration",
            index=False,
        )
        raw_concordance.to_excel(
            writer,
            sheet_name="route_raw_agreement",
            index=False,
        )
        raw_summary.to_excel(
            writer,
            sheet_name="raw_endpoint_summary",
            index=False,
        )
        excluded.to_excel(writer, sheet_name="exclusions", index=False)
    excluded.to_excel(
        output_dir / "D1_exclusions_detail.xlsx",
        index=False,
    )
    return outputs
