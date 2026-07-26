from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from d5_common.hashing import hash_object
from d5_common.math.calibration import empirical_quality_score


@dataclass(frozen=True)
class MappingRecord:
    mapping_id: str
    subscore: str
    risk_metric: str
    analyte: str
    regime_id: int | None
    zone_id: str | None
    mapping_scope: str
    n_calibration: int
    q50: float
    q75: float
    q90: float
    q97_5: float
    mapping_version: str
    mapping_hash: str


class ScoreMapper:
    RISK_TO_Q = {
        "risk_profile": "Q_profile",
        "risk_gradient": "Q_gradient",
        "risk_rank": "Q_rank",
        "risk_rep": "Q_rep",
    }

    def __init__(self, mapping_version: str, gamma: float = 1.0) -> None:
        self.mapping_version = mapping_version
        self.gamma = float(gamma)
        self.references: dict[tuple[str, str, int | None, str | None], np.ndarray] = {}
        self.records: list[MappingRecord] = []

    def fit_transform(self, frame: pd.DataFrame, reference_end: pd.Timestamp) -> pd.DataFrame:
        output = frame.copy()
        reference = output[
            (output["timestamp"] <= reference_end)
            & output["window_coverage"].ge(0.80)
            & output["regime_state"].ne("OODHold")
        ]
        for risk_column, q_column in self.RISK_TO_Q.items():
            output[q_column] = np.nan
            for key, target_rows in output.groupby(["analyte", "active_regime_id", "zone_id"], dropna=False):
                analyte, regime, zone = key
                exact = reference[
                    (reference["analyte"] == analyte)
                    & (reference["active_regime_id"] == regime)
                    & (reference["zone_id"] == zone)
                ][risk_column].dropna()
                variable_regime = reference[
                    (reference["analyte"] == analyte)
                    & (reference["active_regime_id"] == regime)
                ][risk_column].dropna()
                variable = reference[reference["analyte"] == analyte][risk_column].dropna()
                if analyte == "ORP":
                    calibration, scope = variable, "variable_public"
                    resolved_regime, resolved_zone = None, None
                elif len(exact) >= 100:
                    calibration, scope = exact, "variable_regime_zone"
                    resolved_regime, resolved_zone = int(regime), str(zone)
                elif len(variable_regime) >= 100:
                    calibration, scope = variable_regime, "variable_regime"
                    resolved_regime, resolved_zone = int(regime), None
                else:
                    calibration, scope = variable, "variable_public"
                    resolved_regime, resolved_zone = None, None
                if len(calibration) < 20:
                    continue
                ref_key = (risk_column, str(analyte), resolved_regime, resolved_zone)
                values = calibration.to_numpy(dtype=float)
                self.references.setdefault(ref_key, values)
                row_index = target_rows.index
                output.loc[row_index, q_column] = empirical_quality_score(
                    output.loc[row_index, risk_column].to_numpy(dtype=float),
                    values,
                    gamma=self.gamma,
                )
                quantiles = np.quantile(values, [0.50, 0.75, 0.90, 0.975])
                payload = {
                    "risk": risk_column,
                    "analyte": str(analyte),
                    "regime": resolved_regime,
                    "zone": resolved_zone,
                    "scope": scope,
                    "n": len(values),
                    "quantiles": quantiles.tolist(),
                    "version": self.mapping_version,
                }
                mapping_id = f"D5-{q_column}-{analyte}-R{resolved_regime}-Z{resolved_zone}"
                record = MappingRecord(
                    mapping_id=mapping_id,
                    subscore=q_column,
                    risk_metric=risk_column,
                    analyte=str(analyte),
                    regime_id=resolved_regime,
                    zone_id=resolved_zone,
                    mapping_scope=scope,
                    n_calibration=len(values),
                    q50=float(quantiles[0]),
                    q75=float(quantiles[1]),
                    q90=float(quantiles[2]),
                    q97_5=float(quantiles[3]),
                    mapping_version=self.mapping_version,
                    mapping_hash=hash_object(payload),
                )
                if record not in self.records:
                    self.records.append(record)
        return output

    def records_frame(self) -> pd.DataFrame:
        return pd.DataFrame([record.__dict__ for record in self.records]).drop_duplicates(
            subset=["mapping_id", "mapping_hash"]
        )
