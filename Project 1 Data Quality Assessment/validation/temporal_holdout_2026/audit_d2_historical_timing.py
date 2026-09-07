"""Paired old-period D2 timing audit on the same observable timestamp set."""
from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from audit_d2_causality import execute, pipeline
from runtime import OFFICIAL, OUTPUT, START, sha256, write_json


def main() -> None:
    path = OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet"
    raw = pd.read_parquet(path)[pipeline.SCORED_CHANNELS]
    if raw.index.max() >= START:
        raise ValueError("Old-period audit cannot use new measurements")
    cols = ["Q_TI", "Q_GS", "Q_HA", "D2_total", "veto_flag", "usable_tag"]
    with tempfile.TemporaryDirectory(prefix="d2-historical-asof-") as directory:
        original = execute(raw, Path(directory), "old")
        old_scores = {k: v[cols].copy() for k, v in original[2].items()}
        old_stats = {k: v[["P95_gap_min"]].copy() for k, v in original[1].items()}
        del original
        gc.collect()
        candidate = execute(raw, Path(directory), "asof", corrected=True)
    rows = []
    for sensor in pipeline.SCORED_CHANNELS:
        new = candidate[2][sensor]
        old = old_scores[sensor].reindex(new.index)
        for column in cols:
            same = old[column].eq(new[column]) | (old[column].isna() & new[column].isna())
            finite = pd.to_numeric(old[column], errors="coerce") - pd.to_numeric(new[column], errors="coerce")
            rows.append({"sensor_id": sensor, "field": column, "n_sensor_hours": len(new),
                         "changed_hours": int((~same).sum()),
                         "max_abs_difference": float(finite.abs().max()) if finite.notna().any() else None,
                         "na_mismatches": int(old[column].isna().ne(new[column].isna()).sum())})
        a = old_stats[sensor].reindex(candidate[1][sensor].index).P95_gap_min
        b = candidate[1][sensor].P95_gap_min
        rows.append({"sensor_id": sensor, "field": "P95_gap_min", "n_sensor_hours": len(b),
                     "changed_hours": int(a.ne(b).sum()), "max_abs_difference": float((a-b).abs().max()),
                     "na_mismatches": int(a.isna().ne(b.isna()).sum())})
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/D2_historical_timing_summary.csv", index=False)
    write_json(OUTPUT / "audit/D2_historical_timing_qa.json", {
        "scope": "paired_historical_same_unobservable_source_timestamp_contract",
        "published_D2_full_replay": False,
        "reason_not_published_replay": "Both arms conditionally normalize unobservable duplicate/order/interval metrics; old release used source audits.",
        "n_sensor_hours": int(table.loc[table.field.eq("D2_total"), "n_sensor_hours"].sum()),
        "changed_D2_total_hours": int(table.loc[table.field.eq("D2_total"), "changed_hours"].sum()),
        "changed_veto_hours": int(table.loc[table.field.eq("veto_flag"), "changed_hours"].sum()),
        "changed_P95_hours": int(table.loc[table.field.eq("P95_gap_min"), "changed_hours"].sum()),
        "sensitive_response_loss_tested": False, "holdout_opened": False,
        "source_sha256": sha256(path), "thresholds_changed": False,
    })
    print(table.loc[table.changed_hours.gt(0)].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
