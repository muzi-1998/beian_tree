"""Decision-time assembly; never backdate a D3 gate or read an open D5 snapshot."""
from __future__ import annotations

import sys

import pandas as pd

from runtime import PROJECT

ROOT = PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration"
sys.path.insert(0, str(ROOT / "src"))
from dqr_aggregation.common import load_config
from dqr_aggregation.pipeline import build_node_scores, build_pair_scores


def asof_evidence(grid, evidence, *, dimension, object_id, lifetime):
    required = {object_id, "timestamp", "available_at"}
    if not required.issubset(evidence):
        raise ValueError(f"{dimension}: explicit information clock required")
    if evidence.duplicated([object_id, "available_at"]).any():
        raise ValueError(f"{dimension}: ambiguous availability")
    if (evidence.available_at < evidence.timestamp).any():
        raise ValueError("Evidence cannot precede its label")
    source = evidence.rename(columns={"timestamp": f"{dimension}_source_label",
                                      "available_at": f"{dimension}_available_at"})
    right_clock = f"{dimension}_available_at"
    merged = pd.merge_asof(grid.sort_values("decision_at"), source.sort_values(right_clock),
                           left_on="decision_at", right_on=right_clock, by=object_id,
                           direction="backward", tolerance=pd.Timedelta(lifetime), allow_exact_matches=True)
    # Expiry is half-open. Do not search backward for an older non-NA score.
    expired = merged[right_clock].notna() & (merged.decision_at - merged[right_clock] >= pd.Timedelta(lifetime))
    payload = [c for c in source if c != object_id]
    if expired.any():
        for column in payload:
            if pd.api.types.is_bool_dtype(merged[column]):
                merged[column] = merged[column].astype("boolean")
            merged[column] = merged[column].mask(expired)
    known = merged[right_clock].notna()
    if (merged.loc[known, right_clock] > merged.loc[known, "decision_at"]).any():
        raise AssertionError("Future evidence in join")
    return merged.sort_values([object_id, "timestamp"]).reset_index(drop=True)


def assemble(d1, d2, d3, d4, d5, labels):
    sensors = sorted(d5.sensor_id.unique())
    grid = pd.MultiIndex.from_product([labels, sensors], names=["timestamp", "sensor_id"]).to_frame(index=False)
    grid["decision_at"] = grid.timestamp + pd.Timedelta(hours=1, minutes=3)
    a = asof_evidence(grid, d1, dimension="D1", object_id="sensor_id", lifetime="1h")
    a["D1_total"] = a.D1_for_validation
    b = asof_evidence(grid, d2, dimension="D2", object_id="sensor_id", lifetime="1h")
    # D2's source closes three minutes before the synchronized decision. Its
    # evidence remains current for the next reporting interval only.
    b = b.rename(columns={"veto_flag": "D2_veto_flag", "usable_tag": "D2_usable_tag"})
    c = asof_evidence(grid, d3, dimension="D3", object_id="sensor_id", lifetime="2h")
    e = asof_evidence(grid, d5, dimension="D5", object_id="sensor_id", lifetime="1h")
    e["D5_report_score"] = e.D5_for_validation
    config = load_config()
    keys = ["timestamp", "sensor_id"]
    # Keep the native aggregation formula; only the evidence join changes.
    node = build_node_scores(config,
        a[keys + ["D1_total"]], b[keys + ["D2_total", "D2_veto_flag", "D2_usable_tag"]],
        c[keys + ["D3_gate_status"]], e)
    audit = grid.copy()
    for dim, aligned in [("D1", a), ("D2", b), ("D3", c), ("D5", e)]:
        audit = audit.merge(aligned[keys + [f"{dim}_source_label", f"{dim}_available_at"]], on=keys, validate="one_to_one")
    node = node.merge(audit, on=keys, validate="one_to_one")
    pair_grid = pd.MultiIndex.from_product([labels, sorted(d4.pair_id.unique())], names=["timestamp", "pair_id"]).to_frame(index=False)
    pair_grid["decision_at"] = pair_grid.timestamp + pd.Timedelta(hours=1, minutes=3)
    d = asof_evidence(pair_grid, d4, dimension="D4", object_id="pair_id", lifetime="1h")
    # Structural identities are static metadata, not a missing-score imputation.
    identities = d4[["pair_id", "sensor_id", "pair_sensor_id"]].drop_duplicates().set_index("pair_id")
    for field in ["sensor_id", "pair_sensor_id"]:
        d[field] = d.pair_id.map(identities[field])
    pair = build_pair_scores(config, node, d)
    return node, pair, audit
