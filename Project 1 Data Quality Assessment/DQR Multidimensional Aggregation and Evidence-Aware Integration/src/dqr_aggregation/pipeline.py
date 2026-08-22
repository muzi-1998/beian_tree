from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import (
    PROJECT_ROOT,
    combine_gate,
    expand_end_exclusive_windows,
    sha256_file,
    sha256_text_lf,
)


def _path(relative: str) -> Path:
    return PROJECT_ROOT / relative


def resolve_release_status(
    quality: pd.Series,
    gate_status: pd.Series,
    coverage_class: pd.Series,
) -> pd.Series:
    """Apply fail-closed D3 precedence while retaining diagnostic quality values."""
    gate = gate_status.fillna("NotEvaluated")
    return pd.Series(
        np.select(
            [
                gate.eq("Fail"),
                quality.isna(),
                gate.eq("NotEvaluated"),
                gate.eq("Warn"),
                coverage_class.eq("full"),
            ],
            [
                "gate_fail",
                "not_evaluable",
                "gate_not_evaluated",
                "gate_warn",
                "full_evidence",
            ],
            default="report_only",
        ),
        index=quality.index,
        dtype="object",
    )


def verify_frozen_inputs(config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dimension, spec in config["inputs"].items():
        checks = [("path", "expected_sha256")]
        checks.extend(
            (key.removeprefix("expected_").removesuffix("_sha256") + "_path", key)
            for key in spec
            if key.startswith("expected_")
            and key.endswith("_sha256")
            and key not in {"expected_sha256"}
        )
        path_keys = set(spec)
        normalized: list[tuple[str, str]] = []
        for path_key, hash_key in checks:
            if path_key in path_keys:
                normalized.append((path_key, hash_key))
        for path_key, hash_key in normalized:
            path = _path(spec[path_key])
            exists = path.exists()
            hash_method = (
                "sha256_utf8_lf_canonical"
                if path_key.endswith("manifest_path")
                else "sha256_raw_bytes"
            )
            actual = (
                sha256_text_lf(path)
                if exists and hash_method == "sha256_utf8_lf_canonical"
                else sha256_file(path)
                if exists
                else None
            )
            expected = str(spec[hash_key]).lower()
            match = bool(exists and actual == expected)
            rows.append(
                {
                    "dimension": dimension,
                    "artifact_role": path_key,
                    "relative_path": spec[path_key],
                    "exists": exists,
                    "size_bytes": path.stat().st_size if exists else None,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                    "sha256_match": match,
                    "hash_method": hash_method,
                }
            )
    registry = pd.DataFrame(rows)
    failed = registry.loc[~registry["sha256_match"]]
    if not failed.empty:
        details = failed[["dimension", "artifact_role", "relative_path"]].to_dict("records")
        raise RuntimeError(f"Frozen aggregation input mismatch: {details}")
    return registry


def _wide_to_long(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame.melt(id_vars="timestamp", var_name="sensor_id", value_name=value_name)


def load_d1(config: dict[str, Any]) -> pd.DataFrame:
    spec = config["inputs"]["D1"]
    path = _path(spec["path"])
    score = _wide_to_long(pd.read_excel(path, sheet_name=spec["sheet"]), "D1_total")
    usable = _wide_to_long(
        pd.read_excel(path, sheet_name=spec["usable_sheet"]), "D1_legacy_usable_tag"
    )
    frame = score.merge(usable, on=["timestamp", "sensor_id"], how="left")
    frame["D1_run_id"] = spec["expected_run_id"]
    return frame


def load_d2(config: dict[str, Any]) -> pd.DataFrame:
    spec = config["inputs"]["D2"]
    frame = pd.read_excel(_path(spec["path"]), sheet_name=spec["sheet"])
    frame = frame.rename(columns={frame.columns[0]: "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    required = [
        "timestamp",
        "sensor_id",
        "D2_total",
        "usable_tag",
        "veto_flag",
        "veto_reason",
        "dominant_limitation",
        "run_id",
        "calibration_id",
    ]
    frame = frame[required].rename(
        columns={
            "usable_tag": "D2_usable_tag",
            "veto_flag": "D2_veto_flag",
            "veto_reason": "D2_veto_reason",
            "dominant_limitation": "D2_dominant_limitation",
            "run_id": "D2_run_id",
            "calibration_id": "D2_calibration_id",
        }
    )
    if set(frame["D2_run_id"].dropna().unique()) != {spec["expected_run_id"]}:
        raise RuntimeError("D2 run_id is not the frozen aggregation dependency")
    if set(frame["D2_calibration_id"].dropna().unique()) != {
        spec["expected_calibration_id"]
    }:
        raise RuntimeError("D2 calibration_id is not the frozen aggregation dependency")
    return frame


def load_d3(config: dict[str, Any]) -> pd.DataFrame:
    spec = config["inputs"]["D3"]
    frame = pd.read_excel(_path(spec["path"]))
    frame = frame.rename(columns={"ts": "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if set(frame["run_id"].dropna().unique()) != {spec["expected_run_id"]}:
        raise RuntimeError("D3 run_id is not the frozen aggregation dependency")
    expanded = expand_end_exclusive_windows(frame)
    return expanded[
        [
            "timestamp",
            "sensor_id",
            "D3_total",
            "D3_gate_status",
            "evidence_status",
            "dominant_physical_issue",
            "veto_flag",
            "operational_warning_flag",
            "temperature_upper_status",
            "threshold_version",
            "mapping_version",
            "run_id",
            "source_window_end_exclusive",
        ]
    ].rename(
        columns={
            "run_id": "D3_run_id",
            "evidence_status": "D3_evidence_status",
            "dominant_physical_issue": "D3_dominant_issue",
            "veto_flag": "D3_veto_flag",
            "operational_warning_flag": "D3_operational_warning_flag",
            "temperature_upper_status": "D3_temperature_upper_status",
            "threshold_version": "D3_threshold_version",
            "mapping_version": "D3_mapping_version",
        }
    )


def load_d4(config: dict[str, Any]) -> pd.DataFrame:
    spec = config["inputs"]["D4"]
    frame = pd.read_excel(_path(spec["path"]), sheet_name=spec["sheet"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if frame.duplicated(["timestamp", "pair_id"]).any():
        raise RuntimeError("D4 must contain exactly one native pair row per pair-hour")
    if set(frame["run_id"].dropna().unique()) != {spec["expected_run_id"]}:
        raise RuntimeError("D4 run_id is not the frozen aggregation dependency")
    if set(frame["calibration_id"].dropna().unique()) != {
        spec["expected_calibration_id"]
    }:
        raise RuntimeError("D4 calibration_id is not the frozen aggregation dependency")
    mapping = pd.read_excel(
        _path(spec["mapping_path"]), sheet_name="public_quantiles"
    )
    mapping = mapping.loc[
        mapping["mapping_role"].eq("production")
        & mapping["regime_id"].notna()
    ].copy()
    mapping["regime_id"] = mapping["regime_id"].astype(int)

    def scope_class(value: object) -> str:
        scope = str(value).strip().lower()
        if scope == "variable_regime_public":
            return "exact"
        if scope == "variable_public_fallback":
            return "variable_fallback"
        if "global" in scope and "fallback" in scope:
            return "global_fallback"
        return "insufficient"

    mapping["mapping_support_class"] = mapping["mapping_scope"].map(scope_class)
    rows = []
    precision_rank = {"supported": 0, "wide_interval": 1, "not_estimable": 2}
    for (variable, regime_id), group in mapping.groupby(
        ["variable", "regime_id"], sort=True
    ):
        scopes = group["mapping_scope"].dropna().astype(str).unique()
        classes = group["mapping_support_class"].dropna().astype(str).unique()
        if len(scopes) != 1 or len(classes) != 1 or group["subscore"].nunique() != 3:
            raise RuntimeError(
                f"D4 mapping metadata is inconsistent for {variable}/R{regime_id}"
            )
        grades = group["percentile_precision_grade"].dropna().astype(str)
        tail_grade = (
            max(grades, key=lambda item: precision_rank.get(item, 3))
            if len(grades)
            else "not_available"
        )
        rows.append(
            {
                "variable": variable,
                "regime_id": int(regime_id),
                "calibration_scope": scopes[0],
                "mapping_support_class": classes[0],
                "calibration_quality": "|".join(
                    sorted(group["calibration_quality"].dropna().astype(str).unique())
                ),
                "calibration_evidence_quality": "|".join(
                    sorted(
                        group["mapping_evidence_quality"]
                        .dropna()
                        .astype(str)
                        .unique()
                    )
                ),
                "calibration_independent_blocks": int(
                    group["independent_blocks"].min()
                ),
                "calibration_exact_independent_blocks": int(
                    group["exact_independent_blocks"].min()
                ),
                "calibration_sample_size": int(group["sample_size"].min()),
                "calibration_tail_precision_grade": tail_grade,
                "calibration_mapping_ids": "|".join(
                    sorted(group["mapping_id"].dropna().astype(str).unique())
                ),
            }
        )
    lookup = pd.DataFrame(rows)
    frame["regime_id"] = pd.to_numeric(frame["regime_id"], errors="coerce").astype(
        "Int64"
    )
    frame = frame.merge(lookup, on=["variable", "regime_id"], how="left")
    unmapped_supported_regime = frame["regime_id"].notna() & frame[
        "mapping_support_class"
    ].isna()
    if unmapped_supported_regime.any():
        missing = frame.loc[
            unmapped_supported_regime, ["variable", "regime_id"]
        ].drop_duplicates()
        raise RuntimeError(
            f"D4 pair-hours lack mapping metadata: {missing.to_dict('records')}"
        )
    frame["mapping_support_class"] = frame["mapping_support_class"].fillna(
        "insufficient"
    )
    frame["calibration_scope"] = frame["calibration_scope"].fillna("not_mapped")
    return frame


def load_d5(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    spec = config["inputs"]["D5"]
    report = pd.read_parquet(_path(spec["path"]))
    raw = pd.read_parquet(_path(spec["raw_path"]))
    for frame in (report, raw):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        if set(frame["run_id"].dropna().unique()) != {spec["expected_run_id"]}:
            raise RuntimeError("D5 run_id is not the frozen aggregation dependency")
        if set(frame["topology_hash"].dropna().unique()) != {
            spec["expected_topology_hash"]
        }:
            raise RuntimeError("D5 topology_hash is not the frozen aggregation dependency")
    raw_meta = raw[
        [
            "timestamp",
            "sensor_id",
            "D5_raw",
            "active_regime_id",
            "regime_state",
            "ood_distance",
            "mapping_hash",
            "confidence",
        ]
    ].rename(columns={"confidence": "D5_raw_confidence"})
    return report.merge(raw_meta, on=["timestamp", "sensor_id"], how="left"), raw


def _dimension_record(
    frame: pd.DataFrame,
    *,
    dimension: str,
    object_type: str,
    object_id: str,
    score: str | None,
    diagnostic_score: str | None,
    applicable: pd.Series,
    evaluable: pd.Series,
    report_eligible: pd.Series,
    support_level: pd.Series | str,
    status_reason: pd.Series | str,
    run_id: pd.Series | str,
    calibration_id: pd.Series | str,
    version_hash: pd.Series | str,
    phase_role: pd.Series | str,
    reference_status: pd.Series | str,
    mapping_support_class: pd.Series | str,
    source_hash: str,
    metadata_columns: list[str],
) -> pd.DataFrame:
    output = pd.DataFrame(
        {
            "timestamp": frame["timestamp"],
            "object_type": object_type,
            "object_id": frame[object_id],
            "sensor_id": frame["sensor_id"] if "sensor_id" in frame else pd.NA,
            "pair_id": frame["pair_id"] if "pair_id" in frame else pd.NA,
            "dimension": dimension,
            "score_1to5": frame[score] if score else np.nan,
            "diagnostic_score_1to5": frame[diagnostic_score]
            if diagnostic_score
            else np.nan,
            "applicable": applicable.astype(bool),
            "evaluable": evaluable.astype(bool),
            "report_eligible": report_eligible.astype(bool),
            "support_level": support_level,
            "status_reason": status_reason,
            "run_id": run_id,
            "calibration_id": calibration_id,
            "version_hash": version_hash,
            "phase_role": phase_role,
            "reference_status": reference_status,
            "mapping_support_class": mapping_support_class,
            "source_artifact_sha256": source_hash,
            "artifact_hash": pd.NA,
            "artifact_hash_status": "manifest_bound_avoids_recursive_self_hash",
        }
    )
    available_metadata = [column for column in metadata_columns if column in frame.columns]
    metadata = (
        frame[available_metadata].copy()
        if available_metadata
        else pd.DataFrame(index=frame.index)
    )
    output["evidence_metadata"] = metadata.apply(
        lambda row: json.dumps(
            {key: value for key, value in row.items() if pd.notna(value)},
            ensure_ascii=True,
            default=str,
            separators=(",", ":"),
        ),
        axis=1,
    )
    return output


def _phase_reference_metadata(
    config: dict[str, Any], dimension: str, frame: pd.DataFrame
) -> tuple[pd.Series, pd.Series, pd.Series]:
    timestamp = pd.to_datetime(frame["timestamp"])
    contract = config["phase_contracts"][dimension]
    source_hash = config["inputs"][dimension]["expected_sha256"]

    if dimension == "D1":
        fit_end = pd.Timestamp(contract["fit_end"])
        development_end = pd.Timestamp(contract["development_end"])
        validation_end = pd.Timestamp(contract["internal_validation_end"])
        phase = pd.Series(
            np.select(
                [
                    timestamp.le(fit_end),
                    timestamp.le(development_end),
                    timestamp.le(validation_end),
                ],
                ["calibration", "development", "internal_validation"],
                default="terminal_test",
            ),
            index=frame.index,
        )
        reference = pd.Series(
            np.where(timestamp.le(fit_end), "in_reference", "post_reference_supported"),
            index=frame.index,
        )
        version = pd.Series(source_hash, index=frame.index)
    elif dimension == "D2":
        development_end = pd.Timestamp(contract["development_end"])
        validation_end = pd.Timestamp(contract["internal_validation_end"])
        phase = pd.Series(
            np.select(
                [timestamp.le(development_end), timestamp.le(validation_end)],
                ["development", "internal_validation"],
                default="terminal_test",
            ),
            index=frame.index,
        )
        reference = pd.Series(
            np.where(
                timestamp.le(development_end),
                "in_reference",
                "post_reference_supported",
            ),
            index=frame.index,
        )
        version = pd.Series(source_hash, index=frame.index)
    elif dimension == "D3":
        calibration_end = pd.Timestamp(contract["calibration_end"])
        validation_end = pd.Timestamp(contract["internal_validation_end"])
        phase = pd.Series(
            np.select(
                [timestamp.le(calibration_end), timestamp.le(validation_end)],
                ["calibration", "internal_validation"],
                default="terminal_test",
            ),
            index=frame.index,
        )
        reference = pd.Series(
            np.where(
                timestamp.le(calibration_end),
                "in_reference",
                "post_reference_supported",
            ),
            index=frame.index,
        )
        version = frame["D3_threshold_version"].astype(str) + "|" + frame[
            "D3_mapping_version"
        ].astype(str)
    elif dimension == "D4":
        phase = frame["phase_id"].astype(str)
        exact = frame["mapping_support_class"].eq("exact")
        reference = pd.Series(
            np.select(
                [
                    phase.eq("development"),
                    exact,
                    frame["mapping_support_class"].isin(
                        ["variable_fallback", "global_fallback"]
                    ),
                ],
                [
                    "in_reference",
                    "post_reference_supported",
                    "post_reference_limited_support",
                ],
                default="not_evaluable",
            ),
            index=frame.index,
        )
        version = pd.Series(
            config["inputs"]["D4"]["expected_mapping_sha256"], index=frame.index
        )
    elif dimension == "D5":
        fit_end = pd.Timestamp(contract["fit_end"])
        embargo_end = pd.Timestamp(contract["embargo_end"])
        phase = pd.Series(
            np.select(
                [timestamp.le(fit_end), timestamp.le(embargo_end)],
                ["development", "embargo"],
                default="internal_validation",
            ),
            index=frame.index,
        )
        evaluable = frame["evaluation_status"].eq("evaluable")
        ood = frame["evaluation_status"].eq("out_of_template") | frame[
            "regime_state"
        ].astype(str).str.contains("ood", case=False, na=False)
        limited = frame["support_level"].eq("L1")
        reference = pd.Series(
            np.select(
                [
                    timestamp.le(fit_end),
                    timestamp.le(embargo_end),
                    ood,
                    limited,
                    evaluable,
                ],
                [
                    "in_reference",
                    "not_evaluable",
                    "OOD",
                    "post_reference_limited_support",
                    "post_reference_supported",
                ],
                default="not_evaluable",
            ),
            index=frame.index,
        )
        version = frame["template_hash"].fillna(source_hash).astype(str)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")
    return phase, reference, version


def build_dimension_long(
    config: dict[str, Any],
    d1: pd.DataFrame,
    d2: pd.DataFrame,
    d3: pd.DataFrame,
    d4: pd.DataFrame,
    d5: pd.DataFrame,
) -> pd.DataFrame:
    specs = config["inputs"]
    records: list[pd.DataFrame] = []
    d1_phase, d1_reference, d1_version = _phase_reference_metadata(
        config, "D1", d1
    )
    records.append(
        _dimension_record(
            d1,
            dimension="D1",
            object_type="sensor",
            object_id="sensor_id",
            score="D1_total",
            diagnostic_score="D1_total",
            applicable=pd.Series(True, index=d1.index),
            evaluable=d1["D1_total"].notna(),
            report_eligible=d1["D1_total"].notna(),
            support_level="released",
            status_reason=pd.Series(
                np.where(d1["D1_total"].notna(), "scored", "missing_score"),
                index=d1.index,
            ),
            run_id=d1["D1_run_id"],
            calibration_id="embedded_release_mapping",
            version_hash=d1_version,
            phase_role=d1_phase,
            reference_status=d1_reference,
            mapping_support_class="not_applicable",
            source_hash=specs["D1"]["expected_sha256"],
            metadata_columns=["D1_legacy_usable_tag"],
        )
    )
    d2_phase, d2_reference, d2_version = _phase_reference_metadata(
        config, "D2", d2
    )
    records.append(
        _dimension_record(
            d2,
            dimension="D2",
            object_type="sensor",
            object_id="sensor_id",
            score="D2_total",
            diagnostic_score="D2_total",
            applicable=pd.Series(True, index=d2.index),
            evaluable=d2["D2_total"].notna(),
            report_eligible=d2["D2_total"].notna(),
            support_level=d2["D2_usable_tag"],
            status_reason=d2["D2_veto_reason"].fillna("scored"),
            run_id=d2["D2_run_id"],
            calibration_id=d2["D2_calibration_id"],
            version_hash=d2_version,
            phase_role=d2_phase,
            reference_status=d2_reference,
            mapping_support_class="not_applicable",
            source_hash=specs["D2"]["expected_sha256"],
            metadata_columns=[
                "D2_usable_tag",
                "D2_veto_flag",
                "D2_veto_reason",
                "D2_dominant_limitation",
            ],
        )
    )
    d3_phase, d3_reference, d3_version = _phase_reference_metadata(
        config, "D3", d3
    )
    records.append(
        _dimension_record(
            d3,
            dimension="D3",
            object_type="sensor",
            object_id="sensor_id",
            score=None,
            diagnostic_score="D3_total",
            applicable=pd.Series(True, index=d3.index),
            evaluable=d3["D3_gate_status"].ne("NotEvaluated"),
            report_eligible=d3["D3_gate_status"].ne("NotEvaluated"),
            support_level=d3["D3_evidence_status"],
            status_reason=d3["D3_gate_status"],
            run_id=d3["D3_run_id"],
            calibration_id=d3["D3_threshold_version"].astype(str)
            + "|"
            + d3["D3_mapping_version"].astype(str),
            version_hash=d3_version,
            phase_role=d3_phase,
            reference_status=d3_reference,
            mapping_support_class="not_applicable",
            source_hash=specs["D3"]["expected_sha256"],
            metadata_columns=[
                "D3_gate_status",
                "D3_dominant_issue",
                "D3_veto_flag",
                "D3_operational_warning_flag",
                "D3_temperature_upper_status",
                "source_window_end_exclusive",
            ],
        )
    )
    d4_evaluable = d4["usable_for_D4"].fillna(False) & d4["D4_raw"].notna()
    d4_long = d4.copy()
    d4_long["D4_score_formal"] = d4_long["D4_raw"].where(d4_evaluable)
    d4_phase, d4_reference, d4_version = _phase_reference_metadata(
        config, "D4", d4_long
    )
    records.append(
        _dimension_record(
            d4_long,
            dimension="D4",
            object_type="pair",
            object_id="pair_id",
            score="D4_score_formal",
            diagnostic_score="D4_raw",
            applicable=pd.Series(True, index=d4.index),
            evaluable=d4_evaluable,
            report_eligible=d4_evaluable,
            support_level=d4_long["mapping_support_class"],
            status_reason=pd.Series(
                np.where(
                    d4_evaluable,
                    "scored_with_" + d4_long["mapping_support_class"].astype(str),
                    "not_usable_for_D4",
                ),
                index=d4.index,
            ),
            run_id=d4["run_id"],
            calibration_id=d4["calibration_id"],
            version_hash=d4_version,
            phase_role=d4_phase,
            reference_status=d4_reference,
            mapping_support_class=d4_long["mapping_support_class"],
            source_hash=specs["D4"]["expected_sha256"],
            metadata_columns=[
                "sensor_id",
                "pair_sensor_id",
                "regime_id",
                "usable_for_D4",
                "valid_fraction_common_hours",
                "calibration_scope",
                "calibration_quality",
                "calibration_evidence_quality",
                "calibration_independent_blocks",
                "calibration_exact_independent_blocks",
                "calibration_sample_size",
                "calibration_tail_precision_grade",
            ],
        )
    )
    d5_evaluable = d5["report_eligible"].fillna(False) & d5["D5_report_score"].notna()
    d5_long = d5.copy()
    d5_long["D5_score_formal"] = d5_long["D5_report_score"].where(d5_evaluable)
    d5_phase, d5_reference, d5_version = _phase_reference_metadata(
        config, "D5", d5_long
    )
    records.append(
        _dimension_record(
            d5_long,
            dimension="D5",
            object_type="sensor",
            object_id="sensor_id",
            score="D5_score_formal",
            diagnostic_score="D5_raw",
            applicable=pd.Series(True, index=d5.index),
            evaluable=d5["evaluation_status"].eq("evaluable"),
            report_eligible=d5_evaluable,
            support_level=d5["support_level"],
            status_reason=d5["status_reason"].fillna(d5["evaluation_status"]),
            run_id=d5["run_id"],
            calibration_id=d5["template_id_used"],
            version_hash=d5_version,
            phase_role=d5_phase,
            reference_status=d5_reference,
            mapping_support_class="not_applicable",
            source_hash=specs["D5"]["expected_sha256"],
            metadata_columns=[
                "evaluation_status",
                "support_level",
                "family_support_level",
                "node_support_level",
                "node_validation_passed",
                "confidence",
                "uncertainty",
                "active_regime_id",
                "regime_state",
                "ood_distance",
                "template_hash",
                "topology_hash",
                "mapping_version",
            ],
        )
    )
    output = pd.concat(records, ignore_index=True)
    numeric = output["score_1to5"].dropna()
    low = float(config["aggregation"]["score_min"])
    high = float(config["aggregation"]["score_max"])
    if not numeric.between(low, high).all():
        raise RuntimeError("Formal dimension score outside the frozen 1-5 scale")
    return output.sort_values(["timestamp", "object_type", "object_id", "dimension"]).reset_index(drop=True)


def build_phase_evidence_summary(dimension_long: pd.DataFrame) -> pd.DataFrame:
    return (
        dimension_long.groupby(
            [
                "dimension",
                "phase_role",
                "reference_status",
                "mapping_support_class",
            ],
            dropna=False,
            observed=True,
        )
        .agg(
            n_rows=("timestamp", "size"),
            applicable_rate=("applicable", "mean"),
            evaluable_rate=("evaluable", "mean"),
            report_eligible_rate=("report_eligible", "mean"),
            median_formal_score=("score_1to5", "median"),
            p05_formal_score=("score_1to5", lambda x: x.quantile(0.05)),
            median_diagnostic_score=("diagnostic_score_1to5", "median"),
        )
        .reset_index()
    )


def build_node_scores(
    config: dict[str, Any],
    d1: pd.DataFrame,
    d2: pd.DataFrame,
    d3: pd.DataFrame,
    d5: pd.DataFrame,
) -> pd.DataFrame:
    node = d5[
        [
            "timestamp",
            "sensor_id",
            "analyte",
            "line_id",
            "zone_id",
            "position_order",
            "pair_id",
            "D5_report_score",
            "D5_raw",
            "uncertainty",
            "confidence",
            "evaluation_status",
            "status_reason",
            "report_eligible",
            "support_level",
            "family_support_level",
            "node_support_level",
            "active_regime_id",
            "regime_state",
            "ood_distance",
            "run_id",
            "template_hash",
            "topology_hash",
        ]
    ].rename(
        columns={
            "uncertainty": "D5_uncertainty",
            "confidence": "D5_confidence",
            "evaluation_status": "D5_evaluation_status",
            "status_reason": "D5_status_reason",
            "report_eligible": "D5_report_eligible",
            "support_level": "D5_support_level",
            "family_support_level": "D5_family_support_level",
            "node_support_level": "D5_node_support_level",
            "run_id": "D5_run_id",
        }
    )
    node = node.merge(d1, on=["timestamp", "sensor_id"], how="left")
    node = node.merge(d2, on=["timestamp", "sensor_id"], how="left")
    node = node.merge(d3, on=["timestamp", "sensor_id"], how="left")
    node["I_D1"] = node["D1_total"].notna()
    node["I_D2"] = node["D2_total"].notna()
    node["I_D5"] = node["D5_report_eligible"].fillna(False) & node[
        "D5_report_score"
    ].notna()
    node["core_evaluable"] = node["I_D1"] & node["I_D2"]
    node["evidence_atom_count"] = node[["I_D1", "I_D2", "I_D5"]].sum(axis=1)
    node["E_node"] = node["evidence_atom_count"] / 3.0
    numerator = node["D1_total"] + node["D2_total"] + node["D5_report_score"].where(
        node["I_D5"], 0.0
    )
    denominator = 2.0 + node["I_D5"].astype(float)
    node["Q_node_available"] = (numerator / denominator).where(node["core_evaluable"])
    node["Q_node_core12"] = node[["D1_total", "D2_total"]].mean(axis=1).where(
        node["core_evaluable"]
    )
    node["Q_node_full"] = node[["D1_total", "D2_total", "D5_report_score"]].mean(
        axis=1
    ).where(node["I_D1"] & node["I_D2"] & node["I_D5"])
    node["coverage_class"] = np.select(
        [
            node[["I_D1", "I_D2", "I_D5"]].all(axis=1),
            node["core_evaluable"],
            node["evidence_atom_count"].gt(0),
        ],
        ["full", "basic", "limited"],
        default="insufficient",
    )
    node["dimension_mask"] = node.apply(
        lambda row: "|".join(
            dimension
            for dimension, field in (("D1", "I_D1"), ("D2", "I_D2"), ("D5", "I_D5"))
            if bool(row[field])
        )
        or "none",
        axis=1,
    )
    node["D3_gate_status"] = node["D3_gate_status"].fillna("NotEvaluated")
    node["release_status"] = resolve_release_status(
        node["Q_node_available"],
        node["D3_gate_status"],
        node["coverage_class"],
    )
    node["core_release_status"] = resolve_release_status(
        node["Q_node_core12"], node["D3_gate_status"], node["coverage_class"]
    )
    node["full_release_status"] = resolve_release_status(
        node["Q_node_full"], node["D3_gate_status"], node["coverage_class"]
    )
    node["strict_contract_candidate"] = node["coverage_class"].eq("full") & node[
        "D3_gate_status"
    ].eq("Pass")
    node["strict_release_status"] = np.where(
        node["strict_contract_candidate"],
        "pending_D1_hard_fault_interface",
        "not_contract_candidate",
    )
    node["sensitive_contract_candidate"] = node["Q_node_available"].notna() & node[
        "D3_gate_status"
    ].isin(["Pass", "Warn"])
    node["D1_hard_fault_interface_status"] = config["aggregation"][
        "D1_hard_fault_interface"
    ]
    node["D5_sensor_hard_veto_status"] = config["aggregation"]["D5_sensor_hard_veto"]
    node["measurement_assurance_status"] = config["aggregation"][
        "measurement_assurance_status"
    ]
    node["full_aggregation_formula"] = "equal_mean_D1_D2_D5_report"
    node["core_aggregation_formula"] = "equal_mean_D1_D2_fixed"
    node["available_aggregation_formula"] = "equal_mean_D1_D2_optional_D5"
    return node.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)


def build_pair_scores(
    config: dict[str, Any], node: pd.DataFrame, d4: pd.DataFrame
) -> pd.DataFrame:
    fields = [
        "timestamp",
        "sensor_id",
        "analyte",
        "Q_node_full",
        "Q_node_core12",
        "Q_node_available",
        "E_node",
        "coverage_class",
        "dimension_mask",
        "D3_gate_status",
        "I_D1",
        "I_D2",
        "I_D5",
        "D1_total",
        "D2_total",
        "D5_report_score",
        "D5_raw",
    ]
    left = node[fields].add_prefix("left_").rename(columns={"left_timestamp": "timestamp"})
    right = node[fields].add_prefix("right_").rename(columns={"right_timestamp": "timestamp"})
    pair = d4.merge(
        left,
        left_on=["timestamp", "sensor_id"],
        right_on=["timestamp", "left_sensor_id"],
        how="left",
    ).merge(
        right,
        left_on=["timestamp", "pair_sensor_id"],
        right_on=["timestamp", "right_sensor_id"],
        how="left",
    )
    pair["I_D4"] = pair["usable_for_D4"].fillna(False) & pair["D4_raw"].notna()
    pair["Q_pair_available"] = pair[
        ["left_Q_node_available", "right_Q_node_available", "D4_raw"]
    ].mean(axis=1).where(
        pair["left_Q_node_available"].notna()
        & pair["right_Q_node_available"].notna()
        & pair["I_D4"]
    )
    pair["Q_pair_core"] = pair[
        ["left_Q_node_core12", "right_Q_node_core12", "D4_raw"]
    ].mean(axis=1).where(
        pair["left_Q_node_core12"].notna()
        & pair["right_Q_node_core12"].notna()
        & pair["I_D4"]
    )
    pair["Q_pair_full"] = pair[
        ["left_Q_node_full", "right_Q_node_full", "D4_raw"]
    ].mean(axis=1).where(
        pair["left_Q_node_full"].notna()
        & pair["right_Q_node_full"].notna()
        & pair["I_D4"]
    )
    atoms = [
        "left_I_D1",
        "left_I_D2",
        "left_I_D5",
        "right_I_D1",
        "right_I_D2",
        "right_I_D5",
        "I_D4",
    ]
    pair["evidence_atom_count"] = pair[atoms].fillna(False).sum(axis=1)
    pair["E_pair"] = pair["evidence_atom_count"] / 7.0
    pair["coverage_class"] = np.select(
        [
            pair["Q_pair_full"].notna(),
            pair["Q_pair_available"].notna(),
            pair["evidence_atom_count"].gt(0),
        ],
        ["full", "basic", "limited"],
        default="insufficient",
    )
    pair["dimension_mask"] = pair.apply(
        lambda row: "|".join(
            label
            for label, field in (
                ("L:D1", "left_I_D1"),
                ("L:D2", "left_I_D2"),
                ("L:D5", "left_I_D5"),
                ("R:D1", "right_I_D1"),
                ("R:D2", "right_I_D2"),
                ("R:D5", "right_I_D5"),
                ("D4", "I_D4"),
            )
            if bool(row.get(field, False))
        )
        or "none",
        axis=1,
    )
    pair["D3_gate_status"] = combine_gate(
        pair["left_D3_gate_status"], pair["right_D3_gate_status"]
    )
    pair["release_status"] = resolve_release_status(
        pair["Q_pair_available"],
        pair["D3_gate_status"],
        pair["coverage_class"],
    )
    pair["core_release_status"] = resolve_release_status(
        pair["Q_pair_core"], pair["D3_gate_status"], pair["coverage_class"]
    )
    pair["full_release_status"] = resolve_release_status(
        pair["Q_pair_full"], pair["D3_gate_status"], pair["coverage_class"]
    )
    pair["strict_contract_candidate"] = pair["coverage_class"].eq("full") & pair[
        "D3_gate_status"
    ].eq("Pass")
    pair["strict_release_status"] = np.where(
        pair["strict_contract_candidate"],
        "pending_D1_hard_fault_interface",
        "not_contract_candidate",
    )
    pair["sensitive_contract_candidate"] = pair["Q_pair_available"].notna() & pair[
        "D3_gate_status"
    ].isin(["Pass", "Warn"])
    pair["D4_role"] = "native_pair_evidence_not_copied_to_sensor_rows"
    pair["full_aggregation_formula"] = "equal_mean_left_full_right_full_D4_raw"
    pair["core_aggregation_formula"] = "equal_mean_left_core12_right_core12_D4_raw"
    pair["available_aggregation_formula"] = "equal_mean_left_available_right_available_D4_raw"
    return pair.sort_values(["pair_id", "timestamp"]).reset_index(drop=True)


def build_monthly_coverage(node: pd.DataFrame, pair: pd.DataFrame) -> pd.DataFrame:
    node_source = node.assign(month=node["timestamp"].dt.to_period("M").astype(str))
    node_source["D5_ood"] = node_source["D5_evaluation_status"].eq("out_of_template")
    node_source["D5_L1"] = node_source["D5_support_level"].eq("L1")
    node_source["D5_L2"] = node_source["D5_support_level"].eq("L2")
    node_source["D5_L3"] = node_source["D5_support_level"].eq("L3")

    def node_summary(frame: pd.DataFrame, keys: list[str], level: str) -> pd.DataFrame:
        result = (
            frame.groupby(keys, dropna=False, observed=True)
            .agg(
                n_hours=("timestamp", "size"),
                q_available_rate=("Q_node_available", lambda s: s.notna().mean()),
                q_core_rate=("Q_node_core12", lambda s: s.notna().mean()),
                q_full_rate=("Q_node_full", lambda s: s.notna().mean()),
                q_available_median=("Q_node_available", "median"),
                q_core_median=("Q_node_core12", "median"),
                q_full_median=("Q_node_full", "median"),
                full_rate=("coverage_class", lambda s: s.eq("full").mean()),
                basic_rate=("coverage_class", lambda s: s.eq("basic").mean()),
                limited_rate=("coverage_class", lambda s: s.eq("limited").mean()),
                insufficient_rate=("coverage_class", lambda s: s.eq("insufficient").mean()),
                D5_report_rate=("I_D5", "mean"),
                D5_ood_rate=("D5_ood", "mean"),
                D5_L1_rate=("D5_L1", "mean"),
                D5_L2_rate=("D5_L2", "mean"),
                D5_L3_rate=("D5_L3", "mean"),
                D3_pass_rate=("D3_gate_status", lambda s: s.eq("Pass").mean()),
                D3_warn_rate=("D3_gate_status", lambda s: s.eq("Warn").mean()),
                D3_fail_rate=("D3_gate_status", lambda s: s.eq("Fail").mean()),
                D3_ne_rate=("D3_gate_status", lambda s: s.eq("NotEvaluated").mean()),
            )
            .reset_index()
        )
        result["object_type"] = "node"
        result["aggregation_level"] = level
        return result

    node_frames = [
        node_summary(node_source, ["month", "sensor_id", "analyte"], "sensor"),
        node_summary(node_source, ["month", "analyte"], "analyte"),
        node_summary(node_source, ["month"], "all_nodes"),
    ]
    pair_source = pair.assign(month=pair["timestamp"].dt.to_period("M").astype(str))

    def pair_summary(frame: pd.DataFrame, keys: list[str], level: str) -> pd.DataFrame:
        result = (
            frame.groupby(keys, dropna=False, observed=True)
            .agg(
                n_hours=("timestamp", "size"),
                q_available_rate=("Q_pair_available", lambda s: s.notna().mean()),
                q_core_rate=("Q_pair_core", lambda s: s.notna().mean()),
                q_full_rate=("Q_pair_full", lambda s: s.notna().mean()),
                q_available_median=("Q_pair_available", "median"),
                q_core_median=("Q_pair_core", "median"),
                q_full_median=("Q_pair_full", "median"),
                D4_exact_mapping_rate=("mapping_support_class", lambda s: s.eq("exact").mean()),
                D4_variable_fallback_rate=("mapping_support_class", lambda s: s.eq("variable_fallback").mean()),
                D4_global_fallback_rate=("mapping_support_class", lambda s: s.eq("global_fallback").mean()),
                full_rate=("coverage_class", lambda s: s.eq("full").mean()),
                basic_rate=("coverage_class", lambda s: s.eq("basic").mean()),
                limited_rate=("coverage_class", lambda s: s.eq("limited").mean()),
                insufficient_rate=("coverage_class", lambda s: s.eq("insufficient").mean()),
                D3_pass_rate=("D3_gate_status", lambda s: s.eq("Pass").mean()),
                D3_warn_rate=("D3_gate_status", lambda s: s.eq("Warn").mean()),
                D3_fail_rate=("D3_gate_status", lambda s: s.eq("Fail").mean()),
                D3_ne_rate=("D3_gate_status", lambda s: s.eq("NotEvaluated").mean()),
            )
            .reset_index()
        )
        result["object_type"] = "pair"
        result["aggregation_level"] = level
        return result

    pair_frames = [
        pair_summary(pair_source, ["month", "pair_id", "variable"], "pair"),
        pair_summary(pair_source, ["month", "variable"], "analyte"),
        pair_summary(pair_source, ["month"], "all_pairs"),
    ]
    return pd.concat([*node_frames, *pair_frames], ignore_index=True, sort=False)
