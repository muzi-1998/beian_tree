"""Rebuild D3 v2.3 validation products from frozen current scoring outputs."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import yaml


ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from src.common.benchmark_windows import BenchmarkWindows
from src.data.input_loader import load_aligned_data
from src.d3_physical.threshold_store import ThresholdStore
from src.validation.d3_validation import run_validation


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def main() -> dict[str, Path]:
    paths_cfg = _yaml("d3_paths.yaml")
    sensors_cfg = _yaml("d3_sensors.yaml")
    physical_cfg = _yaml("d3_physical_bounds.yaml")
    rate_cfg = _yaml("d3_rate_limits.yaml")
    sensors = [item["id"] for item in sensors_cfg["sensors"]]
    frame = load_aligned_data(paths_cfg, ROOT)
    benchmark = BenchmarkWindows(frame, sensors, window_hours=24, target_n_windows=40).select()
    thresholds = ThresholdStore.build(physical_cfg, rate_cfg, benchmark, version="v2.3.0")
    data = ROOT / "outputs" / "data"
    names = {
        "main_scores": "D3_window_scores.xlsx",
        "value_bounds": "D3_value_evidence.xlsx",
        "rate_constraint": "D3_rate_evidence.xlsx",
        "boundary_features": "D3_boundary_diagnostics.xlsx",
        "events": "D3_physical_events.xlsx",
    }
    results = {key: pd.read_excel(data / name) for key, name in names.items()}
    return run_validation(
        frame=frame,
        results=results,
        sensors=sensors,
        sensor_meta=sensors_cfg["sensors"],
        thresholds=thresholds,
        configs={
            "physical_bounds": physical_cfg,
            "rate_limits": rate_cfg,
            "mapping": _yaml("d3_mapping.yaml"),
            "rules": _yaml("d3_rules.yaml"),
            "dag": _yaml("d3_dag.yaml"),
        },
        root=ROOT,
    )


if __name__ == "__main__":
    outputs = main()
    for label, path in outputs.items():
        print(f"{label}: {path}")
