from __future__ import annotations

import numpy as np
import pandas as pd

from d5_local.contracts.topology_contract import TopologyRegistry
from d5_local.evidence.base import EvidenceBundle
from d5_local.templates.builder import SpatialTemplate


class SpatialEvidenceEngine:
    def __init__(self, topology: TopologyRegistry) -> None:
        self.topology = topology
        self.nodes = topology.nodes.set_index("sensor_id")

    def score(
        self,
        snapshots: pd.DataFrame,
        regime_state: pd.DataFrame,
        templates: dict[tuple[str, int], SpatialTemplate],
    ) -> EvidenceBundle:
        sensors = self.nodes.index.tolist()
        outputs = {
            name: pd.DataFrame(np.nan, index=snapshots.index, columns=sensors)
            for name in [
                "risk_profile",
                "risk_gradient",
                "risk_rank",
                "risk_rep",
                "loo_prediction",
                "normalized_loo_residual",
                "graph_energy_full",
                "graph_energy_replaced",
                "energy_delta",
            ]
        }
        state = regime_state.set_index(["timestamp", "sensor_id"])["active_regime_id"]
        for target in sensors:
            target_state = state.xs(target, level="sensor_id").reindex(snapshots.index)
            for regime in sorted(target_state.dropna().unique().astype(int)):
                template = templates.get((target, int(regime)))
                if template is None:
                    continue
                mask = target_state.eq(regime)
                frame = snapshots.loc[mask]
                scored = self._score_template(frame, template)
                for name, values in scored.items():
                    outputs[name].loc[mask, target] = values
        return EvidenceBundle(**outputs)

    def _score_template(
        self, frame: pd.DataFrame, template: SpatialTemplate
    ) -> dict[str, np.ndarray]:
        order = template.sensor_order
        matrix = frame[order].to_numpy(dtype=float)
        center = np.asarray(template.center)
        scale = np.asarray(template.scale)
        z = (matrix - center) / scale
        target_index = order.index(template.target_sensor)
        complete = np.isfinite(z).all(axis=1)
        global_distance = np.full(len(frame), np.nan)
        if template.covariance_mode == "diagonal_robust_z":
            global_distance[complete] = np.sqrt(np.mean(np.clip(z[complete], -2.5, 2.5) ** 2, axis=1))
        else:
            precision = np.asarray(template.precision)
            global_distance[complete] = np.sqrt(
                np.maximum(np.einsum("ij,jk,ik->i", z[complete], precision, z[complete]), 0.0)
                / len(order)
            )
        target_z = np.abs(z[:, target_index])
        risk_profile = 0.60 * target_z + 0.40 * global_distance

        incident: list[np.ndarray] = []
        for edge in template.edge_templates:
            if template.target_sensor not in {edge["source"], edge["target"]}:
                continue
            delta = frame[edge["target"]].to_numpy() - frame[edge["source"]].to_numpy()
            incident.append(np.abs(delta - edge["median"]) / edge["scale"])
        if incident:
            masked = np.ma.masked_invalid(np.vstack(incident))
            risk_gradient = np.ma.median(masked, axis=0).filled(np.nan)
        else:
            risk_gradient = np.full(len(frame), np.nan)

        weighted = np.zeros(len(frame), dtype=float)
        weight_sum = np.zeros(len(frame), dtype=float)
        for rule in template.rank_templates:
            if template.target_sensor not in {rule["node_i"], rule["node_j"]}:
                continue
            left = frame[rule["node_i"]].to_numpy()
            right = frame[rule["node_j"]].to_numpy()
            valid = np.isfinite(left) & np.isfinite(right)
            expected_left_higher = rule["p_i_gt_j"] >= 0.5
            violation = (
                left < right - rule["tie_tolerance"]
                if expected_left_higher
                else left > right + rule["tie_tolerance"]
            )
            weight = float(rule["pair_weight"])
            weighted[valid] += violation[valid].astype(float) * weight
            weight_sum[valid] += weight
        risk_rank = np.divide(
            weighted, weight_sum, out=np.full(len(frame), np.nan), where=weight_sum > 0
        )

        neighbors = template.reconstruction_neighbors
        coefficients = np.asarray(template.reconstruction_coefficients)
        neighbor_matrix = frame[neighbors].to_numpy(dtype=float)
        neighbor_valid = np.isfinite(neighbor_matrix).all(axis=1)
        prediction = np.full(len(frame), np.nan)
        prediction[neighbor_valid] = (
            neighbor_matrix[neighbor_valid] @ coefficients + template.reconstruction_intercept
        )
        observed = frame[template.target_sensor].to_numpy(dtype=float)
        normalized_residual = np.abs(observed - prediction) / template.reconstruction_scale
        graph_energy_full, graph_energy_replaced, energy_delta = self._energy_delta(
            frame, template, prediction
        )
        risk_rep = normalized_residual * (1.0 + 0.50 * np.clip(energy_delta, 0.0, 1.0))
        return {
            "risk_profile": risk_profile,
            "risk_gradient": risk_gradient,
            "risk_rank": risk_rank,
            "risk_rep": risk_rep,
            "loo_prediction": prediction,
            "normalized_loo_residual": normalized_residual,
            "graph_energy_full": graph_energy_full,
            "graph_energy_replaced": graph_energy_replaced,
            "energy_delta": energy_delta,
        }

    def _energy_delta(
        self, frame: pd.DataFrame, template: SpatialTemplate, prediction: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        order = template.sensor_order
        matrix = frame[order].to_numpy(dtype=float)
        z = (matrix - np.asarray(template.center)) / np.asarray(template.scale)
        replaced = z.copy()
        target_index = order.index(template.target_sensor)
        replaced[:, target_index] = (
            prediction - template.center[target_index]
        ) / template.scale[target_index]
        full_energy = np.zeros(len(frame), dtype=float)
        replaced_energy = np.zeros(len(frame), dtype=float)
        used = np.zeros(len(frame), dtype=float)
        for edge in template.edge_templates:
            source = order.index(edge["source"])
            target = order.index(edge["target"])
            valid = np.isfinite(z[:, source]) & np.isfinite(z[:, target])
            valid_replaced = np.isfinite(replaced[:, source]) & np.isfinite(replaced[:, target])
            full_energy[valid] += (z[valid, source] - z[valid, target]) ** 2
            replaced_energy[valid_replaced] += (
                replaced[valid_replaced, source] - replaced[valid_replaced, target]
            ) ** 2
            used[valid & valid_replaced] += 1
        delta = np.divide(
            full_energy - replaced_energy,
            np.maximum(full_energy, 1e-9),
            out=np.full(len(frame), np.nan),
            where=used > 0,
        )
        full_energy[used == 0] = np.nan
        replaced_energy[used == 0] = np.nan
        return full_energy, replaced_energy, delta
