"""src/data/loader.py — raw multi-source loading (plan §1.1.1, §2.1).

Loads the five North-Bank raw files:
  * 3 min-level Excel  (DO / ORP / QR+QIR)         -> 1 min native
  * 2 hourly legacy .xls (influent / effluent)     -> 1 h native

Min-level loading reuses the D1 `loader.load_raw` logic. Hourly loading parses
the `Data`+`Time` columns into a timestamp index, prefixes columns inf_/eff_,
and turns the effluent "---" sentinel into NaN.

Returns native-resolution frames; alignment to the 1-min master clock and
imputation are handled in `preprocess.py`.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from ..semantics import EFFLUENT_QUALITY, EFFLUENT_AUX, INFLUENT_QUALITY, INFLUENT_FLOW


# ── min-level (1 min native) ────────────────────────────────────────────────
def load_min(do_path: str, orp_path: str, flw_path: str) -> pd.DataFrame:
    """Load & merge the three min-level Excel files on the `data` timestamp."""
    do  = pd.read_excel(do_path)
    orp = pd.read_excel(orp_path)
    flw = pd.read_excel(flw_path)
    df = do.merge(orp, on="data").merge(flw, on="data")
    df["data"] = pd.to_datetime(df["data"])
    df = df.set_index("data").sort_index()
    df.index.name = "timestamp"
    return df


# ── hourly water-quality (1 h native, legacy BIFF .xls) ─────────────────────
def _parse_hour_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Combine `Data` (yy/mm/dd) + `Time` (HH:MM:SS) into a timestamp index."""
    ts = pd.to_datetime(df["Data"].astype(str).str.strip() + " "
                        + df["Time"].astype(str).str.strip(),
                        format="%y/%m/%d %H:%M:%S", errors="coerce")
    return pd.DatetimeIndex(ts)


def load_influent(path: str) -> pd.DataFrame:
    """Influent hourly: pH,T,SS,NH4,TP,TN,COD,Q -> inf_*."""
    df = pd.read_excel(path, engine="xlrd")
    idx = _parse_hour_index(df)
    cols = INFLUENT_QUALITY + INFLUENT_FLOW
    out = df[cols].apply(pd.to_numeric, errors="coerce")
    out.columns = [f"inf_{c}" for c in cols]
    out.index = idx
    out.index.name = "timestamp"
    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def load_effluent(path: str) -> pd.DataFrame:
    """Effluent hourly: COD,TP,NH4,TN,Ph,T,<sludge> -> eff_*.

    "---" sentinels become NaN; the GBK-garbled last column -> eff_sludge.
    """
    df = pd.read_excel(path, engine="xlrd")
    idx = _parse_hour_index(df)
    # positional mapping: COD,TP,NH4,TN,Ph,T, then aux concentration column
    raw_quality = ["COD", "TP", "NH4", "TN", "Ph", "T"]
    out = pd.DataFrame(index=idx)
    for raw, std in zip(raw_quality, ["COD", "TP", "NH4", "TN", "pH", "T"]):
        out[f"eff_{std}"] = pd.to_numeric(
            df[raw].replace({"---": np.nan, "": np.nan}), errors="coerce").values
    # last column = aux concentration (garbled header) -> eff_sludge
    aux_col = df.columns[-1]
    out["eff_sludge"] = pd.to_numeric(
        df[aux_col].replace({"---": np.nan, "": np.nan}), errors="coerce").values
    out.index.name = "timestamp"
    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def load_all(paths: dict) -> dict:
    """Load every raw source; return dict of native frames + metadata.

    Keys: 'min' (1 min), 'influent' (1 h), 'effluent' (1 h).
    """
    out = {
        "min": load_min(paths["do_file"], paths["orp_file"], paths["flw_file"]),
        "influent": load_influent(paths["influent_file"]),
        "effluent": load_effluent(paths["effluent_file"]),
    }
    return out
