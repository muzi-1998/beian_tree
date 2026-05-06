"""run_v11_pipeline.py — D1 v1.1 master orchestrator.

STRICTLY compliant with the 4 governing spec docs:
    1. Cooldown_机制修订版正式文本_无泵状态最终版.docx — 5-state machine
    2. Veto-3_过程感知修订版正式文本_无泵状态最终版.docx — signal-only Veto-3
    3. QR_QIR_仅作为驱动变量纳入D1的修订正式文本_无泵状态最终版.docx — DO/ORP only
    4. D1_ClassCminDQR_Python工程目录结构_核心类设计_注意事项_修订最终版.docx
       — engineering structure

Pipeline:
    [0] Load STRICT V1 baseline (sub-scores + raw detector outputs + raw hourly)
    [1] PELT batch on hourly residuals (DO/ORP only) → emit event_id candidates
    [2] Build event_id timeline per channel
    [3] Run 5-state cooldown machine per channel → Q_drift_eff + state_log
    [4] Multi-regime clustering → D7 templates (NOT D1 scoring)
    [5] QR/QIR side-output annotations (offline, NOT scoring)
    [6] Re-aggregate D1 with v1.1 rules (signal-only Veto-3)
    [7] Persist all artefacts
"""
from __future__ import annotations
import sys, time, pickle, json, warnings, yaml
warnings.filterwarnings("ignore")
from pathlib import Path
from datetime import datetime
ROOT = Path("/home/claude/v11_pipeline")
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.state_blackboard import StateBlackboard, StateEntry
from src.cooldown_state_machine import (run_cooldown_state_machine,
                                          CooldownConfig)
from src.d1_aggregator import (aggregate_d1_v11, to_daily, to_weekly,
                                attribute_dominant_fault, extract_events)
from src.auxiliary_modules import (PELTBatchCalibrator, build_regime_features,
                                    cluster_regimes, build_regime_templates,
                                    compute_qr_qir_side_outputs)


# ─── Channel definitions per spec ──────────────────────────────────────────
ALL_CHANNELS = ['DO_1_1','DO_1_2','DO_1_3','DO_1_4',
                'DO_2_1','DO_2_2','DO_2_3','DO_2_4',
                'ORP_1_1','ORP_1_2','ORP_1_3',
                'ORP_2_1','ORP_2_2','ORP_2_3',
                'QR_1','QR_2','QIR_1','QIR_2']
SCORED_CHANNELS = [c for c in ALL_CHANNELS if c.startswith("DO_") or c.startswith("ORP_")]
SUPPORT_CHANNELS = [c for c in ALL_CHANNELS if c.startswith("Q")]  # QR/QIR


def load_yaml(path):
    with open(path) as f: return yaml.safe_load(f)


def main():
    OUT = ROOT / "outputs"
    LOG = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line); LOG.append(line)

    t0 = time.time()
    log("=" * 78)
    log("D1 v1.1 — DO/ORP-only main link, signal-only Veto-3, 5-state cooldown")
    log("=" * 78)
    log(f"  SCORED channels (n={len(SCORED_CHANNELS)}): "
        f"{SCORED_CHANNELS[:4]}...{SCORED_CHANNELS[-3:]}")
    log(f"  SUPPORT channels (n={len(SUPPORT_CHANNELS)}, NOT scored): {SUPPORT_CHANNELS}")

    # Load configs
    rules = load_yaml(ROOT / "configs" / "rules.yaml")
    sm_cfg = load_yaml(ROOT / "configs" / "state_machine.yaml")
    log(f"[cfg] loaded rules.yaml + state_machine.yaml")

    # Build CooldownConfig from YAML
    cd_cfg = CooldownConfig(
        step_refractory_h=sm_cfg["refractory"]["step_h"],
        regime_refractory_h=sm_cfg["refractory"]["regime_h"],
        drift_neutral_score=sm_cfg["refractory"]["drift_neutral_score"],
        min_event_separation_h=sm_cfg["event_uniqueness"]["min_separation_h"],
        magnitude_change_pct=sm_cfg["event_uniqueness"]["magnitude_change_pct"],
        candidate_search_after_step=tuple(sm_cfg["sustained_anomaly"]["candidate_window_search"]["step_after_h"]),
        candidate_search_after_regime=tuple(sm_cfg["sustained_anomaly"]["candidate_window_search"]["regime_after_h"]),
        stable_window_h=sm_cfg["sustained_anomaly"]["candidate_window_search"]["stable_window_h"],
        drift_slope_threshold=sm_cfg["sustained_anomaly"]["baseline_init"]["drift_slope_threshold"],
        thaw_duration_h=sm_cfg["sustained_anomaly"]["thaw"]["duration_h"],
        enter_recov_q_step=sm_cfg["recovery"]["enter_thresholds"]["Q_step_min"],
        enter_recov_q_regime=sm_cfg["recovery"]["enter_thresholds"]["Q_regime_min"],
        enter_recov_q_freeze=sm_cfg["recovery"]["enter_thresholds"]["Q_freeze_min"],
        residual_z_max=sm_cfg["recovery"]["residual_check"]["max_z_score"],
        w1_norm_max=sm_cfg["recovery"]["residual_check"]["max_w1_norm"],
        min_recovery_streak_h=sm_cfg["recovery"]["min_streak_h"],
        sustained_anomaly_cap=sm_cfg["sustained_anomaly_cap"],
    )
    log(f"[cfg] CooldownConfig: step_ref={cd_cfg.step_refractory_h}h, "
        f"regime_ref={cd_cfg.regime_refractory_h}h, "
        f"thaw={cd_cfg.thaw_duration_h}h, recov_streak={cd_cfg.min_recovery_streak_h}h")

    # ── 0. Load STRICT V1 baseline
    log("[0] Loading STRICT V1 baseline ...")
    with open(ROOT / "strict_v1_inputs.pkl", "rb") as f:
        v1 = pickle.load(f)
    subs_v1 = v1["subs_v1"]   # dict of DataFrames keyed by Q_xxx
    D1_v1_full = v1["D1_v1"]  # full 18-channel D1 from STRICT V1
    detectors_raw = v1["detectors"]
    log(f"    V1 D1_full shape: {D1_v1_full.shape} (all 18 ch from STRICT V1)")

    # Build SCORED-only V1 baseline for comparison
    D1_v1_scored = D1_v1_full[SCORED_CHANNELS]
    log(f"    V1 D1_scored shape: {D1_v1_scored.shape}, "
        f"mean = {D1_v1_scored.mean().mean():.3f}")

    with open(ROOT / "raw_hourly.pkl", "rb") as f:
        raw = pickle.load(f)
    df_h = raw["df_h"]
    resid_h = raw["resid_h"]
    log(f"    Raw hourly: {df_h.shape}, "
        f"residual range = {resid_h.min().min():.1f} .. {resid_h.max().max():.1f}")

    # ── 1. State blackboard
    log("[1] Initialising StateBlackboard ...")
    bb_path = OUT / "logs" / "state_blackboard.json"
    if bb_path.exists(): bb_path.unlink()
    bb = StateBlackboard(bb_path, batch_mode=True)

    # ── 2. PELT batch — only on SCORED channels (DO/ORP)
    log("[2] PELT batch on SCORED channels (DO/ORP only) ...")
    t = time.time()
    pelt_results = {}
    for c in SCORED_CHANNELS:
        cal = PELTBatchCalibrator(lookback_hours=720, min_seg_hours=12,
                                    penalty_factor=2.5, stride_h=336)
        events = cal.calibrate_series(resid_h[c].rename(c))
        pelt_results[c] = events
        for ev in events:
            bb.write(StateEntry(sensor_id=c, flag_name="pelt_changepoint",
                                  flag_value=ev["timestamp"].isoformat(),
                                  start_time=ev["timestamp"].isoformat(),
                                  source="batch_pelt", run_id="v11",
                                  metadata={"magnitude": float(ev["magnitude"])}))
    n_cps = sum(len(v) for v in pelt_results.values())
    log(f"    [{time.time()-t:.1f}s] {n_cps} PELT CPs across {len(SCORED_CHANNELS)} "
        f"scored channels (mean {n_cps/len(SCORED_CHANNELS):.1f}/sensor)")

    # ── 3. Run 5-state cooldown machine per scored channel
    log("[3] Running 5-state cooldown machine per scored channel ...")
    t = time.time()
    Q_drift_eff_dict = {}
    state_log_dict = {}
    transitions_all = []
    for c in SCORED_CHANNELS:
        Q_drift_eff_c, state_log_c, transitions_c = run_cooldown_state_machine(
            sensor_id=c,
            Q_step=subs_v1["Q_step"][c],
            Q_regime=subs_v1["Q_regime"][c],
            Q_drift=subs_v1["Q_drift"][c],
            Q_freeze=subs_v1["Q_freeze"][c],
            ks_stat=detectors_raw["ks_statistic_hourly"][c],
            w1_norm=detectors_raw["w1_normalised_hourly"][c],
            resid_h=resid_h[c],
            pelt_changepoints=[ev["timestamp"] for ev in pelt_results[c]],
            cfg=cd_cfg,
        )
        Q_drift_eff_dict[c] = Q_drift_eff_c
        state_log_dict[c] = state_log_c
        transitions_all.extend(transitions_c)
        # Write state transitions to blackboard
        for tr in transitions_c:
            bb.write(StateEntry(sensor_id=c, flag_name=f"state_to_{tr['to_state']}",
                                  flag_value=tr.get("trigger", ""),
                                  start_time=tr["ts"].isoformat(),
                                  source="streaming", run_id="v11",
                                  metadata={"from": tr["from_state"],
                                              "trigger": tr.get("trigger", "")}))

    log(f"    [{time.time()-t:.1f}s] {len(transitions_all)} state transitions logged")

    # State distribution summary
    state_dist = {}
    for s_name in ["Normal", "Refractory", "SustainedAnomaly", "RecoveryCandidate", "Recovered"]:
        cnt = 0
        for c in SCORED_CHANNELS:
            cnt += (state_log_dict[c]["state_name"] == s_name).sum()
        state_dist[s_name] = cnt
    total_h = sum(state_dist.values())
    log(f"    State coverage (total {total_h}):")
    for s_name, cnt in state_dist.items():
        log(f"      {s_name:20s}: {cnt:7d} ({100*cnt/total_h:5.2f}%)")

    # ── 4. Multi-regime clustering (D7 templates only)
    log("[4] Multi-regime clustering (k=4) — D7 templates, NOT D1 scoring ...")
    t = time.time()
    feat_df = build_regime_features(df_h, window_h=24)
    regime_info = cluster_regimes(feat_df, k=4, random_state=42)
    regime_labels = regime_info["labels"]
    log(f"    [{time.time()-t:.1f}s] regime distribution: "
        f"{regime_labels.value_counts().to_dict()}")
    templates = build_regime_templates(df_h, regime_labels, D1_v1_scored,
                                         min_d1=3.5, scored_channels=SCORED_CHANNELS)
    log(f"    Built {len(templates)} regime templates")

    # ── 5. QR/QIR side annotations (offline only)
    log("[5] QR/QIR side annotations (offline only, NOT D1 scoring) ...")
    t = time.time()
    qr_qir_annotations = compute_qr_qir_side_outputs(df_h)
    log(f"    [{time.time()-t:.1f}s] driver_note rows: "
        f"{(qr_qir_annotations['qr_jump_annotation'] != '').sum()} QR jumps, "
        f"{(qr_qir_annotations['qir_jump_annotation'] != '').sum()} QIR jumps")

    # ── 6. Re-aggregate D1 v1.1 with signal-only Veto-3
    log("[6] Re-aggregating D1 v1.1 with signal-only Veto-3 + 5-state machine ...")
    t = time.time()
    Q_step_idx = subs_v1["Q_step"].index
    D1_v11 = pd.DataFrame(index=Q_step_idx)
    components_v11 = {}
    veto_logs_v11 = {}
    subs_v11 = {}
    for c in SCORED_CHANNELS:
        # v1.1 sub-scores: keep STRICT V1 except replace Q_drift with Q_drift_eff
        # (no process-aware step masking, no response-loss aux per QR_QIR 修订)
        Q_spike_c = subs_v1["Q_spike"][c]
        Q_step_c  = subs_v1["Q_step"][c]
        Q_drift_c = subs_v1["Q_drift"][c]
        Q_freeze_c = subs_v1["Q_freeze"][c]
        Q_regime_c = subs_v1["Q_regime"][c]
        # Q_drift_eff comes from state machine
        Q_drift_eff_c = Q_drift_eff_dict[c]
        subs_v11[c] = {
            "Q_spike": Q_spike_c,
            "Q_step": Q_step_c,
            "Q_drift": Q_drift_eff_c,    # effective drift after α-thaw
            "Q_drift_raw": Q_drift_c,     # keep for audit
            "Q_freeze": Q_freeze_c,
            "Q_regime": Q_regime_c,
        }
        D1_, comp, vlog = aggregate_d1_v11(
            Q_spike_c, Q_step_c, Q_drift_eff_c, Q_freeze_c, Q_regime_c,
            state_log=state_log_dict[c],
            freeze_thr=rules["veto"]["freeze_threshold"],
            freeze_cap=rules["veto"]["freeze_cap"],
            regime_thr=rules["veto"]["regime_threshold"],
            regime_cap=rules["veto"]["regime_cap"],
            veto3_step_thr=rules["veto"]["veto3_step_threshold"],
            veto3_duration_h=rules["veto"]["veto3_duration_h"],
            veto3_cap=rules["veto"]["veto3_cap"],
            sustained_cap=sm_cfg["sustained_anomaly_cap"],
        )
        D1_v11[c] = D1_
        components_v11[c] = comp
        veto_logs_v11[c] = vlog

    bb.flush()
    log(f"    [{time.time()-t:.1f}s] D1 v1.1 mean = {D1_v11.mean().mean():.3f} "
        f"(STRICT V1 scored = {D1_v1_scored.mean().mean():.3f})")

    # ── 7. Multi-scale aggregation + events
    D1_d_v11 = to_daily(D1_v11, q=0.05)
    D1_w_v11 = to_weekly(D1_d_v11, op="min")
    events_v11 = extract_events(D1_v11, threshold=3.0, min_duration_h=6)
    dom_v11 = attribute_dominant_fault(subs_v11)
    log(f"[7] Multi-scale: daily {D1_d_v11.shape}, weekly {D1_w_v11.shape}")
    log(f"    v1.1 events (D1<3, dur≥6h): {len(events_v11)}")

    # ── Per-channel comparison
    log("\n[Per-channel D1 mean comparison: STRICT V1 vs v1.1]")
    delta_rows = []
    for c in SCORED_CHANNELS:
        d1_v1 = float(D1_v1_scored[c].mean())
        d1_v11 = float(D1_v11[c].mean())
        delta = d1_v11 - d1_v1
        cool_v11 = float((state_log_dict[c]["state_name"] == "Refractory").mean())
        sust_v11 = float((state_log_dict[c]["state_name"] == "SustainedAnomaly").mean())
        recov_v11 = float((state_log_dict[c]["state_name"] == "RecoveryCandidate").mean())
        normal_v11 = float((state_log_dict[c]["state_name"] == "Normal").mean())
        veto3 = float(veto_logs_v11[c]["veto3_signal_only"].mean())
        delta_rows.append({
            "channel": c, "D1_v1": d1_v1, "D1_v11": d1_v11, "delta_D1": delta,
            "Refractory_pct": cool_v11 * 100,
            "Sustained_pct": sust_v11 * 100,
            "RecCand_pct": recov_v11 * 100,
            "Normal_pct": normal_v11 * 100,
            "veto3_signal_only_pct": veto3 * 100,
        })
    delta_df = pd.DataFrame(delta_rows).sort_values("delta_D1")
    print(delta_df.round(3).to_string(index=False))
    log(f"\n    Mean Δ = {delta_df['delta_D1'].mean():+.4f}")
    log(f"    Max +Δ = {delta_df['delta_D1'].max():+.4f} "
        f"({delta_df.loc[delta_df['delta_D1'].idxmax(),'channel']})")
    log(f"    Min Δ  = {delta_df['delta_D1'].min():+.4f} "
        f"({delta_df.loc[delta_df['delta_D1'].idxmin(),'channel']})")

    # ── 8. Persist all artefacts
    log("[8] Persisting artefacts ...")
    state = {
        "subs_v1": subs_v1, "subs_v11": subs_v11,
        "D1_v1_full": D1_v1_full,
        "D1_v1_scored": D1_v1_scored,
        "D1_v11": D1_v11,
        "D1_d_v11": D1_d_v11, "D1_w_v11": D1_w_v11,
        "components_v11": components_v11,
        "veto_logs_v11": veto_logs_v11,
        "Q_drift_eff_dict": Q_drift_eff_dict,
        "state_log_dict": state_log_dict,
        "transitions_all": transitions_all,
        "state_dist": state_dist,
        "events_v11": events_v11,
        "dominant_v11": dom_v11,
        "pelt_results": pelt_results,
        "regime_info": regime_info,
        "regime_labels": regime_labels,
        "regime_templates": templates,
        "qr_qir_annotations": qr_qir_annotations,
        "df_h": df_h, "resid_h": resid_h,
        "detectors_raw": detectors_raw,
        "delta_df": delta_df,
        "rules_yaml": rules,
        "state_machine_yaml": sm_cfg,
        "scored_channels": SCORED_CHANNELS,
        "support_channels": SUPPORT_CHANNELS,
        "n_pelt_cps": n_cps,
        "elapsed_sec": time.time() - t0,
    }
    with open(ROOT / "v11_state.pkl", "wb") as f:
        pickle.dump(state, f)
    log(f"    Saved v11_state.pkl ({(ROOT/'v11_state.pkl').stat().st_size/1e6:.1f} MB)")

    # Save log
    with open(OUT / "logs" / "run_v11.log", "w") as f:
        f.write("\n".join(LOG))

    elapsed = time.time() - t0
    log(f"\n{'='*78}")
    log(f"v1.1 pipeline complete in {elapsed:.1f}s")
    log(f"{'='*78}")
    return state


if __name__ == "__main__":
    main()
