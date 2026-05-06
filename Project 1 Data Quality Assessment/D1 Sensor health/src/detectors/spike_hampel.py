"""src/detectors/spike_hampel.py
Spike detector — Hampel filter (rolling MAD-based robust z) per spec §5.
Aux: residual 3σ on de-periodised series.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseDetector, DetectorResult


class HampelSpikeDetector(BaseDetector):
    name = "hampel"

    def __init__(self, window_min: int = 21, k: float = 3.0):
        super().__init__(window_min=window_min, k=k)
        self.win = window_min
        self.k = k

    def score(self, series: pd.Series, **ctx) -> DetectorResult:
        # Rolling median & MAD; spec §5 — fast/short window
        med = series.rolling(self.win, center=True, min_periods=max(5, self.win // 4)).median()
        mad = (series - med).abs().rolling(self.win, center=True,
                                           min_periods=max(5, self.win // 4)).median()
        # 1.4826 = consistency constant for Gaussian σ ≈ 1.4826·MAD
        sigma_est = 1.4826 * mad.replace(0, np.nan)
        robust_z = (series - med).abs() / sigma_est
        flag = (robust_z > self.k).astype(np.int8)
        return DetectorResult(
            sensor_id=series.name, detector_name=self.name,
            timestamps=series.index, raw_score=robust_z, aux_flag=flag,
            metadata={"window_min": self.win, "k": self.k},
        )
