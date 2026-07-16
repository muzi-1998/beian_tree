from __future__ import annotations

import numpy as np
import pandas as pd


class ApplicabilityGate:
    def __init__(
        self,
        *,
        topology_verified: bool,
        minimum_coverage: float = 0.80,
        report_only_coverage: float = 0.60,
    ) -> None:
        self.topology_verified = bool(topology_verified)
        self.minimum_coverage = float(minimum_coverage)
        self.report_only_coverage = float(report_only_coverage)

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        required_scores = output[["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]]
        status = np.full(len(output), "evaluable", dtype=object)
        reason = np.full(len(output), "all_contracts_passed", dtype=object)
        missing = required_scores.isna().any(axis=1) | output["D7_raw"].isna()
        low_coverage = output["window_coverage"] < self.report_only_coverage
        report_coverage = output["window_coverage"].between(
            self.report_only_coverage, self.minimum_coverage, inclusive="left"
        )
        ood = output["regime_state"].eq("OODHold")
        limited = output["support_level"].isin(["L1", "L2"])
        status[report_coverage] = "report_only"
        reason[report_coverage] = "coverage_between_0.60_and_0.80"
        status[limited] = "limited_support"
        reason[limited] = "template_support_not_approved_for_gating"
        if not self.topology_verified:
            topology_mask = ~(missing | low_coverage | ood | limited)
            status[topology_mask] = "report_only"
            reason[topology_mask] = "topology_pending_field_verification"
        status[ood] = "out_of_template"
        reason[ood] = "context_posterior_or_ood_gate_failed"
        status[missing | low_coverage] = "not_evaluable"
        reason[missing | low_coverage] = "insufficient_real_spatial_evidence"
        output["evaluation_status"] = status
        output["status_reason"] = reason
        output["D7_total"] = output["D7_raw"].where(output["evaluation_status"].eq("evaluable"))
        output["D7_forDQR"] = output["D7_total"]
        output["veto_eligible"] = (
            output["support_level"].isin(["L2", "L3"])
            & self.topology_verified
            & output["evaluation_status"].eq("evaluable")
        )
        output["veto_active"] = False
        output["veto_reason"] = np.where(
            output["veto_eligible"], "not_triggered", "ineligible_by_contract"
        )
        return output
