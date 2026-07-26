"""Fixed D3 physical thresholds and benchmark-derived diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.common.benchmark_windows import BenchmarkWindows, FixedTailThreshold
from src.common.exceptions import ConfigValidationError, TailRateContractViolation


BOUNDARY_SOURCE_WHITELIST = ("benchmark_quantile", "instrument", "expert")


@dataclass(frozen=True)
class PhysicalBound:
    threshold_id: str
    sensor_type: str
    sensor_scope: str
    condition_scope: str
    bound_type: str
    low: Optional[float]
    high: Optional[float]
    unit: str
    source: str
    benchmark_window_ids: tuple[str, ...]
    benchmark_version: str
    context_version: str
    version: str
    validator_passed: bool


class ThresholdStore:
    def __init__(self, bounds: list[PhysicalBound], benchmark: BenchmarkWindows):
        self.bounds = bounds
        self.benchmark = benchmark
        self._index_by_type: dict[str, list[PhysicalBound]] = {}
        for bound in bounds:
            self._index_by_type.setdefault(bound.bound_type, []).append(bound)

    @classmethod
    def build(
        cls,
        physical_bounds_cfg: dict,
        rate_limits_cfg: dict,
        benchmark: BenchmarkWindows,
        version: str = "v2.2.0",
    ) -> "ThresholdStore":
        bounds: list[PhysicalBound] = []
        threshold_number = 0

        def append_bound(**kwargs) -> None:
            nonlocal threshold_number
            threshold_number += 1
            bounds.append(
                PhysicalBound(
                    threshold_id=f"T{threshold_number:04d}",
                    benchmark_version=benchmark.version,
                    context_version="fixed_physical_contract_v2.2",
                    version=version,
                    validator_passed=True,
                    **kwargs,
                )
            )

        for sensor_type, config in physical_bounds_cfg["sensors"].items():
            common = {
                "sensor_type": sensor_type,
                "sensor_scope": f"all_{sensor_type}",
                "condition_scope": "all_observed_conditions",
                "unit": config["unit"],
                "source": "expert",
                "benchmark_window_ids": (),
            }
            append_bound(
                bound_type="hard_value",
                low=config["hard_low"],
                high=config["hard_high"],
                **common,
            )
            append_bound(
                bound_type="soft_value",
                low=config["soft_low"],
                high=config["soft_high"],
                **common,
            )

        for sensor_type, config in rate_limits_cfg["rate_limits"].items():
            common = {
                "sensor_type": sensor_type,
                "sensor_scope": f"all_{sensor_type}",
                "condition_scope": "contiguous_finite_observations",
                "unit": config["unit"],
                "source": "expert",
                "benchmark_window_ids": (),
            }
            append_bound(
                bound_type="rate_soft", low=None, high=config["rate_soft"], **common
            )
            append_bound(
                bound_type="rate_hard", low=None, high=config["rate_hard"], **common
            )

        for (sensor, side), fixed_tail in benchmark._fixed_tails.items():
            sensor_type = "DO" if sensor.startswith("DO") else "ORP"
            append_bound(
                sensor_type=sensor_type,
                sensor_scope=sensor,
                condition_scope="diagnostic_only_not_scored",
                bound_type="boundary",
                low=fixed_tail.value if side == "low" else None,
                high=fixed_tail.value if side == "high" else None,
                unit=physical_bounds_cfg["sensors"][sensor_type]["unit"],
                source=fixed_tail.source,
                benchmark_window_ids=fixed_tail.benchmark_window_ids,
            )

        cls.validate(bounds)
        return cls(bounds, benchmark)

    @staticmethod
    def validate(bounds: list[PhysicalBound]) -> None:
        for bound in bounds:
            if bound.bound_type != "boundary":
                continue
            if bound.source not in BOUNDARY_SOURCE_WHITELIST:
                raise ConfigValidationError(
                    f"boundary threshold {bound.threshold_id} source='{bound.source}' "
                    f"not in whitelist {BOUNDARY_SOURCE_WHITELIST}"
                )
            if bound.source == "benchmark_quantile" and not bound.benchmark_window_ids:
                raise ConfigValidationError(
                    f"boundary threshold {bound.threshold_id} with source="
                    "benchmark_quantile has empty benchmark_window_ids"
                )

    def hard_bounds(self, sensor_type: str) -> tuple[float, float]:
        return self._value_bounds("hard_value", sensor_type)

    def soft_bounds(self, sensor_type: str) -> tuple[float, float]:
        return self._value_bounds("soft_value", sensor_type)

    def _value_bounds(self, bound_type: str, sensor_type: str) -> tuple[float, float]:
        for bound in self._index_by_type.get(bound_type, []):
            if bound.sensor_type == sensor_type:
                return float(bound.low), float(bound.high)
        raise KeyError(f"No {bound_type} bounds for {sensor_type}")

    def rate_limits(self, sensor_type: str) -> tuple[float, float]:
        soft = next(
            (b.high for b in self._index_by_type.get("rate_soft", []) if b.sensor_type == sensor_type),
            None,
        )
        hard = next(
            (b.high for b in self._index_by_type.get("rate_hard", []) if b.sensor_type == sensor_type),
            None,
        )
        if soft is None or hard is None:
            raise KeyError(f"No rate limits for {sensor_type}")
        return float(soft), float(hard)

    def get_fixed_tail_threshold(
        self,
        sensor: str,
        side: str,
        source_allowed=BOUNDARY_SOURCE_WHITELIST,
    ) -> FixedTailThreshold:
        fixed_tail = self.benchmark.get_fixed_tail_threshold(
            sensor, side, source_allowed=source_allowed
        )
        if fixed_tail.source not in source_allowed:
            raise TailRateContractViolation(
                f"tail threshold source '{fixed_tail.source}' not in whitelist {source_allowed}"
            )
        return fixed_tail

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for bound in self.bounds:
            benchmark_ids = bound.benchmark_window_ids
            rows.append(
                {
                    "threshold_id": bound.threshold_id,
                    "sensor_type": bound.sensor_type,
                    "sensor_scope": bound.sensor_scope,
                    "condition_scope": bound.condition_scope,
                    "bound_type": bound.bound_type,
                    "low": bound.low,
                    "high": bound.high,
                    "unit": bound.unit,
                    "source": bound.source,
                    "benchmark_window_ids": ",".join(benchmark_ids[:3])
                    + ("..." if len(benchmark_ids) > 3 else ""),
                    "n_benchmark_window_ids": len(benchmark_ids),
                    "benchmark_version": bound.benchmark_version,
                    "context_version": bound.context_version,
                    "version": bound.version,
                    "included_in_D3_score": bound.bound_type != "boundary",
                    "validator_passed": bound.validator_passed,
                }
            )
        return pd.DataFrame(rows)
