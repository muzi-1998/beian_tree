"""src/detectors/base.py
Unified detector base class & result structure (spec §4.3).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np
import pandas as pd


@dataclass
class DetectorResult:
    """All detectors return this structure."""
    sensor_id: str
    detector_name: str
    timestamps: pd.DatetimeIndex
    raw_score: pd.Series        # detector-native metric
    aux_flag: pd.Series         # 0/1 binary alarm flag (per native rule)
    metadata: Dict = field(default_factory=dict)


class BaseDetector:
    """Stateful base class.  Subclasses override fit/score."""
    name: str = "base"

    def __init__(self, **kwargs):
        self.params = kwargs

    def fit(self, ref_series: pd.Series, **ctx):
        """Optional one-time fit (training period)."""
        pass

    def score(self, series: pd.Series, **ctx) -> DetectorResult:
        raise NotImplementedError
