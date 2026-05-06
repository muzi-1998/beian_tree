"""src/outputs/figure_strict_v1.py
Two strict-V1 specific figures showcasing the spec-compliance fixes:
    Fig9 — Harmonic decomposition demonstration (signal / seasonal / baseline / residual)
    Fig10 — Two-tier regime detector breakdown (Tier-1 only vs Tier-2 only vs BOTH)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

C = {"blue": "#2166AC", "red": "#D6604D", "green": "#4DAC26",
     "orange": "#F4A582", "purple": "#762A83", "gray": "#878787",
     "teal": "#1B7837", "amber": "#E08214"}


def fig9_harmonic_demo(R, out_path: Path,
                        sample_sensors=("DO_2_3", "ORP_1_1", "QR_1")):
    """Visualise harmonic decomposition: signal vs (baseline + seasonal) vs residual."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "savefig.dpi": 300})

    n = len(sample_sensors)
    fig, axes = plt.subplots(n, 2, figsize=(13, 2.6 * n),
                              gridspec_kw={"width_ratios": [3, 1]})

    # Use 14-day window for visual clarity
    ts0 = R["df_min"].index[7 * 1440]   # day 8 onwards
    ts1 = ts0 + pd.Timedelta(days=14)

    plot_data = []
    for row, c in enumerate(sample_sensors):
        if c not in R["df_min"].columns: continue
        sig = R["df_min"][c].loc[ts0:ts1]
        base = R["baseline_min"][c].loc[ts0:ts1]
        seas = R["seasonal_min"][c].loc[ts0:ts1]
        resid = R["resid_min"][c].loc[ts0:ts1]

        ax = axes[row, 0]
        ax.plot(sig.index, sig.values, color=C["gray"], lw=0.6, alpha=0.85,
                label="Raw signal")
        ax.plot(base.index, (base + seas).values, color=C["red"], lw=1.2,
                label="Baseline + Seasonal (harmonic fit)")
        ax.set_ylabel(c)
        ax.legend(fontsize=7, loc="upper right", framealpha=0.9)
        ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        if row == 0:
            ax.set_title("(a) Raw signal & harmonic fit (14-day window)",
                          fontsize=10, fontweight="bold", loc="left")

        ax2 = axes[row, 1]
        ax2.hist(resid.dropna().values, bins=60, color=C["blue"],
                 alpha=0.75, edgecolor="black", lw=0.4)
        ax2.set_ylabel("count"); ax2.set_xlabel("residual")
        if row == 0:
            ax2.set_title("(b) Residual distribution\n(after harmonic deperiodisation)",
                          fontsize=10, fontweight="bold", loc="left")
        ax2.text(0.02, 0.95,
                 f"σ={resid.std():.3f}\nautocorr@24h={resid.autocorr(lag=1440):.2f}",
                 transform=ax2.transAxes, va="top", fontsize=7,
                 bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))

        plot_data.append(pd.DataFrame({
            "sensor_id": c, "ts": sig.index,
            "signal": sig.values,
            "baseline": base.values,
            "seasonal": seas.values,
            "residual": resid.values,
        }))

    fig.suptitle("Fig. 9 — Harmonic Decomposition (spec-compliant deperiodisation)\n"
                 "Daily T=1440min + Weekly T=10080min, 3 harmonics each, fit on first 30 days",
                 fontsize=11, fontweight="bold", y=1.0)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, pd.concat(plot_data, ignore_index=True)


def fig10_two_tier_regime(R, out_path: Path):
    """Stacked bar: Tier-1 only vs Tier-2 only vs BOTH per channel.

    Demonstrates the two-tier joint requirement defined in spec §9.
    """
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "savefig.dpi": 300})

    chans = list(R["D1_h"].columns)
    n_h = len(R["D1_h"])
    rows = []
    for c in chans:
        md = R["regime_results"][c].metadata
        t1 = md.get("tier1_only_count", 0)
        t2 = md.get("tier2_only_count", 0)
        bo = md.get("both_tiers_count", 0)
        rows.append({"sensor_id": c,
                     "tier1_only_pct": 100 * t1 / n_h,
                     "tier2_only_pct": 100 * t2 / n_h,
                     "both_tiers_pct": 100 * bo / n_h,
                     "neither_pct": 100 * (n_h - t1 - t2 - bo) / n_h,
                     "w1norm_mean": float(md["w1_norm_series"].mean()),
                     "w1norm_p95":  float(md["w1_norm_series"].quantile(0.95))})
    df = pd.DataFrame(rows)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7),
                              gridspec_kw={"height_ratios": [2, 1]})

    # (a) Stacked bar
    ax = axes[0]
    x = np.arange(len(chans))
    ax.bar(x, df["both_tiers_pct"], color=C["red"], alpha=0.85,
           label="BOTH tiers (true regime)")
    ax.bar(x, df["tier1_only_pct"], bottom=df["both_tiers_pct"],
           color=C["amber"], alpha=0.85,
           label="Tier-1 only (W1 alone, sustained drift but no KS)")
    ax.bar(x, df["tier2_only_pct"],
           bottom=df["both_tiers_pct"] + df["tier1_only_pct"],
           color=C["blue"], alpha=0.7,
           label="Tier-2 only (KS alone, transient with no W1)")
    ax.bar(x, df["neither_pct"],
           bottom=df["both_tiers_pct"] + df["tier1_only_pct"] + df["tier2_only_pct"],
           color="#E5E7E9", alpha=0.6, label="Neither (normal)")
    ax.set_xticks(x); ax.set_xticklabels(chans, rotation=90, fontsize=8)
    ax.set_ylabel("Time fraction (%)")
    ax.set_title("Fig. 10a — Two-tier regime activation breakdown per channel\n"
                 "(spec §9: only BOTH-tiers concurrent counts as a true regime event)",
                 fontsize=10, fontweight="bold", loc="left")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.20),
              ncol=4, frameon=False)
    ax.set_ylim(0, 100)

    # (b) W1_normalised mean per channel (with p95 error bars)
    ax = axes[1]
    ax.bar(x, df["w1norm_mean"], color=C["teal"], alpha=0.7,
           yerr=(df["w1norm_p95"] - df["w1norm_mean"]).clip(lower=0),
           capsize=2, label="mean W1_norm (bar) ± p95 (error)")
    ax.axhline(3.0, color=C["red"], ls="--", lw=0.8, alpha=0.7,
               label="threshold for Tier-1 (W1_norm=3)")
    ax.set_xticks(x); ax.set_xticklabels(chans, rotation=90, fontsize=8)
    ax.set_ylabel("W₁ / bootstrap baseline")
    ax.set_title("Fig. 10b — Tier-1 W1_normalised distribution per channel",
                 fontsize=10, fontweight="bold", loc="left")
    ax.legend(fontsize=8, frameon=False)

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, df


def fig11_pls_peer_audit(R, out_path: Path):
    """Show engineered peer rules visually."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "savefig.dpi": 300})
    chans = list(R["D1_h"].columns)
    matrix = np.zeros((len(chans), len(chans)))
    for i, target in enumerate(chans):
        peers = R["drift_results"][target].metadata.get("peer_cols", [])
        for p in peers:
            if p in chans:
                j = chans.index(p)
                matrix[i, j] = 1

    fig, ax = plt.subplots(figsize=(10, 8))
    cmap = plt.matplotlib.colors.ListedColormap(["white", "#3498DB"])
    im = ax.imshow(matrix, cmap=cmap, aspect="equal", interpolation="nearest")

    # Highlight different peer rule groupings
    for i, t in enumerate(chans):
        for j, p in enumerate(chans):
            if matrix[i, j]:
                # Determine peer category (visual code)
                same_pool = (t.startswith("DO_") or t.startswith("ORP_")) and \
                            (p.startswith("DO_") or p.startswith("ORP_")) and \
                            t.split("_")[1] == p.split("_")[1]
                twin_pool = (t.startswith("DO_") or t.startswith("ORP_")) and \
                            (p.startswith("DO_") or p.startswith("ORP_")) and \
                            t.split("_")[0] == p.split("_")[0] and \
                            t.split("_")[1] != p.split("_")[1] and \
                            t.split("_")[2] == p.split("_")[2]
                exo = p.startswith("Q")

                if exo:
                    color = C["amber"]; label = "exo"
                elif twin_pool:
                    color = C["red"]; label = "twin"
                elif same_pool:
                    color = C["green"]; label = "samePool"
                else:
                    color = C["gray"]; label = "other"
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                            facecolor=color, alpha=0.85,
                                            edgecolor="white", lw=0.5))

    ax.set_xticks(range(len(chans))); ax.set_xticklabels(chans, rotation=90, fontsize=7)
    ax.set_yticks(range(len(chans))); ax.set_yticklabels(chans, fontsize=7)
    ax.set_xlabel("Peer (predictor)"); ax.set_ylabel("Target")
    ax.set_title("Fig. 11 — PLS engineered peer matrix (spec v2 §7)\n"
                 "Green=same-pool adjacent | Red=twin-pool counterpart | Amber=QR/QIR exogenous",
                 fontsize=10, fontweight="bold")

    legend_patches = [
        plt.matplotlib.patches.Patch(color=C["green"],  label="Rule 1: same-pool adjacent"),
        plt.matplotlib.patches.Patch(color=C["red"],    label="Rule 2: twin-pool counterpart"),
        plt.matplotlib.patches.Patch(color=C["amber"],  label="Rule 3: QR/QIR exogenous driver"),
    ]
    ax.legend(handles=legend_patches, loc="upper center",
              bbox_to_anchor=(0.5, -0.13), ncol=3, frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    rows = []
    for i, t in enumerate(chans):
        for j, p in enumerate(chans):
            if matrix[i, j]:
                rows.append({"target": t, "peer": p})
    return out_path, pd.DataFrame(rows)
