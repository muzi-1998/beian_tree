"""Map independent D3 evidence rates to 1-5 quality sub-scores."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def logistic_zero_anchored(value: float, x0: float, k: float) -> float:
    """Descending logistic normalized so zero violations maps exactly to 5."""
    if not np.isfinite(value):
        return float("nan")
    raw = 1.0 + 4.0 / (1.0 + np.exp(k * (value - x0)))
    baseline = 1.0 + 4.0 / (1.0 + np.exp(-k * x0))
    score = 1.0 + 4.0 * (raw - 1.0) / (baseline - 1.0)
    return float(np.clip(score, 1.0, 5.0))


@dataclass(frozen=True)
class SubScores:
    Q_value_hard: float
    Q_value_soft: float
    Q_persistent_rate: float
    Q_persistent_rate_soft_only: float = 5.0
    Q_persistent_rate_hard: float = 5.0

    @property
    def Q_rate(self) -> float:
        """Backward-compatible alias; new outputs use Q_persistent_rate."""
        return self.Q_persistent_rate


class D3ScoreMapper:
    def __init__(self, mapping_cfg: dict):
        self.cfg = mapping_cfg
        component_weights = mapping_cfg["Q_persistent_rate"]["component_weights"]
        if not np.isclose(sum(component_weights.values()), 1.0):
            raise ValueError("Persistent-rate component weights must sum to 1.0")

    def map(self, value_evidence, rate_evidence) -> SubScores:
        ch = self.cfg["Q_value_hard"]
        cs = self.cfg["Q_value_soft"]
        cr = self.cfg["Q_persistent_rate"]
        soft_cfg = cr["soft_only"]
        hard_cfg = cr["hard"]
        q_soft_only = logistic_zero_anchored(
            rate_evidence.rate_soft_only_violation_rate,
            soft_cfg["x0"],
            soft_cfg["k"],
        )
        q_hard = logistic_zero_anchored(
            rate_evidence.rate_hard_violation_rate,
            hard_cfg["x0"],
            hard_cfg["k"],
        )
        rate_weights = cr["component_weights"]
        q_persistent = (
            float(rate_weights["soft_only"]) * q_soft_only
            + float(rate_weights["hard"]) * q_hard
        )
        return SubScores(
            Q_value_hard=logistic_zero_anchored(
                value_evidence.hard_violation_rate, ch["x0"], ch["k"]
            ),
            Q_value_soft=logistic_zero_anchored(
                value_evidence.soft_violation_rate, cs["x0"], cs["k"]
            ),
            Q_persistent_rate=float(q_persistent),
            Q_persistent_rate_soft_only=float(q_soft_only),
            Q_persistent_rate_hard=float(q_hard),
        )
