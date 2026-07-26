from __future__ import annotations

import numpy as np


def graph_energy(values: np.ndarray, edges: list[tuple[int, int, float]]) -> float:
    values = np.asarray(values, dtype=float)
    total = 0.0
    used = 0
    for source, target, weight in edges:
        if np.isfinite(values[source]) and np.isfinite(values[target]):
            total += float(weight) * float(values[source] - values[target]) ** 2
            used += 1
    return total / used if used else float("nan")
