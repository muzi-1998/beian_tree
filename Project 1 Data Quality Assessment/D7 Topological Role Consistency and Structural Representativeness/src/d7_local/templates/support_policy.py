from __future__ import annotations

from typing import Any


class SupportPolicy:
    def __init__(self, config: dict[str, Any]) -> None:
        self.thresholds = config["thresholds"]

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
