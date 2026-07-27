from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.covariance import LedoitWolf, OAS


@dataclass(frozen=True)
class CovarianceFit:
    covariance: np.ndarray
    precision: np.ndarray
    shrinkage: float
    condition_number: float
    minimum_eigen_ratio: float
    method: str


def _diagnostics(covariance: np.ndarray) -> tuple[float, float]:
    eigenvalues = np.linalg.eigvalsh(covariance)
    largest = max(float(np.max(eigenvalues)), 1e-12)
    smallest = max(float(np.min(eigenvalues)), 0.0)
    return float(np.linalg.cond(covariance)), smallest / largest


def fit_shrinkage_covariance(
    values: np.ndarray,
    *,
    method: str = "oas",
    alpha_floor: float = 0.0,
    diagonal_only: bool = False,
) -> CovarianceFit:
    values = np.asarray(values, dtype=float)
    complete = values[np.isfinite(values).all(axis=1)]
    if complete.shape[0] < max(10, complete.shape[1] + 2):
        raise ValueError("Insufficient complete observations for covariance fitting")
    estimator = OAS(store_precision=False) if method == "oas" else LedoitWolf(store_precision=False)
    estimator.fit(complete)
    sample = np.cov(complete, rowvar=False)
    target = np.diag(np.diag(sample))
    alpha = max(float(estimator.shrinkage_), float(alpha_floor))
    covariance = (1.0 - alpha) * sample + alpha * target
    if diagonal_only:
        covariance = target
        alpha = 1.0
    covariance = covariance + np.eye(covariance.shape[0]) * 1e-9
    condition, eigen_ratio = _diagnostics(covariance)
    return CovarianceFit(
        covariance=covariance,
        precision=np.linalg.pinv(covariance),
        shrinkage=alpha,
        condition_number=condition,
        minimum_eigen_ratio=eigen_ratio,
        method="diagonal_robust_z" if diagonal_only else method,
    )
