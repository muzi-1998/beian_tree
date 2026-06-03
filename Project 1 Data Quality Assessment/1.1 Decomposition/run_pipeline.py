"""run_pipeline.py — 1.1 节双轨分解-白化全链路主流程 (plan §7.4).

Differentiated dual-track decomposition + fast/slow whitening for North-Bank
multi-scale heterogeneous data. Produces every §6.3 deliverable:

  W1  unified 1-min time base (parquet) + flags, inventory table, consistency
      report, availability heatmap
  W2  adaptive harmonic-order table, per-channel trend/seasonal/residual,
      four-level decomposition figures
  W3  ARMA/GARCH order table, before/after whitening diagnostics, innovation
      dataset (min native + hourly held to 1-min)
  W4  validation report (sufficiency / no-leakage / differentiation / ablation
      / case studies)  -- see validate.py

Usage:  python run_pipeline.py [--quick]
  --quick limits channels/time for a fast smoke run.
"""
from __future__ import annotations
import argparse
import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from src.config.loader import load_configs, config_hash
from src.semantics import CHANNEL_META, MIN_CHANNELS, channels_in_group
from src.data import loader, preprocess, consistency
from src.baseline import deperiodise
from src.whiten import (offline_identify as oid, online_whitener as ow,
                        diagnostics as dg, warmup as wu, acceptance_gate as ag)
from src.whiten.param_store import ParamStore
from src.outputs import tables, figures

ROOT = Path(__file__).resolve().parent


def _log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ════════════════════════════════════════════════════════════════════════
# W1 — DATA BASE
# ════════════════════════════════════════════════════════════════════════
def w1_data_base(cfg, out):
    paths = cfg["paths"]["data"]
    _log("W1: loading raw sources ...")
    raw_min = loader.load_min(paths["do_file"], paths["orp_file"], paths["flw_file"])
    inf_native = loader.load_influent(paths["influent_file"])
    eff_native = loader.load_effluent(paths["effluent_file"])

    _log("W1: aligning 1-min master clock + flags ...")
    df_min, fl_min = preprocess.align_min(raw_min)
    fl_min = preprocess.mark_transition_zones(fl_min, transition_h=24, freq_min=1)
    fl_min = preprocess.mark_outliers_iqr(df_min, fl_min, k=1.5)

    _log("W1: native hourly preprocessing (cosine fill / same-day / censor) ...")
    inf_f, fl_inf = preprocess.preprocess_hourly(inf_native)
    eff_f, fl_eff = preprocess.preprocess_hourly(eff_native)

    # multi-rate hold onto the 1-min clock (hold_flag)
    inf_held, hflag_inf = preprocess.hold_to_min(inf_f, df_min.index)
    eff_held, hflag_eff = preprocess.hold_to_min(eff_f, df_min.index)

    # ── unified 1-min base parquet ────────────────────────────────────────
    base = pd.concat([df_min, inf_held, eff_held], axis=1)
    flag_all = pd.concat([fl_min, hflag_inf, hflag_eff], axis=1)
    flag_all.columns = [f"flag_{c}" for c in flag_all.columns]
    base_out = pd.concat([base, flag_all], axis=1)
    pq = Path(cfg["paths"]["parquet_root"]); pq.mkdir(parents=True, exist_ok=True)
    base_out.to_parquet(pq / "time_base_1min.parquet")
    inf_f.to_parquet(pq / "influent_hourly.parquet")
    eff_f.to_parquet(pq / "effluent_hourly.parquet")
    fl_inf.to_parquet(pq / "influent_hourly_flags.parquet")
    fl_eff.to_parquet(pq / "effluent_hourly_flags.parquet")
    _log(f"W1: time_base_1min.parquet written {base_out.shape}")

    # ── inventory table (native series + flags + track) ───────────────────
    ff = {}
    for c in df_min.columns:
        ff[c] = (raw_min[c].reindex(df_min.index) if c in raw_min else df_min[c],
                 fl_min[c], "min")
    for c in inf_f.columns:
        ff[c] = (inf_native[c], fl_inf[c], "hour")
    for c in eff_f.columns:
        ff[c] = (eff_native[c], fl_eff[c], "hour")
    inv = tables.inventory_table(ff)
    tables.write_table(inv, cfg["paths"]["table_root"], "data_inventory")

    # ── consistency diagnostics ───────────────────────────────────────────
    _log("W1: consistency diagnostics ...")
    cons = {
        "value_rate": consistency.value_rate_report(raw_min, inf_native, eff_native),
        "parallel_symmetry": consistency.parallel_symmetry(df_min),
        "along_train_gradient": consistency.along_train_gradient(df_min),
        "do4_floor_vs_freeze": consistency.do4_floor_vs_freeze(df_min),
        "nitrogen_balance": consistency.nitrogen_balance(inf_f, eff_f),
    }
    for k, v in cons.items():
        if isinstance(v, pd.DataFrame) and not v.empty:
            tables.write_table(v, cfg["paths"]["table_root"], f"consistency_{k}")

    # ── availability heatmap ──────────────────────────────────────────────
    _log("W1: availability heatmap ...")
    fig_root = Path(cfg["paths"]["figure_root"]); fig_root.mkdir(parents=True, exist_ok=True)
    figures.availability_heatmap(flag_all.rename(columns=lambda c: c.replace("flag_", "")),
                                 fig_root / "fig_W1_availability_heatmap.png",
                                 title="North-Bank data availability (1.1 time base)")

    out.update(dict(df_min=df_min, fl_min=fl_min, inf_f=inf_f, fl_inf=fl_inf,
                    eff_f=eff_f, fl_eff=fl_eff, inventory=inv, consistency=cons))
    return out


# ════════════════════════════════════════════════════════════════════════
# W2 — DIFFERENTIATED DE-PERIODISATION
# ════════════════════════════════════════════════════════════════════════
def _iter_channels(cfg, out, quick=False):
    """Yield (channel, series, group_cfg, dt_native, track, censored_mask)."""
    dcfg = cfg["deperiodise"]; groups = dcfg["groups"]
    df_min, inf_f, eff_f = out["df_min"], out["inf_f"], out["eff_f"]
    fl_inf, fl_eff = out["fl_inf"], out["fl_eff"]

    min_channels = MIN_CHANNELS
    if quick:
        min_channels = ["DO_1_1", "DO_1_4", "ORP_2_1", "QR_2"]
    for c in min_channels:
        meta = CHANNEL_META[c]; g = meta["group"]
        yield c, df_min[c], groups[g], 1.0, "min", None
    inf_channels = list(inf_f.columns) if not quick else ["inf_COD", "inf_Q"]
    for c in inf_channels:
        g = CHANNEL_META[c]["group"]
        yield c, inf_f[c], groups[g], 1.0, "hour", None
    eff_channels = list(eff_f.columns) if not quick else ["eff_COD", "eff_NH4"]
    for c in eff_channels:
        g = CHANNEL_META[c]["group"]
        cm = (fl_eff[c] == preprocess.FLAG["CENSORED"]) if c in fl_eff else None
        yield c, eff_f[c], groups[g], 1.0, "hour", cm


def w2_decompose(cfg, out, quick=False):
    dcfg = cfg["deperiodise"]
    fit_days = dcfg["causal_fit_first_days"]
    alpha = dcfg["f_test_alpha"]
    _log("W2: differentiated decomposition ...")

    order_rows, suff_rows = [], []
    resid_min, trend_min, seas_min = {}, {}, {}
    resid_inf, resid_eff = {}, {}
    decomp_store = {}

    for c, s, gcfg, dt_native, track, cm in _iter_channels(cfg, out, quick):
        dec = deperiodise.decompose_channel(s, gcfg, dt_native, fit_days,
                                            order_alpha=alpha, censored_mask=cm)
        rec = dec["order_record"]
        order_rows.append(dict(channel=c, track=track, group=CHANNEL_META[c]["group"],
                               zone=CHANNEL_META[c]["zone"],
                               periods=str(rec["periods"]),
                               selected_order=rec["selected_order"],
                               nyquist_cap=rec.get("nyquist_cap"),
                               f_driven=rec.get("f_driven_order"),
                               aic_best=rec.get("aic_best_order"),
                               bic_best=rec.get("bic_best_order"),
                               f_pvalues=str(rec.get("f_pvalues", []))[:60]))
        pr = deperiodise.residual_spectrum_peak_ratio(dec["residual"],
                                                      gcfg["candidate_periods"], dt_native)
        suff_rows.append(dict(channel=c, track=track, **pr))
        decomp_store[c] = dec
        if track == "min":
            resid_min[c] = dec["residual"]; trend_min[c] = dec["trend"]; seas_min[c] = dec["seasonal"]
        elif c.startswith("inf_"):
            resid_inf[c] = dec["residual"]
        else:
            resid_eff[c] = dec["residual"]

    order_df = pd.DataFrame(order_rows)
    tables.write_table(order_df, cfg["paths"]["table_root"], "harmonic_order_table")
    tables.write_table(pd.DataFrame(suff_rows), cfg["paths"]["table_root"],
                       "decomposition_sufficiency")

    # save residual datasets
    pq = Path(cfg["paths"]["parquet_root"])
    if resid_min:
        pd.DataFrame(resid_min).to_parquet(pq / "residual_min.parquet")
    if resid_inf:
        pd.DataFrame(resid_inf).to_parquet(pq / "residual_influent.parquet")
    if resid_eff:
        pd.DataFrame(resid_eff).to_parquet(pq / "residual_effluent.parquet")

    out.update(dict(decomp=decomp_store, order_df=order_df,
                    resid_min=resid_min, resid_inf=resid_inf, resid_eff=resid_eff))
    _log(f"W2: {len(decomp_store)} channels decomposed; harmonic_order_table written")
    return out


# ════════════════════════════════════════════════════════════════════════
# W3 — ARMA/GARCH WHITENING
# ════════════════════════════════════════════════════════════════════════
def w3_whiten(cfg, out, quick=False):
    wcfg = cfg["whiten"]
    store = ParamStore()
    _log("W3: cold-start identification + whitening ...")

    arma_rows, cmp_rows = [], []
    innov_min, std_min = {}, {}
    innov_inf, innov_eff = {}, {}
    cold_days = wcfg["cold_start_reference_days"]

    def process(c, resid, track):
        grid = wcfg["arma_grid"]["min" if track == "min" else "hour"]
        lb = wcfg["ljungbox_lags"]["min" if track == "min" else "hour"]
        # cold-start reference window
        if track == "min":
            ref = resid.iloc[:cold_days * 1440]
        else:
            ref = resid
        model = oid.identify(ref, None, grid, wcfg["use_garch"], version=f"{c}_v1",
                             lb_lags=lb)
        if model is None:
            return None
        res = ow.whiten_series(resid, model)
        innov, z = res["innovation"], res["std_innovation"]
        # acceptance gate (post-hoc record)
        passed, reasons = ag.acceptance_gate(model, float(np.nanvar(resid)),
                                              innov.dropna().values, wcfg,
                                              diag=model.diagnostics)
        # warm-restart state refresh on the last warmup_hours
        if track == "min":
            recent = resid.iloc[-wcfg["warmup_hours"] * 60:]
        else:
            recent = resid.iloc[-wcfg["warmup_hours"]:]
        model = wu.warmup(model, recent)
        store.publish(c, model)

        # windowed LB pass-rate (honest large-n metric) + ACF reduction
        win = 1440 if track == "min" else 168
        wlb_res = dg.windowed_lb_pass_rate(resid, win, lags=lb)
        wlb_inn = dg.windowed_lb_pass_rate(z, win, lags=lb)
        # single-shot ADF/KPSS/ARCH on innovation (fine on full series)
        d_inn = dg.full_diagnostics(z.dropna().values, lb_lags=lb)
        arma_rows.append(dict(channel=c, track=track,
                              p=model.p, q=model.q,
                              garch=model.garch is not None,
                              aic=model.diagnostics.get("aic"),
                              bic=model.diagnostics.get("bic"),
                              accepted=passed, gate=";".join(reasons)))
        cmp_rows.append(dict(
            channel=c, track=track,
            lb_passrate_resid=wlb_res["lb_pass_rate"],
            lb_passrate_innov=wlb_inn["lb_pass_rate"],
            n_windows=wlb_inn["n_windows"],
            acf1_resid=dg.acf1(resid.dropna().values),
            acf1_innov=dg.acf1(z.dropna().values),
            mabsacf_resid=dg.mean_abs_acf(resid.dropna().values),
            mabsacf_innov=dg.mean_abs_acf(z.dropna().values),
            adf_p_innov=d_inn["adf_pvalue"], adf_reject_innov=d_inn["adf_reject_unitroot"],
            kpss_p_innov=d_inn["kpss_pvalue"], kpss_stat_innov=d_inn["kpss_stationary"],
            arch_p_innov=d_inn["arch_pvalue"], arch_het_innov=d_inn["arch_heterosked"]))
        return innov, z

    for c, resid in out["resid_min"].items():
        r = process(c, resid, "min")
        if r: innov_min[c], std_min[c] = r
    for c, resid in out["resid_inf"].items():
        r = process(c, resid, "hour")
        if r: innov_inf[c] = r[1]
    for c, resid in out["resid_eff"].items():
        r = process(c, resid, "hour")
        if r: innov_eff[c] = r[1]

    arma_df = pd.DataFrame(arma_rows)
    cmp_df = pd.DataFrame(cmp_rows)
    tables.write_table(arma_df, cfg["paths"]["table_root"], "arma_garch_order_table")
    tables.write_table(cmp_df, cfg["paths"]["table_root"], "whitening_before_after")

    # innovation datasets
    pq = Path(cfg["paths"]["parquet_root"])
    if std_min:
        std_min_df = pd.DataFrame(std_min)
        std_min_df.to_parquet(pq / "innovation_min.parquet")
        # hold hourly innovations to 1-min clock for the §1.2 unified input
        hourly_innov = {}
        for d in (innov_inf, innov_eff):
            hourly_innov.update(d)
        if hourly_innov:
            hi = pd.DataFrame(hourly_innov)
            hi_held, _ = preprocess.hold_to_min(hi, std_min_df.index)
            unified = pd.concat([std_min_df, hi_held], axis=1)
            unified.to_parquet(pq / "innovation_unified_1min.parquet")
    if innov_inf:
        pd.DataFrame(innov_inf).to_parquet(pq / "innovation_influent.parquet")
    if innov_eff:
        pd.DataFrame(innov_eff).to_parquet(pq / "innovation_effluent.parquet")

    out.update(dict(store=store, arma_df=arma_df, cmp_df=cmp_df,
                    innov_min=innov_min, std_min=std_min,
                    innov_inf=innov_inf, innov_eff=innov_eff))
    _log(f"W3: {len(arma_rows)} channels whitened; "
         f"mean innov LB pass-rate = {cmp_df['lb_passrate_innov'].mean():.2f} "
         f"(resid {cmp_df['lb_passrate_resid'].mean():.2f})")
    return out


# ════════════════════════════════════════════════════════════════════════
# Representative figures (four-level decomposition + ACF + spectra)
# ════════════════════════════════════════════════════════════════════════
def make_figures(cfg, out, quick=False):
    fig_root = Path(cfg["paths"]["figure_root"])
    df_min = out["df_min"]
    reps = [c for c in ["DO_1_3", "DO_1_4", "ORP_2_1"] if c in out["decomp"]]
    for c in reps:
        dec = out["decomp"][c]
        innov = out["std_min"].get(c)
        if innov is None:
            continue
        # zoom to a 10-day window with the 2025-10-13 spike if available
        win = slice("2025-10-10", "2025-10-20")
        raw = df_min[c].loc[win]
        if raw.dropna().empty:
            win = slice(df_min.index[0], df_min.index[0] + pd.Timedelta(days=10))
            raw = df_min[c].loc[win]
        try:
            figures.four_level_decomposition(
                raw, dec["trend"].loc[win], dec["seasonal"].loc[win],
                dec["residual"].loc[win], innov.loc[win],
                fig_root / f"fig_W2_decomp_{c}.png",
                title=f"Four-level decomposition — {c} ({CHANNEL_META[c]['zone']})")
        except Exception as e:
            _log(f"  fig decomp {c} skipped: {e}")
        # ACF before/after
        try:
            resid = dec["residual"].dropna().values
            zz = innov.dropna().values
            figures.acf_before_after(dg.acf(resid, 40), dg.acf(zz, 40),
                                     fig_root / f"fig_W3_acf_{c}.png",
                                     title=f"ACF before/after whitening — {c}",
                                     conf=dg.acf_conf(len(zz)))
        except Exception as e:
            _log(f"  fig acf {c} skipped: {e}")

    # spectrum comparison on RAW signals: influent COD vs effluent COD vs aerobic
    # DO — reveals the DIFFERENT periodicity structure that motivates the
    # differentiated decomposition (plan Fig.2). Detrended (mean+slow trend
    # removed) but NOT de-seasonalised, so the daily/weekly peaks remain visible.
    try:
        from scipy.signal import welch
        spectra = {}
        for label, series, fs, nper in [
            ("Influent COD (1h)", out["inf_f"].get("inf_COD"), 24, 24 * 14),
            ("Effluent COD (1h)", out["eff_f"].get("eff_COD"), 24, 24 * 14),
            ("Aerobic DO_1_3 (1min)", out["df_min"].get("DO_1_3"), 1440, 1440 * 7),
        ]:
            if series is None:
                continue
            x = pd.Series(series).interpolate(limit=6).dropna().values.astype(float)
            n = len(x)
            if n < 200:
                continue
            # Welch averaged periodogram (fs = samples/day -> freq in cycles/day);
            # variance-reduced so the 24h/12h/168h peaks stand above the continuum
            freq, power = welch(x, fs=fs, nperseg=min(nper, n), detrend="linear")
            spectra[label] = (freq, power)
        if spectra:
            figures.spectrum_comparison(spectra, fig_root / "fig_W2_spectrum_compare.png",
                                        title="Raw periodicity spectra (decomposition strategy basis)")
    except Exception as e:
        _log(f"  spectrum figure skipped: {e}")
    _log("Figures written")


# ════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fast subset run")
    args = ap.parse_args()

    t0 = time.time()
    cfg = load_configs(ROOT / "configs")
    chash = config_hash(cfg)
    _log(f"config hash = {chash}  quick={args.quick}")
    out = {}
    out = w1_data_base(cfg, out)
    out = w2_decompose(cfg, out, quick=args.quick)
    out = w3_whiten(cfg, out, quick=args.quick)
    make_figures(cfg, out, quick=args.quick)

    # run manifest
    man = dict(timestamp=datetime.now().isoformat(), config_hash=chash,
               quick=args.quick, n_channels=int(len(out["order_df"])),
               elapsed_sec=round(time.time() - t0, 1),
               lb_passrate_innov=float(out["cmp_df"]["lb_passrate_innov"].mean()),
               lb_passrate_resid=float(out["cmp_df"]["lb_passrate_resid"].mean()))
    mp = Path(cfg["paths"]["run_manifest"]); mp.mkdir(parents=True, exist_ok=True)
    with open(mp / f"run_{datetime.now():%Y%m%d_%H%M%S}.json", "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2, ensure_ascii=False)
    _log(f"DONE in {man['elapsed_sec']}s  | innov LB pass-rate = "
         f"{man['lb_passrate_innov']:.2f} (resid {man['lb_passrate_resid']:.2f})")

    # persist `out` essentials for validate.py
    import pickle
    with open(ROOT / "outputs" / "_pipeline_state.pkl", "wb") as fh:
        pickle.dump({k: out[k] for k in
                     ["order_df", "arma_df", "cmp_df", "resid_min", "std_min",
                      "resid_inf", "resid_eff", "innov_inf", "innov_eff",
                      "consistency"]}, fh)


if __name__ == "__main__":
    main()
