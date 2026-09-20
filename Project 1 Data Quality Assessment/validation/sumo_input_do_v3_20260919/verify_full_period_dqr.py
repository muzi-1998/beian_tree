"""Independent checks for the full-period DQR/SUMO export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from export_full_period_dqr import DO, DO6, ORP, END, OUT, START
from prepare_sumo_inputs import sha256


def load(name):
    return pd.read_csv(OUT / name, index_col="datetime", parse_dates=["datetime"])


def main(check_hashes=False):
    checks = {}
    def check(name, value):
        checks[name] = bool(value)
        if not value:
            raise AssertionError(name)
    index = pd.date_range(START, END, freq="5min", inclusive="left", name="datetime")
    ddo, dorp = load("DQR_DO8_5min_20250801_20260730.csv"), load("DQR_ORP6_5min_20250801_20260730.csv")
    raw, common = load("Raw_DO_ORP14_5min_20250801_20260730.csv"), load("Common_technical_DO_ORP14_5min_20250801_20260730.csv")
    for name, frame in [("DO", ddo), ("ORP", dorp), ("Raw", raw), ("Common", common)]:
        check(name + "_timebase", frame.index.equals(index))
        check(name + "_elapsed_time", np.allclose(frame.time_days, (index - START).total_seconds()/86400))
    check("DO_channels", ddo.columns.tolist() == ["time_days"] + DO)
    check("ORP_channels", dorp.columns.tolist() == ["time_days"] + ORP)
    retained_do = ddo[DO6].notna() & common[DO6].notna()
    retained_orp = dorp[ORP].notna() & common[ORP].notna()
    check("retained_DO6_values_unchanged", np.allclose(ddo[DO6].where(retained_do), common[DO6].where(retained_do), equal_nan=True))
    check("retained_ORP_values_unchanged", np.allclose(dorp[ORP].where(retained_orp), common[ORP].where(retained_orp), equal_nan=True))
    check("signed_ORP_retained", (dorp[ORP].min() < 0).all())
    check("SUMO_DO_nonnegative", (ddo[DO].stack() >= 0).all())
    audit = pd.read_parquet(OUT / "DQR_DO_ORP_full_period_1min_long.parquet")
    check("audit_rows", len(audit) == len(pd.date_range(START, END, freq="min", inclusive="left")) * 14)
    check("unique_sensor_minute", not audit.duplicated(["sensor_id", "datetime"]).any())
    future = audit.datetime.ge("2026-04-14")
    known = future & audit.decision_at.notna()
    age = (audit.loc[known, "datetime"] - audit.loc[known, "decision_at"]).dt.total_seconds()
    check("future_decision_clock", (age.ge(0) & age.lt(3600)).all())
    check("historical_semantics_explicit", audit.loc[~future, "source_period"].eq("retrospective_same_hour_conditioning").all())
    unassessed = audit.source_unassessed
    check("source_unassessed_present", int(unassessed.sum()) > 0)
    check("unassessed_not_forced", audit.loc[unassessed, "forcing"].isna().all())
    check("unassessed_reason", audit.loc[unassessed, "reason"].eq("observation_not_present_in_historical_DQR_source").all())
    check("unassessed_only_before_boundary", audit.loc[unassessed, "datetime"].lt("2026-04-14").all())
    check("no_qualified_repair", audit.repair_method.astype(str).eq("none").all())
    windows = pd.read_csv(OUT / "DQR_Raw_14d_window_comparison.csv", parse_dates=["start", "end_exclusive"])
    check("all_windows_14d", (windows.end_exclusive - windows.start).eq(pd.Timedelta(days=14)).all())
    check("ranking_unique_top", windows.contrast_rank.eq(1).sum() >= 1 and windows.direct_run_rank.eq(1).sum() >= 1)
    summary = json.loads((OUT / "full_period_summary.json").read_text(encoding="utf-8"))
    check("actual_end_not_2028", summary["requested_2028_end_available"] is False and summary["actual_data_period"][1].startswith("2026-07-31"))
    check("D5_boundary_frozen", summary["D5_reference_end"].startswith("2026-01-27"))
    if check_hashes:
        manifest = json.loads((OUT / "full_period_manifest.json").read_text(encoding="utf-8"))
        for path, digest in manifest["inputs"].items(): check("input_hash:" + Path(path).name, sha256(Path(path)) == digest)
        for name, digest in manifest["code"].items(): check("code_hash:" + name, sha256(Path(__file__).parent / name) == digest)
        for name, digest in manifest["outputs"].items(): check("output_hash:" + name, sha256(OUT / name) == digest)
    else:
        (OUT / "verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8", newline="\n")
    print(f"{len(checks)} checks passed; hashes={check_hashes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-hashes", action="store_true")
    main(parser.parse_args().verify_hashes)
