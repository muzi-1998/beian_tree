from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _extract_events(frame: pd.DataFrame, min_hours: int = 3) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for pair_id, pair in frame.sort_values("timestamp").groupby("pair_id"):
        active = pair["usable_for_D4"].astype(bool) & pair["D4_raw"].lt(3.0)
        groups = active.ne(active.shift(fill_value=False)).cumsum()
        for _, event in pair[active].groupby(groups[active]):
            duration = (
                (event["timestamp"].max() - event["timestamp"].min()).total_seconds() / 3600.0
                + 1.0
            )
            if duration >= min_hours:
                rows.append({
                    "pair_id": pair_id,
                    "start_ts": event["timestamp"].min(),
                    "end_ts": event["timestamp"].max(),
                    "duration_h": duration,
                })
    return pd.DataFrame(rows)


def _event_overlap(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pair_id in sorted(set(left["pair_id"]) | set(right["pair_id"])):
        l_events = left[left["pair_id"].eq(pair_id)]
        r_events = right[right["pair_id"].eq(pair_id)]
        matched_left: set[int] = set()
        matched_right: set[int] = set()
        onset_displacement = []
        for li, l_event in l_events.iterrows():
            candidates = []
            for ri, r_event in r_events.iterrows():
                overlap = min(l_event.end_ts, r_event.end_ts) >= max(l_event.start_ts, r_event.start_ts)
                if overlap:
                    candidates.append((abs((r_event.start_ts - l_event.start_ts).total_seconds()), ri))
            if candidates:
                _, ri = min(candidates)
                matched_left.add(li)
                matched_right.add(ri)
                onset_displacement.append(
                    abs((r_events.loc[ri, "start_ts"] - l_event.start_ts).total_seconds()) / 3600.0
                )
        union = len(l_events) + len(r_events) - min(len(matched_left), len(matched_right))
        rows.append({
            "pair_id": pair_id,
            "legacy_events": len(l_events),
            "current_events": len(r_events),
            "matched_events": min(len(matched_left), len(matched_right)),
            "event_jaccard": min(len(matched_left), len(matched_right)) / union if union else 1.0,
            "median_onset_displacement_h": (
                float(np.median(onset_displacement)) if onset_displacement else np.nan
            ),
        })
    return pd.DataFrame(rows)


def run_method_sensitivity(
    legacy_path: Path,
    current_path: Path,
    output_path: Path,
) -> dict[str, pd.DataFrame]:
    old = pd.read_excel(legacy_path, sheet_name="main_scores")
    new = pd.read_excel(current_path, sheet_name="main_scores")
    for frame in (old, new):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    key = ["timestamp", "pair_id"]
    aligned = old[key + ["D4_raw", "usable_for_D4", "D2_target_veto", "D2_ref_veto"]].merge(
        new[key + ["D4_raw", "usable_for_D4", "D2_target_veto", "D2_ref_veto", "phase_id"]],
        on=key,
        suffixes=("_v14", "_v15"),
        validate="one_to_one",
    )
    aligned["delta_D4_v15_minus_v14"] = aligned["D4_raw_v15"] - aligned["D4_raw_v14"]
    aligned["d2_gate_changed"] = (
        aligned[["D2_target_veto_v14", "D2_ref_veto_v14"]].max(axis=1)
        != aligned[["D2_target_veto_v15", "D2_ref_veto_v15"]].max(axis=1)
    )
    rows = []
    for pair_id, group in aligned.groupby("pair_id"):
        comparable = group["D4_raw_v14"].notna() & group["D4_raw_v15"].notna()
        fixed_d2 = comparable & ~group["d2_gate_changed"]
        rows.append({
            "pair_id": pair_id,
            "n_aligned": len(group),
            "n_both_scored": int(comparable.sum()),
            "spearman_all_scored": group.loc[comparable, ["D4_raw_v14", "D4_raw_v15"]]
            .corr(method="spearman").iloc[0, 1],
            "median_abs_delta_all_scored": group.loc[comparable, "delta_D4_v15_minus_v14"].abs().median(),
            "p95_abs_delta_all_scored": group.loc[comparable, "delta_D4_v15_minus_v14"].abs().quantile(0.95),
            "median_abs_delta_fixed_D2": group.loc[fixed_d2, "delta_D4_v15_minus_v14"].abs().median(),
            "p95_abs_delta_fixed_D2": group.loc[fixed_d2, "delta_D4_v15_minus_v14"].abs().quantile(0.95),
            "d2_gate_changed_rate": group["d2_gate_changed"].mean(),
            "evaluable_rate_v14": group["usable_for_D4_v14"].mean(),
            "evaluable_rate_v15": group["usable_for_D4_v15"].mean(),
        })
    old_events = _extract_events(old)
    new_events = _extract_events(new)
    event_comparison = _event_overlap(old_events, new_events)
    contract = pd.DataFrame([{
        "legacy_version": "d4-v1.4-canonical-d4-20260726",
        "current_version": "d4-v1.5-common-support-frozen-d4-20260813",
        "primary_changes": "common synchronous support; development-only mapping",
        "concurrent_dependency_change": "D2 process-floor release updated between runs",
        "interpretation": (
            "fixed-D2 deltas isolate score-semantics comparison where observable; "
            "evaluable-rate changes are not attributed to common support alone"
        ),
    }])
    outputs = {
        "pair_score_comparison": pd.DataFrame(rows),
        "event_comparison": event_comparison,
        "aligned_scores": aligned,
        "method_contract": contract,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in outputs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return outputs
