"""Verify newly connected artifacts, keeping causality corrections explicit."""
from __future__ import annotations

import numpy as np
import pandas as pd

from inference_inputs import cache_folder
from runtime import OUTPUT, PROJECT, DIMENSIONS, write_json


def main():
    folder = cache_folder(False)
    new = pd.read_parquet(folder / "D4_risks.parquet")
    old = pd.read_excel(PROJECT / DIMENSIONS["D4"] / "outputs/data/D4_detector_outputs_raw.xlsx", sheet_name="detector_outputs")
    keys = ["timestamp", "pair_id"]
    check = new.merge(old, on=keys, suffixes=("", "_old"), validate="one_to_one")
    rows = []
    for field in ["risk_dist", "risk_trend", "risk_var", "valid_fraction_common", "valid_fraction_common_hours"]:
        a, b = check[field], check[field+"_old"]
        rows.append(dict(field=field, n_pair_hours=len(check), maximum_error=float((a-b).abs().max()),
                         na_mismatches=int(a.isna().ne(b.isna()).sum())))
    previous = pd.read_parquet(OUTPUT / "audit/D4_historical_CP_timing_rows.parquet")
    cp = new[keys+["Q_cp"]].merge(previous[keys+["Q_cp_asof_candidate"]], on=keys, validate="one_to_one")
    cp_error = float((cp.Q_cp-cp.Q_cp_asof_candidate).abs().max())
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/D4_connected_residual_replay.csv", index=False)
    audit = pd.read_parquet(folder / "DQR_time_join.parquet")
    time_checks = []
    for dim in ["D1", "D2", "D3", "D5"]:
        available = audit[f"{dim}_available_at"]
        time_checks.append(not (available > audit.decision_at).any())
    node = pd.read_parquet(folder / "DQR_node.parquet")
    pair = pd.read_parquet(folder / "DQR_pair.parquet")
    expected = (node.D1_total+node.D2_total) / 2
    core_valid = node.D1_total.notna() & node.D2_total.notna()
    core_exact = np.allclose(node.Q_node_core12, expected.where(core_valid), equal_nan=True)
    full = node.I_D1 & node.I_D2 & node.I_D5
    full_exact = np.allclose(node.Q_node_full, ((node.D1_total+node.D2_total+node.D5_report_score)/3).where(full), equal_nan=True)
    pair_expected = pair[["left_Q_node_core12", "right_Q_node_core12", "D4_raw"]].mean(axis=1).where(
        pair.left_Q_node_core12.notna() & pair.right_Q_node_core12.notna() & pair.I_D4)
    pair_exact = np.allclose(pair.Q_pair_core, pair_expected, equal_nan=True)
    qa = dict(D4_risk_replay_passed=bool(table.maximum_error.lt(1e-7).all() and not table.na_mismatches.sum()),
              D4_asof_CP_equal_to_audited_candidate=bool(cp_error < 1e-10), D4_CP_max_error=cp_error,
              DQR_no_future_source=all(time_checks), node_core_formula=bool(core_exact),
              node_full_formula=bool(full_exact), pair_core_formula=bool(pair_exact),
              n_node_hours=len(node), n_pair_hours=len(pair), holdout_opened=False)
    write_json(OUTPUT / "audit/connected_historical_qa.json", qa)
    print(qa, flush=True)
    if not all(qa[key] for key in ["D4_risk_replay_passed", "D4_asof_CP_equal_to_audited_candidate",
            "DQR_no_future_source", "node_core_formula", "node_full_formula", "pair_core_formula"]):
        raise RuntimeError("Connected historical QA failed")


if __name__ == "__main__":
    main()
