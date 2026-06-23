"""src/config/models.py
Strong-typed config models built on Pydantic v2.
Per spec §4.1: validate immediately at load time; no bare-dict propagation.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Window models
# ─────────────────────────────────────────────────────────────────────────────

class WindowSpec(BaseModel):
    """Single detector window: hours + optional fast/confirm horizons."""
    main_h: float
    fast_h: Optional[float] = None
    confirm_h: Optional[float] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("main_h")
    @classmethod
    def _main_h_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"main_h must be > 0; got {v}")
        return v

    @classmethod
    def from_dict(cls, d: dict) -> "WindowSpec":
        d = dict(d)
        main_h    = d.pop("main_h")
        fast_h    = d.pop("fast_h", None)
        confirm_h = d.pop("confirm_h", None)
        return cls(main_h=main_h, fast_h=fast_h, confirm_h=confirm_h, extra=d)


class WindowConfig(BaseModel):
    """All detector window specs, loaded from configs/windows.yaml."""
    spike:       WindowSpec
    step:        WindowSpec
    drift:       WindowSpec
    freeze:      Dict[str, Any]          # kept as raw dict (float values in hours)
    regime:      WindowSpec
    aggregation: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "WindowConfig":
        return cls(
            spike       = WindowSpec.from_dict(d["spike"]),
            step        = WindowSpec.from_dict(d["step"]),
            drift       = WindowSpec.from_dict(d["drift"]),
            freeze      = d["freeze"],
            regime      = WindowSpec.from_dict(d["regime"]),
            aggregation = d.get("aggregation", {}),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mapping models
# ─────────────────────────────────────────────────────────────────────────────

class MappingEntry(BaseModel):
    """Score mapping function for one detector."""
    function:   str
    metric:     str
    k:          Optional[float] = None
    x0:         Optional[float] = None
    thresholds: Optional[List[float]] = None
    scores:     Optional[List[float]] = None
    breaks:     Optional[List[float]] = None
    direction:  Optional[str] = "high_quality_low_metric"
    rate_floor: Optional[float] = 0.0

    @model_validator(mode="after")
    def _validate_function_params(self) -> "MappingEntry":
        valid_fns = {"logistic", "piecewise", "stepwise_duration"}
        if self.function not in valid_fns:
            raise ValueError(f"function must be in {valid_fns}; got '{self.function}'")
        if self.function == "logistic":
            if self.k is None or self.x0 is None:
                raise ValueError(f"logistic mapping needs k and x0")
        if self.function == "piecewise":
            if not self.thresholds or not self.scores:
                raise ValueError("piecewise mapping needs thresholds and scores")
            if len(self.thresholds) != len(self.scores):
                raise ValueError("piecewise: len(scores) must equal len(thresholds)")
        if self.function == "stepwise_duration":
            if not self.breaks or not self.scores:
                raise ValueError("stepwise_duration needs breaks and scores")
            if len(self.breaks) + 1 != len(self.scores):
                raise ValueError("stepwise_duration: len(scores) must equal len(breaks)+1")
        return self

    @classmethod
    def from_dict(cls, d: dict) -> "MappingEntry":
        return cls(
            function   = d["function"],
            metric     = d["metric"],
            k          = d.get("k"),
            x0         = d.get("x0"),
            thresholds = d.get("thresholds"),
            scores     = d.get("scores"),
            breaks     = d.get("breaks"),
            direction  = d.get("direction", "high_quality_low_metric"),
            rate_floor = d.get("rate_floor", 0.0),
        )


class FreezeMappingConfig(BaseModel):
    """Combined freeze detector mapping (RLE + low_var + unique_ratio)."""
    rle:              MappingEntry
    low_var:          MappingEntry
    unique:           MappingEntry
    combined_weights: Dict[str, float]

    @field_validator("combined_weights")
    @classmethod
    def _weights_sum_to_one(cls, v: Dict[str, float]) -> Dict[str, float]:
        s = sum(v.values())
        if abs(s - 1.0) > 1e-3:
            raise ValueError(f"freeze.combined_weights sum != 1.0 (got {s:.4f})")
        return v

    @classmethod
    def from_dict(cls, d: dict) -> "FreezeMappingConfig":
        return cls(
            rle              = MappingEntry.from_dict(d["rle"]),
            low_var          = MappingEntry.from_dict(d["low_var"]),
            unique           = MappingEntry.from_dict(d["unique"]),
            combined_weights = d["combined_weights"],
        )


class MappingConfig(BaseModel):
    """All detector score mappings, loaded from configs/mapping.yaml."""
    spike:  MappingEntry
    step:   MappingEntry
    drift:  MappingEntry
    freeze: FreezeMappingConfig
    regime: MappingEntry

    @classmethod
    def from_dict(cls, d: dict) -> "MappingConfig":
        return cls(
            spike  = MappingEntry.from_dict(d["spike"]),
            step   = MappingEntry.from_dict(d["step"]),
            drift  = MappingEntry.from_dict(d["drift"]),
            freeze = FreezeMappingConfig.from_dict(d["freeze"]),
            regime = MappingEntry.from_dict(d["regime"]),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation / Rules models (kept for standalone use; ProjectConfig uses raw dicts)
# ─────────────────────────────────────────────────────────────────────────────

class AggregationConfig(BaseModel):
    """D1 weighted aggregation parameters."""
    weights:      Dict[str, float]
    lambda_blend: float

    @model_validator(mode="after")
    def _validate_aggregation(self) -> "AggregationConfig":
        s = sum(self.weights.values())
        if abs(s - 1.0) > 1e-3:
            raise ValueError(f"aggregation weights sum != 1.0 (got {s:.4f})")
        required = {"spike", "step", "drift", "freeze", "regime"}
        missing = required - set(self.weights.keys())
        if missing:
            raise ValueError(f"aggregation weights missing keys: {missing}")
        if not (0.0 <= self.lambda_blend <= 1.0):
            raise ValueError(f"lambda_blend must be in [0, 1]; got {self.lambda_blend}")
        return self

    @classmethod
    def from_dict(cls, d: dict) -> "AggregationConfig":
        return cls(weights=d["weights"], lambda_blend=d["lambda_blend"])


# ─────────────────────────────────────────────────────────────────────────────
# Top-level project config
# ─────────────────────────────────────────────────────────────────────────────

class ProjectConfig(BaseModel):
    """Root config object; rules / state_machine / paths stored as raw dicts
    for direct access via cfg.rules["..."] in the pipeline."""
    windows:       WindowConfig
    mapping:       MappingConfig
    rules:         Dict[str, Any]   # raw rules.yaml
    state_machine: Dict[str, Any]   # raw state_machine.yaml
    paths:         Dict[str, Any]   # raw paths.yaml
