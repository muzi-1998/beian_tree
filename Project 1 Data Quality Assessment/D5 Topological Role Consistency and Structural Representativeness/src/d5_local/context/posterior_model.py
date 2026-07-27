from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from d5_common.math.robust import normalized_entropy


@dataclass(frozen=True)
class PosteriorResult:
    probabilities: np.ndarray
    map_regime: np.ndarray
    map_probability: np.ndarray
    entropy: np.ndarray
    ood_distance: np.ndarray
    ood_threshold: float


class ContextPosteriorModel:
    def __init__(
        self,
        n_regimes: int = 4,
        random_seed: int = 42,
        likelihood_temperature_multiplier: float = 0.25,
    ) -> None:
        self.n_regimes = int(n_regimes)
        self.random_seed = int(random_seed)
        self.likelihood_temperature_multiplier = float(likelihood_temperature_multiplier)
        self.scaler = StandardScaler()
        self.model = KMeans(n_clusters=self.n_regimes, n_init=20, random_state=random_seed)
        self.fill_values: pd.Series | None = None
        self.temperature = 1.0
        self.ood_threshold = float("nan")

    def fit(self, features: pd.DataFrame) -> "ContextPosteriorModel":
        self.fill_values = features.median()
        clean = features.fillna(self.fill_values)
        scaled = self.scaler.fit_transform(clean)
        self.model.fit(scaled)
        distance = self.model.transform(scaled)
        nearest = np.min(distance, axis=1)
        self.temperature = max(float(np.median(nearest)), 1e-6)
        self.ood_threshold = float(np.quantile(nearest, 0.99))
        return self

    def predict(self, features: pd.DataFrame) -> PosteriorResult:
        if self.fill_values is None:
            raise RuntimeError("ContextPosteriorModel must be fitted before predict")
        clean = features.fillna(self.fill_values)
        scaled = self.scaler.transform(clean)
        distance = self.model.transform(scaled)
        shifted = distance - np.min(distance, axis=1, keepdims=True)
        likelihood = np.exp(
            -shifted / max(self.temperature * self.likelihood_temperature_multiplier, 1e-6)
        )
        probabilities = likelihood / likelihood.sum(axis=1, keepdims=True)
        map_regime = np.argmax(probabilities, axis=1)
        map_probability = probabilities[np.arange(len(probabilities)), map_regime]
        return PosteriorResult(
            probabilities=probabilities,
            map_regime=map_regime,
            map_probability=map_probability,
            entropy=normalized_entropy(probabilities),
            ood_distance=np.min(distance, axis=1),
            ood_threshold=self.ood_threshold,
        )
