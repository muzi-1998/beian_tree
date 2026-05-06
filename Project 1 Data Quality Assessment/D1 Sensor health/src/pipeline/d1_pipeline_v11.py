"""src/pipeline/d1_pipeline_v11.py
v1.1 pipeline — extends v1.0 with:
    1. State Blackboard (SQLite-backed)
    2. PELT batch calibration (writes pelt_step events)
    3. FF-PCA streaming (drift aux validator)
    4. Process-aware step masking (flow channels)
    5. Multi-regime k-means clustering
    6. Response-loss freeze auxiliary

Usage:
    R = run_v11()        # produces same R structure as v1.0 plus:
                          # R['blackboard'], R['regime_labels'], R['ffpca'],
                          # R['pelt_events'], R['process_masks'],
                          # R['response_loss']
"""
from __future__ import annotations
import sys, time, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from config import load_project_config
from data import (load_raw, time_align_and_impute, summary_stats,
                  DO_CHANNELS, ORP_CHANNELS, FLOW_CHANNELS, ALL_CHANNELS)
from detectors import (HampelSpikeDetector, AdjacentKSStepDetector,
                       PLSVirtualSensorDetector, CompositeFreezeDetector,
                       W1RegimeDetector, FFPCADetector,
                       PELTBatchCalibrator,
                       detect_response_loss, aggregate_response_loss_score)
from mapping import apply_mapping
from aggregation import (aggregate_d1, to_daily, to_weekly,
                          build_process_mask, apply_process_mask,
                          collect_blackboard_events,
                          FLOW_CHANNELS as FLOW_NAMES)
from baseline import (build_regime_features, cluster_regimes, regime_summary,
                       build_regime_templates)
from state import StateBlackboard


# Re-import v1.0 helpers
from pipeline.d1_pipeline import (
    deperiodise, run_spike_detector, compute_spike_rate_6h,
    run_step_detector, run_drift_detector, run_freeze_detector,
    run_regime_detector, compute_subscores, extract_events,
    attribute_dominant_fault, sensor_profile_summary,
)


def run_v11(cache_root: str = "/home/claude/d1_fsd/cache",
            output_root: str = "/mnt/user-data/outputs/d1_fsd_results_v11"):
    Path(cache_root).mkdir(exist_ok=True)
    Path(output_root).mkdir(parents=True, exist_ok=True)

    cfg = load_project_config()
    print("=" * 80)
    print("D1 v1.1 — full pipeline with 6 v1.1 modules")
    print("=" * 80)

    # ── Step 1. Load raw data (cached) ────────────────────────────────
    cache_f = Path(cache_root) / "df_min.pkl"
    if cache_f.exists():
        with open(cache_f, "rb") as f:
            df_min, flags = pickle.load(f)
        print(f"[1] Cached data loaded: {df_min.shape}")
    else:
        df_raw = load_raw(cfg.paths.data["do_file"], cfg.paths.data["orp_file"],
                          cfg.paths.data["flw_file"])
        df_min, flags = time_align_and_impute(df_raw)
        with open(cache_f, "wb") as f: pickle.dump((df_min, flags), f)
        print(f"[1] Loaded fresh: {df_min.shape}")

    stats = summary_stats(df_min, flags)

    # ── Step 2. De-periodise + hourly ─────────────────────────────────
    print("[2] De-periodising ...")
    resid_min = deperiodise(df_min)
    resid_h = resid_min.resample("1h").mean()
    df_h = df_min.resample("1h").mean()

    # ── Step 3. Initialize state blackboard ──────────────────────────
    print("[3] Initialising state blackboard (SQLite) ...")
    bb = StateBlackboard(str(Path(cache_root) / "state_blackboard.sqlite"))
    bb.clear()  # fresh run
    print(f"    Blackboard at: {bb.db_path}")

    # ── Step 4. Run v1.0 detectors (cached if available) ─────────────
    detector_cache = Path(cache_root) / "detector_results.pkl"
    if detector_cache.exists():
        with open(detector_cache, "rb") as f:
            cached_R = pickle.load(f)
        print(f"[4] Cached detector results loaded")
        spike_results  = cached_R["spike_results"]
        spike_rate_6h  = cached_R["spike_rate_6h"]
        step_results   = cached_R["step_results"]
        drift_results  = cached_R["drift_results"]
        freeze_results = cached_R["freeze_results"]
        regime_results = cached_R["regime_results"]
    else:
        print("[4] Running v1.0 detectors ...")
        spike_results  = run_spike_detector(df_min, ALL_CHANNELS)
        spike_rate_6h  = compute_spike_rate_6h(spike_results, ALL_CHANNELS, df_min.index)
        step_results   = run_step_detector(resid_h, ALL_CHANNELS)
        drift_results  = run_drift_detector(resid_h, ALL_CHANNELS)
        freeze_results = run_freeze_detector(df_min, ALL_CHANNELS)
        regime_results = run_regime_detector(resid_h, ALL_CHANNELS)
        with open(detector_cache, "wb") as f:
            pickle.dump({
                "spike_results": spike_results, "spike_rate_6h": spike_rate_6h,
                "step_results": step_results, "drift_results": drift_results,
                "freeze_results": freeze_results, "regime_results": regime_results,
            }, f)

    # ── Step 5. PELT batch calibration ────────────────────────────────
    print("[5] PELT batch calibration on residuals ...")
    pelt = PELTBatchCalibrator(lookback_hours=48, min_seg_hours=6, penalty_factor=2.0)
    pelt_events_all = []
    for c in ALL_CHANNELS:
        # We do a single pass over the whole history (stride=24h equivalent)
        events = pelt.calibrate_full_history(resid_h[[c]], stride_h=24)
        pelt_events_all.extend(events)
    print(f"    PELT detected {len(pelt_events_all)} change-point windows")
    if pelt_events_all:
        bb.set_flag_bulk(pelt_events_all)

    # ── Step 6. FF-PCA streaming aux ──────────────────────────────────
    print("[6] FF-PCA streaming covariance update ...")
    ffpca = FFPCADetector(alpha=0.995, n_components=5,
                          refresh_every=50, train_steps=168)
    try:
        ffpca_res = ffpca.score(resid_h)
        print(f"    FF-PCA UCL = {ffpca_res.metadata['ucl']:.3f}; "
              f"alarm rate = {ffpca_res.aux_flag.mean():.3f}")
    except Exception as e:
        print(f"    ! FF-PCA failed: {e}")
        ffpca_res = None

    # ── Step 7. Multi-regime clustering ──────────────────────────────
    print("[7] Multi-regime clustering (k=4) ...")
    feat_df = build_regime_features(df_h, window_h=24)
    regime_info = cluster_regimes(feat_df, k=4, random_state=42)
    regime_labels = regime_info["labels"]
    print(f"    Regime distribution: {regime_labels.value_counts().to_dict()}")

    # Write regime assignments to blackboard (one flag per regime span)
    diff = regime_labels.diff().fillna(1) != 0
    starts = regime_labels.index[diff].tolist()
    ends = starts[1:] + [regime_labels.index[-1]]
    regime_events = []
    for s, e, r in zip(starts, ends, regime_labels.loc[starts].values):
        regime_events.append({
            "sensor_id": "ALL", "flag_name": "regime_id",
            "value": {"regime": int(r)},
            "start_time": s, "expire_at": e,
            "source": "regime_clustering",
        })
    bb.set_flag_bulk(regime_events)

    # Build templates per regime
    print("[7b] Building per-regime templates ...")
    # Need preliminary D1_h to identify high-quality hours
    print("     Mapping → preliminary D1 to seed regime templates ...")
    subs_pre = compute_subscores(spike_results, step_results, drift_results,
                                  freeze_results, regime_results,
                                  spike_rate_6h, ALL_CHANNELS, cfg.mapping)
    # Quick aggregate (no v1.1 features yet) for template seeding
    d1_pre_dict = {}
    for c in ALL_CHANNELS:
        D1_, _, _ = aggregate_d1(
            subs_pre[c]["Q_spike"], subs_pre[c]["Q_step"], subs_pre[c]["Q_drift"],
            subs_pre[c]["Q_freeze"], subs_pre[c]["Q_regime"],
            weights=cfg.rules.aggregation.weights,
            lambda_blend=cfg.rules.aggregation.lambda_blend,
            cooldown_h=int(cfg.rules.cooldown["drift_after_step_or_regime"].duration_h))
        d1_pre_dict[c] = D1_
    d1_pre_h = pd.DataFrame(d1_pre_dict)
    regime_templates = build_regime_templates(df_h, regime_labels, d1_pre_h, min_d1=3.5)
    print(f"    Built {len(regime_templates)} regime templates")

    # ── Step 8. Process-aware step masking ────────────────────────────
    print("[8] Process-aware step masking on flow channels ...")
    # Index for masks: hourly (matching subscores)
    process_masks = build_process_mask(df_h,
                                         time_index=subs_pre[ALL_CHANNELS[0]]["Q_step"].index,
                                         flow_channels=FLOW_NAMES, pad_h=2)
    n_pump_cycles = sum(m.sum() for m in process_masks.values())
    print(f"    Process mask flagged {n_pump_cycles} hours across {len(FLOW_NAMES)} flow channels")
    pump_events = collect_blackboard_events(process_masks, df_h)
    if pump_events:
        bb.set_flag_bulk(pump_events)

    # Apply masks to Q_step
    masked_subs = {c: dict(subs_pre[c]) for c in ALL_CHANNELS}
    for c in FLOW_NAMES:
        if c in process_masks:
            masked_subs[c]["Q_step"] = apply_process_mask(
                subs_pre[c]["Q_step"], process_masks[c], neutral_score=3.0)

    # ── Step 9. Response-loss freeze auxiliary (DO/ORP only) ──────────
    print("[9] Response-loss freeze for DO/ORP ...")
    drivers_min = df_min[list(FLOW_NAMES)]
    rl_subs = {}
    for c in DO_CHANNELS + ORP_CHANNELS:
        rl_event = detect_response_loss(df_min[c].rename(c), drivers_min)
        rl_score = aggregate_response_loss_score(rl_event)
        # Reindex to subscore index
        rl_score = rl_score.reindex(masked_subs[c]["Q_step"].index).ffill().bfill()
        rl_subs[c] = rl_score
        # Combine into Q_freeze:  Q_freeze_v11 = 0.55·Q_freeze_v10 + 0.45·Q_responseLoss
        q_freeze_v10 = masked_subs[c]["Q_freeze"]
        masked_subs[c]["Q_freeze"] = (0.55 * q_freeze_v10 + 0.45 * rl_score).clip(1, 5)
    print(f"    Mean response-loss subscore = "
          f"{np.mean([rl_subs[c].mean() for c in rl_subs]):.2f}")

    # ── Step 10. Re-aggregate with v1.1 logic (state-machine cooldown) ──
    print("[10] Re-aggregating with v1.1 state-machine cooldown ...")
    d1_v11 = {}; comp_v11 = {}; veto_v11 = {}
    for c in ALL_CHANNELS:
        # Provide diagnostic series for recovery checks
        rz = drift_results.get(c)
        rz_series = rz.raw_score if rz else None
        ks = step_results[c].raw_score
        w1 = regime_results[c].raw_score

        D1, comp, vlog = aggregate_d1(
            masked_subs[c]["Q_spike"], masked_subs[c]["Q_step"],
            masked_subs[c]["Q_drift"], masked_subs[c]["Q_freeze"],
            masked_subs[c]["Q_regime"],
            weights=cfg.rules.aggregation.weights,
            lambda_blend=cfg.rules.aggregation.lambda_blend,
            cooldown_h=int(cfg.rules.cooldown["drift_after_step_or_regime"].duration_h),
            use_recovery=True, recovery_min_h=24,
            residual_z=rz_series, w1_normalised=w1, ks_statistic=ks,
        )
        d1_v11[c] = D1
        comp_v11[c] = comp
        veto_v11[c] = vlog

    D1_h_v11 = pd.DataFrame(d1_v11)
    print(f"    v1.1 D1 mean = {D1_h_v11.mean().mean():.3f}  "
          f"(v1.0 was {d1_pre_h.mean().mean():.3f})")
    print(f"    Cooldown rate (v1.1 mean) = "
          f"{np.mean([veto_v11[c]['cooldown_drift'].mean() for c in ALL_CHANNELS]):.3f}")

    # ── Step 11. Multiscale aggregation + events + profile ───────────
    D1_d_v11 = to_daily(D1_h_v11, q=cfg.windows.aggregation["to_day_quantile"])
    D1_w_v11 = to_weekly(D1_d_v11, op=cfg.windows.aggregation["to_week_op"])
    events_v11 = extract_events(D1_h_v11, threshold=3.0, min_duration_h=6)
    dominant_v11 = attribute_dominant_fault(masked_subs)
    profile_v11 = sensor_profile_summary(D1_h_v11, dominant_v11, events_v11)
    print(f"    v1.1: {len(events_v11)} events; "
          f"{profile_v11['benchmark_window_count'].sum()} benchmark windows")

    return {
        "cfg": cfg, "df_min": df_min, "flags": flags, "stats": stats,
        "resid_min": resid_min, "resid_h": resid_h, "df_h": df_h,
        # detectors
        "spike_results": spike_results, "step_results": step_results,
        "drift_results": drift_results, "freeze_results": freeze_results,
        "regime_results": regime_results,
        # v1.0 + v1.1 subscores
        "subs_v10": subs_pre,    # before masking, before response-loss
        "subs": masked_subs,     # final v1.1 subscores
        # v1.1 modules
        "blackboard": bb,
        "ffpca": ffpca_res,
        "pelt_events": pelt_events_all,
        "process_masks": process_masks,
        "regime_labels": regime_labels,
        "regime_info": regime_info,
        "regime_templates": regime_templates,
        "response_loss_subs": rl_subs,
        # final outputs
        "D1_h": D1_h_v11, "D1_d": D1_d_v11, "D1_w": D1_w_v11,
        "D1_h_v10": d1_pre_h,    # for direct comparison
        "components_per_channel": comp_v11,
        "veto_logs": veto_v11,
        "events": events_v11, "dominant": dominant_v11, "profile": profile_v11,
        "spike_rate_6h": spike_rate_6h,
    }


if __name__ == "__main__":
    R = run_v11()
    with open("/home/claude/d1_fsd/cache/results_v11.pkl", "wb") as f:
        pickle.dump(R, f)
    print("Pickled v1.1 results")
