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
    Q_rate: float
    D3_base: float
    D3_pre: float
    D3_total: float
    evidence_status: str
    n_expected: int
    n_observed: int
    observed_fraction: float
    veto_flag: bool
    veto_reason: str
    process_coherent_shock: bool
    usable_tag: str
    dominant_physical_issue: str


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
                Q_rate=float("nan"),
                D3_base=float("nan"),
                D3_pre=float("nan"),
                D3_total=float("nan"),
                evidence_status="insufficient",
                n_expected=int(expected_samples),
                n_observed=n_observed,
                observed_fraction=float(observed_fraction),
                veto_flag=False,
                veto_reason="",
                process_coherent_shock=bool(rate_evidence.shock_candidate),
                usable_tag="not_evaluated",
                dominant_physical_issue="insufficient_evidence",
            )

        w = self.mapping["aggregation"]["weights"]
        values = {
            "Q_value_hard": sub.Q_value_hard,
            "Q_value_soft": sub.Q_value_soft,
            "Q_rate": sub.Q_rate,
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
            veto_reasons.append("rate_persistent")

        total = float(np.clip(pre, 1.0, 5.0))
        ut = self.rules["usable_tag_rules"]
        if value_evidence.out_of_instrument or total < ut["invalid_caps_below"]:
            usable = "invalid"
        elif total < ut["review_only_below"]:
            usable = "review_only"
        elif total < ut["report_only_below"]:
            usable = "report_only"
        else:
            usable = "train_ok"

        risks = {
            "hard_bound": value_evidence.hard_violation_rate,
            "soft_bound": value_evidence.soft_violation_rate,
            "rate": rate_evidence.rate_hard_violation_rate,
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
            Q_rate=float(sub.Q_rate),
            D3_base=float(base),
            D3_pre=float(pre),
            D3_total=total,
            evidence_status="sufficient",
            n_expected=int(expected_samples),
            n_observed=n_observed,
            observed_fraction=float(observed_fraction),
            veto_flag=veto_flag,
            veto_reason=";".join(veto_reasons),
            process_coherent_shock=bool(rate_evidence.shock_candidate),
            usable_tag=usable,
            dominant_physical_issue=dominant,
        )
