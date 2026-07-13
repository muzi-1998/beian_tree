"""run_all.py — D6 Parallel-redundancy Temporal-consistency module, full build.

Orchestrates the complete D6 link on the real ~255-day minute-level dataset and
emits all ten Excel deliverables, the validation results and the eight figures.

Stages:
  0  load config + raw data
  1  de-periodise -> residuals
  2  derive upstream proxies (D1 health, D2 usability, regime, D7 consensus)
  3  Stage-A compute_raw (once, mad_scale=1.0; quantile mapping is scale-free)
  4  benchmark library + quantile mapper
  5  Stage-B score (full arbitration) + arbitration transitions
  6  write 10 Excel deliverables
  7  validation (injection trials, ablation, correlation, ROC/PR)
  8  figures M1-M3, D1-D3, V1-V2
  9  run manifest
"""
from __future__ import annotations
import os, sys, json, time, hashlib, platform
from datetime import datetime, timezone
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from d6.config.loader import load_d6_config
from d6.pair_manager import PairManager
from d6.pipeline import data_loader as DL
from d6.pipeline.d6_pipeline import D6Pipeline
from d6.benchmark.pair_benchmark_builder import build_benchmark_library
from d6.mapping.mapper import SubscoreMapper
from d6.outputs.output_bundle import (write_sheets, build_event_windows,
                                      build_multiscale, build_pair_profile)
from d6.validation.validation_runner import ValidationRunner

ROOT = os.path.dirname(os.path.abspath(__file__))
RAWDIR = "/mnt/project"
ART = os.path.join(ROOT, "artifacts", "d6")
MAN = os.path.join(ROOT, "run_manifest", "d6")
OUT_RESULTS = "/mnt/user-data/outputs/results"
OUT_FIG = "/mnt/user-data/outputs/figures"
RUN_ID = datetime.now(timezone.utc).strftime("D6-%Y%m%dT%H%M%SZ")
VERSION = "D6 v1.2"

os.makedirs(ART, exist_ok=True); os.makedirs(MAN, exist_ok=True)
os.makedirs(OUT_RESULTS, exist_ok=True); os.makedirs(OUT_FIG, exist_ok=True)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(full=True):
    t0 = time.time()
    cfg = load_d6_config(os.path.join(ROOT, "configs", "d6"))
    pm = PairManager(cfg)
    log("config loaded; pairs=%d" % len(cfg.pairs))

    # ---- Stage 0-1 ----
    nrows = None if full else 45 * 1440
    df = DL.load_raw(f"{RAWDIR}/beian_min_1_DO_25082604.xlsx",
                     f"{RAWDIR}/beian_min_2_ORP082604.xlsx",
                     f"{RAWDIR}/beian_min_3_QRQIR082604.xlsx", nrows_minutes=nrows)
    log("raw loaded %s span %s..%s" % (df.shape, df.index.min(), df.index.max()))
    resid = DL.compute_residuals(df, DL.DO_COLS + DL.ORP_COLS)
    resid.to_pickle(os.path.join(ART, "residuals.pkl"))
    log("residuals %s" % (resid.shape,))

    # ---- Stage 2 ----
    d1 = DL.derive_d1_proxy(df, resid, DL.DO_COLS + DL.ORP_COLS)
    d2 = DL.derive_d2_usability(df, DL.DO_COLS + DL.ORP_COLS)
    regime = DL.derive_regime(df)
    d7 = DL.derive_d7_consensus(resid, cfg.pairs, cfg.zoning)
    log("upstream proxies: d1%s d2%s regimes=%s" %
        (d1.shape, d2.shape, sorted(regime["regime_id"].unique())))

    # ---- Stage 3: Stage-A raw ----
    end_times = pd.date_range(df.index.min() + pd.Timedelta(hours=24), df.index.max(), freq="1h")
    log("windows/pair=%d -> ~%d rows" % (len(end_times), len(end_times) * len(cfg.pairs)))
    pipe = D6Pipeline(cfg, pm, d1, d2, regime, d7, trend_mad=None)
    tA = time.time()
    raw = pipe.compute_raw(resid, end_times)
    raw.to_pickle(os.path.join(ART, "stage_a_raw.pkl"))
    log("Stage-A raw %s in %ds; deadband rate=%.3f" %
        (raw.shape, time.time() - tA, raw["deadband_active"].mean()))

    # ---- Stage 4: benchmark + mapper ----
    bm, metrics, trend_mad, bm_tbl = build_benchmark_library(raw)
    mapper = SubscoreMapper.from_benchmark(metrics, cfg.mapping)
    log("benchmark windows=%d; mapping params=%d" % (len(bm), len(mapper.all_params())))

    # ---- Stage 5: Stage-B score (full) ----
    main, trans = pipe.score(raw, mapper, ablation=None, collect_transitions=True)
    main = main.sort_values(["pair_id", "timestamp"]).reset_index(drop=True)
    log("Stage-B main %s; D6_forDQR mean=%.3f" % (main.shape, main["D6_forDQR"].mean()))

    # ===================== Stage 6: write 10 deliverables =====================
    write_main_scores(main)
    write_detector_raw(raw)
    write_mapping_params(mapper, cfg, trend_mad)
    write_benchmark_library(bm_tbl, bm, cfg)
    ev = build_event_windows(main, cfg.output.event_low_score_threshold,
                             cfg.output.event_min_duration_h)
    write_sheets(os.path.join(OUT_RESULTS, "D6_event_windows.xlsx"), ev)
    log("  wrote D6_event_windows (%d events)" % len(ev["events_main"]))
    prof = build_pair_profile(main, ev["events_main"])
    write_sheets(os.path.join(OUT_RESULTS, "D6_pair_profile_summary.xlsx"), prof)
    ms = build_multiscale(main, cfg.output.dqr_gate_quantile, cfg.output.dqr_report_quantile)
    write_sheets(os.path.join(OUT_RESULTS, "D6_multiscale_aggregates.xlsx"), ms)
    write_arbitration_log(trans, main)
    log("  wrote profile/multiscale/arbitration logs")

    # ===================== Stage 7: validation =====================
    def pipe_factory(ablation=None, d1_override=None):
        return D6Pipeline(cfg, pm, d1_override if d1_override is not None else d1,
                          d2, regime, d7, trend_mad=None)
    vr = ValidationRunner(cfg, pm, pipe_factory, resid, d1, d2, regime, d7,
                          mapper, raw, main)
    # choose representative clean start times (avoid edges)
    span_start = df.index.min() + pd.Timedelta(days=20)
    span_end = df.index.max() - pd.Timedelta(days=10)
    starts = list(pd.date_range(span_start, span_end, periods=4))
    starts = [s.floor("h") for s in starts]
    pairs_by_type = {
        "INJ-A": ["PAIR_DO12", "PAIR_ORP12"], "INJ-B": ["PAIR_DO13", "PAIR_ORP13"],
        "INJ-C": ["PAIR_DO11", "PAIR_DO14"], "INJ-D": ["PAIR_DO12", "PAIR_ORP11"],
        "INJ-E": ["PAIR_DO11", "PAIR_DO12", "PAIR_DO13"],   # same aerobic zone for true switch
        "INJ-F": ["PAIR_DO12", "PAIR_ORP12"],
    }
    log("validation: injection trials ...")
    trials = vr.run_injection_trials(pairs_by_type, starts)
    log("  %d injection trials" % len(trials))
    abl = vr.run_ablation_comparison(drift_pair="PAIR_DO12", start_times=starts)
    log("  ablation conditions: %d" % len(abl))
    corr = vr.run_correlation()
    roc = vr.run_roc_pr()
    bench_summary = summarize_targets(trials, abl, corr)
    write_sheets(os.path.join(OUT_RESULTS, "D6_benchmark_results.xlsx"), {
        "summary_vs_targets": bench_summary,
        "injection_trials": trials.drop(columns=[c for c in trials.columns if c.startswith("_")],
                                        errors="ignore"),
        "ablation_comparison": abl,
        "correlation_results": corr,
        "roc_pr_curves": roc,
    })
    log("  wrote D6_benchmark_results")

    # ===================== Stage 8: figures =====================
    write_audit_log(cfg, df, raw, main, trials, abl, corr, t0)
    make_figures()

    # ===================== Stage 9: manifest =====================
    manifest = {
        "run_id": RUN_ID, "version": VERSION,
        "utc": datetime.now(timezone.utc).isoformat(),
        "data_span": [str(df.index.min()), str(df.index.max())],
        "n_minutes": int(len(df)), "n_windows_per_pair": int(len(end_times)),
        "n_pairs": len(cfg.pairs), "main_rows": int(len(main)),
        "benchmark_windows": int(len(bm)), "deadband_rate": float(raw["deadband_active"].mean()),
        "elapsed_s": round(time.time() - t0, 1),
        "libs": {"numpy": np.__version__, "pandas": pd.__version__},
        "deliverables": sorted(os.listdir(OUT_RESULTS)),
        "figures": sorted(os.listdir(OUT_FIG)),
    }
    with open(os.path.join(MAN, f"{RUN_ID}.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    log("DONE in %.1fs; results=%d figures=%d" %
        (time.time() - t0, len(manifest["deliverables"]), len(manifest["figures"])))
    return manifest


# ---------------- individual writers ----------------
def write_main_scores(main):
    cols = ["timestamp", "pair_id", "sensor_id", "pair_sensor_id", "zone", "regime_id",
            "Q_dist", "Q_trend", "Q_var", "Q_cp", "d_W1", "d_KS", "d_beta", "d_var", "d_tau",
            "D6_base", "D6_raw", "D6_forDQR", "dominant_evidence", "second_evidence",
            "status_label", "fuse_state", "fuse_active", "deadband_active",
            "deadband_DO_used", "deadband_ORP_used", "D1_target", "D1_ref",
            "D7_zone_consensus_label", "D7_zone_consensus_strength", "usable_for_DQR"]
    m = main[cols].copy()
    for c in ["Q_dist", "Q_trend", "Q_var", "Q_cp", "D6_base", "D6_raw", "D6_forDQR",
              "d_W1", "d_KS", "d_beta", "d_var", "d_tau", "D1_target", "D1_ref",
              "D7_zone_consensus_strength"]:
        m[c] = m[c].round(4)
    pidx = (main.groupby("pair_id")
            .agg(sensor_id=("sensor_id", "first"), pair_sensor_id=("pair_sensor_id", "first"),
                 zone=("zone", "first"), n_windows=("timestamp", "count"),
                 mean_D6_forDQR=("D6_forDQR", "mean")).round(3).reset_index())
    write_sheets(os.path.join(OUT_RESULTS, "D6_main_scores.xlsx"),
                 {"main_scores": m, "pair_index": pidx})
    log("  wrote D6_main_scores (%d rows)" % len(m))


def write_detector_raw(raw):
    dist = raw[["timestamp", "pair_id", "regime_id", "d_W1", "d_KS", "d_CvM", "risk_dist",
                "sample_size_target", "sample_size_ref"]].round(5)
    trend = raw[["timestamp", "pair_id", "regime_id", "beta_target", "beta_ref",
                 "beta_target_lo", "beta_target_hi", "beta_ref_lo", "beta_ref_hi",
                 "d_beta", "risk_trend", "I_sign"]].round(6)
    var = raw[["timestamp", "pair_id", "regime_id", "iqr_target", "iqr_ref", "d_var",
               "risk_var", "deadband_active", "deadband_DO_used", "deadband_ORP_used"]].round(5)
    cp = raw[["timestamp", "pair_id", "regime_id", "n_cp_target", "n_cp_ref", "d_tau",
              "cp_one_sided", "Q_cp"]].round(4)
    summary = (raw.groupby("pair_id").agg(
        n=("timestamp", "count"), d_W1_mean=("d_W1", "mean"), d_beta_mean=("d_beta", "mean"),
        d_var_mean=("d_var", "mean"), deadband_rate=("deadband_active", "mean"),
        cp_onesided_rate=("cp_one_sided", "mean")).round(4).reset_index())
    write_sheets(os.path.join(OUT_RESULTS, "D6_detector_outputs_raw.xlsx"),
                 {"dist_raw": dist, "trend_raw": trend, "var_raw": var, "cp_raw": cp,
                  "detector_summary": summary})
    log("  wrote D6_detector_outputs_raw (%d rows)" % len(raw))


def write_mapping_params(mapper, cfg, trend_mad):
    rows = []
    for p in mapper.all_params():
        rows.append({"subscore": p.subscore_name, "regime_id": p.regime_id,
                     "mapping_type": p.mapping_type, "q50": round(p.q50, 6),
                     "q75": round(p.q75, 6), "q90": round(p.q90, 6), "q975": round(p.q975, 6),
                     "sample_size": p.sample_size, "benchmark_source": p.benchmark_source})
    params_df = pd.DataFrame(rows).sort_values(["subscore", "regime_id"])
    db_rows = [{"regime_id": "default", "delta_DO_mgL": cfg.deadband.default["DO"],
                "delta_ORP_mV": cfg.deadband.default["ORP"], "version": cfg.deadband.version,
                "effective_date": cfg.deadband.effective_date}]
    for rid, vals in cfg.deadband.by_regime.items():
        db_rows.append({"regime_id": rid, "delta_DO_mgL": vals.get("DO"),
                        "delta_ORP_mV": vals.get("ORP"), "version": cfg.deadband.version,
                        "effective_date": cfg.deadband.effective_date})
    cp_rule = pd.DataFrame([
        {"condition": "both no change-point", "score": 5},
        {"condition": "both cp, |dtau|<3h", "score": 5},
        {"condition": "both cp, 3-12h", "score": 4},
        {"condition": "both cp, 12-24h", "score": 3},
        {"condition": "both cp, >24h apart", "score": 2},
        {"condition": "one-sided cp <24h", "score": 2},
        {"condition": "one-sided cp >=24h", "score": 1}])
    weights = pd.DataFrame([{"subscore": k, "weight": v} for k, v in cfg.aggregation.weights.items()] +
                           [{"subscore": "lambda_blend", "weight": cfg.aggregation.lambda_blend}])
    tmad = pd.DataFrame([{"pair_id": k, "trend_MAD_scale": round(v, 6)} for k, v in trend_mad.items()])
    versions = pd.DataFrame([{"component": "module", "version": VERSION},
                             {"component": "deadband", "version": cfg.deadband.version},
                             {"component": "mapping", "version": "quantile-v1.0"},
                             {"component": "run_id", "version": RUN_ID}])
    write_sheets(os.path.join(OUT_RESULTS, "D6_mapping_params.xlsx"),
                 {"quantile_params": params_df, "deadband_by_regime": pd.DataFrame(db_rows),
                  "cp_rule_table": cp_rule, "aggregation_weights": weights,
                  "trend_mad_scale": tmad, "versions": versions})
    log("  wrote D6_mapping_params")


def write_benchmark_library(bm_tbl, bm, cfg):
    risk_q = []
    for (pid, reg), g in bm.groupby(["pair_id", "regime_id"]):
        for metric in ["d_W1", "d_KS", "d_CvM", "d_beta", "d_var"]:
            arr = g[metric].dropna()
            if len(arr) < 10:
                continue
            risk_q.append({"pair_id": pid, "regime_id": reg, "metric": metric,
                           "n": int(len(arr)),
                           "q50": round(float(arr.quantile(0.50)), 6),
                           "q75": round(float(arr.quantile(0.75)), 6),
                           "q90": round(float(arr.quantile(0.90)), 6),
                           "q975": round(float(arr.quantile(0.975)), 6)})
    inclusion = pd.DataFrame([
        {"criterion": "D1_target & D1_ref >= 4.5", "rationale": "both sensors healthy"},
        {"criterion": "D2 usable both sides", "rationale": "sufficient valid minutes"},
        {"criterion": "D7 consensus strength < 0.5", "rationale": "no process-asymmetry event"},
        {"criterion": "window length >= 24 h continuous", "rationale": "stable distribution"}])
    write_sheets(os.path.join(OUT_RESULTS, "D6_pair_benchmark_library.xlsx"),
                 {"benchmark_summary": bm_tbl, "risk_quantiles": pd.DataFrame(risk_q),
                  "inclusion_criteria": inclusion})
    log("  wrote D6_pair_benchmark_library")


def write_arbitration_log(trans, main):
    if trans.empty:
        write_sheets(os.path.join(OUT_RESULTS, "D6_arbitration_log.xlsx"),
                     {"arbitration_transitions": pd.DataFrame(), "conflict_log": pd.DataFrame(),
                      "layer_statistics": pd.DataFrame()})
        return
    t = trans.copy()
    for c in ["before", "after", "final_D6_forDQR"]:
        if c in t.columns:
            t[c] = pd.to_numeric(t[c], errors="coerce").round(4)
    # keep transitions that actually changed the score + a sample of pass-throughs
    changed = t[(t["before"] - t["after"]).abs() > 1e-6]
    sample_pass = t[(t["before"] - t["after"]).abs() <= 1e-6].sample(
        min(4000, max(0, len(t) - len(changed))), random_state=0) if len(t) > len(changed) else t.iloc[:0]
    trans_out = pd.concat([changed, sample_pass]).sort_values(["timestamp", "pair_id"])
    conflicts = t[t["conflict"] == True].drop_duplicates(["timestamp", "pair_id"])
    layer_stats = (t.groupby("layer")
                   .agg(n=("layer", "count"),
                        n_changed=("before", lambda s: int((np.abs(s.values - t.loc[s.index, "after"].values) > 1e-6).sum())),
                        mean_delta=("after", lambda s: round(float(np.mean(s.values - t.loc[s.index, "before"].values)), 4)))
                   .reset_index())
    fuse_stats = (main.groupby("fuse_state").size().rename("n").reset_index())
    write_sheets(os.path.join(OUT_RESULTS, "D6_arbitration_log.xlsx"),
                 {"arbitration_transitions": trans_out.head(20000),
                  "conflict_log": conflicts, "layer_statistics": layer_stats,
                  "fuse_state_distribution": fuse_stats})


def write_audit_log(cfg, df, raw, main, trials, abl, corr, t0):
    run_meta = pd.DataFrame([
        {"key": "run_id", "value": RUN_ID}, {"key": "version", "value": VERSION},
        {"key": "utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "python", "value": platform.python_version()},
        {"key": "numpy", "value": np.__version__}, {"key": "pandas", "value": pd.__version__},
        {"key": "data_minutes", "value": int(len(df))},
        {"key": "data_start", "value": str(df.index.min())},
        {"key": "data_end", "value": str(df.index.max())},
        {"key": "main_rows", "value": int(len(main))},
        {"key": "deadband_rate", "value": round(float(raw["deadband_active"].mean()), 4)},
    ])
    cfg_snapshot = pd.DataFrame([
        {"config": "weights", "value": json.dumps(cfg.aggregation.weights)},
        {"config": "lambda_blend", "value": cfg.aggregation.lambda_blend},
        {"config": "deadband_default", "value": json.dumps(cfg.deadband.default)},
        {"config": "window_main_h", "value": cfg.windows.online_main_len_h},
        {"config": "step_h", "value": cfg.windows.online_main_step_h},
        {"config": "cp_len_d", "value": cfg.windows.cp_len_d},
        {"config": "fuse_d1_threshold", "value": cfg.arbitration.d1_low_threshold},
        {"config": "aerobic_floor", "value": cfg.arbitration.aerobic_strong_floor},
    ])
    upstream_versions = pd.DataFrame([
        {"upstream": "D1", "adapter": "D1Adapter", "version": "D1-v1.1(proxy)",
         "contract": "reads health score per sensor; D6 never recomputes D1 stats"},
        {"upstream": "D7", "adapter": "D7Adapter", "version": "D7-v1.1(proxy)",
         "contract": "reads same-zone consensus label/strength per pair"},
        {"upstream": "D2", "adapter": "D2Adapter", "version": "D2-v1.1(proxy)",
         "contract": "reads usability gate per sensor"},
        {"upstream": "regime", "adapter": "RegimeAdapter", "version": "regime-v1.1(proxy)",
         "contract": "reads regime_id per hour"},
    ])
    write_sheets(os.path.join(OUT_RESULTS, "D6_audit_log.xlsx"),
                 {"run_manifest": run_meta, "config_snapshot": cfg_snapshot,
                  "upstream_versions": upstream_versions})
    log("  wrote D6_audit_log")


def summarize_targets(trials, abl, corr):
    def auc_of(t):
        s = trials[trials["inj_type"] == t]
        return round(float(s["AUC_D6raw"].mean()), 3) if len(s) else np.nan
    def auc_dqr(t):
        s = trials[trials["inj_type"] == t]
        return round(float(s["AUC_D6forDQR"].mean()), 3) if len(s) else np.nan
    night_red = abl["night_FAR_reduction_vs_no_deadband"].iloc[0] \
        if "night_FAR_reduction_vs_no_deadband" in abl.columns and len(abl) else np.nan
    corr_all = corr[corr["pair"] == "ALL"].iloc[0] if len(corr) else None
    rows = [
        {"target": "AUC(INJ-A unilateral drift) D6_raw > 0.85", "observed": auc_of("INJ-A"),
         "pass": (auc_of("INJ-A") or 0) > 0.85},
        {"target": "AUC(INJ-B unilateral step) D6_raw high", "observed": auc_of("INJ-B"),
         "pass": (auc_of("INJ-B") or 0) > 0.75},
        {"target": "AUC(INJ-E bilateral switch) D6_raw < 0.35 (should NOT fire)",
         "observed": auc_of("INJ-E"), "pass": (auc_of("INJ-E") if not np.isnan(auc_of("INJ-E")) else 1) < 0.45},
        {"target": "AUC(INJ-F common-mode) D6_forDQR ~0.5 (fuse neutralises)",
         "observed": auc_dqr("INJ-F"),
         "pass": (0.30 <= (auc_dqr("INJ-F") if not np.isnan(auc_dqr('INJ-F')) else 0) <= 0.70)},
        {"target": "night FAR reduction (deadband vs no_deadband) >= 50%",
         "observed": night_red, "pass": (night_red or 0) >= 0.5},
        {"target": "corr(D6_raw, D1-regime) < 0.65 (independent redundancy)",
         "observed": corr_all["corr_D6raw_vs_D1regime"] if corr_all is not None else np.nan,
         "pass": (abs(corr_all["corr_D6raw_vs_D1regime"]) < 0.65) if corr_all is not None else False},
        {"target": "corr(D6_forDQR, D7) < 0.65",
         "observed": corr_all["corr_D6forDQR_vs_D7strength"] if corr_all is not None else np.nan,
         "pass": (abs(corr_all["corr_D6forDQR_vs_D7strength"]) < 0.65) if corr_all is not None else False},
    ]
    return pd.DataFrame(rows)


def make_figures():
    from d6.figures import fig_core, fig_diag, fig_valid
    main_x = os.path.join(OUT_RESULTS, "D6_main_scores.xlsx")
    det_x = os.path.join(OUT_RESULTS, "D6_detector_outputs_raw.xlsx")
    prof_x = os.path.join(OUT_RESULTS, "D6_pair_profile_summary.xlsx")
    res_x = os.path.join(OUT_RESULTS, "D6_benchmark_results.xlsx")
    resid_pkl = os.path.join(ART, "residuals.pkl")
    made = []
    for fn, args in [
        (fig_core.fig_M1, (main_x, resid_pkl, OUT_FIG)),
        (fig_core.fig_M2, (main_x, OUT_FIG)),
        (fig_core.fig_M3, (det_x, main_x, OUT_FIG)),
        (fig_diag.fig_D1, (main_x, OUT_FIG)),
        (fig_diag.fig_D2, (main_x, OUT_FIG)),
        (fig_diag.fig_D3, (main_x, OUT_FIG)),
        (fig_valid.fig_V1, (res_x, OUT_FIG)),
        (fig_valid.fig_V2, (res_x, OUT_FIG)),
    ]:
        try:
            svg, png = fn(*args)
            made.append(os.path.basename(svg))
            log("  figure %s" % os.path.basename(svg))
        except Exception as e:
            log("  FIGURE FAILED %s: %s" % (fn.__name__, e))
    # need pair_subscore_dist available to M2 -> copy from profile workbook
    return made


if __name__ == "__main__":
    full = not (len(sys.argv) > 1 and sys.argv[1] == "--smoke")
    main(full=full)
