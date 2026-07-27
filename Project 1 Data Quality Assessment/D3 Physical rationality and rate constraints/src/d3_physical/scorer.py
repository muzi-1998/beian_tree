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
    Q_rate: float


class D3ScoreMapper:
    def __init__(self, mapping_cfg: dict):
        self.cfg = mapping_cfg

    def map(self, value_evidence, rate_evidence) -> SubScores:
        ch = self.cfg["Q_value_hard"]
        cs = self.cfg["Q_value_soft"]
        cr = self.cfg["Q_rate"]
        return SubScores(
            Q_value_hard=logistic_zero_anchored(
                value_evidence.hard_violation_rate, ch["x0"], ch["k"]
            ),
            Q_value_soft=logistic_zero_anchored(
                value_evidence.soft_violation_rate, cs["x0"], cs["k"]
            ),
            Q_rate=logistic_zero_anchored(
                rate_evidence.rate_hard_violation_rate, cr["x0"], cr["k"]
            ),
        )
