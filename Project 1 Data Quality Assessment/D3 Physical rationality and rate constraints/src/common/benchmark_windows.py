"""
Benchmark-window selection for fixed D3 diagnostic thresholds.

Cross-dimension benchmark window set. Selects high-quality windows from raw
data via simple heuristics (low rate variance, no NaN, within nominal range),
then precomputes per-sensor fixed quantiles used by D3 boundary tail_rate
thresholds (FIXED — not recomputed per evaluation window).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.version import BENCHMARK_VERSION


@dataclass(frozen=True)
class FixedTailThreshold:
    sensor: str
    side: str            # "low" or "high"
    value: float
    source: str          # "benchmark_quantile" / "instrument" / "expert"
    version: str
    benchmark_window_ids: tuple


class BenchmarkWindows:
    """Manages benchmark windows and precomputed fixed tail quantiles."""

    def __init__(self, df_main: pd.DataFrame, sensors: list[str],
                 window_hours: int = 24, target_n_windows: int = 60,
                 q_low: float = 0.01, q_high: float = 0.99):
        self.df_main = df_main
        self.sensors = sensors
        self.window_hours = window_hours
        self.target_n_windows = target_n_windows
        self.q_low = q_low
        self.q_high = q_high
        self.window_ids: list[str] = []
        self.window_index: dict[str, tuple] = {}      # win_id -> (start, end)
        self._fixed_tails: dict[tuple[str, str], FixedTailThreshold] = {}
        self.version = BENCHMARK_VERSION

    def select(self) -> "BenchmarkWindows":
        """Pick `target_n_windows` benchmark windows: per-window dispersion ranking."""
        df = self.df_main
        n_per_window = self.window_hours * 60
        candidates = []
        # stride windows by half window for variety
        stride = n_per_window // 2
        for i in range(0, len(df) - n_per_window, stride):
            seg = df.iloc[i:i + n_per_window]
            quality = self._window_quality(seg)
            if quality is None:
                continue
            candidates.append((i, seg.index[0], seg.index[-1], quality))
        # Sort by quality score descending, pick top-N
        candidates.sort(key=lambda r: r[3], reverse=True)
        chosen = candidates[: self.target_n_windows]
        for k, (i, ts0, ts1, q) in enumerate(chosen):
            wid = f"BW{k:03d}"
            self.window_ids.append(wid)
            self.window_index[wid] = (ts0, ts1)
        # precompute fixed tails
        all_segs = pd.concat([self.df_main.loc[ts0:ts1] for (ts0, ts1) in self.window_index.values()])
        for s in self.sensors:
            if s in all_segs.columns:
                x = all_segs[s].dropna()
                if len(x) > 50:
                    vlow = float(np.quantile(x, self.q_low))
                    vhigh = float(np.quantile(x, self.q_high))
                    self._fixed_tails[(s, "low")] = FixedTailThreshold(
                        sensor=s, side="low", value=vlow, source="benchmark_quantile",
                        version=self.version, benchmark_window_ids=tuple(self.window_ids))
                    self._fixed_tails[(s, "high")] = FixedTailThreshold(
                        sensor=s, side="high", value=vhigh, source="benchmark_quantile",
                        version=self.version, benchmark_window_ids=tuple(self.window_ids))
        return self

    @staticmethod
    def _window_quality(seg: pd.DataFrame) -> float | None:
        """Higher = better. Penalize NaNs and extreme variance / outliers."""
        if seg.isna().mean().mean() > 0.02:
            return None
        sensor_cols = [c for c in seg.columns if c != "data"]
        # use coefficient of variation as a stability proxy; lower CV = more stable
        cvs = []
        for c in sensor_cols:
            x = seg[c].dropna()
            if len(x) < 30:
                continue
            m, sd = float(np.mean(x)), float(np.std(x))
            if m == 0:
                continue
            cvs.append(sd / (abs(m) + 1e-3))
        if not cvs:
            return None
        # quality = -mean CV
        return -float(np.mean(cvs))

    def get_fixed_tail_threshold(self, sensor: str, side: str,
                                 source_allowed=("benchmark_quantile", "instrument", "expert")
                                 ) -> FixedTailThreshold:
        """
        Return a fixed tail threshold whose source must
        be in source_allowed (whitelist).
        """
        key = (sensor, side)
        if key not in self._fixed_tails:
            raise KeyError(f"No fixed tail threshold for {sensor}/{side}")
        ft = self._fixed_tails[key]
        if ft.source not in source_allowed:
            from src.common.exceptions import TailRateContractViolation
            raise TailRateContractViolation(
                f"tail threshold source '{ft.source}' not in whitelist {source_allowed}")
        return ft

    def as_dataframe(self) -> pd.DataFrame:
        rows = []
        for (sensor, side), ft in self._fixed_tails.items():
            rows.append({
                "sensor": sensor,
                "side": side,
                "value": ft.value,
                "source": ft.source,
                "version": ft.version,
                "benchmark_window_ids": ",".join(ft.benchmark_window_ids[:5]) + "...",
                "n_benchmark_windows": len(ft.benchmark_window_ids),
            })
        return pd.DataFrame(rows)
