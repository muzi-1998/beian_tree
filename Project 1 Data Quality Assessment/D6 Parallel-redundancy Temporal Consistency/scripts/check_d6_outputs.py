from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


D6_ROOT = Path(__file__).resolve().parents[1]
DATA = D6_ROOT / "outputs" / "data"
FIGURES = D6_ROOT / "outputs" / "figures"
QA = D6_ROOT / "outputs" / "qa"


def main() -> None:
    scores = pd.read_excel(DATA / "D6_main_scores.xlsx", sheet_name="main_scores")
    params = pd.read_excel(DATA / "D6_mapping_params.xlsx", sheet_name="pair_quantiles")
    validation = pd.read_excel(DATA / "D6_benchmark_results.xlsx", sheet_name="summary")
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
        & scores["D6_raw"].notna()
    )
    stems = {path.stem for path in FIGURES.glob("*.png")}
    missing_counterparts = [
        stem for stem in stems
        if not (FIGURES / f"{stem}.svg").exists() or not (FIGURES / f"{stem}.pdf").exists()
    ]
    checks = {
        "rows": int(len(scores)),
        "pairs": int(scores["pair_id"].nunique()),
        "score_bounds_ok": bool(scores[["D6_base", "D6_raw", "D6_total"]].stack().between(1, 5).all()),
        "base_formula_max_abs_error": float(np.nanmax(np.abs(scores["D6_base"] - expected_base))),
        "raw_formula_max_abs_error": float(np.nanmax(np.abs(scores["D6_raw"] - expected_raw))),
        "d2_gate_mismatch_count": int((scores["usable_for_DQR"] != expected_gate).sum()),
        "calibration_min_n": int(params["sample_size"].min()),
        "calibration_sources": sorted(params["benchmark_source"].drop_duplicates().tolist()),
        "required_validation_failures": int(
            ((validation["required_for_acceptance"] == True) & (validation["pass"] != True)).sum()
        ),
        "figure_stems": len(stems),
        "missing_figure_counterparts": missing_counterparts,
    }
    checks["passed"] = bool(
        checks["pairs"] == 7
        and checks["score_bounds_ok"]
        and checks["base_formula_max_abs_error"] < 1e-10
        and checks["raw_formula_max_abs_error"] < 1e-10
        and checks["d2_gate_mismatch_count"] == 0
        and checks["calibration_min_n"] >= 500
        and checks["required_validation_failures"] == 0
        and checks["figure_stems"] == 8
        and not checks["missing_figure_counterparts"]
    )
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "numerical_qa.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if not checks["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
