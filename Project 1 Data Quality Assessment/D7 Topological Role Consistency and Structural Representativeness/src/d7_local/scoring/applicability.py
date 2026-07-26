from __future__ import annotations

import numpy as np
import pandas as pd


class ApplicabilityGate:
    def __init__(
        self,
        *,
        research_topology_confirmed: bool,
        deployment_approved: bool,
        minimum_coverage: float = 0.80,
        report_only_coverage: float = 0.60,
        report_eligible_support: tuple[str, ...] | list[str] = ("L2", "L3"),
        score_eligible_support: tuple[str, ...] | list[str] = ("L2", "L3"),
        dqr_eligible_support: tuple[str, ...] | list[str] = ("L2", "L3"),
        action_eligible_support: tuple[str, ...] | list[str] = ("L3",),
    ) -> None:
        self.research_topology_confirmed = bool(research_topology_confirmed)
        self.deployment_approved = bool(deployment_approved)
        self.minimum_coverage = float(minimum_coverage)
        self.report_only_coverage = float(report_only_coverage)
        self.report_eligible_support = tuple(report_eligible_support)
        self.score_eligible_support = tuple(score_eligible_support)
        self.dqr_eligible_support = tuple(dqr_eligible_support)
        self.action_eligible_support = tuple(action_eligible_support)

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
        score_support = output["support_level"].isin(self.score_eligible_support)
        dqr_support = output["support_level"].isin(self.dqr_eligible_support)
        action_support = output["support_level"].isin(self.action_eligible_support)
        limited = ~score_support
        status[report_coverage] = "report_only"
        reason[report_coverage] = "coverage_between_0.60_and_0.80"
        status[~report_support] = "limited_support"
        reason[~report_support] = "template_support_diagnostic_only"
        report_only_support = report_support & ~score_support
        status[report_only_support] = "report_only"
        reason[report_only_support] = "template_support_approved_for_reporting_only"
        score_candidate = ~(
            missing | low_coverage | ood | ~score_support
        )
        if not self.research_topology_confirmed:
            status[score_candidate] = "report_only"
            reason[score_candidate] = "research_topology_confirmation_pending"
        else:
            score_coverage = output["window_coverage"].ge(self.minimum_coverage)
            admitted = score_candidate & score_coverage
            status[admitted] = "evaluable"
            reason[admitted] = (
                "scientific_score_admitted_deployment_governance_independent"
            )
        status[ood] = "out_of_template"
        reason[ood] = "context_posterior_or_ood_gate_failed"
        status[missing | low_coverage] = "not_evaluable"
        reason[missing | low_coverage] = "insufficient_real_spatial_evidence"
        output["evaluation_status"] = status
        output["status_reason"] = reason
        report_coverage_ok = output["window_coverage"].ge(self.report_only_coverage)
        report_ready = report_support & report_coverage_ok & ~missing & ~ood
        score_ready = (
            score_support
            & output["window_coverage"].ge(self.minimum_coverage)
            & ~missing
            & ~ood
            & self.research_topology_confirmed
        )
        dqr_ready = (
            dqr_support
            & output["window_coverage"].ge(self.minimum_coverage)
            & ~missing
            & ~ood
            & self.research_topology_confirmed
        )
        output["report_support_eligible"] = report_support
        output["score_support_eligible"] = score_support
        output["gate_support_eligible"] = dqr_support
        research_report_ready = report_ready & self.research_topology_confirmed
        output["report_eligible"] = research_report_ready
        output["score_eligible"] = score_ready
        output["gate_eligible"] = dqr_ready
        output["action_eligible_candidate"] = action_support & score_ready
        output["limited_support"] = limited
        output["D7_report_provisional"] = output["D7_raw"].where(report_ready)
        output["D7_report"] = output["D7_raw"].where(research_report_ready)
        output["D7_total"] = output["D7_raw"].where(score_ready)
        output["D7_forDQR"] = output["D7_raw"].where(dqr_ready)
        output["deployment_approved"] = self.deployment_approved
        output["veto_eligible"] = False
        output["veto_active"] = False
        output["veto_reason"] = "pending_claim_specific_validation"
        return output
