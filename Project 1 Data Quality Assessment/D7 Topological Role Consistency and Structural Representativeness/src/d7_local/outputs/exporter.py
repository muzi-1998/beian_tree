from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from d7_local.contracts.topology_contract import TopologyRegistry
from d7_local.templates.builder import SpatialTemplate


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if isinstance(output[column].dtype, pd.DatetimeTZDtype):
            output[column] = output[column].dt.tz_localize(None)
    for column in output.select_dtypes(include=["object"]).columns:
        output[column] = output[column].map(
            lambda value: (
                value.tz_localize(None)
                if isinstance(value, pd.Timestamp) and value.tzinfo is not None
                else json.dumps(value, ensure_ascii=True, default=str)
                if isinstance(value, (list, dict, tuple))
                else value
            )
        )
    return output


def _autosize(writer: pd.ExcelWriter) -> None:
    for worksheet in writer.book.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cells in worksheet.iter_cols(min_row=1, max_row=min(worksheet.max_row, 200)):
            width = min(max(len(str(cell.value or "")) for cell in cells) + 2, 45)
            worksheet.column_dimensions[cells[0].column_letter].width = width


class D7OutputExporter:
    def __init__(self, output_root: Path) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def write_dual(self, stem: str, frame: pd.DataFrame, sheet: str = "data") -> list[Path]:
        parquet = self.output_root / f"{stem}.parquet"
        workbook = self.output_root / f"{stem}.xlsx"
        frame.to_parquet(parquet, index=False)
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            _excel_safe(frame).to_excel(writer, sheet_name=sheet[:31], index=False)
            _autosize(writer)
        return [parquet, workbook]

    def write_workbook(self, stem: str, sheets: dict[str, pd.DataFrame]) -> Path:
        path = self.output_root / f"{stem}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                _excel_safe(frame).to_excel(writer, sheet_name=name[:31], index=False)
            _autosize(writer)
        return path

    def write_templates(
        self,
        templates: dict[tuple[str, int], SpatialTemplate],
        support: pd.DataFrame,
        hysteresis: dict[str, Any],
    ) -> list[Path]:
        registry: list[dict[str, Any]] = []
        centers: list[dict[str, Any]] = []
        covariance: list[dict[str, Any]] = []
        gradients: list[dict[str, Any]] = []
        ranks: list[dict[str, Any]] = []
        reconstruction: list[dict[str, Any]] = []
        for template in templates.values():
            registry.append(
                {
                    "template_id": template.template_id,
                    "template_version": template.template_version,
                    "track_id": template.track_id,
                    "state": template.lifecycle_state,
                    "analyte": template.analyte,
                    "target_sensor": template.target_sensor,
                    "regime_id": template.regime_id,
                    "zone_id": template.zone_id,
                    "topology_hash": template.topology_hash,
                    "asset_hash": template.template_hash,
                    "fallback_level": template.fallback_level,
                }
            )
            for node, center, scale in zip(
                template.sensor_order, template.center, template.scale
            ):
                centers.append(
                    {
                        "template_id": template.template_id,
                        "node_id": node,
                        "center": center,
                        "scale": scale,
                        "sensor_policy": "target_excluded_context_only",
                    }
                )
            for i, row_node in enumerate(template.sensor_order):
                for j, col_node in enumerate(template.sensor_order):
                    covariance.append(
                        {
                            "template_id": template.template_id,
                            "row_node": row_node,
                            "col_node": col_node,
                            "covariance": template.covariance[i][j],
                            "precision": template.precision[i][j],
                            "mode": template.covariance_mode,
                            "alpha_used": template.alpha_used,
                            "condition_number": template.condition_number,
                        }
                    )
            for row in template.edge_templates:
                gradients.append({"template_id": template.template_id, **row})
            for row in template.rank_templates:
                ranks.append({"template_id": template.template_id, **row})
            reconstruction.append(
                {
                    "template_id": template.template_id,
                    "target_node": template.target_sensor,
                    "neighbor_set": template.reconstruction_neighbors,
                    "coefficients": template.reconstruction_coefficients,
                    "intercept": template.reconstruction_intercept,
                    "residual_scale": template.reconstruction_scale,
                }
            )
        hysteresis_frame = pd.DataFrame(
            [{"parameter": key, "value": value} for key, value in hysteresis.items()]
        )
        version = pd.DataFrame(
            [
                {
                    "version": next(iter(templates.values())).template_version,
                    "parent": "none",
                    "change_reason": "initial_v2.1_candidate_build",
                    "validator": "automated_contract_qa",
                    "approver": "PENDING_PRODUCTION_APPROVAL",
                    "state": "research_candidate_production_pending",
                }
            ]
        )
        workbook = self.write_workbook(
            "D7_spatial_templates",
            {
                "template_registry": pd.DataFrame(registry),
                "profile_centers": pd.DataFrame(centers),
                "profile_covariance": pd.DataFrame(covariance),
                "gradient_templates": pd.DataFrame(gradients),
                "rank_probabilities": pd.DataFrame(ranks),
                "reconstruction_models": pd.DataFrame(reconstruction),
                "hysteresis_policy": hysteresis_frame,
                "template_support": support,
                "template_versions": version,
            },
        )
        bundle = self.output_root / "D7_spatial_templates.template_bundle.json"
        bundle.write_text(
            json.dumps(
                [asdict(template) for template in templates.values()],
                indent=2,
                ensure_ascii=True,
                default=str,
            ),
            encoding="utf-8",
        )
        return [workbook, bundle]

    def write_topology(
        self,
        topology: TopologyRegistry,
        source_yaml: Path,
        schema_path: Path,
        evidence_path: Path,
    ) -> list[Path]:
        metadata = pd.DataFrame(
            [{**topology.metadata, "topology_hash": topology.topology_hash,
              "research_topology_confirmed": topology.research_topology_confirmed,
              "production_topology_verified": topology.topology_verified,
              "topology_verified": topology.topology_verified}]
        )
        evidence_rows: list[dict[str, object]] = []
        confirmation = topology.evidence["research_confirmation"]
        for item, value in confirmation["scope"].items():
            evidence_rows.append(
                {
                    "evidence_group": "author_confirmation",
                    "item": item,
                    "value": value,
                    "status": confirmation["status"],
                }
            )
        inventory = topology.evidence["instrument_inventory"]
        for analyte, record in inventory["biological_pool"].items():
            for item, value in record.items():
                evidence_rows.append(
                    {
                        "evidence_group": f"instrument_inventory_{analyte}",
                        "item": item,
                        "value": value,
                        "status": inventory["reconciliation"]["status"],
                    }
                )
        for limitation in inventory["limitations"]:
            evidence_rows.append(
                {
                    "evidence_group": "inventory_limitation",
                    "item": limitation,
                    "value": True,
                    "status": "documented",
                }
            )
        evidence_rows.extend(
            [
                {
                    "evidence_group": "research_use",
                    "item": "status",
                    "value": topology.evidence["research_use"]["status"],
                    "status": "active",
                },
                {
                    "evidence_group": "production_governance",
                    "item": "status",
                    "value": topology.evidence["production_governance"]["status"],
                    "status": "blocked",
                },
            ]
        )
        workbook = self.write_workbook(
            "D7_topology_registry",
            {
                "metadata": metadata,
                "evidence_summary": pd.DataFrame(evidence_rows),
                "nodes": topology.nodes,
                "edges": topology.edges,
                "twin_pairs": topology.twin_pairs,
                "version_history": pd.DataFrame(
                    [{
                        "version": topology.metadata.get("topology_version"),
                        "topology_hash": topology.topology_hash,
                        "change_reason": "author_confirmed_ordinal_topology_with_inventory_reconciliation",
                        "reviewer": topology.metadata.get("reviewer"),
                        "approver": topology.metadata.get("approver"),
                    }]
                ),
            },
        )
        yaml_target = self.output_root / "D7_topology_registry.yaml"
        schema_target = self.output_root / "D7_topology_registry.schema.json"
        evidence_target = self.output_root / "D7_topology_evidence.yaml"
        shutil.copy2(source_yaml, yaml_target)
        shutil.copy2(schema_path, schema_target)
        shutil.copy2(evidence_path, evidence_target)
        json_target = self.output_root / "D7_topology_registry.json"
        json_target.write_text(
            json.dumps(
                {
                    "metadata": topology.metadata,
                    "evidence": topology.evidence,
                    "topology_hash": topology.topology_hash,
                    "research_topology_confirmed": topology.research_topology_confirmed,
                    "production_topology_verified": topology.topology_verified,
                    "topology_verified": topology.topology_verified,
                    "nodes": topology.nodes.to_dict("records"),
                    "edges": topology.edges.to_dict("records"),
                    "twin_pairs": topology.twin_pairs.to_dict("records"),
                },
                indent=2,
                ensure_ascii=True,
                default=str,
            ),
            encoding="utf-8",
        )
        return [workbook, yaml_target, json_target, schema_target, evidence_target]

    def copy_interface_schema(self, schema_path: Path) -> Path:
        target = self.output_root / "D7_d6_interface.schema.json"
        shutil.copy2(schema_path, target)
        return target


def records_to_frame(records: Iterable[Any]) -> pd.DataFrame:
    return pd.DataFrame([asdict(record) for record in records])
