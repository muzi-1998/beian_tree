from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EvidenceBundle:
    risk_profile: pd.DataFrame
    risk_gradient: pd.DataFrame
    risk_rank: pd.DataFrame
    risk_rep: pd.DataFrame
    loo_prediction: pd.DataFrame
    normalized_loo_residual: pd.DataFrame
    graph_energy_full: pd.DataFrame
    graph_energy_replaced: pd.DataFrame
    energy_delta: pd.DataFrame
