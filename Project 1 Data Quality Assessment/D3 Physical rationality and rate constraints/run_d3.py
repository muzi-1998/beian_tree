"""Run the independent D3 v2.6 physical-plausibility pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from src.common.benchmark_windows import BenchmarkWindows
from src.data.input_loader import (
    align_temperature_to_grid,
    load_aligned_data,
    load_temperature_proxy,
    source_fingerprints,
)
from src.d3_physical.threshold_store import ThresholdStore
from src.outputs.excel_exporter import build_profile_summary, export_all
from src.pipeline.d3_pipeline import D3Pipeline
from src.validation.d3_validation import run_validation
from src.version import (
    BENCHMARK_VERSION,
    D3_VERSION,
    MAPPING_VERSION,
    RATE_UTILS_VERSION,
    SENSITIVITY_VERSION,
    THRESHOLD_VERSION,
)


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main(
    window_min: int = 120,
    stride_min: int = 120,
    max_windows: int | None = None,
    subset_days: int | None = None,
    skip_validation: bool = False,
):
    started = time.time()
    configs_dir = ROOT / "configs"
    paths_cfg = _load_yaml(configs_dir / "d3_paths.yaml")
    sensors_cfg = _load_yaml(configs_dir / "d3_sensors.yaml")
    physical_bounds_cfg = _load_yaml(configs_dir / "d3_physical_bounds.yaml")
    rate_limits_cfg = _load_yaml(configs_dir / "d3_rate_limits.yaml")
    mapping_cfg = _load_yaml(configs_dir / "d3_mapping.yaml")
    rules_cfg = _load_yaml(configs_dir / "d3_rules.yaml")
    dag_cfg = _load_yaml(configs_dir / "d3_dag.yaml")

    for sensor_type, bounds in physical_bounds_cfg["sensors"].items():
        if (
            bounds["instrument_veto_range_low"] > bounds["hard_low"]
            or bounds["instrument_veto_range_high"] < bounds["hard_high"]
        ):
            raise ValueError(
                f"{sensor_type} instrument Veto range must not be narrower than "
                "the hard physical range; otherwise the Veto would override the "
                "documented physical tolerance."
            )

    forbidden = set(dag_cfg["dimension_independence"]["forbidden_score_inputs"])
    if forbidden != {"D1", "D2"}:
        raise ValueError("D3 independence contract must explicitly forbid D1 and D2 score inputs")

    source_meta = source_fingerprints(paths_cfg, ROOT)
    config_hash = _sha256_files(list(configs_dir.glob("*.yaml")))
    code_hash = _sha256_files(list((ROOT / "src").rglob("*.py")) + [ROOT / "run_d3.py"])
    created_at = datetime.now(timezone.utc)
    run_id = f"RUN_D3_{D3_VERSION}_{created_at.strftime('%Y%m%dT%H%M%SZ')}_{config_hash[:8]}"

    print("[A] Loading canonical observations (no imputation)...")
    frame = load_aligned_data(paths_cfg, ROOT)
    if subset_days is not None:
        end = frame.index[0] + pd.Timedelta(days=subset_days)
        frame = frame.loc[frame.index < end]
    print(f"  {len(frame):,} rows; {frame.index[0]} to {frame.index[-1]}")
    temperature_minute = load_temperature_proxy(paths_cfg, ROOT)
    temperature_c = align_temperature_to_grid(temperature_minute, frame.index)
    print(
        "  Temperature proxy: "
        f"{temperature_minute.index.min()} to {temperature_minute.index.max()}; "
        f"study-grid valid coverage={temperature_c.notna().mean():.1%}; "
        f"raw missing={temperature_minute.attrs['raw_missing_count']:,}; "
        f"invalid={temperature_minute.attrs['invalid_range_count']:,}"
    )

    sensors = [item["id"] for item in sensors_cfg["sensors"]]
    missing_sensors = sorted(set(sensors) - set(frame.columns))
    if missing_sensors:
        raise ValueError(f"Configured sensors missing from canonical inputs: {missing_sensors}")

    print("[B] Selecting benchmark windows...")
    benchmark = BenchmarkWindows(frame, sensors, window_hours=24, target_n_windows=40).select()
    print(f"  {len(benchmark.window_ids)} windows; {BENCHMARK_VERSION}")

    print("[C] Building auditable threshold store...")
    thresholds = ThresholdStore.build(
        physical_bounds_cfg=physical_bounds_cfg,
        rate_limits_cfg=rate_limits_cfg,
        benchmark=benchmark,
        version=THRESHOLD_VERSION,
    )
    threshold_frame = thresholds.to_dataframe()

    print("[D] Scoring D3 independently of D1/D2 and D4 regime labels...")
    configs = {
        "physical_bounds": physical_bounds_cfg,
        "rate_limits": rate_limits_cfg,
        "mapping": mapping_cfg,
        "rules": rules_cfg,
        "dag": dag_cfg,
    }
    pipeline = D3Pipeline(
        frame,
        sensors,
        sensors_cfg["sensors"],
        thresholds,
        configs,
        run_id,
        temperature_c=temperature_c,
    )
    results = pipeline.run(window_min, stride_min, max_windows=max_windows)

    print("[E] Exporting current results...")
    profile = build_profile_summary(results)
    output_dir = ROOT / paths_cfg["output"]["data"]
    exported = export_all(results, threshold_frame, mapping_cfg, profile, output_dir)

    validation_paths = {}
    if not skip_validation and max_windows is None and subset_days is None:
        print("[F] Running boundary, persistence, and construct-validity audits...")
        validation_paths = run_validation(
            frame=frame,
            results=results,
            sensors=sensors,
            sensor_meta=sensors_cfg["sensors"],
            thresholds=thresholds,
            configs=configs,
            root=ROOT,
            temperature_minute=temperature_minute,
        )

    scores = results["main_scores"]
    evaluated = scores[scores["evidence_status"] == "sufficient"]
    manifest = {
        "run_id": run_id,
        "d3_version": D3_VERSION,
        "created_at_utc": created_at.isoformat(),
        "wall_time_s": time.time() - started,
        "study_start": str(frame.index.min()),
        "study_end": str(frame.index.max()),
        "subset_days": subset_days,
        "window_min": window_min,
        "stride_min": stride_min,
        "n_sensor_windows": len(scores),
        "n_evaluated": len(evaluated),
        "n_not_evaluated": int((scores["evidence_status"] != "sufficient").sum()),
        "n_events": len(results["events"]),
        "mean_D3_evaluated": float(evaluated["D3_total"].mean()),
        "versions": {
            "mapping": MAPPING_VERSION,
            "threshold": THRESHOLD_VERSION,
            "rate_utils": RATE_UTILS_VERSION,
            "benchmark": BENCHMARK_VERSION,
            "sensitivity": SENSITIVITY_VERSION,
        },
        "independence_contract": {
            "D1_score_consumed": False,
            "D2_score_consumed": False,
            "boundary_in_D3_score": False,
            "canonical_1_1_time_grid": True,
            "imputed_values_scored": False,
            "regime_labels_consumed": False,
            "D1_D2_consumed_by_production_score": False,
            "D1_D2_consumed_by_validation_candidate_filter": True,
        },
        "scientific_contract": {
            "instrument_range_role": "data_quality_fail",
            "operational_bounds_role": "provisional_warning_only",
            "rate_construct": "mutually_exclusive_soft_only_and_hard_persistent_same_sign_rate",
            "rate_component_weights": {"soft_only": 0.30, "hard": 0.70},
            "outer_aggregation_weights": {
                "Q_value_hard": 0.50,
                "Q_value_soft": 0.20,
                "Q_persistent_rate": 0.30,
            },
            "candidate_0.45_0.35_0.20": "sensitivity_only_not_promoted",
            "impulse_return_role": "D1_spike_owned_morphology_exclusion",
            "process_coherence_role": "attribution_guard_not_veto",
            "do4_physical_soft_low_mg_L": 0.0,
            "do4_zero_equivalence_low_mg_L": -0.05,
            "do4_operational_soft_high": "disabled_pending_time_blocked_template_validation",
            "temperature_conditioned_DO_upper_bound": "frozen_site_calibrated_operational_warning",
            "temperature_covariate": "minute_influent_temperature_proxy",
            "temperature_missing_policy": "not_evaluated_no_extrapolation",
            "temperature_study_grid_coverage": float(temperature_c.notna().mean()),
            "temperature_thermodynamic_role": "normalizer_not_hard_saturation_limit",
            "temperature_saturation_reference": "USGS_Benson_Krause_1980_1984_equation_7",
            "temperature_calibration_resolution": "minute_calibration_minute_validation_minute_production",
            "temperature_uncertainty": "1000_replicate_calendar_day_cluster_bootstrap",
            "temperature_validation_rule": "minute_exceedance_and_2h_warning_window_rates_le_0.02_in_independent_validation",
            "temperature_validation_filter": "frozen_D1_total_spike_step_drift_freeze_regime_and_D2_Strict",
            "temperature_optional_D1_saturation_floor_filter": "unavailable_in_frozen_release_not_imputed",
            "temperature_source_start": str(temperature_minute.index.min()),
            "temperature_source_end": str(temperature_minute.index.max()),
            "temperature_raw_missing_minutes": int(
                temperature_minute.attrs["raw_missing_count"]
            ),
            "temperature_invalid_minutes": int(
                temperature_minute.attrs["invalid_range_count"]
            ),
            "aerobic_DO_alpha_by_position": physical_bounds_cfg[
                "operational_envelope_contract"
            ]["aerobic_do_temperature_conditioned_upper"]["calibration"][
                "alpha_by_position"
            ],
            "aerobic_DO_temperature_scored_positions": physical_bounds_cfg[
                "operational_envelope_contract"
            ]["aerobic_do_temperature_conditioned_upper"]["calibration"][
                "scored_positions"
            ],
            "aerobic_DO_temperature_diagnostic_only_positions": physical_bounds_cfg[
                "operational_envelope_contract"
            ]["aerobic_do_temperature_conditioned_upper"]["calibration"][
                "diagnostic_only_positions"
            ],
            "position_conditioned_ORP_envelope": "diagnostic_only_pending_site_review",
            "legacy_v2_3_rate_reconstruction": "all_hard_point_violation_fraction_with_original_caps",
        },
        "source_inputs": source_meta,
        "config_sha256": config_hash,
        "code_sha256": code_hash,
        "exported_files": [path.name for path in exported],
        "validation_files": [path.name for path in validation_paths.values()],
    }
    manifest_path = ROOT / paths_cfg["output"]["manifest"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Done] {run_id}; manifest={manifest_path}")
    return results, threshold_frame, profile, benchmark, frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-min", type=int, default=120)
    parser.add_argument("--stride-min", type=int, default=120)
    parser.add_argument("--max-windows", type=int)
    parser.add_argument("--subset-days", type=int)
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()
    main(
        args.window_min,
        args.stride_min,
        args.max_windows,
        args.subset_days,
        args.skip_validation,
    )
