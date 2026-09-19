"""Recover full empirical references from archived pre-boundary evidence only."""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from runtime import D5_REFERENCE_END, DIMENSIONS, OUTPUT, PROJECT, sha256, write_json

ROOT = PROJECT / DIMENSIONS["D5"]
sys.path.insert(0, str(ROOT / "src"))
from d5_common.config import load_yaml
from d5_local.contracts import TopologyRegistry
from d5_local.scoring.mapper import ScoreMapper


def main():
    folder = ROOT / "outputs/local"
    paths = {name: folder / filename for name, filename in {
        "evidence": "D5_spatial_evidence.parquet", "scores": "D5_main_scores_hourly.parquet",
        "support": "D5_support_assessment.parquet", "templates": "D5_spatial_templates.template_bundle.json",
        "mapping": "D5_mapping_params.xlsx"}.items()}
    evidence = pd.read_parquet(paths["evidence"])
    scores = pd.read_parquet(paths["scores"])
    reference = evidence.merge(scores[["timestamp", "sensor_id", "regime_state"]],
                               on=["timestamp", "sensor_id"], validate="one_to_one")
    nodes = TopologyRegistry.load(ROOT / "configs/common").nodes.set_index("sensor_id")
    reference["zone_id"] = reference.sensor_id.map(nodes.zone_id)
    reference = reference.loc[reference.timestamp.le(D5_REFERENCE_END)
                              & reference.window_coverage.ge(.8) & reference.regime_state.ne("OODHold")]
    records = pd.read_excel(paths["mapping"])
    references = []
    for row in records.itertuples(index=False):
        part = reference.loc[reference.analyte.eq(row.analyte)]
        regime = None if pd.isna(row.regime_id) else int(row.regime_id)
        zone = None if pd.isna(row.zone_id) else row.zone_id
        if regime is not None:
            part = part.loc[part.active_regime_id.eq(regime)]
        if zone is not None:
            part = part.loc[part.zone_id.eq(zone)]
        values = np.sort(part[row.risk_metric].dropna().to_numpy(float))
        if len(values) != row.n_calibration or not np.allclose(
                np.quantile(values, [.5, .75, .9, .975]), [row.q50, row.q75, row.q90, row.q97_5], atol=1e-10):
            raise ValueError(f"Archived ECDF reconstruction mismatch: {row.mapping_id}")
        references.append(dict(risk_metric=row.risk_metric, analyte=row.analyte,
                               regime_id=regime, zone_id=zone, values=values.tolist()))
    support = pd.read_parquet(paths["support"])
    def clean_records(frame):
        return json.loads(frame.to_json(orient="records", date_format="iso"))
    asset = dict(fitted_until=str(D5_REFERENCE_END),
                 gamma=load_yaml(ROOT / "configs/local/mapping.yaml")["gamma"],
                 references=references, records=clean_records(records), support=clean_records(support),
                 templates=json.loads(paths["templates"].read_text(encoding="utf-8")),
                 dependencies={k: sha256(v) for k, v in paths.items()},
                 policy="archived_ECDF_reconstruction_no_new_fit_no_support_upgrade")
    write_json(OUTPUT / "assets/D5_frozen_inference.json", asset)
    print(f"Frozen {len(references)} empirical distributions; {len(support)} support rows", flush=True)


if __name__ == "__main__":
    main()
