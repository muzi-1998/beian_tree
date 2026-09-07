"""Full historical D5 raw-minute replay and closed-prefix checks."""
from __future__ import annotations

import numpy as np
import pandas as pd

from d5_frozen_adapter import FrozenD5, ROOT
from runtime import OFFICIAL, OUTPUT, START, write_json


def compare(actual, expected, columns):
    rows = []
    keys = ["timestamp", "sensor_id"]
    left = actual.set_index(keys).sort_index()
    right = expected.set_index(keys).sort_index().reindex(left.index)
    for column in columns:
        a, b = left[column], right[column]
        missing = int(a.isna().ne(b.isna()).sum())
        if pd.api.types.is_numeric_dtype(a) and not pd.api.types.is_bool_dtype(a):
            delta = (a - b).abs()
            differences = int(delta.gt(1e-8).sum())
            maximum = float(delta.max()) if delta.notna().any() else 0.
        else:
            differences = int(a.fillna("<NA>").ne(b.fillna("<NA>")).sum())
            maximum = None
        rows.append(dict(column=column, rows=len(left), na_mismatches=missing,
                         differences=differences, maximum_error=maximum))
    return rows


def main():
    raw = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet")
    if raw.index.max() >= START:
        raise ValueError("Historical-only audit")
    engine = FrozenD5()
    current, _, _ = engine.predict(raw)
    legacy, _, legacy_hourly = FrozenD5(stable_row_reduction=False).predict(raw)
    archive = pd.read_parquet(ROOT / "outputs/local/D5_main_scores_hourly.parquet")
    cols = ["Q_profile", "Q_gradient", "Q_rank", "Q_rep", "D5_raw", "D5_report_score",
            "support_level", "evaluation_status", "regime_state", "active_regime_id", "window_coverage"]
    rows = compare(legacy, archive, cols)
    arithmetic = pd.DataFrame(compare(current, legacy, cols))
    arithmetic.to_csv(OUTPUT / "audit/D5_deterministic_arithmetic_sensitivity.csv", index=False)
    prefix_rows = []
    # Before/after reference end and regime/support migration; no later period.
    for cutoff in ["2026-02-01", "2026-04-01"]:
        short, _, _ = engine.predict(raw.loc[raw.index < pd.Timestamp(cutoff)])
        prefix_rows.extend([dict(cutoff=cutoff, **r) for r in compare(short, current, cols + ["D5_for_validation"])])
        print("D5 closed-prefix", cutoff, flush=True)
    table = pd.DataFrame(rows)
    prefix = pd.DataFrame(prefix_rows)
    table.to_csv(OUTPUT / "audit/D5_full_historical_replay.csv", index=False)
    prefix.to_csv(OUTPUT / "audit/D5_full_prefix_replay.csv", index=False)
    qa = dict(scope="raw_minutes_to_frozen_context_templates_support_ECDF_gates",
              n_sensor_hours=len(current), historical_passed=bool((table.differences + table.na_mismatches).sum() == 0),
              prefix_passed=bool((prefix.differences + prefix.na_mismatches).sum() == 0),
              future_fit=False, support_upgraded=False, holdout_opened=False)
    write_json(OUTPUT / "audit/D5_full_replay_qa.json", qa)
    print(table.to_string(index=False), qa, flush=True)
    if not qa["historical_passed"] or not qa["prefix_passed"]:
        raise RuntimeError("D5 full replay mismatch")


if __name__ == "__main__":
    main()
