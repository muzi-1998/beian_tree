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
    def __init__(
        self,
        bounds: list[PhysicalBound],
        benchmark: BenchmarkWindows,
        sensor_policies: dict[str, dict] | None = None,
    ):
        self.bounds = bounds
        self.benchmark = benchmark
        self.sensor_policies = sensor_policies or {}
        self._index_by_type: dict[str, list[PhysicalBound]] = {}
        for bound in bounds:
            self._index_by_type.setdefault(bound.bound_type, []).append(bound)

    @classmethod
    def build(
        cls,
        physical_bounds_cfg: dict,
        rate_limits_cfg: dict,
        benchmark: BenchmarkWindows,
        version: str = "v2.7.0",
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
                    context_version="physical_contract_v2.7.0",
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
                "source": "provisional_expert_prior",
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
            append_bound(
                sensor_type=sensor_type,
                sensor_scope=f"all_{sensor_type}",
                condition_scope="hardware_specification",
                bound_type="manufacturer_range",
                low=config["manufacturer_range_low"],
                high=config["manufacturer_range_high"],
                unit=config["unit"],
                source="instrument_register",
                benchmark_window_ids=(),
            )
            append_bound(
                sensor_type=sensor_type,
                sensor_scope=f"all_{sensor_type}",
                condition_scope="observed_values",
                bound_type="instrument_veto",
                low=config["instrument_veto_range_low"],
                high=config["instrument_veto_range_high"],
                unit=config["unit"],
                source=config["instrument_veto_basis"],
                benchmark_window_ids=(),
            )

        sensor_policies: dict[str, dict] = {}
        for sensor_type, config in physical_bounds_cfg["sensors"].items():
            sensor_policies[f"all_{sensor_type}"] = {
                "soft_sensitivity_anchor": config.get("soft_sensitivity_anchor", "center"),
            }

        for sensor, override in physical_bounds_cfg.get("sensor_overrides", {}).items():
            sensor_type = sensor.split("_", 1)[0]
            base = physical_bounds_cfg["sensors"][sensor_type]
            physical_low = override.get("physical_soft_low", base["soft_low"])
            operational_high = (
                override["operational_soft_high"]
                if "operational_soft_high" in override
                else base["soft_high"]
            )
            append_bound(
                sensor_type=sensor_type,
                sensor_scope=sensor,
                condition_scope=override.get("process_zone", "sensor_specific"),
                bound_type="soft_value",
                low=physical_low,
                high=operational_high,
                unit=base["unit"],
                source="sensor_specific_physical_and_operational_contract",
                benchmark_window_ids=(),
            )
            if override.get("zero_equivalence_low") is not None:
                append_bound(
                    sensor_type=sensor_type,
                    sensor_scope=sensor,
                    condition_scope=override.get("process_zone", "sensor_specific"),
                    bound_type="zero_equivalence",
                    low=float(override["zero_equivalence_low"]),
                    high=float(physical_low),
                    unit=base["unit"],
                    source=override.get(
                        "zero_equivalence_basis",
                        "provisional_zero_equivalence_tolerance",
                    ),
                    benchmark_window_ids=(),
                )
            sensor_policies[sensor] = {
                "soft_sensitivity_anchor": override.get(
                    "soft_sensitivity_anchor",
                    base.get("soft_sensitivity_anchor", "center"),
                ),
                "process_zone": override.get("process_zone", "sensor_specific"),
                "upper_bound_status": override.get(
                    "upper_bound_basis", "inherits_sensor_type_contract"
                ),
            }
        for sensor_type, config in rate_limits_cfg["rate_limits"].items():
            common = {
                "sensor_type": sensor_type,
                "sensor_scope": f"all_{sensor_type}",
                "condition_scope": "contiguous_finite_observations",
                "unit": config["unit"],
                "source": "provisional_expert_prior",
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
        return cls(bounds, benchmark, sensor_policies)

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

    def hard_bounds(self, sensor_type: str, sensor: str | None = None) -> tuple[float, float]:
        low, high = self._value_bounds("hard_value", sensor_type, sensor)
        if low is None or high is None:
            raise ValueError(f"Hard bounds must be finite for {sensor or sensor_type}")
        return low, high

    def soft_bounds(
        self, sensor_type: str, sensor: str | None = None
    ) -> tuple[float | None, float | None]:
        return self._value_bounds("soft_value", sensor_type, sensor)

    def _value_bounds(
        self, bound_type: str, sensor_type: str, sensor: str | None = None
    ) -> tuple[float | None, float | None]:
        if sensor is not None:
            for bound in self._index_by_type.get(bound_type, []):
                if bound.sensor_scope == sensor:
                    return (
                        float(bound.low) if bound.low is not None else None,
                        float(bound.high) if bound.high is not None else None,
                    )
        for bound in self._index_by_type.get(bound_type, []):
            if bound.sensor_type == sensor_type and bound.sensor_scope == f"all_{sensor_type}":
                return (
                    float(bound.low) if bound.low is not None else None,
                    float(bound.high) if bound.high is not None else None,
                )
        raise KeyError(f"No {bound_type} bounds for {sensor_type}")

    def zero_equivalence_low(self, sensor: str) -> float | None:
        for bound in self._index_by_type.get("zero_equivalence", []):
            if bound.sensor_scope == sensor:
                return float(bound.low) if bound.low is not None else None
        return None

    def soft_sensitivity_anchor(self, sensor_type: str, sensor: str) -> str:
        policy = self.sensor_policies.get(
            sensor, self.sensor_policies.get(f"all_{sensor_type}", {})
        )
        return str(policy.get("soft_sensitivity_anchor", "center"))

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
                    "included_in_D3_score": bound.bound_type
                    in {
                        "hard_value",
                        "soft_value",
                        "rate_soft",
                        "rate_hard",
                        "instrument_veto",
                        "zero_equivalence",
                    },
                    "validator_passed": bound.validator_passed,
                }
            )
        return pd.DataFrame(rows)
