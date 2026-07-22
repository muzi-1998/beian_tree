"""Pre-specified validation of the DO_2_4 second-order PLS peer.

The formal D1 detector is a static 21-day virtual sensor.  This module keeps
that deployment contract fixed while comparing the topology core with one-
and two-component augmented models over the remaining record.  Model choice
uses development blocks and controlled injections; the terminal block is
opened only to confirm or reject the pre-selected upgrade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class PLSPeerValidationConfig:
    """Locked validation and admission rules for the DO_2_4 peer upgrade."""

    target: str = "DO_2_4"
    core_peer: str = "DO_2_3"
    candidate_peer: str = "DO_2_2"
    train_days: int = 21
    terminal_test_days: int = 42
    validation_block_days: int = 7
    bootstrap_replicates: int = 5000
    bootstrap_block_folds: int = 4
    random_seed: int = 20260721
    injection_window_h: int = 48
    injection_ramp_h: int = 12
    injection_scan_stride_h: int = 24
    clean_abs_z_max: float = 1.5
    clean_fraction_min: float = 0.90
    alarm_abs_z: float = 2.5
    alarm_duration_h: int = 3
    injection_amplitudes_sigma: tuple[float, ...] = (1.0, 2.0, 3.0)
    injection_signs: tuple[int, ...] = (-1, 1)
    material_amplitude_sigma: float = 2.0
    min_median_gain_pct: float = 2.0
    min_positive_fold_fraction: float = 0.60
    max_p90_degradation_pct: float = 5.0
    max_detection_loss_fraction: float = 0.05
    max_false_alarm_increase_fraction: float = 0.05
    max_absolute_false_alarm_fraction: float = 0.05
    min_test_gain_pct: float = 0.0


MODEL_SPECS = (
    {
        "model_id": "M0",
        "label": "Core: DO_2_3 (1 comp.)",
        "peers": ("DO_2_3",),
        "n_components": 1,
        "role": "topology_core",
    },
    {
        "model_id": "M1_1",
        "label": "Augmented: DO_2_3 + DO_2_2 (1 comp.)",
        "peers": ("DO_2_3", "DO_2_2"),
        "n_components": 1,
        "role": "candidate",
    },
    {
        "model_id": "M1_2",
        "label": "Augmented: DO_2_3 + DO_2_2 (2 comp.)",
        "peers": ("DO_2_3", "DO_2_2"),
        "n_components": 2,
        "role": "candidate",
    },
)


@dataclass
class _FittedPLS:
    model_id: str
    label: str
    peers: tuple[str, ...]
    n_components: int
    model: PLSRegression
    x_scaler: StandardScaler
    y_scaler: StandardScaler
    medians: pd.Series
    sigma_residual: float
    target_scale: float
    target: str

    def _prepared(self, frame: pd.DataFrame) -> pd.DataFrame:
        columns = [self.target, *self.peers]
        return (
            frame.loc[:, columns]
            .astype(float)
            .ffill()
            .fillna(self.medians)
            .fillna(0.0)
        )

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        prepared = self._prepared(frame)
        x_scaled = self.x_scaler.transform(
            prepared.loc[:, self.peers].to_numpy(dtype=float)
        )
        prediction_s = self.model.predict(x_scaled).reshape(-1)
        return self.y_scaler.inverse_transform(prediction_s.reshape(-1, 1)).reshape(-1)

    def observed(self, frame: pd.DataFrame) -> np.ndarray:
        return self._prepared(frame)[self.target].to_numpy(dtype=float)

    def residual_z(self, frame: pd.DataFrame) -> np.ndarray:
        return np.abs(self.observed(frame) - self.predict(frame)) / self.sigma_residual


def _fit_model(
    frame: pd.DataFrame,
    target: str,
    spec: dict[str, Any],
    train_h: int,
) -> _FittedPLS:
    peers = tuple(spec["peers"])
    columns = [target, *peers]
    raw = frame.loc[:, columns].astype(float).copy()
    medians = raw.iloc[:train_h].median(axis=0).fillna(0.0)
    prepared = raw.ffill().fillna(medians).fillna(0.0)
    train = prepared.iloc[:train_h]
    x_train = train.loc[:, peers].to_numpy(dtype=float)
    y_train = train[target].to_numpy(dtype=float)
    x_scaler = StandardScaler().fit(x_train)
    y_scaler = StandardScaler().fit(y_train.reshape(-1, 1))
    x_scaled = x_scaler.transform(x_train)
    y_scaled = y_scaler.transform(y_train.reshape(-1, 1)).reshape(-1)
    n_components = min(int(spec["n_components"]), len(peers), len(train) - 1)
    model = PLSRegression(n_components=max(1, n_components), scale=False).fit(
        x_scaled, y_scaled
    )
    train_prediction_s = model.predict(x_scaled).reshape(-1)
    train_prediction = y_scaler.inverse_transform(
        train_prediction_s.reshape(-1, 1)
    ).reshape(-1)
    target_scale = max(float(np.std(y_train)), 1e-9)
    sigma_residual = max(
        float(np.std(y_train - train_prediction)), 0.05 * target_scale, 1e-9
    )
    return _FittedPLS(
        model_id=str(spec["model_id"]),
        label=str(spec["label"]),
        peers=peers,
        n_components=max(1, n_components),
        model=model,
        x_scaler=x_scaler,
        y_scaler=y_scaler,
        medians=medians,
        sigma_residual=sigma_residual,
        target_scale=target_scale,
        target=target,
    )


def _has_sustained_alarm(values: np.ndarray, threshold: float, duration_h: int) -> bool:
    active = np.asarray(values >= threshold, dtype=np.int8)
    if active.size < duration_h:
        return False
    return bool(np.convolve(active, np.ones(duration_h, dtype=int), mode="valid").max() >= duration_h)


def _first_alarm_delay(values: np.ndarray, threshold: float, duration_h: int) -> float:
    active = np.asarray(values >= threshold, dtype=np.int8)
    if active.size < duration_h:
        return np.nan
    run = np.convolve(active, np.ones(duration_h, dtype=int), mode="valid")
    hits = np.flatnonzero(run >= duration_h)
    return float(hits[0]) if hits.size else np.nan


def _moving_block_bootstrap_median(
    values: np.ndarray,
    replicates: int,
    block_folds: int,
    rng: np.random.Generator,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)
    block = min(max(1, block_folds), n)
    n_blocks = int(np.ceil(n / block))
    samples = np.empty(replicates, dtype=float)
    offsets = np.arange(block)
    for i in range(replicates):
        starts = rng.integers(0, n, size=n_blocks)
        indices = ((starts[:, None] + offsets[None, :]) % n).reshape(-1)[:n]
        samples[i] = float(np.median(values[indices]))
    return samples


def _fold_metrics(
    frame: pd.DataFrame,
    fitted: dict[str, _FittedPLS],
    train_h: int,
    test_start: int,
    block_h: int,
) -> pd.DataFrame:
    prediction = {model_id: model.predict(frame) for model_id, model in fitted.items()}
    observed = fitted["M0"].observed(frame)
    target_scale = fitted["M0"].target_scale
    rows = []
    fold_id = 0
    for start in range(train_h, test_start, block_h):
        end = min(start + block_h, test_start)
        if end <= start:
            continue
        fold_id += 1
        for model_id, model in fitted.items():
            error = observed[start:end] - prediction[model_id][start:end]
            rows.append({
                "fold_id": fold_id,
                "model_id": model_id,
                "model_label": model.label,
                "start": frame.index[start],
                "end": frame.index[end - 1],
                "n_h": end - start,
                "nrmse": float(np.sqrt(np.mean(error ** 2)) / target_scale),
                "p90_abs_normalised_error": float(
                    np.quantile(np.abs(error) / target_scale, 0.90)
                ),
            })
    folds = pd.DataFrame(rows)
    baseline = folds.loc[folds.model_id == "M0", ["fold_id", "nrmse"]].rename(
        columns={"nrmse": "baseline_nrmse"}
    )
    folds = folds.merge(baseline, on="fold_id", how="left")
    folds["gain_pct_vs_M0"] = 100.0 * (
        folds["baseline_nrmse"] - folds["nrmse"]
    ) / folds["baseline_nrmse"].clip(lower=1e-12)
    folds.loc[folds.model_id == "M0", "gain_pct_vs_M0"] = 0.0
    return folds


def _hourly_diagnostics(
    frame: pd.DataFrame,
    fitted: dict[str, _FittedPLS],
    train_h: int,
    test_start: int,
    block_h: int,
) -> pd.DataFrame:
    """Publish the row-level quantities needed to reproduce every error metric."""
    observed = fitted["M0"].observed(frame)
    target_scale = fitted["M0"].target_scale
    row_number = np.arange(len(frame))
    split = np.full(len(frame), "development", dtype=object)
    split[:train_h] = "training"
    split[test_start:] = "terminal_test"
    fold_id = np.full(len(frame), np.nan)
    development_rows = np.arange(train_h, test_start)
    fold_id[development_rows] = (
        (development_rows - train_h) // block_h + 1
    )
    diagnostics = pd.DataFrame({
        "timestamp": frame.index,
        "row_number": row_number,
        "split": split,
        "validation_fold_id": fold_id,
        "target_residual_used": observed,
    })
    for model_id, model in fitted.items():
        prediction = model.predict(frame)
        signed_error = observed - prediction
        diagnostics[f"{model_id}_prediction"] = prediction
        diagnostics[f"{model_id}_signed_error"] = signed_error
        diagnostics[f"{model_id}_abs_normalised_error"] = (
            np.abs(signed_error) / target_scale
        )
        diagnostics[f"{model_id}_abs_residual_z"] = (
            np.abs(signed_error) / model.sigma_residual
        )
    return diagnostics


def _performance_summary(
    frame: pd.DataFrame,
    fitted: dict[str, _FittedPLS],
    folds: pd.DataFrame,
    train_h: int,
    test_start: int,
    cfg: PLSPeerValidationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_scale = fitted["M0"].target_scale
    observed = fitted["M0"].observed(frame)
    predictions = {key: model.predict(frame) for key, model in fitted.items()}
    baseline_dev_error = observed[train_h:test_start] - predictions["M0"][train_h:test_start]
    baseline_test_error = observed[test_start:] - predictions["M0"][test_start:]
    baseline_test_nrmse = float(np.sqrt(np.mean(baseline_test_error ** 2)) / target_scale)
    baseline_dev_p90 = float(np.quantile(np.abs(baseline_dev_error) / target_scale, 0.90))
    baseline_test_p90 = float(np.quantile(np.abs(baseline_test_error) / target_scale, 0.90))
    rng = np.random.default_rng(cfg.random_seed)
    summary_rows = []
    bootstrap_rows = []
    for model_id, model in fitted.items():
        model_folds = folds.loc[folds.model_id == model_id].copy()
        gains = model_folds["gain_pct_vs_M0"].to_numpy(dtype=float)
        boot = _moving_block_bootstrap_median(
            gains,
            cfg.bootstrap_replicates,
            cfg.bootstrap_block_folds,
            rng,
        )
        for replicate, value in enumerate(boot, 1):
            bootstrap_rows.append({
                "model_id": model_id,
                "bootstrap_replicate": replicate,
                "median_gain_pct": value,
            })
        dev_error = observed[train_h:test_start] - predictions[model_id][train_h:test_start]
        test_error = observed[test_start:] - predictions[model_id][test_start:]
        test_nrmse = float(np.sqrt(np.mean(test_error ** 2)) / target_scale)
        dev_p90 = float(np.quantile(np.abs(dev_error) / target_scale, 0.90))
        test_p90 = float(np.quantile(np.abs(test_error) / target_scale, 0.90))
        summary_rows.append({
            "model_id": model_id,
            "model_label": model.label,
            "peers": ";".join(model.peers),
            "n_components": model.n_components,
            "n_validation_folds": len(model_folds),
            "median_fold_nrmse": float(model_folds.nrmse.median()),
            "median_gain_pct": float(np.median(gains)),
            "gain_ci95_low_pct": float(np.quantile(boot, 0.025)),
            "gain_ci95_high_pct": float(np.quantile(boot, 0.975)),
            "positive_gain_fold_fraction": float(np.mean(gains > 0.0)),
            "development_p90_change_pct": 100.0 * (dev_p90 / baseline_dev_p90 - 1.0),
            "independent_test_nrmse": test_nrmse,
            "independent_test_gain_pct": 100.0 * (
                baseline_test_nrmse - test_nrmse
            ) / max(baseline_test_nrmse, 1e-12),
            "independent_test_p90_change_pct": 100.0 * (
                test_p90 / baseline_test_p90 - 1.0
            ),
        })
    return pd.DataFrame(summary_rows), pd.DataFrame(bootstrap_rows)


def _clean_windows(
    frame: pd.DataFrame,
    fitted: dict[str, _FittedPLS],
    train_h: int,
    test_start: int,
    cfg: PLSPeerValidationConfig,
) -> pd.DataFrame:
    z_by_model = {key: model.residual_z(frame) for key, model in fitted.items()}
    eligible = []
    latest_end = -1
    for start in range(
        train_h,
        test_start - cfg.injection_window_h + 1,
        cfg.injection_scan_stride_h,
    ):
        end = start + cfg.injection_window_h
        fractions = {
            model_id: float(np.mean(z[start:end] < cfg.clean_abs_z_max))
            for model_id, z in z_by_model.items()
        }
        clean = all(value >= cfg.clean_fraction_min for value in fractions.values())
        alarm_free = all(
            not _has_sustained_alarm(
                z[start:end], cfg.alarm_abs_z, cfg.alarm_duration_h
            )
            for z in z_by_model.values()
        )
        if clean and alarm_free and start >= latest_end:
            eligible.append({
                "window_id": len(eligible) + 1,
                "start_row": start,
                "end_row_exclusive": end,
                "start": frame.index[start],
                "end": frame.index[end - 1],
                **{f"clean_fraction_{key}": value for key, value in fractions.items()},
            })
            latest_end = end
    return pd.DataFrame(eligible)


def _injection_profile(cfg: PLSPeerValidationConfig) -> np.ndarray:
    ramp_h = min(max(1, cfg.injection_ramp_h), cfg.injection_window_h)
    ramp = np.linspace(0.0, 1.0, ramp_h, endpoint=True)
    plateau = np.ones(cfg.injection_window_h - ramp_h, dtype=float)
    return np.concatenate([ramp, plateau])


def _common_process_direction(
    frame: pd.DataFrame,
    train_h: int,
    cfg: PLSPeerValidationConfig,
) -> tuple[np.ndarray, pd.Series, pd.Series]:
    columns = [cfg.candidate_peer, cfg.core_peer, cfg.target]
    train = frame.loc[:, columns].iloc[:train_h].astype(float)
    medians = train.median().fillna(0.0)
    train = train.ffill().fillna(medians).fillna(0.0)
    means = train.mean(axis=0)
    scales = train.std(axis=0, ddof=0).clip(lower=1e-9)
    standardised = (train - means) / scales
    _, _, vt = np.linalg.svd(standardised.to_numpy(dtype=float), full_matrices=False)
    direction = vt[0].copy()
    target_position = columns.index(cfg.target)
    if direction[target_position] < 0:
        direction *= -1.0
    target_loading = max(abs(float(direction[target_position])), 1e-6)
    direction /= target_loading
    return direction, means, scales


def _injection_results(
    frame: pd.DataFrame,
    fitted: dict[str, _FittedPLS],
    windows: pd.DataFrame,
    train_h: int,
    cfg: PLSPeerValidationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if windows.empty:
        return (
            pd.DataFrame(columns=[
                "window_id",
                "window_start",
                "window_end",
                "injection_type",
                "affected_channels",
                "amplitude_sigma",
                "sign",
                "model_id",
                "detected_3h",
                "detection_delay_h",
                "max_abs_residual_z",
            ]),
            pd.DataFrame(columns=[
                "model_id",
                "injection_type",
                "amplitude_sigma",
                "n_scenarios",
                "alarm_fraction",
                "median_detection_delay_h",
                "median_max_abs_residual_z",
            ]),
        )
    profile = _injection_profile(cfg)
    common_direction, _, common_scales = _common_process_direction(frame, train_h, cfg)
    common_columns = [cfg.candidate_peer, cfg.core_peer, cfg.target]
    train_scales = (
        frame.loc[:, common_columns]
        .iloc[:train_h]
        .astype(float)
        .std(axis=0, ddof=0)
        .clip(lower=1e-9)
    )
    injection_types = (
        ("target_drift", (cfg.target,)),
        ("direct_peer_drift", (cfg.core_peer,)),
        ("second_order_peer_drift", (cfg.candidate_peer,)),
        ("common_process_change", tuple(common_columns)),
    )
    rows = []
    for window in windows.itertuples(index=False):
        start = int(window.start_row)
        end = int(window.end_row_exclusive)
        base_window = frame.iloc[start:end].copy()
        for injection_type, affected in injection_types:
            for amplitude in cfg.injection_amplitudes_sigma:
                for sign in cfg.injection_signs:
                    injected = base_window.copy()
                    if injection_type == "common_process_change":
                        for position, channel in enumerate(common_columns):
                            delta = (
                                sign
                                * amplitude
                                * common_direction[position]
                                * common_scales[channel]
                                * profile
                            )
                            injected.loc[:, channel] = injected[channel].to_numpy(dtype=float) + delta
                    else:
                        channel = affected[0]
                        delta = sign * amplitude * train_scales[channel] * profile
                        injected.loc[:, channel] = injected[channel].to_numpy(dtype=float) + delta
                    for model_id, model in fitted.items():
                        z = model.residual_z(injected)
                        detected = _has_sustained_alarm(
                            z, cfg.alarm_abs_z, cfg.alarm_duration_h
                        )
                        rows.append({
                            "window_id": int(window.window_id),
                            "window_start": window.start,
                            "window_end": window.end,
                            "injection_type": injection_type,
                            "affected_channels": ";".join(affected),
                            "amplitude_sigma": float(amplitude),
                            "sign": int(sign),
                            "model_id": model_id,
                            "detected_3h": bool(detected),
                            "detection_delay_h": _first_alarm_delay(
                                z, cfg.alarm_abs_z, cfg.alarm_duration_h
                            ),
                            "max_abs_residual_z": float(np.max(z)),
                        })
    scenarios = pd.DataFrame(rows)
    summary = (
        scenarios.groupby(["model_id", "injection_type", "amplitude_sigma"], as_index=False)
        .agg(
            n_scenarios=("detected_3h", "size"),
            alarm_fraction=("detected_3h", "mean"),
            median_detection_delay_h=("detection_delay_h", "median"),
            median_max_abs_residual_z=("max_abs_residual_z", "median"),
        )
    )
    return scenarios, summary


def _material_alarm_fraction(
    scenarios: pd.DataFrame,
    model_id: str,
    injection_type: str,
    cfg: PLSPeerValidationConfig,
) -> float:
    if scenarios.empty:
        return np.nan
    subset = scenarios.loc[
        (scenarios.model_id == model_id)
        & (scenarios.injection_type == injection_type)
        & (scenarios.amplitude_sigma >= cfg.material_amplitude_sigma)
    ]
    return float(subset.detected_3h.mean()) if len(subset) else np.nan


def _admission_decision(
    performance: pd.DataFrame,
    scenarios: pd.DataFrame,
    cfg: PLSPeerValidationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    indexed = performance.set_index("model_id")
    baseline_rates = {
        kind: _material_alarm_fraction(scenarios, "M0", kind, cfg)
        for kind in (
            "target_drift",
            "direct_peer_drift",
            "second_order_peer_drift",
            "common_process_change",
        )
    }
    gate_rows = []
    for model_id in ("M1_1", "M1_2"):
        row = indexed.loc[model_id]
        rates = {
            kind: _material_alarm_fraction(scenarios, model_id, kind, cfg)
            for kind in baseline_rates
        }
        values = {
            "dev_median_gain": float(row.median_gain_pct),
            "dev_bootstrap_ci_low": float(row.gain_ci95_low_pct),
            "dev_positive_fold_fraction": float(row.positive_gain_fold_fraction),
            "dev_p90_change": float(row.development_p90_change_pct),
            "target_detection_delta": rates["target_drift"] - baseline_rates["target_drift"],
            "direct_peer_fa_delta": rates["direct_peer_drift"] - baseline_rates["direct_peer_drift"],
            "second_peer_fa": rates["second_order_peer_drift"],
            "second_peer_fa_delta": rates["second_order_peer_drift"] - baseline_rates["second_order_peer_drift"],
            "common_process_fa": rates["common_process_change"],
            "common_process_fa_delta": rates["common_process_change"] - baseline_rates["common_process_change"],
            "test_gain": float(row.independent_test_gain_pct),
            "test_p90_change": float(row.independent_test_p90_change_pct),
        }
        passes = {
            "dev_median_gain": values["dev_median_gain"] >= cfg.min_median_gain_pct,
            "dev_bootstrap_ci_low": values["dev_bootstrap_ci_low"] > 0.0,
            "dev_positive_fold_fraction": values["dev_positive_fold_fraction"] >= cfg.min_positive_fold_fraction,
            "dev_p90_change": values["dev_p90_change"] <= cfg.max_p90_degradation_pct,
            "target_detection_delta": values["target_detection_delta"] >= -cfg.max_detection_loss_fraction,
            "direct_peer_fa_delta": values["direct_peer_fa_delta"] <= cfg.max_false_alarm_increase_fraction,
            "second_peer_fa": values["second_peer_fa"] <= cfg.max_absolute_false_alarm_fraction,
            "second_peer_fa_delta": values["second_peer_fa_delta"] <= cfg.max_false_alarm_increase_fraction,
            "common_process_fa": values["common_process_fa"] <= cfg.max_absolute_false_alarm_fraction,
            "common_process_fa_delta": values["common_process_fa_delta"] <= cfg.max_false_alarm_increase_fraction,
            "test_gain": values["test_gain"] > cfg.min_test_gain_pct,
            "test_p90_change": values["test_p90_change"] <= cfg.max_p90_degradation_pct,
        }
        development_gate_names = (
            "dev_median_gain",
            "dev_bootstrap_ci_low",
            "dev_positive_fold_fraction",
            "dev_p90_change",
        )
        injection_gate_names = (
            "target_detection_delta",
            "direct_peer_fa_delta",
            "second_peer_fa",
            "second_peer_fa_delta",
            "common_process_fa",
            "common_process_fa_delta",
        )
        development_pass = all(passes[name] for name in development_gate_names)
        injection_pass = all(passes[name] for name in injection_gate_names)
        test_pass = passes["test_gain"] and passes["test_p90_change"]
        for gate_name, value in values.items():
            gate_rows.append({
                "model_id": model_id,
                "gate": gate_name,
                "value": value,
                "passed": bool(passes[gate_name]),
                "stage": (
                    "development"
                    if gate_name in development_gate_names
                    else "injection"
                    if gate_name in injection_gate_names
                    else "independent_test"
                ),
            })
        indexed.loc[model_id, "development_pass"] = development_pass
        indexed.loc[model_id, "injection_pass"] = injection_pass
        indexed.loc[model_id, "independent_test_pass"] = test_pass

    # Parsimony is pre-specified: a passing one-component upgrade has priority;
    # the two-component model is considered only if the one-component model
    # fails before the independent test is opened.
    nominated = "M0"
    for model_id in ("M1_1", "M1_2"):
        if bool(indexed.loc[model_id, "development_pass"]) and bool(
            indexed.loc[model_id, "injection_pass"]
        ):
            nominated = model_id
            break
    final_model = nominated
    if nominated != "M0" and not bool(indexed.loc[nominated, "independent_test_pass"]):
        final_model = "M0"
    status = "upgrade_confirmed" if final_model != "M0" else "core_retained"
    rationale = (
        "Candidate passed development, controlled-injection and terminal-test gates."
        if status == "upgrade_confirmed"
        else "No augmented model passed the complete pre-specified evidence chain."
    )
    decision = pd.DataFrame([{
        "nominated_before_test": nominated,
        "final_model_id": final_model,
        "decision_status": status,
        "rationale": rationale,
        "parsimony_rule": "M1_1 precedes M1_2; terminal test confirms but does not select",
    }])
    performance = indexed.reset_index()
    performance["selected_final"] = performance.model_id.eq(final_model)
    return pd.DataFrame(gate_rows), decision.merge(
        performance.loc[
            performance.model_id == final_model,
            ["model_id", "model_label", "peers", "n_components"],
        ],
        left_on="final_model_id",
        right_on="model_id",
        how="left",
    )


def validate_do24_peer_upgrade(
    df_hourly: pd.DataFrame,
    cfg: PLSPeerValidationConfig | None = None,
) -> dict[str, Any]:
    """Run the locked three-model validation and return publication-ready tables."""
    cfg = cfg or PLSPeerValidationConfig()
    required = {cfg.target, cfg.core_peer, cfg.candidate_peer}
    missing = sorted(required - set(df_hourly.columns))
    if missing:
        raise ValueError(f"Missing DO_2_4 validation columns: {missing}")
    train_h = cfg.train_days * 24
    test_h = cfg.terminal_test_days * 24
    block_h = cfg.validation_block_days * 24
    minimum = train_h + test_h + 2 * block_h
    if len(df_hourly) < minimum:
        raise ValueError(
            f"Need at least {minimum} hourly rows for train/development/test validation"
        )
    frame = df_hourly.sort_index().copy()
    test_start = len(frame) - test_h
    fitted = {
        spec["model_id"]: _fit_model(frame, cfg.target, spec, train_h)
        for spec in MODEL_SPECS
    }
    folds = _fold_metrics(frame, fitted, train_h, test_start, block_h)
    hourly = _hourly_diagnostics(frame, fitted, train_h, test_start, block_h)
    performance, bootstrap = _performance_summary(
        frame, fitted, folds, train_h, test_start, cfg
    )
    windows = _clean_windows(frame, fitted, train_h, test_start, cfg)
    scenarios, injection_summary = _injection_results(
        frame, fitted, windows, train_h, cfg
    )
    gates, decision = _admission_decision(performance, scenarios, cfg)
    final_id = str(decision.loc[0, "final_model_id"])
    final_spec = next(spec for spec in MODEL_SPECS if spec["model_id"] == final_id)
    split_manifest = pd.DataFrame([{
        "train_start": frame.index[0],
        "train_end": frame.index[train_h - 1],
        "train_n_h": train_h,
        "development_start": frame.index[train_h],
        "development_end": frame.index[test_start - 1],
        "development_n_h": test_start - train_h,
        "independent_test_start": frame.index[test_start],
        "independent_test_end": frame.index[-1],
        "independent_test_n_h": len(frame) - test_start,
        "validation_block_h": block_h,
        "n_validation_folds": int(folds.fold_id.nunique()),
        "n_nonoverlapping_clean_windows": len(windows),
    }])
    model_definitions = pd.DataFrame([
        {
            **{key: value for key, value in spec.items() if key != "peers"},
            "peers": ";".join(spec["peers"]),
        }
        for spec in MODEL_SPECS
    ])
    return {
        "config": pd.DataFrame([asdict(cfg)]),
        "model_definitions": model_definitions,
        "split_manifest": split_manifest,
        "hourly_predictions": hourly,
        "fold_metrics": folds,
        "performance_summary": performance,
        "bootstrap_samples": bootstrap,
        "clean_windows": windows,
        "injection_scenarios": scenarios,
        "injection_summary": injection_summary,
        "gate_results": gates,
        "decision": decision,
        "final_model_id": final_id,
        "final_peers": list(final_spec["peers"]),
        "final_n_components": int(final_spec["n_components"]),
    }


def build_do24_selection_audit(validation: dict[str, Any]) -> dict[str, Any]:
    """Translate the independent validation decision into detector metadata."""
    performance = validation["performance_summary"].set_index("model_id")
    decision = validation["decision"].iloc[0]
    final_id = str(validation["final_model_id"])
    selected = list(validation["final_peers"])
    noncore = [peer for peer in selected if peer != "DO_2_3"]
    selected_row = performance.loc[final_id]
    core_row = performance.loc["M0"]
    return {
        "target": "DO_2_4",
        "core_peers": ["DO_2_3"],
        "candidate_peers": ["DO_2_2"],
        "selected_peers": selected,
        "selected_noncore_peers": noncore,
        "selected_n_components": int(validation["final_n_components"]),
        "core_cv_nrmse_median": float(core_row.median_fold_nrmse),
        "core_cv_nrmse_p90": float(
            validation["fold_metrics"].loc[
                validation["fold_metrics"].model_id == "M0", "nrmse"
            ].quantile(0.90)
        ),
        "selected_cv_nrmse_median": float(selected_row.median_fold_nrmse),
        "selected_cv_nrmse_p90": float(
            validation["fold_metrics"].loc[
                validation["fold_metrics"].model_id == final_id, "nrmse"
            ].quantile(0.90)
        ),
        "cv_improvement_pct": float(selected_row.median_gain_pct),
        "n_blocked_folds": int(selected_row.n_validation_folds),
        "selected_peer_count": len(selected),
        "redundancy_status": "limited_single_peer" if len(selected) == 1 else "multi_peer",
        "topology_contract": "same-analyte adjacent core; same-pool second-order candidate",
        "selection_rule": "full-period forward validation + controlled injections + terminal test",
        "validation_status": str(decision.decision_status),
        "nominated_before_test": str(decision.nominated_before_test),
        "validation_rationale": str(decision.rationale),
    }
