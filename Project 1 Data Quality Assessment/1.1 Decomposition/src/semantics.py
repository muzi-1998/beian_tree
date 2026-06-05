"""src/semantics.py — North-Bank plant process semantics & channel grouping.

Single source of truth (plan §2.1, §2.2) mapping every variable to:
  * its physical / process-zone meaning,
  * its decomposition group (-> configs/deperiodise.yaml `groups`),
  * its data Class (C scoring subject / A driver / D water-quality),
  * its native track (min-level 1min vs hourly 1h).

The North-Bank plant runs two parallel biological trains with an
"anaerobic -> pre-anoxic -> aerobic -> post-anoxic" layout for enhanced
nitrogen & phosphorus removal.
"""
from __future__ import annotations

# ── min-level process-state channels ────────────────────────────────────────
DO_CHANNELS  = [f"DO_{p}_{i}"  for p in (1, 2) for i in range(1, 5)]   # 8
ORP_CHANNELS = [f"ORP_{p}_{i}" for p in (1, 2) for i in range(1, 4)]   # 6
FLOW_CHANNELS = [f"QR_{p}" for p in (1, 2)] + [f"QIR_{p}" for p in (1, 2)]  # 4
MIN_CHANNELS = DO_CHANNELS + ORP_CHANNELS + FLOW_CHANNELS

# Aerobic DO (front->rear nitrification) vs post-anoxic DO (near-zero floor)
AEROBIC_DO     = [f"DO_{p}_{i}" for p in (1, 2) for i in (1, 2, 3)]    # 6
POSTANOXIC_DO  = [f"DO_{p}_4" for p in (1, 2)]                          # 2

# ── hourly water-quality channels (resolved by loader prefix) ───────────────
INFLUENT_QUALITY = ["pH", "T", "SS", "NH4", "TP", "TN", "COD"]
INFLUENT_FLOW    = ["Q"]
EFFLUENT_QUALITY = ["COD", "TP", "NH4", "TN", "pH", "T"]
EFFLUENT_AUX     = ["sludge"]    # last (GBK-garbled) effluent column

# Physical valid ranges (range-clip -> NaN, marked not cleaned). plan §2.5
PHYS_RANGE = {
    **{c: (-0.5, 12.0)  for c in DO_CHANNELS},
    **{c: (-550, 550)   for c in ORP_CHANNELS},
    # flows cannot be negative (physically impossible); negatives are acquisition
    # faults -> flagged RANGE & excluded before decomposition/whitening. The raw
    # negative fraction is still reported by consistency.value_rate_report.
    **{f"QR_{p}":  (0, 8000) for p in (1, 2)},
    **{f"QIR_{p}": (0, 5000) for p in (1, 2)},
    # hourly water quality (prefixed inf_/eff_ by loader)
    "inf_pH": (0, 14), "inf_T": (-5, 45), "inf_SS": (0, 5000),
    "inf_NH4": (0, 200), "inf_TP": (0, 50), "inf_TN": (0, 300),
    "inf_COD": (0, 5000), "inf_Q": (0, 20000),
    "eff_COD": (0, 1000), "eff_TP": (0, 20), "eff_NH4": (0, 100),
    "eff_TN": (0, 200), "eff_pH": (0, 14), "eff_T": (-5, 45),
    "eff_sludge": (-1, 100),
}

# Detection limits for left-censoring (plan §3.4) — effluent near-zero quality.
DETECTION_LIMIT = {
    "eff_NH4": 0.02, "eff_TP": 0.01, "eff_COD": 4.0, "eff_TN": 0.5,
}


def _channel_meta():
    """Build channel -> metadata dict (group/zone/class/track/train)."""
    meta = {}
    # Aerobic DO
    for c in AEROBIC_DO:
        train = int(c.split("_")[1])
        pos = int(c.split("_")[2])
        meta[c] = dict(group="aerobic_do", track="min", cls="C",
                       zone="aerobic", role="nitrification/aeration",
                       train=train, seq=pos)
    # Post-anoxic DO
    for c in POSTANOXIC_DO:
        train = int(c.split("_")[1])
        meta[c] = dict(group="postanoxic_do", track="min", cls="C",
                       zone="post_anoxic", role="deep_denitrification_floor",
                       train=train, seq=4)
    # ORP — anaerobic / pre-anoxic front / pre-anoxic rear
    orp_zone = {1: "anaerobic", 2: "pre_anoxic_front", 3: "pre_anoxic_rear"}
    orp_role = {1: "P-release_redox", 2: "denitrification_front",
                3: "denitrification_rear"}
    for c in ORP_CHANNELS:
        train = int(c.split("_")[1]); pos = int(c.split("_")[2])
        meta[c] = dict(group="anoxic_orp", track="min", cls="C",
                       zone=orp_zone[pos], role=orp_role[pos],
                       train=train, seq=pos)
    # Flows (drivers, Class A)
    for c in FLOW_CHANNELS:
        meta[c] = dict(group="flow", track="min", cls="A",
                       zone="recycle",
                       role="external_recycle" if c.startswith("QR")
                            else "internal_recycle",
                       train=int(c.split("_")[1]), seq=0)
    # Influent hourly
    for c in INFLUENT_QUALITY:
        meta[f"inf_{c}"] = dict(group="influent", track="hour", cls="D",
                                zone="influent", role="water_quality",
                                train=0, seq=0)
    for c in INFLUENT_FLOW:
        meta[f"inf_{c}"] = dict(group="influent_flow", track="hour", cls="A",
                                zone="influent", role="influent_flow",
                                train=0, seq=0)
    # Effluent hourly
    for c in EFFLUENT_QUALITY:
        meta[f"eff_{c}"] = dict(group="effluent", track="hour", cls="D",
                                zone="effluent", role="water_quality",
                                train=0, seq=0)
    for c in EFFLUENT_AUX:
        meta[f"eff_{c}"] = dict(group="effluent", track="hour", cls="D",
                                zone="effluent", role="aux_concentration",
                                train=0, seq=0)
    return meta


CHANNEL_META = _channel_meta()


def group_of(ch: str) -> str:
    return CHANNEL_META.get(ch, {}).get("group", "unknown")


def track_of(ch: str) -> str:
    return CHANNEL_META.get(ch, {}).get("track", "min")


def channels_in_group(group: str) -> list:
    return [c for c, m in CHANNEL_META.items() if m["group"] == group]
