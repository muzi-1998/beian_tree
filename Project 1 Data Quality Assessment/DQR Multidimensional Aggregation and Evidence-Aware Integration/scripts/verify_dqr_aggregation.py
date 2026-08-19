from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dqr_aggregation.common import OUTPUT_ROOT, load_config, sha256_file  # noqa: E402
from dqr_aggregation.figures import ALL_STEMS, STEMS  # noqa: E402
from dqr_aggregation.pipeline import verify_frozen_inputs  # noqa: E402


def verify() -> dict[str, object]:
    config = load_config()
    verify_frozen_inputs(config)
    node = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_node_hourly.parquet")
    pair = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_pair_hourly.parquet")
    dimension = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_dimension_long.parquet")
    checks: dict[str, bool] = {}
    full_node = node["Q_node_full"].notna()
    checks["node_formula"] = bool(
        np.allclose(
            node.loc[full_node, "Q_node_full"],
            node.loc[full_node, ["D1_total", "D2_total", "D5_report_score"]].mean(axis=1),
            rtol=0,
            atol=1e-12,
        )
    )
    full_pair = pair["Q_pair_full"].notna()
    checks["pair_formula"] = bool(
        np.allclose(
            pair.loc[full_pair, "Q_pair_full"],
            pair.loc[full_pair, ["left_Q_node_full", "right_Q_node_full", "D4_raw"]].mean(axis=1),
            rtol=0,
            atol=1e-12,
        )
    )
    checks["D3_gate_only"] = bool(
        dimension.loc[dimension["dimension"].eq("D3"), "score_1to5"].isna().all()
    )
    checks["D4_pair_only"] = bool(
        dimension.loc[dimension["dimension"].eq("D4"), "object_type"].eq("pair").all()
    )
    checks["D5_missing_is_NA"] = bool(
        dimension.loc[
            dimension["dimension"].eq("D5") & ~dimension["report_eligible"],
            "score_1to5",
        ].isna().all()
    )
    manifest_path = OUTPUT_ROOT / "manifests" / "DQR_publication_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_manifest_path = OUTPUT_ROOT / "manifests" / "DQR_run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    hash_checks = []
    for artifact in manifest["artifacts"]:
        path = OUTPUT_ROOT / artifact["relative_path"]
        hash_checks.append(path.exists() and sha256_file(path) == artifact["sha256"])
    checks["publication_manifest_hashes"] = bool(hash_checks and all(hash_checks))
    checks["manifest_run_id_consistency"] = bool(
        manifest["run_id"] == run_manifest["run_id"]
    )
    qa = json.loads((OUTPUT_ROOT / "validation" / "DQR_figure_qa.json").read_text(encoding="utf-8"))
    checks["figure_qa"] = bool(qa["passed"])
    checks["five_main_figures"] = all(
        (OUTPUT_ROOT / "figures" / f"{stem}.{suffix}").exists()
        for stem in STEMS
        for suffix in ("png", "pdf", "svg", "tiff")
    )
    checks["all_declared_figures"] = all(
        (OUTPUT_ROOT / "figures" / f"{stem}.{suffix}").exists()
        for stem in ALL_STEMS
        for suffix in ("png", "pdf", "svg", "tiff")
    )
    checks["selection_composition_closure"] = bool(
        run_manifest["summary"]["selection_composition_decomposition"][
            "absolute_closure_error"
        ]
        <= 1e-12
    )
    passed = all(checks.values())
    result = {"passed": passed, "checks": checks, "run_id": manifest["run_id"]}
    if not passed:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
