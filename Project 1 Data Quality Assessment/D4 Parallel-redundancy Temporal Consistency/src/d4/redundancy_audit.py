from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


BLOCK_DAYS = 7
PAIR_ORDER = (
    "PAIR_DO11", "PAIR_DO12", "PAIR_DO13", "PAIR_DO14",
    "PAIR_ORP11", "PAIR_ORP12", "PAIR_ORP13",
)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else np.nan


def _jaccard(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    return _safe_ratio(np.logical_and(left, right).sum(), union)


def _phi(left: np.ndarray, right: np.ndarray) -> float:
    if np.unique(left).size < 2 or np.unique(right).size < 2:
        return np.nan
    return float(np.corrcoef(left.astype(float), right.astype(float))[0, 1])


def _score_statistics(frame: pd.DataFrame) -> dict[str, float | int]:
    d1 = frame["D1_pair_min"].to_numpy(dtype=float)
    d4 = frame["D4_raw"].to_numpy(dtype=float)
    d1_low = d1 < 3.0
    d4_low = d4 < 3.0
    joint = d1_low & d4_low
    p_d1 = float(d1_low.mean())
    p_d4 = float(d4_low.mean())
    p_joint = float(joint.mean())
    expected = p_d1 * p_d4
    return {
        "n_pair_hours": len(frame),
        "spearman_D1min_D4": float(spearmanr(d1, d4).statistic),
        "D1_low_rate": p_d1,
        "D4_low_rate": p_d4,
        "joint_low_rate": p_joint,
        "expected_joint_under_independence": expected,
        "joint_excess_probability": p_joint - expected,
        "joint_lift": _safe_ratio(p_joint, expected),
        "low_hour_jaccard": _jaccard(d1_low, d4_low),
        "low_hour_phi": _phi(d1_low, d4_low),
        "P_D4low_given_D1low": _safe_ratio(joint.sum(), d1_low.sum()),
        "P_D1low_given_D4low": _safe_ratio(joint.sum(), d4_low.sum()),
    }


def _block_ids(timestamps: pd.Series, block_days: int = BLOCK_DAYS) -> pd.Series:
    values = pd.to_datetime(timestamps)
    anchor = values.min().floor("D")
    return ((values.dt.floor("D") - anchor).dt.days // block_days).astype(int)


def _bootstrap_score_statistics(
    frame: pd.DataFrame,
    *,
    repetitions: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    source = frame.copy()
    source["_block"] = _block_ids(source["timestamp"])
    blocks = [group for _, group in source.groupby("_block", sort=True)]
    metrics = [
        "spearman_D1min_D4", "joint_excess_probability", "joint_lift",
        "low_hour_jaccard", "low_hour_phi", "P_D4low_given_D1low",
        "P_D1low_given_D4low",
    ]
    rows = []
    for repetition in range(repetitions):
        sampled = rng.integers(0, len(blocks), len(blocks))
        draw = pd.concat([blocks[index] for index in sampled], ignore_index=True)
        stats = _score_statistics(draw)
        rows.append({
            "repetition": repetition,
            "n_process_time_blocks": len(blocks),
            **{metric: stats[metric] for metric in metrics},
        })
    return pd.DataFrame(rows)


def _mark_event_hours(
    timestamps: pd.Series,
    events: pd.DataFrame,
    start_column: str,
    end_column: str,
) -> np.ndarray:
    time = pd.to_datetime(timestamps)
    mask = np.zeros(len(time), dtype=bool)
    for event in events.itertuples(index=False):
        start = pd.Timestamp(getattr(event, start_column))
        end = pd.Timestamp(getattr(event, end_column))
        mask |= time.between(start, end).to_numpy()
    return mask


def _event_overlap(
    main: pd.DataFrame,
    d1_events: pd.DataFrame,
    d4_events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    event_rows = []
    for pair_id in PAIR_ORDER:
        pair = main[main["pair_id"].eq(pair_id)].sort_values("timestamp").copy()
        if pair.empty:
            continue
        target = str(pair["sensor_id"].iloc[0])
        reference = str(pair["pair_sensor_id"].iloc[0])
        d1_pair_events = d1_events[d1_events["sensor_id"].isin([target, reference])].copy()
        d4_pair_events = d4_events[d4_events["pair_id"].eq(pair_id)].copy()
        d1_mask = _mark_event_hours(pair["timestamp"], d1_pair_events, "start", "end")
        d4_mask = _mark_event_hours(pair["timestamp"], d4_pair_events, "start_ts", "end_ts")
        joint = d1_mask & d4_mask
        rows.append({
            "pair_id": pair_id,
            "n_pair_hours": len(pair),
            "D1_event_hours": int(d1_mask.sum()),
            "D4_event_hours": int(d4_mask.sum()),
            "overlap_event_hours": int(joint.sum()),
            "event_hour_jaccard": _jaccard(d1_mask, d4_mask),
            "P_D4event_given_D1event": _safe_ratio(joint.sum(), d1_mask.sum()),
            "P_D1event_given_D4event": _safe_ratio(joint.sum(), d4_mask.sum()),
        })
        d4_matched = 0
        for event in d4_pair_events.itertuples(index=False):
            overlap = (
                (d1_pair_events["start"] <= pd.Timestamp(event.end_ts))
                & (d1_pair_events["end"] >= pd.Timestamp(event.start_ts))
            )
            d4_matched += int(overlap.any())
        d1_matched = 0
        for event in d1_pair_events.itertuples(index=False):
            overlap = (
                (d4_pair_events["start_ts"] <= pd.Timestamp(event.end))
                & (d4_pair_events["end_ts"] >= pd.Timestamp(event.start))
            )
            d1_matched += int(overlap.any())
        event_rows.append({
            "pair_id": pair_id,
            "n_D1_events": len(d1_pair_events),
            "n_D4_events": len(d4_pair_events),
            "D1_events_with_any_D4_overlap": d1_matched,
            "D4_events_with_any_D1_overlap": d4_matched,
            "D1_event_match_rate": _safe_ratio(d1_matched, len(d1_pair_events)),
            "D4_event_match_rate": _safe_ratio(d4_matched, len(d4_pair_events)),
            "matching_contract": "any temporal overlap; descriptive many-to-many matching",
        })
    return pd.DataFrame(rows), pd.DataFrame(event_rows)


def _composite_ablation(
    node: pd.DataFrame,
    pair: pd.DataFrame,
    *,
    repetitions: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    node_values = node[
        ["timestamp", "sensor_id", "D2_total", "D5_report_score", "evaluable_D5"]
    ].copy()
    node_values["Q_node_without_D1"] = node_values[
        ["D2_total", "D5_report_score"]
    ].mean(axis=1).where(
        node_values["D2_total"].notna()
        & node_values["D5_report_score"].notna()
        & node_values["evaluable_D5"].fillna(False)
    )
    target = node_values[["timestamp", "sensor_id", "Q_node_without_D1"]].rename(
        columns={"sensor_id": "sensor_id", "Q_node_without_D1": "target_without_D1"}
    )
    reference = node_values[["timestamp", "sensor_id", "Q_node_without_D1"]].rename(
        columns={"sensor_id": "pair_sensor_id", "Q_node_without_D1": "reference_without_D1"}
    )
    audit = pair.merge(target, on=["timestamp", "sensor_id"], how="left").merge(
        reference, on=["timestamp", "pair_sensor_id"], how="left"
    )
    audit["Q_pair_without_D4"] = audit[["Q_node_target", "Q_node_reference"]].mean(axis=1)
    audit["Q_pair_without_D1"] = audit[
        ["target_without_D1", "reference_without_D1", "D4_raw"]
    ].mean(axis=1)
    audit = audit[
        audit["Q_pair"].notna()
        & audit["Q_pair_without_D4"].notna()
        & audit["Q_pair_without_D1"].notna()
    ].copy()
    variants = {"without_D1": "Q_pair_without_D1", "without_D4": "Q_pair_without_D4"}
    summary_rows = []
    bootstrap_rows = []
    audit["_block"] = _block_ids(audit["timestamp"])
    blocks = [group for _, group in audit.groupby("_block", sort=True)]
    for variant, column in variants.items():
        delta = audit[column] - audit["Q_pair"]
        full_low = audit["Q_pair"] < 3.0
        variant_low = audit[column] < 3.0
        point = {
            "variant": variant,
            "n_pair_hours": len(audit),
            "spearman_vs_full": float(spearmanr(audit["Q_pair"], audit[column]).statistic),
            "mean_score_change": float(delta.mean()),
            "median_score_change": float(delta.median()),
            "p90_absolute_change": float(delta.abs().quantile(0.90)),
            "low_hour_jaccard_vs_full": _jaccard(full_low.to_numpy(), variant_low.to_numpy()),
            "full_low_rate": float(full_low.mean()),
            "variant_low_rate": float(variant_low.mean()),
            "n_process_time_blocks": len(blocks),
        }
        draws = []
        for repetition in range(repetitions):
            sampled = rng.integers(0, len(blocks), len(blocks))
            draw = pd.concat([blocks[index] for index in sampled], ignore_index=True)
            draw_delta = draw[column] - draw["Q_pair"]
            draw_full_low = draw["Q_pair"] < 3.0
            draw_variant_low = draw[column] < 3.0
            row = {
                "repetition": repetition,
                "variant": variant,
                "mean_score_change": float(draw_delta.mean()),
                "spearman_vs_full": float(spearmanr(draw["Q_pair"], draw[column]).statistic),
                "low_hour_jaccard_vs_full": _jaccard(
                    draw_full_low.to_numpy(), draw_variant_low.to_numpy()
                ),
            }
            draws.append(row)
            bootstrap_rows.append(row)
        draw_frame = pd.DataFrame(draws)
        for metric in ("mean_score_change", "spearman_vs_full", "low_hour_jaccard_vs_full"):
            low, high = draw_frame[metric].quantile([0.025, 0.975])
            point[f"{metric}_CI_low"] = float(low)
            point[f"{metric}_CI_high"] = float(high)
        summary_rows.append(point)
    detail_columns = [
        "timestamp", "pair_id", "Q_pair", "Q_pair_without_D1", "Q_pair_without_D4",
        "D4_raw", "D1_target", "D1_ref", "pair_coverage_class",
    ]
    return pd.DataFrame(summary_rows), pd.DataFrame(bootstrap_rows), audit[detail_columns]


def run_redundancy_audit(
    main_path: Path,
    d1_event_path: Path,
    d4_event_path: Path,
    composite_dir: Path,
    output_path: Path,
    *,
    repetitions: int = 600,
) -> dict[str, pd.DataFrame]:
    main = pd.read_excel(main_path, sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    main = main[
        main["usable_for_D4"]
        & main["D1_target"].notna()
        & main["D1_ref"].notna()
    ].copy()
    main["D1_pair_min"] = main[["D1_target", "D1_ref"]].min(axis=1)
    d1_events = pd.read_excel(d1_event_path, sheet_name="all_events")
    d1_events[["start", "end"]] = d1_events[["start", "end"]].apply(pd.to_datetime)
    d4_events = pd.read_excel(d4_event_path, sheet_name="events")
    d4_events[["start_ts", "end_ts"]] = d4_events[["start_ts", "end_ts"]].apply(pd.to_datetime)
    rng = np.random.Generator(np.random.PCG64(20260813))

    score_rows = []
    bootstrap_rows = []
    scopes = [("pooled", main), *[(pair, main[main["pair_id"].eq(pair)]) for pair in PAIR_ORDER]]
    for scope, frame in scopes:
        point = _score_statistics(frame)
        draws = _bootstrap_score_statistics(frame, repetitions=repetitions, rng=rng)
        score_rows.append({
            "scope": scope,
            **point,
            **{
                f"{metric}_CI_low": float(draws[metric].quantile(0.025))
                for metric in draws.columns if metric not in {"repetition", "n_process_time_blocks"}
            },
            **{
                f"{metric}_CI_high": float(draws[metric].quantile(0.975))
                for metric in draws.columns if metric not in {"repetition", "n_process_time_blocks"}
            },
            "n_process_time_blocks": int(draws["n_process_time_blocks"].iloc[0]),
            "bootstrap_unit": "synchronized_7d_process_time_block_all_pairs_within_scope",
        })
        draws.insert(0, "scope", scope)
        bootstrap_rows.append(draws)

    event_hour, event_match = _event_overlap(main, d1_events, d4_events)
    node = pd.read_parquet(composite_dir / "WWDQS_node_scores.parquet")
    pair = pd.read_parquet(composite_dir / "WWDQS_pair_scores.parquet")
    composite_summary, composite_bootstrap, composite_detail = _composite_ablation(
        node, pair, repetitions=repetitions, rng=rng
    )
    contract = pd.DataFrame([{
        "D1_pair_definition": "minimum of the two homologous sensor D1 scores",
        "D4_definition": "independent pair-level D4_raw",
        "score_low_threshold": "<3",
        "event_overlap_contract": "formal event-hour overlap plus descriptive any-overlap event matching",
        "bootstrap_unit": "synchronized 7 d process-time block retaining all pairs",
        "incremental_validity_status": "pending_independent_downstream_criterion",
        "claim_boundary": (
            "association and composite sensitivity do not establish conditional "
            "incremental predictive validity"
        ),
    }])
    outputs = {
        "score_dependence": pd.DataFrame(score_rows),
        "score_block_bootstrap": pd.concat(bootstrap_rows, ignore_index=True),
        "event_hour_overlap": event_hour,
        "event_level_matching": event_match,
        "composite_ablation": composite_summary,
        "composite_block_bootstrap": composite_bootstrap,
        "composite_detail": composite_detail,
        "method_contract": contract,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in outputs.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    return outputs
