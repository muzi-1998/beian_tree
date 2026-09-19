"""Historical short-gap publication contract, with bounded checkpoint replay."""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from runtime import PROJECT, OFFICIAL, OUTPUT, START, sha256, write_json
from minute_alignment_contract import BoundedMinuteAligner, align_bounded

sys.path.insert(0, str(PROJECT / "1.1 Decomposition"))
from src.data.preprocess import align_min, mark_transition_zones, mark_outliers_iqr
from src.semantics import MIN_CHANNELS, PHYS_RANGE


def main():
    root = OFFICIAL / "1.1 Decomposition/outputs/parquet"
    source = root / "time_base_1min_raw.parquet"
    if sha256(source) != "df2acf4d548b8e6faee0bda3c73ea195fe131ca56a4fa8e8f3a72614c71dd7e5":
        raise ValueError("Historical raw grid does not match the frozen source")
    raw = pd.read_parquet(source)[MIN_CHANNELS]
    if raw.index.max() >= START:
        raise ValueError("New-period data forbidden in this audit")
    archive = pd.read_parquet(root / "time_base_1min.parquet")[MIN_CHANNELS].reindex(raw.index)
    archived_flags = pd.read_parquet(root / "time_base_1min_flags.parquet")[MIN_CHANNELS].reindex(raw.index)
    original, original_flags = align_min(raw, short_gap_min=3)
    diagnostic_flags = mark_outliers_iqr(original, mark_transition_zones(original_flags, transition_h=24), k=1.5)
    ranges = {sensor: PHYS_RANGE[sensor] for sensor in MIN_CHANNELS}
    candidate, candidate_flags = align_bounded(raw, ranges)
    stream = BoundedMinuteAligner(ranges)
    values, flags = [], []
    for start in range(0, len(raw), 1440):
        chunk = raw.iloc[start:start+1440]
        released, flag, available = stream.advance(chunk)
        assert (available <= chunk.index[-1]).all()
        values.append(released)
        flags.append(flag)
        stream = BoundedMinuteAligner(ranges, checkpoint=json.loads(json.dumps(stream.checkpoint())))
    replay, replay_flags = pd.concat(values), pd.concat(flags)
    rows = []
    for sensor in MIN_CHANNELS:
        delta = (original[sensor]-archive[sensor]).abs()
        changed = candidate_flags[sensor].ne(original_flags[sensor]) | (candidate[sensor]-original[sensor]).abs().gt(1e-10)
        changed |= candidate[sensor].isna().ne(original[sensor].isna())
        chunk_na = replay[sensor].isna().ne(candidate[sensor].reindex(replay.index).isna())
        chunk_delta = (replay[sensor]-candidate[sensor].reindex(replay.index)).abs()
        rows.append({"sensor_id": sensor, "n_minutes": len(raw), "n_released_minutes": len(replay),
            "native_vs_archive_max_abs": float(delta.max()),
            "native_vs_archive_NA_differences": int(original[sensor].isna().ne(archive[sensor].isna()).sum()),
            "native_vs_archive_flag_differences": int(original_flags[sensor].ne(archived_flags[sensor]).sum()),
            "archived_diagnostic_flag_replay_differences": int(diagnostic_flags[sensor].ne(archived_flags[sensor]).sum()),
            "candidate_vs_native_changed_minutes": int(changed.sum()),
            "candidate_short_fill_count": int(candidate_flags[sensor].eq(1).sum()),
            "range_ineligible_count": int(candidate_flags[sensor].eq(7).sum()),
            "chunk_max_abs": float(chunk_delta.max()), "chunk_NA_differences": int(chunk_na.sum()),
            "chunk_flag_differences": int(replay_flags[sensor].ne(candidate_flags[sensor].reindex(replay.index)).sum())})
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/minute_alignment_historical_replay.csv", index=False)
    qa = {"scope": "minute_preprocessing_only_not_full_raw_to_D1",
        "raw_sha256": sha256(source), "n_channels": len(table), "minutes_per_channel": len(raw),
        "native_replay_passed": bool(table.native_vs_archive_max_abs.lt(1e-10).all()
            and table.native_vs_archive_NA_differences.eq(0).all()
            and table.archived_diagnostic_flag_replay_differences.eq(0).all()),
        "alignment_only_vs_archived_diagnostic_flags": "expected_difference_from_offline_transition_5_and_outlier_8_overlays",
        "offline_diagnostic_overlays_used_in_causal_value_transform": False,
        "candidate_changed_channel_minutes": int(table.candidate_vs_native_changed_minutes.sum()),
        "daily_checkpoint_passed": bool(table.chunk_max_abs.lt(1e-10).all()
            and table.chunk_NA_differences.eq(0).all() and table.chunk_flag_differences.eq(0).all()),
        "fixed_preprocessing_publication_delay_minutes": 3,
        "tail_minutes_not_yet_released_per_channel": len(raw)-len(replay),
        "range_thresholds_role": "inherited_decomposition_eligibility_not_D3_safety_bounds",
        "raw_missingness_for_D2": "original_raw_only_never_filled_transform",
        "holdout_opened": False}
    write_json(OUTPUT / "audit/minute_alignment_replay_qa.json", qa)
    write_json(OUTPUT / "assets/minute_alignment_contract.json", {"ranges": ranges,
        "short_gap_min": 3, "publication_delay_min": 3, "source": "frozen_section_1_1_preprocessing_contract",
        "range_invalid_never_filled": True, "complete_invalid_span_short": True,
        "raw_observations_preserved": True, "temperature_route": "separate_native_minute_source"})
    print(table.to_string(index=False), flush=True)
    print(json.dumps(qa), flush=True)


if __name__ == "__main__":
    main()
