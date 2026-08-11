"""Common data access and labels for D3 figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "data"
VALIDATION = ROOT / "outputs" / "validation"
OUT = ROOT / "outputs" / "figures"


def read(name: str, **kwargs) -> pd.DataFrame:
    frame = pd.read_excel(DATA / name, **kwargs)
    if "ts" in frame:
        frame["ts"] = pd.to_datetime(frame["ts"])
    return frame


def read_validation(name: str, **kwargs) -> pd.DataFrame:
    frame = pd.read_excel(VALIDATION / name, **kwargs)
    for column in ("ts", "timestamp"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    return frame


def load_yaml(name: str) -> dict:
    with (ROOT / "configs" / name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def sensor_type(sensor: str) -> str:
    return "DO" if sensor.startswith("DO") else "ORP"


def short_sensor(sensor: str) -> str:
    return sensor.replace("_", "-")


def sensor_order(sensor_ids: list[str] | None = None) -> list[str]:
    """Return the fixed process-position order used across the figure bundle."""
    ordered = [
        *(f"DO_{line}_{position}" for position in (1, 2, 3, 4) for line in (1, 2)),
        *(f"ORP_{line}_{position}" for position in (1, 2, 3) for line in (1, 2)),
    ]
    if sensor_ids is None:
        return ordered
    available = set(sensor_ids)
    return [sensor for sensor in ordered if sensor in available]


def sensor_metadata() -> pd.DataFrame:
    return pd.DataFrame(load_yaml("d3_sensors.yaml")["sensors"]).rename(
        columns={"id": "sensor_id"}
    )
