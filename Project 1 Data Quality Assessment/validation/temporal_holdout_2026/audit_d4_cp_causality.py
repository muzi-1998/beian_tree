"""Synthetic audit of global change-point de-duplication versus as-of replay."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from runtime import DIMENSIONS, OUTPUT, PROJECT, write_json
from causal_change_points import causal_change_timeline

sys.path.insert(0, str(PROJECT / DIMENSIONS["D4"] / "src"))
from d4.scoring import adjacent_ks_change_timeline, compare_change_points

PARAMS = dict(auxiliary_window_days=7, adjacent_segment_hours=12,
              candidate_step_hours=6, ks_stat_min=.35, pvalue_max=.01,
              min_valid_fraction=.8)


def replay_asof(series: pd.Series, output_index: pd.DatetimeIndex) -> pd.DataFrame:
    # Audit oracle, not a production implementation: recomputes each information
    # set independently so future candidates cannot replace past representatives.
    rows = []
    for available in output_index:
        known = series.loc[series.index < available]
        rows.append(adjacent_ks_change_timeline(known, pd.DatetimeIndex([available]), **PARAMS))
    return pd.DataFrame([row.iloc[0].to_dict() for row in rows], index=output_index)


def main() -> None:
    index = pd.date_range("2026-02-01", periods=120, freq="h")
    t = np.arange(len(index))
    reference = pd.Series(np.sin(t * 1.7) * .1, index=index)
    # Three deterministic levels; no held-out plant measurements are used.
    target = reference + np.where(t < 42, 0., np.where(t < 60, 1., 3.))
    boundary = 60
    at = index[boundary]
    output = index[24:]
    prefix_output = output[output <= at]
    full = adjacent_ks_change_timeline(target, output, **PARAMS)
    prefix = adjacent_ks_change_timeline(target.iloc[:boundary], prefix_output, **PARAMS)
    independent = replay_asof(target, output)
    prefix_independent = replay_asof(target.iloc[:boundary], prefix_output)
    pd.testing.assert_frame_equal(prefix_independent, independent.loc[prefix_output])
    corrected = causal_change_timeline(target, output, **PARAMS)
    corrected_prefix = causal_change_timeline(target.iloc[:boundary], prefix_output, **PARAMS)
    pd.testing.assert_frame_equal(corrected, independent)
    pd.testing.assert_frame_equal(corrected_prefix, corrected.loc[prefix_output])
    ref = adjacent_ks_change_timeline(reference, output, **PARAMS)
    ref_prefix = adjacent_ks_change_timeline(reference.iloc[:boundary], prefix_output, **PARAMS)
    old_q = compare_change_points(full, ref).Q_cp
    prefix_q = compare_change_points(prefix, ref_prefix).Q_cp
    asof_q = compare_change_points(independent, replay_asof(reference, output)).Q_cp
    same_time = prefix.cp_time.eq(full.loc[prefix_output].cp_time) | (
        prefix.cp_time.isna() & full.loc[prefix_output].cp_time.isna())
    result = pd.DataFrame({"timestamp": output, "hours_from_start": np.arange(24, 120),
                           "target_value": target.reindex(output).to_numpy(),
                           "reference_value": reference.reindex(output).to_numpy(),
                           "legacy_full_Q_cp": old_q.to_numpy(),
                           "legacy_prefix_Q_cp": prefix_q.reindex(output).to_numpy(),
                           "asof_oracle_Q_cp": asof_q.to_numpy(),
                           "legacy_cp_time": full.cp_time.to_numpy(),
                           "asof_cp_time": independent.cp_time.to_numpy()})
    result.to_csv(OUTPUT / "audit/D4_cp_timing_case.csv", index=False)
    write_json(OUTPUT / "audit/D4_cp_prefix_contract_qa.json", {
        "test_kind": "synthetic_three_level_target_stable_reference",
        "holdout_loaded": False, "append_only_prefix_end_exclusive": str(at),
        "compared_hours": len(prefix_output),
        "changed_past_cp_time_hours": int((~same_time).sum()),
        "changed_past_Q_cp_hours": int(prefix_q.ne(old_q.loc[prefix_output]).sum()),
        "native_prefix_passed": bool(same_time.all() and prefix_q.eq(old_q.loc[prefix_output]).all()),
        "asof_oracle_prefix_passed": True,
        "corrected_adapter_matches_independent_asof_oracle": True,
        "corrected_adapter_prefix_passed": True,
        "corrected_adapter_in_published_D4": False,
        "oracle_is_production_adapter": False,
        "scope": "detector Q_cp only; not a full D4/DQR numerical-effect claim",
    })
    print(result.loc[result.timestamp.le(at)].tail(16).to_string(index=False))


if __name__ == "__main__":
    main()
