"""Aggregate D3 evidence without consuming D1 or D2 scores."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd

from src.d3_physical.scorer import SubScores


@dataclass(frozen=True)
class D3Result:
    ts: pd.Timestamp
    sensor: str
    sensor_type: str
    Q_value_hard: float
    Q_value_soft: float
    Q_persistent_rate: float
    Q_persistent_rate_soft_only: float
    Q_persistent_rate_hard: float
    D3_base: float
    D3_pre: float
    D3_total: float
    evidence_status: str
    n_expected: int
    n_observed: int
    observed_fraction: float
    veto_flag: bool
    veto_reason: str
    data_veto_flag: bool
    operational_warning_flag: bool
    D3_gate_status: str
    process_coherent_shock: bool
    usable_tag: str
    dominant_physical_issue: str

    @property
    def Q_rate(self) -> float:
        """Backward-compatible alias; the scientific construct is persistent rate."""
        return self.Q_persistent_rate


class D3Aggregator:
    def __init__(self, rules_cfg: dict, mapping_cfg: dict):
        self.rules = rules_cfg
        self.mapping = mapping_cfg
        weights = mapping_cfg["aggregation"]["weights"]
        if not np.isclose(sum(weights.values()), 1.0):
            raise ValueError("D3 aggregation weights must sum to 1.0")

    def aggregate(
        self,
        ts,
        sensor,
        sensor_type,
        sub: SubScores,
        value_evidence,
        rate_evidence,
        expected_samples: int,
    ) -> D3Result:
        n_observed = int(value_evidence.n_samples)
        observed_fraction = n_observed / max(expected_samples, 1)
        evidence_cfg = self.rules["evidence"]
        required = max(
            int(evidence_cfg["min_observations"]),
            ceil(float(evidence_cfg["min_observed_fraction"]) * expected_samples),
        )
        sufficient = n_observed >= required and rate_evidence.n_samples >= max(required - 1, 1)

        if not sufficient:
            return D3Result(
                ts=ts,
                sensor=sensor,
                sensor_type=sensor_type,
                Q_value_hard=float("nan"),
                Q_value_soft=float("nan"),
                Q_persistent_rate=float("nan"),
                Q_persistent_rate_soft_only=float("nan"),
                Q_persistent_rate_hard=float("nan"),
                D3_base=float("nan"),
                D3_pre=float("nan"),
                D3_total=float("nan"),
                evidence_status="insufficient",
                n_expected=int(expected_samples),
                n_observed=n_observed,
                observed_fraction=float(observed_fraction),
                veto_flag=False,
                veto_reason="",
                data_veto_flag=False,
                operational_warning_flag=False,
                D3_gate_status="NotEvaluated",
                process_coherent_shock=bool(rate_evidence.shock_candidate),
                usable_tag="not_evaluated",
                dominant_physical_issue="insufficient_evidence",
            )

        subscore_values = np.array(
            [sub.Q_value_hard, sub.Q_value_soft, sub.Q_persistent_rate], dtype=float
        )
        if not np.isfinite(subscore_values).all():
            data_veto = bool(value_evidence.out_of_instrument)
            known_hard_warning = bool(value_evidence.hard_violation_rate > 0)
            known_rate_warning = bool(
                rate_evidence.rate_hard_violation_rate > 0
                or rate_evidence.rate_soft_violation_rate > 0
            )
            if data_veto:
                gate_status, usable = "Fail", "invalid"
                dominant = "instrument_range"
            elif known_hard_warning or known_rate_warning:
                gate_status, usable = "Warn", "review_only"
                dominant = "hard_bound" if known_hard_warning else "persistent_rate"
            else:
                gate_status, usable = "NotEvaluated", "not_evaluated"
                dominant = "context_unavailable"
            return D3Result(
                ts=ts,
                sensor=sensor,
                sensor_type=sensor_type,
                Q_value_hard=float(sub.Q_value_hard),
                Q_value_soft=float(sub.Q_value_soft),
                Q_persistent_rate=float(sub.Q_persistent_rate),
                Q_persistent_rate_soft_only=float(sub.Q_persistent_rate_soft_only),
                Q_persistent_rate_hard=float(sub.Q_persistent_rate_hard),
                D3_base=float("nan"),
                D3_pre=float("nan"),
                D3_total=float("nan"),
                evidence_status="context_unavailable",
                n_expected=int(expected_samples),
                n_observed=n_observed,
                observed_fraction=float(observed_fraction),
                veto_flag=data_veto,
                veto_reason="instrument_range" if data_veto else "",
                data_veto_flag=data_veto,
                operational_warning_flag=known_hard_warning or known_rate_warning,
                D3_gate_status=gate_status,
                process_coherent_shock=bool(rate_evidence.shock_candidate),
                usable_tag=usable,
                dominant_physical_issue=dominant,
            )

        w = self.mapping["aggregation"]["weights"]
        values = {
            "Q_value_hard": sub.Q_value_hard,
            "Q_value_soft": sub.Q_value_soft,
            "Q_persistent_rate": sub.Q_persistent_rate,
        }
        base = sum(w[name] * values[name] for name in w)
        lam = float(self.mapping["aggregation"]["lambda_base"])
        pre = lam * base + (1.0 - lam) * min(values.values())

        veto_flag = False
        veto_reasons = []
        v1 = self.rules["veto"]["veto_1"]
        if (
            value_evidence.hard_violation_rate > v1["trigger"]["hard_violation_rate_gt"]
            or value_evidence.consecutive_hard_max_min > v1["trigger"]["OR_consecutive_min_gt"]
        ):
            pre = min(pre, float(v1["cap"]))
            veto_flag = True
            veto_reasons.append("hard_violation")

        v2 = self.rules["veto"]["veto_2"]
        if value_evidence.out_of_instrument:
            pre = min(pre, float(v2["cap"]))
            veto_flag = True
            veto_reasons.append("instrument_range")

        v3 = self.rules["veto"]["veto_3"]
        if rate_evidence.rate_hard_consec_max_min > v3["trigger"]["rate_hard_violation_min_gt"]:
            pre = min(pre, float(v3["cap"]))
            veto_flag = True
            veto_reasons.append("persistent_rate")

        total = float(np.clip(pre, 1.0, 5.0))
        data_veto = bool(value_evidence.out_of_instrument)
        operational_warning = bool(
            value_evidence.hard_violation_rate > 0
            or value_evidence.soft_violation_rate > 0
            or rate_evidence.rate_hard_violation_rate > 0
            or rate_evidence.rate_soft_violation_rate > 0
        )
        if data_veto:
            usable = "invalid"
            gate_status = "Fail"
        elif value_evidence.hard_violation_rate > 0 or "persistent_rate" in veto_reasons:
            usable = "review_only"
            gate_status = "Warn"
        elif operational_warning:
            usable = "train_ok_with_operational_warning"
            gate_status = "Warn"
        else:
            usable = "train_ok"
            gate_status = "Pass"

        risks = {
            "hard_bound": value_evidence.hard_violation_rate,
            "soft_bound": value_evidence.soft_violation_rate,
            "persistent_rate": (
                0.3 * rate_evidence.rate_soft_only_violation_rate
                + 0.7 * rate_evidence.rate_hard_violation_rate
            ),
        }
        dominant = max(risks, key=risks.get)
        if risks[dominant] < 0.005:
            dominant = "none"

        return D3Result(
            ts=ts,
            sensor=sensor,
            sensor_type=sensor_type,
            Q_value_hard=float(sub.Q_value_hard),
            Q_value_soft=float(sub.Q_value_soft),
            Q_persistent_rate=float(sub.Q_persistent_rate),
            Q_persistent_rate_soft_only=float(sub.Q_persistent_rate_soft_only),
            Q_persistent_rate_hard=float(sub.Q_persistent_rate_hard),
            D3_base=float(base),
            D3_pre=float(pre),
            D3_total=total,
            evidence_status="sufficient",
            n_expected=int(expected_samples),
            n_observed=n_observed,
            observed_fraction=float(observed_fraction),
            veto_flag=veto_flag,
            veto_reason=";".join(veto_reasons),
            data_veto_flag=data_veto,
            operational_warning_flag=operational_warning,
            D3_gate_status=gate_status,
            process_coherent_shock=bool(rate_evidence.shock_candidate),
            usable_tag=usable,
            dominant_physical_issue=dominant,
        )
