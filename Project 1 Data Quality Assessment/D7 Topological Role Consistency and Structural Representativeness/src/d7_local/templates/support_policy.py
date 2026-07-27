from __future__ import annotations

from typing import Any


class SupportPolicy:
    def __init__(self, config: dict[str, Any]) -> None:
        self.thresholds = config["thresholds"]
        self.node_thresholds = config["node_validation"]

    def resolve(
        self,
        n_effective: int,
        distinct_months: int,
        *,
        bootstrap_stability: float,
        holdout_count: int,
        holdout_far: float,
    ) -> str:
        l3 = self.thresholds["L3"]
        if (
            n_effective >= int(l3["min_effective_blocks"])
            and distinct_months >= int(l3["min_distinct_months"])
            and bootstrap_stability >= float(l3["min_bootstrap_stability"])
            and holdout_count >= int(l3["min_blocked_holdouts"])
            and holdout_far <= float(l3["max_holdout_far"])
        ):
            return "L3"
        l2 = self.thresholds["L2"]
        if (
            n_effective >= int(l2["min_effective_blocks"])
            and distinct_months >= int(l2["min_distinct_months"])
        ):
            return "L2"
        if n_effective >= int(self.thresholds["L1"]["min_effective_blocks"]):
            return "L1"
        return "L0"

    def resolve_node(
        self,
        n_effective: int,
        distinct_months: int,
        *,
        reference_coverage: float,
        bootstrap_stability: float,
        holdout_count: int,
        holdout_far: float,
    ) -> str:
        l3 = self.node_thresholds["L3"]
        if (
            n_effective >= int(l3["min_effective_blocks"])
            and distinct_months >= int(l3["min_distinct_months"])
            and reference_coverage >= float(l3["min_reference_coverage"])
            and bootstrap_stability >= float(l3["min_bootstrap_stability"])
            and holdout_count >= int(l3["min_blocked_holdouts"])
            and holdout_far <= float(l3["max_holdout_far"])
        ):
            return "L3"
        l2 = self.node_thresholds["L2"]
        if (
            n_effective >= int(l2["min_effective_blocks"])
            and distinct_months >= int(l2["min_distinct_months"])
            and reference_coverage >= float(l2["min_reference_coverage"])
        ):
            return "L2"
        if n_effective >= int(
            self.node_thresholds["L1"]["min_effective_blocks"]
        ):
            return "L1"
        return "L0"

    @staticmethod
    def minimum_tier(family_level: str, node_level: str) -> str:
        order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
        return min((family_level, node_level), key=order.__getitem__)
