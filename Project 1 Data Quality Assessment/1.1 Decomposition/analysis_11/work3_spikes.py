"""analysis_11/work3_spikes.py — Work 3: spike-event statistics as a §1.1
whitening SANITY CHECK (formal spike detection / attribution belongs to §1.2 D1).

Manifest-driven thresholding (the key point — global thresholds are invalid off
the iid track):
  iid            : local Hampel (k·MAD) on the WHITE innovation η. A global 3·MAD
                   (assumes near-normal symmetry) or a 99th-pct (empirical) cut
                   would disagree; the local Hampel is the single consistent rule.
  autocorr_aware : local Hampel on the residual/robust_z — a GLOBAL 3·MAD/99th-pct
                   is dominated by the slow random walk and makes the "event count"
                   statistically meaningless, so it is forbidden here.
  floor_freeze   : no spike test; handled by freeze / censoring.

Event RATE (per 1000 points), not raw count, so channels of different length /
sampling rate compare; the rate's CI uses the EFFECTIVE sample size
(n·n_eff_ratio) on the autocorr_aware track, not n.

This is a sufficiency check ("does the whitened series still carry anomalous
clustering / structure?"), NOT fault adjudication — see §1.2 D1.

Outputs
  outputs/figures/fig_A3_spike_event_rate.png
  outputs/tables/A2_spike_event_rate.csv
  outputs/plot_data/fig_A3_spike_event_rate.csv
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (TAB, FIG, PDATA, MODE_COLOR, OKABE_ITO, PROCESS_ORDER,
                    POS_BAND, BAND_ORDER, load_manifest, get_residual,
                    get_innovation, setup_style)

K = 3.0                       # Hampel threshold (k·MAD)
IID_EXPECTED = 1000 * 2 * (1 - 0.5 * (1 + 1.0)) if False else 2.70  # 2·(1−Φ(3))·1000


def hampel_events(s: pd.Series, win: int, k: float = K) -> tuple[int, int]:
    """Local Hampel: flag |x − rolling_median| > k·1.4826·rolling_MAD.
    Returns (n_events, n_valid). Causal (trailing) window."""
    v = s.dropna()
    if len(v) < win + 5:
        return 0, len(v)
    med = v.rolling(win, center=False, min_periods=max(5, win // 4)).median()
    mad = (v - med).abs().rolling(win, center=False, min_periods=max(5, win // 4)).median()
    sigma = 1.4826 * mad.replace(0, np.nan)
    z = (v - med).abs() / sigma
    flag = (z > k)
    valid = flag[sigma.notna()]
    return int(valid.sum()), int(len(valid))


def rate_ci(n_events: int, n_valid: int, n_eff_ratio: float) -> tuple[float, float, float]:
    """Event rate per 1000 pts + 95% CI using the EFFECTIVE sample size."""
    if n_valid == 0:
        return np.nan, np.nan, np.nan
    p = n_events / n_valid
    n_eff = max(n_valid * float(n_eff_ratio), 1.0)
    se = np.sqrt(max(p * (1 - p), 1e-12) / n_eff)
    return 1000 * p, 1000 * max(0.0, p - 1.96 * se), 1000 * (p + 1.96 * se)


def main():
    setup_style()
    man = load_manifest()
    rows = []
    for ch in PROCESS_ORDER:
        mode = man.loc[ch, "scoring_mode"]
        innk = man.loc[ch, "innov_kind"]
        neff = float(man.loc[ch, "n_eff_ratio"])
        track_min = not ch.startswith(("inf_", "eff_"))
        # window long enough that the local MAD scale is stable (≈ global on the
        # variance-standardised innovation) yet still local for slow-drift residuals
        win = 721 if track_min else 49
        if mode == "floor_freeze":
            rows.append({"channel": ch, "band": POS_BAND[ch], "scoring_mode": mode,
                         "threshold": "—  (floor/censor → freeze, §1.2)",
                         "input": innk, "rate_per_1000": np.nan, "ci_lo": np.nan,
                         "ci_hi": np.nan, "n_events": np.nan, "n_valid": np.nan,
                         "n_eff_used": np.nan})
            continue
        src = get_innovation(ch) if mode == "iid" else get_residual(ch)
        ne, nv = hampel_events(src, win)
        r, lo, hi = rate_ci(ne, nv, neff if mode == "autocorr_aware" else 1.0)
        rows.append({
            "channel": ch, "band": POS_BAND[ch], "scoring_mode": mode,
            "threshold": f"local Hampel k={K:g} on {'η (innovation)' if mode=='iid' else 'residual/robust_z'}",
            "input": innk, "rate_per_1000": r, "ci_lo": lo, "ci_hi": hi,
            "n_events": ne, "n_valid": nv,
            "n_eff_used": (nv * neff if mode == "autocorr_aware" else nv)})
    df = pd.DataFrame(rows)
    df.round(4).to_csv(TAB / "A2_spike_event_rate.csv", index=False, encoding="utf-8-sig")
    df.round(4).to_csv(PDATA / "fig_A3_spike_event_rate.csv", index=False, encoding="utf-8-sig")

    # ── figure: event-rate bars by process position, coloured by scoring_mode ──
    n = len(df); x = np.arange(n)
    VERM = OKABE_ITO["vermillion"]
    fig, ax = plt.subplots(figsize=(13.5, 4.8))
    colors = [MODE_COLOR[m] for m in df["scoring_mode"]]
    r = df["rate_per_1000"].values
    lo = df["ci_lo"].values; hi = df["ci_hi"].values
    yerr = np.vstack([np.nan_to_num(r - lo), np.nan_to_num(hi - r)])
    ax.bar(x, np.nan_to_num(r), color=colors, width=0.82, edgecolor="white", linewidth=0.4)
    ax.errorbar(x, np.nan_to_num(r), yerr=yerr, fmt="none", ecolor="0.25", elinewidth=0.7, capsize=2)
    ax.axhline(IID_EXPECTED, color=VERM, lw=1.0, ls="--")

    band_edges = {}
    for i, ch in enumerate(df["channel"]):
        band_edges.setdefault(POS_BAND[ch], [i, i])[1] = i
    ymax = float(np.nanmax(np.r_[df["ci_hi"].values, IID_EXPECTED])) * 1.18
    # floor channels carry no spike test → visible hatched stub + clear label
    for i in np.where(df["scoring_mode"] == "floor_freeze")[0]:
        ax.bar(i, ymax * 0.10, width=0.82, color=MODE_COLOR["floor_freeze"],
               alpha=0.55, hatch="///", edgecolor="white", linewidth=0.4)
        ax.text(i, ymax * 0.12, "floor → freeze (§1.2)", rotation=90, ha="center",
                va="bottom", fontsize=8.5, fontweight="bold", color="0.30")
    for b in BAND_ORDER:
        lo_i, hi_i = band_edges[b]
        if lo_i > 0:
            ax.axvline(lo_i - 0.5, color="0.35", lw=0.8, ls=":")
        ax.text((lo_i + hi_i) / 2, ymax * 0.985, b.replace("_", " "), ha="center",
                va="top", fontsize=8.4, fontweight="bold", color="0.15")
    ax.set_xticks(x); ax.set_xticklabels(df["channel"], rotation=60, ha="right", fontsize=7.6)
    ax.set_ylim(0, ymax); ax.set_xlim(-0.7, n - 0.3)
    ax.set_ylabel("spike-event rate (per 1000 pts)\n95% CI uses n·n_eff", fontsize=9)

    import matplotlib.patches as mp
    handles = [mp.Patch(color=MODE_COLOR[k], label=k) for k in ["iid", "autocorr_aware", "floor_freeze"]]
    handles.append(plt.Line2D([], [], color=VERM, ls="--",
                              label=f"iid normal-tail expectation ≈ {IID_EXPECTED:.2f}/1000 (k=3)"))
    # placed mid-left (below the top band labels, above the low aerobic/ORP bars)
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.008, 0.80),
              ncol=2, fontsize=8.2, framealpha=0.95)
    fig.suptitle("Figure A3.  Whitening sanity check — local-Hampel spike-event RATE "
                 "(per 1000 pts; manifest-keyed input; formal detection → §1.2 D1)",
                 fontsize=9.8, y=1.0)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.9, bottom=0.2)
    fig.savefig(FIG / "fig_A3_spike_event_rate.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    iid = df[df.scoring_mode == "iid"]["rate_per_1000"]
    ac = df[df.scoring_mode == "autocorr_aware"]["rate_per_1000"]
    print(f"[Work3] iid rate/1000: mean {iid.mean():.2f} (expect ≈{IID_EXPECTED:.2f}), "
          f"range {iid.min():.2f}–{iid.max():.2f}")
    print(f"[Work3] autocorr_aware rate/1000: {ac.round(2).tolist()} (local Hampel, not inflated)")
    print("[Work3] wrote A2_spike_event_rate.csv + fig_A3 + bundle")


if __name__ == "__main__":
    main()
