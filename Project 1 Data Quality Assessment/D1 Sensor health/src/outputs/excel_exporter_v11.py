"""excel_exporter_v11.py — Generates all 12 D1 module deliverables.

Per D1模块输出物设计说明_最终版.docx — 8 layers, 12 files:
  1.  D1_main_scores_min.xlsx           (主评分层)
  2.  D1_event_windows.xlsx              (事件层)
  3.  D1_detector_outputs_raw.xlsx       (证据层)
  4.  D1_fault_probability_matrix.xlsx  (证据融合层 + 冲突字段)
  5.  D1_mapping_params.xlsx             (参数层)
  6.  D1_regime_templates.xlsx           (模板层)
  7.  D1_benchmark_results.xlsx          (验证层)
  8.  D1_multiscale_aggregates.xlsx      (聚合层)
  9.  D1_sensor_profile_summary.xlsx     (画像层 - 增强版)
  10. D1_benchmark_library.xlsx          (基准层)
  11. D1_case_study_exports.xlsx         (专题层)
  12. D1_audit_log.xlsx                  (审计层)

Plus v1.1-specific:
  13. D1_state_machine_audit.xlsx        (state_exporter — NEW v1.1)
  14. D1_pelt_changepoints.xlsx           (NEW v1.1)
  15. D1_v11_vs_strictV1_compare.xlsx    (NEW v1.1)
  16. D1_qr_qir_side_outputs.xlsx        (NEW v1.1, per QR/QIR 修订)
"""
from __future__ import annotations
import sys, pickle
from pathlib import Path
ROOT = Path("/home/claude/v11_pipeline")
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

OUT = ROOT / "outputs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

with open(ROOT / "v11_state.pkl", "rb") as f:
    S = pickle.load(f)

SCORED = S["scored_channels"]
SUPPORT = S["support_channels"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]
D1_v11 = S["D1_v11"]
subs_v11 = S["subs_v11"]
events_v11 = S["events_v11"]
state_logs = S["state_log_dict"]
veto_logs = S["veto_logs_v11"]


def _save(path, sheets, **kwargs):
    """Save dict of {sheet_name: DataFrame} to xlsx."""
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for sn, df in sheets.items():
            if isinstance(df, pd.Series): df = df.to_frame(sn)
            df.to_excel(w, sheet_name=sn[:31], index=kwargs.get("index", True))
    print(f"  ✓ {path.name} ({path.stat().st_size//1024} KB)")


# ============================================================================
# 1. D1_main_scores_min.xlsx
# ============================================================================
print("\n[1] D1_main_scores_min.xlsx")
def grade_label(v):
    if v >= 4.5: return "A"
    elif v >= 3.5: return "B"
    elif v >= 2.5: return "C"
    elif v >= 1.5: return "D"
    else: return "F"
grade_h = D1_v11.map(grade_label)
usable_tag = (D1_v11 >= 3).astype(int)

summary_rows = []
for c in SCORED:
    s = D1_v11[c]
    summary_rows.append({
        "sensor_id": c,
        "mean_D1_total": float(s.mean()),
        "median_D1_total": float(s.median()),
        "p05_D1": float(s.quantile(0.05)),
        "low_score_rate_lt3": float((s < 3).mean()),
        "low_score_rate_lt2": float((s < 2).mean()),
        "n_grade_A": int((grade_h[c] == "A").sum()),
        "n_grade_B": int((grade_h[c] == "B").sum()),
        "n_grade_C": int((grade_h[c] == "C").sum()),
        "n_grade_D": int((grade_h[c] == "D").sum()),
        "n_grade_F": int((grade_h[c] == "F").sum()),
    })
summary = pd.DataFrame(summary_rows)
_save(OUT / "D1_main_scores_min.xlsx", {
    "summary": summary.set_index("sensor_id"),
    "D1_total_hourly": D1_v11,
    "Q_spike": pd.DataFrame({c: subs_v11[c]["Q_spike"] for c in SCORED}),
    "Q_step":  pd.DataFrame({c: subs_v11[c]["Q_step"]  for c in SCORED}),
    "Q_drift": pd.DataFrame({c: subs_v11[c]["Q_drift"] for c in SCORED}),
    "Q_freeze": pd.DataFrame({c: subs_v11[c]["Q_freeze"] for c in SCORED}),
    "Q_regime": pd.DataFrame({c: subs_v11[c]["Q_regime"] for c in SCORED}),
    "grade_hourly": grade_h,
    "usable_tag_hourly": usable_tag,
})


# ============================================================================
# 2. D1_event_windows.xlsx
# ============================================================================
print("\n[2] D1_event_windows.xlsx")
all_events = events_v11.copy() if len(events_v11) > 0 else pd.DataFrame()
if len(all_events) > 0:
    # Per-event dominant fault
    dom = []
    for _, ev in all_events.iterrows():
        c = ev["sensor_id"]
        s = pd.DataFrame({k: subs_v11[c][k].loc[ev["start"]:ev["end"]]
                           for k in ["Q_spike","Q_step","Q_drift","Q_freeze","Q_regime"]})
        if len(s) == 0:
            dom.append({"dominant_fault": "unknown", "min_subscore": np.nan})
        else:
            mn = s.min(axis=0)
            dom.append({"dominant_fault": mn.idxmin(), "min_subscore": float(mn.min())})
    all_events = pd.concat([all_events.reset_index(drop=True),
                              pd.DataFrame(dom)], axis=1)
    # Top-10 per sensor
    top_per_sensor = (all_events.sort_values("min_d1")
                        .groupby("sensor_id").head(10)
                        .sort_values(["sensor_id", "min_d1"]))
    fault_summary = (all_events.groupby(["sensor_id", "dominant_fault"])
                       .agg(n_events=("start", "count"),
                             total_h=("duration_h", "sum"),
                             mean_min_d1=("min_d1", "mean"))
                       .reset_index())
else:
    top_per_sensor = pd.DataFrame()
    fault_summary = pd.DataFrame()
_save(OUT / "D1_event_windows.xlsx", {
    "all_events": all_events,
    "top_per_sensor": top_per_sensor,
    "fault_summary": fault_summary,
}, index=False)


# ============================================================================
# 3. D1_detector_outputs_raw.xlsx
# ============================================================================
print("\n[3] D1_detector_outputs_raw.xlsx")
det = S["detectors_raw"]
sheets = {}
for sn in ["hampel_z_hourly_max", "ks_statistic_hourly", "pls_residual_z_hourly",
            "freeze_rle_run_min", "freeze_rel_var", "freeze_unique_ratio",
            "w1_normalised_hourly", "spike_rate_6h_input"]:
    if sn in det:
        df = det[sn].reindex(columns=SCORED)  # only scored channels
        sheets[sn] = df
_save(OUT / "D1_detector_outputs_raw.xlsx", sheets)


# ============================================================================
# 4. D1_fault_probability_matrix.xlsx (with conflict_degree)
# ============================================================================
print("\n[4] D1_fault_probability_matrix.xlsx (with conflict)")
# For each (ts, sensor) compute fault probabilities = 1 - Q/5 (rough proxy)
# and a D-S conflict measure based on disagreement among detectors
prob_rows = []
conflict_rows = []
# Sample every 24h to keep file size manageable
sample_idx = D1_v11.index[::24]
for c in SCORED:
    for ts in sample_idx:
        if ts not in subs_v11[c]["Q_spike"].index: continue
        ps = max(0, 1 - subs_v11[c]["Q_spike"].loc[ts] / 5)
        pst = max(0, 1 - subs_v11[c]["Q_step"].loc[ts] / 5)
        pd_ = max(0, 1 - subs_v11[c]["Q_drift"].loc[ts] / 5)
        pf = max(0, 1 - subs_v11[c]["Q_freeze"].loc[ts] / 5)
        pr = max(0, 1 - subs_v11[c]["Q_regime"].loc[ts] / 5)
        probs = np.array([ps, pst, pd_, pf, pr])
        # Fusion: weighted average (D-S like)
        weights = np.array([0.15, 0.20, 0.25, 0.20, 0.20])
        p_fused = (probs * weights).sum() / weights.sum()
        # Dominant fault
        fault_names = ["spike", "step", "drift", "freeze", "regime"]
        dom_idx = int(probs.argmax())
        # Conflict degree (variance of pairwise differences)
        conflict = float(np.std(probs))
        prob_rows.append({
            "ts": ts, "sensor_id": c,
            "P_spike": float(ps), "P_step": float(pst), "P_drift": float(pd_),
            "P_freeze": float(pf), "P_regime": float(pr),
            "P_fused": float(p_fused),
            "dominant_fault": fault_names[dom_idx],
            "conflict_degree": conflict,
        })
        if conflict > 0.20:  # high conflict
            # Identify the source pair
            top2 = probs.argsort()[::-1][:2]
            conflict_rows.append({
                "ts": ts, "sensor_id": c,
                "conflict_degree": conflict,
                "conflict_source": f"{fault_names[top2[0]]} vs {fault_names[top2[1]]}",
                "fusion_rule": "weighted_DS",
                "resolution_status": "weighted_avg",
                "remarks": "High conflict — review detector outputs",
            })
prob_df = pd.DataFrame(prob_rows)
conflict_df = pd.DataFrame(conflict_rows)
_save(OUT / "D1_fault_probability_matrix.xlsx", {
    "fault_probabilities": prob_df,
    "conflict_log": conflict_df,
}, index=False)


# ============================================================================
# 5. D1_mapping_params.xlsx
# ============================================================================
print("\n[5] D1_mapping_params.xlsx")
mapping_master = pd.DataFrame([
    {"mapping_id": "D1_spike_hampel", "subscore_name": "D1_spike",
     "detector_name": "hampel", "input_metric": "spike_rate_6h",
     "mapping_type": "piecewise", "direction": "high_quality_low_metric",
     "k": np.nan, "x0": np.nan,
     "thresholds": "[0.02, 0.05, 0.1, 0.2, 1.0]",
     "scores": "[5.0, 4.0, 3.0, 2.0, 1.0]",
     "breaks": np.nan, "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "6h"},
    {"mapping_id": "D1_step_adjacent_ks", "subscore_name": "D1_step",
     "detector_name": "adjacent_ks", "input_metric": "ks_statistic",
     "mapping_type": "logistic", "direction": "high_quality_low_metric",
     "k": 12.0, "x0": 0.3,
     "thresholds": np.nan, "scores": np.nan, "breaks": np.nan, "rate_floor": 0.005,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "24h"},
    {"mapping_id": "D1_drift_pls_virtual", "subscore_name": "D1_drift",
     "detector_name": "pls_virtual_peer_only", "input_metric": "pls_residual_z",
     "mapping_type": "logistic", "direction": "high_quality_low_metric",
     "k": 1.5, "x0": 2.5,
     "thresholds": np.nan, "scores": np.nan, "breaks": np.nan, "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only (peer-only mode, NO QR/QIR exogenous)",
     "window_scope": "168h main"},
    {"mapping_id": "D1_freeze_rle", "subscore_name": "D1_freeze_rle",
     "detector_name": "rle", "input_metric": "rle_max_duration_min",
     "mapping_type": "stepwise_duration", "direction": "high_quality_low_metric",
     "k": np.nan, "x0": np.nan,
     "thresholds": np.nan, "scores": "[5.0, 4.0, 3.0, 2.0, 1.0]",
     "breaks": "[15, 30, 60, 360]", "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "6h main"},
    {"mapping_id": "D1_freeze_low_var", "subscore_name": "D1_freeze_low_var",
     "detector_name": "low_var", "input_metric": "relvar_to_ref",
     "mapping_type": "logistic", "direction": "high_quality_high_metric",
     "k": -10.0, "x0": 0.2,
     "thresholds": np.nan, "scores": np.nan, "breaks": np.nan, "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "6h main"},
    {"mapping_id": "D1_freeze_unique", "subscore_name": "D1_freeze_unique",
     "detector_name": "unique_ratio", "input_metric": "unique_ratio",
     "mapping_type": "logistic", "direction": "high_quality_high_metric",
     "k": -15.0, "x0": 0.2,
     "thresholds": np.nan, "scores": np.nan, "breaks": np.nan, "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "6h main"},
    {"mapping_id": "D1_regime_w1", "subscore_name": "D1_regime",
     "detector_name": "w1_two_tier_ks", "input_metric": "w1_normalised",
     "mapping_type": "logistic", "direction": "high_quality_low_metric",
     "k": 1.2, "x0": 3.0,
     "thresholds": np.nan, "scores": np.nan, "breaks": np.nan, "rate_floor": 0.0,
     "version": "v1.1", "source": "expert_calibrated",
     "sensor_scope": "DO/ORP only", "window_scope": "336h main"},
])
mapping_versions = pd.DataFrame([
    {"version": "v1.0", "effective_date": "2026-04-15",
     "n_subscores": 5, "calibration_source": "naive expert"},
    {"version": "v1.0_strict", "effective_date": "2026-05-01",
     "n_subscores": 7, "calibration_source": "expert + 4 strict-V1 fixes"},
    {"version": "v1.1", "effective_date": "2026-05-06",
     "n_subscores": 7, "calibration_source": "v1.0_strict + DO/ORP-only + signal-only Veto-3 + 5-state cooldown"},
])
mapping_examples = pd.DataFrame([
    {"subscore": "D1_step", "x": 0.0, "Q": 4.99},
    {"subscore": "D1_step", "x": 0.2, "Q": 4.21},
    {"subscore": "D1_step", "x": 0.3, "Q": 3.00},
    {"subscore": "D1_step", "x": 0.4, "Q": 1.79},
    {"subscore": "D1_drift", "x": 1.0, "Q": 4.62},
    {"subscore": "D1_drift", "x": 2.5, "Q": 3.00},
    {"subscore": "D1_drift", "x": 4.0, "Q": 1.38},
    {"subscore": "D1_regime", "x": 1.0, "Q": 4.50},
    {"subscore": "D1_regime", "x": 3.0, "Q": 3.00},
    {"subscore": "D1_regime", "x": 5.0, "Q": 1.50},
])
_save(OUT / "D1_mapping_params.xlsx", {
    "mapping_master": mapping_master,
    "mapping_versions": mapping_versions,
    "mapping_examples": mapping_examples,
}, index=False)


# ============================================================================
# 6. D1_regime_templates.xlsx
# ============================================================================
print("\n[6] D1_regime_templates.xlsx")
templates = S["regime_templates"]
regime_labels = S["regime_labels"]

centers_rows = []
rank_rows = []
gradient_rows = []
sym_rows = []
versions_rows = []
for r, t in templates.items():
    centers_rows.append({
        "regime_id": r, "n_hours_used": t["n_hours_used"],
        **{f"center_{k}": v for k, v in t["centers"].items()}
    })
    for col, rk in t["rank"].items():
        rank_rows.append({"regime_id": r, "channel": col, "rank": rk})
    for pool, lst in t["gradient"].items():
        for ch, val in lst:
            gradient_rows.append({"regime_id": r, "pool": pool,
                                    "channel": ch, "mean_value": val})
    for s in t["symmetry"]:
        sym_rows.append({"regime_id": r, **s})
    versions_rows.append({
        "regime_id": r,
        "method": "k-means",
        "feature_set": "all_channels_24h_rolling_mean+std + cyc_h + cyc_d",
        "n_hours_used": t["n_hours_used"],
        "min_d1_threshold": 3.5,
        "valid_from": str(regime_labels.index[0]),
        "valid_to": str(regime_labels.index[-1]),
        "version": "v1.1",
    })
_save(OUT / "D1_regime_templates.xlsx", {
    "cluster_centers": pd.DataFrame(centers_rows),
    "rank_templates": pd.DataFrame(rank_rows),
    "gradient_templates": pd.DataFrame(gradient_rows),
    "twin_symmetry_templates": pd.DataFrame(sym_rows),
    "template_versions": pd.DataFrame(versions_rows),
    "regime_labels_hourly": regime_labels.to_frame("regime_id"),
}, index=False)


# ============================================================================
# 7. D1_benchmark_results.xlsx (placeholder + cooldown ablation per spec §11)
# ============================================================================
print("\n[7] D1_benchmark_results.xlsx (with cooldown_ablation)")
# Cooldown ablation: V1 (timer) vs v1.1 (state machine)
def v1_cooldown_estimate(qs, qr):
    n = len(qs); cd = np.zeros(n, dtype=bool); last = -10000
    for i in range(n):
        if (qs.iat[i] <= 2 or qr.iat[i] <= 2): last = i
        if i - last <= 48: cd[i] = True
    return cd

ablation_rows = []
for c in SCORED:
    qs = S["subs_v1"]["Q_step"][c]; qr = S["subs_v1"]["Q_regime"][c]
    cd_v1 = v1_cooldown_estimate(qs, qr).mean()
    cd_v11_refr = (state_logs[c]["state_name"] == "Refractory").mean()
    sus_v11 = (state_logs[c]["state_name"] == "SustainedAnomaly").mean()
    rec_v11 = (state_logs[c]["state_name"] == "RecoveryCandidate").mean()
    norm_v11 = (state_logs[c]["state_name"] == "Normal").mean()
    ablation_rows.append({
        "sensor_id": c,
        "v1_cooldown_pct (48h timer)": cd_v1 * 100,
        "v1.1_Refractory_pct": cd_v11_refr * 100,
        "v1.1_SustainedAnomaly_pct": sus_v11 * 100,
        "v1.1_RecoveryCandidate_pct": rec_v11 * 100,
        "v1.1_Normal_pct": norm_v11 * 100,
        "cooldown_savings (V1 - v1.1.Refr)": (cd_v1 - cd_v11_refr) * 100,
        "delta_D1": float(D1_v11[c].mean() - S["D1_v1_scored"][c].mean()),
    })
ablation_df = pd.DataFrame(ablation_rows)

# Per-detector "performance" (qualitative, no labels)
perf_rows = []
for det_name, m_id in [("hampel", "Q_spike"), ("adjacent_ks", "Q_step"),
                          ("pls_peer_only", "Q_drift"), ("freeze_composite", "Q_freeze"),
                          ("w1_two_tier_ks", "Q_regime")]:
    rates = [float((subs_v11[c][m_id] < 3).mean()) for c in SCORED]
    perf_rows.append({
        "detector": det_name, "subscore": m_id,
        "mean_low_score_rate": float(np.mean(rates)),
        "max_low_score_rate": float(np.max(rates)),
        "min_low_score_rate": float(np.min(rates)),
        "channel_count": len(rates),
    })
_save(OUT / "D1_benchmark_results.xlsx", {
    "cooldown_ablation_v1_vs_v11": ablation_df,
    "detector_performance_summary": pd.DataFrame(perf_rows),
    "note": pd.DataFrame([{
        "note": "v1.1 introduces 5-state machine which separates Refractory "
                "(short shock) from SustainedAnomaly (recoverable). V1's "
                "level-triggered 48h timer caused indefinite re-triggering.",
        "spec_doc": "Cooldown_机制修订版正式文本_无泵状态最终版.docx",
    }]),
}, index=False)


# ============================================================================
# 8. D1_multiscale_aggregates.xlsx
# ============================================================================
print("\n[8] D1_multiscale_aggregates.xlsx")
D1_h = D1_v11
D1_d = S["D1_d_v11"]
D1_w = S["D1_w_v11"]
# Monthly
D1_m = D1_h.resample("ME").mean()
# Gate (lower quantile) vs Report (mean) versions
D1_d_gate = D1_h.resample("1D").quantile(0.05)
D1_d_report = D1_h.resample("1D").mean()
D1_w_gate = D1_d.resample("7D").min()
D1_w_report = D1_h.resample("7D").mean()
_save(OUT / "D1_multiscale_aggregates.xlsx", {
    "D1_hourly_full": D1_h,
    "D1_daily_gate_q05": D1_d_gate,
    "D1_daily_report_mean": D1_d_report,
    "D1_weekly_gate_min": D1_w_gate,
    "D1_weekly_report_mean": D1_w_report,
    "D1_monthly_mean": D1_m,
})


# ============================================================================
# 9. D1_sensor_profile_summary.xlsx (enhanced version per spec §4.4)
# ============================================================================
print("\n[9] D1_sensor_profile_summary.xlsx (enhanced)")
profile_rows = []
benchmark_rows = []
for c in SCORED:
    s = D1_v11[c]
    # Dominant fault overall
    dom = S["dominant_v11"][c].value_counts(normalize=True)
    dom_top = dom.index[0] if len(dom) > 0 else "unknown"
    dom_top_pct = float(dom.iloc[0]) if len(dom) > 0 else 0
    # Worst month
    monthly = s.resample("ME").mean()
    worst_month = monthly.idxmin()
    # Benchmark windows = consecutive ≥24h with D1≥4
    bench_thr = 4.0; bench_min_h = 24
    above = (s >= bench_thr).values
    runs = []
    i = 0; n = len(above)
    while i < n:
        if not above[i]: i += 1; continue
        j = i
        while j < n and above[j]: j += 1
        if j - i >= bench_min_h:
            runs.append((s.index[i], s.index[j-1], j - i))
        i = j
    bench_count = len(runs)
    bench_total_h = sum(r[2] for r in runs)
    # Generate benchmark IDs
    bench_ids = [f"{c}_BW_{i:03d}" for i in range(bench_count)]
    # Profile row
    profile_rows.append({
        "sensor_id": c,
        "mean_D1": float(s.mean()),
        "median_D1": float(s.median()),
        "p05_D1": float(s.quantile(0.05)),
        "p25_D1": float(s.quantile(0.25)),
        "p75_D1": float(s.quantile(0.75)),
        "p95_D1": float(s.quantile(0.95)),
        "low_score_rate_lt3": float((s < 3).mean()),
        "low_score_rate_lt2": float((s < 2).mean()),
        "dominant_fault_type": dom_top,
        "dominant_fault_share": dom_top_pct,
        "month_of_worst_quality": worst_month.strftime("%Y-%m"),
        "worst_month_mean_D1": float(monthly.min()),
        "benchmark_window_count": bench_count,
        "benchmark_total_hours": bench_total_h,
        "benchmark_definition": "D1 >= 4.0 sustained >= 24h",
        "benchmark_ids": ",".join(bench_ids[:5]) + ("..." if len(bench_ids) > 5 else ""),
        "profile_version": "v1.1",
        "remarks": ("V1.1 main scoring uses 5-state cooldown — refractory + "
                     "sustained anomaly recognition"),
    })
    # Benchmark windows table
    for i, (start, end, dur) in enumerate(runs):
        benchmark_rows.append({
            "benchmark_id": bench_ids[i], "sensor_id": c,
            "start_time": start, "end_time": end, "duration_h": dur,
            "mean_D1_in_window": float(s.loc[start:end].mean()),
            "min_D1_in_window": float(s.loc[start:end].min()),
        })
_save(OUT / "D1_sensor_profile_summary.xlsx", {
    "sensor_profiles": pd.DataFrame(profile_rows),
    "benchmark_windows_detail": pd.DataFrame(benchmark_rows),
}, index=False)


# ============================================================================
# 10. D1_benchmark_library.xlsx
# ============================================================================
print("\n[10] D1_benchmark_library.xlsx")
# Library of high-quality windows with stats
lib_rows = []
df_h = S["df_h"]
for c in SCORED:
    s = D1_v11[c]
    above = (s >= 4.0).values
    i = 0; n = len(above); idx_run = 0
    while i < n:
        if not above[i]: i += 1; continue
        j = i
        while j < n and above[j]: j += 1
        if j - i >= 24:
            window_data = df_h[c].loc[s.index[i]:s.index[j-1]]
            lib_rows.append({
                "benchmark_id": f"{c}_BW_{idx_run:03d}",
                "sensor_id": c,
                "regime_id_at_start": int(S["regime_labels"].loc[s.index[i]])
                  if s.index[i] in S["regime_labels"].index else -1,
                "start": s.index[i], "end": s.index[j-1],
                "duration_h": j - i,
                "mean_value": float(window_data.mean()),
                "std_value": float(window_data.std()),
                "iqr_value": float(window_data.quantile(0.75) - window_data.quantile(0.25)),
                "min_d1": float(s.loc[s.index[i]:s.index[j-1]].min()),
                "mean_d1": float(s.loc[s.index[i]:s.index[j-1]].mean()),
            })
            idx_run += 1
        i = j
benchmark_lib_df = pd.DataFrame(lib_rows)
# Aggregate by regime
regime_summary_lib = (benchmark_lib_df.groupby("regime_id_at_start")
                       .agg(n_windows=("benchmark_id", "count"),
                             total_h=("duration_h", "sum"),
                             mean_d1=("mean_d1", "mean"))
                       .reset_index() if len(benchmark_lib_df) else pd.DataFrame())
_save(OUT / "D1_benchmark_library.xlsx", {
    "benchmark_windows": benchmark_lib_df,
    "regime_summary": regime_summary_lib,
}, index=False)


# ============================================================================
# 11. D1_case_study_exports.xlsx
# ============================================================================
print("\n[11] D1_case_study_exports.xlsx")
case_channels = ["DO_2_3", "DO_2_4", "ORP_1_3", "ORP_2_2"]
case_sheets = {}
for c in case_channels:
    if c not in SCORED: continue
    case_data = pd.DataFrame({
        "Q_spike": subs_v11[c]["Q_spike"],
        "Q_step": subs_v11[c]["Q_step"],
        "Q_drift": subs_v11[c]["Q_drift"],
        "Q_freeze": subs_v11[c]["Q_freeze"],
        "Q_regime": subs_v11[c]["Q_regime"],
        "D1_total": D1_v11[c],
        "state_name": state_logs[c]["state_name"],
        "event_id": state_logs[c]["event_id"],
        "alpha": state_logs[c]["alpha"],
        "drift_mask_reason": state_logs[c]["drift_mask_reason"],
    })
    case_sheets[c] = case_data
_save(OUT / "D1_case_study_exports.xlsx", case_sheets)


# ============================================================================
# 12. D1_audit_log.xlsx
# ============================================================================
print("\n[12] D1_audit_log.xlsx")
from datetime import datetime
audit = pd.DataFrame([
    {"run_id": "v11", "script_version": "1.1.0",
     "param_version": "v1.1",
     "data_version": "STRICT_V1_baseline",
     "regime_template_version": "v1.1",
     "mapping_param_version": "v1.1",
     "rules_yaml_version": "v1.1 (DO/ORP only, signal-only Veto-3, 5-state cooldown)",
     "state_machine_yaml_version": "v1.1",
     "generated_at": datetime.now().isoformat(),
     "n_scored_channels": len(SCORED),
     "n_support_channels": len(SUPPORT),
     "n_state_transitions": len(S["transitions_all"]),
     "n_pelt_changepoints": S["n_pelt_cps"],
     "elapsed_sec": float(S["elapsed_sec"]),
     "spec_compliance": ("Cooldown_机制修订版_无泵状态; "
                            "Veto-3_过程感知修订版_无泵状态; "
                            "QR_QIR_仅作为驱动变量纳入D1_无泵状态; "
                            "工程目录结构修订最终版"),
    },
])
# Module versions
modules = pd.DataFrame([
    {"module": "src/cooldown_state_machine.py", "version": "v1.1.0",
     "spec_ref": "Cooldown 修订 §四–§十二"},
    {"module": "src/local_baseline.py", "version": "v1.1.0",
     "spec_ref": "Cooldown 修订 §八"},
    {"module": "src/d1_aggregator.py", "version": "v1.1.0",
     "spec_ref": "Veto-3 修订 §三, §五"},
    {"module": "src/state_blackboard.py", "version": "v1.1.0",
     "spec_ref": "工程目录修订 §八"},
    {"module": "src/auxiliary_modules.py", "version": "v1.1.0",
     "spec_ref": "QR/QIR 修订 §七 (D5/D7 templates only)"},
    {"module": "configs/rules.yaml", "version": "v1.1.0",
     "spec_ref": "veto3_signal_only=true, scored_channels=DO/ORP only"},
    {"module": "configs/state_machine.yaml", "version": "v1.1.0",
     "spec_ref": "5-state machine + α-thaw"},
])
_save(OUT / "D1_audit_log.xlsx", {
    "run_manifest": audit,
    "module_versions": modules,
}, index=False)


# ============================================================================
# 13. D1_state_machine_audit.xlsx (NEW v1.1)
# ============================================================================
print("\n[13] D1_state_machine_audit.xlsx (NEW v1.1)")
# All transitions
trans_df = pd.DataFrame(S["transitions_all"])
# State coverage per channel
cov_rows = []
for c in SCORED:
    sl = state_logs[c]
    cov_rows.append({
        "sensor_id": c,
        "Normal_h":            int((sl["state_name"] == "Normal").sum()),
        "Refractory_h":        int((sl["state_name"] == "Refractory").sum()),
        "SustainedAnomaly_h":  int((sl["state_name"] == "SustainedAnomaly").sum()),
        "RecoveryCandidate_h": int((sl["state_name"] == "RecoveryCandidate").sum()),
        "Recovered_h":         int((sl["state_name"] == "Recovered").sum()),
        "n_local_baseline_versions": int(sl["local_baseline_version"].max()),
        "n_transitions": sum(1 for tr in S["transitions_all"] if tr["sensor_id"] == c),
    })
cov_df = pd.DataFrame(cov_rows)

# Local baseline records (where we have them)
baseline_records = []
for tr in S["transitions_all"]:
    if tr.get("to_state") == "SustainedAnomaly" and "baseline_center" in tr:
        baseline_records.append({
            "sensor_id": tr["sensor_id"], "ts": tr["ts"],
            "trigger": tr.get("trigger", ""),
            "baseline_center": tr["baseline_center"],
            "baseline_scale": tr["baseline_scale"],
            "init_window_start": tr["baseline_init_window"][0],
            "init_window_end": tr["baseline_init_window"][1],
        })
_save(OUT / "D1_state_machine_audit.xlsx", {
    "all_transitions": trans_df,
    "state_coverage_per_channel": cov_df,
    "local_baseline_records": pd.DataFrame(baseline_records),
}, index=False)


# ============================================================================
# 14. D1_pelt_changepoints.xlsx (NEW v1.1)
# ============================================================================
print("\n[14] D1_pelt_changepoints.xlsx (NEW v1.1)")
all_cps = []
for c, evts in S["pelt_results"].items():
    for ev in evts:
        all_cps.append({"sensor_id": c, **ev})
cp_df = pd.DataFrame(all_cps)
cp_summary = (cp_df.groupby("sensor_id")
                .agg(n_cps=("timestamp", "count"),
                      median_magnitude=("magnitude", "median"),
                      max_magnitude=("magnitude", "max"))
                .reset_index() if len(cp_df) else pd.DataFrame())
_save(OUT / "D1_pelt_changepoints.xlsx", {
    "all_changepoints": cp_df,
    "summary_per_channel": cp_summary,
}, index=False)


# ============================================================================
# 15. D1_v11_vs_strictV1_compare.xlsx
# ============================================================================
print("\n[15] D1_v11_vs_strictV1_compare.xlsx")
delta_df = S["delta_df"]
# Hourly diff
hourly_diff = D1_v11 - S["D1_v1_scored"]
# Detailed per-channel comparison
detail_rows = []
for c in SCORED:
    detail_rows.append({
        "sensor_id": c,
        "D1_strict_v1": float(S["D1_v1_scored"][c].mean()),
        "D1_v11": float(D1_v11[c].mean()),
        "delta_D1": float(D1_v11[c].mean() - S["D1_v1_scored"][c].mean()),
        "Q_drift_v1_mean": float(S["subs_v1"]["Q_drift"][c].mean()),
        "Q_drift_eff_v11_mean": float(S["Q_drift_eff_dict"][c].mean()),
        "Q_drift_change": float(S["Q_drift_eff_dict"][c].mean()
                                  - S["subs_v1"]["Q_drift"][c].mean()),
        "low_lt3_strict_v1": float((S["D1_v1_scored"][c] < 3).mean()),
        "low_lt3_v11": float((D1_v11[c] < 3).mean()),
    })
_save(OUT / "D1_v11_vs_strictV1_compare.xlsx", {
    "per_channel_summary": delta_df,
    "detailed_comparison": pd.DataFrame(detail_rows),
    "hourly_delta": hourly_diff.describe(),
}, index=False)


# ============================================================================
# 16. D1_qr_qir_side_outputs.xlsx (NEW v1.1, per QR/QIR 修订 §七)
# ============================================================================
print("\n[16] D1_qr_qir_side_outputs.xlsx (NEW v1.1)")
ann = S["qr_qir_annotations"]
# Daily summary
daily_qr_jumps = (ann["qr_jump_annotation"] != "").resample("1D").sum()
daily_qir_jumps = (ann["qir_jump_annotation"] != "").resample("1D").sum()
daily_summary = pd.DataFrame({
    "qr_jumps_per_day": daily_qr_jumps,
    "qir_jumps_per_day": daily_qir_jumps,
})
_save(OUT / "D1_qr_qir_side_outputs.xlsx", {
    "hourly_annotations": ann,
    "daily_summary": daily_summary,
    "note": pd.DataFrame([{
        "note": "Per QR/QIR 仅作为驱动变量纳入D1的修订正式文本_无泵状态最终版.docx, "
                "QR/QIR are NOT scored in D1 main link. These annotations are "
                "for offline case-study, D5 modelling, and D7 template only.",
        "spec_section": "§七 — QR/QIR 在当前项目中的正式保留用途",
    }]),
})


print(f"\n{'='*70}\nAll 16 Excel deliverables generated.\nLocation: {OUT}\n{'='*70}")
import os
files = sorted(OUT.glob("*.xlsx"))
total_kb = sum(f.stat().st_size for f in files) // 1024
print(f"Total: {len(files)} files, {total_kb} KB")
