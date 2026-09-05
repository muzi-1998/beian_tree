"""Historical-only candidate D2 as-of adapter; frozen thresholds, no interpolation.

Not a replacement for the published D2 entry point. Raw timestamp defects stay
unobservable in aligned exports. Sensitive peer diagnostics remain out of scope.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from causal_gap_evidence import causal_gap_evidence


def preprocess(raw: pd.DataFrame, pipeline) -> dict[str, pd.DataFrame]:
    result = {}
    for ch in pipeline.SCORED_CHANNELS:
        values = raw[ch]
        cfg = pipeline._d2_cfg.sensors[ch]
        kind = "DO" if ch.startswith("DO") else "ORP"
        defaults = pipeline.ENG_DEFAULTS
        precision = defaults[f"precision_{kind}"]
        iqr_limit = defaults[f"tau_iqr_{kind}"]
        gap = causal_gap_evidence(values, defaults["short_gap_max_min"])
        present = values.notna()
        same = values.diff().abs().lt(precision) & present & present.shift(fill_value=False)
        rle = pipeline.consecutive_run_len(same)
        iqr = values.rolling("30min", min_periods=15).quantile(.75) - values.rolling("30min", min_periods=15).quantile(.25)
        evidence = pipeline.route_availability_evidence(
            aligned_value=values, missing=~present, long_gap=gap.long_gap_asof,
            rle_run_min=rle, hard_rle_run_min=rle, rolling_iqr=iqr,
            low_iqr_threshold=iqr_limit, lenient_rle_min=defaults["tau_rle_D2_min"],
            hard_rle_min=defaults["tau_rle_D1_min"], availability_mode=cfg.availability_mode,
            process_floor_threshold=cfg.process_floor_threshold)
        flags = evidence.astype(np.int8)
        flags["present_raw"] = present.astype(np.int8)
        flags["missing"] = (~present).astype(np.int8)
        flags["value_gap_recovery"] = gap.completed_gap_length_known_now.notna().astype(np.int8)
        flags["imputed"] = np.int8(0)
        flags["long_gap"] = gap.long_gap_asof.astype(np.int8)
        flags["info_empty"] = flags["any_information_unavailable"]
        flags["freeze_candidate"] = flags["sensor_freeze"]
        flags["qha_unavailable"] = flags["hard_availability_loss"]
        flags["raw_value"] = values
        flags["aligned_value"] = values
        flags["rle_run_min"] = rle
        flags["hard_rle_run_min"] = rle
        flags["rolling_iqr"] = iqr
        flags["P95_asof"] = gap.P95_completed_gap_24h_asof
        result[ch] = flags
    return result


def window_stats(flags: dict[str, pd.DataFrame], pipeline) -> dict[str, pd.DataFrame]:
    result = pipeline.compute_window_stats(flags)
    for ch, frame in result.items():
        frame["P95_gap_min"] = flags[ch].P95_asof.resample("h").last().reindex(frame.index)
        # A partial current hour is not a released hour. The whole history is
        # retained here; a future streaming adapter must checkpoint its state.
        last_available = flags[ch].index[-1] + pd.Timedelta(minutes=1)
        result[ch] = frame.loc[frame.index + pd.Timedelta(hours=1) <= last_available]
    return result
