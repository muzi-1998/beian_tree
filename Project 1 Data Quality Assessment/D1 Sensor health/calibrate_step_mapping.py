"""Calibrate the D1 Step logistic mapping from raw detector-input injections."""
from __future__ import annotations

import json
import pickle
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.calibration.step_injection import (  # noqa: E402
    StepCalibrationConfig,
    build_injection_library,
    select_step_mapping,
)


def main() -> dict:
    with open(ROOT / "raw_hourly.pkl", "rb") as handle:
        raw = pickle.load(handle)
    with open(ROOT / "v11_state.pkl", "rb") as handle:
        state = pickle.load(handle)

    routed = raw["whitened_input_h"][state["scored_channels"]]
    normal_masks = {}
    for channel in state["scored_channels"]:
        q = state["subs_v11"][channel]
        normal_masks[channel] = (
            state["state_log_dict"][channel]["state_name"].eq("Normal")
            & (q["Q_freeze"] >= 3.0)
            & (q["Q_regime"] >= 3.0)
        )

    cfg = StepCalibrationConfig()
    scoring_mode = raw.get("scoring_mode", {})
    library = build_injection_library(
        routed,
        normal_masks,
        raw.get("eff_neff", {}),
        scoring_mode,
        cfg,
    )
    result = select_step_mapping(library, cfg)
    selected = result["selected"]

    data_dir = ROOT / "outputs" / "data"
    plot_dir = ROOT / "outputs" / "plot_data"
    log_dir = ROOT / "outputs" / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    applicability_rows = []
    included_channels = set(library["sensor_id"].unique())
    for channel in state["scored_channels"]:
        mode = str(scoring_mode.get(channel, "unknown"))
        neff = float(raw.get("eff_neff", {}).get(channel, 1.0))
        included = channel in included_channels
        if included:
            reason = "eligible iid detector route"
        elif mode == "autocorr_aware":
            reason = "n_eff-deflated KS is an auxiliary detector, outside global mapping fit"
        elif mode == "floor_freeze":
            reason = "process-floor channel excluded from adjacent-KS calibration"
        else:
            reason = f"scoring mode {mode!r} is outside calibration scope"
        applicability_rows.append({
            "sensor_id": channel,
            "scoring_mode": mode,
            "neff_ratio": neff,
            "max_corrected_ks": float(np.sqrt(np.clip(neff, 0.0, 1.0))),
            "included_in_mapping_fit": included,
            "exclusion_reason": reason,
        })
    applicability = pd.DataFrame(applicability_rows)

    library_export = library.drop(columns=["ks24_window", "ks36_window"]).copy()
    library_export["ks24_peak"] = [float(np.nanmax(v)) for v in library["ks24_window"]]
    library_export["ks36_peak"] = [float(np.nanmax(v)) for v in library["ks36_window"]]
    summary = pd.DataFrame([{
        "calibration_id": result["calibration_id"],
        "library_sha256": result["library_sha256"],
        "selected_k": selected["k"],
        "selected_x0": selected["x0"],
        "n_channels": library["sensor_id"].nunique(),
        "n_scenarios": len(library),
        "windows_per_channel_max": cfg.windows_per_channel,
        "rmse_channel_balanced": selected["rmse_channel_balanced"],
        "null_warning_rate": selected["null_warning_rate"],
        "small_hard_rate": selected["small_hard_rate"],
        "material_detection_rate": selected["material_detection_rate"],
        "material_miss_rate": selected["material_miss_rate"],
        "calibration_scope": "raw routed detector input -> KS24/KS36 -> confirmation gate",
        "eligible_scoring_modes": ", ".join(cfg.calibration_scoring_modes),
    }])
    workbook = data_dir / "D1_step_mapping_calibration.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        result["grid"].to_excel(writer, sheet_name="parameter_grid", index=False)
        result["leave_one_channel_out"].to_excel(writer, sheet_name="LOCO_validation", index=False)
        result["scenario_scores"].to_excel(writer, sheet_name="scenario_scores", index=False)
        library_export.to_excel(writer, sheet_name="injection_library", index=False)
        applicability.to_excel(writer, sheet_name="applicability_audit", index=False)
    result["scenario_scores"].to_csv(
        plot_dir / "D1_step_mapping_calibration_scenarios.csv", index=False
    )
    manifest = {
        "calibration_id": result["calibration_id"],
        "library_sha256": result["library_sha256"],
        "selected_k": selected["k"],
        "selected_x0": selected["x0"],
        "metrics": {key: selected[key] for key in (
            "rmse_channel_balanced", "null_warning_rate", "small_hard_rate",
            "material_detection_rate", "material_miss_rate",
        )},
        "config": cfg.__dict__,
        "source_run_id": state.get("run_id"),
        "included_scoring_modes": list(cfg.calibration_scoring_modes),
        "excluded_scoring_modes": sorted(
            set(applicability.loc[~applicability["included_in_mapping_fit"], "scoring_mode"])
        ),
        "applicability": applicability.to_dict(orient="records"),
    }
    (log_dir / "D1_step_mapping_calibration.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print(f"[step-calibration] wrote {workbook}")
    return manifest


if __name__ == "__main__":
    main()
