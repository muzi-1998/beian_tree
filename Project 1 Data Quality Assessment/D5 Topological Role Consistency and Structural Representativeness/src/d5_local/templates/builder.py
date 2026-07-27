from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from d5_common.hashing import hash_object
from d5_common.math.covariance import fit_shrinkage_covariance
from d5_common.math.robust import mad_scale, robust_center_scale
from d5_local.contracts.topology_contract import TopologyRegistry
from d5_local.reference.effective_blocks import EffectiveBlockEstimator
from d5_local.templates.orp_degradation import ORPDegradationPolicy
from d5_local.templates.support_policy import SupportPolicy


@dataclass
class SpatialTemplate:
    template_id: str
    template_version: str
    target_sensor: str
    analyte: str
    zone_id: str
    regime_id: int
    sensor_order: list[str]
    center: list[float]
    scale: list[float]
    covariance: list[list[float]]
    precision: list[list[float]]
    covariance_mode: str
    shrinkage_method: str
    alpha_floor: float
    alpha_used: float
    condition_number: float
    minimum_eigen_ratio: float
    edge_templates: list[dict[str, Any]]
    rank_templates: list[dict[str, Any]]
    reconstruction_neighbors: list[str]
    reconstruction_coefficients: list[float]
    reconstruction_intercept: float
    reconstruction_scale: float
    support: dict[str, Any]
    fallback_level: str
    lifecycle_state: str
    topology_hash: str
    track_id: str
    template_hash: str = ""

    def finalize_hash(self) -> None:
        payload = asdict(self)
        payload.pop("template_hash", None)
        self.template_hash = hash_object(payload)


class SpatialTemplateBuilder:
    def __init__(
        self,
        topology: TopologyRegistry,
        template_version: str,
        orp_policy: ORPDegradationPolicy,
        support_config: dict[str, Any],
    ) -> None:
        self.topology = topology
        self.template_version = template_version
        self.orp_policy = orp_policy
        self.support_policy = SupportPolicy(support_config)
        self.bootstrap_config = support_config["bootstrap"]
        self._support_diagnostics_cache: dict[
            tuple[str, int, str], dict[str, Any]
        ] = {}
        self.nodes = topology.nodes.set_index("sensor_id")

    def build(
        self,
        snapshots: pd.DataFrame,
        regime_state: pd.DataFrame,
        reference_end: pd.Timestamp,
    ) -> tuple[dict[tuple[str, int], SpatialTemplate], pd.DataFrame]:
        templates: dict[tuple[str, int], SpatialTemplate] = {}
        support_rows: list[dict[str, Any]] = []
        state = regime_state.set_index(["timestamp", "sensor_id"])["active_regime_id"]
        for target in self.nodes.index:
            target_state = state.xs(target, level="sensor_id").reindex(snapshots.index)
            for regime in sorted(target_state.dropna().unique().astype(int)):
                mask = (target_state == regime) & (snapshots.index <= reference_end)
                frame = snapshots.loc[mask]
                analyte = str(self.nodes.loc[target, "analyte"])
                sensor_order = self.nodes[self.nodes["analyte"] == analyte].index.tolist()
                fallback_level = (
                    "variable_regime_zone" if analyte == "DO" else "variable_public"
                )
                if len(frame[sensor_order].dropna()) < 50:
                    frame = snapshots.loc[snapshots.index <= reference_end]
                    fallback_level = "variable_public_low_regime_support"
                template = self._build_one(
                    target, int(regime), frame, fallback_level=fallback_level
                )
                templates[(target, int(regime))] = template
                support_rows.append(
                    {
                        "template_id": template.template_id,
                        "target_sensor": target,
                        "analyte": template.analyte,
                        "regime_id": int(regime),
                        "zone_id": template.zone_id,
                        **template.support,
                        "fallback_level": template.fallback_level,
                        "profile_covariance_mode": template.covariance_mode,
                        "shrinkage_method": template.shrinkage_method,
                        "alpha_floor": template.alpha_floor,
                        "alpha_used": template.alpha_used,
                        "covariance_condition_number": template.condition_number,
                        "min_eigen_ratio": template.minimum_eigen_ratio,
                        "limited_support": template.support["support_level"] in {"L0", "L1"},
                        "action_limited": template.support["support_level"] != "L3",
                        "limited_support_exit_status": template.support["limited_support_exit_status"],
                        "veto_eligible": template.support["veto_eligible"],
                        "template_hash": template.template_hash,
                        "topology_hash": self.topology.topology_hash,
                        "track_id": "d5_local",
                    }
                )
        return templates, pd.DataFrame(support_rows)

    def _build_one(
        self,
        target: str,
        regime: int,
        frame: pd.DataFrame,
        *,
        fallback_level: str,
    ) -> SpatialTemplate:
        target_meta = self.nodes.loc[target]
        analyte = str(target_meta["analyte"])
        sensor_order = self.nodes[self.nodes["analyte"] == analyte].index.tolist()
        complete = frame[sensor_order].dropna()
        if len(complete) < 50:
            raise ValueError(f"Insufficient D5-local reference snapshots for {target}/R{regime}")
        center, scale = robust_center_scale(complete.to_numpy())
        standardized = (complete.to_numpy() - center) / scale
        family_support = EffectiveBlockEstimator().estimate(complete.index)
        family_diagnostics = self._support_diagnostics(
            complete,
            analyte=analyte,
            regime=regime,
            fallback_level=fallback_level,
        )
        family_support_level = self.support_policy.resolve(
            int(family_support["n_effective"]),
            int(family_support["distinct_months"]),
            bootstrap_stability=float(
                family_diagnostics["bootstrap_stability"]
            ),
            holdout_count=int(family_diagnostics["holdout_count"]),
            holdout_far=float(family_diagnostics["holdout_far"]),
        )
        if analyte == "ORP":
            covariance_mode, alpha_floor = self.orp_policy.resolve_mode(
                family_support_level
            )
        else:
            covariance_mode = (
                "full_shrinkage"
                if family_support_level in {"L2", "L3"}
                else "diagonal_robust_z"
            )
            alpha_floor = 0.0 if covariance_mode == "full_shrinkage" else 1.0
        fit = fit_shrinkage_covariance(
            standardized,
            method="oas",
            alpha_floor=alpha_floor,
            diagonal_only=covariance_mode == "diagonal_robust_z",
        )
        if fit.condition_number > 1000.0 or fit.minimum_eigen_ratio < 0.001:
            fit = fit_shrinkage_covariance(standardized, diagonal_only=True, alpha_floor=1.0)
            covariance_mode = "diagonal_robust_z"
        edge_templates = self._edge_templates(complete, analyte)
        rank_templates = self._rank_templates(complete, analyte, scale, sensor_order)
        neighbors = self._neighbors(target, analyte)
        model_frame = frame[[target, *neighbors]].dropna()
        ridge = Ridge(alpha=1.0).fit(model_frame[neighbors], model_frame[target])
        residual = model_frame[target].to_numpy() - ridge.predict(model_frame[neighbors])
        residual_scale = max(float(mad_scale(residual)), 1e-6)
        node_support = EffectiveBlockEstimator().estimate(model_frame.index)
        node_diagnostics = self._node_support_diagnostics(
            model_frame,
            target=target,
            neighbors=neighbors,
            expected_rows=len(frame),
        )
        node_support_level = self.support_policy.resolve_node(
            int(node_support["n_effective"]),
            int(node_support["distinct_months"]),
            reference_coverage=float(node_diagnostics["node_reference_coverage"]),
            bootstrap_stability=float(
                node_diagnostics["node_bootstrap_stability"]
            ),
            holdout_count=int(node_diagnostics["node_holdout_count"]),
            holdout_far=float(node_diagnostics["node_holdout_far"]),
        )
        support_level = self.support_policy.minimum_tier(
            family_support_level, node_support_level
        )
        family_support_id = (
            f"D5-{analyte}-R{regime}-{covariance_mode}-{fallback_level}"
        )
        support = {
            **family_support,
            **family_diagnostics,
            "family_support_id": family_support_id,
            "model_family_id": f"D5-{analyte}-R{regime}-{covariance_mode}",
            "family_support_level": family_support_level,
            "family_n_effective": int(family_support["n_effective"]),
            "family_distinct_months": int(
                family_support["distinct_months"]
            ),
            "family_bootstrap_stability": float(
                family_diagnostics["bootstrap_stability"]
            ),
            "family_holdout_count": int(
                family_diagnostics["holdout_count"]
            ),
            "family_holdout_far": float(
                family_diagnostics["holdout_far"]
            ),
            "node_support_level": node_support_level,
            "node_n_effective": int(node_support["n_effective"]),
            "node_distinct_months": int(node_support["distinct_months"]),
            **node_diagnostics,
        }
        support.update(
            {
                "support_level": support_level,
                "FAR": family_diagnostics["holdout_far"],
                "score_eligible": support_level in {"L2", "L3"},
                "node_validation_passed": (
                    family_support_level == "L3"
                    and node_support_level == "L3"
                ),
                "action_eligible_candidate": (
                    family_support_level == "L3"
                    and node_support_level == "L3"
                ),
                "limited_support_exit_status": {
                    "L3": "family_and_node_action_candidate",
                    "L2": "scientific_score_ready",
                    "L1": "diagnostic_only",
                    "L0": "disabled",
                }[support_level],
                "family_exit_failed_reasons": self._family_exit_failed_reasons(
                    family_support_level,
                    family_support,
                    family_diagnostics,
                ),
                "node_exit_failed_reasons": self._node_exit_failed_reasons(
                    node_support_level,
                    node_support,
                    node_diagnostics,
                ),
                "veto_eligible": False,
            }
        )
        support["exit_failed_reasons"] = "|".join(
            reason
            for reason in [
                support["family_exit_failed_reasons"],
                support["node_exit_failed_reasons"],
            ]
            if reason != "none"
        ) or "none"
        template = SpatialTemplate(
            template_id=f"D5-{target}-R{regime}",
            template_version=self.template_version,
            target_sensor=target,
            analyte=analyte,
            zone_id=str(target_meta["zone_id"]),
            regime_id=regime,
            sensor_order=sensor_order,
            center=center.tolist(),
            scale=scale.tolist(),
            covariance=fit.covariance.tolist(),
            precision=fit.precision.tolist(),
            covariance_mode=covariance_mode,
            shrinkage_method=fit.method,
            alpha_floor=float(alpha_floor),
            alpha_used=float(fit.shrinkage),
            condition_number=float(fit.condition_number),
            minimum_eigen_ratio=float(fit.minimum_eigen_ratio),
            edge_templates=edge_templates,
            rank_templates=rank_templates,
            reconstruction_neighbors=neighbors,
            reconstruction_coefficients=ridge.coef_.astype(float).tolist(),
            reconstruction_intercept=float(ridge.intercept_),
            reconstruction_scale=residual_scale,
            support=support,
            fallback_level=fallback_level,
            lifecycle_state="candidate",
            topology_hash=self.topology.topology_hash,
            track_id="d5_local",
        )
        template.finalize_hash()
        return template

    def _support_diagnostics(
        self,
        complete: pd.DataFrame,
        *,
        analyte: str,
        regime: int,
        fallback_level: str,
    ) -> dict[str, Any]:
        cache_key = (analyte, regime, fallback_level)
        cached = self._support_diagnostics_cache.get(cache_key)
        if cached is not None:
            return cached.copy()

        daily = complete.resample("1D").median().dropna()
        base_center, base_scale = robust_center_scale(daily.to_numpy())
        rng = np.random.default_rng(int(self.bootstrap_config["random_seed"]))
        stability: list[float] = []
        repetitions = int(self.bootstrap_config["repetitions"])
        for _ in range(repetitions):
            sampled = daily.iloc[
                rng.integers(0, len(daily), size=len(daily))
            ]
            sampled_center, _ = robust_center_scale(sampled.to_numpy())
            standardized_shift = np.abs(
                (sampled_center - base_center) / np.maximum(base_scale, 1e-6)
            )
            stability.append(float(np.exp(-np.median(standardized_shift))))

        months = pd.PeriodIndex(daily.index, freq="M")
        false_alarms = 0
        holdout_rows = 0
        valid_holdouts = 0
        for month in months.unique():
            train = daily.loc[months != month]
            test = daily.loc[months == month]
            if len(train) < 20 or test.empty:
                continue
            train_center, train_scale = robust_center_scale(train.to_numpy())
            train_z = (
                train.to_numpy() - train_center
            ) / np.maximum(train_scale, 1e-6)
            test_z = (
                test.to_numpy() - train_center
            ) / np.maximum(train_scale, 1e-6)
            train_risk = np.sqrt(np.mean(np.square(train_z), axis=1))
            test_risk = np.sqrt(np.mean(np.square(test_z), axis=1))
            threshold = float(np.quantile(train_risk, 0.95))
            false_alarms += int((test_risk > threshold).sum())
            holdout_rows += int(len(test_risk))
            valid_holdouts += 1

        diagnostics = {
            "bootstrap_stability": float(np.median(stability)),
            "holdout_count": valid_holdouts,
            "holdout_rows": holdout_rows,
            "holdout_far": (
                float(false_alarms / holdout_rows)
                if holdout_rows
                else 1.0
            ),
            "support_validation_unit": "nonoverlap_calendar_day",
            "support_validation_method": (
                "daily_block_bootstrap_and_leave_one_month_out_robust_profile"
            ),
        }
        self._support_diagnostics_cache[cache_key] = diagnostics
        return diagnostics.copy()

    def _node_support_diagnostics(
        self,
        model_frame: pd.DataFrame,
        *,
        target: str,
        neighbors: list[str],
        expected_rows: int,
    ) -> dict[str, Any]:
        daily = model_frame.resample("1D").median().dropna()
        base_model = Ridge(alpha=1.0).fit(daily[neighbors], daily[target])
        base_residual = (
            daily[target].to_numpy()
            - base_model.predict(daily[neighbors])
        )
        base_scale = max(float(mad_scale(base_residual)), 1e-6)
        rng = np.random.default_rng(
            int(self.bootstrap_config["random_seed"])
            + sum(ord(character) for character in target)
        )
        stability: list[float] = []
        for _ in range(int(self.bootstrap_config["repetitions"])):
            sampled = daily.iloc[
                rng.integers(0, len(daily), size=len(daily))
            ]
            model = Ridge(alpha=1.0).fit(
                sampled[neighbors], sampled[target]
            )
            residual = (
                sampled[target].to_numpy()
                - model.predict(sampled[neighbors])
            )
            scale = max(float(mad_scale(residual)), 1e-6)
            stability.append(min(scale / base_scale, base_scale / scale))

        months = pd.PeriodIndex(daily.index, freq="M")
        false_alarms = 0
        holdout_rows = 0
        valid_holdouts = 0
        for month in months.unique():
            train = daily.loc[months != month]
            test = daily.loc[months == month]
            if len(train) < 20 or test.empty:
                continue
            model = Ridge(alpha=1.0).fit(train[neighbors], train[target])
            train_residual = np.abs(
                train[target].to_numpy()
                - model.predict(train[neighbors])
            )
            scale = max(float(mad_scale(train_residual)), 1e-6)
            train_z = train_residual / scale
            test_z = np.abs(
                test[target].to_numpy()
                - model.predict(test[neighbors])
            ) / scale
            threshold = float(np.quantile(train_z, 0.95))
            false_alarms += int((test_z > threshold).sum())
            holdout_rows += int(len(test_z))
            valid_holdouts += 1
        return {
            "node_reference_coverage": float(
                len(model_frame) / max(expected_rows, 1)
            ),
            "node_bootstrap_stability": float(np.median(stability)),
            "node_holdout_count": valid_holdouts,
            "node_holdout_rows": holdout_rows,
            "node_holdout_far": (
                float(false_alarms / holdout_rows)
                if holdout_rows
                else 1.0
            ),
            "node_validation_unit": "nonoverlap_calendar_day",
            "node_validation_method": (
                "daily_block_residual_bootstrap_and_leave_one_month_out"
            ),
        }

    def _family_exit_failed_reasons(
        self,
        support_level: str,
        support: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> str:
        if support_level == "L3":
            return "none"
        reasons: list[str] = []
        l3 = self.support_policy.thresholds["L3"]
        if int(support["n_effective"]) < int(l3["min_effective_blocks"]):
            reasons.append("effective_blocks")
        if int(support["distinct_months"]) < int(l3["min_distinct_months"]):
            reasons.append("distinct_months")
        if float(diagnostics["bootstrap_stability"]) < float(
            l3["min_bootstrap_stability"]
        ):
            reasons.append("bootstrap_stability")
        if int(diagnostics["holdout_count"]) < int(l3["min_blocked_holdouts"]):
            reasons.append("blocked_holdouts")
        if float(diagnostics["holdout_far"]) > float(l3["max_holdout_far"]):
            reasons.append("holdout_far")
        return "|".join(reasons) if reasons else "score_only_below_action_grade"

    def _node_exit_failed_reasons(
        self,
        support_level: str,
        support: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> str:
        if support_level == "L3":
            return "none"
        reasons: list[str] = []
        l3 = self.support_policy.node_thresholds["L3"]
        if int(support["n_effective"]) < int(l3["min_effective_blocks"]):
            reasons.append("node_effective_blocks")
        if int(support["distinct_months"]) < int(l3["min_distinct_months"]):
            reasons.append("node_distinct_months")
        if float(diagnostics["node_reference_coverage"]) < float(
            l3["min_reference_coverage"]
        ):
            reasons.append("node_reference_coverage")
        if float(diagnostics["node_bootstrap_stability"]) < float(
            l3["min_bootstrap_stability"]
        ):
            reasons.append("node_bootstrap_stability")
        if int(diagnostics["node_holdout_count"]) < int(
            l3["min_blocked_holdouts"]
        ):
            reasons.append("node_blocked_holdouts")
        if float(diagnostics["node_holdout_far"]) > float(
            l3["max_holdout_far"]
        ):
            reasons.append("node_holdout_far")
        return "|".join(reasons) if reasons else "node_score_only"

    def _edge_templates(self, frame: pd.DataFrame, analyte: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        analyte_nodes = set(self.nodes[self.nodes["analyte"] == analyte].index)
        for edge in self.topology.edges.itertuples(index=False):
            if edge.source not in analyte_nodes or edge.target not in analyte_nodes:
                continue
            delta = frame[edge.target] - frame[edge.source]
            median = float(delta.median())
            scale = max(float(mad_scale(delta.to_numpy())), 1e-6)
            rows.append(
                {
                    "edge_id": edge.edge_id,
                    "source": edge.source,
                    "target": edge.target,
                    "median": median,
                    "scale": scale,
                    "p_positive": float((delta > 0).mean()),
                    "q05": float(delta.quantile(0.05)),
                    "q95": float(delta.quantile(0.95)),
                    "censored_model": bool(
                        self.nodes.loc[edge.source, "floor_flag"]
                        or self.nodes.loc[edge.target, "floor_flag"]
                    ),
                }
            )
        return rows

    def _rank_templates(
        self, frame: pd.DataFrame, analyte: str, scale: np.ndarray, sensor_order: list[str]
    ) -> list[dict[str, Any]]:
        scale_map = dict(zip(sensor_order, scale))
        rows: list[dict[str, Any]] = []
        subset = self.nodes[self.nodes["analyte"] == analyte]
        for line in subset["line_id"].unique():
            sensors = subset[subset["line_id"] == line].sort_values("position_order").index.tolist()
            for i, left in enumerate(sensors):
                for right in sensors[i + 1 :]:
                    valid = frame[[left, right]].dropna()
                    wins = int((valid[left] > valid[right]).sum())
                    probability = (wins + 1.0) / (len(valid) + 2.0)
                    rows.append(
                        {
                            "pair_rule_id": f"{left}|{right}",
                            "node_i": left,
                            "node_j": right,
                            "p_i_gt_j": probability,
                            "pair_weight": 2.0 * abs(probability - 0.5),
                            "tie_tolerance": 0.10 * float(np.mean([scale_map[left], scale_map[right]])),
                        }
                    )
        return rows

    def _neighbors(self, target: str, analyte: str) -> list[str]:
        candidates: set[str] = set()
        for edge in self.topology.edges.itertuples(index=False):
            if edge.source == target:
                candidates.add(edge.target)
            if edge.target == target:
                candidates.add(edge.source)
        for pair in self.topology.twin_pairs.itertuples(index=False):
            if pair.sensor_a == target:
                candidates.add(pair.sensor_b)
            if pair.sensor_b == target:
                candidates.add(pair.sensor_a)
        return sorted(
            sensor for sensor in candidates if self.nodes.loc[sensor, "analyte"] == analyte
        )
