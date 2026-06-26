"""analysis_11/common.py — shared loaders / ordering / style for the §1.1
results-analysis work-streams (variance partition, whitening, spike sanity).

All three work-streams are *manifest-driven*: every split, threshold and
statistical unit is keyed on the channel's `scoring_mode` / `group` / `zone`
so §1.1 stays internally consistent and matches the §1.2 interface.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.outputs.figstyle import OKABE_ITO, setup_style  # noqa: E402

PQ = ROOT / "outputs" / "parquet"
TAB = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
PDATA = ROOT / "outputs" / "plot_data"
FIG.mkdir(parents=True, exist_ok=True)
PDATA.mkdir(parents=True, exist_ok=True)

# ── three-component colours (plan: trend / seasonal / residual = blue/orange/grey)
COMP = {"trend": OKABE_ITO["blue"], "seasonal": OKABE_ITO["orange"],
        "residual": OKABE_ITO["gray"]}
# scoring_mode track colours (neutral; alarm-vermillion reserved for thresholds)
MODE_COLOR = {"iid": OKABE_ITO["blue"],
              "autocorr_aware": OKABE_ITO["skyblue"],
              "floor_freeze": OKABE_ITO["gray"]}

# process-position order: aerobic front→mid→rear · post-anoxic · anoxic/anaer ORP
# · recycle QR/QIR · influent · effluent  (33 channels)
PROCESS_ORDER = [
    "DO_1_1", "DO_2_1",                       # aerobic front
    "DO_1_2", "DO_2_2",                       # aerobic mid
    "DO_1_3", "DO_2_3",                       # aerobic rear
    "DO_1_4", "DO_2_4",                       # post-anoxic DO (floor)
    "ORP_1_1", "ORP_2_1",                     # anaerobic ORP
    "ORP_1_2", "ORP_2_2",                     # pre-anoxic front ORP
    "ORP_1_3", "ORP_2_3",                     # pre-anoxic rear ORP
    "QR_1", "QR_2", "QIR_1", "QIR_2",         # recycle flows
    "inf_Q", "inf_COD", "inf_NH4", "inf_TN",  # influent
    "inf_TP", "inf_SS", "inf_pH", "inf_T",
    "eff_COD", "eff_NH4", "eff_TN", "eff_TP",  # effluent
    "eff_sludge", "eff_pH", "eff_T",
]
# coarse position bands for x-axis grouping / aggregation
POS_BAND = {**{c: "aerobic_DO" for c in ["DO_1_1", "DO_2_1", "DO_1_2", "DO_2_2",
                                         "DO_1_3", "DO_2_3"]},
            **{c: "postanoxic_DO" for c in ["DO_1_4", "DO_2_4"]},
            **{c: "anoxic_ORP" for c in ["ORP_1_1", "ORP_2_1", "ORP_1_2",
                                         "ORP_2_2", "ORP_1_3", "ORP_2_3"]},
            **{c: "recycle_flow" for c in ["QR_1", "QR_2", "QIR_1", "QIR_2"]},
            **{c: "influent" for c in ["inf_Q", "inf_COD", "inf_NH4", "inf_TN",
                                       "inf_TP", "inf_SS", "inf_pH", "inf_T"]},
            **{c: "effluent" for c in ["eff_COD", "eff_NH4", "eff_TN", "eff_TP",
                                       "eff_sludge", "eff_pH", "eff_T"]}}
BAND_ORDER = ["aerobic_DO", "postanoxic_DO", "anoxic_ORP", "recycle_flow",
              "influent", "effluent"]
# distinct, colour-blind-safe colour per variable group (for the summary bar)
BAND_COLOR = {"aerobic_DO": "#0072B2", "postanoxic_DO": "#56B4E9",
              "anoxic_ORP": "#009E73", "recycle_flow": "#E69F00",
              "influent": "#CC79A7", "effluent": "#666666"}


def load_manifest() -> pd.DataFrame:
    m = pd.read_csv(TAB / "whiteness_manifest.csv", encoding="utf-8-sig")
    m.columns = [c.strip().lstrip("﻿") for c in m.columns]
    return m.set_index("channel")


def load_config() -> dict:
    with open(ROOT / "configs" / "deperiodise.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def trend_bandwidth_h(group: str, cfg: dict) -> int:
    return int(cfg["groups"][group]["loess_trend_bandwidth_h"])


def primary_period_native(group: str, cfg: dict) -> int:
    """Dominant period in native steps (min for min-track, hour for hour-track)."""
    return int(cfg["groups"][group]["candidate_periods"][0])


def longest_period_hours(group: str, cfg: dict) -> float:
    """Longest candidate period expressed in HOURS (min-track periods are in
    minutes, hour-track in hours)."""
    g = cfg["groups"][group]
    longest = max(g["candidate_periods"])
    return longest / 60.0 if g["track"] == "min" else float(longest)


def get_raw(channel: str) -> pd.Series:
    """Raw aligned X(t) at native resolution (min-track from time_base_1min,
    hourly-track from the native hourly parquets)."""
    if channel.startswith(("inf_",)):
        df = pd.read_parquet(PQ / "influent_hourly.parquet")
    elif channel.startswith(("eff_",)):
        df = pd.read_parquet(PQ / "effluent_hourly.parquet")
    else:
        df = pd.read_parquet(PQ / "time_base_1min.parquet")
    return df[channel].astype(float)


def get_residual(channel: str) -> pd.Series:
    if channel.startswith("inf_"):
        df = pd.read_parquet(PQ / "residual_influent.parquet")
    elif channel.startswith("eff_"):
        df = pd.read_parquet(PQ / "residual_effluent.parquet")
    else:
        df = pd.read_parquet(PQ / "residual_min.parquet")
    return df[channel].astype(float)


def get_innovation(channel: str) -> pd.Series:
    if channel.startswith("inf_"):
        df = pd.read_parquet(PQ / "innovation_influent.parquet")
    elif channel.startswith("eff_"):
        df = pd.read_parquet(PQ / "innovation_effluent.parquet")
    else:
        df = pd.read_parquet(PQ / "innovation_min.parquet")
    return df[channel].astype(float)
