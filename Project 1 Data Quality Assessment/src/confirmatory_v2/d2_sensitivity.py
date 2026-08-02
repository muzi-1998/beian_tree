from __future__ import annotations

import copy
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .common import CONFIG_ROOT, PROJECT_ROOT, event_jaccard, read_yaml


D2_ROOT = PROJECT_ROOT / "D2 Temporal Continuity & Information Availability"


def _load_d2_api():
    import src

    source_root = D2_ROOT / "src"
    if str(source_root) not in src.__path__:
        src.__path__.append(str(source_root))
    from src.d2_availability.scorer import (  # type: ignore
        D2Aggregator,
        FreezeAvailabilityScorer,
        GapSeverityScorer,
    )
    from src.utils.config_loader import load_config  # type: ignore

    return load_config, FreezeAvailabilityScorer, GapSeverityScorer, D2Aggregator


def _long_scores(all_d2: dict[str, pd.DataFrame], variant_id: str) -> pd.DataFrame:
    frames = []
    for sensor_id, frame in all_d2.items():
        selected = frame[["D2_total", "Q_TI", "Q_GS", "Q_FA", "veto_flag", "veto_reason"]].copy()
        selected.insert(0, "sensor_id", sensor_id)
        selected.insert(0, "timestamp", selected.index)
        selected["variant_id"] = variant_id
        frames.append(selected.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True)


def _rescore(
    state: dict,
    cfg,
    *,
    qfa_window_hours: int = 6,
    hard_rle_minutes: int = 15,
    gap_break_multiplier: float = 1.0,
) -> dict[str, pd.DataFrame]:
    _, FreezeAvailabilityScorer, GapSeverityScorer, D2Aggregator = _load_d2_api()
    cfg_variant = copy.deepcopy(cfg)
    for metric, values in cfg_variant.mapping.piecewise_breaks["Q_GS"].items():
        cfg_variant.mapping.piecewise_breaks["Q_GS"][metric] = [
            float(value) * float(gap_break_multiplier) for value in values
        ]
    fa_scorer = FreezeAvailabilityScorer(cfg_variant)
    gs_scorer = GapSeverityScorer(cfg_variant)
    aggregator = D2Aggregator(cfg_variant, state["calib"])
    outputs: dict[str, pd.DataFrame] = {}
    for sensor_id in state["scored_channels"]:
        stats = state["stats_all"][sensor_id].copy()
        flags = state["flags_all"][sensor_id]
        meta = cfg_variant.sensors[sensor_id]
        if meta.availability_mode == "process_floor":
            unavailable = (
                flags["missing"].astype(bool)
                | flags["long_gap"].astype(bool)
                | flags["hard_rle_run_min"].ge(int(hard_rle_minutes))
            )
        else:
            unavailable = flags["qfa_unavailable"].astype(bool)
        minimum = int(qfa_window_hours * 60)
        stats["info_empty_cov"] = (
            unavailable.astype(float)
            .rolling(f"{qfa_window_hours}h", min_periods=minimum)
            .mean()
            .resample("1h")
            .last()
            .reindex(stats.index)
        )
        q_ti = state["subs_all"][sensor_id]["Q_TI"].reindex(stats.index)
        q_gs = gs_scorer.score(stats)
        q_fa, _ = fa_scorer.score(
            stats,
            state["rl_all"][sensor_id],
            allow_response_loss=meta.response_loss_enabled,
        )
        scored = aggregator.aggregate(q_ti, q_gs, q_fa, stats)
        outputs[sensor_id] = scored
    return outputs


def _variant_metrics(
    baseline: pd.DataFrame,
    variant: pd.DataFrame,
    *,
    dimension: str,
    setting: float,
    primary_setting: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = baseline.merge(
        variant,
        on=["timestamp", "sensor_id"],
        suffixes=("_baseline", "_variant"),
        validate="one_to_one",
    )
    base_means = merged.groupby("sensor_id")["D2_total_baseline"].mean()
    variant_means = merged.groupby("sensor_id")["D2_total_variant"].mean()
    rho = float(spearmanr(base_means, variant_means).statistic)
    jaccard = event_jaccard(
        merged["D2_total_baseline"].lt(3.0),
        merged["D2_total_variant"].lt(3.0),
    )
    summary = pd.DataFrame(
        [
            {
                "parameter": dimension,
                "setting": setting,
                "is_primary": setting == primary_setting,
                "channel_rank_spearman": rho,
                "event_jaccard": jaccard,
                "veto_hour_change": int(
                    merged["veto_flag_variant"].sum() - merged["veto_flag_baseline"].sum()
                ),
                "mean_score_change": float(
                    merged["D2_total_variant"].mean() - merged["D2_total_baseline"].mean()
                ),
                "rank_stable": rho >= 0.90,
                "events_stable": jaccard >= 0.75,
                "analysis_unit": "sensor_hour",
            }
        ]
    )
    by_sensor = (
        merged.groupby("sensor_id", as_index=False)
        .agg(
            baseline_mean=("D2_total_baseline", "mean"),
            variant_mean=("D2_total_variant", "mean"),
            baseline_veto_hours=("veto_flag_baseline", "sum"),
            variant_veto_hours=("veto_flag_variant", "sum"),
        )
    )
    by_sensor["parameter"] = dimension
    by_sensor["setting"] = setting
    by_sensor["mean_score_change"] = by_sensor["variant_mean"] - by_sensor["baseline_mean"]
    by_sensor["veto_hour_change"] = (
        by_sensor["variant_veto_hours"] - by_sensor["baseline_veto_hours"]
    )
    return summary, by_sensor


def run_d2_sensitivity(output_dir: Path) -> dict[str, pd.DataFrame]:
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D2"]
    with (D2_ROOT / "artifacts" / "d2_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    load_config, *_ = _load_d2_api()
    cfg = load_config(D2_ROOT / "configs", version="v1")
    baseline = _long_scores(state["all_D2"], "production")

    score_frames = [baseline]
    summary_frames: list[pd.DataFrame] = []
    sensor_frames: list[pd.DataFrame] = []
    variants = []
    for hours in design["qfa_window_hours"]:
        variants.append(("qfa_window_hours", float(hours), {"qfa_window_hours": int(hours)}))
    for minutes in design["hard_rle_minutes"]:
        variants.append(("hard_rle_minutes", float(minutes), {"hard_rle_minutes": int(minutes)}))
    for multiplier in design["gap_break_multipliers"]:
        variants.append(
            ("gap_break_multiplier", float(multiplier), {"gap_break_multiplier": float(multiplier)})
        )
    primary = {
        "qfa_window_hours": float(design["primary_qfa_window_hours"]),
        "hard_rle_minutes": float(design["primary_hard_rle_minutes"]),
        "gap_break_multiplier": 1.0,
    }
    for parameter, setting, override in variants:
        scored = _rescore(state, cfg, **override)
        variant_id = f"{parameter}={setting:g}"
        long = _long_scores(scored, variant_id)
        score_frames.append(long)
        summary, by_sensor = _variant_metrics(
            baseline,
            long,
            dimension=parameter,
            setting=setting,
            primary_setting=primary[parameter],
        )
        summary_frames.append(summary)
        sensor_frames.append(by_sensor)

    scores = pd.concat(score_frames, ignore_index=True)
    summary = pd.concat(summary_frames, ignore_index=True)
    by_sensor = pd.concat(sensor_frames, ignore_index=True)
    reason_migration = (
        scores.assign(veto_reason=scores["veto_reason"].replace("", "none"))
        .groupby(["variant_id", "veto_reason"], as_index=False)
        .size()
        .rename(columns={"size": "sensor_hours"})
    )
    challenge_path = (
        D2_ROOT
        / "artifacts"
        / "data"
        / "D2_process_floor_casebook.xlsx"
    )
    if not challenge_path.exists():
        challenge_path = (
            D2_ROOT
            / "artifacts"
            / "data"
            / "D2_process_floor_validation.xlsx"
        )
    challenges = pd.read_excel(challenge_path, sheet_name=None)
    challenge_summary = pd.concat(
        [frame.assign(sheet=name) for name, frame in challenges.items()],
        ignore_index=True,
        sort=False,
    )
    outputs = {
        "D2_sensitivity_scores": scores,
        "D2_oat_summary": summary,
        "D2_oat_by_sensor": by_sensor,
        "D2_reason_migration": reason_migration,
        "D2_process_floor_challenges": challenge_summary,
        "D2_process_floor_contract_checks": challenges.get(
            "contract_checks",
            pd.DataFrame(),
        ),
        "D2_process_floor_casebook": challenges.get(
            "challenge_timeseries",
            pd.DataFrame(),
        ),
        "D2_process_floor_observed_channels": challenges.get(
            "observed_channels",
            pd.DataFrame(),
        ),
        "D2_process_floor_semantic_contract": challenges.get(
            "semantic_contract",
            pd.DataFrame(),
        ),
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
