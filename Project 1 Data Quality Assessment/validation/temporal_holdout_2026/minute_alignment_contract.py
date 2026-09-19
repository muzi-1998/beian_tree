"""Bounded-delay minute preprocessing; raw observations remain a separate input.

An entire invalid/missing span must be short, with two valid endpoints. A fixed
three-minute publication delay prevents an unfinished gap from being backfilled
after a value/flag was already released. Range-invalid values are never imputed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from runtime import content_hash


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_clock(frame):
    index = frame.index
    if (frame.empty or not isinstance(index, pd.DatetimeIndex) or index.tz is not None
            or not index.is_unique or not index.is_monotonic_increasing
            or not index.equals(index.floor("min"))
            or (len(index) > 1 and not index.to_series().diff().dropna().eq(pd.Timedelta(minutes=1)).all())):
        raise ValueError("Require a complete naive Asia/Shanghai minute clock, with explicit missing rows")


def align_bounded(frame: pd.DataFrame, ranges: dict, short_gap_min: int = 3):
    validate_clock(frame)
    clean = frame.astype(float).copy()
    flags = pd.DataFrame(0, index=frame.index, columns=frame.columns, dtype=np.int8)
    for sensor in clean:
        low, high = ranges[sensor]
        bad = clean[sensor].notna() & (~np.isfinite(clean[sensor]) | ~clean[sensor].between(low, high))
        clean.loc[bad, sensor] = np.nan
        flags.loc[bad, sensor] = 7
        original_missing = frame[sensor].isna()
        flags.loc[original_missing, sensor] = 2
        unavailable = clean[sensor].isna()
        groups = unavailable.ne(unavailable.shift(fill_value=False)).cumsum()
        total_span = unavailable.groupby(groups).transform("sum")
        candidate = clean[sensor].interpolate(method="linear", limit_area="inside")
        fillable = original_missing & total_span.le(short_gap_min) & candidate.notna()
        clean.loc[fillable, sensor] = candidate.loc[fillable]
        flags.loc[fillable, sensor] = 1
    return clean, flags


class BoundedMinuteAligner:
    def __init__(self, ranges: dict, short_gap_min: int = 3, checkpoint: dict | None = None):
        if not isinstance(short_gap_min, int) or short_gap_min < 1:
            raise ValueError("A positive fixed short-gap limit is required")
        self.ranges = json.loads(json.dumps(ranges))
        if any(len(v) != 2 or not np.isfinite(v).all() or v[0] >= v[1] for v in self.ranges.values()):
            raise ValueError("Invalid transformation eligibility range")
        self.delay = short_gap_min
        self.columns = list(ranges)
        self.binding = digest({"ranges": self.ranges, "column_order": self.columns,
                               "delay": self.delay, "code": content_hash(Path(__file__))})
        self.tail = pd.DataFrame(columns=self.columns, index=pd.DatetimeIndex([]), dtype=float)
        self.last_released = None
        if checkpoint is not None:
            unsigned = {k: v for k, v in checkpoint.items() if k != "sha256"}
            if checkpoint.get("binding") != self.binding or digest(unsigned) != checkpoint.get("sha256"):
                raise ValueError("Checkpoint differs from frozen alignment policy or content")
            self.tail = pd.DataFrame(checkpoint["tail_values"], columns=self.columns,
                                     index=pd.to_datetime(checkpoint["tail_index"]), dtype=float)
            self.last_released = pd.Timestamp(checkpoint["last_released"]) if checkpoint["last_released"] else None

    def advance(self, raw: pd.DataFrame):
        validate_clock(raw)
        if list(raw.columns) != self.columns:
            raise ValueError("Channel order differs from the frozen alignment contract")
        if len(self.tail) and raw.index[0] != self.tail.index[-1] + pd.Timedelta(minutes=1):
            raise ValueError("Raw chunks must be adjacent; represent skipped minutes explicitly")
        joined = raw.astype(float) if self.tail.empty else pd.concat([self.tail, raw.astype(float)])
        values, flags = align_bounded(joined, self.ranges, self.delay)
        cutoff = raw.index[-1] - pd.Timedelta(minutes=self.delay)
        keep = joined.index <= cutoff
        if self.last_released is not None:
            keep &= joined.index > self.last_released
        emitted = values.loc[keep]
        if len(emitted):
            self.last_released = emitted.index[-1]
        # Retain the left endpoint until every minute of a short gap is released.
        self.tail = joined.iloc[-(2*self.delay+1):].copy()
        available = pd.Series(emitted.index+pd.Timedelta(minutes=self.delay), index=emitted.index,
                               name="preprocessing_available_at")
        return emitted, flags.loc[keep], available

    def checkpoint(self):
        result = {"schema": "bounded-minute-alignment-v1", "binding": self.binding,
            "tail_index": [t.isoformat() for t in self.tail.index],
            "tail_values": self.tail.astype(object).where(self.tail.notna(), None).values.tolist(),
            "last_released": self.last_released.isoformat() if self.last_released is not None else None}
        result["sha256"] = digest(result)
        return result
