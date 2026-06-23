"""src/pipeline/window_manager.py
WindowManager — unified window slicing for all detectors per工程目录终稿.

Per spec: every detector receives a *view* (lazy slice) rather than the full
DataFrame, and the same window definition is consulted by aggregator (e.g. for
sustained-low evaluation).  This avoids drift between Python-rolling implicit
windows and the spec-defined main_h windows.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Optional, Dict, Iterator, Tuple


class WindowSpec:
    """Pure data-class: minutes/hours window with type tag."""
    def __init__(self, kind: str, length: pd.Timedelta, freq: str = "1h"):
        self.kind = kind   # 'fast' | 'main' | 'confirm'
        self.length = length
        self.freq = freq

    def __repr__(self):
        return f"<WindowSpec kind={self.kind} len={self.length} freq={self.freq}>"


class WindowManager:
    """Provide sliding views over min/h DataFrames for every detector.

    Use case 1 — slicing for streaming style:
        for ts, view in wm.iter_views(df, freq='1h', length='168h'):
            ...

    Use case 2 — pre-fetch a single view as of timestamp:
        view = wm.view_as_of(df, ts, length='24h')

    Detector-specific window catalogue is loaded from configs/windows.yaml.
    """
    def __init__(self, windows_cfg, df_min: pd.DataFrame, df_h: pd.DataFrame):
        self.cfg = windows_cfg
        self.df_min = df_min
        self.df_h = df_h
        self._cache: Dict[str, WindowSpec] = {}
        self._build_catalogue()

    def _build_catalogue(self):
        """Build {detector_kind+role: WindowSpec} from cfg."""
        for det_kind, ws in [("spike",  self.cfg.spike),
                              ("step",   self.cfg.step),
                              ("drift",  self.cfg.drift),
                              ("regime", self.cfg.regime)]:
            for role, h_attr in [("main", "main_h"),
                                  ("fast", "fast_h"),
                                  ("confirm", "confirm_h")]:
                v = getattr(ws, h_attr, None)
                if v is not None:
                    self._cache[f"{det_kind}_{role}"] = WindowSpec(
                        role, pd.Timedelta(hours=float(v)),
                        freq="1h" if det_kind != "spike" else "1min"
                    )
            # drift and regime carry early_h in the extra dict
            early_v = ws.extra.get("early_h") if hasattr(ws, "extra") else None
            if early_v is not None:
                self._cache[f"{det_kind}_early"] = WindowSpec(
                    "early", pd.Timedelta(hours=float(early_v)), freq="1h"
                )

        # Freeze is a dict in cfg.
        # windows.yaml keys: flash_h, hard_h, main_h, sustained_h (all in hours)
        for role, key in [("main",      "main_h"),
                           ("flash",     "flash_h"),
                           ("hard",      "hard_h"),
                           ("sustained", "sustained_h")]:
            if key in self.cfg.freeze:
                v = self.cfg.freeze[key]
                self._cache[f"freeze_{role}"] = WindowSpec(
                    role, pd.Timedelta(hours=float(v)),
                    freq="1min"
                )

    def get_spec(self, key: str) -> WindowSpec:
        if key not in self._cache:
            raise KeyError(f"WindowManager: unknown window key '{key}'. "
                           f"Available: {list(self._cache)}")
        return self._cache[key]

    # ── Streaming view helpers ────────────────────────────────────────────
    def view_as_of(self, df: pd.DataFrame, ts: pd.Timestamp,
                    length: pd.Timedelta) -> pd.DataFrame:
        """Return df slice [ts-length, ts]. Endpoint inclusive."""
        start = ts - length
        return df.loc[(df.index > start) & (df.index <= ts)]

    def iter_views(self, df: pd.DataFrame, freq: str = "1h",
                   length: pd.Timedelta = pd.Timedelta(hours=24),
                   start_at: Optional[pd.Timestamp] = None
                   ) -> Iterator[Tuple[pd.Timestamp, pd.DataFrame]]:
        """Yield (ts, view) pairs at specified update frequency."""
        if start_at is None:
            start_at = df.index[0] + length
        timestamps = pd.date_range(start_at, df.index[-1], freq=freq)
        for ts in timestamps:
            yield ts, self.view_as_of(df, ts, length)

    # ── Pair views (for cross-channel detectors) ──────────────────────────
    def pair_view_as_of(self, df: pd.DataFrame, ts: pd.Timestamp,
                          length: pd.Timedelta,
                          channels: list) -> pd.DataFrame:
        v = self.view_as_of(df, ts, length)
        return v[channels]

    def list_specs(self) -> Dict[str, str]:
        return {k: repr(v) for k, v in self._cache.items()}
