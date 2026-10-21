"""Validate design invariants without reading or modifying raw observations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
import math


@dataclass
class DesignCheck:
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_design(
    study: dict[str, Any], contracts: dict[str, Any], root: Path,
    *, check_paths: bool = True, protocol: dict[str, Any] | None = None,
    candidates: dict[str, Any] | None = None,
) -> DesignCheck:
    result = DesignCheck()
    if study.get("status") not in {"research_design_algorithms_pending", "intake_and_archive_diagnostics_only"}:
        result.errors.append("Status must explicitly declare the limited execution scope.")
    if study.get("ready_for_model_execution") is not False:
        result.errors.append("Model execution must remain disabled until scientific admission.")
    if study.get("flow_semantics") != "instantaneous_flow" or study.get("flow_unit") != "m3/h":
        result.errors.append("Q must be instantaneous flow in m3/h, never a cumulative counter.")

    splits: dict[str, tuple[date, date]] = {}
    try:
        target = study["target_period"]
        start, end = date.fromisoformat(target["start"]), date.fromisoformat(target["end"])
        for item in study["splits"]:
            name = item["id"]
            left, right = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
            if name in splits or not start <= left <= right <= end:
                result.errors.append(f"Invalid/duplicate split or target range: {name}")
            splits[name] = (left, right)
        ordered = sorted(splits.items(), key=lambda item: item[1][0])
        if not ordered or ordered[0][1][0] != start or ordered[-1][1][1] != end:
            result.errors.append("Splits must span the target calendar period.")
        for (a, (_, ar)), (b, (bl, _)) in zip(ordered, ordered[1:]):
            if bl <= ar:
                result.errors.append(f"Overlapping splits: {a}, {b}")
            elif bl != ar + timedelta(days=1):
                result.errors.append(f"Unspecified calendar gap between splits: {a}, {b}")
        observed_end = date.fromisoformat(study["observed_high_frequency_period"]["end"])
        if observed_end < end:
            result.notes.append(f"Observed high-frequency data end at {observed_end}; target ends at {end}.")
    except (KeyError, TypeError, ValueError) as exc:
        result.errors.append(f"Malformed period/split definition: {exc}")

    fit_ids = study.get("fit_split_ids", [])
    selection_ids = study.get("model_selection_split_ids", [])
    if fit_ids != ["development"] or selection_ids != ["validation"]:
        result.errors.append("Fitting is restricted to development; selection to validation.")
    if not {"development", "validation", "terminal_test"}.issubset(splits):
        result.errors.append("Development, validation and terminal_test splits are required.")
    if not study.get("freeze_before_terminal_test"):
        result.errors.append("Freeze choices before opening terminal_test.")
    if study.get("acceptance_thresholds_status") != "pending_development_freeze":
        result.errors.append("Scientific thresholds are pending, not passed or already validated.")
    result.notes.append("Scientific acceptance thresholds are pending; no model/metric pass is claimed.")
    _validate_final_protocol(study, protocol, candidates, result)

    external = contracts.get("external_inputs", {})
    if check_paths:
        for name, item in external.items():
            rel = item.get("path")
            if item.get("required_now") and (not rel or not (root / rel).resolve().exists()):
                result.errors.append(f"Required design input path missing: {name}")
    modules = contracts.get("modules", [])
    seen_stages: set[str] = set()
    seen_outputs: set[str] = set()
    seen_paths: set[str] = set()
    for module in modules:
        mid = module.get("id", "")
        if not mid or mid in seen_stages:
            result.errors.append(f"Missing/duplicate module id: {mid}")
        implementation = module.get("implementation_status")
        if implementation not in {"not_implemented", "implemented", "diagnostics_only"}:
            result.errors.append(f"Unknown implementation status: {mid}")
        if implementation != "not_implemented":
            entry = module.get("implementation_entry")
            if not entry or (check_paths and not (root / entry).is_file()):
                result.errors.append(f"Implemented module has no existing entry: {mid}")
        if not module.get("gates") or not module.get("outputs"):
            result.errors.append(f"Missing quality gates or planned outputs: {mid}")
        for dep in module.get("depends_on", []):
            if dep not in seen_stages:
                result.errors.append(f"Forward/cyclic/unknown dependency {mid} -> {dep}")
        for inp in module.get("inputs", []):
            if inp.startswith("external:"):
                if inp.split(":", 1)[1] not in external:
                    result.errors.append(f"Unknown external input: {inp}")
            elif inp not in seen_outputs:
                result.errors.append(f"Input has no earlier producer: {mid}/{inp}")
        for out in module.get("outputs", []):
            oid, rel = out.get("id", ""), out.get("path", "")
            path = PurePosixPath(rel)
            if not oid or oid in seen_outputs:
                result.errors.append(f"Missing/duplicate artifact id: {oid}")
            if not rel or path.is_absolute() or ".." in path.parts or "\\" in rel or ":" in rel:
                result.errors.append(f"Output path escapes/violates artifact namespace: {rel}")
            key = rel.casefold()
            if key in seen_paths:
                result.errors.append(f"Duplicate output path: {rel}")
            seen_paths.add(key)
            seen_outputs.add(oid)
        seen_stages.add(mid)
    if len(modules) != 12:
        result.errors.append("Expected the twelve declared research modules M01–M12.")
    return result


def _validate_final_protocol(
    study: dict[str, Any], protocol: dict[str, Any] | None,
    candidates: dict[str, Any] | None, result: DesignCheck,
) -> None:
    """Reject design choices that would invalidate the planned research contrasts."""
    if set(study.get("candidate_steps_minutes", [])) != {5, 15, 60}:
        result.errors.append("Scale screening must start from 5/15/60 min after native-frequency audit.")
    if study.get("priority_candidate_step_minutes") is not None:
        result.errors.append("Do not preselect 5 min or automatically fall back to 1 min.")
    if study.get("main_step_minutes") == 1:
        admission = study.get("one_minute_model_admission", {})
        if any(admission.get(key) != "passed" for key in ("native_information_status", "coarser_loss_status")):
            result.errors.append("1 min modelling requires both native information and coarser-loss admission.")
    views = study.get("concentration_views", {})
    if set(views.get("saved", [])) != {"time_weighted", "flow_weighted"}:
        result.errors.append("Both concentration views must be retained.")
    if views.get("primary_model") != "flow_weighted" or views.get("sumo_boundary") != "flow_weighted":
        result.errors.append("The declared primary generator and SUMO boundary must use the same flow-weighted view.")
    if views.get("load_identity_requires_common_support") is not True:
        result.errors.append("Load identity requires common Q/concentration time support.")
    if not protocol or not candidates:
        result.errors.append("Final design requires experiment_protocol and model_candidates inputs.")
        return
    try:
        tiers = protocol["evt_tiers"]
        if (tiers["threshold_research"]["decision"] != "only_if_GPD_materially_changes_primary_conclusion"
                or tiers["extension"]["enabled_in_mainline"] is not False):
            result.errors.append("EQD research is conditional; extended EVT is excluded from the mainline.")
        if tiers["tail_mass_population"] != "same_all_time_innovation_population; event_peak_is_separate":
            result.errors.append("All-time tail mass cannot be replaced by event-peak mass.")
        if protocol["terminal_test_can_select"] is not False:
            result.errors.append("Terminal test cannot select thresholds, ratios or candidates.")
        e2 = protocol["experiments"]["E2"]
        metrics = e2["matching_metrics"]
        metric_ids = [m["id"] for m in metrics]
        required = {"concentration_quantiles", "sync_tau", "sync_joint_exceedance", "daily_volume",
                    "daily_COD_load", "daily_TN_load", "event_amplitude"}
        if len(set(metric_ids)) != len(metric_ids) or not required.issubset(metric_ids):
            result.errors.append("Input matching needs unique concentration/joint/volume/load/amplitude gates.")
        if set(metric_ids) & set(e2["manipulated_metric_ids"]):
            result.errors.append("A metric cannot be both matched and manipulated in the same E2 contrast.")
        for metric in metrics:
            proposal = metric.get("pilot_proposal")
            if isinstance(proposal, bool) or not isinstance(proposal, (int, float)) or not math.isfinite(proposal) or proposal <= 0:
                result.errors.append(f"Invalid pilot tolerance: {metric['id']}")
            if metric.get("status") == "passed" and (not protocol["frozen"] or metric.get("final_tolerance") is None):
                result.errors.append("An unfrozen/null matching tolerance cannot be marked passed.")
        if (e2["primary_control_mode"] != "same_policy"
                or e2["primary_response_metric_kind"] != "simulation_to_simulation"):
            result.errors.append("Paired responses require the same policy and a simulation-to-simulation estimand.")
        if (any(e2[key] is not True for key in ("same_theta", "same_process_and_controller_initial_state", "same_warmup"))
                or e2.get("warmup_protocol") != "common_reference_input_then_clone_process_and_controller_snapshot_at_intervention_start"):
            result.errors.append("Controlled response pairs require common warmup and cloned process/controller initial states.")
        if e2["synthetic_input_vs_field_kind"] != "scenario_departure_not_prediction_error":
            result.errors.append("Synthetic-input response versus field TN is not a prediction error against its own truth.")
        if e2["candidate_selection_uses_response_or_field_TN"] is not False:
            result.errors.append("Input-pair matching cannot select candidates using response or field TN.")
        e3 = protocol["experiments"]["E3"]
        if (e3["ratio_selection_split"] != "validation" or e3["source_selection_split"] != "validation"
                or e3["freeze_selection_rule_before_test"] is not True):
            result.errors.append("E3 source/ratio selection must be frozen from validation before terminal test.")
        ratios = e3["ratio_candidates"]
        if not ratios or 0 not in ratios or any(isinstance(x, bool) or not isinstance(x, (int, float))
                or not math.isfinite(x) or x < 0 for x in ratios):
            result.errors.append("E3 needs finite non-negative ratios and a real-only zero-ratio baseline.")
        if "Student_t" not in candidates["dependence"]["baseline"]:
            result.errors.append("The declared minimal dependence baselines include Gaussian and Student t.")
    except (KeyError, TypeError, ValueError) as exc:
        result.errors.append(f"Malformed final experiment protocol: {exc}")
    result.notes.append("Matching tolerances are pilot proposals; pending scientific gates cannot pass.")
