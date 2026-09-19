"""Historical detector-output -> frozen D4 mapping replay; no calibration fit."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import yaml

from runtime import DIMENSIONS, OUTPUT, PROJECT, START, sha256, write_json

D4 = PROJECT / DIMENSIONS["D4"]
sys.path.insert(0, str(D4 / "src"))
from d4.scoring import aggregate_scores, score_from_quantiles


def main() -> None:
    root = D4 / "outputs/data"
    paths = {"mapping": root / "D4_mapping_params.xlsx",
             "scores": root / "D4_main_scores.xlsx",
             "detectors": root / "D4_detector_outputs_raw.xlsx"}
    params = pd.read_excel(paths["mapping"], sheet_name="public_quantiles")
    old = pd.read_excel(paths["scores"], sheet_name="main_scores")
    risk = pd.read_excel(paths["detectors"], sheet_name="detector_outputs")
    if pd.to_datetime(old.timestamp).max() >= START:
        raise ValueError("Historical mapping replay cannot include later rows")
    keys = ["timestamp", "pair_id"]
    base = old[keys + ["variable", "regime_id", "deadband_active"]].merge(
        risk[keys + ["risk_dist", "risk_trend", "risk_var", "Q_cp"]],
        on=keys, validate="one_to_one")
    for column in ["Q_dist", "Q_trend", "Q_var"]:
        base[column] = np.nan
        subset = params.loc[params.subscore.eq(column)]
        if subset.duplicated(["variable", "regime_id"]).any():
            raise ValueError("Ambiguous production mapping")
        for row in subset.to_dict("records"):
            regime_mask = (base.regime_id.eq(row["regime_id"]) if pd.notna(row["regime_id"])
                           else base.regime_id.isna())
            mask = base.variable.eq(row["variable"]) & regime_mask
            base.loc[mask, column] = score_from_quantiles(
                base.loc[mask, row["risk_metric"]].to_numpy(),
                np.array([row[k] for k in ["q50", "q75", "q90", "q97_5"]]))
    base.loc[base.deadband_active.astype(bool), "Q_var"] = 5.
    cfg = yaml.safe_load((D4 / "configs/d4.yaml").read_text(encoding="utf-8"))
    base["D4_base"], base["D4_raw"] = aggregate_scores(
        *[base[col].to_numpy() for col in ["Q_dist", "Q_trend", "Q_var", "Q_cp"]],
        weights=cfg["aggregation"]["weights"], lambda_blend=cfg["aggregation"]["lambda_blend"])
    result = base.merge(old[keys + ["Q_dist", "Q_trend", "Q_var", "Q_cp", "D4_base", "D4_raw"]],
                        on=keys, suffixes=("", "_published"), validate="one_to_one")
    rows = []
    for pair, group in result.groupby("pair_id"):
        for col in ["Q_dist", "Q_trend", "Q_var", "Q_cp", "D4_base", "D4_raw"]:
            delta = (group[col] - group[col + "_published"]).abs()
            rows.append({"pair_id": pair, "metric": col, "n_pair_hours": len(group),
                         "max_abs_difference": float(delta.max()),
                         "na_mismatches": int(group[col].isna().ne(group[col + "_published"].isna()).sum()),
                         "n_different_1e_10": int(delta.gt(1e-10).sum())})
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/D4_mapping_historical_replay.csv", index=False)
    production = params.loc[params.mapping_role.eq("production")].copy()
    production.to_csv(OUTPUT / "assets/D4_frozen_production_mapping.csv", index=False)
    write_json(OUTPUT / "audit/D4_mapping_replay_qa.json", {
        "passed": bool(table.na_mismatches.sum() == 0 and table.n_different_1e_10.sum() == 0),
        "n_pair_hours": len(base), "numeric_tolerance": 1e-10,
        "scope": "published_detector_inputs_to_frozen_mapping_and_raw_aggregation_only",
        "change_point_detector_recomputed": False, "D2_gate_recomputed": False,
        "calibration_refitted": False, "holdout_scored": False,
        "sources": {key: {"path": str(path.relative_to(PROJECT)), "sha256": sha256(path)}
                    for key, path in paths.items()},
    })
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
