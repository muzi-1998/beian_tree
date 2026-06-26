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
                        diagnostics as dg, warmup as wu, acceptance_gate as ag,
                        model_selection as ms)
from src.whiten.param_store import ParamStore
from src.outputs import tables, figures

ROOT = Path(__file__).resolve().parent

_PERIOD_LABEL = {1440: "24h", 720: "12h", 10080: "168h",
                 24: "24h", 168: "168h", 12: "12h"}


def _period_str(periods):
    return "+".join(_PERIOD_LABEL.get(int(p), f"{int(p)}") for p in periods)


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

    order_rows, suff_rows, subhourly_rows = [], [], []
    resid_min, trend_min, seas_min = {}, {}, {}
    resid_inf, resid_eff = {}, {}
    decomp_store = {}

    for c, s, gcfg, dt_native, track, cm in _iter_channels(cfg, out, quick):
        dec = deperiodise.decompose_channel(s, gcfg, dt_native, fit_days,
                                            order_alpha=alpha, censored_mask=cm)
        # ── Item 4: aerobic-DO sub-hourly aeration limit-cycle removal ────────
        # The 24h/12h harmonics miss the blower start/stop limit cycle; detect &
        # remove it (decomposition route, not AR — keeps the cycle explicit and
        # scorable via aeration_cycle.csv, avoids hiding a fault in AR lags).
        if gcfg.get("remove_subhourly") and track == "min":
            det = deperiodise.detect_dominant_period(
                dec["residual"], dt_native,
                period_range=tuple(gcfg.get("subhourly_period_range", [20, 180])),
                min_prominence=gcfg.get("subhourly_min_prominence", 6.0))
            if det:
                dec["residual"] = deperiodise.extra_stl_pass(dec["residual"], det["period"])
                subhourly_rows.append(dict(channel=c, zone=CHANNEL_META[c]["zone"],
                                           period_min=det["period"],
                                           prominence=det["prominence"]))
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
        # ── Fix 1: 主周期峰 >= 闸门则迭代 STL 重剥,并落 decomp_pass 标志 ──────
        gate = gcfg.get("decomp_peak_gate",
                        cfg["deperiodise"]["residual_spectrum_peak_ratio_max"])
        max_it = cfg["deperiodise"].get("stl_max_refine_iters", 4)
        n_it = min(gcfg.get("stl_refine_iters",
                            cfg["deperiodise"].get("stl_refine_iters_default", 1)), max_it)
        prim_key = "P1440" if track == "min" else "P24"
        prim_period = 1440 if track == "min" else 24
        it = 0
        while it < n_it and (pr.get(prim_key) or 0) >= gate:
            dec["residual"] = deperiodise.extra_stl_pass(dec["residual"], prim_period)
            pr = deperiodise.residual_spectrum_peak_ratio(
                dec["residual"], gcfg["candidate_periods"], dt_native)
            it += 1
        decomp_pass = bool((pr.get(prim_key) or 0) < gate)
        suff_rows.append(dict(channel=c, track=track,
                              decomp_pass=decomp_pass, stl_iters=it, **pr))
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
    if subhourly_rows:
        tables.write_table(pd.DataFrame(subhourly_rows),
                           cfg["paths"]["table_root"], "aeration_cycle")
        _log(f"W2: aeration sub-hourly cycle removed on {len(subhourly_rows)} "
             f"aerobic-DO channels (recorded in aeration_cycle.csv)")

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

    def process(c, resid, track, raw=None):
        grid = wcfg["arma_grid"]["min" if track == "min" else "hour"]
        lb = wcfg["ljungbox_lags"]["min" if track == "min" else "hour"]
        # cold-start reference window
        ref = resid.iloc[:cold_days * 1440] if track == "min" else resid

        # ── Item 2: detection-floor route (post-anoxic DO) — censored-z, no ARMA ──
        fcfg = wcfg.get("floor_route", {})
        if (fcfg.get("enable", True) and raw is not None
                and CHANNEL_META[c]["group"] == "postanoxic_do"):
            fthr = fcfg.get("near_floor_value", 0.05)
            occ = float((raw.dropna() <= fthr).mean())
            if occ >= fcfg.get("route_occupancy", 0.70):
                z = dg.censored_robust_z(resid, raw=raw, floor_thr=fthr)
                win = 1440
                wlb_r = dg.windowed_lb_pass_rate(resid, win, lags=lb)
                wlb_i = dg.windowed_lb_pass_rate(z, win, lags=lb)
                arma_rows.append(dict(channel=c, track=track, family="floor",
                                      d=0, D=0, p=0, q=0, fd=None, garch=False,
                                      lrd_flag=False, lrd_d_gph=None, aic=None,
                                      bic=None, accepted=False, fallback=True,
                                      gate=f"floor route (occ {occ:.2f}); censored-z"))
                cmp_rows.append(dict(channel=c, track=track,
                    lb_passrate_resid=wlb_r["lb_pass_rate"],
                    lb_passrate_innov=wlb_i["lb_pass_rate"], n_windows=wlb_i["n_windows"],
                    acf1_resid=dg.acf1(resid.dropna().values),
                    acf1_innov=dg.acf1(z.dropna().values),
                    mabsacf_resid=dg.mean_abs_acf(resid.dropna().values),
                    mabsacf_innov=dg.mean_abs_acf(z.dropna().values),
                    adf_p_innov=np.nan, adf_reject_innov=None, kpss_p_innov=np.nan,
                    kpss_stat_innov=None, arch_p_innov=np.nan, arch_het_innov=None,
                    arch_effect=np.nan, signbias_p=np.nan))
                _log(f"  {c}: floor route (occ {occ:.2f}) -> censored-z (excluded from whitening)")
                return z, z
        # ── data-driven per-channel model selection (ARMA/ARIMA/SARIMA/ARFIMA) ──
        if wcfg.get("model_selection", {}).get("enable", True):
            model, sel = ms.select_model(ref, wcfg, version=f"{c}_v1",
                                         track=track, lb_lags=lb)
        else:
            model = oid.identify(ref, None, grid, wcfg["use_garch"],
                                 version=f"{c}_v1", lb_lags=lb)
            sel = dict(family="arma", d=0, D=0, p_arma=getattr(model, "p", 0),
                       q=getattr(model, "q", 0), fd=None, lrd_flag=False,
                       lrd_d_gph=None) if model is not None else {}
        if model is None:
            return None
        res = ow.whiten_series(resid, model)
        innov, z = res["innovation"], res["std_innovation"]

        # honest large-n metrics on the FULL innovation
        win = 1440 if track == "min" else 168
        wlb_res = dg.windowed_lb_pass_rate(resid, win, lags=lb)
        wlb_inn = dg.windowed_lb_pass_rate(z, win, lags=lb)
        acf1_inn = dg.acf1(z.dropna().values)
        # acceptance gate on the FULL-series windowed-LB + acf1 (consistent)
        gate_diag = dict(model.diagnostics)
        gate_diag["windowed_lb_passrate"] = wlb_inn["lb_pass_rate"]
        gate_diag["acf1_innov"] = acf1_inn
        passed, reasons = ag.acceptance_gate(model, float(np.nanvar(resid)),
                                             innov.dropna().values, wcfg,
                                             diag=gate_diag)
        # ── Fix 2: 接受门失败 -> 兜底,而不是照样发布失败模型的创新 ──────────
        fb = wcfg.get("fallback", {}).get("on_gate_fail", "none")
        used_fallback = False
        if not passed and fb == "robust_z":
            z = dg.robust_z(resid)            # MAD 标准化残差兜底
            innov = z.copy()
            used_fallback = True
            wlb_inn = dg.windowed_lb_pass_rate(z, win, lags=lb)
            acf1_inn = dg.acf1(z.dropna().values)
        # warm-restart state refresh on the last warmup_hours
        if track == "min":
            recent = resid.iloc[-wcfg["warmup_hours"] * 60:]
        else:
            recent = resid.iloc[-wcfg["warmup_hours"]:]
        model = wu.warmup(model, recent)
        store.publish(c, model)

        # single-shot ADF/KPSS/ARCH on innovation (fine on full series)
        d_inn = dg.full_diagnostics(z.dropna().values, lb_lags=lb)
        arma_rows.append(dict(channel=c, track=track,
                              family=sel.get("family"), d=sel.get("d"),
                              D=sel.get("D"), p=sel.get("p_arma"), q=sel.get("q"),
                              fd=sel.get("fd"), garch=model.garch is not None,
                              lrd_flag=sel.get("lrd_flag"),
                              lrd_d_gph=sel.get("lrd_d_gph"),
                              aic=model.diagnostics.get("aic"),
                              bic=model.diagnostics.get("bic"),
                              accepted=passed, fallback=used_fallback,
                              gate=";".join(reasons)))
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
            arch_p_innov=d_inn["arch_pvalue"], arch_het_innov=d_inn["arch_heterosked"],
            arch_effect=dg.mean_abs_acf((z.dropna().values) ** 2, 1, 10),
            signbias_p=dg.sign_bias_test(z.dropna().values).get("signbias_p")))
        return innov, z

    for c, resid in out["resid_min"].items():
        r = process(c, resid, "min", raw=out["df_min"].get(c))
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
                title=f"Four-level decomposition — {c} ({CHANNEL_META[c]['zone']})",
                innov_kind=out.get("kind_of", {}).get(c, "innovation"))
        except Exception as e:
            _log(f"  fig decomp {c} skipped: {e}")
        # ACF before/after
        try:
            resid = dec["residual"].dropna().values
            zz = innov.dropna().values
            # min-level (DO/ORP) ACF at lag 60 (≈1 h of 1-min lags)
            figures.acf_before_after(dg.acf(resid, 60), dg.acf(zz, 60),
                                     fig_root / f"fig_W3_acf_{c}.png",
                                     title=f"ACF before/after whitening — {c} (lag 60)",
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
# Per-variable EMD-style stacked decomposition figures (one PNG per channel)
# ════════════════════════════════════════════════════════════════════════
def _decomp_ylabels(dec, ch, arma_lk):
    """English panel labels with method annotations (J harmonic order, AR(p))."""
    rec = dec.get("order_record", {}) or {}
    J = rec.get("selected_order", 0) or 0
    periods = rec.get("periods", []) or []
    if J > 0 and periods:
        seas = f"Seasonal s(t)\n({_period_str(periods)}, J={J})"
    else:
        seas = "Seasonal s(t)\n(STL)"
    p, q, fb = arma_lk.get(ch, (0, 0, False))
    if fb:
        inn = "Innovation η(t)\n(robust-z)"
    elif p > 0 and q > 0:
        inn = f"Innovation η(t)\n(ARMA({p},{q}))"
    elif p > 0:
        inn = f"Innovation η(t)\n(AR({p}))"
    elif q > 0:
        inn = f"Innovation η(t)\n(MA({q}))"
    else:
        inn = "Innovation η(t)"
    return [f"Raw X(t)\n{ch}", "Trend m(t)", seas, "Residual e(t)", inn]


def _kind_of(out):
    """channel -> innov_kind (innovation/robust_z/censored_z) from the manifest,
    so figures label the innovation panel honestly (non-whitened channels carry
    robust_z / censored_z, not a genuine whitened η)."""
    try:
        man = tables.whiteness_manifest(out["arma_df"], out["cmp_df"])
        return dict(zip(man.channel, man.innov_kind))
    except Exception:
        return {}


def _arma_lookup(out):
    """channel -> (p, q, fallback) from the ARMA/GARCH order table."""
    lk = {}
    arma = out.get("arma_df")
    if arma is not None and len(arma):
        for _, r in arma.iterrows():
            lk[r["channel"]] = (int(r["p"]), int(r["q"]),
                                bool(r.get("fallback", False)))
    return lk


def make_decomposition_stacks(cfg, out, quick=False, min_window_days=10):
    """For EVERY decomposed channel, emit a FULL-FRAME stacked figure:
    raw X(t) -> trend -> seasonal -> residual -> whitened innovation η(t),
    analogous to the IMF_1..n + Residue layout. Min-level channels are shown on
    a representative `min_window_days` window (360k pts would be unreadable);
    hourly channels (naturally ~10^3 pts) are shown in full. Each figure also
    dumps a reproducible CSV+JSON bundle into plot_data/.
    """
    fig_root = Path(cfg["paths"]["figure_root"]) / "decomposition"
    fig_root.mkdir(parents=True, exist_ok=True)
    pdr = cfg["paths"].get("plot_data_root")
    df_min = out["df_min"]; inf_f = out["inf_f"]; eff_f = out["eff_f"]
    std_min = out.get("std_min", {})
    innov_inf = out.get("innov_inf", {}); innov_eff = out.get("innov_eff", {})
    arma_lk = _arma_lookup(out)
    n_done = 0
    for c, dec in out["decomp"].items():
        track = CHANNEL_META[c]["track"]
        zone = CHANNEL_META[c]["zone"]
        try:
            if track == "min":
                raw_full = df_min[c]
                win = slice("2025-10-10", "2025-10-20")
                if raw_full.loc[win].dropna().empty:
                    end = raw_full.index[0] + pd.Timedelta(days=min_window_days)
                    win = slice(raw_full.index[0], end)
                raw = raw_full.loc[win]
                trend = dec["trend"].loc[win]; seasonal = dec["seasonal"].loc[win]
                residual = dec["residual"].loc[win]
                inn = std_min.get(c)
                innov = inn.loc[win] if inn is not None else None
            else:
                raw = (inf_f[c] if c.startswith("inf_") else eff_f[c])
                trend = dec["trend"]; seasonal = dec["seasonal"]; residual = dec["residual"]
                innov = (innov_inf if c.startswith("inf_") else innov_eff).get(c)
            span = f"{raw.index[0]:%Y-%m-%d}~{raw.index[-1]:%Y-%m-%d}"
            figures.decomposition_stack(
                raw, trend, seasonal, residual, innov,
                fig_root / f"decomp_stack_{c}.png",
                ylabels=_decomp_ylabels(dec, c, arma_lk),
                title=f"Multi-scale decomposition — {c} ({zone}, {track})  [{span}]",
                innov_kind=out.get("kind_of", {}).get(c, "innovation"),
                plot_data_root=pdr, bundle_name=f"decomp_stack_{c}")
            n_done += 1
        except Exception as e:
            _log(f"  decomp stack {c} skipped: {e}")
    _log(f"Decomposition-stack figures written: {n_done} -> {fig_root}")


def _channel_components(c, out, win):
    """Return [raw, trend, seasonal, residual, innovation] for a channel,
    windowed (min) or full (hourly); components may be None if unavailable."""
    dec = out["decomp"].get(c)
    if dec is None:
        return None
    track = CHANNEL_META[c]["track"]
    if track == "min":
        raw = out["df_min"][c].loc[win]
        trend = dec["trend"].loc[win]; seasonal = dec["seasonal"].loc[win]
        residual = dec["residual"].loc[win]
        inn = out.get("std_min", {}).get(c)
        innov = inn.loc[win] if inn is not None else None
    else:
        src = out["inf_f"] if c.startswith("inf_") else out["eff_f"]
        raw = src[c]
        trend = dec["trend"]; seasonal = dec["seasonal"]; residual = dec["residual"]
        store = out.get("innov_inf", {}) if c.startswith("inf_") else out.get("innov_eff", {})
        innov = store.get(c)
    return [raw, trend, seasonal, residual, innov]


def make_combined_figures(cfg, out, quick=False, min_window_days=10):
    """One COMBINED full-frame DECOMPOSITION GRID per process group:
    rows = variables, columns = [Raw, Trend, Seasonal, Residual, Innovation],
    shared date x-axis. Dumps reproducible grid bundles to plot_data/.
    """
    fig_root = Path(cfg["paths"]["figure_root"]) / "combined"
    fig_root.mkdir(parents=True, exist_ok=True)
    pdr = cfg["paths"].get("plot_data_root")
    df_min = out["df_min"]; inf_f = out["inf_f"]; eff_f = out["eff_f"]

    win = slice("2025-10-10", "2025-10-20")
    if df_min.loc[win].dropna(how="all").empty:
        end = df_min.index[0] + pd.Timedelta(days=min_window_days)
        win = slice(df_min.index[0], end)
    wmin = df_min.loc[win]
    span_min = f"{wmin.index[0]:%Y-%m-%d}~{wmin.index[-1]:%Y-%m-%d}"
    span_inf = f"{inf_f.index[0]:%Y-%m-%d}~{inf_f.index[-1]:%Y-%m-%d}"
    span_eff = f"{eff_f.index[0]:%Y-%m-%d}~{eff_f.index[-1]:%Y-%m-%d}"

    groups = [
        ("DO", [f"DO_{p}_{i}" for p in (1, 2) for i in range(1, 5)], span_min,
         "DO channels (both trains)"),
        ("ORP", [f"ORP_{p}_{i}" for p in (1, 2) for i in range(1, 4)], span_min,
         "ORP channels (both trains)"),
        ("flow", ["QR_1", "QR_2", "QIR_1", "QIR_2"], span_min,
         "Recycle-flow drivers (QR / QIR)"),
        ("influent", list(inf_f.columns), span_inf,
         "Influent water-quality variables"),
        ("effluent", list(eff_f.columns), span_eff,
         "Effluent water-quality variables"),
    ]
    n_done = 0
    for gname, chans, span, gtitle in groups:
        rows = []
        for c in chans:
            comps = _channel_components(c, out, win)
            if comps is not None:
                rows.append((c, comps))
        if not rows:
            continue
        kinds = [out.get("kind_of", {}).get(c, "innovation") for c, _ in rows]
        figures.combined_group_grid(
            rows, fig_root / f"combined_{gname}.png",
            title=f"{gtitle} — trend/seasonal/residual/innovation grid  [{span}]",
            innov_kinds=kinds, plot_data_root=pdr, bundle_name=f"combined_{gname}")
        n_done += 1
    _log(f"Combined group grids written: {n_done} -> {fig_root}")


# ════════════════════════════════════════════════════════════════════════
# Full-span (whole-record) daily-envelope overviews for the dense min-level
# channels (1-min, 368k pts) — complements the 10-day zoom stacks/grids.
# ════════════════════════════════════════════════════════════════════════
def make_decomposition_overviews(cfg, out, quick=False):
    """Per min-level channel: a FULL-SPAN daily min–max envelope overview of the
    4-level decomposition (so all ~256 days are visible alongside the 10-day
    zoom). Hourly channels are already shown full-span, so are skipped here."""
    fig_root = Path(cfg["paths"]["figure_root"]) / "decomposition_overview"
    fig_root.mkdir(parents=True, exist_ok=True)
    pdr = cfg["paths"].get("plot_data_root")
    df_min = out["df_min"]; std_min = out.get("std_min", {})
    arma_lk = _arma_lookup(out)
    n_done = 0
    for c, dec in out["decomp"].items():
        if CHANNEL_META[c]["track"] != "min":
            continue
        try:
            raw = df_min[c]
            span = f"{raw.index[0]:%Y-%m-%d}~{raw.index[-1]:%Y-%m-%d}"
            figures.decomposition_overview_stack(
                raw, dec["trend"], dec["seasonal"], dec["residual"],
                std_min.get(c), fig_root / f"decomp_overview_{c}.png",
                ylabels=_decomp_ylabels(dec, c, arma_lk),
                title=f"Full-span daily overview — {c} "
                      f"({CHANNEL_META[c]['zone']}, min)  [{span}]",
                innov_kind=out.get("kind_of", {}).get(c, "innovation"),
                plot_data_root=pdr, bundle_name=f"decomp_overview_{c}")
            n_done += 1
        except Exception as e:
            _log(f"  decomp overview {c} skipped: {e}")
    _log(f"Decomposition full-span overviews written: {n_done} -> {fig_root}")


def make_combined_overviews(cfg, out, quick=False):
    """Per min-level group (DO / ORP / QR-QIR): a FULL-SPAN daily min–max
    envelope grid (variables × 5 components) over the whole record."""
    fig_root = Path(cfg["paths"]["figure_root"]) / "combined"
    fig_root.mkdir(parents=True, exist_ok=True)
    pdr = cfg["paths"].get("plot_data_root")
    df_min = out["df_min"]; std_min = out.get("std_min", {})
    groups = [
        ("DO", [f"DO_{p}_{i}" for p in (1, 2) for i in range(1, 5)],
         "DO channels (both trains)"),
        ("ORP", [f"ORP_{p}_{i}" for p in (1, 2) for i in range(1, 4)],
         "ORP channels (both trains)"),
        ("flow", ["QR_1", "QR_2", "QIR_1", "QIR_2"],
         "Recycle-flow drivers (QR / QIR)"),
    ]
    n_done = 0
    for gname, chans, gtitle in groups:
        rows = []
        for c in chans:
            dec = out["decomp"].get(c)
            if dec is None:
                continue
            comps = [df_min[c], dec["trend"], dec["seasonal"],
                     dec["residual"], std_min.get(c)]
            rows.append((c, comps))
        if not rows:
            continue
        span = f"{df_min.index[0]:%Y-%m-%d}~{df_min.index[-1]:%Y-%m-%d}"
        kinds = [out.get("kind_of", {}).get(c, "innovation") for c, _ in rows]
        figures.combined_overview_grid(
            rows, fig_root / f"combined_overview_{gname}.png",
            title=f"{gtitle} — full-span daily overview (min–max envelope)  [{span}]",
            innov_kinds=kinds, plot_data_root=pdr,
            bundle_name=f"combined_overview_{gname}")
        n_done += 1
    _log(f"Combined full-span overviews written: {n_done} -> {fig_root}")


def make_ribbon_overviews(cfg, out, quick=False):
    """SI bird's-eye ribbon overviews: one boxed panel per variable (raw daily
    min–max envelope + mean) for ALL influent / effluent variables, full span.
    A supplementary data-landscape figure (the full-resolution decomposition
    stacks remain the main-text figures)."""
    fig_root = Path(cfg["paths"]["figure_root"]) / "combined"
    fig_root.mkdir(parents=True, exist_ok=True)
    pdr = cfg["paths"].get("plot_data_root")
    for gname, src, gtitle in [
            ("influent", out["inf_f"], "Influent water-quality variables"),
            ("effluent", out["eff_f"], "Effluent water-quality variables")]:
        series_list = [(c, src[c]) for c in src.columns]
        if not series_list:
            continue
        span = f"{src.index[0]:%Y-%m-%d}~{src.index[-1]:%Y-%m-%d}"
        figures.multivar_ribbon_overview(
            series_list, fig_root / f"ribbon_{gname}.png",
            title=f"{gtitle} — full-span overview (daily min–max envelope)  [{span}]",
            plot_data_root=pdr, bundle_name=f"ribbon_{gname}")
    _log(f"Ribbon overviews written -> {fig_root}")


def make_acf_band_figures(cfg, out, quick=False):
    """Combined before/after-whitening ACF grids (rows = variables, cols =
    before residual / after innovation). Hourly sources are banded by daily lag
    (influent lag 48: 1–24/25–48 h; effluent lag 72: 1–24/25–48/49–72 h) so any
    leftover daily-period autocorrelation is easy to spot; the minute-level
    process groups (all DO / all ORP / all QR+QIR) use lag 60 (≈1 h)."""
    fr = Path(cfg["paths"]["figure_root"])
    pdr = cfg["paths"].get("plot_data_root")
    rmin = out.get("resid_min", {}); smin = out.get("std_min", {})
    DO = [f"DO_{p}_{i}" for p in (1, 2) for i in range(1, 5)]
    ORP = [f"ORP_{p}_{i}" for p in (1, 2) for i in range(1, 4)]
    FLOW = ["QR_1", "QR_2", "QIR_1", "QIR_2"]
    specs = [
        ("influent", out.get("resid_inf", {}), out.get("innov_inf", {}),
         list(out["inf_f"].columns), 48, [24, 48], "h",
         "Influent — ACF before/after whitening (lag 48)"),
        ("effluent", out.get("resid_eff", {}), out.get("innov_eff", {}),
         list(out["eff_f"].columns), 72, [24, 48, 72], "h",
         "Effluent — ACF before/after whitening (lag 72)"),
        ("ORP", rmin, smin, ORP, 60, [60], "min",
         "ORP channels — ACF before/after whitening (lag 60)"),
        ("flow", rmin, smin, FLOW, 60, [60], "min",
         "Recycle-flow QR/QIR — ACF before/after whitening (lag 60)"),
    ]
    for gname, R, I, order, lag, edges, unit, title in specs:
        rows = []
        for c in order:
            if c in R and c in I:
                rv = pd.Series(R[c]).dropna().values
                iv = pd.Series(I[c]).dropna().values
                if len(rv) < lag + 5 or len(iv) < lag + 5:
                    continue
                rows.append((c, dg.acf(rv, lag), dg.acf(iv, lag),
                             dg.acf_conf(len(rv)), dg.acf_conf(len(iv))))
        if rows:
            # ORP/QR-QIR are single-band (all-iid, monotone blue) → recolour the
            # After-innovation column yellow/amber to flag "whitened" (matches the
            # warm band tone of the effluent grid). Hourly grids keep lag bands.
            after_c = "#E08214" if gname in ("ORP", "flow") else None
            figures.acf_band_grid(rows, fr / f"fig_W3_acf_{gname}_banded.png",
                                  lag, edges, title=title, lag_unit=unit,
                                  plot_data_root=pdr,
                                  bundle_name=f"acf_{gname}_banded",
                                  after_color=after_c)
    _log("Combined ACF grids (influent/effluent/DO/ORP/flow) written")


def make_do_manifest_figures(cfg, out):
    """Manifest-driven DO ACF figure set (replaces the single 8-channel DO
    before/after grid). Groups DO channels by `scoring_mode` from the whiteness
    manifest and draws the appropriate figure for each:
      A (iid)            before/after ACF + ±1.96/√n band + effect-size labels
      B (autocorr_aware) residual ACF slow decay + broadband spectrum (un-whitenable)
      C (floor_freeze)   floor occupancy / ECDF (censoring, not dynamics)
      D (all DO)         D7 parallel-train symmetry + along-train gradient
    """
    from scipy.signal import welch
    fr = Path(cfg["paths"]["figure_root"])
    man = tables.whiteness_manifest(out["arma_df"], out["cmp_df"])
    do = man[man.channel.str.startswith("DO_")]
    iid = list(do[do.scoring_mode == "iid"].channel)
    nur = list(do[do.scoring_mode == "autocorr_aware"].channel)
    floor = list(do[do.scoring_mode == "floor_freeze"].channel)
    neff = dict(zip(man.channel, man.n_eff_ratio))
    rmin = out.get("resid_min", {}); smin = out.get("std_min", {})
    df_min = out["df_min"]
    frc = cfg["whiten"].get("floor_route", {})
    floor_thr = frc.get("near_floor_value", 0.05)
    route_occ = frc.get("route_occupancy", 0.70)

    # ── (a) iid before/after (After-col shared y + mabsacf effect size) ───
    rows_a = []
    for c in iid:
        if c in rmin and c in smin:
            rv = pd.Series(rmin[c]).dropna().values
            iv = pd.Series(smin[c]).dropna().values
            zn = ("post-anoxic, whitened"
                  if CHANNEL_META[c]["zone"] == "post_anoxic" else "")
            rows_a.append((c, dg.acf(rv, 60), dg.acf(iv, 60), dg.acf_conf(len(rv)),
                           dg.mean_abs_acf(rv), dg.mean_abs_acf(iv), zn))
    if rows_a:
        figures.do_panel_iid(rows_a, fr / "fig_W3_acf_DO_A_iid.png")

    # ── (b) near-UR residual ACF (lag 120) + spectrum (f^-2 ref) ──────────
    rows_b = []
    for c in nur:
        if c in rmin:
            rv = pd.Series(rmin[c]).interpolate(limit=6).dropna().values.astype(float)
            f, P = welch(rv, fs=60.0, nperseg=min(10080, len(rv)), detrend="linear")
            sel = f > 0
            rows_b.append((c, dg.acf(rv, 120), f[sel], P[sel],
                           float(neff.get(c, np.nan))))
    if rows_b:
        figures.do_panel_nearur(rows_b, fr / "fig_W3_acf_DO_B_nearUR.png")

    # ── (c) floor occupancy (floor channel + parallel partner) ────────────
    series_c = {}
    for c in floor:
        series_c[c] = df_min[c].values
        tr = c.split("_")[1]
        partner = f"DO_{'2' if tr == '1' else '1'}_4"
        if partner in df_min:
            series_c[partner] = df_min[partner].values
    if series_c:
        figures.do_panel_floor(series_c, fr / "fig_W3_acf_DO_C_floor.png",
                               floor_thr=floor_thr, route_occ=route_occ)

    # ── (d) D7 spatial profile + parallel-train difference ────────────────
    do_raw = {c: df_min[c].values
              for c in [f"DO_{p}_{i}" for p in (1, 2) for i in range(1, 5)]
              if c in df_min}
    zone_lab = {1: "aerobic\nfront", 2: "aerobic\nmid", 3: "aerobic\nrear",
                4: "post-\nanoxic"}
    positions = [(zone_lab[i], f"DO_1_{i}", f"DO_2_{i}") for i in range(1, 5)
                 if f"DO_1_{i}" in do_raw and f"DO_2_{i}" in do_raw]
    if positions:
        figures.do_panel_d7(do_raw, positions, fr / "fig_W3_acf_DO_D_d7.png")

    # ── composite (a)–(d), vector (PDF/SVG) ───────────────────────────────
    if rows_a and rows_b and series_c and positions:
        figures.do_composite(rows_a, rows_b, series_c, do_raw, positions,
                             fr / "fig_W3_DO_composite.png",
                             floor_thr=floor_thr, route_occ=route_occ, vector=True)

    old = fr / "fig_W3_acf_DO_banded.png"     # retire the superseded single grid
    if old.exists():
        old.unlink()
    _log(f"DO manifest figure set (a–d + composite) written "
         f"(a iid={len(iid)}, b nearUR={len(nur)}, c floor={len(floor)})")


def make_whiteness_manifest(cfg, out):
    """§1.1 -> §1.2 input contract: per-channel whitening-usability manifest +
    a column sidecar for innovation_unified_1min.parquet (which columns are a
    genuine white innovation vs an autocorrelated robust_z / censored fallback),
    so §1.2 branches its scoring instead of assuming whiteness."""
    if "arma_df" not in out or "cmp_df" not in out:
        return
    man = tables.whiteness_manifest(out["arma_df"], out["cmp_df"])
    tables.write_table(man, cfg["paths"]["table_root"], "whiteness_manifest")
    pq = Path(cfg["paths"]["parquet_root"])
    upath = pq / "innovation_unified_1min.parquet"
    if upath.exists():
        import pyarrow.parquet as paq
        cols = list(paq.ParquetFile(upath).schema.names)
        side = man[man.channel.isin(cols)][
            ["channel", "track", "whitened", "innov_kind", "scoring_mode"]]
        side.to_csv(pq / "innovation_unified_1min.columns.csv",
                    index=False, encoding="utf-8-sig")
    _log(f"whiteness_manifest ({int(man.whitened.sum())}/{len(man)} whitened) "
         f"+ unified sidecar written")


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
    out["kind_of"] = _kind_of(out)
    make_figures(cfg, out, quick=args.quick)
    make_decomposition_stacks(cfg, out, quick=args.quick)
    make_combined_figures(cfg, out, quick=args.quick)
    make_decomposition_overviews(cfg, out, quick=args.quick)
    make_combined_overviews(cfg, out, quick=args.quick)
    make_ribbon_overviews(cfg, out, quick=args.quick)
    make_acf_band_figures(cfg, out, quick=args.quick)
    make_do_manifest_figures(cfg, out)
    make_whiteness_manifest(cfg, out)

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
