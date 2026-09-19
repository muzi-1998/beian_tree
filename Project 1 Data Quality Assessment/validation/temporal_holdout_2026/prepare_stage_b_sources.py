"""Assemble derived audit sources and fail-closed stage status, never open scores."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from information_time import interval_contract
from runtime import HERE, OUTPUT, START, END, D5_REFERENCE_END, write_json


def main() -> None:
    source = OUTPUT / "source_data"
    source.mkdir(parents=True, exist_ok=True)
    intervals = pd.concat([interval_contract(d, pd.DatetimeIndex(["2026-02-15 00:00"]))
                           for d in ["D1", "D2", "D3", "D4", "D5"]], ignore_index=True)
    intervals["closure_delay_minutes"] = (intervals.base_available_at - intervals.timestamp_label).dt.total_seconds()/60
    intervals.to_csv(source / "information_intervals.csv", index=False)
    timeline = pd.DataFrame([
        {"series": "Historical replay", "start": "2025-08-01", "end_exclusive": str(START), "status": "old_data_only"},
        {"series": "D5 reference", "start": "2025-08-01", "end_exclusive": str(D5_REFERENCE_END + pd.Timedelta(minutes=10)),
         "status": "absolute_reference_not_full_year_fraction"},
        {"series": "Later period", "start": str(START), "end_exclusive": str(END), "status": "scoring_unopened"},
    ])
    timeline.to_csv(source / "validation_timeline.csv", index=False)
    tables = {"Temporal scope": timeline, "Information intervals": intervals,
              "D2 synthetic": pd.read_csv(OUTPUT / "audit/D2_gap_timing_case.csv"),
              "D4 synthetic": pd.read_csv(OUTPUT / "audit/D4_cp_timing_case.csv"),
              "D4 historical impact": pd.read_csv(OUTPUT / "audit/D4_historical_CP_timing_summary.csv"),
              "D2 historical impact": pd.read_csv(OUTPUT / "audit/D2_historical_timing_summary.csv"),
              "D4 mapping replay": pd.read_csv(OUTPUT / "audit/D4_mapping_historical_replay.csv"),
              "D1 PLS replay": pd.read_csv(OUTPUT / "audit/D1_pls_historical_replay.csv"),
              "D1 recovery replay": pd.read_csv(OUTPUT / "audit/D1_recovery_historical_replay.csv"),
              "D1 recovery prefix": pd.read_csv(OUTPUT / "audit/D1_recovery_prefix_audit.csv"),
              "Minute alignment": pd.read_csv(OUTPUT / "audit/minute_alignment_historical_replay.csv"),
              "Transform replay": pd.read_csv(OUTPUT / "audit/decomposition_and_filter_replay.csv"),
              "D5 context replay": pd.read_csv(OUTPUT / "audit/D5_context_historical_replay.csv"),
              "D3 replay": pd.read_csv(OUTPUT / "audit/D3_historical_replay.csv")}
    impact = tables["D4 historical impact"]
    impact["changed_Q_cp_pct"] = 100*impact.changed_Q_cp_hours/impact.n_pair_hours
    impact["low_tail_flip_pct_common"] = 100*impact.low_tail_flip_hours/impact.common_evaluable_hours
    for name, table in tables.items():
        table.to_parquet(source / (name.replace(" ", "_") + ".parquet"), index=False)
    payload = []
    for name, table in tables.items():
        clean = table.astype(object).where(pd.notna(table), None)
        rows = [[str(v) if isinstance(v, pd.Timestamp) else v for v in row] for row in clean.values.tolist()]
        payload.append({"name": name, "columns": table.columns.tolist(), "rows": rows})
    write_json(source / "workbook_tables.json", payload)
    write_json(OUTPUT / "opening_gate.json", {
        "stage": "B_in_progress_holdout_closed",
        "historical_replay": "partial_component_replay_not_all_dimension_end_to_end",
        "prefix_invariance": "native_D2_and_D4_failed_corrected_candidates_pass_synthetic_tests",
        "chunk_equivalence": "partial_minute_alignment_whitener_context_and_D1_recovery_journal_not_full_pipeline",
        "time_contract": "audited_candidate_intervals_not_integrated_DQR_asof_join",
        "unknown_evidence": "partial_D2_timestamp_unknown_preserved",
        "asset_closure": "partial_D5_numeric_equivalent_reconstruction_not_byte_identity",
        "performance_opening_allowed": False,
        "new_period_scores_computed": False,
        "source_attestation": "researcher_confirmed_not_independent_SCADA_verification",
        "reason": "Research-plan Stage B stop-and-investigate rule applies to time leakage; no performance-based threshold changes.",
    })
    write_json(source / "source_index.json", {
        "stage": "historical_replay_and_synthetic_contract_audit",
        "data_kind": "derived_results_no_raw_plant_time_series",
        "n_future_scores": 0,
        "tables": {name: {"rows": len(table), "columns": len(table.columns)} for name, table in tables.items()},
        "statistical_unit": "paired old-period hours; deterministic contract examples",
        "CI": "not_applicable_to_deterministic_replay_or_exact_finite_dataset_difference",
        "historical_D4_sensitivity_scope": "CP_dedup_and_clock_only_other_risks_mappings_gates_fixed",
    })


if __name__ == "__main__":
    main()
