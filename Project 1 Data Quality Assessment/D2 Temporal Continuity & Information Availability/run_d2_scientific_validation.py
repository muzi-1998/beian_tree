"""Confirmatory scientific validation for the frozen D2 V4 release."""
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
    HardAvailabilityScorer,
    TemporalIntegrityScorer,
)
from src.utils.config_loader import load_config  # noqa: E402


WEIGHT_SETS = {
    "equal": {"Q_TI": 1 / 3, "Q_GS": 1 / 3, "Q_HA": 1 / 3},
    "primary_qha_040": {"Q_TI": 0.30, "Q_GS": 0.30, "Q_HA": 0.40},
    "qha_enhanced_050": {"Q_TI": 0.25, "Q_GS": 0.25, "Q_HA": 0.50},
}
LAMBDAS = (0.50, 0.70, 0.90)
PRIMARY_ID = "primary_qha_040__lambda_070"
METRICS = ("Q_TI", "Q_GS", "Q_HA", "D2_total")
EVENT_COLUMNS = ("event_id", "sensor_id", "start", "end", "duration_hours")
PAIR_COLUMNS = (
    "sensor_id", "reference_event_id", "candidate_event_id",
    "reference_start", "candidate_start", "overlap_hours", "separation_hours",
)


def _phase(index: pd.DatetimeIndex, cfg) -> pd.Series:
    result = pd.Series("outside_contract", index=index, dtype=object)
    for name, period in cfg.study_design.periods.items():
        start = pd.Timestamp(period.start)
        end = pd.Timestamp(period.end)
        result.iloc[np.flatnonzero((index >= start) & (index <= end))] = name
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
            "info_empty_cov", "hard_stasis_fraction_observed",
            "qha_observed_fraction", "sensor_freeze_cov", "low_iqr_cov",
            "soft_rle_cov", "soft_stasis_cov", "floor_occupancy",
            "resolution_limited", "rl_rate", "intrinsic_soft_evidence",
            "peer_response_loss_evidence", "soft_evidence_family_count",
            "quasi_freeze_suspect", "D2_sensitive_risk",
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
            subs["Q_TI"], subs["Q_GS"], subs["Q_HA"], subs
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


def _bootstrap_rate(clustered: pd.DataFrame, rng, repeats: int) -> tuple[float, float]:
    values = []
    array = clustered[["events", "sensor_hours"]].to_numpy(dtype=float)
    for _ in range(repeats):
        sampled = array[rng.integers(0, len(array), size=len(array))].sum(axis=0)
        values.append(sampled[0] / sampled[1] * 1000 if sampled[1] else np.nan)
    return _percentile_ci(values)


def _binary_association(left: pd.Series, right: pd.Series) -> tuple[float, float]:
    a = left.astype(bool).to_numpy()
    b = right.astype(bool).to_numpy()
    n11 = float(np.logical_and(a, b).sum())
    n10 = float(np.logical_and(a, ~b).sum())
    n01 = float(np.logical_and(~a, b).sum())
    n00 = float(np.logical_and(~a, ~b).sum())
    denominator = np.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    phi = (n11 * n00 - n10 * n01) / denominator if denominator else np.nan
    union = n11 + n10 + n01
    jaccard = n11 / union if union else 1.0
    return float(phi), float(jaccard)


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
                scored = aggregator.aggregate(q_ti, q_gs, subs["Q_HA"], stats)
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


def d1_d2_concordance(
    base: pd.DataFrame, cfg
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    phase_indices = {
        name: np.flatnonzero(
            (timeline >= pd.Timestamp(period.start))
            & (timeline <= pd.Timestamp(period.end))
        )
        for name, period in cfg.study_design.periods.items()
    }
    null = []
    phase_null = []
    for replicate in range(2000):
        intersection = union = 0
        phase_intersection = phase_union = 0
        for sensor_id in sensors:
            shift = int(rng.integers(minimum_shift, len(timeline) - minimum_shift))
            shifted = np.roll(d2_masks[sensor_id], shift)
            intersection += np.logical_and(d1_masks[sensor_id], shifted).sum()
            union += np.logical_or(d1_masks[sensor_id], shifted).sum()
            constrained = np.zeros(len(timeline), dtype=bool)
            for indices in phase_indices.values():
                if not len(indices):
                    continue
                segment = d2_masks[sensor_id][indices]
                lower = min(minimum_shift, max(1, len(indices) // 4))
                upper = max(lower + 1, len(indices) - lower)
                phase_shift = int(rng.integers(lower, upper)) if upper > lower else 1
                constrained[indices] = np.roll(segment, phase_shift)
            phase_intersection += np.logical_and(d1_masks[sensor_id], constrained).sum()
            phase_union += np.logical_or(d1_masks[sensor_id], constrained).sum()
        null.append({"replicate": replicate + 1, "duration_jaccard": intersection / max(union, 1)})
        phase_null.append({
            "replicate": replicate + 1,
            "duration_jaccard": phase_intersection / max(phase_union, 1),
            "constraint": "within_locked_phase",
        })
    null_frame = pd.DataFrame(null)
    phase_null_frame = pd.DataFrame(phase_null)
    null_median = float(null_frame["duration_jaccard"].median())
    null_mean = float(null_frame["duration_jaccard"].mean())
    summary = pd.DataFrame([{
        "D1_events": len(d1),
        "D2_hard_availability_events": len(d2),
        "matched_event_pairs": len(pairs),
        "event_jaccard": event_jaccard,
        "duration_jaccard_observed": observed,
        "duration_jaccard_null_median": null_median,
        "duration_jaccard_null_mean": null_mean,
        "duration_jaccard_enrichment_vs_null_mean": (
            observed / null_mean if null_mean > 0 else np.nan
        ),
        "circular_shift_p_upper": (1 + null_frame["duration_jaccard"].ge(observed).sum()) / (1 + len(null_frame)),
        "phase_constrained_null_median": float(phase_null_frame["duration_jaccard"].median()),
        "phase_constrained_null_mean": float(phase_null_frame["duration_jaccard"].mean()),
        "phase_constrained_p_upper": (
            1 + phase_null_frame["duration_jaccard"].ge(observed).sum()
        ) / (1 + len(phase_null_frame)),
        "matching_tolerance": "1h",
        "null_model": "sensor_specific_circular_shift_minimum_7d",
        "sensitivity_null_model": "sensor_specific_circular_shift_within_locked_phase",
    }])
    return summary, pairs, null_frame, phase_null_frame


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
        high_quality = subs.loc[subs["Q_GS"].ge(4.5) & subs["Q_HA"].ge(4.5)]
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
                "candidate_high_quality_rule": "Q_GS>=4.5 and Q_HA>=4.5",
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


def evidence_redundancy_audit(
    state: dict, cfg, base: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Quantify correlated evidence and prespecified leave-one-family-out effects."""
    component_cols = ["Q_TI", "Q_GS", "Q_HA"]
    complete = base[component_cols].dropna()
    pearson = complete.corr(method="pearson")
    spearman = complete.corr(method="spearman")
    correlation_rows = []
    for row in component_cols:
        for column in component_cols:
            phi, jaccard = _binary_association(
                complete[row].lt(3), complete[column].lt(3)
            )
            correlation_rows.append({
                "row": row,
                "column": column,
                "pearson_r": float(pearson.loc[row, column]),
                "spearman_rho": float(spearman.loc[row, column]),
                "low_event_phi": phi,
                "low_event_jaccard": jaccard,
                "low_threshold": 3.0,
            })
    correlation = pd.DataFrame(correlation_rows)
    standardised = (complete - complete.mean()) / complete.std(ddof=0).replace(0, np.nan)
    eigenvalues = np.linalg.eigvalsh(standardised.corr().fillna(0).to_numpy())[::-1]
    effective_dimension = float(eigenvalues.sum() ** 2 / np.square(eigenvalues).sum())
    correlation["effective_dimension_global"] = effective_dimension

    variants = []
    for sensor_id in state["scored_channels"]:
        subs = state["subs_all"][sensor_id]
        qti_without_missing = (
            0.25 * subs["Q_true_irregular_comp"]
            + 0.05 * subs["Q_duplicate_comp"]
            + 0.05 * subs["Q_out_of_order_comp"]
        ) / 0.35
        candidates = {
            "strict_production": (subs["Q_TI"], subs["Q_GS"], subs["Q_HA"]),
            "without_QTI_missing": (qti_without_missing, subs["Q_GS"], subs["Q_HA"]),
            "without_QGS": (subs["Q_TI"], pd.Series(np.nan, index=subs.index), subs["Q_HA"]),
            "without_QHA": (subs["Q_TI"], subs["Q_GS"], pd.Series(np.nan, index=subs.index)),
        }
        aggregator = D2Aggregator(cfg, state["calib"])
        for variant_id, (qti, qgs, qha) in candidates.items():
            scored = aggregator.aggregate(qti, qgs, qha, subs)
            frame = scored[["D2_total"]].rename(columns={"D2_total": "score"})
            frame.insert(0, "sensor_id", sensor_id)
            frame.insert(0, "timestamp", frame.index)
            frame["variant_id"] = variant_id
            variants.append(frame.reset_index(drop=True))
    scores = pd.concat(variants, ignore_index=True)
    reference = scores.loc[scores["variant_id"].eq("strict_production")].copy()
    reference = reference.rename(columns={"score": "reference"})[
        ["timestamp", "sensor_id", "reference"]
    ]
    reference_events = _extract_events(
        reference.rename(columns={"reference": "D2_total"}), "D2_total"
    )
    rng = np.random.default_rng(int(cfg.study_design.inference["random_seed"]))
    repeats = int(cfg.study_design.inference["bootstrap_replicates"])
    summaries = []
    for variant_id, candidate in scores.groupby("variant_id"):
        merged = reference.merge(
            candidate[["timestamp", "sensor_id", "score"]],
            on=["timestamp", "sensor_id"], validate="one_to_one",
        )
        ref_low = merged["reference"].lt(3)
        alt_low = merged["score"].lt(3)
        merged["intersection"] = (ref_low & alt_low).astype(int)
        merged["union"] = (ref_low | alt_low).astype(int)
        merged["week"] = merged["timestamp"].dt.to_period("W").astype(str)
        clusters = merged.groupby(["sensor_id", "week"], as_index=False)[
            ["intersection", "union"]
        ].sum()
        hour_low, hour_high = _bootstrap_binary(clusters, rng, repeats)
        candidate_events = _extract_events(
            candidate.rename(columns={"score": "D2_total"}), "D2_total"
        )
        event_jaccard, pairs = _event_jaccard(reference_events, candidate_events)
        event_low, event_high = _bootstrap_event_jaccard(
            reference_events, candidate_events, pairs, rng, repeats
        )
        sensor_means = merged.groupby("sensor_id")[["reference", "score"]].mean()
        summaries.append({
            "variant_id": variant_id,
            "mean_score": float(merged["score"].mean()),
            "deficit_points_per_1000h": float((5 - merged["score"]).sum() / len(merged) * 1000),
            "low_hours_per_1000h": float(alt_low.mean() * 1000),
            "low_hour_jaccard": float(merged["intersection"].sum() / max(merged["union"].sum(), 1)),
            "low_hour_ci95_low": hour_low,
            "low_hour_ci95_high": hour_high,
            "low_event_jaccard": event_jaccard,
            "low_event_ci95_low": event_low,
            "low_event_ci95_high": event_high,
            "sensor_rank_spearman": _spearman_stat(sensor_means["reference"], sensor_means["score"]),
            "reference_events": len(reference_events),
            "candidate_events": len(candidate_events),
        })
    summary_frame = pd.DataFrame(summaries)
    strict = summary_frame.loc[summary_frame["variant_id"].eq("strict_production")].iloc[0]
    summary_frame["delta_candidate_events"] = summary_frame["candidate_events"] - strict["candidate_events"]
    summary_frame["delta_low_hours_per_1000h"] = (
        summary_frame["low_hours_per_1000h"] - strict["low_hours_per_1000h"]
    )
    summary_frame["delta_deficit_points_per_1000h"] = (
        summary_frame["deficit_points_per_1000h"] - strict["deficit_points_per_1000h"]
    )
    hierarchy = pd.DataFrame([
        {"source": "Raw source", "target": "Timestamp audit", "role": "source_branch"},
        {"source": "Timestamp audit", "target": "Q_TI", "role": "strict"},
        {"source": "Raw source", "target": "Missing runs", "role": "source_branch"},
        {"source": "Missing runs", "target": "Q_TI", "role": "shared_input"},
        {"source": "Missing runs", "target": "Q_GS", "role": "shared_input"},
        {"source": "Raw source", "target": "Observed values", "role": "source_branch"},
        {"source": "Observed values", "target": "Q_HA", "role": "strict"},
        {"source": "Raw source", "target": "Soft dynamics + peer", "role": "source_branch"},
        {"source": "Soft dynamics + peer", "target": "Sensitive risk", "role": "diagnostic_only"},
    ])
    return correlation, summary_frame, hierarchy


def qha_window_sensitivity(state: dict, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    score_frames = []
    for window_h in (3, 6, 9, 12):
        for sensor_id in state["scored_channels"]:
            flags = state["flags_all"][sensor_id]
            minutes = window_h * 60
            hard = flags["sensor_freeze"].rolling(f"{window_h}h", min_periods=minutes).sum()
            observed = flags["present_raw"].rolling(f"{window_h}h", min_periods=minutes).sum()
            fraction = hard.div(observed.where(observed > 0)).resample("1h").last()
            subs = state["subs_all"][sensor_id]
            stats = state["stats_all"][sensor_id].copy()
            stats["hard_stasis_fraction_observed"] = fraction.reindex(stats.index)
            qha, _ = HardAvailabilityScorer(cfg).score(
                stats, pd.Series(0.0, index=stats.index), allow_response_loss=False
            )
            scored = D2Aggregator(cfg, state["calib"]).aggregate(
                subs["Q_TI"], subs["Q_GS"], qha, stats
            )
            frame = scored[["D2_total", "Q_HA"]].copy()
            frame.insert(0, "sensor_id", sensor_id)
            frame.insert(0, "timestamp", frame.index)
            frame["window_h"] = window_h
            score_frames.append(frame.reset_index(drop=True))
    scores = pd.concat(score_frames, ignore_index=True)
    reference = scores.loc[scores["window_h"].eq(6), ["timestamp", "sensor_id", "D2_total"]]
    reference_events = _extract_events(reference, "D2_total")
    rng = np.random.default_rng(int(cfg.study_design.inference["random_seed"]) + 18)
    repeats = int(cfg.study_design.inference["bootstrap_replicates"])
    summaries = []
    for window_h, candidate in scores.groupby("window_h"):
        merged = reference.merge(
            candidate[["timestamp", "sensor_id", "D2_total"]],
            on=["timestamp", "sensor_id"], suffixes=("_ref", "_candidate"),
        )
        ref_low = merged["D2_total_ref"].lt(3)
        alt_low = merged["D2_total_candidate"].lt(3)
        candidate_events = _extract_events(candidate, "D2_total")
        event_jaccard, pairs = _event_jaccard(reference_events, candidate_events)
        event_low, event_high = _bootstrap_event_jaccard(
            reference_events, candidate_events, pairs, rng, repeats
        )
        merged["low"] = alt_low.astype(int)
        merged["total"] = 1
        merged["week"] = merged["timestamp"].dt.to_period("W").astype(str)
        clustered = merged.groupby(["sensor_id", "week"], as_index=False).agg(
            events=("low", "sum"), sensor_hours=("total", "sum")
        )
        low_rate_low, low_rate_high = _bootstrap_rate(clustered, rng, repeats)
        summaries.append({
            "window_h": window_h,
            "mean_Q_HA": float(candidate["Q_HA"].mean()),
            "low_hour_rate": float(alt_low.mean()),
            "low_hour_jaccard_vs_6h": float((ref_low & alt_low).sum() / max((ref_low | alt_low).sum(), 1)),
            "low_event_jaccard_vs_6h": event_jaccard,
            "low_event_jaccard_ci95_low": event_low,
            "low_event_jaccard_ci95_high": event_high,
            "candidate_events": len(candidate_events),
            "low_hour_rate_ci95_low": low_rate_low / 1000,
            "low_hour_rate_ci95_high": low_rate_high / 1000,
            "passes_prespecified_jaccard_0_75": bool(event_jaccard >= 0.75),
        })
    return scores, pd.DataFrame(summaries)


def _veto_reason_group(reasons: pd.Series) -> np.ndarray:
    return np.select(
        [
            reasons.eq("L_max_p99|missing_p99"),
            reasons.eq("missing_p99"),
            reasons.eq("L_max_p99"),
            reasons.str.contains("hard_stasis_severe", na=False),
        ],
        ["Gap + missing", "Missing only", "Gap only", "Hard stasis"],
        default="Other",
    )


def low_tail_burden(
    state: dict, cfg, base: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    for keys, group in base.groupby(["phase", "sensor_id", "analyte"]):
        phase, sensor_id, analyte = keys
        n = len(group)
        rows.append({
            "phase": phase,
            "sensor_id": sensor_id,
            "analyte": analyte,
            "n_sensor_hours": n,
            "mean_D2_auxiliary": float(group["D2_total"].mean()),
            "p01_D2": float(group["D2_total"].quantile(0.01)),
            "deficit_points_per_1000h": float((5 - group["D2_total"]).sum() / n * 1000),
            "low_hours_per_1000h": float(group["D2_total"].lt(3).mean() * 1000),
            "veto_hours_per_1000h": float(group["veto_flag"].mean() * 1000),
            "sensitive_suspect_hours_per_1000h": float(group["quasi_freeze_suspect"].mean() * 1000),
        })
    burden = pd.DataFrame(rows)

    raw_events = []
    gap = state["gap_df"].rename(columns={
        "gap_id": "event_id", "sensor_scope": "sensor_id",
        "start_ts": "start", "end_ts": "end", "duration_min": "raw_duration_min",
    }).copy()
    gap["event_type"] = "gap"
    raw_events.append(gap[["event_id", "sensor_id", "start", "end", "raw_duration_min", "event_type"]])
    hard = state["freeze_events"].rename(columns={
        "start_ts": "start", "end_ts": "end", "duration_min": "raw_duration_min",
    }).copy()
    if len(hard):
        hard["event_type"] = "hard_stasis"
        raw_events.append(hard[["event_id", "sensor_id", "start", "end", "raw_duration_min", "event_type"]])
    raw = pd.concat(raw_events, ignore_index=True)
    raw["start"] = pd.to_datetime(raw["start"])
    raw["end"] = pd.to_datetime(raw["end"])
    scored_events = _extract_events(base, "D2_total")
    pairs = _match_events(raw, scored_events, tolerance="24h")
    impact = raw.merge(
        pairs[["reference_event_id", "candidate_event_id", "overlap_hours", "separation_hours"]],
        left_on="event_id", right_on="reference_event_id", how="left",
    ).merge(
        scored_events[["event_id", "duration_hours"]],
        left_on="candidate_event_id", right_on="event_id", how="left", suffixes=("", "_score"),
    )
    impact = impact.drop(columns=["event_id_score"], errors="ignore")
    impact["score_impact_duration_h"] = impact["duration_hours"]
    impact["raw_duration_h"] = impact["raw_duration_min"] / 60

    score_events = scored_events.copy()
    score_events["phase"] = _phase(pd.DatetimeIndex(score_events["start"]), cfg).to_numpy()
    score_events["analyte"] = score_events["sensor_id"].str.split("_").str[0]
    score_events["month"] = score_events["start"].dt.to_period("M").astype(str)
    exposure = base[["timestamp", "sensor_id", "analyte", "phase"]].copy()
    exposure["month"] = exposure["timestamp"].dt.to_period("M").astype(str)
    rng = np.random.default_rng(int(cfg.study_design.inference["random_seed"]) + 15)
    repeats = int(cfg.study_design.inference["bootstrap_replicates"])
    event_summary_rows = []
    for phase in cfg.study_design.periods:
        for analyte in ("DO", "ORP", "ALL"):
            exp = exposure.loc[exposure["phase"].eq(phase)].copy()
            events = score_events.loc[score_events["phase"].eq(phase)].copy()
            if analyte != "ALL":
                exp = exp.loc[exp["analyte"].eq(analyte)]
                events = events.loc[events["analyte"].eq(analyte)]
            clusters = exp.groupby(["sensor_id", "month"]).size().rename("sensor_hours").reset_index()
            event_counts = events.groupby(["sensor_id", "month"]).size().rename("events")
            clusters = clusters.join(event_counts, on=["sensor_id", "month"])
            clusters["events"] = clusters["events"].fillna(0)
            rate = len(events) / len(exp) * 1000 if len(exp) else np.nan
            rate_low, rate_high = _bootstrap_rate(clusters, rng, repeats)
            duration = events["duration_hours"]
            event_summary_rows.append({
                "phase": phase,
                "analyte": analyte,
                "n_events": int(len(events)),
                "n_sensor_hours": int(len(exp)),
                "events_per_1000h": float(rate),
                "event_rate_ci95_low": rate_low,
                "event_rate_ci95_high": rate_high,
                "duration_median_h": float(duration.median()) if len(duration) else np.nan,
                "duration_p95_h": float(duration.quantile(0.95)) if len(duration) else np.nan,
                "duration_max_h": float(duration.max()) if len(duration) else np.nan,
            })
    event_summary = pd.DataFrame(event_summary_rows)

    veto = base.loc[base["veto_flag"].astype(bool), ["phase", "veto_reason"]].copy()
    veto["reason_group"] = _veto_reason_group(veto["veto_reason"])
    veto_summary = veto.groupby(["phase", "reason_group"], as_index=False).size().rename(
        columns={"size": "veto_hours"}
    )
    totals = veto_summary.groupby("phase")["veto_hours"].transform("sum")
    veto_summary["veto_share"] = veto_summary["veto_hours"] / totals
    phase_hours = base.groupby("phase").size()
    veto_summary["veto_hours_per_1000h"] = veto_summary.apply(
        lambda row: row["veto_hours"] / phase_hours.get(row["phase"], np.nan) * 1000,
        axis=1,
    )
    return burden, impact, event_summary, veto_summary


def channel_outcome_profile(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for (sensor_id, analyte), group in base.groupby(["sensor_id", "analyte"], sort=True):
        score = group["D2_Strict"]
        grade_share = group["grade"].value_counts(normalize=True).reindex(
            list("ABCDE"), fill_value=0.0
        )
        rows.append({
            "sensor_id": sensor_id,
            "analyte": analyte,
            "n_sensor_hours": int(len(group)),
            "mean_D2_Strict": float(score.mean()),
            "p05_D2_Strict": float(score.quantile(0.05)),
            "q25_D2_Strict": float(score.quantile(0.25)),
            "median_D2_Strict": float(score.median()),
            "q75_D2_Strict": float(score.quantile(0.75)),
            "p95_D2_Strict": float(score.quantile(0.95)),
            "low_hours_per_1000h": float(score.lt(3.0).mean() * 1000),
            "veto_hours_per_1000h": float(group["veto_flag"].astype(bool).mean() * 1000),
            **{f"grade_{grade}_pct": float(grade_share[grade] * 100) for grade in "ABCDE"},
        })
    profile = pd.DataFrame(rows).sort_values(
        ["median_D2_Strict", "p05_D2_Strict", "mean_D2_Strict", "sensor_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    profile.insert(0, "display_order", np.arange(1, len(profile) + 1))

    veto = base.loc[
        base["veto_flag"].astype(bool), ["sensor_id", "analyte", "veto_reason"]
    ].copy()
    veto["reason_group"] = _veto_reason_group(veto["veto_reason"])
    counts = veto.groupby(
        ["sensor_id", "analyte", "reason_group"], as_index=False
    ).size().rename(columns={"size": "veto_hours"})
    exposure = base.groupby("sensor_id").size().rename("n_sensor_hours")
    totals = counts.groupby("sensor_id")["veto_hours"].transform("sum")
    counts["veto_share_pct"] = counts["veto_hours"] / totals * 100
    counts["veto_hours_per_1000h"] = counts.apply(
        lambda row: row["veto_hours"] / exposure[row["sensor_id"]] * 1000,
        axis=1,
    )
    counts = counts.merge(
        profile[["sensor_id", "display_order"]], on="sensor_id", how="left"
    ).sort_values(["display_order", "reason_group"]).reset_index(drop=True)
    return profile, counts


def sensitive_diagnostic_summary(state: dict) -> pd.DataFrame:
    rows = []
    for sensor_id in state["scored_channels"]:
        sub = state["subs_all"][sensor_id]
        rows.append({
            "sensor_id": sensor_id,
            "analyte": sensor_id.split("_")[0],
            "soft_stasis_fraction": float(sub["soft_stasis_cov"].mean()),
            "intrinsic_soft_hour_rate": float(sub["intrinsic_soft_evidence"].mean()),
            "peer_response_loss_hour_rate": float(sub["peer_response_loss_evidence"].mean()),
            "joint_soft_hour_rate": float(sub["soft_evidence_family_count"].ge(2).mean()),
            "sustained_quasi_freeze_hour_rate": float(sub["quasi_freeze_suspect"].mean()),
            "production_Q_HA_low_rate": float(sub["Q_HA"].lt(3).mean()),
        })
    return pd.DataFrame(rows)


def _write_manifest(state: dict, outputs: list[Path]) -> Path:
    records = {}
    for path in sorted(outputs):
        records[str(path.relative_to(OUTPUT)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "d2-scientific-validation-v3",
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
    concordance, pairs, null, phase_null = d1_d2_concordance(base, cfg)
    qti_audit = qti_component_audit(state, cfg)
    qti_thresholds = qti_threshold_reference(state, cfg)
    redundancy_corr, redundancy_ablation, hierarchy = evidence_redundancy_audit(
        state, cfg, base
    )
    window_scores, window_summary = qha_window_sensitivity(state, cfg)
    burden, event_impact, event_summary, veto_summary = low_tail_burden(state, cfg, base)
    channel_profile, channel_veto = channel_outcome_profile(base)
    sensitive_summary = sensitive_diagnostic_summary(state)
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
        "D2_d1d2_phase_constrained_null.parquet": phase_null,
        "D2_qti_component_audit.parquet": qti_audit,
        "D2_qti_threshold_reference.parquet": qti_thresholds,
        "D2_evidence_redundancy_correlation.parquet": redundancy_corr,
        "D2_evidence_redundancy_ablation.parquet": redundancy_ablation,
        "D2_evidence_hierarchy.parquet": hierarchy,
        "D2_qha_window_scores.parquet": window_scores,
        "D2_qha_window_sensitivity.parquet": window_summary,
        "D2_low_tail_burden.parquet": burden,
        "D2_raw_vs_score_event_impact.parquet": event_impact,
        "D2_low_tail_event_summary.parquet": event_summary,
        "D2_veto_reason_summary.parquet": veto_summary,
        "D2_channel_outcome_profile.parquet": channel_profile,
        "D2_channel_veto_composition.parquet": channel_veto,
        "D2_sensitive_diagnostic_summary.parquet": sensitive_summary,
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
        phase_null.to_excel(writer, sheet_name="D1_D2_phase_null", index=False)
        qti_audit.groupby(["sensor_id", "analyte"], as_index=False).agg(
            Q_TI_mean=("Q_TI", "mean"),
            observed_weight_mean=("observed_weight", "mean"),
            missing_deficit=("weighted_deficit_missing", "mean"),
            irregular_deficit=("weighted_deficit_true_irregular", "mean"),
            duplicate_deficit=("weighted_deficit_duplicate", "mean"),
            out_of_order_deficit=("weighted_deficit_out_of_order", "mean"),
        ).to_excel(writer, sheet_name="QTI_component_audit", index=False)
        qti_thresholds.to_excel(writer, sheet_name="QTI_threshold_reference", index=False)
        redundancy_corr.to_excel(writer, sheet_name="redundancy_corr", index=False)
        redundancy_ablation.to_excel(writer, sheet_name="redundancy_ablation", index=False)
        hierarchy.to_excel(writer, sheet_name="evidence_hierarchy", index=False)
        window_summary.to_excel(writer, sheet_name="QHA_window_sensitivity", index=False)
        burden.to_excel(writer, sheet_name="low_tail_burden", index=False)
        event_impact.to_excel(writer, sheet_name="raw_vs_score_impact", index=False)
        event_summary.to_excel(writer, sheet_name="low_tail_events", index=False)
        veto_summary.to_excel(writer, sheet_name="veto_reasons", index=False)
        channel_profile.to_excel(writer, sheet_name="channel_outcome", index=False)
        channel_veto.to_excel(writer, sheet_name="channel_veto", index=False)
        sensitive_summary.to_excel(writer, sheet_name="sensitive_diagnostics", index=False)
    written.append(workbook)
    manifest = _write_manifest(state, written)
    print(json.dumps({
        "run_id": state["run_id"],
        "calibration_id": state["calibration_id"],
        "weight_variants": len(weight_summary),
        "redundancy_variants": len(redundancy_ablation),
        "qha_windows": window_summary["window_h"].tolist(),
        "event_concordance": concordance.to_dict("records")[0],
        "manifest": str(manifest),
    }, indent=2, default=str))
    return manifest


if __name__ == "__main__":
    main()
