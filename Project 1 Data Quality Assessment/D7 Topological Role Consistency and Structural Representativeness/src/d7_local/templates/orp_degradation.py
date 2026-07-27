from __future__ import annotations


class ORPPolicyViolation(RuntimeError):
    pass


class ORPDegradationPolicy:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    def resolve_mode(self, support_level: str) -> tuple[str, float]:
        if self.config.get("force_diagonal_robust_model", True):
            return "diagonal_robust_z", float(self.config["alpha_l1"])
        if support_level == "L3":
            return "full_shrinkage", 0.0
        if support_level == "L2":
            return "pooled_shrinkage", float(self.config["alpha_floor_l2"])
        if support_level == "L1":
            return "diagonal_robust_z", 1.0
        return "disabled", 1.0

    def enforce(self, mode: str, alpha: float, covariance_offdiag_max: float) -> None:
        if mode == "diagonal_robust_z" and covariance_offdiag_max > 1e-10:
            raise ORPPolicyViolation("ORP diagonal mode contains non-diagonal covariance")
        if mode == "pooled_shrinkage" and alpha < 0.50:
            raise ORPPolicyViolation("ORP L2 shrinkage alpha is below 0.50")
