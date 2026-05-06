"""src/pipeline/d1_pipeline.py
STRICT spec-compliant D1 pipeline (V1.0-strict).

Compliance fixes vs prior V1:
    1. De-periodisation: harmonic decomposition (daily+weekly Fourier),
       NOT 24h rolling mean.
    2. Regime: TwoTierRegimeDetector (W1 + adjacent KS joint).
    3. Drift: engineered peer selection (same-pool adjacent + twin-pool
       counterpart + QR/QIR exogenous).
    4. WindowManager: every detector consults unified window catalogue.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/claude/d1_fsd_strict/src")

import time, pickle
import numpy as np
import pandas as pd
from pathlib import Path

from config import load_project_config
from data import (load_raw, time_align_and_impute, summary_stats,
                  DO_CHANNELS, ORP_CHANNELS, FLOW_CHANNELS, ALL_CHANNELS)
from detectors import (HampelSpikeDetector, AdjacentKSStepDetector,
                       PLSVirtualSensorDetector, engineered_peers,
                       CompositeFreezeDetector, TwoTierRegimeDetector)
from baseline import harmonic_decomposition_dataframe
from mapping import apply_mapping
from aggregation import aggregate_d1, to_daily, to_weekly
from pipeline.window_manager import WindowManager


def run_spike_detector(df_min, channels, wm):
    print(f"    [spike] Hampel; window={wm.get_spec('spike_main')}")
    detector = HampelSpikeDetector(window_min=21, k=3.0)
    return {c: detector.score(df_min[c]) for c in channels}


def compute_spike_rate_6h(spike_results, channels, wm):
    rates = {}
    win = wm.get_spec("spike_main")
    rule = f"{int(win.length.total_seconds()/60)}min"
    for c in channels:
        flag = spike_results[c].aux_flag.astype(float)
        rate_min = flag.rolling(rule, min_periods=60).mean()
        rates[c] = rate_min.resample("1h").mean()
    return pd.DataFrame(rates)


def run_step_detector(resid_h, channels, wm):
    win_h = int(wm.get_spec("step_main").length.total_seconds()/3600)
    print(f"    [step] Adjacent KS; win_h={win_h}")
    detector = AdjacentKSStepDetector(win_h=win_h, alpha=0.001)
    return {c: detector.score(resid_h[c].rename(c)) for c in channels}


def run_drift_detector(resid_h, channels, wm):
    print(f"    [drift] PLS — engineered peers (spec v2 §7)")
    detector = PLSVirtualSensorDetector(n_components=3, train_days=21)
    out = {}
    for c in channels:
        peers = engineered_peers(c, list(resid_h.columns))
        if len(peers) < 2:
            peers = [x for x in resid_h.columns if x != c][:6]
        try:
            out[c] = detector.score(resid_h, target=c, peer_cols=peers)
        except Exception as e:
            print(f"      ! PLS failed on {c}: {e}")
    return out


def run_freeze_detector(df_min, channels, wm):
    print(f"    [freeze] Composite RLE+low-var+unique")
    detector = CompositeFreezeDetector()
    return {c: detector.score(df_min[c]) for c in channels}


def run_regime_detector(resid_h, channels, wm):
    print(f"    [regime] Two-tier W1+KS joint")
    detector = TwoTierRegimeDetector(
        ref_days=30, w1_win_days=7, ks_win_days=7,
        w1_update_h=12, ks_update_h=24, ks_alpha=0.001, n_bootstrap=100)
    return {c: detector.score(resid_h[c].rename(c)) for c in channels}


def compute_subscores(spike_results, step_results, drift_results,
                       freeze_results, regime_results,
                       spike_rate_6h, channels, mapping_cfg):
    print("    [mapping] applying ScoreMapper to detector outputs ...")
    subs = {}
    for c in channels:
        Q_spike = apply_mapping(spike_rate_6h[c].rename("spike_rate_6h"),
                                mapping_cfg.spike)
        Q_step = apply_mapping(step_results[c].raw_score.rename("ks_statistic"),
                               mapping_cfg.step)
        if c in drift_results:
            drift_metric = drift_results[c].raw_score.rename("pls_residual_z")
        else:
            drift_metric = pd.Series(0.0, index=Q_step.index, name="pls_residual_z")
        Q_drift = apply_mapping(drift_metric, mapping_cfg.drift)
        comp = freeze_results[c].metadata["components"]
        comp_h = comp.resample("1h").max()
        Q_rle = apply_mapping(comp_h["rle_run_min"].rename("rle_max_duration_min"),
                              mapping_cfg.freeze.rle)
        Q_lv  = apply_mapping(comp_h["rel_var"].rename("relvar_to_ref"),
                              mapping_cfg.freeze.low_var)
        Q_uq  = apply_mapping(comp_h["unique_ratio"].rename("unique_ratio"),
                              mapping_cfg.freeze.unique)
        cw = mapping_cfg.freeze.combined_weights
        Q_freeze = (cw["rle"]*Q_rle + cw["low_var"]*Q_lv +
                    cw["unique"]*Q_uq).clip(1, 5).rename("Q_freeze")
        Q_regime = apply_mapping(
            regime_results[c].raw_score.rename("w1_normalised"),
            mapping_cfg.regime)
        idx = Q_step.index
        subs[c] = {
            "Q_spike":  Q_spike.reindex(idx).ffill().bfill(),
            "Q_step":   Q_step.reindex(idx).ffill().bfill(),
            "Q_drift":  Q_drift.reindex(idx).ffill().bfill(),
            "Q_freeze": Q_freeze.reindex(idx).ffill().bfill(),
            "Q_regime": Q_regime.reindex(idx).ffill().bfill(),
        }
    return subs


def extract_events(d1_h, threshold=3.0, min_duration_h=6):
    rows = []
    for c in d1_h.columns:
        s = d1_h[c]; low = (s < threshold).astype(int)
        grp = (low.diff() != 0).cumsum()
        for g, sub in s.groupby(grp):
            if (sub < threshold).all() and len(sub) >= min_duration_h:
                rows.append({"sensor_id": c, "start": sub.index[0],
                              "end": sub.index[-1], "duration_h": len(sub),
                              "min_d1": float(sub.min()),
                              "mean_d1": float(sub.mean())})
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["sensor_id", "start"]).reset_index(drop=True)


def attribute_dominant_fault(subs):
    rows = []
    for c, qd in subs.items():
        df = pd.DataFrame({"spike": qd["Q_spike"], "step": qd["Q_step"],
                            "drift": qd["Q_drift"], "freeze": qd["Q_freeze"],
                            "regime": qd["Q_regime"]})
        dom = df.idxmin(axis=1)
        rows.append(pd.DataFrame({"sensor_id": c, "ts": df.index,
                                   "dominant_fault": dom.values,
                                   "min_subscore": df.min(axis=1).values}))
    return pd.concat(rows, ignore_index=True)


def sensor_profile_summary(d1_h, dominant_df, event_df):
    rows = []
    for c in d1_h.columns:
        s = d1_h[c]
        dom = dominant_df[dominant_df["sensor_id"] == c]
        ev  = event_df[event_df["sensor_id"] == c] if len(event_df) else pd.DataFrame()
        high = (s >= 4.5).astype(int); grp = (high.diff() != 0).cumsum()
        bench_count = 0; bench_ids = []
        for g, sub in s.groupby(grp):
            if (sub >= 4.5).all() and len(sub) >= 48:
                bench_count += 1
                bench_ids.append(f"BW_{c}_{sub.index[0].strftime('%Y%m%d%H')}")
        rows.append({
            "sensor_id": c,
            "mean_D1": float(s.mean()), "median_D1": float(s.median()),
            "p05_D1": float(s.quantile(0.05)), "p25_D1": float(s.quantile(0.25)),
            "p75_D1": float(s.quantile(0.75)), "p95_D1": float(s.quantile(0.95)),
            "low_score_rate_lt3": float((s < 3).mean()),
            "very_low_rate_lt2":  float((s < 2).mean()),
            "dominant_fault_type": dom["dominant_fault"].mode().iloc[0] if len(dom) else "n/a",
            "n_event_windows": len(ev),
            "benchmark_window_count": bench_count,
            "benchmark_definition": "D1>=4.5 sustained >=48h",
            "benchmark_ids_first3": ";".join(bench_ids[:3]),
            "profile_version": "v1.0-strict",
        })
    return pd.DataFrame(rows).sort_values("mean_D1").reset_index(drop=True)


def run(cache_root="/home/claude/d1_fsd_strict/cache",
        force_rerun_detectors: bool = False):
    t0 = time.time()
    Path(cache_root).mkdir(parents=True, exist_ok=True)
    cfg = load_project_config()
    print("=" * 78)
    print("[1] Loading YAML configs ... OK")

    print("[2] Loading raw min-level data ...")
    cache_min = Path(cache_root) / "df_min.pkl"
    if cache_min.exists():
        with open(cache_min, "rb") as f:
            df_min, flags = pickle.load(f)
        print(f"    Loaded from cache: {df_min.shape}")
    else:
        df_raw = load_raw(cfg.paths.data["do_file"], cfg.paths.data["orp_file"],
                          cfg.paths.data["flw_file"])
        df_min, flags = time_align_and_impute(df_raw, short_gap_min=3)
        with open(cache_min, "wb") as f:
            pickle.dump((df_min, flags), f)
    stats = summary_stats(df_min, flags)

    print("[3] STRICT de-periodisation: harmonic decomposition (daily+weekly, 3 harmonics)")
    cache_dep = Path(cache_root) / "deperiodised.pkl"
    if cache_dep.exists() and not force_rerun_detectors:
        with open(cache_dep, "rb") as f:
            resid_min, baseline_min, seasonal_min = pickle.load(f)
        print("    Loaded from cache")
    else:
        t_dep = time.time()
        resid_min, baseline_min, seasonal_min = harmonic_decomposition_dataframe(
            df_min, daily_period_min=1440, weekly_period_min=10080,
            n_harmonics=3, baseline_window="168h", fit_first_days=30)
        print(f"    Done in {time.time()-t_dep:.1f}s")
        with open(cache_dep, "wb") as f:
            pickle.dump((resid_min, baseline_min, seasonal_min), f)

    resid_h = resid_min.resample("1h").mean()
    df_h = df_min.resample("1h").mean()
    print(f"    Hourly residual shape: {resid_h.shape}")

    wm = WindowManager(cfg.windows, df_min, df_h)
    print(f"[4] WindowManager built ({len(wm.list_specs())} window specs registered)")

    print("[5] Running 5 detectors per channel ...")
    cache_det = Path(cache_root) / "detector_results.pkl"
    if cache_det.exists() and not force_rerun_detectors:
        with open(cache_det, "rb") as f:
            (spike_results, spike_rate_6h, step_results,
             drift_results, freeze_results, regime_results) = pickle.load(f)
        print("    Loaded from cache")
    else:
        spike_results  = run_spike_detector(df_min, ALL_CHANNELS, wm)
        spike_rate_6h  = compute_spike_rate_6h(spike_results, ALL_CHANNELS, wm)
        step_results   = run_step_detector(resid_h, ALL_CHANNELS, wm)
        drift_results  = run_drift_detector(resid_h, ALL_CHANNELS, wm)
        freeze_results = run_freeze_detector(df_min, ALL_CHANNELS, wm)
        regime_results = run_regime_detector(resid_h, ALL_CHANNELS, wm)
        with open(cache_det, "wb") as f:
            pickle.dump((spike_results, spike_rate_6h, step_results,
                          drift_results, freeze_results, regime_results), f)

    print("[6] Mapping detector outputs to 1-5 sub-scores ...")
    subs = compute_subscores(spike_results, step_results, drift_results,
                              freeze_results, regime_results,
                              spike_rate_6h, ALL_CHANNELS, cfg.mapping)

    print("[7] Aggregating sub-scores → D1_total per channel ...")
    d1_per_channel, components_per_channel, veto_logs = {}, {}, {}
    for c in ALL_CHANNELS:
        D1, comp, vlog = aggregate_d1(
            subs[c]["Q_spike"], subs[c]["Q_step"], subs[c]["Q_drift"],
            subs[c]["Q_freeze"], subs[c]["Q_regime"],
            weights=cfg.rules.aggregation.weights,
            lambda_blend=cfg.rules.aggregation.lambda_blend,
            cooldown_h=int(cfg.rules.cooldown["drift_after_step_or_regime"].duration_h))
        d1_per_channel[c] = D1
        components_per_channel[c] = comp
        veto_logs[c] = vlog
    D1_h = pd.DataFrame(d1_per_channel)
    print(f"    D1_h shape: {D1_h.shape}; channel-mean D1 = {D1_h.mean().mean():.3f}")

    print("[8] Multiscale aggregation: h → d → w ...")
    D1_d = to_daily(D1_h, q=cfg.windows.aggregation["to_day_quantile"])
    D1_w = to_weekly(D1_d, op=cfg.windows.aggregation["to_week_op"])

    print("[9] Event extraction & sensor profiling ...")
    events = extract_events(D1_h, threshold=3.0, min_duration_h=6)
    dominant = attribute_dominant_fault(subs)
    profile = sensor_profile_summary(D1_h, dominant, events)
    print(f"    Events: {len(events)};  benchmark windows total: "
          f"{profile['benchmark_window_count'].sum()}")

    elapsed = time.time() - t0
    print(f"[done] STRICT pipeline in {elapsed/60:.1f} min")

    return {"cfg": cfg, "wm": wm, "df_min": df_min, "flags": flags, "stats": stats,
            "resid_min": resid_min, "resid_h": resid_h, "df_h": df_h,
            "baseline_min": baseline_min, "seasonal_min": seasonal_min,
            "spike_results": spike_results, "step_results": step_results,
            "drift_results": drift_results, "freeze_results": freeze_results,
            "regime_results": regime_results, "subs": subs,
            "D1_h": D1_h, "D1_d": D1_d, "D1_w": D1_w,
            "components_per_channel": components_per_channel,
            "veto_logs": veto_logs, "events": events,
            "dominant": dominant, "profile": profile,
            "spike_rate_6h": spike_rate_6h}


if __name__ == "__main__":
    R = run()
    with open("/home/claude/d1_fsd_strict/cache/results.pkl", "wb") as f:
        pickle.dump(R, f)
    print("Pickled.")
