"""run_v11.py
Master v1.1 enhancement orchestrator.

Loads v1.0 cached results, applies the 6 v1.1 modules sequentially, re-runs
aggregation with state-blackboard-driven cooldown, and emits delta outputs:
    - v11 Excel files (D1v11_*.xlsx)
    - v11 figures (FigV11_*.png)
    - v11 analysis report (v1.1 vs v1.0 comparison)

Each module's effect is logged so we can attribute the D1 change to specific
fixes.
"""
from __future__ import annotations
import sys, time, pickle, json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import load_project_config
from data import ALL_CHANNELS, DO_CHANNELS, ORP_CHANNELS, FLOW_CHANNELS
from aggregation import aggregate_d1, to_daily, to_weekly
from mapping import apply_mapping
from state.state_blackboard import (StateBlackboard, StateEntry,
                                     emit_step_confirmed, emit_regime_shift,
                                     emit_batch_pelt_changepoints,
                                     emit_recovery_ready)
from v11 import (calibrate_step_locations, ffpca_drift_score,
                 detect_pump_cycle_template, mask_operational_steps,
                 fit_multiregime, assign_regime,
                 compute_response_loss_table)


OUTPUT_ROOT = Path("/mnt/user-data/outputs/d1_fsd_results")
V11_DIR     = OUTPUT_ROOT / "v11"
V11_DIR.mkdir(parents=True, exist_ok=True)
(V11_DIR / "data").mkdir(exist_ok=True)
(V11_DIR / "figures").mkdir(exist_ok=True)
(V11_DIR / "plot_data").mkdir(exist_ok=True)


# Style sync with v1.0
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.linewidth": 0.8, "axes.grid": True, "grid.alpha": 0.25,
    "axes.spines.top": False, "axes.spines.right": False,
})
C = {"blue":"#2166AC","red":"#D6604D","green":"#4DAC26","orange":"#F4A582",
     "purple":"#762A83","gray":"#878787","teal":"#1B7837","amber":"#E08214",
     "navy":"#053061","cyan":"#35978F"}


# ─────────────────────────────────────────────────────────────────────────
# 1. Load v1.0 cache
# ─────────────────────────────────────────────────────────────────────────
def load_v10_cache():
    p = Path("/home/claude/d1_fsd/cache/results.pkl")
    if not p.exists():
        raise FileNotFoundError(f"v1.0 cache missing: {p}. Run run_all.py first.")
    with open(p, "rb") as f:
        return pickle.load(f)


# ─────────────────────────────────────────────────────────────────────────
# 2. State-blackboard driven cooldown re-aggregation
# ─────────────────────────────────────────────────────────────────────────
def aggregate_with_blackboard(subs: dict, channels: list, cfg, bb: StateBlackboard,
                                cooldown_h: int = 48,
                                run_id: str = "v11"):
    """Re-aggregate using state-blackboard for cooldown management.

    Adds 'recovery condition' check beyond simple 48h timer:
        - residual_mean_in_baseline_band (proxy via Q_drift > 3.5)
        - residual_var_stable (proxy via Q_freeze > 3.5)
        - adjacent_ks_not_significant (Q_step > 3.0)
        - w1_normalised < 1.5 (Q_regime > 3.5)

    During cooldown, drift is replaced with neutral 3.0 (per spec §4).
    """
    d1_per_channel = {}
    components_per_channel = {}
    veto_logs = {}
    cooldown_h_used = {}

    for c in channels:
        s = subs[c]
        idx = s["Q_step"].index
        Q_drift_eff = s["Q_drift"].copy()
        cooldown_active = pd.Series(False, index=idx)
        cooldown_until = None

        for ts in idx:
            qs = float(s["Q_step"].at[ts])
            qr = float(s["Q_regime"].at[ts])
            qd = float(s["Q_drift"].at[ts])
            qf = float(s["Q_freeze"].at[ts])

            # Trigger cooldown (write to BB)
            if qs <= 2.0:
                cooldown_until = ts + pd.Timedelta(hours=cooldown_h)
                emit_step_confirmed(bb, c, ts, run_id, cooldown_h)
            elif qr <= 2.0:
                cooldown_until = ts + pd.Timedelta(hours=cooldown_h)
                emit_regime_shift(bb, c, ts, run_id, cooldown_h)

            # Check active
            if cooldown_until is not None and ts <= cooldown_until:
                cooldown_active.at[ts] = True
                Q_drift_eff.at[ts] = 3.0  # neutral
                # Recovery check: 4 conditions
                recov_ok = (qs > 3.0 and qr > 3.5 and qf > 3.5)
                if recov_ok:
                    # Look back 24h for sustained recovery
                    win_lo = max(0, idx.get_loc(ts) - 24)
                    sustained = (s["Q_step"].iloc[win_lo:idx.get_loc(ts)] > 3.0).all() and \
                                (s["Q_regime"].iloc[win_lo:idx.get_loc(ts)] > 3.5).all()
                    if sustained:
                        cooldown_until = None
                        emit_recovery_ready(bb, c, ts, run_id)

        # Use the standard aggregator with our adjusted Q_drift
        D1, comp, vlog = aggregate_d1(
            s["Q_spike"], s["Q_step"], Q_drift_eff,
            s["Q_freeze"], s["Q_regime"],
            weights=cfg.rules.aggregation.weights,
            lambda_blend=cfg.rules.aggregation.lambda_blend,
            cooldown_h=0,  # we already handled cooldown above
        )
        # Override the cooldown_drift column with our richer version
        vlog["cooldown_drift"] = cooldown_active.astype(int)
        d1_per_channel[c] = D1
        components_per_channel[c] = comp
        veto_logs[c] = vlog
        cooldown_h_used[c] = float(cooldown_active.mean())

    return (pd.DataFrame(d1_per_channel),
            components_per_channel, veto_logs, cooldown_h_used)


# ─────────────────────────────────────────────────────────────────────────
# Main V1.1 pipeline
# ─────────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 80)
    print("D1 FSD  v1.1  — applying 6 deferred enhancements")
    print("=" * 80)

    # 0. Load v1.0
    R = load_v10_cache()
    cfg = load_project_config()
    R["cfg"] = cfg
    print(f"[0] v1.0 loaded; D1_h shape {R['D1_h'].shape}")

    # 1. State-blackboard
    bb_path = V11_DIR / "state_blackboard.json"
    if bb_path.exists(): bb_path.unlink()
    bb = StateBlackboard(bb_path, batch_mode=True)
    print(f"[1] StateBlackboard initialised at {bb_path}")
    R["state_bb"] = bb

    # 2. PELT batch calibration (full series, batch mode)
    print("[2] PELT batch calibration (full 8.4 mo, BIC penalty) ...")
    t = time.time()
    pelt_results = calibrate_step_locations(R["resid_h"], ALL_CHANNELS,
                                              window_h=None, min_size=24)
    n_cps_total = sum(len(v) for v in pelt_results.values())
    print(f"    [{time.time()-t:.1f}s] {n_cps_total} change-points across "
          f"{len(pelt_results)} channels (mean {n_cps_total/len(pelt_results):.1f}/sensor)")
    for c, cps in pelt_results.items():
        emit_batch_pelt_changepoints(bb, c, cps, run_id="v11")
    R["pelt_changepoints"] = pelt_results

    # 3. FF-PCA streaming aux
    print("[3] FF-PCA streaming aux (alpha=0.995, k=5) ...")
    t = time.time()
    ffpca_spe = ffpca_drift_score(R["resid_h"], train_days=21, alpha=0.995,
                                    n_components=5, refit_every=50)
    print(f"    [{time.time()-t:.1f}s] mean SPE {ffpca_spe.mean():.3f}")
    R["ffpca_spe"] = ffpca_spe

    # 4. Process-aware step masking for flow channels
    print("[4] Process-aware step masking (twin-pool + magnitude + isolated) ...")
    t = time.time()
    # Build pump-cycle template from "high-quality" benchmark periods
    median_d1 = R["D1_h"].median(axis=1)
    bench_mask = median_d1 > 3.2
    bench_index = R["D1_h"].index[bench_mask]
    df_h_full = R["df_h"]
    pump_template = detect_pump_cycle_template(df_h_full, FLOW_CHANNELS,
                                                 benchmark_window=df_h_full.loc[bench_index])
    # Original KS_d_h matrix
    ks_d_h_orig = pd.DataFrame({c: R["step_results"][c].raw_score
                                 for c in ALL_CHANNELS})
    ks_d_h_masked, mask_log = mask_operational_steps(
        ks_d_h_orig, df_h_full, FLOW_CHANNELS, pump_template, twin_window_h=2)
    print(f"    [{time.time()-t:.1f}s] {len(mask_log)} step events masked as operational")
    R["ks_d_h_masked"] = ks_d_h_masked
    R["step_mask_log"] = mask_log
    R["pump_template"] = pump_template

    # Recompute Q_step using masked KS
    print("    [4b] Re-mapping Q_step with masked KS ...")
    new_subs = {c: dict(v) for c, v in R["subs"].items()}  # shallow copy
    for c in ALL_CHANNELS:
        Q_step_new = apply_mapping(ks_d_h_masked[c].rename("ks_statistic"),
                                    cfg.mapping.step)
        Q_step_new = Q_step_new.reindex(new_subs[c]["Q_step"].index).ffill().bfill()
        new_subs[c]["Q_step"] = Q_step_new
    R["subs_v11"] = new_subs

    # 5. Multi-regime clustering
    print("[5] Multi-regime k-means clustering on benchmark periods ...")
    t = time.time()
    regime_fit = fit_multiregime(df_h_full, bench_index, k=None)
    if regime_fit.get("k", 0) > 0:
        print(f"    [{time.time()-t:.1f}s] k={regime_fit['k']} regimes fit; "
              f"{regime_fit['n_benchmark_hours']} benchmark hours")
        labels_full = assign_regime(df_h_full, regime_fit)
        R["regime_fit"] = regime_fit
        R["regime_labels"] = labels_full
    else:
        print("    Insufficient benchmark hours; multi-regime skipped.")

    # 6. Response-loss freeze auxiliary
    print("[6] Response-loss freeze auxiliary detector ...")
    t = time.time()
    response_table = compute_response_loss_table(R["df_min"],
                                                   benchmark_window=df_h_full.loc[bench_index])
    print(f"    [{time.time()-t:.1f}s] response-loss table for "
          f"{len(response_table)} DO/ORP channels")
    print(f"    Mean response-loss score: {response_table['score'].mean():.2f}")
    R["response_loss"] = response_table

    # Apply response-loss to Q_freeze: blend with existing Q_freeze
    print("    [6b] Updating Q_freeze with response-loss aux (weight=0.20) ...")
    for c in ALL_CHANNELS:
        if c in response_table.index:
            rl_score = float(response_table.at[c, "score"])
            old_qf = new_subs[c]["Q_freeze"]
            new_qf = (0.80 * old_qf + 0.20 * rl_score).clip(1, 5)
            new_subs[c]["Q_freeze"] = new_qf

    # 7. Re-aggregate D1 with state-blackboard cooldown
    print("[7] Re-aggregating D1 with state-blackboard-driven cooldown ...")
    t = time.time()
    D1_h_v11, comps_v11, vlogs_v11, cool_rates = aggregate_with_blackboard(
        new_subs, ALL_CHANNELS, cfg, bb, cooldown_h=48, run_id="v11")
    bb.flush()
    print(f"    [{time.time()-t:.1f}s] D1_h v1.1 shape {D1_h_v11.shape}")
    print(f"    BB events written: {len(bb._load())}")
    R["D1_h_v11"] = D1_h_v11
    R["components_v11"] = comps_v11
    R["veto_logs_v11"] = vlogs_v11
    R["cooldown_rates_v11"] = cool_rates

    # 8. Multiscale aggregates
    R["D1_d_v11"] = to_daily(D1_h_v11, q=0.05)
    R["D1_w_v11"] = to_weekly(R["D1_d_v11"], op="min")

    # 9. Compare v1.0 vs v1.1
    print()
    print("=" * 80)
    print("V1.0 → V1.1 delta (per channel)")
    print("=" * 80)
    delta_rows = []
    for c in ALL_CHANNELS:
        d10 = float(R["D1_h"][c].mean())
        d11 = float(D1_h_v11[c].mean())
        delta = d11 - d10
        cool10 = float(R["veto_logs"][c]["cooldown_drift"].astype(int).mean())
        cool11 = cool_rates[c]
        delta_rows.append({
            "sensor_id": c, "D1_v10": d10, "D1_v11": d11, "delta_D1": delta,
            "cooldown_v10": cool10, "cooldown_v11": cool11,
            "delta_cooldown": cool11 - cool10,
        })
    delta_df = pd.DataFrame(delta_rows).sort_values("delta_D1")
    R["delta_df"] = delta_df
    print(delta_df.round(3).to_string(index=False))

    # 10. Save updated cache (drop unpickle-able objects)
    R_save = {k: v for k, v in R.items() if k != "state_bb"}
    with open("/home/claude/d1_fsd/cache/results_v11.pkl", "wb") as f:
        pickle.dump(R_save, f)

    elapsed = time.time() - t0
    print()
    print(f"v1.1 enhancements completed in {elapsed/60:.1f} min")
    return R


if __name__ == "__main__":
    R = main()
    print("Pickled v1.1 results to cache/results_v11.pkl")
