"""Production D2 prefix tests on synthetic pre-holdout clocks, no later data."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from runtime import DIMENSIONS, OUTPUT, PROJECT, write_json
from causal_gap_evidence import causal_gap_evidence
import d2_causal_adapter as causal

D2 = PROJECT / DIMENSIONS["D2"]
sys.path.insert(0, str(D2))
import run_d2_pipeline as pipeline


def execute(values: pd.DataFrame, cache: Path, key: str, corrected: bool = False):
    pipeline.CACHE = cache
    pipeline.CACHE_KEY = key
    pipeline.SOURCE_TIMESTAMP_AUDIT = {"hourly": pd.DataFrame()}
    flags = causal.preprocess(values, pipeline) if corrected else pipeline.compute_preprocess_flags(values, values)
    stats = causal.window_stats(flags, pipeline) if corrected else pipeline.compute_window_stats(flags)
    calibration = yaml.safe_load((D2 / "d2_calibration.yaml").read_text(encoding="utf-8"))
    # The Strict route disables response-loss; this probe intentionally isolates
    # continuity and observation evidence, not the Sensitive peer diagnostic.
    subs = pipeline.compute_subscores(stats, {}, calibration)
    scores, _ = pipeline.aggregate_d2(subs, calibration)
    return flags, stats, scores


def main() -> None:
    index = pd.date_range("2026-02-01", periods=3 * 1440, freq="1min")
    t = np.arange(len(index))
    raw = pd.DataFrame({sensor: ((0.1 if sensor.endswith("_4") else 2.0)
                                + 0.04 * np.sin(t * 0.9))
                        if sensor.startswith("DO") else -120 + 10 * np.sin(t * 0.9)
                        for sensor in pipeline.SCORED_CHANNELS}, index=index)
    # At 47:58 a missing run starts. At 48:00 its eventual duration is unknown.
    boundary = 48 * 60
    raw.iloc[boundary - 2:boundary + 30] = np.nan
    cutoff = index[boundary - 1]
    with tempfile.TemporaryDirectory(prefix="d2-prefix-") as directory:
        cache = Path(directory)
        short = execute(raw.iloc[:boundary], cache, "prefix")
        full = execute(raw, cache, "full")
        causal_short = execute(raw.iloc[:boundary], cache, "asof-prefix", corrected=True)
        causal_full = execute(raw, cache, "asof-full", corrected=True)
    for sensor in pipeline.SCORED_CHANNELS:
        for pos in range(3):
            a = causal_short[pos][sensor]
            b = causal_full[pos][sensor].reindex(a.index)
            # Run identifiers are packaging metadata, not streaming state.
            cols = [c for c in a if c not in {"run_id", "calibration_id"}]
            pd.testing.assert_frame_equal(a[cols], b[cols], check_freq=False)
    rows = []
    for sensor in pipeline.SCORED_CHANNELS:
        for kind, columns, pos in [
            ("minute_flag", ["present_raw", "missing", "long_gap", "sensor_freeze", "info_empty"], 0),
            ("window_stat", ["missing_rate", "L_max_min", "gap_run_count", "P95_gap_min"], 1),
            ("hourly_score", ["Q_TI", "Q_GS", "Q_HA", "D2_total", "veto_flag", "usable_tag"], 2),
        ]:
            a = short[pos][sensor]
            b = full[pos][sensor].reindex(a.index)
            for column in columns:
                same = a[column].eq(b[column]) | (a[column].isna() & b[column].isna())
                rows.append({"sensor_id": sensor, "kind": kind, "field": column,
                             "compared_rows": len(a), "changed_prefix_rows": int((~same).sum()),
                             "first_changed_time": str(a.index[~same][0]) if (~same).any() else "",
                             "prefix_end": str(cutoff), "future_change": "append_only"})
    table = pd.DataFrame(rows)
    (OUTPUT / "audit").mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT / "audit/D2_prefix_contract.csv", index=False)
    fixed_prefix = causal_gap_evidence(raw.DO_1_4.iloc[:boundary])
    fixed_full = causal_gap_evidence(raw.DO_1_4)
    pd.testing.assert_frame_equal(fixed_prefix, fixed_full.iloc[:boundary])
    case = pd.DataFrame({
        "timestamp": index,
        "raw_observed": raw.DO_1_4.notna().to_numpy().astype(int),
        "legacy_full_long_gap": full[0]["DO_1_4"].long_gap.to_numpy(),
        "legacy_prefix_long_gap": short[0]["DO_1_4"].long_gap.reindex(index).to_numpy(),
        "causal_long_gap_asof": fixed_full.long_gap_asof.to_numpy().astype(int),
        "causal_completed_gap_length": fixed_full.completed_gap_length_known_now.to_numpy(),
        "causal_P95_completed": fixed_full.P95_completed_gap_24h_asof.to_numpy(),
    })
    case = case.loc[case.timestamp.between(index[boundary - 12], index[boundary + 40])]
    case.to_csv(OUTPUT / "audit/D2_gap_timing_case.csv", index=False)
    write_json(OUTPUT / "audit/D2_prefix_contract_qa.json", {
        "test_kind": "production_functions_synthetic_pre_holdout_clock",
        "raw_holdout_loaded": False,
        "all_evidence_prefix_invariant": bool(table.changed_prefix_rows.sum() == 0),
        "changed_fields": sorted(table.loc[table.changed_prefix_rows.gt(0), "field"].unique()),
        "strict_response_loss": "disabled_by_production_contract",
        "sensitive_peer_route_tested": False,
        "new_asof_gap_helper_prefix_test": "passed",
        "new_helper_in_production_D2": False,
        "isolated_candidate_flags_stats_Strict_prefix_passed": True,
        "notes": "Scores are hour-start-labelled, available at the next hour; completion-dependent evidence requires separate audit.",
    })
    print(table.loc[table.changed_prefix_rows.gt(0)].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
