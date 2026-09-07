"""Raw minute -> bounded alignment -> inherited causal decomposition/whitening."""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from inference_inputs import load_raw, cache_folder
from minute_alignment_contract import align_bounded
from frozen_whitener import FrozenWhitener
from runtime import PROJECT, OUTPUT, OFFICIAL, write_json

sys.path.insert(0, str(PROJECT / "1.1 Decomposition"))
from src.baseline.deperiodise import decompose_channel, extra_stl_pass
from src.semantics import PHYS_RANGE


def transform(raw):
    policies = json.loads((OUTPUT / "assets/decomposition_policy_candidate.json").read_text())["models"]
    white = json.loads((OUTPUT / "assets/whitening_reconstruction_candidates.json").read_text())["models"]
    selected = list(policies)
    processed, flags = align_bounded(raw[selected], {s: PHYS_RANGE[s] for s in selected})
    # Three unclosed tail minutes remain raw/auditable, not released transforms.
    processed, flags = processed.iloc[:-3], flags.iloc[:-3]
    residuals, innovations = {}, {}
    for sensor, policy in policies.items():
        if str(processed.index[0]) != policy["absolute_phase_origin"]:
            raise ValueError("Full past journal must preserve absolute harmonic phase")
        config = dict(policy["group_config"])
        # Disable structural selection by constraining both bounds to the frozen order.
        config["harmonic_order_min"] = config["harmonic_order_max"] = policy["selected_order"]
        d = decompose_channel(processed[sensor], config, 1., policy["harmonic_order_fit_days"])
        residual = d["residual"]
        if policy["subhourly_period_min"] is not None:
            residual = extra_stl_pass(residual, policy["subhourly_period_min"])
        for _ in range(policy["extra_stl_passes"]):
            residual = extra_stl_pass(residual, 1440)
        residuals[sensor] = residual
        innovations[sensor] = FrozenWhitener(white[sensor]).transform(residual.to_numpy())
        print("Causal transform", sensor, len(residual), flush=True)
    return processed, flags, pd.DataFrame(residuals), pd.DataFrame(innovations, index=processed.index)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    raw = load_raw(holdout=args.holdout)
    processed, flags, residual, innovation = transform(raw)
    folder = cache_folder(args.holdout)
    for name, frame in [("processed", processed), ("flags", flags), ("residual", residual), ("innovation", innovation)]:
        frame.to_parquet(folder / f"{name}.parquet")
    write_json(folder / "transform_contract.json", dict(raw_minutes=len(raw), released_minutes=len(processed),
        available_delay_minutes=3, structure_refit=False, coefficient_update="inherited_14d_strictly_past_30d",
        whitening_refit=False, new_period=args.holdout))
    if not args.holdout:
        rows = []
        for name, current, archived_name in [("residual", residual, "residual_min"),
                                             ("innovation", innovation, "innovation_min")]:
            old = pd.read_parquet(OFFICIAL / f"1.1 Decomposition/outputs/parquet/{archived_name}.parquet").reindex(current.index)
            for sensor in current:
                rows.append(dict(route=name, sensor_id=sensor, maximum_error=float((current[sensor]-old[sensor]).abs().max()),
                                 na_mismatches=int(current[sensor].isna().ne(old[sensor].isna()).sum())))
        table = pd.DataFrame(rows)
        table.to_csv(OUTPUT / "audit/raw_transform_historical_replay.csv", index=False)
        if table.maximum_error.gt(1e-7).any() or table.na_mismatches.sum():
            raise RuntimeError("Frozen raw transform differs from historical release")


if __name__ == "__main__":
    main()
