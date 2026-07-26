"""D1 final-candidate causal sensor-health pipeline.

STRICTLY compliant with the 4 governing spec docs:
    1. Final recovery specification — causal six-state machine
    2. Veto-3_过程感知修订版正式文本_无泵状态最终版.docx — signal-only Veto-3
    3. QR_QIR_仅作为驱动变量纳入D1的修订正式文本_无泵状态最终版.docx — DO/ORP only
    4. D1_ClassCminDQR_Python工程目录结构_核心类设计_注意事项_修订最终版.docx
       — engineering structure

Pipeline:
    [0] Load STRICT V1 baseline (sub-scores + raw detector outputs + raw hourly)
    [1] PELT batch on hourly residuals (DO/ORP only) → emit event_id candidates
    [2] Build event_id timeline per channel
    [3] Run the causal six-state recovery machine per channel
    [4] Multi-regime clustering → D5 templates (NOT D1 scoring)
    [5] QR/QIR side-output annotations (offline, NOT scoring)
    [6] Re-aggregate D1 with signal-only Veto-3
    [7] Persist all artefacts
"""
from __future__ import annotations
import sys, time, pickle, warnings, hashlib, json
warnings.filterwarnings("ignore")
from dataclasses import replace
from pathlib import Path
from datetime import datetime

# Project root = directory containing this script
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd

from src.config.loader import load_project_config
from src.pipeline.window_manager import WindowManager
from src.state.state_blackboard import StateBlackboard, StateEntry
from src.aggregation.cooldown_state_machine import (run_cooldown_state_machine,
                                                     CooldownConfig)
from src.aggregation.recovery_metrics import (
    audit_transition_conservation,
    build_episode_table,
    build_recovery_summary,
    kaplan_meier_recovery,
)
from src.baseline.local_baseline import estimate_empirical_scale_floor
from src.aggregation.d1_aggregator import (aggregate_d1_v11, to_daily, to_weekly,
                                            attribute_dominant_fault, extract_events)
from src.state.auxiliary_modules import (PELTBatchCalibrator, build_regime_features,
                                          cluster_regimes, build_regime_templates,
                                          compute_qr_qir_side_outputs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    OUT = _ROOT / "outputs"
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    LOG = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line); LOG.append(line)

    t0 = time.time()
    log("=" * 78)
    log("D1 final candidate - causal six-state recovery, DO/ORP-only scoring")
    log("=" * 78)

    # ── Load all configs via loader (handles windows: key, relative paths, etc.)
    cfg = load_project_config()
    rules  = cfg.rules          # raw rules.yaml dict
    sm_cfg = cfg.state_machine  # raw state_machine.yaml dict
    calibration_path = _ROOT / "outputs" / "logs" / "D1_step_mapping_calibration.json"
    with open(calibration_path, "r", encoding="utf-8") as handle:
        step_mapping_calibration = json.load(handle)
    if (
        float(cfg.mapping.step.k) != float(step_mapping_calibration["selected_k"])
        or float(cfg.mapping.step.x0) != float(step_mapping_calibration["selected_x0"])
        or cfg.mapping.step.calibration_id != step_mapping_calibration["calibration_id"]
    ):
        raise RuntimeError("Step mapping config does not match its calibration manifest")
    log(f"[cfg] loaded via src.config.loader — windows, mapping, rules, state_machine, paths")

    # ── Channel definitions come from rules.yaml, not hardcoded
    dependency_files = {
        "strict_v1_inputs": _ROOT / "strict_v1_inputs.pkl",
        "raw_hourly": _ROOT / "raw_hourly.pkl",
        "state_machine_config": _ROOT / "configs" / "state_machine.yaml",
        "rules_config": _ROOT / "configs" / "rules.yaml",
        "mapping_config": _ROOT / "configs" / "mapping.yaml",
        "state_machine_code": _ROOT / "src" / "aggregation" / "cooldown_state_machine.py",
        "local_baseline_code": _ROOT / "src" / "baseline" / "local_baseline.py",
        "detector_bridge_code": _ROOT / "load_real_data_v11.py",
        "pls_detector_code": _ROOT / "src" / "detectors" / "drift_pls.py",
        "pls_peer_validation_code": (
            _ROOT / "src" / "validation" / "pls_peer_upgrade.py"
        ),
        "pipeline_code": Path(__file__),
    }
    dependency_hashes = {name: _sha256(path) for name, path in dependency_files.items()}
    run_hash = hashlib.sha256(
        json.dumps(dependency_hashes, sort_keys=True).encode("utf-8")
    ).hexdigest()
    run_id = f"d1-final-{run_hash[:12]}"
    log(f"[cfg] run_id={run_id}, state_machine_version={sm_cfg.get('version', 'unknown')}")

    SCORED_CHANNELS  = rules["scored_channels"]
    SUPPORT_CHANNELS = rules["support_channels"]
    log(f"  SCORED channels  (n={len(SCORED_CHANNELS)}): "
        f"{SCORED_CHANNELS[:4]}...{SCORED_CHANNELS[-3:]}")
    log(f"  SUPPORT channels (n={len(SUPPORT_CHANNELS)}, NOT scored): {SUPPORT_CHANNELS}")

    # ── Aggregation params from rules.yaml
    agg_weights  = rules["aggregation"]["weights"]
    lambda_blend = rules["aggregation"]["lambda_blend"]
    log(f"[cfg] aggregation weights={agg_weights}, lambda={lambda_blend}")

    # Build CooldownConfig from state_machine.yaml
    baseline_cfg = sm_cfg["sustained_anomaly"]["baseline_init"]
    cd_cfg_template = CooldownConfig.from_dict(sm_cfg)
    log(f"[cfg] CooldownConfig: step_ref={cd_cfg_template.step_refractory_h}h, "
        f"regime_ref={cd_cfg_template.regime_refractory_h}h, "
        f"recovery={cd_cfg_template.min_recovery_streak_h}/"
        f"{cd_cfg_template.max_recovery_window_h}h, observation="
        f"{cd_cfg_template.recovered_observation_h}h, W1_hard_gate="
        f"{cd_cfg_template.use_w1_hard_gate}")

    # ── 0. Load STRICT V1 baseline
    log("[0] Loading STRICT V1 baseline ...")
    with open(_ROOT / "strict_v1_inputs.pkl", "rb") as f:
        v1 = pickle.load(f)
    subs_v1      = v1["subs_v1"]
    D1_v1_full   = v1["D1_v1"]
    detectors_raw = v1["detectors"]
    log(f"    V1 D1_full shape: {D1_v1_full.shape}")

    D1_v1_scored = D1_v1_full[SCORED_CHANNELS]
    log(f"    V1 D1_scored shape: {D1_v1_scored.shape}, "
        f"mean = {D1_v1_scored.mean().mean():.3f}")

    with open(_ROOT / "raw_hourly.pkl", "rb") as f:
        raw = pickle.load(f)
    df_h    = raw["df_h"]
    resid_h = raw["resid_h"]
    # §1.1 bridge (audit §3): PELT segments the whitened/routed input (innovation
    # for iid channels, residual for autocorr_aware) and uses a per-channel
    # n_eff to inflate its BIC penalty. Fall back to the residual / n_eff=1 for
    # legacy pkls produced before the bridge.
    pelt_input = raw.get("whitened_input_h", resid_h)
    eff_neff   = raw.get("eff_neff", {})
    log(f"    Raw hourly: {df_h.shape}, "
        f"residual range = {resid_h.min().min():.1f} .. {resid_h.max().max():.1f}")
    if "whitened_input_h" in raw:
        n_susp = sum(1 for v in eff_neff.values() if v < 1.0)
        log(f"    §1.1 bridge active: PELT on whitened_input_h, "
            f"{n_susp} channel(s) with n_eff<1 (penalty inflated)")

    # ── Connect WindowManager to hourly data (cfg.windows already stripped/validated)
    scale_cfg = baseline_cfg["scale_floor"]
    scale_calibration = {}
    for c in SCORED_CHANNELS:
        clean_mask = (subs_v1["Q_step"][c] >= 3.0) & (subs_v1["Q_freeze"][c] >= 3.0)
        scale_calibration[c] = estimate_empirical_scale_floor(
            resid_h[c], valid_mask=clean_mask,
            calibration_h=scale_cfg["calibration_h"],
            rolling_h=scale_cfg["rolling_h"],
            noise_quantile=scale_cfg["noise_quantile"],
            resolution_multiplier=scale_cfg["resolution_multiplier"],
            epsilon=scale_cfg["epsilon"],
        )
    log("[cfg] empirical residual scale floors: " + ", ".join(
        f"{channel}={values['scale_floor']:.4g}"
        for channel, values in scale_calibration.items()
    ))

    wm = WindowManager(cfg.windows, df_min=pd.DataFrame(), df_h=df_h)
    log(f"[WindowManager] {len(wm.list_specs())} window specs: {list(wm.list_specs().keys())}")

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
                                    penalty_factor=2.5, stride_h=336,
                                    neff_ratio=float(eff_neff.get(c, 1.0)))
        events = cal.calibrate_series(pelt_input[c].rename(c))
        pelt_results[c] = events
        for ev in events:
            bb.write(StateEntry(sensor_id=c, flag_name="pelt_changepoint",
                                  flag_value=ev["timestamp"].isoformat(),
                                  start_time=ev["timestamp"].isoformat(),
                                  source="batch_pelt", run_id=run_id,
                                  metadata={
                                      "magnitude": float(ev["magnitude"]),
                                      "signed_magnitude": float(ev["signed_magnitude"]),
                                      "available_at": ev["available_at"].isoformat(),
                                  }))
    n_cps = sum(len(v) for v in pelt_results.values())
    log(f"    [{time.time()-t:.1f}s] {n_cps} PELT CPs across {len(SCORED_CHANNELS)} "
        f"scored channels (mean {n_cps/len(SCORED_CHANNELS):.1f}/sensor)")

    # ── 3. Run the causal six-state recovery machine per scored channel
    log("[3] Running causal six-state recovery machine per scored channel ...")
    t = time.time()
    Q_drift_eff_dict = {}
    state_log_dict   = {}
    transitions_all  = []
    for c in SCORED_CHANNELS:
        # step_confirmed: 两级触发 — confirmed step 才进 Refractory（PDF §六）
        sc_df = detectors_raw.get("step_confirmed_flag")
        step_confirmed_c = sc_df[c] if sc_df is not None and c in sc_df.columns else None
        peer_df = detectors_raw.get("pls_residual_z_hourly")
        peer_residual_c = peer_df[c] if peer_df is not None and c in peer_df.columns else None
        cd_cfg = replace(cd_cfg_template, local_scale_floor=scale_calibration[c]["scale_floor"])
        Q_drift_eff_c, state_log_c, transitions_c = run_cooldown_state_machine(
            sensor_id      = c,
            Q_step         = subs_v1["Q_step"][c],
            Q_regime       = subs_v1["Q_regime"][c],
            Q_drift        = subs_v1["Q_drift"][c],
            Q_freeze       = subs_v1["Q_freeze"][c],
            ks_stat        = detectors_raw["ks_statistic_hourly"][c],
            w1_norm        = detectors_raw["w1_normalised_hourly"][c],
            resid_h        = resid_h[c],
            pelt_changepoints = pelt_results[c],
            step_confirmed = step_confirmed_c,
            peer_residual_z = peer_residual_c,
            cfg            = cd_cfg,
        )
        Q_drift_eff_dict[c] = Q_drift_eff_c
        state_log_dict[c]   = state_log_c
        transitions_all.extend(transitions_c)
        for tr in transitions_c:
            bb.write(StateEntry(sensor_id=c, flag_name=f"state_to_{tr['to_state']}",
                                  flag_value=tr.get("trigger", ""),
                                  start_time=tr["ts"].isoformat(),
                                  source="streaming", run_id=run_id,
                                  metadata={"from": tr["from_state"],
                                              "trigger": tr.get("trigger", "")}))

    log(f"    [{time.time()-t:.1f}s] {len(transitions_all)} state transitions logged")

    state_dist = {}
    for s_name in ["Normal", "Refractory", "BaselinePending", "SustainedAnomaly",
                   "RecoveryCandidate", "Recovered"]:
        cnt = sum((state_log_dict[c]["state_name"] == s_name).sum() for c in SCORED_CHANNELS)
        state_dist[s_name] = cnt
    total_h = sum(state_dist.values())
    log(f"    State coverage (total {total_h}):")
    for s_name, cnt in state_dist.items():
        log(f"      {s_name:20s}: {cnt:7d} ({100*cnt/total_h:5.2f}%)")

    # ── 4. Multi-regime clustering (D5 templates only)
    log("[4] Multi-regime clustering (k=4) — D5 templates, NOT D1 scoring ...")
    t = time.time()
    recovery_episodes = build_episode_table(transitions_all, state_log_dict)
    recovery_summary = build_recovery_summary(recovery_episodes, state_log_dict)
    recovery_km = kaplan_meier_recovery(recovery_episodes)
    transition_qa = audit_transition_conservation(recovery_episodes, transitions_all)
    overall_recovery = recovery_summary.loc[
        recovery_summary["sensor_id"] == "Overall"
    ].iloc[0]
    log(
        "    Event recovery: "
        f"{int(overall_recovery['n_recovered'])}/"
        f"{int(overall_recovery['n_completed'])} completed episodes; "
        f"right-censored={int(overall_recovery['n_right_censored'])}; "
        f"rate={overall_recovery['event_recovery_rate']:.3f}"
    )
    log(f"    Transition conservation: {transition_qa.iloc[0].to_dict()}")
    if not bool(transition_qa.loc[0, "all_opened_accounted"]):
        raise RuntimeError("State-machine episode conservation audit failed")

    feat_df = build_regime_features(df_h, window_h=24)
    regime_info   = cluster_regimes(feat_df, k=4, random_state=42)
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
    log(f"    [{time.time()-t:.1f}s] "
        f"QR jumps: {(qr_qir_annotations['qr_jump_annotation'] != '').sum()}, "
        f"QIR jumps: {(qr_qir_annotations['qir_jump_annotation'] != '').sum()}")

    # ── 6. Re-aggregate final D1 with signal-only Veto-3
    log("[6] Re-aggregating final D1 with signal-only Veto-3 + causal recovery ...")
    t = time.time()
    Q_step_idx    = subs_v1["Q_step"].index
    D1_v11        = pd.DataFrame(index=Q_step_idx)
    components_v11 = {}
    veto_logs_v11  = {}
    subs_v11       = {}
    for c in SCORED_CHANNELS:
        Q_spike_c  = subs_v1["Q_spike"][c]
        Q_step_c   = subs_v1["Q_step"][c]
        Q_drift_c  = subs_v1["Q_drift"][c]
        Q_freeze_c = subs_v1["Q_freeze"][c]
        Q_regime_c = subs_v1["Q_regime"][c]
        Q_drift_eff_c = Q_drift_eff_dict[c]
        subs_v11[c] = {
            "Q_spike":    Q_spike_c,
            "Q_step":     Q_step_c,
            "Q_drift":    Q_drift_eff_c,   # effective drift after α-thaw
            "Q_drift_raw": Q_drift_c,       # kept for audit
            "Q_freeze":   Q_freeze_c,
            "Q_regime":   Q_regime_c,
        }
        D1_, comp, vlog = aggregate_d1_v11(
            Q_spike_c, Q_step_c, Q_drift_eff_c, Q_freeze_c, Q_regime_c,
            state_log    = state_log_dict[c],
            weights      = agg_weights,
            lambda_blend = lambda_blend,
            freeze_thr   = rules["veto"]["freeze_threshold"],
            freeze_cap   = rules["veto"]["freeze_cap"],
            regime_thr   = rules["veto"]["regime_threshold"],
            regime_cap   = rules["veto"]["regime_cap"],
            veto3_step_thr      = rules["veto"]["veto3_step_threshold"],
            veto3_duration_h    = rules["veto"]["veto3_duration_h"],
            veto3_min_event_count = rules["veto"].get("veto3_min_event_count_36h", 6),
            veto3_cap           = rules["veto"]["veto3_cap"],
            sustained_cap       = sm_cfg["sustained_anomaly_cap"],
        )
        D1_v11[c]           = D1_
        components_v11[c]   = comp
        veto_logs_v11[c]    = vlog

    bb.flush()
    log(f"    [{time.time()-t:.1f}s] final D1 mean = {D1_v11.mean().mean():.3f} "
        f"(STRICT V1 scored = {D1_v1_scored.mean().mean():.3f})")

    # ── 7. Multi-scale aggregation + events
    D1_d_v11  = to_daily(D1_v11, q=0.05)
    D1_w_v11  = to_weekly(D1_d_v11, op="min")
    events_v11 = extract_events(D1_v11, threshold=3.0, min_duration_h=6)
    dom_v11    = attribute_dominant_fault(subs_v11)
    log(f"[7] Multi-scale: daily {D1_d_v11.shape}, weekly {D1_w_v11.shape}")
    log(f"    final events (D1<3, duration >=6 h): {len(events_v11)}")

    # ── Per-channel comparison
    log("\n[Per-channel D1 mean comparison: STRICT V1 vs final candidate]")
    delta_rows = []
    for c in SCORED_CHANNELS:
        d1_v1  = float(D1_v1_scored[c].mean())
        d1_v11 = float(D1_v11[c].mean())
        delta  = d1_v11 - d1_v1
        cool_v11  = float((state_log_dict[c]["state_name"] == "Refractory").mean())
        pending_v11 = float((state_log_dict[c]["state_name"] == "BaselinePending").mean())
        sust_v11  = float((state_log_dict[c]["state_name"] == "SustainedAnomaly").mean())
        recov_v11 = float((state_log_dict[c]["state_name"] == "RecoveryCandidate").mean())
        recovered_v11 = float((state_log_dict[c]["state_name"] == "Recovered").mean())
        norm_v11  = float((state_log_dict[c]["state_name"] == "Normal").mean())
        veto3     = float(veto_logs_v11[c]["veto3_signal_only"].mean())
        delta_rows.append({
            "channel": c, "D1_v1": d1_v1, "D1_v11": d1_v11, "delta_D1": delta,
            "Refractory_pct":  cool_v11 * 100,
            "BaselinePending_pct": pending_v11 * 100,
            "Sustained_pct":   sust_v11 * 100,
            "RecCand_pct":     recov_v11 * 100,
            "Recovered_state_occupancy_pct": recovered_v11 * 100,
            "Normal_pct":      norm_v11 * 100,
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
        "scale_calibration": scale_calibration,
        "recovery_episodes": recovery_episodes,
        "recovery_summary": recovery_summary,
        "recovery_km": recovery_km,
        "transition_qa": transition_qa,
        "regime_info": regime_info,
        "regime_labels": regime_labels,
        "regime_templates": templates,
        "qr_qir_annotations": qr_qir_annotations,
        "df_h": df_h, "resid_h": resid_h,
        "whitened_input_h": pelt_input,
        "scoring_mode": raw.get("scoring_mode", {}),
        "eff_neff": eff_neff,
        "step_mapping_calibration": step_mapping_calibration,
        "detectors_raw": detectors_raw,
        "delta_df": delta_df,
        "rules_yaml": rules,
        "state_machine_yaml": sm_cfg,
        "scored_channels": SCORED_CHANNELS,
        "support_channels": SUPPORT_CHANNELS,
        "n_pelt_cps": n_cps,
        "algorithm_version": sm_cfg.get("version", "unknown"),
        "run_id": run_id,
        "dependency_hashes": dependency_hashes,
        "elapsed_sec": time.time() - t0,
    }
    pkl_out = _ROOT / "v11_state.pkl"
    with open(pkl_out, "wb") as f:
        pickle.dump(state, f)
    log(f"    Saved {pkl_out} ({pkl_out.stat().st_size/1e6:.1f} MB)")

    run_manifest = {
        "run_id": run_id,
        "algorithm_version": sm_cfg.get("version", "unknown"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dependency_hashes": dependency_hashes,
        "state_pickle_sha256": _sha256(pkl_out),
        "n_channels": len(SCORED_CHANNELS),
        "n_hourly_rows": len(D1_v11),
        "n_state_transitions": len(transitions_all),
        "n_recovery_episodes": len(recovery_episodes),
        "transition_conservation_passed": bool(
            transition_qa.loc[0, "all_opened_accounted"]
            and transition_qa.loc[0, "all_episodes_terminal_or_censored"]
        ),
        "scale_calibration": scale_calibration,
        "step_mapping_calibration": step_mapping_calibration,
    }
    with open(OUT / "logs" / "D1_run_manifest.json", "w", encoding="utf-8") as handle:
        json.dump(run_manifest, handle, indent=2, ensure_ascii=True)

    with open(OUT / "logs" / "run_v11.log", "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))

    elapsed = time.time() - t0
    log(f"\n{'='*78}")
    log(f"Final-candidate pipeline complete in {elapsed:.1f}s")
    log(f"{'='*78}")
    try:
        from generate_expert_report_v11 import maybe_update_report
        maybe_update_report()
    except Exception as exc:
        log(f"[auto-report] skipped: {exc}")
    return state


if __name__ == "__main__":
    main()
