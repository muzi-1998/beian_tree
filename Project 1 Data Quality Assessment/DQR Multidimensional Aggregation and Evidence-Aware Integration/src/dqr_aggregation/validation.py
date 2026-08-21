from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, rankdata, spearmanr, wasserstein_distance

from .common import arithmetic, geometric, soft_min


def _spearman(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 3 or np.nanstd(left) == 0 or np.nanstd(right) == 0:
        return np.nan
    return float(spearmanr(left, right).statistic)


def _jaccard(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    return float(np.logical_and(left, right).sum() / union) if union else 1.0


def complete_case_invariance(node: pd.DataFrame, pair: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, frame, full_column, available_column in (
        ("node", node, "Q_node_full", "Q_node_available"),
        ("pair", pair, "Q_pair_full", "Q_pair_available"),
    ):
        valid = frame[full_column].notna()
        difference = (frame.loc[valid, full_column] - frame.loc[valid, available_column]).abs()
        rows.append(
            {
                "scope": scope,
                "n_complete_case": int(valid.sum()),
                "maximum_absolute_difference": float(difference.max()) if len(difference) else np.nan,
                "mean_absolute_difference": float(difference.mean()) if len(difference) else np.nan,
                "mismatch_count_gt_1e-12": int(difference.gt(1e-12).sum()),
                "passed": bool(len(difference) and difference.le(1e-12).all()),
                "contract": "Q_full equals Q_available on identical complete-evidence rows",
            }
        )
    return pd.DataFrame(rows)


def _candidate_metrics(
    values: np.ndarray,
    *,
    scope: str,
    tau: float,
    low_threshold: float,
) -> pd.DataFrame:
    candidates = {
        "arithmetic_equal_weight": arithmetic(values),
        "geometric_equal_weight": geometric(values),
        f"soft_min_tau_{tau:g}": soft_min(values, tau),
        "hard_min": np.nanmin(values, axis=1),
    }
    reference = candidates["arithmetic_equal_weight"]
    reference_low = reference < low_threshold
    rows = []
    for name, score in candidates.items():
        delta = score - reference
        rows.append(
            {
                "scope": scope,
                "aggregator": name,
                "n_complete_case": len(score),
                "mean_score": float(np.mean(score)),
                "median_score": float(np.median(score)),
                "p05_score": float(np.quantile(score, 0.05)),
                "low_tail_rate": float(np.mean(score < low_threshold)),
                "spearman_vs_arithmetic": _spearman(reference, score),
                "low_tail_jaccard_vs_arithmetic": _jaccard(reference_low, score < low_threshold),
                "decision_flip_rate_at_3": float(np.mean(reference_low != (score < low_threshold))),
                "mean_change_vs_arithmetic": float(np.mean(delta)),
                "p90_absolute_change": float(np.quantile(np.abs(delta), 0.90)),
                "maximum_absolute_change": float(np.max(np.abs(delta))),
                "controlled_discrimination_status": "pending_no_unified_frozen_event_truth",
            }
        )
    return pd.DataFrame(rows)


def aggregator_comparison(
    config: dict[str, Any], node: pd.DataFrame, pair: pd.DataFrame
) -> pd.DataFrame:
    tau = float(config["aggregation"]["softmin_tau"])
    threshold = float(config["aggregation"]["low_tail_threshold"])
    node_values = node.loc[
        node["Q_node_full"].notna(), ["D1_total", "D2_total", "D5_report_score"]
    ].to_numpy(float)
    pair_values = pair.loc[
        pair["Q_pair_full"].notna(),
        ["left_Q_node_full", "right_Q_node_full", "D4_raw"],
    ].to_numpy(float)
    return pd.concat(
        [
            _candidate_metrics(node_values, scope="node", tau=tau, low_threshold=threshold),
            _candidate_metrics(pair_values, scope="pair", tau=tau, low_threshold=threshold),
        ],
        ignore_index=True,
    )


def dimension_ablation(
    config: dict[str, Any], node: pd.DataFrame, pair: pd.DataFrame
) -> pd.DataFrame:
    threshold = float(config["aggregation"]["low_tail_threshold"])
    rows: list[dict[str, Any]] = []
    designs = (
        (
            "node",
            node.loc[node["Q_node_full"].notna()],
            "Q_node_full",
            {"D1": "D1_total", "D2": "D2_total", "D5": "D5_report_score"},
        ),
        (
            "pair",
            pair.loc[pair["Q_pair_full"].notna()],
            "Q_pair_full",
            {
                "left_node": "left_Q_node_full",
                "right_node": "right_Q_node_full",
                "D4": "D4_raw",
            },
        ),
    )
    for scope, frame, reference_column, mapping in designs:
        reference = frame[reference_column].to_numpy(float)
        for removed, column in mapping.items():
            kept = [value for key, value in mapping.items() if key != removed]
            variant = frame[kept].mean(axis=1).to_numpy(float)
            delta = variant - reference
            rows.append(
                {
                    "scope": scope,
                    "variant": f"without_{removed}",
                    "removed_component": removed,
                    "n_complete_case": len(frame),
                    "spearman_vs_full": _spearman(reference, variant),
                    "low_tail_jaccard_vs_full": _jaccard(
                        reference < threshold, variant < threshold
                    ),
                    "decision_flip_rate_at_3": float(
                        np.mean((reference < threshold) != (variant < threshold))
                    ),
                    "mean_score_change": float(np.mean(delta)),
                    "p90_absolute_change": float(np.quantile(np.abs(delta), 0.90)),
                }
            )
    return pd.DataFrame(rows)


def _constrained_weights(
    *,
    draws: int,
    concentration: float,
    minimum: float,
    maximum: float,
    rng: np.random.Generator,
) -> np.ndarray:
    accepted: list[np.ndarray] = []
    alpha = np.full(3, concentration / 3.0)
    while sum(len(item) for item in accepted) < draws:
        batch = rng.dirichlet(alpha, size=max(draws, 256))
        batch = batch[(batch.min(axis=1) >= minimum) & (batch.max(axis=1) <= maximum)]
        if len(batch):
            accepted.append(batch)
    return np.vstack(accepted)[:draws]


def weight_sensitivity(
    config: dict[str, Any], node: pd.DataFrame, pair: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    settings = config["statistics"]
    rng = np.random.default_rng(int(settings["weight_seed"]))
    weights = _constrained_weights(
        draws=int(settings["weight_draws"]),
        concentration=float(settings["dirichlet_concentration"]),
        minimum=float(settings["weight_min"]),
        maximum=float(settings["weight_max"]),
        rng=rng,
    )
    threshold = float(config["aggregation"]["low_tail_threshold"])
    rows: list[dict[str, Any]] = []
    designs = (
        (
            "node",
            node.loc[node["Q_node_full"].notna(), ["D1_total", "D2_total", "D5_report_score"]].to_numpy(float),
            ["D1", "D2", "D5"],
        ),
        (
            "pair",
            pair.loc[
                pair["Q_pair_full"].notna(),
                ["left_Q_node_full", "right_Q_node_full", "D4_raw"],
            ].to_numpy(float),
            ["left_node", "right_node", "D4"],
        ),
    )
    for scope, values, labels in designs:
        reference = arithmetic(values)
        reference_low = reference < threshold
        for draw_id, weight in enumerate(weights, 1):
            score = values @ weight
            delta = score - reference
            rows.append(
                {
                    "scope": scope,
                    "draw_id": draw_id,
                    f"weight_{labels[0]}": weight[0],
                    f"weight_{labels[1]}": weight[1],
                    f"weight_{labels[2]}": weight[2],
                    "spearman_vs_equal": _spearman(reference, score),
                    "low_tail_jaccard_vs_equal": _jaccard(reference_low, score < threshold),
                    "decision_flip_rate_at_3": float(
                        np.mean(reference_low != (score < threshold))
                    ),
                    "mean_score_change": float(np.mean(delta)),
                    "p90_absolute_change": float(np.quantile(np.abs(delta), 0.90)),
                    "maximum_absolute_change": float(np.max(np.abs(delta))),
                }
            )
    draws = pd.DataFrame(rows)
    metric_columns = [
        "spearman_vs_equal",
        "low_tail_jaccard_vs_equal",
        "decision_flip_rate_at_3",
        "mean_score_change",
        "p90_absolute_change",
        "maximum_absolute_change",
    ]
    summary_rows = []
    for scope, frame in draws.groupby("scope"):
        for metric in metric_columns:
            summary_rows.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "median": float(frame[metric].median()),
                    "p05": float(frame[metric].quantile(0.05)),
                    "p95": float(frame[metric].quantile(0.95)),
                    "minimum": float(frame[metric].min()),
                    "maximum": float(frame[metric].max()),
                    "n_weight_draws": len(frame),
                }
            )
    return draws, pd.DataFrame(summary_rows)


def _smd(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or len(right) < 2:
        return np.nan
    pooled = np.sqrt((np.var(left, ddof=1) + np.var(right, ddof=1)) / 2.0)
    return float((np.mean(left) - np.mean(right)) / pooled) if pooled > 0 else 0.0


def coverage_shift(node: pd.DataFrame) -> pd.DataFrame:
    source = node.loc[
        node["coverage_class"].isin(["full", "basic"]) & node["Q_node_available"].notna()
    ].copy()
    source["month"] = source["timestamp"].dt.to_period("M").astype(str)
    rows: list[dict[str, Any]] = []
    strata = [
        ("overall", []),
        ("month", ["month"]),
        ("analyte", ["analyte"]),
        ("sensor", ["sensor_id"]),
    ]
    for level, keys in strata:
        groups = [("all", source)] if not keys else source.groupby(keys, dropna=False, observed=True)
        for key, frame in groups:
            full = frame.loc[frame["coverage_class"].eq("full"), "Q_node_available"].to_numpy(float)
            basic = frame.loc[frame["coverage_class"].eq("basic"), "Q_node_available"].to_numpy(float)
            if not len(full) or not len(basic):
                continue
            rows.append(
                {
                    "stratum_type": level,
                    "stratum": key if isinstance(key, str) else "|".join(map(str, key if isinstance(key, tuple) else [key])),
                    "n_full": len(full),
                    "n_basic": len(basic),
                    "mean_full": float(np.mean(full)),
                    "mean_basic": float(np.mean(basic)),
                    "median_full": float(np.median(full)),
                    "median_basic": float(np.median(basic)),
                    "standardized_mean_difference_full_minus_basic": _smd(full, basic),
                    "wasserstein_distance": float(wasserstein_distance(full, basic)),
                    "interpretation": "descriptive_selection_audit_not_causal",
                }
            )
    return pd.DataFrame(rows)


def selection_composition_decomposition(
    config: dict[str, Any], node: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate D5 availability selection from its within-Full score contribution."""
    source = node.loc[
        node["core_evaluable"] & node["coverage_class"].isin(["full", "basic"])
    ].copy()
    source["Q_core_D1_D2"] = source[["D1_total", "D2_total"]].mean(axis=1)
    start = pd.Timestamp(config["study"]["start"])
    end = pd.Timestamp(config["study"]["end"])
    block_hours = int(config["statistics"]["primary_block_hours"])
    repetitions = int(config["statistics"]["bootstrap_repetitions"])
    seed = int(config["statistics"]["bootstrap_seed"]) + 101
    total_hours = int((end - start) / pd.Timedelta(hours=1)) + 1
    n_blocks = int(np.ceil(total_hours / block_hours))
    source["process_time_block"] = (
        (source["timestamp"] - start).dt.total_seconds() // (block_hours * 3600)
    ).astype(int)
    strata: list[tuple[str, str, pd.DataFrame]] = [("overall", "all", source)]
    strata.extend(
        ("analyte", str(key), frame)
        for key, frame in source.groupby("analyte", dropna=False, observed=True)
    )
    summary_rows: list[dict[str, Any]] = []
    draw_rows: list[pd.DataFrame] = []
    for stratum_type, stratum, frame in strata:
        is_full = frame["coverage_class"].eq("full")
        is_basic = frame["coverage_class"].eq("basic")
        if not is_full.any() or not is_basic.any():
            continue
        working = frame.assign(
            core_full=frame["Q_core_D1_D2"].where(is_full),
            core_basic=frame["Q_core_D1_D2"].where(is_basic),
            quality_full=frame["Q_node_full"].where(is_full),
        )
        grouped = (
            working.groupby("process_time_block")
            .agg(
                sum_core_full=("core_full", "sum"),
                n_core_full=("core_full", "count"),
                sum_core_basic=("core_basic", "sum"),
                n_core_basic=("core_basic", "count"),
                sum_quality_full=("quality_full", "sum"),
                n_quality_full=("quality_full", "count"),
            )
            .reindex(range(n_blocks), fill_value=0)
        )
        rng = np.random.default_rng(seed)
        selected = rng.integers(0, n_blocks, size=(repetitions, n_blocks))
        values = grouped.to_numpy(float)[selected].sum(axis=1)
        (
            sum_core_full,
            n_core_full,
            sum_core_basic,
            n_core_basic,
            sum_quality_full,
            n_quality_full,
        ) = values.T
        boot_core_full = np.divide(sum_core_full, n_core_full)
        boot_core_basic = np.divide(sum_core_basic, n_core_basic)
        boot_quality_full = np.divide(sum_quality_full, n_quality_full)
        samples = {
            "selection_only": boot_core_full - boot_core_basic,
            "within_Full_D5_compositional_contribution": boot_quality_full - boot_core_full,
            "total_observed_estimand_shift": boot_quality_full - boot_core_basic,
        }
        core_full = float(frame.loc[is_full, "Q_core_D1_D2"].mean())
        core_basic = float(frame.loc[is_basic, "Q_core_D1_D2"].mean())
        quality_full = float(frame.loc[is_full, "Q_node_full"].mean())
        estimates = {
            "selection_only": core_full - core_basic,
            "within_Full_D5_compositional_contribution": quality_full - core_full,
            "total_observed_estimand_shift": quality_full - core_basic,
        }
        for effect, estimate in estimates.items():
            sample = samples[effect]
            summary_rows.append(
                {
                    "stratum_type": stratum_type,
                    "stratum": stratum,
                    "effect": effect,
                    "estimate": estimate,
                    "ci_low": float(np.nanquantile(sample, 0.025)),
                    "ci_high": float(np.nanquantile(sample, 0.975)),
                    "n_full_sensor_hours": int(is_full.sum()),
                    "n_basic_sensor_hours": int(is_basic.sum()),
                    "independent_process_time_blocks": n_blocks,
                    "bootstrap_repetitions": repetitions,
                    "bootstrap_method": "synchronized_7d_process_time_block_bootstrap",
                    "analysis_unit": "sensor_hour_pooled_estimand_with_process_time_clusters",
                }
            )
            draw_rows.append(
                pd.DataFrame(
                    {
                        "stratum_type": stratum_type,
                        "stratum": stratum,
                        "effect": effect,
                        "draw_id": np.arange(1, repetitions + 1),
                        "estimate": sample,
                    }
                )
            )
    summary = pd.DataFrame(summary_rows)
    draws = pd.concat(draw_rows, ignore_index=True)
    overall = summary.loc[
        summary["stratum_type"].eq("overall") & summary["stratum"].eq("all")
    ].set_index("effect")["estimate"]
    closure = float(
        overall["total_observed_estimand_shift"]
        - overall["selection_only"]
        - overall["within_Full_D5_compositional_contribution"]
    )
    summary["overall_closure_error"] = closure
    summary["interpretation"] = "descriptive_estimand_decomposition_not_causal"
    return summary, draws


def _extract_low_tail_episodes(
    frame: pd.DataFrame,
    score_column: str,
    low_threshold: float,
    model: str,
) -> pd.DataFrame:
    ordered = frame.sort_values(["pair_id", "timestamp"]).copy()
    low = ordered[score_column].lt(low_threshold)
    same_pair = ordered["pair_id"].eq(ordered["pair_id"].shift())
    contiguous = ordered["timestamp"].sub(ordered["timestamp"].shift()).eq(
        pd.Timedelta(hours=1)
    )
    event_start = low & ~(low.shift(fill_value=False) & same_pair & contiguous)
    ordered["_episode_number"] = event_start.groupby(ordered["pair_id"]).cumsum()
    events = (
        ordered.loc[low]
        .groupby(["pair_id", "_episode_number"], observed=True)
        .agg(
            start_timestamp=("timestamp", "min"),
            end_timestamp=("timestamp", "max"),
            duration_h=("timestamp", "size"),
            minimum_score=(score_column, "min"),
            mean_score=(score_column, "mean"),
        )
        .reset_index(drop=False)
    )
    events.insert(0, "model", model)
    events.insert(1, "threshold", float(low_threshold))
    events["episode_id"] = (
        events["model"]
        + "_Qlt"
        + events["threshold"].map(lambda value: f"{value:.2f}")
        + "_"
        + events["pair_id"].astype(str)
        + "_"
        + events["_episode_number"].astype(int).astype(str).str.zfill(4)
    )
    return events.drop(columns="_episode_number")


def _episode_summary(
    events: pd.DataFrame, *, n_pair_hours: int
) -> dict[str, float | int]:
    return {
        "event_count": int(len(events)),
        "events_per_1000_pair_hours": float(len(events) / n_pair_hours * 1000.0),
        "median_episode_duration_h": (
            float(events["duration_h"].median()) if len(events) else np.nan
        ),
    }


def pair_weighting_sensitivity(
    config: dict[str, Any], pair: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare hierarchical component weighting with equal native-atom weighting."""
    source = pair.loc[pair["Q_pair_full"].notna()].copy()
    atoms = [
        "left_D1_total",
        "left_D2_total",
        "left_D5_report_score",
        "right_D1_total",
        "right_D2_total",
        "right_D5_report_score",
        "D4_raw",
    ]
    source["Q_pair_hierarchical"] = source["Q_pair_full"]
    source["Q_pair_native_atom_equal"] = source[atoms].mean(axis=1)
    threshold = float(config["aggregation"]["low_tail_threshold"])
    thresholds = sorted(
        {float(value) for value in config["statistics"]["low_tail_threshold_sweep"]}
        | {threshold}
    )
    hierarchy = source["Q_pair_hierarchical"].to_numpy(float)
    atom = source["Q_pair_native_atom_equal"].to_numpy(float)
    threshold_rows: list[dict[str, Any]] = []
    episode_frames: list[pd.DataFrame] = []
    for candidate in thresholds:
        hierarchy_low = hierarchy < candidate
        atom_low = atom < candidate
        both = hierarchy_low & atom_low
        union = hierarchy_low | atom_low
        hierarchy_events = _extract_low_tail_episodes(
            source, "Q_pair_hierarchical", candidate, "hierarchical"
        )
        atom_events = _extract_low_tail_episodes(
            source, "Q_pair_native_atom_equal", candidate, "native_atom_equal"
        )
        episode_frames.extend([hierarchy_events, atom_events])
        hierarchy_episode_summary = _episode_summary(
            hierarchy_events, n_pair_hours=len(source)
        )
        atom_episode_summary = _episode_summary(atom_events, n_pair_hours=len(source))
        threshold_rows.append(
            {
                "threshold": candidate,
                "n_complete_pair_hours": len(source),
                "hierarchical_low_tail_count": int(hierarchy_low.sum()),
                "native_atom_low_tail_count": int(atom_low.sum()),
                "intersection_both_count": int(both.sum()),
                "union_count": int(union.sum()),
                "hierarchical_only_count": int((hierarchy_low & ~atom_low).sum()),
                "native_atom_only_count": int((atom_low & ~hierarchy_low).sum()),
                "both_count": int(both.sum()),
                "neither_count": int((~hierarchy_low & ~atom_low).sum()),
                "low_tail_jaccard": (
                    _jaccard(hierarchy_low, atom_low) if union.any() else np.nan
                ),
                "jaccard_estimable": bool(union.any()),
                "decision_flip_rate": float(np.mean(hierarchy_low != atom_low)),
                "hierarchical_low_hours_per_1000": float(hierarchy_low.mean() * 1000.0),
                "native_atom_low_hours_per_1000": float(atom_low.mean() * 1000.0),
                "hierarchical_event_count": hierarchy_episode_summary["event_count"],
                "native_atom_event_count": atom_episode_summary["event_count"],
                "hierarchical_events_per_1000": hierarchy_episode_summary[
                    "events_per_1000_pair_hours"
                ],
                "native_atom_events_per_1000": atom_episode_summary[
                    "events_per_1000_pair_hours"
                ],
                "hierarchical_median_episode_duration_h": hierarchy_episode_summary[
                    "median_episode_duration_h"
                ],
                "native_atom_median_episode_duration_h": atom_episode_summary[
                    "median_episode_duration_h"
                ],
                "threshold_role": (
                    "formal_primary" if np.isclose(candidate, threshold) else "sensitivity"
                ),
            }
        )
    threshold_sweep = pd.DataFrame(threshold_rows)
    episodes = pd.concat(episode_frames, ignore_index=True)
    primary = threshold_sweep.loc[np.isclose(threshold_sweep["threshold"], threshold)].iloc[0]
    summary = pd.DataFrame(
        [
            {
                "comparison": "hierarchical_equal_component_vs_native_atom_equal",
                "n_complete_pair_hours": len(source),
                "spearman": _spearman(hierarchy, atom),
                "formal_low_tail_threshold": threshold,
                "low_tail_jaccard": float(primary["low_tail_jaccard"]),
                "decision_flip_rate_at_3": float(primary["decision_flip_rate"]),
                "hierarchical_mean": float(np.mean(hierarchy)),
                "native_atom_mean": float(np.mean(atom)),
                "mean_native_minus_hierarchical": float(np.mean(atom - hierarchy)),
                "p90_absolute_change": float(np.quantile(np.abs(atom - hierarchy), 0.90)),
                "hierarchical_low_tail_count": int(primary["hierarchical_low_tail_count"]),
                "native_atom_low_tail_count": int(primary["native_atom_low_tail_count"]),
                "intersection_both_count": int(primary["intersection_both_count"]),
                "union_count": int(primary["union_count"]),
                "hierarchical_only_count": int(primary["hierarchical_only_count"]),
                "native_atom_only_count": int(primary["native_atom_only_count"]),
                "both_count": int(primary["both_count"]),
                "neither_count": int(primary["neither_count"]),
                "hierarchical_low_hours_per_1000": float(
                    primary["hierarchical_low_hours_per_1000"]
                ),
                "native_atom_low_hours_per_1000": float(
                    primary["native_atom_low_hours_per_1000"]
                ),
                "hierarchical_events_per_1000": float(
                    primary["hierarchical_events_per_1000"]
                ),
                "native_atom_events_per_1000": float(
                    primary["native_atom_events_per_1000"]
                ),
                "hierarchical_event_count": int(primary["hierarchical_event_count"]),
                "native_atom_event_count": int(primary["native_atom_event_count"]),
                "hierarchical_median_episode_duration_h": float(
                    primary["hierarchical_median_episode_duration_h"]
                ),
                "native_atom_median_episode_duration_h": float(
                    primary["native_atom_median_episode_duration_h"]
                ),
                "formal_model_changed": False,
                "interpretation": "supplementary_weighting_sensitivity_not_model_selection",
            }
        ]
    )
    rows = source[
        [
            "timestamp",
            "pair_id",
            "variable",
            "Q_pair_hierarchical",
            "Q_pair_native_atom_equal",
        ]
    ].copy()
    rows["hierarchical_low"] = rows["Q_pair_hierarchical"].lt(threshold)
    rows["native_atom_low"] = rows["Q_pair_native_atom_equal"].lt(threshold)
    rows["absolute_change"] = (
        rows["Q_pair_native_atom_equal"] - rows["Q_pair_hierarchical"]
    ).abs()
    return summary, rows, threshold_sweep, episodes


def _circular_block_bootstrap_mean(
    values: np.ndarray,
    *,
    block_hours: int,
    repetitions: int,
    rng: np.random.Generator,
) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    n = len(array)
    if not n:
        return np.full(repetitions, np.nan)
    block = min(int(block_hours), n)
    n_blocks = int(np.ceil(n / block))
    offsets = np.arange(block)
    output = np.empty(repetitions, dtype=float)
    for start in range(0, repetitions, 100):
        size = min(100, repetitions - start)
        starts = rng.integers(0, n, size=(size, n_blocks))
        indices = ((starts[:, :, None] + offsets) % n).reshape(size, -1)[:, :n]
        output[start : start + size] = np.nanmean(array[indices], axis=1)
    return output


def block_bootstrap_summary(
    config: dict[str, Any], node: pd.DataFrame, pair: pd.DataFrame
) -> pd.DataFrame:
    settings = config["statistics"]
    repetitions = int(settings["bootstrap_repetitions"])
    rng = np.random.default_rng(int(settings["bootstrap_seed"]))
    start = pd.Timestamp(config["study"]["start"])
    end = pd.Timestamp(config["study"]["end"])
    grid = pd.date_range(start, end, freq="1h")
    designs = (
        ("node", "full", node, "Q_node_full"),
        ("node", "core_fixed", node, "Q_node_core12"),
        ("node", "availability_aware", node, "Q_node_available"),
        ("pair", "full", pair, "Q_pair_full"),
        ("pair", "core_fixed", pair, "Q_pair_core"),
        ("pair", "availability_aware", pair, "Q_pair_available"),
    )
    rows = []
    for scope, estimand, frame, column in designs:
        plant_hour = frame.groupby("timestamp")[column].median().reindex(grid)
        for block_hours in map(int, settings["block_hours"]):
            samples = _circular_block_bootstrap_mean(
                plant_hour.to_numpy(float),
                block_hours=block_hours,
                repetitions=repetitions,
                rng=rng,
            )
            independent_blocks = int(np.ceil(len(grid) / block_hours))
            inferential = independent_blocks >= int(settings["inferential_min_blocks"])
            rows.append(
                {
                    "scope": scope,
                    "estimand": estimand,
                    "block_hours": block_hours,
                    "method": "synchronized_circular_process_time_block_bootstrap",
                    "analysis_unit": "plant_hour_joint_across_objects",
                    "estimate": float(np.nanmean(plant_hour)),
                    "ci_low": float(np.nanquantile(samples, 0.025)) if inferential else np.nan,
                    "ci_high": float(np.nanquantile(samples, 0.975)) if inferential else np.nan,
                    "n_calendar_hours": len(grid),
                    "n_evaluable_plant_hours": int(plant_hour.notna().sum()),
                    "independent_blocks": independent_blocks,
                    "inferential_ci_reported": inferential,
                    "repetitions": repetitions,
                }
            )
    return pd.DataFrame(rows)


def _block_correlation_ci(
    frame: pd.DataFrame,
    left: str,
    right: str,
    *,
    block_hours: int,
    repetitions: int,
    seed: int,
    low_threshold: float,
    inferential_min_blocks: int,
) -> dict[str, Any]:
    sample = frame[["timestamp", left, right]].dropna().copy()
    if len(sample) < 3:
        return {
            "n": len(sample),
            "n_blocks": 0,
            "spearman": np.nan,
            "kendall_tau": np.nan,
            "spearman_ci_low": np.nan,
            "spearman_ci_high": np.nan,
            "low_tail_jaccard": np.nan,
            "jaccard_ci_low": np.nan,
            "jaccard_ci_high": np.nan,
            "inferential_ci_reported": False,
        }
    origin = sample["timestamp"].min().floor("1h")
    sample["block_id"] = (
        (sample["timestamp"] - origin).dt.total_seconds() // (block_hours * 3600)
    ).astype(int)
    x = sample[left].to_numpy(float)
    y = sample[right].to_numpy(float)
    sample["rank_x"] = rankdata(x)
    sample["rank_y"] = rankdata(y)
    sample["rank_x2"] = sample["rank_x"] ** 2
    sample["rank_y2"] = sample["rank_y"] ** 2
    sample["rank_xy"] = sample["rank_x"] * sample["rank_y"]
    sample["low_intersection"] = (sample[left] < low_threshold) & (
        sample[right] < low_threshold
    )
    sample["low_union"] = (sample[left] < low_threshold) | (sample[right] < low_threshold)
    grouped = sample.groupby("block_id").agg(
        n=(left, "size"),
        sx=("rank_x", "sum"),
        sy=("rank_y", "sum"),
        sxx=("rank_x2", "sum"),
        syy=("rank_y2", "sum"),
        sxy=("rank_xy", "sum"),
        intersection=("low_intersection", "sum"),
        union=("low_union", "sum"),
    )
    n_blocks = len(grouped)
    inferential = n_blocks >= inferential_min_blocks
    ci_rho = np.full(repetitions, np.nan)
    ci_jaccard = np.full(repetitions, np.nan)
    if inferential:
        values = grouped.to_numpy(float)
        rng = np.random.default_rng(seed)
        selected = rng.integers(0, n_blocks, size=(repetitions, n_blocks))
        sums = values[selected].sum(axis=1)
        n, sx, sy, sxx, syy, sxy, intersection, union = sums.T
        covariance = sxy - sx * sy / n
        variance_x = sxx - sx * sx / n
        variance_y = syy - sy * sy / n
        ci_rho = covariance / np.sqrt(np.maximum(variance_x * variance_y, 1e-15))
        ci_jaccard = np.divide(
            intersection,
            union,
            out=np.ones_like(intersection),
            where=union > 0,
        )
    return {
        "n": len(sample),
        "n_blocks": n_blocks,
        "spearman": _spearman(x, y),
        "kendall_tau": float(kendalltau(x, y).statistic),
        "spearman_ci_low": float(np.nanquantile(ci_rho, 0.025)) if inferential else np.nan,
        "spearman_ci_high": float(np.nanquantile(ci_rho, 0.975)) if inferential else np.nan,
        "low_tail_jaccard": _jaccard(x < low_threshold, y < low_threshold),
        "jaccard_ci_low": float(np.nanquantile(ci_jaccard, 0.025)) if inferential else np.nan,
        "jaccard_ci_high": float(np.nanquantile(ci_jaccard, 0.975)) if inferential else np.nan,
        "inferential_ci_reported": inferential,
    }


def construct_validity(
    config: dict[str, Any], pair: pd.DataFrame
) -> pd.DataFrame:
    frame = pair[["timestamp", "pair_id", "variable", "regime_id", "D4_raw", "I_D4"]].copy()
    for dimension in ("D1", "D2"):
        left = pair[f"left_{dimension}_total"]
        right = pair[f"right_{dimension}_total"]
        frame[dimension] = ((left + right) / 2.0).where(left.notna() & right.notna())
    left_report = pair["left_D5_report_score"]
    right_report = pair["right_D5_report_score"]
    frame["D5_report"] = ((left_report + right_report) / 2.0).where(
        left_report.notna() & right_report.notna()
    )
    left_raw = pair["left_D5_raw"]
    right_raw = pair["right_D5_raw"]
    frame["D5_raw"] = ((left_raw + right_raw) / 2.0).where(
        left_raw.notna() & right_raw.notna()
    )
    frame["D4"] = frame["D4_raw"].where(frame["I_D4"])
    settings = config["statistics"]
    common = {
        "block_hours": int(settings["primary_block_hours"]),
        "repetitions": int(settings["bootstrap_repetitions"]),
        "seed": int(settings["bootstrap_seed"]),
        "low_threshold": float(config["aggregation"]["low_tail_threshold"]),
        "inferential_min_blocks": int(settings["inferential_min_blocks"]),
    }
    rows = []
    for left, right in combinations(["D1", "D2", "D4", "D5_report"], 2):
        stats = _block_correlation_ci(frame, left, right, **common)
        rows.append(
            {
                "scope": "pairwise_complete_formal_scores",
                "left": left,
                "right": right,
                **stats,
            }
        )
    for d5_scope in ("D5_report", "D5_raw"):
        stats = _block_correlation_ci(frame, "D4", d5_scope, **common)
        rows.append(
            {
                "scope": "D4_D5_dual_scope",
                "left": "D4",
                "right": d5_scope,
                **stats,
            }
        )
    output = pd.DataFrame(rows)
    output["bootstrap_method"] = "synchronized_7d_fixed_rank_process_time_block_bootstrap"
    output["interpretation"] = "association_and_overlap_not_causal_independence"
    return output


def pending_validation_registry(config: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "validation_id": "V3-controlled-composite-discrimination",
                "status": "pending_not_executed",
                "reason": "no unified frozen event-truth matrix across native node and pair evidence",
                "blocking_effect": "candidate aggregators remain sensitivity-only",
            },
            {
                "validation_id": "V7-prospective-temporal-holdout",
                "status": config["study"]["future_holdout"]["status"],
                "reason": "2026-04-14 to 2026-07-31 has not been scored by the frozen D1-D5 stack",
                "blocking_effect": "no prospective effectiveness or A-E cutpoint claim",
            },
            {
                "validation_id": "V8-downstream-fitness-for-use",
                "status": "pending_not_executed",
                "reason": "no frozen SUMO, EnKF or prediction endpoint bundle is available in this release",
                "blocking_effect": "no optimized weights or criterion-referenced grades",
            },
            {
                "validation_id": "D1-release-hard-fault-interface",
                "status": "pending_interface",
                "reason": "D1 release exports score and legacy score>=3 tag, not a distinct validated hard-fault field",
                "blocking_effect": "Strict eligibility is a contract candidate, not an automated final release",
            },
            {
                "validation_id": "measurement-assurance",
                "status": "not_available_not_scored",
                "reason": "maintenance and metrological records are not available",
                "blocking_effect": "excluded rather than assigned a neutral or low value",
            },
            {
                "validation_id": "D1-development-only-regime-context-shadow",
                "status": "pending_preregistered_shadow",
                "reason": "the downstream K=4 context is retrospective and requires a development-only frozen comparison",
                "blocking_effect": "no independent-validation claim is made for the retrospective context",
            },
            {
                "validation_id": "D4-development-only-regime-shadow",
                "status": "pending_after_D1_shadow",
                "reason": "D4 sensitivity requires the frozen D1 context artifact before a paired shadow rerun",
                "blocking_effect": "current D4 remains retrospective with explicit context-hindsight limitation",
            },
            {
                "validation_id": "D5-prospective-template-lifecycle",
                "status": "pending_future_support_and_bridge",
                "reason": "candidate maturity requires new independent support, frozen validation and a dual-score bridge",
                "blocking_effect": "historical L1 is not backfilled and no new template version is activated",
            },
        ]
    )
