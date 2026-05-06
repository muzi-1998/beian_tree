"""src/outputs/excel_exporter.py
Generate the 8 minimum-delivery + 4 extended Excel files per output spec §V.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd


def _writer(path):
    return pd.ExcelWriter(path, engine="openpyxl")


# ─────────────────────────────────────────────────────────────────────────
# 1. D1_main_scores_min.xlsx — main scoring layer
# ─────────────────────────────────────────────────────────────────────────
def export_main_scores(R, out_path: Path):
    """Hourly Q_*, D1_total, grade, usable_tag — one sheet per channel +
    summary sheet."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grading_thr = R["cfg"].rules.grading
    bins = [-0.001, grading_thr["D"], grading_thr["C"],
            grading_thr["B"], grading_thr["A"], 5.001]
    labels = ["F", "D", "C", "B", "A"]

    with _writer(out_path) as w:
        # Summary sheet
        d1_h = R["D1_h"].copy()
        summary_rows = []
        for c in d1_h.columns:
            grades = pd.cut(d1_h[c], bins=bins, labels=labels, include_lowest=True)
            summary_rows.append({
                "sensor_id": c,
                "mean_D1_total": float(d1_h[c].mean()),
                "median_D1_total": float(d1_h[c].median()),
                "p05_D1": float(d1_h[c].quantile(0.05)),
                "low_score_rate_lt3": float((d1_h[c] < 3).mean()),
                "low_score_rate_lt2": float((d1_h[c] < 2).mean()),
                "n_grade_A": int((grades == "A").sum()),
                "n_grade_B": int((grades == "B").sum()),
                "n_grade_C": int((grades == "C").sum()),
                "n_grade_D": int((grades == "D").sum()),
                "n_grade_F": int((grades == "F").sum()),
            })
        pd.DataFrame(summary_rows).to_excel(w, sheet_name="summary", index=False)

        # Combined hourly D1 table (one sheet for all sensors compact)
        d1_h.index.name = "ts"
        d1_h.to_excel(w, sheet_name="D1_total_hourly")

        # Q-component sheet (each Q-type as a sheet, channels as columns)
        for q in ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]:
            df = pd.DataFrame({c: R["subs"][c][q] for c in d1_h.columns})
            df.index.name = "ts"
            df.to_excel(w, sheet_name=q)

        # Grade & usable_tag (usable = D1 ≥ 3)
        gr = pd.DataFrame({c: pd.cut(d1_h[c], bins=bins, labels=labels,
                                     include_lowest=True).astype(str)
                           for c in d1_h.columns})
        gr.index.name = "ts"
        gr.to_excel(w, sheet_name="grade_hourly")

        usable = (d1_h >= 3).astype(int)
        usable.index.name = "ts"
        usable.to_excel(w, sheet_name="usable_tag_hourly")

    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 2. D1_event_windows.xlsx — event layer
# ─────────────────────────────────────────────────────────────────────────
def export_events(R, out_path: Path, top_n_per_sensor: int = 10):
    """Anomaly windows with start/end/duration/dominant fault."""
    events = R["events"].copy()
    if len(events) == 0:
        events = pd.DataFrame(columns=["sensor_id", "start", "end",
                                        "duration_h", "min_d1", "mean_d1"])

    # Attribute dominant fault per event window
    dom = R["dominant"]
    rows = []
    for _, ev in events.iterrows():
        sub = dom[(dom["sensor_id"] == ev["sensor_id"]) &
                  (dom["ts"] >= ev["start"]) & (dom["ts"] <= ev["end"])]
        if len(sub) > 0:
            ev_dom = sub["dominant_fault"].mode().iloc[0]
            ev_min_sub = float(sub["min_subscore"].min())
        else:
            ev_dom = "n/a"; ev_min_sub = np.nan
        rows.append({**ev.to_dict(),
                     "dominant_fault": ev_dom,
                     "min_subscore": ev_min_sub})
    df = pd.DataFrame(rows).sort_values(
        ["sensor_id", "duration_h"], ascending=[True, False])

    # Top events per sensor (for case study selection)
    top_rows = []
    for c in R["D1_h"].columns:
        sub = df[df["sensor_id"] == c].head(top_n_per_sensor)
        top_rows.append(sub)
    top = pd.concat(top_rows, ignore_index=True) if top_rows else df

    with _writer(out_path) as w:
        df.to_excel(w, sheet_name="all_events", index=False)
        top.to_excel(w, sheet_name="top_per_sensor", index=False)

        # Per-fault aggregate count
        if len(df) > 0:
            agg = df.groupby(["sensor_id", "dominant_fault"]).agg(
                n_events=("duration_h", "count"),
                total_h=("duration_h", "sum"),
                mean_min_d1=("min_d1", "mean"),
            ).reset_index()
            agg.to_excel(w, sheet_name="fault_summary", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 3. D1_detector_outputs_raw.xlsx — evidence layer (raw detector scores)
# ─────────────────────────────────────────────────────────────────────────
def export_detector_raw(R, out_path: Path):
    """Detector raw outputs: Hampel z, KS, PLS-residz, freeze-components, W1-norm."""
    with _writer(out_path) as w:
        # Hampel robust z (subsample to hourly max for size)
        spike_z = pd.DataFrame({
            c: R["spike_results"][c].raw_score.resample("1h").max()
            for c in R["D1_h"].columns
        })
        spike_z.index.name = "ts"
        spike_z.to_excel(w, sheet_name="hampel_z_hourly_max")

        # KS statistic (already hourly)
        ks_df = pd.DataFrame({
            c: R["step_results"][c].raw_score for c in R["D1_h"].columns
        })
        ks_df.index.name = "ts"
        ks_df.to_excel(w, sheet_name="ks_statistic_hourly")

        # PLS residual z
        pls_df = pd.DataFrame({
            c: R["drift_results"][c].raw_score
            for c in R["D1_h"].columns if c in R["drift_results"]
        })
        pls_df.index.name = "ts"
        pls_df.to_excel(w, sheet_name="pls_residual_z_hourly")

        # Freeze components (RLE / rel_var / unique_ratio) at hourly max
        for comp_name in ["rle_run_min", "rel_var", "unique_ratio"]:
            df = pd.DataFrame({
                c: R["freeze_results"][c].metadata["components"][comp_name].resample("1h").max()
                for c in R["D1_h"].columns
            })
            df.index.name = "ts"
            df.to_excel(w, sheet_name=f"freeze_{comp_name}")

        # W1 normalised
        w1_df = pd.DataFrame({
            c: R["regime_results"][c].raw_score for c in R["D1_h"].columns
        })
        w1_df.index.name = "ts"
        w1_df.to_excel(w, sheet_name="w1_normalised_hourly")

        # Spike rate 6h (input to mapper)
        R["spike_rate_6h"].to_excel(w, sheet_name="spike_rate_6h_input")

    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 4. D1_fault_probability_matrix.xlsx — evidence fusion + conflict
# ─────────────────────────────────────────────────────────────────────────
def export_fault_probability_matrix(R, out_path: Path):
    """Per (channel, hour): probabilities of each fault, dominant, conflict."""
    rows = []
    for c in R["D1_h"].columns:
        s = R["subs"][c]
        # Map sub-score to fault probability:  P_fault = (5 - Q) / 4
        df = pd.DataFrame({
            "P_spike":  (5 - s["Q_spike"])  / 4,
            "P_step":   (5 - s["Q_step"])   / 4,
            "P_drift":  (5 - s["Q_drift"])  / 4,
            "P_freeze": (5 - s["Q_freeze"]) / 4,
            "P_regime": (5 - s["Q_regime"]) / 4,
        })
        weights = R["cfg"].rules.aggregation.weights
        wsum = sum(weights.values())
        df["P_fused"] = (
            df["P_spike"]  * weights["Q_spike"]  +
            df["P_step"]   * weights["Q_step"]   +
            df["P_drift"]  * weights["Q_drift"]  +
            df["P_freeze"] * weights["Q_freeze"] +
            df["P_regime"] * weights["Q_regime"]
        ) / wsum
        df["dominant_fault"] = df[["P_spike","P_step","P_drift","P_freeze","P_regime"]].idxmax(axis=1)
        df["conflict_degree"] = df[["P_spike","P_step","P_drift","P_freeze","P_regime"]].var(axis=1)
        df["sensor_id"] = c
        df["ts"] = df.index
        df = df.reset_index(drop=True)
        rows.append(df)
    full = pd.concat(rows, ignore_index=True)

    # Conflict log: events with conflict > 0.06
    conflict_log = full[full["conflict_degree"] > 0.06].copy()
    conflict_log["conflict_source"] = "high_variance_among_5_detectors"
    conflict_log["fusion_rule"] = "weighted_average"
    conflict_log["resolution_status"] = "flagged_for_review"

    with _writer(out_path) as w:
        # Sample to keep file small: every 12h
        sample = full[full["ts"].dt.hour % 12 == 0]
        if len(sample) == 0:
            sample = full.head(50000)
        sample.to_excel(w, sheet_name="fault_probabilities_12h", index=False)
        # Per-channel summary
        agg = full.groupby("sensor_id").agg(
            mean_P_spike=("P_spike", "mean"),
            mean_P_step=("P_step", "mean"),
            mean_P_drift=("P_drift", "mean"),
            mean_P_freeze=("P_freeze", "mean"),
            mean_P_regime=("P_regime", "mean"),
            mean_conflict=("conflict_degree", "mean"),
            max_conflict=("conflict_degree", "max"),
        ).reset_index()
        agg.to_excel(w, sheet_name="per_channel_summary", index=False)
        if len(conflict_log) == 0:
            # Write a placeholder
            pd.DataFrame([{"note": "No conflicts above threshold 0.06"}]).to_excel(
                w, sheet_name="conflict_log_top2k", index=False)
        else:
            conflict_log.head(2000).to_excel(w, sheet_name="conflict_log_top2k", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 5. D1_mapping_params.xlsx — parameter layer
# ─────────────────────────────────────────────────────────────────────────
def export_mapping_params(R, out_path: Path):
    from mapping import export_mapping_params as _exp
    df = _exp(R["cfg"].mapping)
    with _writer(out_path) as w:
        df.to_excel(w, sheet_name="mapping_master", index=False)
        # Versions (single row for now)
        ver = pd.DataFrame([{
            "version": "v1.0", "effective_date": datetime.now().date(),
            "n_subscores": 7, "calibration_source": "expert + report priors",
        }])
        ver.to_excel(w, sheet_name="mapping_versions", index=False)
        # Examples — sample of mapping curves
        x_vals = np.concatenate([np.linspace(0, 0.2, 21),
                                 np.linspace(0.2, 1.0, 21),
                                 np.linspace(1.0, 5.0, 21)])
        examples = []
        for c in [(R["cfg"].mapping.spike, "Q_spike"),
                  (R["cfg"].mapping.step,  "Q_step"),
                  (R["cfg"].mapping.drift, "Q_drift"),
                  (R["cfg"].mapping.regime, "Q_regime")]:
            from mapping import apply_mapping
            ser = apply_mapping(pd.Series(x_vals), c[0])
            examples.append(pd.DataFrame({
                "subscore": c[1], "x": x_vals, "Q": ser.values
            }))
        pd.concat(examples, ignore_index=True).to_excel(w, sheet_name="mapping_examples", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 6. D1_regime_templates.xlsx — template layer (simple v1: gradient + symmetry)
# ─────────────────────────────────────────────────────────────────────────
def export_regime_templates(R, out_path: Path):
    """Pool-level gradient & symmetry templates derived from 'high-quality' periods."""
    df_h = R["df_h"]
    d1_h = R["D1_h"]
    # Identify global high-quality periods: hours where median D1 across all sensors > 4
    median_d1 = d1_h.median(axis=1)
    bench_hours = median_d1[median_d1 > 4].index
    # If no such hours, fall back to top-25% periods
    if len(bench_hours) < 100:
        thr = median_d1.quantile(0.75)
        bench_hours = median_d1[median_d1 >= thr].index

    bench_df = df_h.loc[bench_hours]

    # Cluster centers (single regime for v1; full Regime clustering deferred)
    cluster_center = bench_df.mean()
    cluster_std    = bench_df.std()
    cluster_iqr    = bench_df.quantile(0.75) - bench_df.quantile(0.25)

    # Rank template (DO 8-channel argsort by mean)
    do_cols = [c for c in df_h.columns if c.startswith("DO_")]
    rank_template = bench_df[do_cols].mean().rank(ascending=False).astype(int)

    # Gradient template per pool (DO_p_1 → DO_p_4 mean)
    gradient_rows = []
    for p in (1, 2):
        for i in range(1, 5):
            cn = f"DO_{p}_{i}"
            if cn in df_h.columns:
                gradient_rows.append({
                    "pool": p, "segment": i, "channel": cn,
                    "mean_DO": float(bench_df[cn].mean()),
                    "p25":     float(bench_df[cn].quantile(0.25)),
                    "p75":     float(bench_df[cn].quantile(0.75)),
                })
    gradient_template = pd.DataFrame(gradient_rows)

    # Twin symmetry: corr between pool-1 and pool-2 same-segment pairs
    pairs = [(f"DO_{1}_{i}", f"DO_{2}_{i}") for i in range(1, 5)]
    pairs += [(f"ORP_{1}_{i}", f"ORP_{2}_{i}") for i in range(1, 4)]
    pairs += [("QR_1", "QR_2"), ("QIR_1", "QIR_2")]
    sym_rows = []
    for a, b in pairs:
        if a in bench_df.columns and b in bench_df.columns:
            corr = float(bench_df[a].corr(bench_df[b]))
            mean_diff = float((bench_df[a] - bench_df[b]).abs().mean())
            sym_rows.append({
                "pair_a": a, "pair_b": b,
                "corr": corr, "mean_abs_diff": mean_diff,
                "ratio_a_to_b": float(bench_df[a].mean() / (bench_df[b].mean() + 1e-9)),
            })
    sym_template = pd.DataFrame(sym_rows)

    with _writer(out_path) as w:
        pd.DataFrame({"channel": cluster_center.index,
                      "cluster_center": cluster_center.values,
                      "std": cluster_std.values,
                      "iqr": cluster_iqr.values}).to_excel(
            w, sheet_name="cluster_centers", index=False)
        rank_template.reset_index().rename(
            columns={"index": "channel", 0: "expected_rank"}).to_excel(
            w, sheet_name="rank_templates", index=False)
        gradient_template.to_excel(w, sheet_name="gradient_templates", index=False)
        sym_template.to_excel(w, sheet_name="twin_symmetry_templates", index=False)
        ver = pd.DataFrame([{
            "regime_id": "C0_baseline_high_quality",
            "cluster_method": "single_cluster_v1",
            "feature_set": "all_18_channels_hourly_means",
            "sample_size": int(len(bench_df)),
            "time_coverage": f"{bench_hours[0]} → {bench_hours[-1]}",
            "valid_from": str(bench_hours[0].date()),
            "valid_to":   str(bench_hours[-1].date()),
            "version": "v1.0",
            "notes": "single-regime baseline; multi-regime clustering deferred to v1.1",
        }])
        ver.to_excel(w, sheet_name="template_versions", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 7. D1_benchmark_results.xlsx — validation layer
# ─────────────────────────────────────────────────────────────────────────
def export_benchmark_results(R, out_path: Path):
    """Use existing report numbers + DQR-ROC for our pipeline against known issues."""
    from sklearn.metrics import roc_auc_score
    rows_method = [
        {"method": "PCA-SPE (event-level)", "F1": 0.311, "Recall": 0.187,
         "Precision": 0.923, "FAR": 0.023, "AUC": 0.643, "MDD_h": 223,
         "source": "Supplementary Benchmark Report 2026"},
        {"method": "ICA+KDE (event-level)", "F1": 0.353, "Recall": 0.217,
         "Precision": 0.951, "FAR": 0.017, "AUC": 0.743, "MDD_h": 45,
         "source": "Supplementary Benchmark Report 2026"},
        {"method": "PLS (event-level)", "F1": 0.486, "Recall": 0.323,
         "Precision": 0.980, "FAR": 0.010, "AUC": 0.809, "MDD_h": 24,
         "source": "Supplementary Benchmark Report 2026"},
        {"method": "KS(48h) (event-level)", "F1": 0.779, "Recall": 0.793,
         "Precision": 0.765, "FAR": 0.365, "AUC": 0.825, "MDD_h": 19,
         "source": "Supplementary Benchmark Report 2026"},
    ]

    # DQR-ROC: for each known-bad sensor, label the documented anomaly window;
    # treat low D1_total as "anomaly score" — compute AUC.
    known_bad = {
        "ORP_1_3": "always_drift",  # entire monitoring period
        "QR_2":    "always_zero_negative",
        "ORP_2_2": "always_low_var",
        "DO_2_3":  "frequent_problem",
    }
    # We simulate per-sensor binary label = 1 if sensor is in known-bad,
    # and treat each hour as an observation. AUC of D1 against this.
    d1_h = R["D1_h"]
    n_h = len(d1_h)
    rows_dqr_roc = []
    for c in d1_h.columns:
        y = 1 if c in known_bad else 0
        # AUC needs positives and negatives → compute one global AUC across all sensors
        pass

    # Cross-sensor AUC: anomaly score = -D1 (lower D1 = more anomalous)
    y_true = np.array([1 if c in known_bad else 0 for c in d1_h.columns]
                      * n_h).reshape(n_h, len(d1_h.columns))
    score = -d1_h.values
    # Flatten valid entries
    ys = y_true.ravel(); ss = score.ravel()
    mask = ~np.isnan(ss)
    auc_global = float(roc_auc_score(ys[mask], ss[mask]))

    rows_method.append({
        "method": "D1_total (this work)",
        "F1": np.nan, "Recall": np.nan, "Precision": np.nan, "FAR": np.nan,
        "AUC": auc_global, "MDD_h": np.nan,
        "source": f"Cross-sensor AUC against known-bad list ({len(known_bad)} bad)"
    })

    # Per-sensor mean D1 ranked vs. known-bad
    rank_rows = []
    for c in d1_h.columns:
        rank_rows.append({
            "sensor_id": c,
            "mean_D1":  float(d1_h[c].mean()),
            "low_lt3_rate": float((d1_h[c] < 3).mean()),
            "low_lt2_rate": float((d1_h[c] < 2).mean()),
            "is_known_bad": int(c in known_bad),
            "known_issue": known_bad.get(c, ""),
        })
    rank_df = pd.DataFrame(rank_rows).sort_values("mean_D1")

    with _writer(out_path) as w:
        pd.DataFrame(rows_method).to_excel(w, sheet_name="method_comparison", index=False)
        rank_df.to_excel(w, sheet_name="dqr_ranking_vs_known_bad", index=False)
        pd.DataFrame([{
            "test_type": "Cross-sensor AUC (low-D1 ↔ known-bad)",
            "AUC": auc_global,
            "n_sensors": len(d1_h.columns),
            "n_known_bad": len(known_bad),
            "n_hours": n_h,
            "interpretation": "AUC > 0.7 means D1_total ranks known-bad sensors below known-good consistently",
        }]).to_excel(w, sheet_name="benchmark_summary", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# 8. D1_sensor_profile_summary.xlsx — profile layer (enhanced)
# ─────────────────────────────────────────────────────────────────────────
def export_profile_summary(R, out_path: Path):
    profile = R["profile"]
    with _writer(out_path) as w:
        profile.to_excel(w, sheet_name="profile_main", index=False)
        # Worst by mean D1 + worst by low<2 rate
        d1_h = R["D1_h"]
        worst_mean = d1_h.mean().sort_values().head(5).reset_index()
        worst_mean.columns = ["sensor_id", "mean_D1"]
        worst_low2 = (d1_h < 2).mean().sort_values(ascending=False).head(5).reset_index()
        worst_low2.columns = ["sensor_id", "low_score_rate_lt2"]
        worst_mean.to_excel(w, sheet_name="worst_by_mean_D1", index=False)
        worst_low2.to_excel(w, sheet_name="worst_by_low2_rate", index=False)

        # Monthly breakdown
        d1_d = R["D1_d"]
        monthly = d1_d.resample("MS").mean().T.round(3)
        monthly.index.name = "sensor_id"
        monthly.to_excel(w, sheet_name="monthly_mean_D1")
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# Extension files
# ─────────────────────────────────────────────────────────────────────────
def export_multiscale_aggregates(R, out_path: Path):
    with _writer(out_path) as w:
        R["D1_h"].to_excel(w, sheet_name="D1_hourly")
        R["D1_d"].to_excel(w, sheet_name="D1_daily_q05")
        R["D1_w"].to_excel(w, sheet_name="D1_weekly_min")
        # Daily mean (gate vs report)
        d1_d_mean = R["D1_h"].resample("1D").mean()
        d1_d_mean.to_excel(w, sheet_name="D1_daily_mean_for_report")
    return out_path


def export_case_study(R, out_path: Path,
                      case_sensors: list = ("DO_2_3", "ORP_1_3", "ORP_2_2", "QR_2")):
    with _writer(out_path) as w:
        for c in case_sensors:
            if c not in R["D1_h"].columns: continue
            s = R["subs"][c]
            df = pd.DataFrame({
                "Q_spike":  s["Q_spike"],
                "Q_step":   s["Q_step"],
                "Q_drift":  s["Q_drift"],
                "Q_freeze": s["Q_freeze"],
                "Q_regime": s["Q_regime"],
                "D1_total": R["D1_h"][c],
            })
            df.index.name = "ts"
            df.to_excel(w, sheet_name=c[:31])  # Excel sheet name limit
    return out_path


def export_audit_log(R, cfg_dict, out_path: Path):
    cfg_str = json.dumps(cfg_dict, sort_keys=True, default=str)
    cfg_hash = hashlib.md5(cfg_str.encode()).hexdigest()[:12]
    log = pd.DataFrame([{
        "run_id": datetime.now().strftime("%Y%m%dT%H%M%S"),
        "config_hash": cfg_hash,
        "n_channels": len(R["D1_h"].columns),
        "data_span_start": str(R["df_min"].index[0]),
        "data_span_end": str(R["df_min"].index[-1]),
        "n_min_rows": len(R["df_min"]),
        "n_hourly_rows": len(R["D1_h"]),
        "weights_Q_spike": R["cfg"].rules.aggregation.weights["Q_spike"],
        "weights_Q_step":  R["cfg"].rules.aggregation.weights["Q_step"],
        "weights_Q_drift": R["cfg"].rules.aggregation.weights["Q_drift"],
        "weights_Q_freeze": R["cfg"].rules.aggregation.weights["Q_freeze"],
        "weights_Q_regime": R["cfg"].rules.aggregation.weights["Q_regime"],
        "lambda_blend": R["cfg"].rules.aggregation.lambda_blend,
        "spec_version": "v2_2026-05",
        "code_version": "d1_fsd_v1.0",
    }])
    with _writer(out_path) as w:
        log.to_excel(w, sheet_name="run_manifest", index=False)
    return out_path


# ─────────────────────────────────────────────────────────────────────────
# Master export
# ─────────────────────────────────────────────────────────────────────────
def export_all(R, output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    print("    Exporting D1_main_scores_min.xlsx ...")
    paths["main"]    = export_main_scores(R, out/"D1_main_scores_min.xlsx")
    print("    Exporting D1_event_windows.xlsx ...")
    paths["events"]  = export_events(R, out/"D1_event_windows.xlsx")
    print("    Exporting D1_detector_outputs_raw.xlsx ...")
    paths["raw"]     = export_detector_raw(R, out/"D1_detector_outputs_raw.xlsx")
    print("    Exporting D1_fault_probability_matrix.xlsx ...")
    paths["fpm"]     = export_fault_probability_matrix(R, out/"D1_fault_probability_matrix.xlsx")
    print("    Exporting D1_mapping_params.xlsx ...")
    paths["mp"]      = export_mapping_params(R, out/"D1_mapping_params.xlsx")
    print("    Exporting D1_regime_templates.xlsx ...")
    paths["rt"]      = export_regime_templates(R, out/"D1_regime_templates.xlsx")
    print("    Exporting D1_benchmark_results.xlsx ...")
    paths["bm"]      = export_benchmark_results(R, out/"D1_benchmark_results.xlsx")
    print("    Exporting D1_sensor_profile_summary.xlsx ...")
    paths["profile"] = export_profile_summary(R, out/"D1_sensor_profile_summary.xlsx")
    print("    Exporting D1_multiscale_aggregates.xlsx ...")
    paths["multi"]   = export_multiscale_aggregates(R, out/"D1_multiscale_aggregates.xlsx")
    print("    Exporting D1_case_study_exports.xlsx ...")
    paths["case"]    = export_case_study(R, out/"D1_case_study_exports.xlsx")
    print("    Exporting D1_audit_log.xlsx ...")
    paths["audit"]   = export_audit_log(R, R["cfg"].model_dump(), out/"D1_audit_log.xlsx")
    return paths
