"""Historical replay of the inherited causal harmonic update policy."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from runtime import OFFICIAL, OUTPUT, PROJECT, START, sha256, write_json

DECOMP = PROJECT / "1.1 Decomposition"
sys.path.insert(0, str(DECOMP))
from src.config.loader import load_configs
from src.semantics import CHANNEL_META
from src.baseline.deperiodise import decompose_channel, extra_stl_pass
from frozen_whitener import FrozenWhitener


def main() -> None:
    import json
    config = load_configs(DECOMP / "configs")["deperiodise"]
    source = OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min.parquet"
    raw = pd.read_parquet(source)
    archive = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/residual_min.parquet")
    raw = raw[archive.columns]
    archive_z = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/innovation_min.parquet")
    order_table = pd.read_csv(DECOMP / "outputs/tables/harmonic_order_table.csv").set_index("channel")
    refinement = pd.read_csv(DECOMP / "outputs/tables/decomposition_sufficiency.csv").set_index("channel")
    cycle_path = DECOMP / "outputs/tables/aeration_cycle.csv"
    cycles = pd.read_csv(cycle_path).set_index("channel") if cycle_path.is_file() else pd.DataFrame()
    assets = json.loads((OUTPUT / "assets/whitening_reconstruction_candidates.json").read_text(encoding="utf-8"))["models"]
    if raw.index.max() >= START:
        raise ValueError("Decomposition replay is historical-only")
    rows, policies = [], {}
    for sensor in raw:
        group = CHANNEL_META[sensor]["group"]
        group_config = config["groups"][group]
        passes = int(refinement.loc[sensor, "stl_iters"])
        subhourly = int(cycles.loc[sensor, "period_min"]) if sensor in cycles.index else None

        def transform(values):
            dec = decompose_channel(values, group_config, 1.0,
                                    config["causal_fit_first_days"], config["f_test_alpha"])
            if dec["order_record"]["selected_order"] != order_table.loc[sensor, "selected_order"]:
                raise ValueError(f"Historical harmonic order changed: {sensor}")
            residual = dec["residual"]
            if subhourly is not None:
                residual = extra_stl_pass(residual, subhourly)
            for _ in range(passes):
                residual = extra_stl_pass(residual, 1440)
            return residual

        current = transform(raw[sensor])
        difference = (current - archive[sensor]).abs()
        # The final historical week is appended; all update decisions remain old.
        prefix_length = len(raw) - 7 * 1440
        prefix = transform(raw[sensor].iloc[:prefix_length])
        prefix_diff = (prefix - current.iloc[:prefix_length]).abs()
        whitened = FrozenWhitener(assets[sensor]).transform(archive[sensor].to_numpy())
        z_diff = np.abs(whitened - archive_z[sensor].to_numpy())
        chunk_filter = FrozenWhitener(assets[sensor])
        first = chunk_filter.transform(archive[sensor].to_numpy()[:prefix_length])
        resumed = FrozenWhitener(assets[sensor], chunk_filter.checkpoint())
        second = resumed.transform(archive[sensor].to_numpy()[prefix_length:])
        chunk_diff = np.abs(np.r_[first, second] - whitened)
        rows.append({"sensor_id": sensor, "group": group,
                     "selected_order": int(order_table.loc[sensor, "selected_order"]),
                     "fixed_extra_stl_passes": passes, "subhourly_period_min": subhourly,
                     "n_minutes": len(raw), "decomposition_max_error": float(difference.max()),
                     "decomposition_na_mismatches": int((current.isna() != archive[sensor].isna()).sum()),
                     "prefix_max_error": float(prefix_diff.max()),
                     "whitening_max_error": float(np.nanmax(z_diff)),
                     "whitening_chunk_max_error": float(np.nanmax(chunk_diff))})
        policies[sensor] = {
            "group_config": group_config, "selected_order": int(order_table.loc[sensor, "selected_order"]),
            "extra_stl_passes": passes, "subhourly_period_min": subhourly,
            "structure_selection_end": str(raw.index.max()),
            "harmonic_order_fit_days": config["causal_fit_first_days"],
            "coefficient_policy": "14_day_update_from_strictly_past_30_days",
            "future_spectral_reselection": "prohibited",
            "absolute_phase_origin": str(raw.index.min()),
        }
        print(sensor, "residual error", difference.max(), "prefix", prefix_diff.max(), flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/decomposition_and_filter_replay.csv", index=False)
    write_json(OUTPUT / "assets/decomposition_policy_candidate.json", {
        "source_sha256": sha256(source), "models": policies,
        "strict_parameter_frozen": False, "update_rule_frozen": True,
        "raw_to_processed_available_at_audit": "pending",
    })
    write_json(OUTPUT / "audit/decomposition_replay_qa.json", {
        "n_channels": len(table), "historical_decomposition_equal_1e_8": bool(
            table.decomposition_max_error.lt(1e-8).all() and table.decomposition_na_mismatches.eq(0).all()),
        "decomposition_prefix_equal_1e_8": bool(table.prefix_max_error.lt(1e-8).all()),
        "frozen_filter_equal_1e_7": bool(table.whitening_max_error.lt(1e-7).all()),
        "frozen_filter_checkpoint_equal_1e_10": bool(table.whitening_chunk_max_error.lt(1e-10).all()),
        "scope": "historical_processed_input_not_full_raw_to_D1_end_to_end",
        "holdout_opened": False,
    })


if __name__ == "__main__":
    main()
