"""Historical-only CP timing sensitivity; other risks/maps and gates held fixed."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import yaml

from causal_change_points import causal_change_timeline
from runtime import DIMENSIONS, OFFICIAL, OUTPUT, PROJECT, START, sha256, write_json

D4 = PROJECT / DIMENSIONS["D4"]
sys.path.insert(0, str(D4 / "src"))
from d4.scoring import adjacent_ks_change_timeline, aggregate_scores, compare_change_points


def main() -> None:
    cfg = yaml.safe_load((D4 / "configs/d4.yaml").read_text(encoding="utf-8"))
    path = OFFICIAL / "1.1 Decomposition/outputs/parquet/residual_min.parquet"
    residuals = pd.read_parquet(path)
    if residuals.index.max() >= START:
        raise ValueError("Historical timing audit may not use new period")
    hourly = residuals.resample("10min").median().resample("h").median()
    published = pd.read_excel(D4 / "outputs/data/D4_main_scores.xlsx")
    kwargs = cfg["change_point"] | {"min_valid_fraction": cfg["min_valid_fraction"]}
    rows, summaries = [], []
    for pair in cfg["pairs"]:
        old = published.loc[published.pair_id.eq(pair["pair_id"])].copy().sort_values("timestamp")
        labels = pd.DatetimeIndex(old.timestamp)
        available = labels + pd.Timedelta(hours=1)
        native, corrected, dedup_only = {}, {}, {}
        for role in ["target", "reference"]:
            s = hourly[pair[role]]
            native[role] = adjacent_ks_change_timeline(s, labels, **kwargs)
            corrected[role] = causal_change_timeline(s, available, **kwargs)
            dedup_only[role] = causal_change_timeline(s, labels, **kwargs)
        replay_cp = compare_change_points(native["target"], native["reference"]).Q_cp.to_numpy()
        qcp = compare_change_points(corrected["target"], corrected["reference"]).Q_cp.to_numpy()
        qcp_dedup = compare_change_points(dedup_only["target"], dedup_only["reference"]).Q_cp.to_numpy()
        if not np.array_equal(replay_cp, old.Q_cp.to_numpy()):
            raise ValueError(f"Native CP historical replay failed for {pair['pair_id']}")
        _, raw = aggregate_scores(old.Q_dist.to_numpy(), old.Q_trend.to_numpy(),
                                  old.Q_var.to_numpy(), qcp,
                                  weights=cfg["aggregation"]["weights"],
                                  lambda_blend=cfg["aggregation"]["lambda_blend"])
        old["available_at_candidate"] = available
        old["Q_cp_asof_candidate"] = qcp
        old["Q_cp_asof_dedup_only"] = qcp_dedup
        old["D4_raw_CP_only_candidate"] = raw
        old["Q_cp_changed"] = old.Q_cp.ne(qcp)
        old["D4_raw_delta_CP_only"] = raw - old.D4_raw
        valid = old.usable_for_D4.astype(bool) & old.D4_raw.notna() & np.isfinite(raw)
        old["low_tail_flip_on_common_support"] = valid & old.D4_raw.lt(3).ne(raw < 3)
        summaries.append({"pair_id": pair["pair_id"], "n_pair_hours": len(old),
                          "native_CP_replay_exact": True,
                          "changed_Q_cp_hours": int(old.Q_cp_changed.sum()),
                          "changed_Q_cp_dedup_only_hours": int(old.Q_cp.ne(qcp_dedup).sum()),
                          "changed_Q_cp_clock_after_dedup_hours": int(np.count_nonzero(qcp_dedup != qcp)),
                          "common_evaluable_hours": int(valid.sum()),
                          "changed_D4_raw_common_hours": int((valid & old.D4_raw_delta_CP_only.abs().gt(1e-10)).sum()),
                          "low_tail_flip_hours": int(old.low_tail_flip_on_common_support.sum()),
                          "mean_D4_raw_delta_common": float(old.loc[valid, "D4_raw_delta_CP_only"].mean()),
                          "max_abs_D4_raw_delta_common": float(old.loc[valid, "D4_raw_delta_CP_only"].abs().max()),
                          "scope": "CP_dedup_and_available_clock_only_other_risks_and_gates_fixed"})
        rows.append(old[["timestamp", "available_at_candidate", "pair_id", "phase_id", "Q_cp",
                         "Q_cp_asof_candidate", "Q_cp_asof_dedup_only", "Q_cp_changed", "D4_raw", "D4_raw_CP_only_candidate",
                         "D4_raw_delta_CP_only", "usable_for_D4", "low_tail_flip_on_common_support"]])
        print(summaries[-1], flush=True)
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUTPUT / "audit/D4_historical_CP_timing_summary.csv", index=False)
    pd.concat(rows, ignore_index=True).to_parquet(OUTPUT / "audit/D4_historical_CP_timing_rows.parquet", index=False)
    write_json(OUTPUT / "audit/D4_historical_CP_timing_qa.json", {
        "native_CP_replay_exact": True, "n_pair_hours": int(summary.n_pair_hours.sum()),
        "changed_Q_cp_hours": int(summary.changed_Q_cp_hours.sum()),
        "changed_Q_cp_dedup_only_hours": int(summary.changed_Q_cp_dedup_only_hours.sum()),
        "changed_Q_cp_clock_after_dedup_hours": int(summary.changed_Q_cp_clock_after_dedup_hours.sum()),
        "low_tail_flip_hours": int(summary.low_tail_flip_hours.sum()),
        "scope": "one_factor_historical_sensitivity_not_revised_full_D4_release",
        "raw_residual_sha256": sha256(path), "holdout_opened": False,
        "historical_release_overwritten": False, "new_threshold_selection": False,
    })


if __name__ == "__main__":
    main()
