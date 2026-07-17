from __future__ import annotations

import numpy as np
import pandas as pd

from src.aggregation.cooldown_state_machine import CooldownConfig, run_cooldown_state_machine


def _inputs(n: int = 40):
    index = pd.date_range("2025-01-01", periods=n, freq="h")
    high = pd.Series(5.0, index=index)
    zeros = pd.Series(0.0, index=index)
    return {
        "index": index,
        "Q_step": high.copy(),
        "Q_regime": high.copy(),
        "Q_drift": pd.Series(4.0, index=index),
        "Q_freeze": high.copy(),
        "ks_stat": zeros.copy(),
        "w1_norm": pd.Series(0.5, index=index),
        "resid_h": zeros.copy(),
        "step_confirmed": pd.Series(False, index=index),
        "peer_residual_z": zeros.copy(),
    }


def _cfg(**overrides):
    values = dict(
        step_refractory_h=3,
        regime_refractory_h=3,
        min_event_separation_h=2,
        stable_window_h=4,
        max_baseline_pending_h=12,
        min_recovery_streak_h=3,
        max_recovery_window_h=5,
        max_soft_fail_h=1,
        max_missing_h=1,
        recovered_observation_h=3,
        observation_max_soft_fail_h=1,
        observation_max_missing_h=1,
        observation_max_total_nonpass_h=1,
        local_scale_floor=0.1,
    )
    values.update(overrides)
    return CooldownConfig(**values)


def _run(data, pelt=None, cfg=None):
    kwargs = {key: value for key, value in data.items() if key != "index"}
    return run_cooldown_state_machine(
        sensor_id="DO_1_1",
        pelt_changepoints=pelt or [],
        cfg=cfg or _cfg(),
        **kwargs,
    )


def test_direct_recovery_is_an_event_outcome_not_recovered_occupancy():
    data = _inputs()
    data["step_confirmed"].iloc[1] = True
    _, log, transitions = _run(data)
    direct = [row for row in transitions if row.get("episode_outcome") == "direct_recovery"]
    assert len(direct) == 1
    assert direct[0]["direct_confirmation_h"] == 6
    assert direct[0]["ts"] == data["index"][9]
    assert not log["state_name"].eq("Recovered").any()


def test_missing_stable_window_remains_baseline_pending():
    data = _inputs(20)
    data["step_confirmed"].iloc[1] = True
    data["Q_regime"].iloc[1:] = 1.0
    data["resid_h"].iloc[4:10] = np.nan
    _, log, transitions = _run(data)
    assert log.loc[data["index"][4], "state_name"] == "BaselinePending"
    early = [row for row in transitions if row["to_state"] == "SustainedAnomaly" and row["ts"] <= data["index"][7]]
    assert early == []


def test_contextual_regime_recovery_tolerates_one_soft_failure_and_observes():
    data = _inputs()
    data["step_confirmed"].iloc[1] = True
    data["Q_regime"].iloc[1:] = 1.0
    data["Q_step"].iloc[9] = 2.5
    _, log, transitions = _run(data)
    adapted = [row for row in transitions if row.get("episode_outcome") == "adapted_recovery"]
    assert len(adapted) == 1
    recovered_run = log["state_name"].eq("Recovered")
    assert recovered_run.sum() == 3
    assert adapted[0]["used_contextual_regime"]
    assert log.iloc[-1]["state_name"] == "Normal"
    assert log.iloc[-1]["accepted_contextual_regime"]


def test_same_active_event_cannot_reset_without_new_pelt_segment():
    data = _inputs(20)
    data["step_confirmed"].iloc[[1, 5]] = True
    data["resid_h"].iloc[1] = 1.0
    data["resid_h"].iloc[5] = 3.0
    _, _, no_pelt_transitions = _run(data, cfg=_cfg(step_refractory_h=10))
    no_pelt_starts = [row for row in no_pelt_transitions if row["to_state"] == "Refractory"]
    assert len(no_pelt_starts) == 1

    pelt = [{
        "timestamp": data["index"][5],
        "available_at": data["index"][5],
        "before_mean": 0.0,
        "after_mean": 3.0,
        "magnitude": 3.0,
    }]
    _, _, with_pelt_transitions = _run(data, pelt=pelt, cfg=_cfg(step_refractory_h=10))
    with_pelt_starts = [row for row in with_pelt_transitions if row["to_state"] == "Refractory"]
    assert len(with_pelt_starts) == 2
    assert with_pelt_starts[-1]["pelt_segment_id"].startswith("pelt_")
