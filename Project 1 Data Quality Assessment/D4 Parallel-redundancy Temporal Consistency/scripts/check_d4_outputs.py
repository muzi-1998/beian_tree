from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
DATA = D4_ROOT / "outputs" / "data"
FIGURES = D4_ROOT / "outputs" / "figures"
FIGURE_SOURCE = D4_ROOT / "outputs" / "figure_source_data"
QA = D4_ROOT / "outputs" / "qa"
COMPARISON = D4_ROOT / "outputs" / "comparison"
INTEGRATION = D4_ROOT / "outputs" / "integration"
EXPECTED_FIGURES = {
    "FigD4_1_scientific_construct",
    "FigD4_2_pair_mechanism_profile",
    "FigD4_3_burden_coverage_calibration",
    "FigD4_4_formal_episode_cases",
    "FigD4_5_mechanism_specificity",
    "FigD4_6_ablation_and_lag_resolution",
    "FigS1_all_pair_residual_trajectories",
    "FigS2_trend_concordance",
    "FigS3_numeric_independence_audit",
    "FigS4_distribution_construct_ablation",
    "FigS5_do14_episode_duration",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    scores = pd.read_excel(DATA / "D4_main_scores.xlsx", sheet_name="main_scores")
    params = pd.read_excel(DATA / "D4_mapping_params.xlsx", sheet_name="public_quantiles")
    benchmark = pd.read_excel(DATA / "D4_pair_benchmark_library.xlsx", sheet_name="benchmark_windows")
    events = pd.read_excel(DATA / "D4_event_windows.xlsx", sheet_name="events")
    validation = pd.read_excel(DATA / "D4_benchmark_results.xlsx", sheet_name="summary")
    common_change = pd.read_excel(
        DATA / "D4_benchmark_results.xlsx", sheet_name="common_change_contract"
    )
    expected_base = (
        0.35 * scores["Q_dist"] + 0.25 * scores["Q_trend"]
        + 0.20 * scores["Q_var"] + 0.20 * scores["Q_cp"]
    )
    expected_raw = 0.75 * expected_base + 0.25 * scores[
        ["Q_dist", "Q_trend", "Q_var", "Q_cp"]
    ].min(axis=1)
    expected_gate = (
        scores["D2_target_veto"].eq(0) & scores["D2_ref_veto"].eq(0)
        & scores["valid_fraction_common"].ge(0.80)
        & scores["valid_fraction_common_hours"].ge(0.80)
        & scores["D4_raw"].notna()
    )
    stems = {path.stem for path in FIGURES.glob("*.png")}
    missing_counterparts = [
        f"{stem}.{extension}"
        for stem in EXPECTED_FIGURES
        for extension in ("svg", "pdf", "png", "tiff")
        if not (FIGURES / f"{stem}.{extension}").exists()
    ]
    missing_source_data = [
        f"{stem}_source_data.xlsx" for stem in EXPECTED_FIGURES
        if not (FIGURE_SOURCE / f"{stem}_source_data.xlsx").exists()
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
    composite_refresh_manifest = json.loads(
        (
            INTEGRATION / "D4V15_composite_refresh"
            / "D4V15_composite_refresh_manifest.json"
        ).read_text(encoding="utf-8")
    )
    common_roles = common_change.set_index("scenario")["role"].to_dict()
    equal_far = float(
        common_change.loc[common_change["scenario"].eq("common_equal"), "estimate"].iloc[0]
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
        "benchmark_non_development_rows": int(benchmark["phase_id"].ne("development").sum()),
        "calibration_non_development_rows": int(params["fit_phase"].ne("development").sum()),
        "calibration_after_fit_end_rows": int(
            (pd.to_datetime(params["fit_end"]) > pd.Timestamp("2026-01-24 23:59:59")).sum()
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
        "common_change_roles_ok": common_roles == {
            "common_equal": "negative_control",
            "common_unequal": "positive_asymmetry_stress_test",
            "opposite_direction": "positive_asymmetry_stress_test",
        },
        "equal_common_mode_far": equal_far,
        "positive_common_changes_excluded_from_far": bool(
            common_change.loc[
                common_change["scenario"].isin(["common_unequal", "opposite_direction"]),
                "metric",
            ].eq("conditional_response_rate").all()
        ),
        "composite_refresh_status": composite_refresh_manifest["status"],
        "composite_refresh_d4_hash_matches": bool(
            composite_refresh_manifest["input_files"]["D4"]["sha256"]
            == _sha256(DATA / "D4_main_scores.xlsx")
        ),
        "composite_refresh_numeric_source": composite_refresh_manifest["D4_numeric_source"],
        "figure_stems": len(stems),
        "figure_stems_exact": stems == EXPECTED_FIGURES,
        "missing_figure_counterparts": missing_counterparts,
        "missing_figure_source_data": missing_source_data,
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
        and checks["benchmark_non_development_rows"] == 0
        and checks["calibration_non_development_rows"] == 0
        and checks["calibration_after_fit_end_rows"] == 0
        and checks["event_duration_violations"] == 0
        and checks["final_D4_forDQR_nonnull"] == 0
        and checks["D5_proxy_rows"] == 0
        and checks["integration_finalized_rows"] > 0
        and checks["integration_numeric_source"] == "D4_raw"
        and checks["integration_max_abs_numeric_adjustment"] < 1e-12
        and checks["required_validation_failures"] == 0
        and checks["common_change_roles_ok"]
        and checks["equal_common_mode_far"] <= 0.10
        and checks["positive_common_changes_excluded_from_far"]
        and checks["composite_refresh_status"]
        == "retrospective_sha_bound_refresh_not_untouched_terminal_validation"
        and checks["composite_refresh_d4_hash_matches"]
        and checks["composite_refresh_numeric_source"] == "D4_raw"
        and checks["figure_stems"] == 11
        and checks["figure_stems_exact"]
        and not checks["missing_figure_counterparts"]
        and not checks["missing_figure_source_data"]
        and checks["comparison_bundle_ok"]
    )
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "numerical_qa.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if not checks["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
