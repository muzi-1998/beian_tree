from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DO_COMPARATORS = ("PAIR_DO11", "PAIR_DO12", "PAIR_DO13")
PRIMARY_BLOCK_HOURS = 7 * 24


def _event_runs(
    score: np.ndarray,
    evaluable: np.ndarray,
    *,
    threshold: float = 3.0,
    min_hours: int = 3,
    break_before: np.ndarray | None = None,
) -> list[dict[str, float]]:
    values = np.asarray(score, dtype=float)
    valid = np.asarray(evaluable, dtype=bool) & np.isfinite(values)
    active = valid & (values < threshold)
    boundaries = (
        np.zeros(len(values), dtype=bool)
        if break_before is None
        else np.asarray(break_before, dtype=bool)
    )
    if boundaries.shape != active.shape:
        raise ValueError("break_before must have the same shape as score")
    segment_starts = np.flatnonzero(boundaries)
    segment_starts = np.unique(np.r_[0, segment_starts])
    segment_stops = np.r_[segment_starts[1:], len(values)]
    events: list[dict[str, float]] = []
    for segment_start, segment_stop in zip(segment_starts, segment_stops):
        local_active = active[segment_start:segment_stop]
        transitions = np.flatnonzero(
            np.diff(np.r_[False, local_active, False].astype(int))
        )
        for local_start, local_stop in transitions.reshape(-1, 2):
            start = int(segment_start + local_start)
            stop = int(segment_start + local_stop)
            duration = stop - start
            if duration < min_hours:
                continue
            segment = values[start:stop]
            events.append({
                "start_index": float(start),
                "end_index": float(stop - 1),
                "duration_h": float(duration),
                "min_D4_raw": float(np.nanmin(segment)),
                "mean_D4_raw": float(np.nanmean(segment)),
                "area_below_3": float(np.nansum(threshold - segment)),
            })
    return events


def _summary(
    score: np.ndarray,
    evaluable: np.ndarray,
    *,
    break_before: np.ndarray | None = None,
) -> dict[str, float]:
    events = _event_runs(score, evaluable, break_before=break_before)
    durations = np.asarray([event["duration_h"] for event in events], dtype=float)
    valid = np.asarray(evaluable, dtype=bool) & np.isfinite(score)
    active_hours = float(sum(event["duration_h"] for event in events))
    n_valid = int(valid.sum())
    return {
        "n_evaluable_hours": n_valid,
        "n_events": len(events),
        "event_rate_per_1000_h": 1000.0 * len(events) / n_valid if n_valid else np.nan,
        "time_burden": active_hours / n_valid if n_valid else np.nan,
        "median_duration_h": float(np.median(durations)) if durations.size else np.nan,
        "iqr_duration_h": (
            float(np.quantile(durations, 0.75) - np.quantile(durations, 0.25))
            if durations.size else np.nan
        ),
        "p90_duration_h": float(np.quantile(durations, 0.90)) if durations.size else np.nan,
        "p95_duration_h": float(np.quantile(durations, 0.95)) if durations.size else np.nan,
        "max_duration_h": float(np.max(durations)) if durations.size else np.nan,
        "restricted_mean_duration_168h": (
            float(np.mean(np.minimum(durations, 168.0))) if durations.size else np.nan
        ),
        "deficit_area_per_1000_h": (
            1000.0 * sum(event["area_below_3"] for event in events) / n_valid
            if n_valid else np.nan
        ),
    }


def _circular_block_indices(
    n: int,
    block_hours: int,
    rng: np.random.Generator,
) -> np.ndarray:
    blocks = int(np.ceil(n / block_hours))
    starts = rng.integers(0, n, size=blocks)
    offsets = np.arange(block_hours)
    return np.concatenate([(start + offsets) % n for start in starts])[:n]


def _resample_boundaries(indices: np.ndarray, block_hours: int) -> np.ndarray:
    """Mark joins that cannot represent continuous observed-time episodes."""
    sampled = np.asarray(indices, dtype=int)
    boundaries = np.zeros(len(sampled), dtype=bool)
    boundaries[np.arange(block_hours, len(sampled), block_hours)] = True
    if len(sampled) > 1:
        # A circular block that wraps from the study end to its beginning must
        # also be split because those observations were never adjacent in time.
        boundaries[1:] |= sampled[1:] < sampled[:-1]
    return boundaries


def _contrast(pair_stats: dict[str, dict[str, float]]) -> dict[str, float]:
    target = pair_stats["PAIR_DO14"]
    comparators = [pair_stats[pair] for pair in DO_COMPARATORS]
    comparator_median = float(np.nanmedian([item["median_duration_h"] for item in comparators]))
    comparator_event_rate = float(np.nanmean([item["event_rate_per_1000_h"] for item in comparators]))
    comparator_burden = float(np.nanmean([item["time_burden"] for item in comparators]))
    return {
        "delta_median_duration_h": target["median_duration_h"] - comparator_median,
        "median_duration_ratio": target["median_duration_h"] / comparator_median,
        "delta_event_rate_per_1000_h": target["event_rate_per_1000_h"] - comparator_event_rate,
        "delta_time_burden": target["time_burden"] - comparator_burden,
        "delta_restricted_mean_duration_168h": target["restricted_mean_duration_168h"]
        - float(np.nanmean([item["restricted_mean_duration_168h"] for item in comparators])),
    }


def run_episode_validation(
    main: pd.DataFrame,
    output_path: Path,
    *,
    repetitions: int = 600,
) -> dict[str, pd.DataFrame]:
    frame = main.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    timestamps = pd.DatetimeIndex(sorted(frame["timestamp"].unique()))
    pair_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    pair_rows = []
    event_rows = []
    for pair_id, group in frame.groupby("pair_id", sort=False):
        indexed = group.set_index("timestamp").reindex(timestamps)
        score = indexed["D4_raw"].to_numpy(dtype=float)
        evaluable = indexed["usable_for_D4"].fillna(False).to_numpy(dtype=bool)
        pair_arrays[pair_id] = (score, evaluable)
        pair_rows.append({"pair_id": pair_id, **_summary(score, evaluable)})
        for event_number, event in enumerate(_event_runs(score, evaluable), 1):
            start = int(event.pop("start_index"))
            end = int(event.pop("end_index"))
            event_rows.append({
                "pair_id": pair_id,
                "event_number": event_number,
                "start_ts": timestamps[start],
                "end_ts": timestamps[end],
                **event,
            })

    point_stats = {row["pair_id"]: row for row in pair_rows}
    point_contrast = _contrast(point_stats)
    rng = np.random.Generator(np.random.PCG64(20260813))
    sensitivity_rows = []
    primary_draws: list[dict[str, float]] = []
    pair_bootstrap_rows: list[dict[str, float | int | str]] = []
    for block_hours in (48, PRIMARY_BLOCK_HOURS, 14 * 24):
        draws = {metric: np.empty(repetitions) for metric in point_contrast}
        for repetition in range(repetitions):
            sampled = _circular_block_indices(len(timestamps), block_hours, rng)
            break_before = _resample_boundaries(sampled, block_hours)
            sampled_stats = {
                pair_id: _summary(
                    score[sampled], evaluable[sampled], break_before=break_before
                )
                for pair_id, (score, evaluable) in pair_arrays.items()
            }
            contrast = _contrast(sampled_stats)
            for metric, value in contrast.items():
                draws[metric][repetition] = value
            if block_hours == PRIMARY_BLOCK_HOURS:
                primary_draws.append({"repetition": repetition, **contrast})
                for pair_id, statistics in sampled_stats.items():
                    pair_bootstrap_rows.append({
                        "repetition": repetition,
                        "pair_id": pair_id,
                        "median_duration_h": statistics["median_duration_h"],
                        "event_rate_per_1000_h": statistics["event_rate_per_1000_h"],
                        "time_burden": statistics["time_burden"],
                    })
        for metric, values in draws.items():
            low, high = np.nanquantile(values, [0.025, 0.975])
            sensitivity_rows.append({
                "contrast": "DO14_vs_median_or_mean_DO11_DO12_DO13",
                "metric": metric,
                "point_estimate": point_contrast[metric],
                "CI_low": float(low),
                "CI_high": float(high),
                "block_hours": block_hours,
                "bootstrap_repetitions": repetitions,
                "bootstrap_unit": (
                    "synchronous_circular_moving_time_block_with_explicit_"
                    "join_and_wrap_event_breaks"
                ),
            })

    contract = pd.DataFrame([{
        "primary_block_hours": PRIMARY_BLOCK_HOURS,
        "sensitivity_block_hours": "48;336",
        "event_threshold": "D4_raw<3",
        "minimum_duration_hours": 3,
        "independent_unit": "synchronous time block across homologous pairs",
        "block_boundary_contract": (
            "events are re-extracted within continuous sampled segments; joins "
            "between sampled blocks and circular study-end wraps cannot merge"
        ),
        "inference_scope": "retrospective episode-duration confirmation; no sensor causality",
    }])
    outputs = {
        "pair_summary": pd.DataFrame(pair_rows),
        "event_detail": pd.DataFrame(event_rows),
        "do14_contrasts": pd.DataFrame(sensitivity_rows),
        "primary_bootstrap": pd.DataFrame(primary_draws),
        "pair_bootstrap": pd.DataFrame(pair_bootstrap_rows),
        "method_contract": contract,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, output in outputs.items():
            output.to_excel(writer, sheet_name=name, index=False)
    return outputs
