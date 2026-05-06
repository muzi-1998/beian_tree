"""src/config/models.py
Strong-typed config models (dataclass-based; pydantic-equivalent semantics).
Per spec §4.1: validate immediately at load time; no bare-dict propagation.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any


def _require(cond, msg):
    if not cond:
        raise ValueError(f"[ConfigValidation] {msg}")


@dataclass
class WindowSpec:
    main_h: float
    fast_h: Optional[float] = None
    confirm_h: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict):
        d = dict(d)
        main_h = d.pop("main_h"); fast_h = d.pop("fast_h", None); confirm_h = d.pop("confirm_h", None)
        _require(main_h > 0, f"main_h must be > 0; got {main_h}")
        return cls(main_h=main_h, fast_h=fast_h, confirm_h=confirm_h, extra=d)


@dataclass
class WindowConfig:
    spike: WindowSpec
    step: WindowSpec
    drift: WindowSpec
    freeze: Dict
    regime: WindowSpec
    aggregation: Dict

    @classmethod
    def from_dict(cls, d: Dict):
        return cls(
            spike  = WindowSpec.from_dict(d["spike"]),
            step   = WindowSpec.from_dict(d["step"]),
            drift  = WindowSpec.from_dict(d["drift"]),
            freeze = d["freeze"],
            regime = WindowSpec.from_dict(d["regime"]),
            aggregation = d["aggregation"],
        )


@dataclass
class MappingEntry:
    function: str
    metric: str
    k: Optional[float] = None
    x0: Optional[float] = None
    thresholds: Optional[List[float]] = None
    scores: Optional[List[float]] = None
    breaks: Optional[List[float]] = None
    direction: Optional[str] = "high_quality_low_metric"
    rate_floor: Optional[float] = 0.0

    @classmethod
    def from_dict(cls, d: Dict):
        valid_fns = {"logistic", "piecewise", "stepwise_duration"}
        _require(d["function"] in valid_fns,
                 f"function must be in {valid_fns}; got {d['function']}")
        if d["function"] == "logistic":
            _require(d.get("k") is not None and d.get("x0") is not None,
                     f"logistic mapping needs k and x0; got {d}")
        if d["function"] == "piecewise":
            _require(len(d["thresholds"]) == len(d["scores"]),
                     "piecewise: len(scores) must = len(thresholds); "
                     "convention: x <= thresholds[i] gets scores[i], else scores[-1]")
        if d["function"] == "stepwise_duration":
            _require(len(d["breaks"]) + 1 == len(d["scores"]),
                     "stepwise_duration: len(scores) must = len(breaks)+1")
        return cls(
            function=d["function"], metric=d["metric"],
            k=d.get("k"), x0=d.get("x0"),
            thresholds=d.get("thresholds"), scores=d.get("scores"),
            breaks=d.get("breaks"),
            direction=d.get("direction", "high_quality_low_metric"),
            rate_floor=d.get("rate_floor", 0.0),
        )


@dataclass
class FreezeMappingConfig:
    rle: MappingEntry
    low_var: MappingEntry
    unique: MappingEntry
    combined_weights: Dict[str, float]

    @classmethod
    def from_dict(cls, d: Dict):
        s = sum(d["combined_weights"].values())
        _require(abs(s - 1.0) < 1e-3,
                 f"freeze.combined_weights sum != 1.0 (got {s})")
        return cls(
            rle=MappingEntry.from_dict(d["rle"]),
            low_var=MappingEntry.from_dict(d["low_var"]),
            unique=MappingEntry.from_dict(d["unique"]),
            combined_weights=d["combined_weights"],
        )


@dataclass
class MappingConfig:
    spike: MappingEntry
    step: MappingEntry
    drift: MappingEntry
    freeze: FreezeMappingConfig
    regime: MappingEntry

    @classmethod
    def from_dict(cls, d: Dict):
        return cls(
            spike  = MappingEntry.from_dict(d["spike"]),
            step   = MappingEntry.from_dict(d["step"]),
            drift  = MappingEntry.from_dict(d["drift"]),
            freeze = FreezeMappingConfig.from_dict(d["freeze"]),
            regime = MappingEntry.from_dict(d["regime"]),
        )


@dataclass
class VetoRule:
    name: str
    condition: str
    cap: float


@dataclass
class CooldownRule:
    trigger: str
    duration_h: float
    drift_replacement: float
    recovery_conditions: List[str]
    min_recovery_h: float


@dataclass
class AggregationConfig:
    weights: Dict[str, float]
    lambda_blend: float

    @classmethod
    def from_dict(cls, d: Dict):
        s = sum(d["weights"].values())
        _require(abs(s - 1.0) < 1e-3, f"aggregation weights sum != 1.0 (got {s})")
        required = {"Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"}
        _require(set(d["weights"].keys()) >= required,
                 f"aggregation weights missing keys: {required - set(d['weights'].keys())}")
        _require(0 <= d["lambda_blend"] <= 1, f"lambda_blend must be in [0,1]; got {d['lambda_blend']}")
        return cls(weights=d["weights"], lambda_blend=d["lambda_blend"])


@dataclass
class RulesConfig:
    aggregation: AggregationConfig
    vetos: List[VetoRule]
    cooldown: Dict[str, CooldownRule]
    grading: Dict[str, float]

    @classmethod
    def from_dict(cls, d: Dict):
        return cls(
            aggregation=AggregationConfig.from_dict(d["aggregation"]),
            vetos=[VetoRule(**v) for v in d["vetos"]],
            cooldown={k: CooldownRule(**v) for k, v in d["cooldown"].items()},
            grading=d["grading"],
        )


@dataclass
class PathsConfig:
    data: Dict[str, str]
    output_root: str
    parquet_root: str
    figure_root: str
    plot_data_root: str
    run_manifest: str

    @classmethod
    def from_dict(cls, d: Dict):
        return cls(**d)


@dataclass
class ProjectConfig:
    windows: WindowConfig
    mapping: MappingConfig
    rules: RulesConfig
    paths: PathsConfig

    def model_dump(self) -> dict:
        return asdict(self)
