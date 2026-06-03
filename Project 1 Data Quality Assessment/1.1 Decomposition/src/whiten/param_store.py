"""src/whiten/param_store.py — versioned whitening params + atomic hot-swap.

Single-plant / 14-channel scale -> in-process thread-safe dict (plan §6.4 (三)):
no Redis. The fast track reads an immutable snapshot; the slow track publishes
a new immutable `WhitenModel`. Swap = reference exchange (GIL-atomic).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import threading
import numpy as np


@dataclass(frozen=True)
class WhitenModel:
    version: str
    p: int
    q: int
    ar: np.ndarray                 # phi_1..phi_p  (AR coeffs)
    ma: np.ndarray                 # theta_1..theta_q (MA coeffs)
    intercept: float = 0.0
    garch: dict | None = None      # {'omega','alpha','beta'} or None
    warmup_state: dict = field(default_factory=dict)  # eps[], eta[], sigma2
    diagnostics: dict = field(default_factory=dict)


class ParamStore:
    def __init__(self):
        self._d: dict[str, WhitenModel] = {}
        self._lock = threading.Lock()

    def latest(self, ch: str) -> WhitenModel | None:
        return self._d.get(ch)             # snapshot read (atomic ref)

    def publish(self, ch: str, m: WhitenModel) -> None:
        with self._lock:
            self._d[ch] = m                # atomic ref exchange

    def versions(self) -> dict:
        return {ch: m.version for ch, m in self._d.items()}
