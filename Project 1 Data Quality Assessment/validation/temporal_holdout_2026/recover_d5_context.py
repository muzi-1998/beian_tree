"""Reconstruct only the archived D5 context on its absolute historical reference."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from frozen_context import FrozenContext
from runtime import (D5_REFERENCE_END, DIMENSIONS, OFFICIAL, OUTPUT, PROJECT,
                     START, assert_fit_before_holdout, sha256, write_json)

D5 = PROJECT / DIMENSIONS["D5"]
sys.path.insert(0, str(D5 / "src"))
from d5_common.config import load_yaml
from d5_common.hashing import hash_object
from d5_local.context import ContextPosteriorModel, GlobalProcessContextBuilder, RegimeHysteresisController
from d5_local.contracts import TopologyRegistry
from d5_local.data import SnapshotBuilder


def main() -> None:
    topology = TopologyRegistry.load(D5 / "configs/common")
    config = load_yaml(D5 / "configs/local/d5_local.yaml")
    windows = load_yaml(D5 / "configs/common/windows.yaml")
    source = OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet"
    observations = pd.read_parquet(source)
    if observations.index.max() >= START:
        raise ValueError("Expected the frozen pre-holdout canonical input, not annual data")
    floors = topology.nodes.loc[topology.nodes.floor_flag, "sensor_id"].tolist()
    snapshots = SnapshotBuilder(windows["snapshot_main_minutes"],
                                windows["snapshot_min_observations"]).build(observations, floors).values
    features = GlobalProcessContextBuilder(topology).build(snapshots)
    training = features.loc[:D5_REFERENCE_END]
    assert_fit_before_holdout(training.index, D5_REFERENCE_END)
    print(f"Reconstruct D5 context: {len(training)} historical snapshots; no later inputs", flush=True)
    model = ContextPosteriorModel(
        n_regimes=config["context_regimes"], random_seed=config["random_seed"],
        likelihood_temperature_multiplier=config["posterior_temperature_multiplier"],
    ).fit(training)
    asset = {
        "scope": "plant_global_robust_context", "feature_names": features.columns.tolist(),
        "cluster_centers": model.model.cluster_centers_.tolist(),
        "scaler_mean": model.scaler.mean_.tolist(), "scaler_scale": model.scaler.scale_.tolist(),
        "temperature": model.temperature,
        "likelihood_temperature_multiplier": model.likelihood_temperature_multiplier,
        "ood_threshold": model.ood_threshold,
    }
    legacy_hash = hash_object(asset)
    asset.update(fill_values=model.fill_values.reindex(features.columns).tolist(),
                 fitted_until=str(D5_REFERENCE_END),
                 source_sha256=sha256(source), legacy_model_asset_hash=legacy_hash,
                 recovered_historical_only=True)
    frozen = FrozenContext.from_dict(asset)
    probabilities, distance = frozen.predict(features)
    result = model.predict(features)
    controller = RegimeHysteresisController(load_yaml(D5 / "configs/local/hysteresis.yaml"))
    replay = controller.replay(snapshots.index, probabilities, result.entropy, distance,
                               frozen.ood_threshold, "DO_1_1", windows["snapshot_main_minutes"])
    archived_path = D5 / "outputs/local/D5_regime_state.parquet"
    archived = pd.read_parquet(archived_path)
    old = archived.loc[archived.sensor_id.eq("DO_1_1")].set_index("timestamp")
    now = replay.set_index("timestamp").reindex(old.index)
    old_prob = np.stack(old.posterior_vector)
    error = np.max(np.abs(old_prob - probabilities), axis=1)
    rows = []
    for month, part in old.groupby(old.index.to_period("M")):
        idx = old.index.get_indexer(part.index)
        rows.append({"month": str(month), "n_snapshots": len(part),
                     "posterior_max_abs_error": float(error[idx].max()),
                     "map_regime_mismatches": int((now.loc[part.index, "map_regime_id"] != part.map_regime_id).sum()),
                     "active_regime_mismatches": int((now.loc[part.index, "active_regime_id"] != part.active_regime_id).sum()),
                     "state_mismatches": int((now.loc[part.index, "regime_state"] != part.regime_state).sum())})
    prefix_n = len(features) - 7 * 144
    prefix_p, prefix_d = frozen.predict(features.iloc[:prefix_n])
    chunks = [frozen.predict(part)[0] for start in range(0, len(features), 144)
              if len(part := features.iloc[start:start + 144])]
    archived_refs = archived.model_asset_ref.unique().tolist()
    checks = {
        "archived_model_hash_equal": archived_refs == [f"embedded:{legacy_hash}"],
        "archived_posterior_equal_1e_10": bool(error.max() < 1e-10),
        "archived_active_regime_exact": bool((now.active_regime_id == old.active_regime_id).all()),
        "archived_state_exact": bool((now.regime_state == old.regime_state).all()),
        "predictor_prefix_invariance": bool(np.allclose(prefix_p, probabilities[:prefix_n], atol=1e-12, rtol=0)),
        "predictor_chunk_equivalence": bool(np.allclose(np.concatenate(chunks), probabilities, atol=1e-12, rtol=0)),
        "no_holdout_in_fit": bool(training.index.max() < START),
    }
    table = pd.DataFrame(rows)
    (OUTPUT / "audit").mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT / "audit/D5_context_historical_replay.csv", index=False)
    write_json(OUTPUT / "audit/D5_context_recovery_qa.json", {
        "checks": checks, "all_passed": all(checks.values()),
        "maximum_posterior_error": float(error.max()),
        "source_sha256": sha256(source), "archived_state_sha256": sha256(archived_path),
        "scope": "context_model_and_historical_hysteresis_only_not_full_D5_score",
        "streaming_hysteresis_checkpoint": "pending_chunk_state_adapter",
    })
    # A rebuilt estimator has a new content identity even when predictions are
    # numerically equivalent. Keep byte identity separate from replay evidence.
    asset["archived_model_refs"] = archived_refs
    asset["release_byte_identity"] = checks["archived_model_hash_equal"]
    asset["historical_numeric_equivalence"] = all(
        value for key, value in checks.items() if key != "archived_model_hash_equal"
    )
    write_json(OUTPUT / "assets/D5_reconstructed_context_candidate.json", asset)
    print(checks, flush=True)


if __name__ == "__main__":
    main()
