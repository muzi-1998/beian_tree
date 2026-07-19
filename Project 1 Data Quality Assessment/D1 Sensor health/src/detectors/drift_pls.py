"""PLS virtual-sensor drift detector with auditable blocked-CV peer selection."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler

from .base import BaseDetector, DetectorResult


def _parse_sensor(channel: str) -> tuple[str | None, int | None, int | None]:
    parts = channel.split("_")
    if len(parts) == 3 and parts[0] in {"DO", "ORP"}:
        return parts[0], int(parts[1]), int(parts[2])
    return None, None, None


def core_engineered_peers(
    target: str,
    all_columns: list[str],
    excluded_predictors: set[str] | None = None,
) -> list[str]:
    """Return process-defensible same-analyte structural peers.

    Numeric suffix equality is not treated as evidence that DO and ORP sensors
    are co-located. Cross-analyte predictors therefore require an external
    topology contract and are excluded from the D1 default model.
    """
    columns = set(all_columns) - set(excluded_predictors or set())
    kind, pool, segment = _parse_sensor(target)
    if kind is None:
        return []
    peers = set()
    for offset in (-1, 1):
        candidate = f"{kind}_{pool}_{segment + offset}"
        if candidate in columns:
            peers.add(candidate)
    twin_pool = 2 if pool == 1 else 1
    twin = f"{kind}_{twin_pool}_{segment}"
    if twin in columns:
        peers.add(twin)
    peers.discard(target)
    return sorted(peers)


def candidate_same_analyte_peers(
    target: str,
    all_columns: list[str],
    core_peers: list[str] | None = None,
    excluded_predictors: set[str] | None = None,
) -> list[str]:
    kind, _, _ = _parse_sensor(target)
    core = set(core_peers or [])
    excluded = set(excluded_predictors or set())
    return sorted(
        channel for channel in all_columns
        if channel != target and channel not in core and channel not in excluded
        and _parse_sensor(channel)[0] == kind
    )


def engineered_peers(target: str, all_columns: list[str]) -> list[str]:
    """Backward-compatible alias for the revised structural core."""
    return core_engineered_peers(target, all_columns)


def _blocked_cv_errors(
    df_hourly: pd.DataFrame,
    target: str,
    peers: list[str],
    n_components: int = 3,
    train_days: int = 21,
    validation_days: int = 7,
    n_folds: int = 3,
) -> np.ndarray:
    train_h = train_days * 24
    validation_h = validation_days * 24
    required = train_h + n_folds * validation_h
    if len(df_hourly) < required or not peers:
        return np.array([], dtype=float)

    errors = []
    for fold in range(n_folds):
        train_start = fold * validation_h
        train_end = train_start + train_h
        validation_end = train_end + validation_h
        block = df_hourly.loc[:, [target, *peers]].iloc[train_start:validation_end].copy()
        train = block.iloc[:train_h]
        medians = train.median(axis=0).fillna(0.0)
        block = block.ffill().fillna(medians).fillna(0.0)
        train = block.iloc[:train_h]
        validation = block.iloc[train_h:]

        sx = StandardScaler().fit(train[peers].to_numpy(dtype=float))
        sy = StandardScaler().fit(train[[target]].to_numpy(dtype=float))
        x_train = sx.transform(train[peers].to_numpy(dtype=float))
        y_train = sy.transform(train[[target]].to_numpy(dtype=float)).ravel()
        components = min(n_components, len(peers), len(train) - 1)
        model = PLSRegression(n_components=max(1, components), scale=False)
        model.fit(x_train, y_train)
        prediction_s = model.predict(
            sx.transform(validation[peers].to_numpy(dtype=float))
        ).ravel()
        prediction = sy.inverse_transform(prediction_s.reshape(-1, 1)).ravel()
        observed = validation[target].to_numpy(dtype=float)
        train_scale = max(float(train[target].std(ddof=0)), 1e-9)
        errors.append(float(np.sqrt(np.mean((observed - prediction) ** 2)) / train_scale))
    return np.asarray(errors, dtype=float)


def select_pls_peers(
    df_hourly: pd.DataFrame,
    target: str,
    n_components: int = 3,
    min_improvement: float = 0.02,
    max_tail_degradation: float = 0.05,
    excluded_predictors: set[str] | None = None,
) -> dict:
    """Greedily add same-analyte peers only when blocked CV supports them."""
    columns = list(df_hourly.columns)
    excluded = set(excluded_predictors or set())
    core = core_engineered_peers(target, columns, excluded)
    candidates = candidate_same_analyte_peers(target, columns, core, excluded)
    if len(core) < 2:
        core = sorted(
            channel for channel in columns
            if channel != target and channel not in excluded
            and _parse_sensor(channel)[0] == _parse_sensor(target)[0]
        )[:2]
        candidates = candidate_same_analyte_peers(target, columns, core, excluded)
    if not core:
        raise ValueError(f"No same-analyte PLS peers are available for {target}")

    selected = list(core)
    core_errors = _blocked_cv_errors(df_hourly, target, selected, n_components)
    if core_errors.size == 0:
        raise ValueError(f"Insufficient data for blocked-CV peer selection: {target}")
    current_errors = core_errors
    remaining = list(candidates)
    additions = []
    while remaining:
        trial_results = []
        current_median = float(np.median(current_errors))
        current_tail = float(np.quantile(current_errors, 0.90))
        for candidate in remaining:
            errors = _blocked_cv_errors(
                df_hourly, target, [*selected, candidate], n_components
            )
            if errors.size:
                trial_results.append((float(np.median(errors)), candidate, errors))
        if not trial_results:
            break
        trial_median, candidate, errors = min(trial_results, key=lambda item: item[0])
        improvement = (current_median - trial_median) / max(current_median, 1e-9)
        tail_ok = float(np.quantile(errors, 0.90)) <= current_tail * (1.0 + max_tail_degradation)
        if improvement < min_improvement or not tail_ok:
            break
        selected.append(candidate)
        remaining.remove(candidate)
        current_errors = errors
        additions.append(candidate)

    core_median = float(np.median(core_errors))
    selected_median = float(np.median(current_errors))
    return {
        "target": target,
        "core_peers": core,
        "candidate_peers": candidates,
        "selected_peers": selected,
        "selected_noncore_peers": additions,
        "core_cv_nrmse_median": core_median,
        "core_cv_nrmse_p90": float(np.quantile(core_errors, 0.90)),
        "selected_cv_nrmse_median": selected_median,
        "selected_cv_nrmse_p90": float(np.quantile(current_errors, 0.90)),
        "cv_improvement_pct": 100.0 * (core_median - selected_median) / max(core_median, 1e-9),
        "n_blocked_folds": int(len(current_errors)),
        "selection_rule": "same-analyte core + blocked-CV forward selection",
    }


class PLSVirtualSensorDetector(BaseDetector):
    """Static 21-day PLS virtual sensor using an externally audited peer set."""

    name = "pls_virtual"

    def __init__(self, n_components: int = 3, train_days: int = 21):
        super().__init__(n_components=n_components, train_days=train_days)
        self.k = n_components
        self.train_days = train_days
        self._models = {}

    def fit(self, df_hourly: pd.DataFrame, target: str, peer_cols: list[str], **ctx):
        n_train = self.train_days * 24
        frame = df_hourly.loc[:, [target, *peer_cols]].copy()
        medians = frame.iloc[:n_train].median(axis=0).fillna(0.0)
        frame = frame.ffill().fillna(medians).fillna(0.0)
        x_train = frame.loc[:, peer_cols].iloc[:n_train].to_numpy(dtype=float)
        y_train = frame.loc[:, target].iloc[:n_train].to_numpy(dtype=float)
        sx = StandardScaler().fit(x_train)
        sy = StandardScaler().fit(y_train.reshape(-1, 1))
        x_scaled = sx.transform(x_train)
        y_scaled = sy.transform(y_train.reshape(-1, 1)).ravel()
        components = min(self.k, len(peer_cols), len(x_scaled) - 1)
        model = PLSRegression(n_components=max(1, components), scale=False).fit(
            x_scaled, y_scaled
        )
        train_prediction_s = model.predict(x_scaled).ravel()
        train_prediction = sy.inverse_transform(train_prediction_s.reshape(-1, 1)).ravel()
        sigma_y = max(float(np.std(y_train)), 1e-9)
        sigma_residual = max(float(np.std(y_train - train_prediction)), 0.05 * sigma_y, 1e-9)
        self._models[target] = (model, sx, sy, sigma_residual, medians, list(peer_cols))

    def score(
        self,
        df_hourly: pd.DataFrame,
        target: str,
        peer_cols: list[str] | None = None,
        selection_audit: dict | None = None,
        **ctx,
    ) -> DetectorResult:
        if peer_cols is None:
            peer_cols = core_engineered_peers(target, list(df_hourly.columns))
        if target not in self._models:
            self.fit(df_hourly, target=target, peer_cols=peer_cols)
        model, sx, sy, sigma_residual, medians, peers_used = self._models[target]
        frame = df_hourly.loc[:, [target, *peers_used]].copy()
        frame = frame.ffill().fillna(medians).fillna(0.0)
        prediction_s = model.predict(
            sx.transform(frame.loc[:, peers_used].to_numpy(dtype=float))
        ).ravel()
        prediction = sy.inverse_transform(prediction_s.reshape(-1, 1)).ravel()
        residual = frame[target].to_numpy(dtype=float) - prediction
        residual_z = pd.Series(np.abs(residual) / sigma_residual, index=df_hourly.index)
        flag = (residual_z > 3.0).astype(np.int8)
        metadata = {
            "n_components": self.k,
            "train_days": self.train_days,
            "sigma_residual": sigma_residual,
            "peer_cols": peers_used,
            "peer_selection_rule": "same-analyte blocked-CV v1",
        }
        if selection_audit:
            metadata["peer_selection_audit"] = selection_audit
        return DetectorResult(
            sensor_id=target,
            detector_name=self.name,
            timestamps=df_hourly.index,
            raw_score=residual_z,
            aux_flag=flag,
            metadata=metadata,
        )
