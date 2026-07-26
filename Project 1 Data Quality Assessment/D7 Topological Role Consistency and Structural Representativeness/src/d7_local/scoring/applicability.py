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
        report_eligible_support: tuple[str, ...] | list[str] = ("L2", "L3"),
        gate_eligible_support: tuple[str, ...] | list[str] = ("L3",),
        veto_eligible_support: tuple[str, ...] | list[str] = ("L3",),
    ) -> None:
        self.topology_verified = bool(topology_verified)
        self.minimum_coverage = float(minimum_coverage)
        self.report_only_coverage = float(report_only_coverage)
        self.report_eligible_support = tuple(report_eligible_support)
        self.gate_eligible_support = tuple(gate_eligible_support)
        self.veto_eligible_support = tuple(veto_eligible_support)

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
        report_support = output["support_level"].isin(self.report_eligible_support)
        gate_support = output["support_level"].isin(self.gate_eligible_support)
        limited = ~gate_support
        status[report_coverage] = "report_only"
        reason[report_coverage] = "coverage_between_0.60_and_0.80"
        status[~report_support] = "limited_support"
        reason[~report_support] = "template_support_diagnostic_only"
        report_only_support = report_support & ~gate_support
        status[report_only_support] = "report_only"
        reason[report_only_support] = "template_support_approved_for_reporting_only"
        if not self.topology_verified:
            topology_mask = ~(missing | low_coverage | ood | ~report_support)
            status[topology_mask] = "report_only"
            reason[topology_mask] = "topology_pending_field_verification"
        status[ood] = "out_of_template"
        reason[ood] = "context_posterior_or_ood_gate_failed"
        status[missing | low_coverage] = "not_evaluable"
        reason[missing | low_coverage] = "insufficient_real_spatial_evidence"
        output["evaluation_status"] = status
        output["status_reason"] = reason
        report_coverage_ok = output["window_coverage"].ge(self.report_only_coverage)
        report_ready = report_support & report_coverage_ok & ~missing & ~ood
        gate_ready = (
            gate_support
            & output["window_coverage"].ge(self.minimum_coverage)
            & ~missing
            & ~ood
            & self.topology_verified
        )
        output["report_support_eligible"] = report_support
        output["gate_support_eligible"] = gate_support
        output["report_eligible"] = report_ready
        output["gate_eligible"] = gate_ready
        output["limited_support"] = limited
        output["D7_report_provisional"] = output["D7_raw"].where(report_ready)
        output["D7_report"] = (
            output["D7_report_provisional"] if self.topology_verified else np.nan
        )
        output["D7_total"] = output["D7_raw"].where(output["evaluation_status"].eq("evaluable"))
        output["D7_forDQR"] = output["D7_total"]
        output["veto_eligible"] = (
            output["support_level"].isin(self.veto_eligible_support)
            & self.topology_verified
            & output["evaluation_status"].eq("evaluable")
        )
        output["veto_active"] = False
        output["veto_reason"] = np.where(
            output["veto_eligible"], "not_triggered", "ineligible_by_contract"
        )
        return output
