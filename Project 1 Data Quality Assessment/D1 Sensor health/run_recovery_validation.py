"""Recovery sensitivity and mechanism-level injection validation for D1."""
from __future__ import annotations

import pickle
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.aggregation.cooldown_state_machine import CooldownConfig, run_cooldown_state_machine
from src.aggregation.recovery_metrics import build_episode_table, build_recovery_summary
from src.config.loader import load_project_config


def _variants(base: CooldownConfig) -> dict[str, CooldownConfig]:
    return {
        "A_legacy_gate_corrected_engine": replace(
            base,
            use_w1_hard_gate=True,
            allow_contextual_regime=False,
            min_recovery_streak_h=12,
            max_recovery_window_h=12,
            max_soft_fail_h=0,
            max_missing_h=0,
            max_consecutive_soft_fail_h=0,
            recovery_entry_consecutive_h=1,
            recovery_retry_cooldown_h=0,
            recovered_observation_h=1,
            observation_max_soft_fail_h=0,
            observation_max_missing_h=0,
            observation_max_total_nonpass_h=0,
            observation_max_consecutive_soft_fail_h=0,
            direct_recovery_confirmation_h=1,
        ),
        "B_remove_duplicate_W1": replace(
            base,
            use_w1_hard_gate=False,
            allow_contextual_regime=False,
            min_recovery_streak_h=12,
            max_recovery_window_h=12,
            max_soft_fail_h=0,
            max_missing_h=0,
            max_consecutive_soft_fail_h=0,
            recovery_entry_consecutive_h=1,
            recovery_retry_cooldown_h=0,
            recovered_observation_h=1,
            observation_max_soft_fail_h=0,
            observation_max_missing_h=0,
            observation_max_total_nonpass_h=0,
            observation_max_consecutive_soft_fail_h=0,
            direct_recovery_confirmation_h=1,
        ),
        "C_tolerant_3h_retry12h": base,
        "D_hysteresis_6h_retry24h": replace(
            base,
            recovery_entry_consecutive_h=6,
            recovery_retry_cooldown_h=24,
        ),
    }


def _run_channel(
    channel: str,
    cfg: CooldownConfig,
    subs: dict,
    detectors: dict,
    resid: pd.DataFrame,
    pelt: list,
):
    step_frame = detectors.get("step_confirmed_flag")
    peer_frame = detectors.get("pls_residual_z_hourly")
    return run_cooldown_state_machine(
        sensor_id=channel,
        Q_step=subs["Q_step"][channel],
        Q_regime=subs["Q_regime"][channel],
        Q_drift=subs["Q_drift"][channel],
        Q_freeze=subs["Q_freeze"][channel],
        ks_stat=detectors["ks_statistic_hourly"][channel],
        w1_norm=detectors["w1_normalised_hourly"][channel],
        resid_h=resid[channel],
        pelt_changepoints=pelt,
        step_confirmed=step_frame[channel] if step_frame is not None else None,
        peer_residual_z=peer_frame[channel] if peer_frame is not None else None,
        cfg=cfg,
    )


def _controlled_injection_frame(
    index: pd.DatetimeIndex,
    centre: float,
    scale_floor: float,
    length: int = 180,
):
    """Build a deterministic channel-scaled challenge without outcome leakage."""
    index = index[:length]
    phase = np.arange(length, dtype=float)
    residual = centre + scale_floor * (
        0.18 * np.sin(2 * np.pi * phase / 24)
        + 0.08 * np.cos(2 * np.pi * phase / 11)
    )
    return {
        "Q_step": pd.Series(4.5, index=index),
        "Q_regime": pd.Series(4.5, index=index),
        "Q_drift": pd.Series(4.5, index=index),
        "Q_freeze": pd.Series(4.5, index=index),
        "ks_stat": pd.Series(0.02, index=index),
        "w1_norm": pd.Series(0.20, index=index),
        "resid_h": pd.Series(residual, index=index),
        "step_confirmed": pd.Series(False, index=index),
        "peer_residual_z": pd.Series(
            0.20 * np.sin(2 * np.pi * phase / 19), index=index
        ),
    }


def _inject(template: dict, scenario: str, scale_floor: float):
    data = {name: series.copy() for name, series in template.items()}
    event = 12
    data["step_confirmed"].iloc[event] = True
    data["Q_step"].iloc[event : event + 12] = 1.0
    pelt = []
    if scenario == "transient_step":
        pass
    elif scenario == "stable_new_regime":
        data["Q_regime"].iloc[event:] = 1.0
        data["w1_norm"].iloc[event:] = 3.0
        data["peer_residual_z"].iloc[event:] = 0.0
        data["resid_h"].iloc[event:] += 3.0 * scale_floor
    elif scenario == "persistent_fault":
        data["Q_step"].iloc[event:] = 1.0
        data["resid_h"].iloc[event:] += np.sin(np.arange(len(data["resid_h"]) - event)) * 8 * scale_floor
    elif scenario == "recurrent_independent_step":
        second = 38
        data["step_confirmed"].iloc[second] = True
        data["Q_step"].iloc[second : second + 12] = 1.0
        data["resid_h"].iloc[event:second] += 2.0 * scale_floor
        data["resid_h"].iloc[second:] -= 3.0 * scale_floor
        pelt = [{
            "timestamp": data["resid_h"].index[second],
            "available_at": data["resid_h"].index[second],
            "before_mean": 2.0 * scale_floor,
            "after_mean": -3.0 * scale_floor,
            "magnitude": 5.0 * scale_floor,
        }]
    else:
        raise ValueError(scenario)
    return data, pelt


def _scenario_pass(scenario: str, episodes: pd.DataFrame) -> bool:
    outcomes = episodes["outcome"].tolist()
    if scenario == "transient_step":
        return outcomes == ["direct_recovery"]
    if scenario == "stable_new_regime":
        return outcomes == ["adapted_recovery"]
    if scenario == "persistent_fault":
        return outcomes == ["right_censored"]
    if scenario == "recurrent_independent_step":
        return outcomes == ["superseded", "direct_recovery"]
    return False


def main() -> None:
    cfg = load_project_config()
    base = CooldownConfig.from_dict(cfg.state_machine)
    variants = _variants(base)
    with open(ROOT / "strict_v1_inputs.pkl", "rb") as handle:
        v1 = pickle.load(handle)
    with open(ROOT / "raw_hourly.pkl", "rb") as handle:
        raw = pickle.load(handle)
    with open(ROOT / "v11_state.pkl", "rb") as handle:
        production = pickle.load(handle)
    subs = v1["subs_v1"]
    detectors = v1["detectors"]
    resid = raw["resid_h"]
    channels = production["scored_channels"]
    run_id = production["run_id"]
    algorithm_version = production["algorithm_version"]

    sensitivity_rows = []
    per_channel_rows = []
    for variant_name, variant in variants.items():
        logs = {}
        transitions = []
        for channel in channels:
            scale = production["scale_calibration"][channel]["scale_floor"]
            channel_cfg = replace(
                variant,
                local_scale_floor=1e-3 if variant_name.startswith("A_") else scale,
            )
            _, log, channel_transitions = _run_channel(
                channel, channel_cfg, subs, detectors, resid, production["pelt_results"][channel]
            )
            logs[channel] = log
            transitions.extend(channel_transitions)
        episodes = build_episode_table(transitions, logs)
        summary = build_recovery_summary(episodes, logs)
        overall = summary[summary["sensor_id"] == "Overall"].iloc[0].to_dict()
        overall.update({
            "variant": variant_name,
            "selected_for_production": variant_name.startswith("C_"),
            "run_id": run_id,
            "algorithm_version": algorithm_version,
            "n_transitions": len(transitions),
            "mean_candidate_entries_per_candidate_episode": (
                episodes.loc[episodes["candidate_entry_count"] > 0, "candidate_entry_count"].mean()
                if (episodes["candidate_entry_count"] > 0).any() else np.nan
            ),
        })
        sensitivity_rows.append(overall)
        channel_summary = summary[summary["sensor_id"] != "Overall"].copy()
        channel_summary.insert(0, "variant", variant_name)
        per_channel_rows.append(channel_summary)

    scenarios = [
        "transient_step", "stable_new_regime", "persistent_fault",
        "recurrent_independent_step",
    ]
    injection_rows = []
    for channel in channels:
        scale = production["scale_calibration"][channel]["scale_floor"]
        finite_residual = resid[channel].dropna()
        centre = float(finite_residual.iloc[:720].median())
        template = _controlled_injection_frame(resid.index, centre, scale)
        for variant_name, variant in variants.items():
            channel_cfg = replace(
                variant,
                local_scale_floor=1e-3 if variant_name.startswith("A_") else scale,
            )
            for scenario in scenarios:
                data, pelt = _inject(template, scenario, scale)
                _, log, transitions = run_cooldown_state_machine(
                    sensor_id=channel, pelt_changepoints=pelt, cfg=channel_cfg, **data
                )
                episodes = build_episode_table(transitions, {channel: log})
                injection_rows.append({
                    "variant": variant_name,
                    "selected_for_production": variant_name.startswith("C_"),
                    "run_id": run_id,
                    "algorithm_version": algorithm_version,
                    "sensor_id": channel,
                    "variable": channel.split("_")[0],
                    "scenario": scenario,
                    "scenario_pass": _scenario_pass(scenario, episodes),
                    "observed_outcomes": ";".join(episodes["outcome"].astype(str)),
                    "n_episodes": len(episodes),
                    "n_recovered": int(episodes["recovered"].sum()) if len(episodes) else 0,
                    "median_recovery_h": episodes.loc[
                        episodes["recovered"], "time_to_recovery_h"
                    ].median() if len(episodes) else np.nan,
                    "candidate_attempts": int(episodes["candidate_entry_count"].sum()) if len(episodes) else 0,
                })

    sensitivity = pd.DataFrame(sensitivity_rows)
    per_channel = pd.concat(per_channel_rows, ignore_index=True)
    injections = pd.DataFrame(injection_rows)
    injection_summary = (
        injections.groupby(["variant", "scenario"], as_index=False)
        .agg(
            n_channels=("sensor_id", "nunique"),
            pass_rate=("scenario_pass", "mean"),
            median_recovery_h=("median_recovery_h", "median"),
            mean_candidate_attempts=("candidate_attempts", "mean"),
        )
    )
    config_table = pd.DataFrame([
        {
            "variant": name,
            "selected_for_production": name.startswith("C_"),
            "run_id": run_id,
            "algorithm_version": algorithm_version,
            **asdict(config),
        }
        for name, config in variants.items()
    ])
    metadata = pd.DataFrame([{
        "run_id": run_id,
        "algorithm_version": algorithm_version,
        "natural_data_scope": f"{len(channels)} scored channels",
        "mechanism_challenge_scope": f"{len(channels)} channel-scaled deterministic templates",
        "selected_variant": "C_tolerant_3h_retry12h",
        "selection_rule": (
            "Natural-data sensitivity plus 100% expected-outcome pass across four "
            "mechanism challenges, including no false recovery under persistent fault"
        ),
    }])

    data_dir = ROOT / "outputs" / "data"
    plot_dir = ROOT / "outputs" / "plot_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(data_dir / "D1_recovery_validation.xlsx", engine="openpyxl") as writer:
        sensitivity.to_excel(writer, sheet_name="natural_sensitivity", index=False)
        per_channel.to_excel(writer, sheet_name="per_channel", index=False)
        injections.to_excel(writer, sheet_name="injection_detail", index=False)
        injection_summary.to_excel(writer, sheet_name="injection_summary", index=False)
        config_table.to_excel(writer, sheet_name="variant_config", index=False)
        metadata.to_excel(writer, sheet_name="metadata", index=False)
    sensitivity.to_csv(plot_dir / "D1_recovery_sensitivity.csv", index=False)
    injection_summary.to_csv(plot_dir / "D1_recovery_injection_summary.csv", index=False)
    print(sensitivity[[
        "variant", "event_recovery_rate", "candidate_attempt_count",
        "candidate_attempt_confirmation_rate", "n_transitions",
        "mean_candidate_entries_per_candidate_episode",
    ]].to_string(index=False))
    print("\nInjection pass rates")
    print(injection_summary.pivot(index="variant", columns="scenario", values="pass_rate").to_string())


if __name__ == "__main__":
    main()
