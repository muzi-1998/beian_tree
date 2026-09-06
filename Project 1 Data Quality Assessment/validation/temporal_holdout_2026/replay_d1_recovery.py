"""Old-period D1 recovery replay and scheduled-candidate sensitivity, no holdout."""
from __future__ import annotations

import json
import pickle
from dataclasses import asdict

import numpy as np
import pandas as pd
import yaml

from runtime import HERE, DIMENSIONS, OFFICIAL, PROJECT, OUTPUT, START, sha256, write_json
from d1_recovery_adapter import (FIELDS, CooldownConfig, FrozenD1Recovery,
                                  aggregation_contract, fingerprint, normalize_events, score_recovery)
from d1_scheduled_changepoints import scheduled_candidates
from src.state.auxiliary_modules import PELTBatchCalibrator

SOURCE_HASH = "6aaede79b37d64c5af627364cc98b8fa1344b05f1ff37524a68d8732c3889a96"


def difference(a: pd.DataFrame, b: pd.DataFrame) -> tuple[int, float]:
    if list(a.columns) != list(b.columns) or not a.index.equals(b.index):
        raise ValueError("Replay dimensions are not identical")
    changed = pd.Series(False, index=a.index)
    maximum = 0.
    for col in a:
        left, right = a[col], b[col]
        null = left.isna() != right.isna()
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            delta = (left.astype(float)-right.astype(float)).abs()
            maximum = max(maximum, float(delta.max()) if delta.notna().any() else 0.)
            changed |= null | delta.gt(1e-10)
        else:
            changed |= null | ~(left.eq(right) | (left.isna() & right.isna()))
    return int(changed.sum()), maximum


def evidence_from_state(state: dict, sensor: str) -> pd.DataFrame:
    data = {k: state["subs_v1"][k][sensor] for k in FIELDS[:5]}
    data.update({"ks_stat": state["detectors_raw"]["ks_statistic_hourly"][sensor],
                 "w1_norm": state["detectors_raw"]["w1_normalised_hourly"][sensor],
                 "resid_h": state["resid_h"][sensor],
                 "step_confirmed": state["detectors_raw"]["step_confirmed_flag"][sensor],
                 "peer_residual_z": state["detectors_raw"]["pls_residual_z_hourly"][sensor]})
    return pd.DataFrame(data).reindex(columns=FIELDS).astype(float)


def main() -> None:
    source = OFFICIAL / DIMENSIONS["D1"] / "v11_state.pkl"
    if sha256(source) != SOURCE_HASH:
        raise ValueError("Unverified frozen D1 state")
    with source.open("rb") as handle:
        state = pickle.load(handle)
    if state["D1_v11"].index.max() >= START:
        raise ValueError("Holdout observations are not allowed")
    for filename, name in [("rules.yaml", "rules_yaml"), ("state_machine.yaml", "state_machine_yaml")]:
        actual = yaml.safe_load((PROJECT / DIMENSIONS["D1"] / "configs" / filename).read_text(encoding="utf-8"))
        if actual != state[name]:
            raise ValueError(f"Frozen configuration differs: {filename}")
    aggregation = aggregation_contract(state["rules_yaml"], state["state_machine_yaml"])
    rows, prefix_rows, score_rows, configs = [], [], [], {}
    checkpoint_folder = HERE / ".local_qa/D1_recovery_journals"
    checkpoint_folder.mkdir(parents=True, exist_ok=True)
    for sensor in state["scored_channels"]:
        evidence = evidence_from_state(state, sensor)
        cfg = asdict(CooldownConfig.from_dict(state["state_machine_yaml"],
                    local_scale_floor=state["scale_calibration"][sensor]["scale_floor"]))
        configs[sensor] = cfg
        original, transitions = score_recovery(sensor, evidence, state["pelt_results"][sensor], cfg, aggregation)
        old_log = state["state_log_dict"][sensor]
        state_mismatch, max_state_difference = difference(original[old_log.columns], old_log)
        score_delta = (original.D1_total-state["D1_v11"][sensor]).abs()
        drift_delta = (original.Q_drift_eff-state["Q_drift_eff_dict"][sensor]).abs()
        old_veto = state["veto_logs_v11"][sensor]
        veto_mismatch, _ = difference(original[old_veto.columns], old_veto)
        old_transitions = [t for t in state["transitions_all"] if t["sensor_id"] == sensor]
        transitions_equal = fingerprint(transitions) == fingerprint(old_transitions)
        raw = state["whitened_input_h"][sensor]
        neff = float(state["eff_neff"].get(sensor, 1.))
        native = PELTBatchCalibrator(neff_ratio=neff).calibrate_series(raw)
        native_equal = fingerprint(native) == fingerprint(state["pelt_results"][sensor])
        causal = scheduled_candidates(raw, neff_ratio=neff)
        candidate, candidate_transitions = score_recovery(sensor, evidence, causal, cfg, aggregation)
        for cutoff in pd.to_datetime(["2026-02-01", "2026-03-01", "2026-04-01"]):
            prefix_input = evidence.loc[evidence.index < cutoff]
            native_prefix = PELTBatchCalibrator(neff_ratio=neff).calibrate_series(raw.loc[raw.index < cutoff])
            available_native = [e for e in native if e["available_at"] < cutoff]
            a = {fingerprint(e) for e in native_prefix}
            b = {fingerprint(e) for e in available_native}
            prefix_score, _ = score_recovery(sensor, prefix_input, native_prefix, cfg, aggregation)
            state_rows, _ = difference(prefix_score[old_log.columns], original.loc[prefix_input.index, old_log.columns])
            causal_prefix = scheduled_candidates(raw.loc[raw.index < cutoff], neff_ratio=neff)
            expected_causal = [e for e in causal if e["available_at"] < cutoff]
            corrected, _ = score_recovery(sensor, prefix_input, causal_prefix, cfg, aggregation)
            candidate_changed, _ = difference(corrected, candidate.loc[prefix_input.index])
            prefix_rows.append({"sensor_id": sensor, "cutoff_exclusive": cutoff,
                "native_candidate_symmetric_difference": len(a ^ b), "native_state_changed_hours": state_rows,
                "native_score_changed_hours": int((prefix_score.D1_total-original.D1_total).abs().gt(1e-10).sum()),
                "candidate_event_prefix_equal": fingerprint(causal_prefix) == fingerprint(expected_causal),
                "candidate_output_changed_hours": candidate_changed})
        stream = FrozenD1Recovery(sensor, cfg, aggregation)
        journal_output, journal_events = [], []
        n = len(evidence)
        for begin, end in [(0, n-25), (n-25, n-1), (n-1, n)]:
            block = evidence.iloc[begin:end]
            arrivals = [e for e in causal if block.index[0] <= e["available_at"] <= block.index[-1]]
            out, emitted = stream.advance(block, arrivals, observed_through=block.index[-1]+pd.Timedelta(hours=1))
            journal_output.append(out)
            journal_events.extend(emitted)
            saved = json.loads(json.dumps(stream.checkpoint(), allow_nan=False))
            stream = FrozenD1Recovery(sensor, cfg, aggregation, saved)
        restored = pd.concat(journal_output)
        checkpoint_mismatch, _ = difference(restored, candidate)
        journal_transitions_equal = fingerprint(journal_events) == fingerprint(candidate_transitions)
        write_json(checkpoint_folder / f"{sensor}.json", stream.checkpoint())
        diff = (candidate.D1_total-original.D1_total).abs()
        common = candidate.D1_total.notna() & original.D1_total.notna()
        row = {"sensor_id": sensor, "n_hours": len(evidence), "native_state_changed_hours": state_mismatch,
            "native_state_max_abs_difference": max_state_difference, "native_D1_max_abs_difference": float(score_delta.max()),
            "native_drift_max_abs_difference": float(drift_delta.max()), "native_veto_changed_hours": veto_mismatch,
            "native_NA_mismatches": int((original.D1_total.isna() != state["D1_v11"][sensor].isna()).sum()),
            "native_transitions_equal": transitions_equal, "native_pelt_events_equal": native_equal,
            "native_event_count": len(native), "scheduled_event_count": len(causal),
            "scheduled_score_changed_hours": int(diff.gt(1e-10).sum()),
            "scheduled_low_tail_flips": int(((candidate.D1_total.lt(3) != original.D1_total.lt(3)) & common).sum()),
            "scheduled_state_changed_hours": int(candidate.state_name.ne(original.state_name).sum()),
            "checkpoint_output_changed_hours": checkpoint_mismatch,
            "checkpoint_transitions_equal": journal_transitions_equal,
            "incomplete_detector_hours": int((~candidate.detector_evidence_complete).sum()),
            "n_transitions": len(transitions), "journal_sha256": stream.checkpoint()["journal_sha256"]}
        rows.append(row)
        selected = pd.DataFrame({"sensor_id": sensor, "D1_native": original.D1_total,
            "D1_scheduled_candidate": candidate.D1_total, "D1_candidate_releasable": candidate.D1_for_validation,
            "native_state": original.state_name, "candidate_state": candidate.state_name,
            "detector_evidence_complete": candidate.detector_evidence_complete}, index=evidence.index)
        score_rows.append(selected.rename_axis("timestamp").reset_index())
        print(sensor, json.dumps(row), flush=True)
    table, prefix = pd.DataFrame(rows), pd.DataFrame(prefix_rows)
    table.to_csv(OUTPUT / "audit/D1_recovery_historical_replay.csv", index=False)
    prefix.to_csv(OUTPUT / "audit/D1_recovery_prefix_audit.csv", index=False)
    pd.concat(score_rows).to_parquet(OUTPUT / "audit/D1_recovery_historical_rows.parquet", index=False)
    write_json(OUTPUT / "assets/D1_frozen_recovery_contract.json", {"source_state_sha256": SOURCE_HASH,
        "cooldown_by_sensor": configs, "aggregation": aggregation,
        "pelt_schedule_candidate": {"policy": "fixed_valid_observation_count_no_endpoint_flush",
            "lookback": 720, "stride": 336, "min_seg": 12, "penalty_factor": 2.5, "max_cps": 20},
        "full_raw_domain_adapter_ready": False})
    qa = {"scope": "frozen_detector_evidence_to_recovery_and_D1_not_raw_domain_end_to_end",
        "n_sensor_hours": int(table.n_hours.sum()), "n_sensors": len(table),
        "native_replay_passed": bool(table.native_state_changed_hours.sum() == 0
            and table.native_veto_changed_hours.sum() == 0 and table.native_NA_mismatches.sum() == 0
            and table.native_D1_max_abs_difference.max() < 1e-10 and table.native_drift_max_abs_difference.max() < 1e-10
            and table.native_transitions_equal.all() and table.native_pelt_events_equal.all()),
        "native_pelt_prefix_passed": bool(prefix.native_candidate_symmetric_difference.sum() == 0),
        "native_prefix_state_changed_hours_summed_across_cuts": int(prefix.native_state_changed_hours.sum()),
        "candidate_prefix_passed": bool(prefix.candidate_event_prefix_equal.all() and prefix.candidate_output_changed_hours.sum() == 0),
        "checkpoint_passed": bool(table.checkpoint_output_changed_hours.sum() == 0 and table.checkpoint_transitions_equal.all()),
        "candidate_historical_score_changed_hours": int(table.scheduled_score_changed_hours.sum()),
        "candidate_historical_low_tail_flips": int(table.scheduled_low_tail_flips.sum()),
        "native_recovery_transition_count": int(table.n_transitions.sum()),
        "heldout_scores_computed": False}
    write_json(OUTPUT / "audit/D1_recovery_replay_qa.json", qa)
    print(json.dumps(qa), flush=True)


if __name__ == "__main__":
    main()
