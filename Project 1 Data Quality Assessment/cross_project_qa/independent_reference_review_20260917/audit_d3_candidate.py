"""Read-only eligibility contrast; never write a production calibration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
SOURCE = (
    PROJECT
    / "D3 Physical rationality and rate constraints"
    / "outputs/validation/D3_temperature_conditioned_DO_upper.parquet"
)


def estimate(values: np.ndarray) -> dict[str, float]:
    values = values[np.isfinite(values)]
    if not len(values):
        raise ValueError("Cannot estimate an envelope from an empty reference")
    median = float(np.median(values))
    scale = float(1.4826 * np.median(np.abs(values - median)))
    p99 = float(np.quantile(values, 0.99))
    return {"alpha": max(p99, median + 3 * scale), "median": median,
            "mad_scale": scale, "p99": p99}


def main() -> None:
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    data = pd.read_parquet(SOURCE)
    required = {"ts", "sensor_id", "position", "phase", "DO_minute_mg_L",
                "DO_over_Csat", "Csat_reference_mg_L", "upper_evaluable",
                "high_quality_evaluable", "frozen_alpha"}
    if required - set(data.columns):
        raise ValueError(f"Missing source fields: {sorted(required - set(data.columns))}")
    if data.duplicated(["ts", "sensor_id"]).any():
        raise ValueError("Duplicate sensor-minute rows in source")

    rows = []
    for position, group in data.groupby("position", sort=True):
        calibration = group["phase"].eq("calibration")
        neutral = (
            group["upper_evaluable"].eq(True)
            & group["DO_minute_mg_L"].between(0.0, 20.0)
            & np.isfinite(group["DO_over_Csat"])
            & group["Csat_reference_mg_L"].gt(0)
        )
        masks = {
            "published_screened_reference": calibration & group["high_quality_evaluable"],
            "neutral_candidate_pre_support_audit": calibration & neutral,
            "neutral_plus_D1D2_screen_sensitivity": (
                calibration & neutral & group["high_quality_evaluable"]
            ),
        }
        frozen_values = group["frozen_alpha"].dropna().unique()
        if len(frozen_values) != 1:
            raise ValueError("Expected one frozen alpha per position")
        frozen = float(frozen_values[0])
        for route, mask in masks.items():
            selected = group.loc[mask & np.isfinite(group["DO_over_Csat"])]
            result = estimate(selected["DO_over_Csat"].to_numpy(dtype=float))
            if route == "published_screened_reference" and not np.isclose(
                result["alpha"], frozen, rtol=0, atol=1e-9
            ):
                raise AssertionError("Published screened coefficient failed replay")
            rows.append({
                "position": int(position), "route": route,
                "n_sensor_minutes": int(len(selected)),
                "n_calendar_days": int(pd.to_datetime(selected["ts"]).dt.normalize().nunique()),
                "n_sensors": int(selected["sensor_id"].nunique()),
                "frozen_alpha": frozen, **result,
                "relative_change_pct": 100 * (result["alpha"] / frozen - 1),
                "production_status": "audit_only_not_promoted",
            })

    table = pd.DataFrame(rows)
    table.to_csv(HERE / "D3_candidate_reference_contrast.csv", index=False)
    source_after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_sha != source_after:
        raise AssertionError("Source changed while the audit was running")
    manifest = {
        "audit_date": "2026-09-17",
        "source": SOURCE.relative_to(PROJECT).as_posix(),
        "source_sha256": source_sha,
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checkout_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "source_rows": len(data),
        "calibration_period": "2025-08-01 <= ts < 2026-02-01",
        "estimator": "max(P99, median + 3 * 1.4826 * MAD)",
        "checks": {
            "source_sensor_minute_keys_unique": True,
            "three_published_coefficients_reproduced_at_1e_9": True,
            "source_hash_unchanged": True,
        },
        "limitations": [
            "Pre-support-audit eligibility contrast, not an approved neutral calibration.",
            "Uses exported minute observations; the current source loader documents no imputation.",
            "Original row-level imputation and timestamp audit flags are not in this parquet.",
            "No new minimum hourly or independent-block support admission has been applied.",
            "Calendar-day counts describe support, not statistically independent sample sizes.",
            "No new confidence intervals or production scores/gates have been calculated.",
            "No new-period observations are used to estimate these candidate coefficients.",
        ],
        "results": rows,
    }
    (HERE / "D3_candidate_reference_audit.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(table[["position", "route", "n_sensor_minutes", "alpha", "relative_change_pct"]].to_string(index=False))
    print("PASS: frozen replay, unique source keys, unchanged source hash")


if __name__ == "__main__":
    main()
