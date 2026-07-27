from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
DATA = D4_ROOT / "outputs" / "data"
FIGURES = D4_ROOT / "outputs" / "figures"
QA = D4_ROOT / "outputs" / "qa"
COMPARISON = D4_ROOT / "outputs" / "comparison"
INTEGRATION = D4_ROOT / "outputs" / "integration"


def main() -> None:
    scores = pd.read_excel(DATA / "D4_main_scores.xlsx", sheet_name="main_scores")
    params = pd.read_excel(DATA / "D4_mapping_params.xlsx", sheet_name="public_quantiles")
    benchmark = pd.read_excel(DATA / "D4_pair_benchmark_library.xlsx", sheet_name="benchmark_windows")
    events = pd.read_excel(DATA / "D4_event_windows.xlsx", sheet_name="events")
    validation = pd.read_excel(DATA / "D4_benchmark_results.xlsx", sheet_name="summary")
    expected_base = (
        0.35 * scores["Q_dist"] + 0.25 * scores["Q_trend"]
        + 0.20 * scores["Q_var"] + 0.20 * scores["Q_cp"]
    )
    expected_raw = 0.75 * expected_base + 0.25 * scores[
        ["Q_dist", "Q_trend", "Q_var", "Q_cp"]
    ].min(axis=1)
    expected_gate = (
        scores["D2_target_veto"].eq(0) & scores["D2_ref_veto"].eq(0)
        & scores["valid_fraction_target"].ge(0.80)
        & scores["valid_fraction_reference"].ge(0.80)
        & scores["D4_raw"].notna()
    )
    stems = {path.stem for path in FIGURES.glob("*.png")}
    missing_counterparts = [
        stem for stem in stems
        if not (FIGURES / f"{stem}.svg").exists() or not (FIGURES / f"{stem}.pdf").exists()
    ]
    comparison_stem = "Fig_D4_three_version_sensitivity"
    comparison_bundle_ok = all(
        (COMPARISON / f"{comparison_stem}.{suffix}").exists()
        for suffix in ("png", "svg", "pdf")
    ) and (COMPARISON / "D4_three_version_sensitivity.xlsx").exists()
    integration_manifest = json.loads(
        (INTEGRATION / "D4_D5_aggregation_readiness_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    checks = {
        "rows": int(len(scores)),
        "pairs": int(scores["pair_id"].nunique()),
        "score_bounds_ok": bool(
            scores[["D4_base", "D4_raw", "D4_total", "D4_after_D1", "D4_forDQR_provisional"]]
            .stack().between(1, 5).all()
        ),
        "base_formula_max_abs_error": float(np.nanmax(np.abs(scores["D4_base"] - expected_base))),
        "raw_formula_max_abs_error": float(np.nanmax(np.abs(scores["D4_raw"] - expected_raw))),
        "d2_gate_mismatch_count": int((scores["usable_for_D4"] != expected_gate).sum()),
        "calibration_min_n": int(params["sample_size"].min()),
        "calibration_sources": sorted(params["benchmark_source"].drop_duplicates().tolist()),
        "pair_specific_mapping_count": int(params["mapping_scope"].str.contains("pair", case=False).sum()),
        "benchmark_D1_violations": int(
            (benchmark["D1_target"].lt(4.5) | benchmark["D1_ref"].lt(4.5)).sum()
        ),
        "benchmark_D2_continuity_violations": int(
            (~benchmark["D2_target_continuous_24h"].astype(bool)
             | ~benchmark["D2_ref_continuous_24h"].astype(bool)).sum()
        ),
        "event_duration_violations": int(events["duration_h"].lt(3.0).sum()),
        "final_D4_forDQR_nonnull": int(scores["D4_forDQR"].notna().sum()),
        "D5_proxy_rows": int(scores["D5_zone_consensus_label"].ne("not_available").sum()),
        "integration_finalized_rows": int(integration_manifest["finalized_rows"]),
        "integration_numeric_source": integration_manifest["numeric_source"],
        "integration_max_abs_numeric_adjustment": float(
            integration_manifest["max_abs_numeric_adjustment"]
        ),
        "required_validation_failures": int(
            ((validation["required_for_acceptance"] == True) & (validation["pass"] != True)).sum()
        ),
        "figure_stems": len(stems),
        "missing_figure_counterparts": missing_counterparts,
        "comparison_bundle_ok": bool(comparison_bundle_ok),
    }
    checks["passed"] = bool(
        checks["pairs"] == 7
        and checks["score_bounds_ok"]
        and checks["base_formula_max_abs_error"] < 1e-10
        and checks["raw_formula_max_abs_error"] < 1e-10
        and checks["d2_gate_mismatch_count"] == 0
        and checks["calibration_min_n"] >= 50
        and checks["pair_specific_mapping_count"] == 0
        and checks["benchmark_D1_violations"] == 0
        and checks["benchmark_D2_continuity_violations"] == 0
        and checks["event_duration_violations"] == 0
        and checks["final_D4_forDQR_nonnull"] == 0
        and checks["D5_proxy_rows"] == 0
        and checks["integration_finalized_rows"] > 0
        and checks["integration_numeric_source"] == "D4_raw"
        and checks["integration_max_abs_numeric_adjustment"] < 1e-12
        and checks["required_validation_failures"] == 0
        and checks["figure_stems"] == 8
        and not checks["missing_figure_counterparts"]
        and checks["comparison_bundle_ok"]
    )
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "numerical_qa.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if not checks["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
