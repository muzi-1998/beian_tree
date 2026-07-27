from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class _State:
    active_regime: int
    candidate_regime: int | None = None
    confirm_elapsed_min: int = 0
    refractory_until: pd.Timestamp | None = None


class RegimeHysteresisController:
    def __init__(self, config: dict[str, float | int]) -> None:
        self.delta = float(config["delta_p_switch"])
        self.p_enter = float(config["p_enter"])
        self.entropy_max = float(config["entropy_max"])
        self.confirm_minutes = int(config["confirm_minutes"])
        self.refractory_minutes = int(config["refractory_minutes"])

    def replay(
        self,
        index: pd.DatetimeIndex,
        probabilities: np.ndarray,
        entropy: np.ndarray,
        ood_distance: np.ndarray,
        ood_threshold: float,
        sensor_id: str,
        snapshot_minutes: int,
    ) -> pd.DataFrame:
        first = int(np.argmax(probabilities[0]))
        state = _State(active_regime=first)
        rows: list[dict[str, object]] = []
        transition_no = 0
        for i, timestamp in enumerate(index):
            map_regime = int(np.argmax(probabilities[i]))
            map_probability = float(probabilities[i, map_regime])
            active_probability = float(probabilities[i, state.active_regime])
            gap = map_probability - active_probability
            ood = (
                map_probability < self.p_enter
                or float(entropy[i]) > self.entropy_max
                or float(ood_distance[i]) > ood_threshold
            )
            transition_id = None
            transition_pending = False
            from_regime = state.active_regime
            regime_state = "Locked"
            if ood:
                state.candidate_regime = None
                state.confirm_elapsed_min = 0
                regime_state = "OODHold"
            elif state.refractory_until is not None and timestamp < state.refractory_until:
                state.candidate_regime = None
                state.confirm_elapsed_min = 0
            elif map_regime != state.active_regime and gap > self.delta:
                transition_pending = True
                regime_state = "SwitchCandidate"
                if state.candidate_regime == map_regime:
                    state.confirm_elapsed_min += snapshot_minutes
                else:
                    state.candidate_regime = map_regime
                    state.confirm_elapsed_min = snapshot_minutes
                if state.confirm_elapsed_min >= self.confirm_minutes:
                    transition_no += 1
                    transition_id = f"D5-REG-{sensor_id}-{transition_no:04d}"
                    state.active_regime = map_regime
                    state.candidate_regime = None
                    state.confirm_elapsed_min = 0
                    state.refractory_until = timestamp + pd.Timedelta(minutes=self.refractory_minutes)
                    regime_state = "ActiveNew"
                    transition_pending = False
            else:
                state.candidate_regime = None
                state.confirm_elapsed_min = 0
            rows.append(
                {
                    "timestamp": timestamp,
                    "sensor_id": sensor_id,
                    "posterior_vector": probabilities[i].tolist(),
                    "map_regime_id": map_regime,
                    "map_probability": map_probability,
                    "active_regime_id": state.active_regime,
                    "posterior_gap": gap,
                    "normalized_entropy": float(entropy[i]),
                    "ood_distance": float(ood_distance[i]),
                    "ood_threshold": float(ood_threshold),
                    "regime_state": regime_state,
                    "candidate_regime": state.candidate_regime,
                    "confirm_elapsed_min": state.confirm_elapsed_min,
                    "confirm_required_min": self.confirm_minutes,
                    "refractory_until": state.refractory_until,
                    "transition_id": transition_id,
                    "from_regime": from_regime if transition_id else np.nan,
                    "to_regime": state.active_regime if transition_id else np.nan,
                    "transition_pending": transition_pending,
                }
            )
        return pd.DataFrame(rows)
