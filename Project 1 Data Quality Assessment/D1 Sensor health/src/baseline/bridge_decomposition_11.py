"""src/baseline/bridge_decomposition_11.py
§1.1 Decomposition → D1 input-source bridge.

D1 v1.0 de-periodised each channel with its OWN harmonic / STL baseline
(``src/baseline/deperiodise.py``). That residual is NOT whitened — the i.i.d.
critical values used by the step (KS), regime (KS) and PELT detectors therefore
over-reject on autocorrelated residuals (false Q_step / Q_regime degradation).
The STL variant additionally leaks the future (phase-bin means computed over the
whole series). See ``D1_detector_audit.md`` §2–§3.

This bridge replaces that input source with §1.1's per-channel ARMA/GARCH
output, governed by the ``whiteness_manifest.csv`` contract:

    scoring_mode    innov_kind     fed to i.i.d. detectors as ...
    ───────────────────────────────────────────────────────────────────────
    iid             innovation     innovation (white)  → n_eff = 1.0
    autocorr_aware  robust_z       residual            → n_eff = manifest ratio
    floor_freeze    censored_z     (excluded)          → n_eff = 0.0  (freeze owns it)

The i.i.d. detectors are made n_eff-aware by deflating their raw statistic by
``sqrt(n_eff_ratio)`` (see ``effective_neff``): for a white innovation the
statistic is unchanged; for a near-unit-root residual (n_eff≈0.01) it is shrunk
~10× so it can no longer drive a false alarm; for a floor channel it is zeroed
and the freeze sub-score takes over.

Detectors that are multivariate / local — Drift-PLS, FF-PCA (residual) and
Spike-Hampel, Freeze (raw minute) — are robust to autocorrelation and keep their
existing inputs; only their leakage fix (Hampel causal window) is applied
elsewhere.

The module is additive: it does not modify D1's own ``deperiodise`` path, so the
legacy behaviour remains reproducible (env ``D1_USE_DECOMP_11=0``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


# ── default location of §1.1 outputs, relative to the D1 project root ──────────
# this file lives at:  <D1 root>/src/baseline/bridge_decomposition_11.py
#   parents[0]=baseline  parents[1]=src  parents[2]=<D1 root>  parents[3]=<Project 1>
_D1_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _D1_ROOT.parent
DEFAULT_DECOMP_DIR = _PROJECT_ROOT / "1.1 Decomposition" / "outputs"

# manifest scoring_mode → how the channel is routed
_MODE_IID = "iid"
_MODE_AUTOCORR = "autocorr_aware"
_MODE_FLOOR = "floor_freeze"


def effective_neff(channel: str,
                   scoring_mode: Dict[str, str],
                   neff_map: Dict[str, float]) -> float:
    """Effective n_eff ratio used to deflate an i.i.d. detector statistic.

    iid            → 1.0   (innovation is white; statistic unchanged)
    autocorr_aware → manifest n_eff_ratio  (statistic shrunk by sqrt of it)
    floor_freeze   → 0.0   (statistic zeroed; freeze sub-score owns the channel)
    """
    mode = scoring_mode.get(channel, _MODE_IID)
    if mode == _MODE_IID:
        return 1.0
    if mode == _MODE_AUTOCORR:
        return float(np.clip(neff_map.get(channel, 1.0), 0.0, 1.0))
    if mode == _MODE_FLOOR:
        return 0.0
    return 1.0


def load_manifest(decomp_dir: Path | str = DEFAULT_DECOMP_DIR) -> pd.DataFrame:
    """Load whiteness_manifest.csv indexed by channel.

    Tolerates a UTF-8 BOM on the header (the file is exported with one).
    """
    decomp_dir = Path(decomp_dir)
    path = decomp_dir / "tables" / "whiteness_manifest.csv"
    if not path.exists():
        raise FileNotFoundError(f"§1.1 whiteness_manifest not found: {path}")
    man = pd.read_csv(path, encoding="utf-8-sig")
    man.columns = [c.strip().lstrip("﻿") for c in man.columns]
    man = man.set_index("channel")
    return man


def _read_parquet_hourly(path: Path, channels: list[str]) -> pd.DataFrame:
    """Read a 1-min/1-h parquet, keep requested channels, resample to hourly mean."""
    df = pd.read_parquet(path)
    keep = [c for c in channels if c in df.columns]
    df = df[keep]
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    # mean over the hour — for already-hourly channels this is a no-op pass-through
    return df.resample("1h").mean()


def load_decomposition_11(channels: Iterable[str],
                          decomp_dir: Path | str = DEFAULT_DECOMP_DIR,
                          target_index_h: Optional[pd.DatetimeIndex] = None,
                          ) -> Dict[str, object]:
    """Load §1.1 residual + innovation + manifest as D1's hourly input source.

    Parameters
    ----------
    channels : the D1 channels to bridge (scored + support).
    decomp_dir : §1.1 ``outputs/`` directory (defaults to the sibling project).
    target_index_h : if given, all hourly frames are reindexed onto it
        (ffill→bfill on the edges) so downstream shapes match D1's existing
        hourly index exactly.

    Returns
    -------
    dict with keys
        resid_h           : DataFrame — §1.1 residual @ hourly (drift / cooldown)
        innov_h           : DataFrame — §1.1 innovation @ hourly
        detector_input_h  : DataFrame — per-channel routed series for the
                            i.i.d. detectors (innovation for iid, residual else)
        scoring_mode      : dict channel → {iid|autocorr_aware|floor_freeze}
        neff              : dict channel → manifest n_eff_ratio
        manifest          : the manifest sub-frame for these channels
    """
    decomp_dir = Path(decomp_dir)
    channels = list(channels)
    par = decomp_dir / "parquet"

    resid_h = _read_parquet_hourly(par / "residual_min.parquet", channels)
    innov_h = _read_parquet_hourly(par / "innovation_min.parquet", channels)

    man = load_manifest(decomp_dir)
    missing = [c for c in channels if c not in man.index]
    if missing:
        raise KeyError(f"channels absent from §1.1 manifest: {missing}")

    scoring_mode = {c: str(man.loc[c, "scoring_mode"]) for c in channels}
    neff = {c: float(man.loc[c, "n_eff_ratio"]) for c in channels}

    # align both frames to a common channel order / column set
    cols = [c for c in channels if c in resid_h.columns and c in innov_h.columns]
    resid_h = resid_h[cols]
    innov_h = innov_h[cols]

    # per-channel routed input for the i.i.d.-sensitive detectors
    det_cols = {}
    for c in cols:
        if scoring_mode.get(c) == _MODE_IID:
            det_cols[c] = innov_h[c]          # white innovation
        else:
            det_cols[c] = resid_h[c]          # residual (autocorr_aware / floor)
    detector_input_h = pd.DataFrame(det_cols)

    if target_index_h is not None:
        resid_h = resid_h.reindex(target_index_h).ffill().bfill()
        innov_h = innov_h.reindex(target_index_h).ffill().bfill()
        detector_input_h = detector_input_h.reindex(target_index_h).ffill().bfill()

    return {
        "resid_h": resid_h,
        "innov_h": innov_h,
        "detector_input_h": detector_input_h,
        "scoring_mode": scoring_mode,
        "neff": neff,
        "manifest": man.loc[cols],
    }


def summarise(bridge: Dict[str, object]) -> str:
    """One-line summary of the routing for logging."""
    sm = bridge["scoring_mode"]
    n_iid = sum(v == _MODE_IID for v in sm.values())
    n_ac = sum(v == _MODE_AUTOCORR for v in sm.values())
    n_fl = sum(v == _MODE_FLOOR for v in sm.values())
    rh = bridge["resid_h"]
    return (f"§1.1 bridge: {len(sm)} channels "
            f"[iid={n_iid}, autocorr_aware={n_ac}, floor_freeze={n_fl}], "
            f"hourly {rh.shape[0]}×{rh.shape[1]}, "
            f"{rh.index[0]} → {rh.index[-1]}")
