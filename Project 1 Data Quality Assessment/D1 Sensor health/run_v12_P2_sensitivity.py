"""run_v12_P2_sensitivity.py — D1 v1.2-P2: Q_regime Reference Sensitivity Analysis

Variants (2×partial-factorial design):
  R30    : ref_days=30, w1_win=7,  ks_win=7   (current baseline, cached)
  R60    : ref_days=60, w1_win=7,  ks_win=7   (extend reference only)
  R90    : ref_days=90, w1_win=7,  ks_win=7   (long reference)
  R60W14 : ref_days=60, w1_win=14, ks_win=14  (isolate window effect)

Expert improvements over naive R30/R60/R90:
  1. 4th variant (R60W14) separates ref_days effect from window effect
  2. Common comparable period: all metrics computed from day+91 onwards
  3. Stability metric: Q_regime temporal std per channel per variant
  4. Spearman rank-order correlation matrix across variants
  5. Wilcoxon signed-rank test across channel pairs

Output:
  outputs/v12_P2/data/    — tidy CSV tables
  outputs/v12_P2/figures/ — 10 SCI-quality PNG (600 dpi)
  cache/regime_R*.pkl     — per-variant regime detector caches
"""
from __future__ import annotations
import sys, time, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

from src.config.loader import load_project_config
from src.detectors import TwoTierRegimeDetector
from src.mapping.mapper import apply_mapping
from src.aggregation.cooldown_state_machine import run_cooldown_state_machine, CooldownConfig
from src.aggregation.d1_aggregator import aggregate_d1_v11, extract_events, attribute_dominant_fault
from src.state.auxiliary_modules import PELTBatchCalibrator

# ─── Variant definitions ──────────────────────────────────────────────────────
VARIANTS = {
    "R30":    dict(ref_days=30,  w1_win_days=7,  ks_win_days=7),
    "R60":    dict(ref_days=60,  w1_win_days=7,  ks_win_days=7),
    "R90":    dict(ref_days=90,  w1_win_days=7,  ks_win_days=7),
    "R60W14": dict(ref_days=60,  w1_win_days=14, ks_win_days=14),
}
VARIANT_ORDER = ["R30", "R60", "R90", "R60W14"]
CACHE_DIR = _ROOT / "cache"

# Common comparable period: skip first 90 days to equalise training period
COMMON_SKIP_DAYS = 90

# ─── SCI style ────────────────────────────────────────────────────────────────
FONT_SZ  = 8
TITLE_SZ = 9
TICK_SZ  = 7
LW_MAIN  = 1.0
LW_AUX   = 0.6
LW_AXIS  = 0.8
DPI      = 600

WONG = {
    "black":  "#000000", "orange": "#E69F00", "sky":    "#56B4E9",
    "green":  "#009E73", "yellow": "#F0E442", "blue":   "#0072B2",
    "red":    "#D55E00", "pink":   "#CC79A7",
}
VAR_COLORS = {
    "R30":    WONG["blue"],
    "R60":    WONG["orange"],
    "R90":    WONG["red"],
    "R60W14": WONG["green"],
}
STATE_COLORS = {
    "Normal":            WONG["green"],
    "Refractory":        WONG["red"],
    "SustainedAnomaly":  WONG["sky"],
    "RecoveryCandidate": WONG["yellow"],
    "Recovered":         WONG["pink"],
}
STATE_ORDER = ["Normal", "Refractory", "SustainedAnomaly", "RecoveryCandidate", "Recovered"]


def sci_rc():
    plt.rcParams.update({
        "font.family":        "Arial",
        "font.size":          FONT_SZ,
        "axes.titlesize":     TITLE_SZ,
        "axes.labelsize":     FONT_SZ,
        "xtick.labelsize":    TICK_SZ,
        "ytick.labelsize":    TICK_SZ,
        "axes.linewidth":     LW_AXIS,
        "lines.linewidth":    LW_MAIN,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "figure.dpi":         100,
        "savefig.dpi":        DPI,
        "savefig.bbox":       "tight",
        "savefig.pad_inches": 0.05,
        "legend.fontsize":    TICK_SZ,
        "legend.frameon":     False,
    })


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def save_fig(fig, name, fig_dir):
    p = fig_dir / f"{name}.png"
    fig.savefig(p, format="png")
    plt.close(fig)
    print(f"  [saved] {p.name}")


# ─── Step 1: Load base data ───────────────────────────────────────────────────
def load_base_data():
    log("Loading base data (strict_v1_inputs + raw_hourly + v11_state)...")
    with open(_ROOT / "strict_v1_inputs.pkl", "rb") as f:
        v1 = pickle.load(f)
    with open(_ROOT / "raw_hourly.pkl", "rb") as f:
        raw = pickle.load(f)
    with open(_ROOT / "v11_state.pkl", "rb") as f:
        sp1 = pickle.load(f)

    cfg = load_project_config()
    return v1, raw, sp1, cfg


# ─── Step 2: Compute regime scores for each variant ──────────────────────────
def run_regime_variant(variant_name: str, params: dict,
                        resid_h: pd.DataFrame, channels: list,
                        mapping_cfg) -> dict:
    """Run TwoTierRegimeDetector with given params; return Q_regime + raw results."""
    cache_path = CACHE_DIR / f"regime_{variant_name}.pkl"
    if cache_path.exists():
        log(f"  [{variant_name}] Loading from cache: {cache_path.name}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log(f"  [{variant_name}] Running regime detector "
        f"(ref={params['ref_days']}d, w1_win={params['w1_win_days']}d, "
        f"ks_win={params['ks_win_days']}d) on {len(channels)} channels...")
    t = time.time()
    detector = TwoTierRegimeDetector(
        ref_days      = params["ref_days"],
        w1_win_days   = params["w1_win_days"],
        ks_win_days   = params["ks_win_days"],
        w1_update_h   = 6,
        ks_update_h   = 24,
        ks_alpha      = 0.001,
        n_bootstrap   = 100,
    )
    results = {}
    for i, c in enumerate(channels, 1):
        results[c] = detector.score(resid_h[c].rename(c))
        if i % 4 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} done")
    log(f"    [{time.time()-t:.1f}s] complete")

    # Apply mapping → Q_regime [1-5]
    Q_regime_dict = {}
    w1_norm_dict  = {}
    for c in channels:
        raw_score = results[c].raw_score.fillna(0.0)
        w1_norm_dict[c] = raw_score
        Q_regime_dict[c] = apply_mapping(
            raw_score.rename("w1_normalised"), mapping_cfg.regime)

    out = {
        "variant":       variant_name,
        "params":        params,
        "regime_results": results,
        "Q_regime":      pd.DataFrame(Q_regime_dict),
        "w1_norm":       pd.DataFrame(w1_norm_dict),
    }
    with open(cache_path, "wb") as f:
        pickle.dump(out, f)
    log(f"    Cached → {cache_path.name}")
    return out


# ─── Step 3: Run pipeline for each variant ───────────────────────────────────
def run_pipeline_for_variant(vname: str, Q_regime_df: pd.DataFrame,
                              v1: dict, raw: dict, sp1: dict,
                              cfg, cd_cfg: CooldownConfig) -> dict:
    """Run state machine + D1 aggregation using a given Q_regime variant."""
    log(f"  [{vname}] Running state machine + D1 aggregation...")
    channels     = sp1["scored_channels"]
    subs_v1      = v1["subs_v1"]
    detectors_raw = v1["detectors"]
    resid_h      = raw["resid_h"]
    rules        = cfg.rules
    sm_cfg       = cfg.state_machine

    # PELT results — reuse from sp1 (same data, same changepoints regardless of regime)
    pelt_results = sp1["pelt_results"]

    Q_drift_eff_dict = {}
    state_log_dict   = {}
    transitions_all  = []
    for c in channels:
        sc_df = detectors_raw.get("step_confirmed_flag")
        step_confirmed_c = sc_df[c] if sc_df is not None and c in sc_df.columns else None

        # Reindex Q_regime to match subs index
        Q_regime_c = Q_regime_df[c].reindex(subs_v1["Q_step"][c].index).ffill().bfill().clip(1, 5)

        Q_drift_eff_c, state_log_c, transitions_c = run_cooldown_state_machine(
            sensor_id         = c,
            Q_step            = subs_v1["Q_step"][c],
            Q_regime          = Q_regime_c,
            Q_drift           = subs_v1["Q_drift"][c],
            Q_freeze          = subs_v1["Q_freeze"][c],
            ks_stat           = detectors_raw["ks_statistic_hourly"][c],
            w1_norm           = detectors_raw["w1_normalised_hourly"][c],
            resid_h           = resid_h[c],
            pelt_changepoints = [ev["timestamp"] for ev in pelt_results[c]],
            step_confirmed    = step_confirmed_c,
            cfg               = cd_cfg,
        )
        Q_drift_eff_dict[c] = Q_drift_eff_c
        state_log_dict[c]   = state_log_c
        transitions_all.extend(transitions_c)

    # D1 aggregation
    agg_weights  = rules["aggregation"]["weights"]
    lambda_blend = rules["aggregation"]["lambda_blend"]
    idx = subs_v1["Q_step"].index
    D1_v11      = pd.DataFrame(index=idx)
    veto_logs   = {}
    subs_full   = {}
    for c in channels:
        Q_spike_c  = subs_v1["Q_spike"][c]
        Q_step_c   = subs_v1["Q_step"][c]
        Q_freeze_c = subs_v1["Q_freeze"][c]
        Q_regime_c = Q_regime_df[c].reindex(idx).ffill().bfill().clip(1, 5)
        Q_drift_eff_c = Q_drift_eff_dict[c]

        subs_full[c] = {
            "Q_spike":  Q_spike_c,  "Q_step":  Q_step_c,
            "Q_drift":  Q_drift_eff_c, "Q_freeze": Q_freeze_c,
            "Q_regime": Q_regime_c,
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
            veto3_step_thr        = rules["veto"]["veto3_step_threshold"],
            veto3_duration_h      = rules["veto"]["veto3_duration_h"],
            veto3_min_event_count = rules["veto"].get("veto3_min_event_count_36h", 6),
            veto3_cap             = rules["veto"]["veto3_cap"],
            sustained_cap         = sm_cfg["sustained_anomaly_cap"],
        )
        D1_v11[c] = D1_
        veto_logs[c] = vlog

    dominant = attribute_dominant_fault(subs_full)
    log(f"    [{vname}] D1 mean = {D1_v11.mean().mean():.3f}, "
        f"transitions = {len(transitions_all)}")
    return {
        "variant":         vname,
        "D1_v11":          D1_v11,
        "Q_drift_eff_dict": Q_drift_eff_dict,
        "state_log_dict":  state_log_dict,
        "veto_logs":       veto_logs,
        "transitions_all": transitions_all,
        "dominant":        dominant,
        "subs_full":       subs_full,
    }


# ─── Step 4: Collect summary metrics ─────────────────────────────────────────
def collect_metrics(variant_results: dict, Q_regime_variants: dict,
                    channels: list, t_start: pd.Timestamp) -> pd.DataFrame:
    """Build tidy summary DataFrame; aligned to common period (day+90 onward)."""
    t_common = t_start + pd.Timedelta(days=COMMON_SKIP_DAYS)
    rows = []
    for vname in VARIANT_ORDER:
        vr = variant_results[vname]
        qr = Q_regime_variants[vname]["Q_regime"]
        for c in channels:
            qrc = qr[c].loc[qrc.index >= t_common] if (qrc := qr[c]).index[0] < t_common else qrc
            qrc = qr[c][qr[c].index >= t_common]
            d1c = vr["D1_v11"][c][vr["D1_v11"][c].index >= t_common]
            slc = vr["state_log_dict"][c][vr["state_log_dict"][c].index >= t_common]
            vlc = vr["veto_logs"][c][vr["veto_logs"][c].index >= t_common]

            state_pcts = slc["state_name"].value_counts(normalize=True) * 100
            rows.append({
                "variant": vname,
                "channel": c,
                "ref_days":      VARIANTS[vname]["ref_days"],
                "w1_win_days":   VARIANTS[vname]["w1_win_days"],
                "ks_win_days":   VARIANTS[vname]["ks_win_days"],
                # Q_regime stats
                "Qreg_mean":     qrc.mean(),
                "Qreg_std":      qrc.std(),
                "Qreg_median":   qrc.median(),
                "Qreg_p05":      qrc.quantile(0.05),
                "Qreg_p95":      qrc.quantile(0.95),
                "Qreg_lt2_pct":  (qrc < 2.0).mean() * 100,
                "Qreg_lt3_pct":  (qrc < 3.0).mean() * 100,
                # Veto
                "veto_regime_pct":  vlc["veto_regime"].mean() * 100 if "veto_regime" in vlc.columns else 0,
                "cooldown_pct":     vlc["cooldown_active"].mean() * 100,
                "sustained_pct":    vlc["sustained_active"].mean() * 100,
                # State
                "Normal_pct":           state_pcts.get("Normal", 0),
                "Refractory_pct":       state_pcts.get("Refractory", 0),
                "SustainedAnomaly_pct": state_pcts.get("SustainedAnomaly", 0),
                "RecoveryCandidate_pct":state_pcts.get("RecoveryCandidate", 0),
                "Recovered_pct":        state_pcts.get("Recovered", 0),
                # D1
                "D1_mean":   d1c.mean(),
                "D1_std":    d1c.std(),
                "D1_median": d1c.median(),
            })
    return pd.DataFrame(rows)


# ─── Step 5: Spearman rank correlation across variants ───────────────────────
def compute_rank_correlation(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation of per-channel D1_mean rankings across variants."""
    pivot = metrics_df.pivot(index="channel", columns="variant", values="D1_mean")
    corr_mat = pivot.corr(method="spearman")
    return corr_mat


# ─── Figures ──────────────────────────────────────────────────────────────────
def fig1_variant_overview(fig_dir, data_dir):
    """Parameter table: all 4 variants with design rationale."""
    rows = [
        ("R30",    30,  7,  7,  "Current baseline (cached)",
         "Establishes short-term reference; reactive to early anomalies"),
        ("R60",    60,  7,  7,  "Extend reference only",
         "Tests effect of doubling reference period, window unchanged"),
        ("R90",    90,  7,  7,  "Long reference period",
         "Stable reference using ~35% of total 255-day dataset"),
        ("R60W14", 60, 14, 14, "Isolate window effect",
         "Same ref as R60 but wider detection window; separates interactions"),
    ]
    df = pd.DataFrame(rows, columns=["Variant", "ref_days", "w1_win_days",
                                      "ks_win_days", "Design role", "Rationale"])
    df.to_csv(data_dir / "variant_definitions.csv", index=False)

    sci_rc()
    fig, ax = plt.subplots(figsize=(10, 2.4))
    ax.axis("off")
    tbl = ax.table(cellText=df.values, colLabels=df.columns,
                   loc="center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(TICK_SZ)
    tbl.scale(1, 1.6)
    for (r, c_), cell in tbl.get_celld().items():
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_facecolor("#2166AC")
            cell.set_text_props(color="white", fontsize=FONT_SZ, fontweight="bold")
        elif r % 2 == 1:
            cell.set_facecolor("#EFF3FF")
        else:
            cell.set_facecolor("#FFFFFF")
        if r > 0:
            vname = df.iloc[r - 1]["Variant"]
            cell.set_edgecolor(VAR_COLORS.get(vname, "gray"))
    ax.set_title("D1 v1.2-P2 Sensitivity Variants — 2×Partial-Factorial Design",
                 fontsize=TITLE_SZ, fontweight="bold", pad=6)
    save_fig(fig, "fig01_variant_overview", fig_dir)


def fig2_qregime_mean(metrics_df, channels, fig_dir, data_dir):
    """Q_regime mean per channel per variant — grouped bar."""
    piv = metrics_df.pivot(index="channel", columns="variant", values="Qreg_mean")
    piv.to_csv(data_dir / "fig_qregime_mean.csv")

    sci_rc()
    fig, ax = plt.subplots(figsize=(9.5, 3.2))
    x = np.arange(len(channels))
    w = 0.2
    for i, vname in enumerate(VARIANT_ORDER):
        vals = [piv.loc[c, vname] if c in piv.index else np.nan for c in channels]
        ax.bar(x + (i - 1.5) * w, vals, width=w, color=VAR_COLORS[vname],
               alpha=0.8, label=vname)
    ax.axhline(3.0, color="gray", lw=LW_AUX, ls=":", alpha=0.6)
    ax.axhline(2.0, color="gray", lw=LW_AUX, ls="--", alpha=0.6, label="Veto threshold")
    ax.set_xticks(x)
    ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax.set_ylabel("Q_regime mean score", fontsize=FONT_SZ)
    ax.set_ylim(1, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.legend(fontsize=TICK_SZ, ncol=5)
    ax.set_title("Q_regime Mean Score Per Channel — All Variants (common period)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig02_qregime_mean", fig_dir)


def fig3_qregime_stability(metrics_df, channels, fig_dir, data_dir):
    """Q_regime temporal std per channel — stability comparison."""
    piv = metrics_df.pivot(index="channel", columns="variant", values="Qreg_std")
    piv.to_csv(data_dir / "fig_qregime_stability.csv")

    sci_rc()
    fig, ax = plt.subplots(figsize=(9.5, 3.2))
    x = np.arange(len(channels))
    w = 0.2
    for i, vname in enumerate(VARIANT_ORDER):
        vals = [piv.loc[c, vname] if c in piv.index else np.nan for c in channels]
        ax.bar(x + (i - 1.5) * w, vals, width=w, color=VAR_COLORS[vname],
               alpha=0.8, label=vname)
    ax.set_xticks(x)
    ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax.set_ylabel("Q_regime temporal std (score)", fontsize=FONT_SZ)
    ax.legend(fontsize=TICK_SZ, ncol=4)
    ax.set_title("Q_regime Temporal Stability (Std) Per Channel — Larger = Less Stable",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig03_qregime_stability", fig_dir)


def fig4_qregime_lt2_heatmap(metrics_df, channels, fig_dir, data_dir):
    """Q_regime < 2.0 proportion heatmap (channels × variants)."""
    piv = metrics_df.pivot(index="channel", columns="variant", values="Qreg_lt2_pct")
    piv = piv[VARIANT_ORDER].reindex(channels)
    piv.to_csv(data_dir / "fig_qregime_lt2_heatmap.csv")

    sci_rc()
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(piv.values, cmap=plt.cm.Reds, vmin=0, vmax=50, aspect="auto")
    ax.set_xticks(range(len(VARIANT_ORDER)))
    ax.set_xticklabels(VARIANT_ORDER, fontsize=TICK_SZ)
    ax.set_yticks(range(len(channels)))
    ax.set_yticklabels(channels, fontsize=TICK_SZ)
    for i in range(len(channels)):
        for j in range(len(VARIANT_ORDER)):
            v = piv.values[i, j]
            ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                    fontsize=TICK_SZ,
                    color="white" if v > 30 else "black")
    plt.colorbar(im, ax=ax, shrink=0.85, label="Q_regime < 2.0 (%)")
    ax.set_xlabel("Variant", fontsize=FONT_SZ)
    ax.set_ylabel("Channel", fontsize=FONT_SZ)
    ax.set_title("Q_regime < 2.0 Proportion Heatmap (Veto Activation Risk)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig04_qregime_lt2_heatmap", fig_dir)


def fig5_veto_regime_rate(metrics_df, channels, fig_dir, data_dir):
    """Regime veto activation rate + cooldown rate comparison."""
    piv_veto = metrics_df.pivot(index="channel", columns="variant", values="veto_regime_pct")
    piv_cool = metrics_df.pivot(index="channel", columns="variant", values="cooldown_pct")
    piv_veto.to_csv(data_dir / "fig_veto_regime_rate.csv")

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2), sharey=False)
    x = np.arange(len(channels))
    w = 0.2

    for i, vname in enumerate(VARIANT_ORDER):
        vals_v = [piv_veto.loc[c, vname] if c in piv_veto.index else 0 for c in channels]
        ax1.bar(x + (i - 1.5) * w, vals_v, width=w, color=VAR_COLORS[vname],
                alpha=0.8, label=vname)
    ax1.set_xticks(x)
    ax1.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax1.set_ylabel("Regime veto activation (%)", fontsize=FONT_SZ)
    ax1.legend(fontsize=TICK_SZ, ncol=2)
    ax1.set_title("Regime Veto Activation Rate Per Channel",
                  fontsize=FONT_SZ, fontweight="bold")

    for i, vname in enumerate(VARIANT_ORDER):
        vals_c = [piv_cool.loc[c, vname] if c in piv_cool.index else 0 for c in channels]
        ax2.bar(x + (i - 1.5) * w, vals_c, width=w, color=VAR_COLORS[vname],
                alpha=0.8, label=vname)
    ax2.set_xticks(x)
    ax2.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax2.set_ylabel("Refractory (cooldown) activation (%)", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ, ncol=2)
    ax2.set_title("Refractory Activation Rate Per Channel",
                  fontsize=FONT_SZ, fontweight="bold")

    fig.suptitle("Veto & Refractory Activation Rate Comparison Across Variants",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig05_veto_regime_rate", fig_dir)


def fig6_d1_total_change(metrics_df, channels, fig_dir, data_dir):
    """D1 total mean change relative to R30 baseline."""
    piv = metrics_df.pivot(index="channel", columns="variant", values="D1_mean")
    delta = piv.subtract(piv["R30"], axis=0)
    delta.to_csv(data_dir / "fig_d1_delta_vs_r30.csv")
    piv.to_csv(data_dir / "fig_d1_mean_all_variants.csv")

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))

    x = np.arange(len(channels))
    w = 0.2
    for i, vname in enumerate(VARIANT_ORDER):
        vals = [piv.loc[c, vname] if c in piv.index else np.nan for c in channels]
        ax1.bar(x + (i - 1.5) * w, vals, width=w, color=VAR_COLORS[vname],
                alpha=0.8, label=vname)
    ax1.axhline(3.0, color="gray", lw=LW_AUX, ls=":", alpha=0.6)
    ax1.set_xticks(x)
    ax1.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax1.set_ylabel("D1 mean score", fontsize=FONT_SZ)
    ax1.set_ylim(1, 5)
    ax1.legend(fontsize=TICK_SZ, ncol=2)
    ax1.set_title("D1 Mean Score Per Variant", fontsize=FONT_SZ, fontweight="bold")

    for i, vname in enumerate(VARIANT_ORDER[1:], 1):
        vals_d = [delta.loc[c, vname] if c in delta.index else 0 for c in channels]
        ax2.bar(x + (i - 2) * w, vals_d, width=w, color=VAR_COLORS[vname],
                alpha=0.8, label=f"{vname}−R30")
    ax2.axhline(0, color="black", lw=LW_AUX, ls="-")
    ax2.set_xticks(x)
    ax2.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax2.set_ylabel("ΔD1 vs R30 baseline", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ, ncol=2)
    ax2.set_title("D1 Change Relative to R30 Baseline",
                  fontsize=FONT_SZ, fontweight="bold")

    fig.suptitle("D1 Score Comparison — Reference Sensitivity (v1.2-P2)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig06_d1_total_change", fig_dir)


def fig7_key_channel_timeseries(variant_results, Q_regime_variants,
                                 channels, fig_dir, data_dir):
    """Q_regime and D1 time series for 3 key channels across all variants."""
    key_chs = ["DO_2_3", "DO_1_4", "ORP_1_3"]

    sci_rc()
    fig = plt.figure(figsize=(12, 7.5))
    gs  = GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.3)

    ts_rows = []
    for row_i, c in enumerate(key_chs):
        ax_d1 = fig.add_subplot(gs[row_i, 0])
        ax_qr = fig.add_subplot(gs[row_i, 1])

        for vname in VARIANT_ORDER:
            vr = variant_results[vname]
            qr = Q_regime_variants[vname]["Q_regime"][c]
            d1 = vr["D1_v11"][c]
            ax_d1.plot(d1.index, d1.values, color=VAR_COLORS[vname],
                       lw=0.8, alpha=0.8, label=vname)
            ax_qr.plot(qr.index, qr.values, color=VAR_COLORS[vname],
                       lw=0.8, alpha=0.8, label=vname)
            for t in d1.index:
                ts_rows.append({"channel": c, "variant": vname, "time": t,
                                 "D1": d1.get(t, np.nan),
                                 "Q_regime": qr.get(t, np.nan)})

        ax_d1.axhline(3.0, color="gray", lw=LW_AUX, ls=":", alpha=0.5)
        ax_d1.set_ylabel("D1 score", fontsize=FONT_SZ)
        ax_d1.set_ylim(1, 5)
        ax_d1.set_title(f"{c} — D1", fontsize=FONT_SZ, fontweight="bold")
        if row_i == 0:
            ax_d1.legend(fontsize=TICK_SZ, loc="lower right", ncol=2)
        ax_d1.tick_params(axis="x", labelsize=TICK_SZ, rotation=20)

        ax_qr.axhline(2.0, color=WONG["red"], lw=LW_AUX, ls="--", alpha=0.7,
                      label="Veto threshold = 2.0")
        ax_qr.axhline(3.0, color="gray",      lw=LW_AUX, ls=":",  alpha=0.5)
        ax_qr.set_ylabel("Q_regime score", fontsize=FONT_SZ)
        ax_qr.set_ylim(1, 5)
        ax_qr.set_title(f"{c} — Q_regime", fontsize=FONT_SZ, fontweight="bold")
        if row_i == 0:
            ax_qr.legend(fontsize=TICK_SZ, loc="lower right", ncol=2)
        ax_qr.tick_params(axis="x", labelsize=TICK_SZ, rotation=20)

    pd.DataFrame(ts_rows).to_csv(data_dir / "fig_key_channel_timeseries.csv", index=False)
    fig.suptitle("Key Channel Time Series — Q_regime & D1 Across All Variants",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig07_key_channel_timeseries", fig_dir)


def fig8_qregime_violin(Q_regime_variants, channels, fig_dir, data_dir):
    """Q_regime score distribution violin plot across all variants and channels."""
    rows = []
    for vname in VARIANT_ORDER:
        qr = Q_regime_variants[vname]["Q_regime"]
        for c in channels:
            for v in qr[c].dropna().values:
                rows.append({"variant": vname, "channel": c, "Q_regime": v})
    pd.DataFrame(rows).to_csv(data_dir / "fig_qregime_violin.csv", index=False)

    sci_rc()
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.5), sharey=True)
    for ax, vname in zip(axes, VARIANT_ORDER):
        qr = Q_regime_variants[vname]["Q_regime"]
        data_list = [qr[c].dropna().values for c in channels]
        bp = ax.violinplot(data_list, positions=range(len(channels)),
                           showmedians=True, showextrema=False, widths=0.7)
        for pc in bp["bodies"]:
            pc.set_facecolor(VAR_COLORS[vname])
            pc.set_alpha(0.5)
        bp["cmedians"].set_color(VAR_COLORS[vname])
        bp["cmedians"].set_lw(LW_MAIN)
        ax.axhline(2.0, color=WONG["red"], lw=LW_AUX, ls="--", alpha=0.7)
        ax.axhline(3.0, color="gray",      lw=LW_AUX, ls=":",  alpha=0.5)
        ax.set_xticks(range(len(channels)))
        ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=5)
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_title(vname, fontsize=FONT_SZ, fontweight="bold",
                     color=VAR_COLORS[vname])
    axes[0].set_ylabel("Q_regime score", fontsize=FONT_SZ)
    fig.suptitle("Q_regime Score Distribution Per Channel — All Variants (Violin)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig08_qregime_violin", fig_dir)


def fig9_rank_correlation(metrics_df, fig_dir, data_dir):
    """Spearman rank correlation matrix of channel D1_mean rankings across variants."""
    corr = compute_rank_correlation(metrics_df)
    corr.to_csv(data_dir / "fig_rank_correlation.csv")

    # Wilcoxon test: R30 vs each other variant across channels
    piv = metrics_df.pivot(index="channel", columns="variant", values="D1_mean")
    wilcox_rows = []
    for vname in VARIANT_ORDER[1:]:
        stat, p = stats.wilcoxon(piv["R30"].values, piv[vname].values,
                                 alternative="two-sided")
        wilcox_rows.append({"comparison": f"R30 vs {vname}", "statistic": stat, "p_value": p})
    wilcox_df = pd.DataFrame(wilcox_rows)
    wilcox_df.to_csv(data_dir / "fig_wilcoxon_test.csv", index=False)

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.0))

    # Correlation heatmap
    im = ax1.imshow(corr.values, cmap=plt.cm.RdYlGn, vmin=0.8, vmax=1.0, aspect="auto")
    ax1.set_xticks(range(len(VARIANT_ORDER)))
    ax1.set_yticks(range(len(VARIANT_ORDER)))
    ax1.set_xticklabels(VARIANT_ORDER, fontsize=TICK_SZ)
    ax1.set_yticklabels(VARIANT_ORDER, fontsize=TICK_SZ)
    for i in range(len(VARIANT_ORDER)):
        for j in range(len(VARIANT_ORDER)):
            ax1.text(j, i, f"{corr.values[i, j]:.3f}", ha="center", va="center",
                     fontsize=TICK_SZ, color="black")
    plt.colorbar(im, ax=ax1, shrink=0.85, label="Spearman ρ")
    ax1.set_title("Channel Ranking Consistency\n(Spearman ρ of D1_mean)",
                  fontsize=FONT_SZ, fontweight="bold")

    # Wilcoxon p-values
    colors = ["green" if p > 0.05 else "red" for p in wilcox_df["p_value"]]
    ax2.barh(range(len(wilcox_df)), -np.log10(wilcox_df["p_value"].clip(1e-10)),
             color=colors, alpha=0.7)
    ax2.axvline(-np.log10(0.05), color="gray", lw=LW_AUX, ls="--",
                label="p = 0.05")
    ax2.set_yticks(range(len(wilcox_df)))
    ax2.set_yticklabels(wilcox_df["comparison"].values, fontsize=TICK_SZ)
    ax2.set_xlabel("−log₁₀(p-value)", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ)
    ax2.set_title("Wilcoxon Signed-Rank Test\nvs R30 Baseline (p > 0.05 = not sig.)",
                  fontsize=FONT_SZ, fontweight="bold")

    for i, (_, row) in enumerate(wilcox_df.iterrows()):
        ax2.text(-np.log10(max(row["p_value"], 1e-10)) + 0.05, i,
                 f"p={row['p_value']:.3f}", va="center", fontsize=TICK_SZ)

    fig.suptitle("Cross-Variant Consistency: Rank Correlation & Significance Test",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig09_rank_correlation", fig_dir)


def fig10_summary_radar(metrics_df, fig_dir, data_dir):
    """Summary comparison: global mean metrics per variant (bar chart summary)."""
    global_summary = metrics_df.groupby("variant").agg(
        Qreg_mean=("Qreg_mean", "mean"),
        Qreg_std=("Qreg_std", "mean"),
        Qreg_lt2_pct=("Qreg_lt2_pct", "mean"),
        veto_regime_pct=("veto_regime_pct", "mean"),
        cooldown_pct=("cooldown_pct", "mean"),
        D1_mean=("D1_mean", "mean"),
        D1_std=("D1_std", "mean"),
        Normal_pct=("Normal_pct", "mean"),
        Refractory_pct=("Refractory_pct", "mean"),
    ).reindex(VARIANT_ORDER)
    global_summary.to_csv(data_dir / "fig_global_summary.csv")

    sci_rc()
    fig, axes = plt.subplots(2, 4, figsize=(12, 5.5))
    axes = axes.flatten()
    metrics_plot = [
        ("D1_mean",        "D1 Mean Score",             (1, 5)),
        ("Qreg_mean",      "Q_regime Mean",             (1, 5)),
        ("Qreg_std",       "Q_regime Std (Stability)",  (0, 1.5)),
        ("Qreg_lt2_pct",   "Q_regime < 2.0 (%)",        (0, 40)),
        ("veto_regime_pct","Regime Veto Rate (%)",       (0, 40)),
        ("cooldown_pct",   "Refractory Rate (%)",        (0, 60)),
        ("Normal_pct",     "Normal State (%)",           (0, 100)),
        ("Refractory_pct", "Refractory State (%)",       (0, 60)),
    ]
    for ax, (col, label, ylim) in zip(axes, metrics_plot):
        vals = [global_summary.loc[v, col] for v in VARIANT_ORDER]
        bars = ax.bar(VARIANT_ORDER, vals,
                      color=[VAR_COLORS[v] for v in VARIANT_ORDER], alpha=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01 * ylim[1],
                    f"{val:.2f}", ha="center", va="bottom", fontsize=5)
        ax.set_ylim(*ylim)
        ax.set_ylabel(label, fontsize=TICK_SZ)
        ax.set_xticklabels(VARIANT_ORDER, fontsize=TICK_SZ, rotation=20)
        ax.set_title(label, fontsize=TICK_SZ, fontweight="bold")

    fig.suptitle("Global Summary — All Metrics Across Variants (v1.2-P2)",
                 fontsize=TITLE_SZ, fontweight="bold")
    plt.tight_layout()
    save_fig(fig, "fig10_global_summary", fig_dir)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    t_total = time.time()
    out_dir  = _ROOT / "outputs" / "v12_P2"
    fig_dir  = out_dir / "figures"
    data_dir = out_dir / "data"
    fig_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("D1 v1.2-P2: Q_regime Reference Sensitivity Analysis")
    log(f"Variants: {list(VARIANTS.keys())}")
    log(f"Common period skip: {COMMON_SKIP_DAYS} days")
    log(f"Output: {out_dir}")
    log("=" * 70)

    # Load base data
    v1, raw, sp1, cfg = load_base_data()
    channels = sp1["scored_channels"]
    resid_h  = raw["resid_h"]
    t_start  = resid_h.index[0]
    log(f"Data: {len(channels)} channels, "
        f"{resid_h.index[0].date()} → {resid_h.index[-1].date()}")

    # Build CooldownConfig from current (P1) state_machine.yaml
    sm_cfg = cfg.state_machine
    cd_cfg = CooldownConfig(
        step_refractory_h           = sm_cfg["refractory"]["step_h"],
        regime_refractory_h         = sm_cfg["refractory"]["regime_h"],
        drift_neutral_score         = sm_cfg["refractory"]["drift_neutral_score"],
        min_event_separation_h      = sm_cfg["event_uniqueness"]["min_separation_h"],
        magnitude_change_pct        = sm_cfg["event_uniqueness"]["magnitude_change_pct"],
        candidate_search_after_step = tuple(sm_cfg["sustained_anomaly"]["candidate_window_search"]["step_after_h"]),
        candidate_search_after_regime = tuple(sm_cfg["sustained_anomaly"]["candidate_window_search"]["regime_after_h"]),
        stable_window_h             = sm_cfg["sustained_anomaly"]["candidate_window_search"]["stable_window_h"],
        drift_slope_threshold       = sm_cfg["sustained_anomaly"]["baseline_init"]["drift_slope_threshold"],
        thaw_duration_h             = sm_cfg["sustained_anomaly"]["thaw"]["duration_h"],
        enter_recov_q_step          = sm_cfg["recovery"]["enter_thresholds"]["Q_step_min"],
        enter_recov_q_regime        = sm_cfg["recovery"]["enter_thresholds"]["Q_regime_min"],
        enter_recov_q_freeze        = sm_cfg["recovery"]["enter_thresholds"]["Q_freeze_min"],
        residual_z_max              = sm_cfg["recovery"]["residual_check"]["max_z_score"],
        w1_norm_max                 = sm_cfg["recovery"]["residual_check"]["max_w1_norm"],
        min_recovery_streak_h       = sm_cfg["recovery"]["min_streak_h"],
        sustained_anomaly_cap       = sm_cfg["sustained_anomaly_cap"],
    )

    # ── Run regime detector for each variant
    log("\n[A] Running regime detector for all variants...")
    Q_regime_variants = {}
    for vname, params in VARIANTS.items():
        # R30 baseline: reuse existing cache/regime_results.pkl if R30 cache missing
        if vname == "R30":
            r30_cache = CACHE_DIR / "regime_R30.pkl"
            if not r30_cache.exists():
                src = CACHE_DIR / "regime_results.pkl"
                if src.exists():
                    log(f"  [R30] Copying from regime_results.pkl → regime_R30.pkl...")
                    with open(src, "rb") as f:
                        raw_cache = pickle.load(f)
                    # raw_cache is a dict {c: DetectorResult}
                    # Apply mapping to get Q_regime
                    Q_regime_dict = {}
                    w1_norm_dict  = {}
                    for c in channels:
                        raw_score = raw_cache[c].raw_score.fillna(0.0)
                        w1_norm_dict[c]  = raw_score
                        Q_regime_dict[c] = apply_mapping(
                            raw_score.rename("w1_normalised"), cfg.mapping.regime)
                    out_r30 = {
                        "variant": "R30", "params": params,
                        "regime_results": raw_cache,
                        "Q_regime": pd.DataFrame(Q_regime_dict),
                        "w1_norm":  pd.DataFrame(w1_norm_dict),
                    }
                    with open(r30_cache, "wb") as f:
                        pickle.dump(out_r30, f)
                    Q_regime_variants["R30"] = out_r30
                else:
                    Q_regime_variants["R30"] = run_regime_variant(
                        "R30", params, resid_h[channels], channels, cfg.mapping)
            else:
                with open(r30_cache, "rb") as f:
                    Q_regime_variants["R30"] = pickle.load(f)
                log(f"  [R30] Loaded from cache")
        else:
            Q_regime_variants[vname] = run_regime_variant(
                vname, params, resid_h[channels], channels, cfg.mapping)

    # ── Run pipeline (state machine + aggregation) for each variant
    log("\n[B] Running state machine + D1 aggregation for all variants...")
    variant_results = {}
    for vname in VARIANT_ORDER:
        variant_results[vname] = run_pipeline_for_variant(
            vname, Q_regime_variants[vname]["Q_regime"],
            v1, raw, sp1, cfg, cd_cfg)

    # ── Collect metrics
    log("\n[C] Collecting summary metrics (common period from day +90)...")
    metrics_df = collect_metrics(variant_results, Q_regime_variants, channels, t_start)
    metrics_df.to_csv(data_dir / "metrics_all_variants.csv", index=False)
    log(f"  metrics table: {metrics_df.shape}")

    # Print summary
    gsum = metrics_df.groupby("variant").agg(
        D1_mean=("D1_mean", "mean"),
        Qreg_mean=("Qreg_mean", "mean"),
        Qreg_lt2_pct=("Qreg_lt2_pct", "mean"),
        cooldown_pct=("cooldown_pct", "mean"),
    ).reindex(VARIANT_ORDER).round(3)
    print("\n[Summary] Global means across all channels (common period):")
    print(gsum.to_string())

    # ── Save all variant results
    log("\n[D] Saving variant state files...")
    p2_state = {
        "variant_results":    variant_results,
        "Q_regime_variants":  {v: {"Q_regime": Q_regime_variants[v]["Q_regime"],
                                    "params":   Q_regime_variants[v]["params"]}
                               for v in VARIANT_ORDER},
        "metrics_df":         metrics_df,
        "channels":           channels,
        "t_start":            t_start,
    }
    pkl_out = _ROOT / "v12_P2_state.pkl"
    with open(pkl_out, "wb") as f:
        pickle.dump(p2_state, f)
    log(f"  Saved {pkl_out} ({pkl_out.stat().st_size/1e6:.1f} MB)")

    # ── Generate figures
    log("\n[E] Generating figures...")
    sci_rc()
    fig1_variant_overview(fig_dir, data_dir)
    fig2_qregime_mean(metrics_df, channels, fig_dir, data_dir)
    fig3_qregime_stability(metrics_df, channels, fig_dir, data_dir)
    fig4_qregime_lt2_heatmap(metrics_df, channels, fig_dir, data_dir)
    fig5_veto_regime_rate(metrics_df, channels, fig_dir, data_dir)
    fig6_d1_total_change(metrics_df, channels, fig_dir, data_dir)
    fig7_key_channel_timeseries(variant_results, Q_regime_variants, channels, fig_dir, data_dir)
    fig8_qregime_violin(Q_regime_variants, channels, fig_dir, data_dir)
    fig9_rank_correlation(metrics_df, fig_dir, data_dir)
    fig10_summary_radar(metrics_df, fig_dir, data_dir)

    log(f"\n{'='*70}")
    log(f"P2 sensitivity analysis complete. Total time: {(time.time()-t_total)/60:.1f} min")
    log(f"  Figures: {fig_dir}")
    log(f"  Data:    {data_dir}")
    log(f"{'='*70}")


if __name__ == "__main__":
    main()
