from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from d7_common.config import D7_ROOT, load_yaml, resolve_paths
from d7_common.hashing import hash_object


class D7GraphShadowPipeline:
    """Exploratory graph candidates with a hard-coded zero production impact."""

    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.output_root = self.paths.shadow_v2_output_root
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.sensors = load_yaml(D7_ROOT / "configs" / "common" / "sensors.yaml")["nodes"]
        self.topology = load_yaml(D7_ROOT / "configs" / "common" / "topology.yaml")

    def run(self) -> dict[str, object]:
        observations = pd.read_parquet(self.paths.canonical_observations)
        hourly = observations.resample("1h").median()
        nodes = pd.DataFrame(self.sensors).set_index("sensor_id")
        declared = {
            frozenset([edge["source"], edge["target"]]) for edge in self.topology["edges"]
        }
        rows = []
        for analyte in ["DO", "ORP"]:
            sensors = nodes[nodes["analyte"] == analyte].index.tolist()
            for left, right in itertools.combinations(sensors, 2):
                pair = hourly[[left, right]].dropna()
                correlation = float(pair.corr(method="spearman").iloc[0, 1])
                residual = pair[left] - pair[right]
                residual_scale = float((residual - residual.median()).abs().median() * 1.4826)
                edge_declared = frozenset([left, right]) in declared
                candidate = (not edge_declared) and abs(correlation) >= 0.80
                rows.append(
                    {
                        "design_topology_id": self.topology["topology_version"],
                        "candidate_graph_id": f"D7-GRAPH-{left}-{right}",
                        "source": left,
                        "target": right,
                        "analyte": analyte,
                        "declared_edge": edge_declared,
                        "candidate_edge_add": candidate,
                        "spearman_correlation": correlation,
                        "robust_residual_scale": residual_scale,
                        "variant_type": "effective_topology_variant" if candidate else "none",
                        "review_status": "unreviewed" if candidate else "not_flagged",
                        "production_impact": "none",
                        "track_id": "shadow_v2",
                    }
                )
        output = pd.DataFrame(rows)
        output.to_parquet(
            self.output_root / "D7_graph_structure_learning_shadow.parquet", index=False
        )
        with pd.ExcelWriter(
            self.output_root / "D7_graph_structure_learning_shadow.xlsx", engine="openpyxl"
        ) as writer:
            output.to_excel(writer, sheet_name="graph_candidates", index=False)
        manifest = {
            "track_id": "shadow_v2",
            "production_impact": "none",
            "auto_topology_update": False,
            "generated_utc": pd.Timestamp.utcnow().isoformat(),
            "candidate_rows": int(output["candidate_edge_add"].sum()),
            "output_hash": hash_object(output.to_dict("records")),
        }
        (self.output_root / "D7_shadow_v2_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        return manifest
