from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from d5_common.config import reference_end_from_fraction


LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class AuditBoundary:
    reference_fraction: float
    reference_end: pd.Timestamp
    embargo_hours: int
    support_audit_post_start: pd.Timestamp
    controlled_validation_start: pd.Timestamp


class D5SupportMigrationAudit:
    """Post hoc support-migration audit that never changes frozen D5 scores."""

    def __init__(self, d5_root: Path) -> None:
        self.root = Path(d5_root)
        self.local = self.root / "outputs" / "local"
        self.aggregation = self._load_yaml(
            self.root / "configs" / "local" / "aggregation.yaml"
        )["support_policy"]
        self.templates = self._load_yaml(
            self.root / "configs" / "local" / "templates.yaml"
        )
        self.windows = self._load_yaml(
            self.root / "configs" / "common" / "windows.yaml"
        )

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def run(self) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
        regime = pd.read_parquet(self.local / "D5_regime_state.parquet")
        main = pd.read_parquet(self.local / "D5_main_scores_hourly.parquet")
        support = pd.read_parquet(self.local / "D5_support_assessment.parquet")
        boundary = self._boundary(regime)

        monthly, shift = self._monthly_regime_occupancy(regime, boundary)
        template_matrix = self._template_matrix(main, support, boundary)
        l1_blockers = self._l1_to_l2_blockers(template_matrix)
        l3_blockers = self._l2_to_l3_blockers(template_matrix)
        attribution = self._coverage_loss_attribution(l1_blockers, main, boundary)
        counterfactual = self._counterfactual_coverage(main, template_matrix, boundary)
        monthly_eligibility = self._monthly_eligibility(main)
        horizon = self._reference_horizon_sensitivity(regime)

        tables = {
            "01_monthly_regime_occupancy": monthly,
            "01b_pre_post_regime_shift": shift,
            "02_template_occupancy_56": template_matrix,
            "03_L1_to_L2_blockers": l1_blockers,
            "04_L2_to_L3_blockers": l3_blockers,
            "05_coverage_loss_attribution": attribution,
            "06_counterfactual_coverage": counterfactual,
            "07_reference_horizon_sensitivity": horizon,
            "08_monthly_report_eligibility": monthly_eligibility,
        }
        metadata = self._metadata(main, support, boundary, tables)
        return tables, metadata

    def _boundary(self, regime: pd.DataFrame) -> AuditBoundary:
        unique = regime.drop_duplicates("timestamp").sort_values("timestamp")
        index = pd.DatetimeIndex(unique["timestamp"])
        fraction = float(self.templates["reference_fraction"])
        reference_end = pd.Timestamp(reference_end_from_fraction(index, fraction))
        embargo_hours = int(self.windows.get("embargo_hours", 168))
        return AuditBoundary(
            reference_fraction=fraction,
            reference_end=reference_end,
            embargo_hours=embargo_hours,
            support_audit_post_start=reference_end + pd.Timedelta(hours=embargo_hours),
            controlled_validation_start=reference_end.ceil("D") + pd.Timedelta(days=1),
        )

    @staticmethod
    def _plant_global(regime: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "timestamp",
            "active_regime_id",
            "regime_state",
            "map_probability",
            "ood_distance",
        ]
        unique = regime[columns].drop_duplicates("timestamp").sort_values("timestamp")
        duplicates = regime.groupby("timestamp")["active_regime_id"].nunique()
        if int(duplicates.max()) != 1:
            raise ValueError("D5 regime state is not plant-global at every timestamp")
        return unique

    def _monthly_regime_occupancy(
        self, regime: pd.DataFrame, boundary: AuditBoundary
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        plant = self._plant_global(regime)
        plant["month"] = pd.to_datetime(plant["timestamp"]).dt.to_period("M").astype(str)
        monthly_counts = (
            plant.groupby(["month", "active_regime_id"], observed=True)
            .size()
            .rename("snapshot_count")
            .reset_index()
        )
        totals = plant.groupby("month").size().rename("month_snapshot_count")
        monthly_counts = monthly_counts.merge(totals, on="month", how="left")
        monthly_counts["occupancy_rate"] = (
            monthly_counts["snapshot_count"] / monthly_counts["month_snapshot_count"]
        )
        ood = (
            plant.assign(is_ood=plant["regime_state"].eq("OODHold"))
            .groupby("month", observed=True)["is_ood"]
            .mean()
            .rename("ood_rate")
        )
        monthly_counts = monthly_counts.merge(ood, on="month", how="left")
        monthly_counts["regime_label"] = monthly_counts["active_regime_id"].map(
            lambda value: f"R{int(value)}"
        )

        pre = plant[pd.to_datetime(plant["timestamp"]) <= boundary.reference_end]
        post = plant[
            pd.to_datetime(plant["timestamp"]) >= boundary.support_audit_post_start
        ]
        rows: list[dict[str, Any]] = []
        for regime_id in range(4):
            pre_rate = float(pre["active_regime_id"].eq(regime_id).mean())
            post_rate = float(post["active_regime_id"].eq(regime_id).mean())
            rows.append(
                {
                    "regime_id": regime_id,
                    "regime_label": f"R{regime_id}",
                    "reference_occupancy": pre_rate,
                    "post_occupancy": post_rate,
                    "delta_percentage_points": 100.0 * (post_rate - pre_rate),
                    "migration_ratio": (post_rate + 1e-6) / (pre_rate + 1e-6),
                    "reference_snapshots": int(len(pre)),
                    "post_snapshots": int(len(post)),
                }
            )
        return monthly_counts, pd.DataFrame(rows)

    def _template_matrix(
        self,
        main: pd.DataFrame,
        support: pd.DataFrame,
        boundary: AuditBoundary,
    ) -> pd.DataFrame:
        post = main[
            pd.to_datetime(main["timestamp"]) >= boundary.support_audit_post_start
        ].copy()
        occupancy = (
            post.groupby(["sensor_id", "active_regime_id"], observed=True)
            .agg(
                post_ref_sensor_hours=("timestamp", "size"),
                report_eligible_hours=("report_eligible", "sum"),
                limited_support_hours=(
                    "evaluation_status",
                    lambda values: values.eq("limited_support").sum(),
                ),
                ood_hours=("evaluation_status", lambda values: values.eq("out_of_template").sum()),
                not_evaluable_hours=("evaluation_status", lambda values: values.eq("not_evaluable").sum()),
            )
            .reset_index()
        )
        output = support.rename(
            columns={"target_sensor": "sensor_id", "regime_id": "active_regime_id"}
        ).merge(occupancy, on=["sensor_id", "active_regime_id"], how="left")
        count_columns = [
            "post_ref_sensor_hours",
            "report_eligible_hours",
            "limited_support_hours",
            "ood_hours",
            "not_evaluable_hours",
        ]
        output[count_columns] = output[count_columns].fillna(0).astype(int)
        total_post = max(int(len(post)), 1)
        output["post_ref_share"] = output["post_ref_sensor_hours"] / total_post
        output["coverage_loss_hours"] = (
            output["post_ref_sensor_hours"] - output["report_eligible_hours"]
        )
        output["support_attributable_loss_hours"] = output["limited_support_hours"]
        output["report_coverage_rate"] = np.divide(
            output["report_eligible_hours"],
            output["post_ref_sensor_hours"],
            out=np.zeros(len(output), dtype=float),
            where=output["post_ref_sensor_hours"].to_numpy() > 0,
        )
        output["regime_label"] = output["active_regime_id"].map(
            lambda value: f"R{int(value)}"
        )
        return output.sort_values(["analyte", "sensor_id", "active_regime_id"]).reset_index(
            drop=True
        )

    def _l1_to_l2_blockers(self, templates: pd.DataFrame) -> pd.DataFrame:
        output = templates[templates["support_level"].eq("L1")].copy()
        family = self.aggregation["thresholds"]["L2"]
        node = self.aggregation["node_validation"]["L2"]
        checks = {
            "family_days": output["family_n_effective"]
            < int(family["min_effective_blocks"]),
            "family_months": output["family_distinct_months"]
            < int(family["min_distinct_months"]),
            "node_days": output["node_n_effective"]
            < int(node["min_effective_blocks"]),
            "node_months": output["node_distinct_months"]
            < int(node["min_distinct_months"]),
            "node_coverage": output["node_reference_coverage"]
            < float(node["min_reference_coverage"]),
        }
        for name, values in checks.items():
            output[name] = values.astype(bool)
        blocker_columns = list(checks)
        output["blocker_set"] = output[blocker_columns].apply(
            lambda row: "|".join(row.index[row.to_numpy(dtype=bool)]) or "unresolved",
            axis=1,
        )
        output["primary_blocker"] = output.apply(
            lambda row: next(
                (name for name in blocker_columns if bool(row[name])), "unresolved"
            ),
            axis=1,
        )
        return output.reset_index(drop=True)

    def _l2_to_l3_blockers(self, templates: pd.DataFrame) -> pd.DataFrame:
        output = templates[templates["support_level"].isin(["L2", "L3"])].copy()
        family = self.aggregation["thresholds"]["L3"]
        node = self.aggregation["node_validation"]["L3"]
        checks = {
            "family_days_l3": output["family_n_effective"]
            < int(family["min_effective_blocks"]),
            "family_months_l3": output["family_distinct_months"]
            < int(family["min_distinct_months"]),
            "family_stability": output["family_bootstrap_stability"]
            < float(family["min_bootstrap_stability"]),
            "family_holdouts": output["family_holdout_count"]
            < int(family["min_blocked_holdouts"]),
            "family_far": output["family_holdout_far"]
            > float(family["max_holdout_far"]),
            "node_days_l3": output["node_n_effective"]
            < int(node["min_effective_blocks"]),
            "node_months_l3": output["node_distinct_months"]
            < int(node["min_distinct_months"]),
            "node_coverage_l3": output["node_reference_coverage"]
            < float(node["min_reference_coverage"]),
            "node_stability": output["node_bootstrap_stability"]
            < float(node["min_bootstrap_stability"]),
            "node_holdouts": output["node_holdout_count"]
            < int(node["min_blocked_holdouts"]),
            "node_far": output["node_holdout_far"]
            > float(node["max_holdout_far"]),
        }
        for name, values in checks.items():
            output[name] = values.astype(bool)
        blocker_columns = list(checks)
        output["l3_blocker_set"] = output[blocker_columns].apply(
            lambda row: "|".join(row.index[row.to_numpy(dtype=bool)]) or "none",
            axis=1,
        )
        return output.reset_index(drop=True)

    @staticmethod
    def _coverage_loss_attribution(
        blockers: pd.DataFrame, main: pd.DataFrame, boundary: AuditBoundary
    ) -> pd.DataFrame:
        post = main[
            pd.to_datetime(main["timestamp"]) >= boundary.support_audit_post_start
        ]
        post_rows = int(len(post))
        support = (
            blockers.groupby(["primary_blocker", "blocker_set"], observed=True)
            .agg(
                template_count=("template_id", "size"),
                loss_sensor_hours=("support_attributable_loss_hours", "sum"),
                occupied_sensor_hours=("post_ref_sensor_hours", "sum"),
            )
            .reset_index()
        )
        support.insert(0, "loss_class", "limited_support")
        rows = [support]
        for status, label in (
            ("out_of_template", "OOD / out of frozen template"),
            ("not_evaluable", "Incomplete evidence"),
        ):
            count = int(post["evaluation_status"].eq(status).sum())
            rows.append(
                pd.DataFrame(
                    {
                        "loss_class": [status],
                        "primary_blocker": ["not_applicable"],
                        "blocker_set": [label],
                        "template_count": [0],
                        "loss_sensor_hours": [count],
                        "occupied_sensor_hours": [count],
                    }
                )
            )
        output = pd.concat(rows, ignore_index=True)
        output["coverage_percentage_point_contribution"] = (
            100.0 * output["loss_sensor_hours"] / max(post_rows, 1)
        )
        output["loss_share_within_unreported"] = np.divide(
            output["loss_sensor_hours"],
            max(int((~post["report_eligible"].astype(bool)).sum()), 1),
        )
        return output.sort_values("loss_sensor_hours", ascending=False).reset_index(drop=True)

    def _counterfactual_coverage(
        self,
        main: pd.DataFrame,
        templates: pd.DataFrame,
        boundary: AuditBoundary,
    ) -> pd.DataFrame:
        post = main[
            pd.to_datetime(main["timestamp"]) >= boundary.support_audit_post_start
        ].copy()
        family = self.aggregation["thresholds"]["L2"]
        node = self.aggregation["node_validation"]["L2"]
        family_days = templates["family_n_effective"].ge(
            int(family["min_effective_blocks"])
        )
        family_months = templates["family_distinct_months"].ge(
            int(family["min_distinct_months"])
        )
        node_days = templates["node_n_effective"].ge(int(node["min_effective_blocks"]))
        node_months = templates["node_distinct_months"].ge(
            int(node["min_distinct_months"])
        )
        node_coverage = templates["node_reference_coverage"].ge(
            float(node["min_reference_coverage"])
        )
        scenarios = {
            "Current": templates["support_level"].isin(["L2", "L3"]),
            "Family days repaired": family_months
            & node_days
            & node_months
            & node_coverage,
            "Family months repaired": family_days
            & node_days
            & node_months
            & node_coverage,
            "Node days repaired": family_days
            & family_months
            & node_months
            & node_coverage,
            "Node months repaired": family_days
            & family_months
            & node_days
            & node_coverage,
            "Node coverage repaired": family_days
            & family_months
            & node_days
            & node_months,
            "All L2 support repaired": pd.Series(True, index=templates.index),
        }
        evidence_ready = (
            post["D5_raw"].notna()
            & post["window_coverage"].ge(float(self.windows["report_only_coverage"]))
            & ~post["regime_state"].eq("OODHold")
            & post["research_topology_confirmed"].astype(bool)
        )
        current = float(post["report_eligible"].mean())
        rows: list[dict[str, Any]] = []
        keys = list(zip(templates["sensor_id"], templates["active_regime_id"].astype(int)))
        for name, eligibility in scenarios.items():
            lookup = dict(zip(keys, eligibility.astype(bool)))
            support_ready = pd.Series(
                [
                    lookup.get((sensor, int(regime)), False)
                    for sensor, regime in zip(post["sensor_id"], post["active_regime_id"])
                ],
                index=post.index,
            )
            coverage = float((evidence_ready & support_ready).mean())
            rows.append(
                {
                    "scenario": name,
                    "report_coverage": coverage,
                    "delta_percentage_points": 100.0 * (coverage - current),
                    "report_eligible_sensor_hours": int((evidence_ready & support_ready).sum()),
                    "total_post_sensor_hours": int(len(post)),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _monthly_eligibility(main: pd.DataFrame) -> pd.DataFrame:
        frame = main.copy()
        frame["month"] = pd.to_datetime(frame["timestamp"]).dt.to_period("M").astype(str)
        return (
            frame.groupby("month", observed=True)
            .agg(
                sensor_hours=("timestamp", "size"),
                report_coverage=("report_eligible", "mean"),
                limited_support_rate=("evaluation_status", lambda values: values.eq("limited_support").mean()),
                ood_rate=("evaluation_status", lambda values: values.eq("out_of_template").mean()),
                not_evaluable_rate=("evaluation_status", lambda values: values.eq("not_evaluable").mean()),
            )
            .reset_index()
        )

    def _reference_horizon_sensitivity(self, regime: pd.DataFrame) -> pd.DataFrame:
        """Occupied-day upper bound with the frozen K=4 assignments held fixed.

        This deliberately does not relabel regimes or rebuild family/node templates.
        It therefore cannot be interpreted as an effective-support recalculation.
        """
        plant = self._plant_global(regime)
        index = pd.DatetimeIndex(plant["timestamp"])
        rows: list[dict[str, Any]] = []
        l2 = self.aggregation["thresholds"]["L2"]
        for fraction in (0.70, 0.80, 0.90):
            endpoint = pd.Timestamp(reference_end_from_fraction(index, fraction))
            ref = plant[pd.to_datetime(plant["timestamp"]) <= endpoint].copy()
            ref["day"] = pd.to_datetime(ref["timestamp"]).dt.floor("D")
            ref["month"] = pd.to_datetime(ref["timestamp"]).dt.to_period("M").astype(str)
            for regime_id in range(4):
                subset = ref[ref["active_regime_id"].eq(regime_id)]
                days = int(subset["day"].nunique())
                months = int(subset["month"].nunique())
                rows.append(
                    {
                        "reference_fraction": fraction,
                        "reference_end": endpoint,
                        "regime_id": regime_id,
                        "regime_label": f"R{regime_id}",
                        "occupied_calendar_days_upper_bound": days,
                        "distinct_months": months,
                        "family_L2_occupancy_horizon_pass": bool(
                            days >= int(l2["min_effective_blocks"])
                            and months >= int(l2["min_distinct_months"])
                        ),
                        "effective_support_recalculated": False,
                        "scope": "descriptive_occupied_day_upper_bound_with_frozen_K4_assignments",
                    }
                )
        return pd.DataFrame(rows)

    def _metadata(
        self,
        main: pd.DataFrame,
        support: pd.DataFrame,
        boundary: AuditBoundary,
        tables: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        sources = [
            self.root / "src" / "d5_local" / "publication" / "support_migration.py",
            self.root / "scripts" / "run_d5_support_migration_audit.py",
            self.local / "D5_regime_state.parquet",
            self.local / "D5_main_scores_hourly.parquet",
            self.local / "D5_support_assessment.parquet",
            self.local / "D5_run_manifest.json",
            self.root / "configs" / "local" / "aggregation.yaml",
            self.root / "configs" / "local" / "templates.yaml",
            self.root / "configs" / "common" / "windows.yaml",
        ]
        return {
            "audit_id": "D5-SUPPORT-MIGRATION-V1.1",
            "authoritative_scores_modified": False,
            "source_run_id": str(main["run_id"].dropna().unique()[0]),
            "template_version": str(main["template_version"].dropna().unique()[0]),
            "topology_hash": str(main["topology_hash"].dropna().unique()[0]),
            "reference_fraction": boundary.reference_fraction,
            "reference_end": boundary.reference_end.isoformat(),
            "embargo_hours": boundary.embargo_hours,
            "support_audit_post_start": boundary.support_audit_post_start.isoformat(),
            "controlled_validation_start": boundary.controlled_validation_start.isoformat(),
            "study_end": pd.Timestamp(main["timestamp"].max()).isoformat(),
            "sensor_hours": int(len(main)),
            "template_count": int(len(support)),
            "source_sha256": {
                path.relative_to(self.root).as_posix(): sha256_file(path) for path in sources
            },
            "table_rows": {name: int(len(frame)) for name, frame in tables.items()},
            "scope_notes": [
                "L1-to-L2 blockers use only the prespecified L2 support contract.",
                "Stability, blocked holdout and FAR are restricted to L2-to-L3 maturity.",
                "Counterfactual coverage is diagnostic and does not alter production thresholds.",
                "Reference-horizon sensitivity is an occupied-day upper bound with frozen K=4 assignments, not an effective-support recalculation.",
                "K=3/K=5 refits are deferred pending full outer-fold discrimination and localization validation.",
            ],
        }


def write_manifest(
    path: Path,
    metadata: dict[str, Any],
    artifacts: list[Path],
    *,
    base_root: Path | None = None,
) -> None:
    payload = dict(metadata)
    payload["artifacts"] = {
        (
            artifact.resolve().relative_to(base_root.resolve()).as_posix()
            if base_root is not None
            else artifact.name
        ): {"sha256": sha256_file(artifact), "size": artifact.stat().st_size}
        for artifact in artifacts
        if artifact.exists()
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
