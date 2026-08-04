"""Confirmatory scientific validation for the frozen D2 V3 release."""
from __future__ import annotations

import copy
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wasserstein_distance


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUTPUT = ROOT / "artifacts" / "validation"
OUTPUT.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.d2_availability.scorer import (  # noqa: E402
    D2Aggregator,
    GapSeverityScorer,
    TemporalIntegrityScorer,
)
from src.utils.config_loader import load_config  # noqa: E402


WEIGHT_SETS = {
    "equal": {"Q_TI": 1 / 3, "Q_GS": 1 / 3, "Q_FA": 1 / 3},
    "primary_qfa_040": {"Q_TI": 0.30, "Q_GS": 0.30, "Q_FA": 0.40},
    "qfa_enhanced_050": {"Q_TI": 0.25, "Q_GS": 0.25, "Q_FA": 0.50},
}
LAMBDAS = (0.50, 0.70, 0.90)
PRIMARY_ID = "primary_qfa_040__lambda_070"
METRICS = ("Q_TI", "Q_GS", "Q_FA", "D2_total")
EVENT_COLUMNS = ("event_id", "sensor_id", "start", "end", "duration_hours")
PAIR_COLUMNS = (
    "sensor_id", "reference_event_id", "candidate_event_id",
    "reference_start", "candidate_start", "overlap_hours", "separation_hours",
)


def _phase(index: pd.DatetimeIndex, cfg) -> pd.Series:
    result = pd.Series("outside_contract", index=index, dtype=object)
    for name, period in cfg.study_design.periods.items():
        result.loc[pd.Timestamp(period.start):pd.Timestamp(period.end)] = name
    return result


def _long_state(state: dict, cfg) -> pd.DataFrame:
    frames = []
    for sensor_id, frame in state["all_D2"].items():
        selected = frame.copy()
        selected.insert(0, "sensor_id", sensor_id)
        selected.insert(0, "timestamp", selected.index)
        subs = state["subs_all"][sensor_id]
        for column in (
            "missing_rate", "L_max_min", "P95_gap_min", "gap_run_count",
            "true_irregular_rate", "duplicate_rate", "out_of_order_rate",
            "source_gap_recovery_rate", "value_gap_recovery_rate",
            "Q_TI_observed_weight", "Q_miss_comp", "Q_true_irregular_comp",
            "Q_duplicate_comp", "Q_out_of_order_comp",
            "info_empty_cov", "sensor_freeze_cov", "low_iqr_cov",
            "soft_rle_cov", "soft_stasis_cov", "floor_occupancy",
            "resolution_limited", "rl_rate",
        ):
            selected[column] = subs.get(column, pd.Series(0.0, index=selected.index))
        selected["phase"] = _phase(selected.index, cfg).to_numpy()
        selected["analyte"] = sensor_id.split("_")[0]
        frames.append(selected.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True)


def _rescore(state: dict, cfg, weights: dict, lam: float) -> pd.DataFrame:
    variant = copy.deepcopy(cfg)
    variant.mapping.aggregation["weights"] = dict(weights)
    variant.mapping.aggregation["lambda_blend"] = float(lam)
    aggregator = D2Aggregator(variant, state["calib"])
    frames = []
    for sensor_id in state["scored_channels"]:
        subs = state["subs_all"][sensor_id]
        scored = aggregator.aggregate(
            subs["Q_TI"], subs["Q_GS"], subs["Q_FA"], subs
        )
        frame = scored[["D2_total", "veto_flag", "veto_reason"]].copy()
        frame.insert(0, "sensor_id", sensor_id)
        frame.insert(0, "timestamp", frame.index)
        frames.append(frame.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True)


def _extract_events(frame: pd.DataFrame, score_column: str) -> pd.DataFrame:
    rows = []
    for sensor_id, group in frame.groupby("sensor_id", sort=True):
        group = group.sort_values("timestamp")
        flag = group[score_column].lt(3.0).to_numpy()
        times = pd.DatetimeIndex(group["timestamp"])
        starts = np.flatnonzero(flag & ~np.r_[False, flag[:-1]])
        ends = np.flatnonzero(flag & ~np.r_[flag[1:], False])
        for event_no, (start_i, end_i) in enumerate(zip(starts, ends), start=1):
            rows.append({
                "event_id": f"{sensor_id}-L{event_no:04d}",
                "sensor_id": sensor_id,
                "start": times[start_i],
                "end": times[end_i] + pd.Timedelta(hours=1),
                "duration_hours": end_i - start_i + 1,
            })
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def _match_events(reference: pd.DataFrame, candidate: pd.DataFrame, tolerance="1h") -> pd.DataFrame:
    tolerance = pd.Timedelta(tolerance)
    pairs = []
    for sensor_id in sorted(set(reference.get("sensor_id", [])) | set(candidate.get("sensor_id", []))):
        ref = reference.loc[reference["sensor_id"].eq(sensor_id)].copy()
        alt = candidate.loc[candidate["sensor_id"].eq(sensor_id)].copy()
        possibilities = []
        for ri, r in ref.iterrows():
            for ai, a in alt.iterrows():
                overlap = min(r["end"], a["end"]) - max(r["start"], a["start"])
                separation = max(r["start"] - a["end"], a["start"] - r["end"], pd.Timedelta(0))
                if overlap > pd.Timedelta(0) or separation <= tolerance:
                    possibilities.append((max(overlap.total_seconds(), 0.0), -separation.total_seconds(), ri, ai))
        used_ref, used_alt = set(), set()
        for overlap_s, neg_sep_s, ri, ai in sorted(possibilities, reverse=True):
            if ri in used_ref or ai in used_alt:
                continue
            used_ref.add(ri)
            used_alt.add(ai)
            pairs.append({
                "sensor_id": sensor_id,
                "reference_event_id": ref.loc[ri, "event_id"],
                "candidate_event_id": alt.loc[ai, "event_id"],
                "reference_start": ref.loc[ri, "start"],
                "candidate_start": alt.loc[ai, "start"],
                "overlap_hours": overlap_s / 3600,
                "separation_hours": -neg_sep_s / 3600,
            })
    return pd.DataFrame(pairs, columns=PAIR_COLUMNS)


def _event_jaccard(reference: pd.DataFrame, candidate: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    pairs = _match_events(reference, candidate)
    matched = len(pairs)
    denominator = len(reference) + len(candidate) - matched
    return (matched / denominator if denominator else 1.0), pairs


def _percentile_ci(values: list[float]) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return np.nan, np.nan
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def _spearman_stat(reference: pd.Series, candidate: pd.Series) -> float:
    if reference.nunique(dropna=True) < 2 or candidate.nunique(dropna=True) < 2:
        return np.nan
    return float(spearmanr(reference, candidate).statistic)


def _bootstrap_rank(monthly: pd.DataFrame, rng, repeats: int) -> tuple[float, float, int]:
    months = monthly["month"].unique()
    values = []
    for _ in range(repeats):
        sampled = rng.choice(months, size=len(months), replace=True)
        pieces = [monthly.loc[monthly["month"].eq(month)] for month in sampled]
        boot = pd.concat(pieces).groupby("sensor_id")[["reference", "candidate"]].mean()
        values.append(_spearman_stat(boot["reference"], boot["candidate"]))
    low, high = _percentile_ci(values)
    return low, high, int(np.isfinite(values).sum())


def _bootstrap_binary(clustered: pd.DataFrame, rng, repeats: int) -> tuple[float, float]:
    values = []
    array = clustered[["intersection", "union"]].to_numpy(dtype=float)
    for _ in range(repeats):
        sampled = array[rng.integers(0, len(array), size=len(array))]
        denominator = sampled[:, 1].sum()
        values.append(sampled[:, 0].sum() / denominator if denominator else 1.0)
    return _percentile_ci(values)


def _bootstrap_event_jaccard(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    pairs: pd.DataFrame,
    rng,
    repeats: int,
) -> tuple[float, float]:
    """Resample sensor-month event clusters rather than treating events as iid."""
    ref = reference.assign(cluster=(
        reference["sensor_id"].astype(str) + "|" +
        reference["start"].dt.to_period("M").astype(str)
    ))
    alt = candidate.assign(cluster=(
        candidate["sensor_id"].astype(str) + "|" +
        candidate["start"].dt.to_period("M").astype(str)
    ))
    matched = pairs.assign(cluster=(
        pairs["sensor_id"].astype(str) + "|" +
        pairs["reference_start"].dt.to_period("M").astype(str)
    )) if len(pairs) else pairs.assign(cluster=pd.Series(dtype=str))
    clusters = sorted(set(ref["cluster"]) | set(alt["cluster"]))
    if not clusters:
        return 1.0, 1.0
    counts = pd.DataFrame(index=clusters)
    counts["reference"] = ref.groupby("cluster").size().reindex(clusters, fill_value=0)
    counts["candidate"] = alt.groupby("cluster").size().reindex(clusters, fill_value=0)
    counts["matched"] = matched.groupby("cluster").size().reindex(clusters, fill_value=0)
    array = counts.to_numpy(dtype=float)
    values = []
    for _ in range(repeats):
        sampled = array[rng.integers(0, len(array), size=len(array))].sum(axis=0)
        denominator = sampled[0] + sampled[1] - sampled[2]
        values.append(sampled[2] / denominator if denominator else 1.0)
    return _percentile_ci(values)


def weight_lambda_sensitivity(state: dict, cfg, base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    repeats = int(cfg.study_design.inference["bootstrap_replicates"])
    rng = np.random.default_rng(int(cfg.study_design.inference["random_seed"]))
    score_frames = []
    for weight_id, weights in WEIGHT_SETS.items():
        for lam in LAMBDAS:
            variant_id = f"{weight_id}__lambda_{int(lam * 100):03d}"
            frame = _rescore(state, cfg, weights, lam)
            frame["variant_id"] = variant_id
            frame["weight_id"] = weight_id
            frame["lambda"] = lam
            score_frames.append(frame)
    scores = pd.concat(score_frames, ignore_index=True)
    primary = scores.loc[scores["variant_id"].eq(PRIMARY_ID), ["timestamp", "sensor_id", "D2_total"]].rename(columns={"D2_total": "reference"})
    reference_events = _extract_events(primary.rename(columns={"reference": "D2_total"}), "D2_total")
    summaries = []
    for variant_id, candidate in scores.groupby("variant_id"):
        merged = primary.merge(
            candidate[["timestamp", "sensor_id", "D2_total", "weight_id", "lambda"]],
            on=["timestamp", "sensor_id"], validate="one_to_one",
        ).rename(columns={"D2_total": "candidate"})
        sensor_means = merged.groupby("sensor_id")[["reference", "candidate"]].mean()
        rho = _spearman_stat(sensor_means["reference"], sensor_means["candidate"])
        merged["month"] = merged["timestamp"].dt.to_period("M").astype(str)
        monthly = merged.groupby(["month", "sensor_id"], as_index=False)[["reference", "candidate"]].mean()
        rho_low, rho_high, rho_valid = _bootstrap_rank(monthly, rng, repeats)
        ref_low = merged["reference"].lt(3)
        alt_low = merged["candidate"].lt(3)
        merged["intersection"] = (ref_low & alt_low).astype(int)
        merged["union"] = (ref_low | alt_low).astype(int)
        merged["week"] = merged["timestamp"].dt.to_period("W").astype(str)
        clustered = merged.groupby(["sensor_id", "week"], as_index=False)[["intersection", "union"]].sum()
        hour_jaccard = merged["intersection"].sum() / max(merged["union"].sum(), 1)
        hour_low, hour_high = _bootstrap_binary(clustered, rng, repeats)
        candidate_events = _extract_events(
            merged[["timestamp", "sensor_id", "candidate"]].rename(columns={"candidate": "D2_total"}),
            "D2_total",
        )
        event_jaccard, pairs = _event_jaccard(reference_events, candidate_events)
        event_low, event_high = _bootstrap_event_jaccard(
            reference_events, candidate_events, pairs, rng, repeats
        )
        summaries.append({
            "variant_id": variant_id,
            "weight_id": candidate["weight_id"].iloc[0],
            "lambda": float(candidate["lambda"].iloc[0]),
            "channel_rank_spearman": rho,
            "channel_rank_ci95_low": rho_low,
            "channel_rank_ci95_high": rho_high,
            "channel_rank_bootstrap_valid": rho_valid,
            "low_hour_jaccard": hour_jaccard,
            "low_hour_ci95_low": hour_low,
            "low_hour_ci95_high": hour_high,
            "low_event_jaccard": event_jaccard,
            "low_event_ci95_low": event_low,
            "low_event_ci95_high": event_high,
            "reference_events": len(reference_events),
            "candidate_events": len(candidate_events),
            "matched_events": len(pairs),
            "low_hour_rate": float(alt_low.mean()),
            "mean_score": float(merged["candidate"].mean()),
        })
    return scores, pd.DataFrame(summaries)


def threshold_sensitivity(state: dict, cfg) -> pd.DataFrame:
    rows = []
    for family in ("Q_TI", "Q_GS"):
        for multiplier in (0.8, 1.0, 1.2):
            variant = copy.deepcopy(cfg)
            for metric, breaks in variant.mapping.piecewise_breaks[family].items():
                variant.mapping.piecewise_breaks[family][metric] = [
                    float(value) * multiplier for value in breaks
                ]
            ti = TemporalIntegrityScorer(variant)
            gs = GapSeverityScorer(variant)
            aggregator = D2Aggregator(variant, state["calib"])
            scores = []
            for sensor_id in state["scored_channels"]:
                stats = state["stats_all"][sensor_id]
                subs = state["subs_all"][sensor_id]
                q_ti = ti.score(stats) if family == "Q_TI" else subs["Q_TI"]
                q_gs = gs.score(stats) if family == "Q_GS" else subs["Q_GS"]
                scored = aggregator.aggregate(q_ti, q_gs, subs["Q_FA"], stats)
                scores.append(scored["D2_total"].rename(sensor_id))
            long = pd.concat(scores, axis=1).stack()
            rows.append({
                "parameter": f"{family}_break_multiplier",
                "setting": multiplier,
                "mean_score": float(long.mean()),
                "low_hour_rate": float(long.lt(3).mean()),
                "score_sd": float(long.std()),
            })
    for analyte, multipliers in {"DO": (0.5, 1.0, 2.0), "ORP": (0.5, 1.0, 2.0)}.items():
        threshold = cfg.mapping.freeze_detection[f"tau_iqr_{analyte}"]
        for multiplier in multipliers:
            fractions = []
            for sensor_id in [s for s in state["scored_channels"] if s.startswith(analyte)]:
                iqr = state["flags_all"][sensor_id]["rolling_iqr"]
                fractions.append(float(iqr.lt(threshold * multiplier).mean()))
            rows.append({
                "parameter": f"{analyte}_soft_iqr_diagnostic_multiplier",
                "setting": multiplier,
                "mean_score": np.nan,
                "low_hour_rate": np.nan,
                "score_sd": np.nan,
                "diagnostic_fraction": float(np.mean(fractions)),
                "affects_production_score": False,
            })
    for threshold in (0.10, 0.20, 0.30):
        fractions = []
        for sensor_id in ("DO_1_4", "DO_2_4"):
            values = state["flags_all"][sensor_id]["aligned_value"]
            fractions.append(float(values.notna().mul(values.le(threshold)).mean()))
        rows.append({
            "parameter": "process_floor_threshold_mg_L",
            "setting": threshold,
            "diagnostic_fraction": float(np.mean(fractions)),
            "affects_production_score": False,
        })
    return pd.DataFrame(rows)


def distribution_summary(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    for keys, group in base.groupby(["phase", "sensor_id", "analyte"]):
        phase, sensor_id, analyte = keys
        for metric in METRICS:
            values = group[metric].dropna()
            rows.append({
                "phase": phase,
                "sensor_id": sensor_id,
                "analyte": analyte,
                "metric": metric,
                "n_sensor_hours": len(values),
                "median": float(values.median()),
                "iqr": float(values.quantile(0.75) - values.quantile(0.25)),
                "p05": float(values.quantile(0.05)),
                "low_rate_lt3": float(values.lt(3).mean()),
            })
    summary = pd.DataFrame(rows)
    daily_rows = []
    temp = base.copy()
    temp["date"] = temp["timestamp"].dt.date
    for keys, group in temp.groupby(["sensor_id", "analyte", "date"]):
        sensor_id, analyte, date = keys
        for metric in METRICS:
            daily_rows.append({
                "sensor_id": sensor_id,
                "analyte": analyte,
                "date": date,
                "metric": metric,
                "daily_p05": float(group[metric].quantile(0.05)),
                "daily_min": float(group[metric].min()),
                "daily_low_rate_lt3": float(group[metric].lt(3).mean()),
            })
    daily = pd.DataFrame(daily_rows)
    sensor_month = base.assign(month=base["timestamp"].dt.to_period("M").astype(str)).groupby(
        ["month", "sensor_id", "analyte"], as_index=False
    )[list(METRICS)].mean()
    effects = []
    rng = np.random.default_rng(20260804)
    months = sensor_month["month"].unique()
    for metric in METRICS:
        do = sensor_month.loc[sensor_month["analyte"].eq("DO"), metric]
        orp = sensor_month.loc[sensor_month["analyte"].eq("ORP"), metric]
        pooled = np.sqrt((do.var(ddof=1) + orp.var(ddof=1)) / 2)
        smd = (orp.mean() - do.mean()) / pooled if pooled > 0 else np.nan
        boot = []
        for _ in range(2000):
            sampled = rng.choice(months, size=len(months), replace=True)
            frame = pd.concat([sensor_month.loc[sensor_month["month"].eq(month)] for month in sampled])
            boot.append(
                frame.loc[frame["analyte"].eq("ORP"), metric].mean()
                - frame.loc[frame["analyte"].eq("DO"), metric].mean()
            )
        low, high = _percentile_ci(boot)
        effects.append({
            "metric": metric,
            "ORP_minus_DO_mean": float(orp.mean() - do.mean()),
            "block_ci95_low": low,
            "block_ci95_high": high,
            "standardized_mean_difference": float(smd),
            "wasserstein_distance_descriptive": float(wasserstein_distance(orp, do)),
            "analysis_unit": "sensor_month",
        })
    return summary, daily, pd.DataFrame(effects)


def d1_d2_concordance(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d2 = pd.read_excel(ROOT / "artifacts" / "data" / "D2_freeze_availability_events.xlsx")
    d1 = pd.read_excel(PROJECT / "D1 Sensor health" / "outputs" / "data" / "D1_event_windows.xlsx", sheet_name="all_events")
    d2 = d2.rename(columns={"start_ts": "start", "end_ts": "end"})
    d1 = d1.rename(columns={"start": "start", "end": "end", "dominant_fault": "fault_type"})
    if "event_id" not in d1:
        d1.insert(0, "event_id", [f"D1E_{i:05d}" for i in range(1, len(d1) + 1)])
    for frame in (d1, d2):
        frame["start"] = pd.to_datetime(frame["start"])
        frame["end"] = pd.to_datetime(frame["end"])
    pairs = _match_events(d1, d2)
    event_jaccard = len(pairs) / max(len(d1) + len(d2) - len(pairs), 1)
    timeline = pd.DatetimeIndex(sorted(base["timestamp"].unique()))
    sensors = sorted(base["sensor_id"].unique())
    d1_masks, d2_masks = {}, {}
    for sensor_id in sensors:
        d1_mask = np.zeros(len(timeline), dtype=bool)
        d2_mask = np.zeros(len(timeline), dtype=bool)
        for _, event in d1.loc[d1["sensor_id"].eq(sensor_id)].iterrows():
            d1_mask |= (timeline >= event["start"].floor("h")) & (timeline <= event["end"].ceil("h"))
        for _, event in d2.loc[d2["sensor_id"].eq(sensor_id)].iterrows():
            d2_mask |= (timeline >= event["start"].floor("h")) & (timeline <= event["end"].ceil("h"))
        d1_masks[sensor_id] = d1_mask
        d2_masks[sensor_id] = d2_mask
    observed_intersection = sum(np.logical_and(d1_masks[s], d2_masks[s]).sum() for s in sensors)
    observed_union = sum(np.logical_or(d1_masks[s], d2_masks[s]).sum() for s in sensors)
    observed = observed_intersection / max(observed_union, 1)
    rng = np.random.default_rng(20260804)
    minimum_shift = 24 * 7
    null = []
    for replicate in range(2000):
        intersection = union = 0
        for sensor_id in sensors:
            shift = int(rng.integers(minimum_shift, len(timeline) - minimum_shift))
            shifted = np.roll(d2_masks[sensor_id], shift)
            intersection += np.logical_and(d1_masks[sensor_id], shifted).sum()
            union += np.logical_or(d1_masks[sensor_id], shifted).sum()
        null.append({"replicate": replicate + 1, "duration_jaccard": intersection / max(union, 1)})
    null_frame = pd.DataFrame(null)
    null_median = float(null_frame["duration_jaccard"].median())
    summary = pd.DataFrame([{
        "D1_events": len(d1),
        "D2_hard_availability_events": len(d2),
        "matched_event_pairs": len(pairs),
        "event_jaccard": event_jaccard,
        "duration_jaccard_observed": observed,
        "duration_jaccard_null_median": null_median,
        "duration_jaccard_enrichment": observed / null_median if null_median > 0 else np.nan,
        "circular_shift_p_upper": (1 + null_frame["duration_jaccard"].ge(observed).sum()) / (1 + len(null_frame)),
        "matching_tolerance": "1h",
        "null_model": "sensor_specific_circular_shift_minimum_7d",
    }])
    return summary, pairs, null_frame


def qti_component_audit(state: dict, cfg) -> pd.DataFrame:
    """Expose hourly Q_TI observability and weighted score deficits."""
    weights = cfg.mapping.Q_TI_weights
    frames = []
    component_columns = {
        "missing": "Q_miss_comp",
        "true_irregular": "Q_true_irregular_comp",
        "duplicate": "Q_duplicate_comp",
        "out_of_order": "Q_out_of_order_comp",
    }
    for sensor_id in state["scored_channels"]:
        subs = state["subs_all"][sensor_id]
        frame = pd.DataFrame({
            "timestamp": subs.index,
            "sensor_id": sensor_id,
            "analyte": sensor_id.split("_")[0],
            "phase": _phase(subs.index, cfg).to_numpy(),
            "Q_TI": subs["Q_TI"].to_numpy(),
            "observed_weight": subs["Q_TI_observed_weight"].to_numpy(),
            "source_gap_recovery_rate": subs["source_gap_recovery_rate"].to_numpy(),
            "value_gap_recovery_rate": subs["value_gap_recovery_rate"].to_numpy(),
        })
        for component, score_col in component_columns.items():
            values = subs[score_col]
            frame[f"Q_{component}"] = values.to_numpy()
            frame[f"weighted_deficit_{component}"] = (
                weights[component] * (5.0 - values)
            ).to_numpy()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def qti_threshold_reference(state: dict, cfg) -> pd.DataFrame:
    """Development-only threshold reference; never replaces production mapping."""
    development = cfg.study_design.periods["development"]
    metrics = (
        "missing_rate", "true_irregular_rate", "duplicate_rate", "out_of_order_rate"
    )
    rows = []
    for sensor_id in state["scored_channels"]:
        subs = state["subs_all"][sensor_id].loc[
            pd.Timestamp(development.start):pd.Timestamp(development.end)
        ]
        high_quality = subs.loc[subs["Q_GS"].ge(4.5) & subs["Q_FA"].ge(4.5)]
        for metric in metrics:
            values = high_quality[metric].dropna()
            quantiles = values.quantile([0.75, 0.90, 0.95, 0.99]) if len(values) else pd.Series(dtype=float)
            production = cfg.mapping.piecewise_breaks["Q_TI"][metric]
            unique_n = int(values.nunique())
            rows.append({
                "sensor_id": sensor_id,
                "analyte": sensor_id.split("_")[0],
                "metric": metric,
                "development_start": development.start,
                "development_end": development.end,
                "candidate_high_quality_rule": "Q_GS>=4.5 and Q_FA>=4.5",
                "support_n": int(len(values)),
                "unique_value_n": unique_n,
                "q75": quantiles.get(0.75, np.nan),
                "q90": quantiles.get(0.90, np.nan),
                "q95": quantiles.get(0.95, np.nan),
                "q99": quantiles.get(0.99, np.nan),
                "production_b0": production[0],
                "production_b1": production[1],
                "production_b2": production[2],
                "production_b3": production[3],
                "production_b4": production[4],
                "degenerate_reference": bool(unique_n < 5),
                "decision": "sensitivity_only_not_adopted",
                "reason": (
                    "zero_or_sparse_empirical_support_requires_engineering_floor"
                    if unique_n < 5 else
                    "independent_SAP_lock_required_before_production_use"
                ),
            })
    return pd.DataFrame(rows)


def _write_manifest(state: dict, outputs: list[Path]) -> Path:
    records = {}
    for path in sorted(outputs):
        records[str(path.relative_to(OUTPUT)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "d2-scientific-validation-v2",
        "run_id": state["run_id"],
        "calibration_id": state["calibration_id"],
        "external_site_validation": "deferred",
        "outputs": records,
    }
    path = OUTPUT / "D2_scientific_validation_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def main() -> Path:
    cfg = load_config(ROOT / "configs", version="v1")
    with (ROOT / "artifacts" / "d2_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    base = _long_state(state, cfg)
    weight_scores, weight_summary = weight_lambda_sensitivity(state, cfg, base)
    threshold_summary = threshold_sensitivity(state, cfg)
    distributions, daily, effects = distribution_summary(base)
    concordance, pairs, null = d1_d2_concordance(base)
    qti_audit = qti_component_audit(state, cfg)
    qti_thresholds = qti_threshold_reference(state, cfg)
    outputs = {
        "D2_weight_lambda_scores.parquet": weight_scores,
        "D2_weight_lambda_summary.parquet": weight_summary,
        "D2_threshold_sensitivity.parquet": threshold_summary,
        "D2_distribution_summary.parquet": distributions,
        "D2_daily_summary.parquet": daily,
        "D2_analyte_effects.parquet": effects,
        "D2_d1d2_concordance.parquet": concordance,
        "D2_d1d2_event_pairs.parquet": pairs,
        "D2_d1d2_circular_null.parquet": null,
        "D2_qti_component_audit.parquet": qti_audit,
        "D2_qti_threshold_reference.parquet": qti_thresholds,
    }
    written = []
    for filename, frame in outputs.items():
        path = OUTPUT / filename
        frame.to_parquet(path, index=False)
        written.append(path)
    workbook = OUTPUT / "D2_scientific_validation_source_data.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        weight_summary.to_excel(writer, sheet_name="weight_lambda", index=False)
        threshold_summary.to_excel(writer, sheet_name="thresholds", index=False)
        distributions.to_excel(writer, sheet_name="distributions", index=False)
        effects.to_excel(writer, sheet_name="analyte_effects", index=False)
        concordance.to_excel(writer, sheet_name="D1_D2_concordance", index=False)
        pairs.to_excel(writer, sheet_name="event_pairs", index=False)
        qti_audit.groupby(["sensor_id", "analyte"], as_index=False).agg(
            Q_TI_mean=("Q_TI", "mean"),
            observed_weight_mean=("observed_weight", "mean"),
            missing_deficit=("weighted_deficit_missing", "mean"),
            irregular_deficit=("weighted_deficit_true_irregular", "mean"),
            duplicate_deficit=("weighted_deficit_duplicate", "mean"),
            out_of_order_deficit=("weighted_deficit_out_of_order", "mean"),
        ).to_excel(writer, sheet_name="QTI_component_audit", index=False)
        qti_thresholds.to_excel(writer, sheet_name="QTI_threshold_reference", index=False)
    written.append(workbook)
    manifest = _write_manifest(state, written)
    print(json.dumps({
        "run_id": state["run_id"],
        "calibration_id": state["calibration_id"],
        "weight_variants": len(weight_summary),
        "event_concordance": concordance.to_dict("records")[0],
        "manifest": str(manifest),
    }, indent=2, default=str))
    return manifest


if __name__ == "__main__":
    main()
