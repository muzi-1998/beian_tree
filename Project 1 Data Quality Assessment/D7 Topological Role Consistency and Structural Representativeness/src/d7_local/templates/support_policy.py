from __future__ import annotations


class SupportPolicy:
    def resolve(self, n_effective: int, distinct_months: int) -> str:
        if n_effective >= 100 and distinct_months >= 3:
            return "L3"
        if n_effective >= 50 and distinct_months >= 2:
            return "L2"
        if n_effective >= 20:
            return "L1"
        return "L0"
