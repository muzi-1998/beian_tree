"""Freeze first-90-day W1 references; test the recovered PLS prediction formula."""
from __future__ import annotations

import numpy as np
from scipy.stats import wasserstein_distance

from d1_frozen_adapter import read_state, frozen_pls
from runtime import OUTPUT, write_json
import json


def main():
    state = read_state()
    models = json.loads((OUTPUT / "assets/D1_reconstructed_pls_candidates.json").read_text())["models"]
    assets, errors = {}, {}
    for sensor in state["scored_channels"]:
        reference = state["whitened_input_h"][sensor].iloc[:2160].dropna().to_numpy(float)
        rng = np.random.default_rng(42)
        draws = []
        for _ in range(100):
            a = rng.choice(len(reference), size=min(168, len(reference)-1), replace=False)
            b = rng.choice(len(reference), size=min(168, len(reference)-1), replace=False)
            draws.append(wasserstein_distance(reference[a], reference[b]))
        assets[sensor] = dict(reference=reference.tolist(), baseline=max(float(np.percentile(draws, 99.5)), 1e-9),
                              reference_end=str(state["whitened_input_h"].index[2159]),
                              neff=float(state["eff_neff"][sensor]), mode=state["scoring_mode"][sensor])
        z = frozen_pls(state["resid_h"], sensor, models[sensor])
        error = float((z - state["detectors_raw"]["pls_residual_z_hourly"][sensor]).abs().max())
        if error > 1e-8:
            raise RuntimeError(f"Frozen PLS predictor mismatch: {sensor}, {error}")
        errors[sensor] = error
    write_json(OUTPUT / "assets/D1_frozen_detector_references.json", assets)
    write_json(OUTPUT / "audit/D1_full_asset_formula_qa.json", dict(pls_max_errors=errors, passed=True,
        W1_reference="first_90_historical_days", no_new_data_fit=True))


if __name__ == "__main__":
    main()
