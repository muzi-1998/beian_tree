"""
src/utils/config_loader.py
==========================
统一配置加载层 (P2)。负责把 4 份 YAML 加载、合并、校验后,生成一个
D2Config dataclass,供下游所有模块只读消费。

设计原则:
  - 任何下游模块禁止再读 yaml,只接收 D2Config
  - 任何下游模块禁止访问全局变量;所有依赖经由构造函数注入
  - 启动阶段一次性强校验,失败立即报错(fail-fast)

设计依据:工程目录 v2.0 §3.1 (D2Config / SensorMeta / CalibrationProfile)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


@dataclass(frozen=True)
class SensorMeta:
    """单个传感器的元数据。"""
    sensor_id:          str
    pool:               int
    sensor_type:        str            # "DO" or "ORP"
    position:           int
    parallel_to:        Optional[str]
    in_pool_neighbors:  List[str]
    precision:          float
    unit:               str
    availability_mode:  str
    process_zone:       str
    process_floor_threshold: Optional[float]
    response_loss_enabled: bool
    response_loss_peers: List[str]


@dataclass(frozen=True)
class WindowSpec:
    name:    str
    length:  str          # pandas offset string e.g. "24h"
    step:    str
    purpose: str


@dataclass
class MappingConfig:
    piecewise_breaks:   Dict[str, Dict[str, list]]
    Q_TI_weights:       Dict[str, float]
    Q_GS_weights:       Dict[str, float]
    Q_FA_rule:          Dict[str, Any]
    aggregation:        Dict[str, Any]
    veto_rules:         Dict[str, Dict[str, Any]]
    safety_floor:       Dict[str, float]
    imputation:         Dict[str, Any]
    freeze_detection:   Dict[str, Any]
    process_floor_policy: Dict[str, Any]
    mapping_version:    str


@dataclass
class D2Config:
    """完整配置 root,贯穿所有下游模块。"""
    plant_id:           str
    sensors:            Dict[str, SensorMeta]
    scored_channels:    List[str]
    support_channels:   List[str]
    pools:              List[int]
    has_parallel_pools: bool
    windows:            Dict[str, WindowSpec]
    enabled_windows:    List[str]
    time_grid:          Dict[str, Any]
    mapping:            MappingConfig

    @property
    def main_window(self) -> WindowSpec:
        return self.windows["main_window"]

    @property
    def freeze_window(self) -> WindowSpec:
        return self.windows["freeze_window"]


# ─── Loading ──────────────────────────────────────────────────────────────────

def load_config(config_dir: Path, version: str = "v1") -> D2Config:
    """加载 4 份 YAML 并构造 D2Config。失败立即报错。"""
    config_dir = Path(config_dir)
    sensors_yaml = yaml.safe_load((config_dir / "d2_sensors.yaml").read_text(encoding="utf-8"))
    mapping_yaml = yaml.safe_load((config_dir / "d2_mapping.yaml").read_text(encoding="utf-8"))
    windows_yaml = yaml.safe_load((config_dir / "d2_windows.yaml").read_text(encoding="utf-8"))

    # SensorMeta
    sensors = {}
    availability_defaults = sensors_yaml.get("availability_defaults", {})
    for sid, s in sensors_yaml["sensors"].items():
        sensors[sid] = SensorMeta(
            sensor_id=sid,
            pool=s["pool"],
            sensor_type=s["type"],
            position=s["position"],
            parallel_to=s.get("parallel_to"),
            in_pool_neighbors=list(s.get("in_pool_neighbors", [])),
            precision=float(s["precision"]),
            unit=s["unit"],
            availability_mode=s.get(
                "availability_mode", availability_defaults.get("mode", "standard")
            ),
            process_zone=s.get("process_zone", "unspecified"),
            process_floor_threshold=(
                float(s["process_floor_threshold"])
                if s.get("process_floor_threshold") is not None else None
            ),
            response_loss_enabled=bool(
                s.get(
                    "response_loss_enabled",
                    availability_defaults.get("response_loss_enabled", True),
                )
            ),
            response_loss_peers=list(
                s.get(
                    "response_loss_peers",
                    [s["parallel_to"]] if s.get("parallel_to") else [],
                )
            ),
        )

    # WindowSpec
    windows = {name: WindowSpec(name=name, **spec)
               for name, spec in windows_yaml["windows"].items()}
    enabled_key = f"enabled_in_{version}"
    enabled = windows_yaml.get(enabled_key, ["main_window"])

    # MappingConfig
    mapping = MappingConfig(
        piecewise_breaks=mapping_yaml["piecewise_breaks"],
        Q_TI_weights=mapping_yaml["Q_TI_components"]["weights"],
        Q_GS_weights=mapping_yaml["Q_GS_components"]["weights"],
        Q_FA_rule=mapping_yaml["Q_FA_rule"],
        aggregation=mapping_yaml["aggregation"],
        veto_rules=mapping_yaml["veto_rules"],
        safety_floor=mapping_yaml["safety_floor"],
        imputation=mapping_yaml["imputation"],
        freeze_detection=mapping_yaml["freeze_detection"],
        process_floor_policy=mapping_yaml["process_floor_policy"],
        mapping_version=mapping_yaml["mapping_version"],
    )

    cfg = D2Config(
        plant_id=sensors_yaml["plant_id"],
        sensors=sensors,
        scored_channels=list(sensors_yaml["scored_channels"]),
        support_channels=list(sensors_yaml.get("support_channels", [])),
        pools=sensors_yaml["topology"]["pools"],
        has_parallel_pools=sensors_yaml["topology"]["has_parallel_pools"],
        windows=windows,
        enabled_windows=enabled,
        time_grid=windows_yaml["time_grid"],
        mapping=mapping,
    )
    _validate(cfg)
    return cfg


# ─── Validation ───────────────────────────────────────────────────────────────

def _validate(cfg: D2Config) -> None:
    """启动期硬校验:权重和、阈值单调、传感器一致等。"""
    # 1. Q_TI 权重和应为 1
    s = sum(cfg.mapping.Q_TI_weights.values())
    assert abs(s - 1.0) < 1e-6, f"Q_TI weights sum {s} != 1.0"

    # 2. Q_GS 权重和应为 1
    s = sum(cfg.mapping.Q_GS_weights.values())
    assert abs(s - 1.0) < 1e-6, f"Q_GS weights sum {s} != 1.0"

    # 3. D2 聚合权重和应为 1
    a = cfg.mapping.aggregation["weights"]
    s = a["Q_TI"] + a["Q_GS"] + a["Q_FA"]
    assert abs(s - 1.0) < 1e-6, f"D2 weights sum {s} != 1.0"

    # 4. lambda 在 [0, 1]
    lam = cfg.mapping.aggregation["lambda_blend"]
    assert 0 <= lam <= 1, f"lambda_blend {lam} out of [0,1]"

    # 5. 每个传感器的 parallel_to 必须在 sensors 中
    for sid, s in cfg.sensors.items():
        if s.parallel_to is not None:
            assert s.parallel_to in cfg.sensors, \
                f"{sid}.parallel_to={s.parallel_to} not in sensors"

    # 6. 每个 in_pool_neighbor 必须存在且同 pool
    for sid, s in cfg.sensors.items():
        for n in s.in_pool_neighbors:
            assert n in cfg.sensors, f"{sid}: neighbor {n} not in sensors"
            assert cfg.sensors[n].pool == s.pool, \
                f"{sid}: neighbor {n} is in pool {cfg.sensors[n].pool}, expected {s.pool}"

    # 7. piecewise_breaks 必须严格递增
    for sub, metrics in cfg.mapping.piecewise_breaks.items():
        for m, brks in metrics.items():
            assert all(brks[i] < brks[i+1] for i in range(len(brks)-1)), \
                f"{sub}.{m} breaks not strictly increasing: {brks}"

    # 8. tau_RLE_D2 < tau_RLE_D1
    fd = cfg.mapping.freeze_detection
    assert fd["tau_rle_D2_min"] < fd["tau_rle_D1_min"], \
        f"D2 RLE threshold {fd['tau_rle_D2_min']} not strictly less than D1 {fd['tau_rle_D1_min']}"

    # 9. Process-floor routing must be explicit and response-loss peers comparable.
    for sid, sensor in cfg.sensors.items():
        assert sensor.availability_mode in {"standard", "process_floor"}, \
            f"{sid}: unsupported availability_mode={sensor.availability_mode}"
        if sensor.availability_mode == "process_floor":
            assert sensor.process_floor_threshold is not None and sensor.process_floor_threshold > 0, \
                f"{sid}: process_floor_threshold must be positive"
        if sensor.response_loss_enabled:
            assert sensor.response_loss_peers, \
                f"{sid}: response loss requires at least one comparable peer"
            for peer_id in sensor.response_loss_peers:
                assert peer_id in cfg.sensors, f"{sid}: response-loss peer {peer_id} not in sensors"
                peer = cfg.sensors[peer_id]
                assert peer.sensor_type == sensor.sensor_type, \
                    f"{sid}: response-loss peer {peer_id} has incompatible sensor type"
                assert peer.position == sensor.position, \
                    f"{sid}: response-loss peer {peer_id} is not at the same process position"
                assert peer.process_zone == sensor.process_zone, \
                    f"{sid}: response-loss peer {peer_id} is not in the same process zone"
