from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from d7_common.config import D7_ROOT, load_yaml, resolve_paths
from d7_common.hashing import hash_file, hash_object
from d7_common.math.calibration import empirical_quality_score


class D7SensitivityPipeline:
    """Physically isolated shadow reference/mapping sensitivity track."""

    RISK_TO_Q = {
        "risk_profile": "shadow_Q_profile",
        "risk_gradient": "shadow_Q_gradient",
        "risk_rank": "shadow_Q_rank",
        "risk_rep": "shadow_Q_rep",
    }

    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.config = load_yaml(D7_ROOT / "configs" / "sensitivity" / "d7_sensitivity.yaml")
        self.mapping = load_yaml(D7_ROOT / "configs" / "local" / "mapping.yaml")
        self.aggregation = load_yaml(D7_ROOT / "configs" / "local" / "aggregation.yaml")
        self.output_root = self.paths.sensitivity_output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict[str, Any]:
        evidence = pd.read_parquet(
            self.paths.local_output_root / "D7_spatial_evidence.parquet"
        )
        local = pd.read_parquet(
            self.paths.local_output_root / "D7_main_scores_hourly.parquet"
        )
        influence = pd.read_parquet(
            self.paths.local_output_root / "D7_sensor_influence.parquet"
        )
        upstream = self._load_upstream()
        shadow = evidence.merge(upstream, on=["timestamp", "sensor_id"], how="left")
        shadow["upstream_filter_pass"] = (
            shadow[["D1_score", "D2_score", "D4_score"]].ge(3.0).all(axis=1)
        )
        reference_end = local["timestamp"].sort_values().iloc[int(len(local) * 0.70)]
        mapping_rows: list[dict[str, Any]] = []
        shift_rows: list[dict[str, Any]] = []
        for risk, q_column in self.RISK_TO_Q.items():
            shadow[q_column] = np.nan
            for key, rows in shadow.groupby(
                ["analyte", "active_regime_id", "sensor_id"], dropna=False
            ):
                analyte, regime, sensor = key
                local_ref = shadow[
                    (shadow["analyte"] == analyte)
                    & (shadow["active_regime_id"] == regime)
                    & (shadow["timestamp"] <= reference_end)
                    & shadow["window_coverage"].ge(0.80)
                ][risk].dropna()
                filtered = shadow[
                    (shadow["analyte"] == analyte)
                    & (shadow["active_regime_id"] == regime)
                    & (shadow["timestamp"] <= reference_end)
                    & shadow["window_coverage"].ge(0.80)
                    & shadow["upstream_filter_pass"]
                ][risk].dropna()
                scope = "variable_regime_upstream_filtered"
                if len(filtered) < 100:
                    filtered = shadow[
                        (shadow["analyte"] == analyte)
                        & (shadow["timestamp"] <= reference_end)
                        & shadow["window_coverage"].ge(0.80)
                        & shadow["upstream_filter_pass"]
                    ][risk].dropna()
                    scope = "variable_public_upstream_filtered"
                if len(filtered) < 20:
                    continue
                index = rows.index
                shadow.loc[index, q_column] = empirical_quality_score(
                    shadow.loc[index, risk].to_numpy(dtype=float),
                    filtered.to_numpy(dtype=float),
                    gamma=float(self.mapping["gamma"]),
                )
                local_q = local_ref.quantile([0.50, 0.75, 0.90, 0.975])
                shadow_q = filtered.quantile([0.50, 0.75, 0.90, 0.975])
                mapping_rows.append(
                    {
                        "risk_metric": risk,
                        "analyte": analyte,
                        "regime_id": regime,
                        "sensor_id": sensor,
                        "scope": scope,
                        "n_filtered": len(filtered),
                        "filter_retention": len(filtered) / max(len(local_ref), 1),
                        "mapping_hash": hash_object(filtered.round(8).tolist()),
                    }
                )
                for quantile in [0.50, 0.75, 0.90, 0.975]:
                    shift_rows.append(
                        {
                            "risk_metric": risk,
                            "analyte": analyte,
                            "regime_id": regime,
                            "sensor_id": sensor,
                            "quantile": quantile,
                            "local_value": local_q.get(quantile, np.nan),
                            "shadow_value": shadow_q.get(quantile, np.nan),
                            "absolute_shift": shadow_q.get(quantile, np.nan)
                            - local_q.get(quantile, np.nan),
                            "relative_shift": (
                                shadow_q.get(quantile, np.nan)
                                - local_q.get(quantile, np.nan)
                            )
                            / max(abs(local_q.get(quantile, np.nan)), 1e-9),
                        }
                    )
        q = ["shadow_Q_profile", "shadow_Q_gradient", "shadow_Q_rank", "shadow_Q_rep"]
        matrix = shadow[q].to_numpy(dtype=float)
        weights = np.array(
            [
                self.aggregation["weights"]["profile"],
                self.aggregation["weights"]["gradient"],
                self.aggregation["weights"]["rank"],
                self.aggregation["weights"]["rep"],
            ]
        )
        base = np.sum(matrix * weights, axis=1)
        minimum = np.ma.min(np.ma.masked_invalid(matrix[:, [0, 1, 3]]), axis=1).filled(np.nan)
        shadow["shadow_D7"] = (
            float(self.aggregation["lambda_blend"]) * base
            + (1.0 - float(self.aggregation["lambda_blend"])) * minimum
        )
        shadow.loc[~np.isfinite(matrix).all(axis=1), "shadow_D7"] = np.nan
        shadow["shadow_status"] = np.where(
            shadow["shadow_D7"].notna(), "shadow_evaluable", "shadow_not_evaluable"
        )
        shadow["shadow_template_id"] = shadow["template_id_used"].astype(str) + "-SENS"
        shadow["consumed_sources"] = "D1_total_hourly;D2_total_wide;D4_total"
        shadow["track_id"] = "sensitivity"
        keep = [
            "timestamp", "sensor_id", "analyte", "active_regime_id", *q, "shadow_D7",
            "shadow_status", "shadow_template_id", "upstream_filter_pass", "D1_score",
            "D2_score", "D4_score", "consumed_sources", "track_id", "topology_hash",
            "template_version",
        ]
        shadow = shadow[keep]
        invariance = self._invariance(local, shadow, influence)
        template_shift = pd.DataFrame(shift_rows)
        self._write_dual("D7_shadow_scores", shadow)
        self._write_workbook(
            "D7_track_invariance",
            {
                "track_invariance": invariance,
                "mapping_registry": pd.DataFrame(mapping_rows).drop_duplicates(),
            },
        )
        self._write_workbook(
            "D7_shadow_template_shift", {"quantile_shift": template_shift}
        )
        d1_release_path = self.paths.d1_scores.parent / "D1_release_manifest.json"
        d1_release = (
            json.loads(d1_release_path.read_text(encoding="utf-8"))
            if d1_release_path.exists()
            else {}
        )
        dependency_paths = {
            "D1_scores": self.paths.d1_scores,
            "D2_scores": self.paths.d2_scores,
            "D4_scores": self.paths.d4_scores,
            "D7_local_evidence": self.paths.local_output_root / "D7_spatial_evidence.parquet",
        }
        workspace_root = D7_ROOT.parent.resolve()

        def project_relative(path: Path) -> str:
            return path.resolve().relative_to(workspace_root).as_posix()

        manifest = {
            "track_id": "sensitivity",
            "production_write_permission": False,
            "generated_utc": pd.Timestamp.utcnow().isoformat(),
            "d1_release_id": d1_release.get("release_id"),
            "consumed_sources": [
                project_relative(self.paths.d1_scores),
                project_relative(self.paths.d2_scores),
                project_relative(self.paths.d4_scores),
                project_relative(
                    self.paths.local_output_root / "D7_spatial_evidence.parquet"
                ),
            ],
            "dependencies": [
                {
                    "role": role,
                    "path": project_relative(path),
                    "sha256": hash_file(path),
                }
                for role, path in dependency_paths.items()
            ],
            "forbidden_outputs": ["D7_forDQR", "D7_zone_consensus", "D6_arbitration"],
            "D7_forDQR_status": "pending_not_produced",
            "local_imported": False,
            "rows": len(shadow),
            "invariance": invariance.to_dict("records"),
        }
        (self.output_root / "D7_sensitivity_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
        )
        return manifest

    def _load_upstream(self) -> pd.DataFrame:
        d1 = pd.read_excel(self.paths.d1_scores, sheet_name="D1_total_hourly")
        d1 = d1.rename(columns={d1.columns[0]: "timestamp"}).set_index("timestamp")
        d1.index = pd.to_datetime(d1.index)
        d1 = d1.stack().rename("D1_score").reset_index()
        d1.columns = ["timestamp", "sensor_id", "D1_score"]

        d2 = pd.read_excel(self.paths.d2_scores, sheet_name="D2_total_wide")
        d2 = d2.rename(columns={d2.columns[0]: "timestamp"}).set_index("timestamp")
        d2.index = pd.to_datetime(d2.index)
        d2 = d2.stack().rename("D2_score").reset_index()
        d2.columns = ["timestamp", "sensor_id", "D2_score"]

        d4 = pd.read_excel(self.paths.d4_scores)
        d4["timestamp"] = pd.to_datetime(d4["ts"])
        d4 = d4[["timestamp", "sensor_id", "D4_total"]].rename(
            columns={"D4_total": "D4_score"}
        )
        d4 = d4.sort_values("timestamp").drop_duplicates(
            ["timestamp", "sensor_id"], keep="last"
        )
        output = d1.merge(d2, on=["timestamp", "sensor_id"], how="outer")
        return output.merge(d4, on=["timestamp", "sensor_id"], how="outer")

    def _invariance(
        self, local: pd.DataFrame, shadow: pd.DataFrame, influence: pd.DataFrame
    ) -> pd.DataFrame:
        merged = local[["timestamp", "sensor_id", "D7_raw"]].merge(
            shadow[["timestamp", "sensor_id", "shadow_D7", "shadow_Q_rep"]],
            on=["timestamp", "sensor_id"],
            how="inner",
        )
        valid = merged.dropna(subset=["D7_raw", "shadow_D7"])
        ie = float((valid["D7_raw"] - valid["shadow_D7"]).abs().mean() / 4.0)
        local_event = set(map(tuple, valid.loc[valid["D7_raw"] < 3.0, ["timestamp", "sensor_id"]].to_numpy()))
        shadow_event = set(map(tuple, valid.loc[valid["shadow_D7"] < 3.0, ["timestamp", "sensor_id"]].to_numpy()))
        jaccard = len(local_event & shadow_event) / max(len(local_event | shadow_event), 1)
        culprit = influence[["timestamp", "sensor_id", "influence_score"]].merge(
            shadow[["timestamp", "sensor_id", "shadow_Q_rep"]],
            on=["timestamp", "sensor_id"],
            how="inner",
        ).dropna()
        rho = float(spearmanr(culprit["influence_score"], (5 - culprit["shadow_Q_rep"]) / 4).statistic)
        far_delta = float((valid["shadow_D7"] < 3.0).mean() - (valid["D7_raw"] < 3.0).mean())
        rows = [
            {"metric": "IE_track", "estimate": ie, "criterion": "<=0.20", "passed": ie <= 0.20},
            {"metric": "event_jaccard", "estimate": jaccard, "criterion": ">=0.80", "passed": jaccard >= 0.80},
            {"metric": "culprit_spearman", "estimate": rho, "criterion": ">=0.80", "passed": rho >= 0.80},
            {"metric": "FAR_delta", "estimate": far_delta, "criterion": "report", "passed": True},
        ]
        return pd.DataFrame(rows)

    def _write_dual(self, stem: str, frame: pd.DataFrame) -> None:
        frame.to_parquet(self.output_root / f"{stem}.parquet", index=False)
        self._write_workbook(stem, {"data": frame})

    def _write_workbook(self, stem: str, sheets: dict[str, pd.DataFrame]) -> None:
        with pd.ExcelWriter(self.output_root / f"{stem}.xlsx", engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name[:31], index=False)
