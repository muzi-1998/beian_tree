from __future__ import annotations

import numpy as np
import pandas as pd


class UncertaintyEngine:
    SUPPORT_UNCERTAINTY = {"L3": 0.10, "L2": 0.35, "L1": 0.65, "L0": 1.00}

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["U_regime"] = output["regime_entropy"].clip(0.0, 1.0)
        output["U_support"] = output["support_level"].map(self.SUPPORT_UNCERTAINTY).fillna(1.0)
        output["U_coverage"] = (1.0 - output["window_coverage"]).clip(0.0, 1.0)
        condition_column = (
            "covariance_condition_number"
            if "covariance_condition_number" in output.columns
            else "condition_number"
        )
        condition = output[condition_column].astype(float)
        output["U_covariance"] = np.clip(np.log10(condition.clip(lower=1.0)) / 3.0, 0.0, 1.0)
        output["uncertainty"] = (
            0.35 * output["U_regime"]
            + 0.30 * output["U_support"]
            + 0.20 * output["U_coverage"]
            + 0.15 * output["U_covariance"]
        ).clip(0.0, 1.0)
        output["confidence"] = 1.0 - output["uncertainty"]
        return output
