from __future__ import annotations

import numpy as np


def mad_scale(values: np.ndarray, axis: int = 0, epsilon: float = 1e-6) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    center = np.nanmedian(values, axis=axis, keepdims=True)
    scale = 1.4826 * np.nanmedian(np.abs(values - center), axis=axis)
    return np.maximum(scale, epsilon)


def robust_center_scale(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=float)
    return np.nanmedian(values, axis=0), mad_scale(values, axis=0)


def huber_squared(values: np.ndarray, c: float = 2.5) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    clipped = np.clip(values, -c, c)
    return clipped * clipped


def normalized_entropy(probabilities: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(probabilities, dtype=float)
    safe = np.clip(probabilities, 1e-12, 1.0)
    entropy = -np.sum(safe * np.log(safe), axis=1)
    return entropy / np.log(probabilities.shape[1])
