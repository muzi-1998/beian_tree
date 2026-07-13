"""Common data access and labels for D4 figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "data"
OUT = ROOT / "outputs" / "figures"


def read(name: str, **kwargs) -> pd.DataFrame:
    frame = pd.read_excel(DATA / name, **kwargs)
    if "ts" in frame:
        frame["ts"] = pd.to_datetime(frame["ts"])
    return frame


def load_yaml(name: str) -> dict:
    with (ROOT / "configs" / name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def sensor_type(sensor: str) -> str:
    return "DO" if sensor.startswith("DO") else "ORP"


def short_sensor(sensor: str) -> str:
    return sensor.replace("_", "-")
