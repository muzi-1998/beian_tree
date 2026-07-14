from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np
import pandas as pd

from .config import D6Config
from .figure_style import PALETTE, configure_style, panel_label, save_figure


def _boxed(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(True)


def _open(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _pair_label(pair_id: str) -> str:
    return pair_id.replace("PAIR_", "")


def figure_m1(cfg: D6Config, main: pd.DataFrame, output_dir: Path) -> None:
    residuals = pd.read_parquet(cfg.paths["residuals"])
    residuals = residuals.resample("6h").median()
    fig, axes = plt.subplots(len(cfg.pairs), 1, figsize=(183 / 25.4, 178 / 25.4), sharex=True)
    for index, (ax, pair) in enumerate(zip(axes, cfg.pairs)):
        pooled = pd.concat([residuals[pair.target], residuals[pair.reference]])
        scale = max(float((pooled - pooled.median()).abs().median() * 1.4826), cfg.deadband[pair.variable])
        ax.plot(residuals.index, residuals[pair.target] / scale, color=PALETTE["blue"], lw=0.55,
                label="Pool 1" if index == 0 else None)
        ax.plot(residuals.index, residuals[pair.reference] / scale, color=PALETTE["orange"], lw=0.55,
                alpha=0.90, label="Pool 2" if index == 0 else None)
        events = main[(main["pair_id"] == pair.pair_id) & (main["raw_status_label"] == "pair_asymmetry")]
        for timestamp in events["timestamp"].iloc[::6]:
            ax.axvspan(timestamp, timestamp + pd.Timedelta(hours=6), color=PALETTE["red"], alpha=0.08, lw=0)
        ax.axhline(0, color=PALETTE["light_gray"], lw=0.45, zorder=0)
        ax.set_ylabel(_pair_label(pair.pair_id), rotation=0, ha="right", va="center", labelpad=22)
        panel_label(ax, chr(97 + index))
        _open(ax)
    axes[0].legend(loc="lower right", ncol=2, handlelength=2.2)
    axes[-1].set_xlabel("Date")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.text(0.012, 0.5, "De-periodised residual (robust z)", rotation=90,
             ha="left", va="center", fontsize=7)
    fig.subplots_adjust(left=0.17, right=0.99, top=0.98, bottom=0.08, hspace=0.18)
    save_figure(fig, output_dir / "Fig_M1_paired_residual_consistency")


def figure_m2(main: pd.DataFrame, profile: pd.DataFrame, output_dir: Path) -> None:
    pairs = profile["pair_id"].tolist()
    labels = [_pair_label(item) for item in pairs]
    fig, axes = plt.subplots(1, 2, figsize=(183 / 25.4, 77 / 25.4), gridspec_kw={"wspace": 0.34})
    colors = [PALETTE["blue"], PALETTE["green"], PALETTE["orange"], PALETTE["purple"]]
    q_cols = ["Q_dist", "Q_trend", "Q_var", "Q_cp"]
    weights = np.array([0.35, 0.25, 0.20, 0.20])
    means = main.groupby("pair_id")[q_cols].mean().reindex(pairs).to_numpy()
    bottom = np.zeros(len(pairs))
    for values, color, label in zip((means * weights).T, colors, ["Distribution", "Trend", "Variability", "Change point"]):
        axes[0].bar(np.arange(len(pairs)), values, bottom=bottom, color=color, width=0.72, label=label)
        bottom += values
    axes[0].set_ylabel("Weighted contribution to D6 base")
    axes[0].set_xticks(np.arange(len(pairs)), labels, rotation=45, ha="right")
    axes[0].set_ylim(0, 5)
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, columnspacing=0.8)
    panel_label(axes[0], "a")
    _open(axes[0])

    positions = np.arange(len(pairs))
    data = [main.loc[(main["pair_id"] == pair) & main["usable_for_D6"], "D6_total"].dropna() for pair in pairs]
    box = axes[1].boxplot(data, positions=positions, widths=0.58, patch_artist=True, showfliers=False,
                          medianprops={"color": "white", "linewidth": 0.9},
                          whiskerprops={"linewidth": 0.7}, capprops={"linewidth": 0.7})
    for patch in box["boxes"]:
        patch.set_facecolor(PALETTE["teal"])
        patch.set_edgecolor(PALETTE["teal"])
    axes[1].axhline(3.0, color=PALETTE["red"], lw=0.7, ls="--", label="Asymmetry threshold")
    axes[1].set_ylabel("D6 score (1-5)")
    axes[1].set_xticks(positions, labels, rotation=45, ha="right")
    axes[1].set_ylim(1, 5)
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, 1.13))
    panel_label(axes[1], "b")
    _open(axes[1])
    fig.subplots_adjust(left=0.08, right=0.99, top=0.80, bottom=0.24)
    save_figure(fig, output_dir / "Fig_M2_subscore_contribution")


def figure_m3(raw: pd.DataFrame, output_dir: Path) -> None:
    fig = plt.figure(figsize=(183 / 25.4, 82 / 25.4))
    grid = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.045], wspace=0.34)
    axes = np.array([fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])])
    colorbar_ax = fig.add_subplot(grid[0, 2])
    shared_norm = mpl.colors.LogNorm(vmin=1, vmax=1500)
    density = None
    for index, (ax, variable) in enumerate(zip(axes, ("DO", "ORP"))):
        frame = raw[raw["pair_id"].str.contains(variable)].dropna(subset=["beta_target", "beta_reference"])
        limit = float(np.nanquantile(np.abs(frame[["beta_target", "beta_reference"]]), 0.99))
        density = ax.hexbin(frame["beta_target"], frame["beta_reference"], gridsize=44,
                            extent=(-limit, limit, -limit, limit), mincnt=1,
                            cmap="mako" if "mako" in plt.colormaps() else "Blues", norm=shared_norm)
        ax.plot([-limit, limit], [-limit, limit], color=PALETTE["gray"], lw=0.75, ls="--")
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-limit, limit)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(f"Pool 1 {variable} slope")
        ax.set_ylabel(f"Pool 2 {variable} slope")
        panel_label(ax, chr(97 + index))
        _boxed(ax)
    cbar = fig.colorbar(density, cax=colorbar_ax)
    cbar.set_label("Window count (log scale)")
    fig.subplots_adjust(left=0.09, right=0.94, top=0.94, bottom=0.16)
    save_figure(fig, output_dir / "Fig_M3_trend_slope_scatter")


def figure_d1(main: pd.DataFrame, output_dir: Path) -> None:
    weekly = (main.set_index("timestamp").groupby("pair_id")["D6_forDQR_provisional"]
              .resample("W-MON").mean().unstack(0))
    weekly = weekly[[c for c in main["pair_id"].drop_duplicates() if c in weekly.columns]]
    fig, ax = plt.subplots(figsize=(183 / 25.4, 57 / 25.4))
    image = ax.imshow(weekly.T, aspect="auto", interpolation="nearest", cmap="viridis", vmin=1, vmax=5)
    ax.set_yticks(np.arange(len(weekly.columns)), [_pair_label(c) for c in weekly.columns])
    tick = np.linspace(0, len(weekly) - 1, 9, dtype=int)
    ax.set_xticks(tick, [weekly.index[i].strftime("%Y-%m-%d") for i in tick], rotation=35, ha="right")
    ax.set_xlabel("ISO week ending")
    cbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.018, ticks=[1, 2, 3, 4, 5])
    cbar.set_label("Mean provisional D6-for-DQR score")
    fig.text(0.10, 0.965, "Provisional: D1 fuse applied; D7 pending",
             ha="left", va="bottom", fontsize=6)
    _boxed(ax)
    fig.subplots_adjust(left=0.10, right=0.94, top=0.91, bottom=0.27)
    save_figure(fig, output_dir / "Fig_D1_dqr_heatmap")


def figure_d2(main: pd.DataFrame, output_dir: Path) -> None:
    order = list(main["pair_id"].drop_duplicates())
    status_order = ["paired_consistent", "pending_D7_arbitration", "ambiguous_asymmetry", "not_evaluable"]
    status_map = {name: index for index, name in enumerate(status_order)}
    weekly = main.copy()
    weekly["week"] = weekly["timestamp"].dt.to_period("W-MON").dt.start_time
    mode = weekly.groupby(["pair_id", "week"])["status_label"].agg(lambda x: x.mode().iloc[0]).unstack()
    coverage = weekly.groupby(["pair_id", "week"])["usable_for_D6"].mean().unstack()
    mode = mode.reindex(order)
    coverage = coverage.reindex(order)
    coded = mode.apply(lambda column: column.map(status_map)).to_numpy(dtype=float)
    cmap = ListedColormap([PALETTE["green"], PALETTE["amber"], PALETTE["red"], PALETTE["light_gray"]])
    norm = BoundaryNorm(np.arange(-0.5, 4.5), cmap.N)
    fig, axes = plt.subplots(2, 1, figsize=(183 / 25.4, 83 / 25.4), sharex=True,
                             gridspec_kw={"height_ratios": [1.6, 1], "hspace": 0.32})
    axes[0].imshow(coded, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm)
    axes[0].set_yticks(np.arange(len(order)), [_pair_label(item) for item in order])
    handles = [mpl.patches.Patch(color=cmap(i), label=name.replace("_", " ")) for i, name in enumerate(status_order)]
    axes[0].legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.25), ncol=4, columnspacing=0.8)
    panel_label(axes[0], "a")
    _boxed(axes[0])
    coverage_image = axes[1].imshow(coverage.to_numpy(dtype=float), aspect="auto", interpolation="nearest",
                                    cmap="Blues", vmin=0, vmax=1)
    axes[1].set_yticks(np.arange(len(order)), [_pair_label(item) for item in order])
    panel_label(axes[1], "b")
    _boxed(axes[1])
    tick = np.linspace(0, mode.shape[1] - 1, 9, dtype=int)
    axes[1].set_xticks(tick, [mode.columns[i].strftime("%Y-%m-%d") for i in tick], rotation=35, ha="right")
    axes[1].set_xlabel("ISO week starting")
    cbar = fig.colorbar(coverage_image, ax=axes[1], fraction=0.025, pad=0.018)
    cbar.set_label("Evaluable fraction")
    fig.subplots_adjust(left=0.10, right=0.94, top=0.88, bottom=0.22)
    save_figure(fig, output_dir / "Fig_D2_status_barcode")


def figure_d3(main: pd.DataFrame, output_dir: Path) -> None:
    valid = main.dropna(subset=["D6_raw", "D6_forDQR_provisional"]).copy()
    fig, axes = plt.subplots(1, 2, figsize=(183 / 25.4, 77 / 25.4), gridspec_kw={"wspace": 0.34})
    hb = axes[0].hexbin(valid["D6_raw"], valid["D6_forDQR_provisional"],
                        gridsize=42, mincnt=1, cmap="Blues", extent=(1, 5, 1, 5))
    axes[0].plot([1, 5], [1, 5], color=PALETTE["gray"], lw=0.75, ls="--")
    axes[0].set(xlim=(1, 5), ylim=(1, 5), xlabel="D6 raw score",
                ylabel="Provisional D6-for-DQR score")
    fig.colorbar(hb, ax=axes[0], fraction=0.046, pad=0.03, label="Window count")
    panel_label(axes[0], "a")
    _boxed(axes[0])

    states = ["valid_pair", "target_suspect", "reference_unreliable", "bilateral_unreliable"]
    counts = valid["fuse_state"].value_counts().reindex(states, fill_value=0)
    axes[1].bar(np.arange(len(states)), counts.to_numpy(),
                color=[PALETTE["teal"], PALETTE["blue"], PALETTE["orange"], PALETTE["red"]],
                width=0.72)
    axes[1].set_yscale("log")
    axes[1].set_ylim(0.8, max(10.0, float(counts.max()) * 1.8))
    for position, count in enumerate(counts.to_numpy()):
        axes[1].text(position, max(float(count), 1.0) * 1.12, f"{int(count):,}",
                     ha="center", va="bottom", fontsize=6)
    axes[1].set_xticks(np.arange(len(states)), [item.replace("_", " ") for item in states],
                       rotation=28, ha="right")
    axes[1].set_ylabel("Evaluable windows (log scale)")
    axes[1].text(0.98, 0.96, "Final D7 arbitration pending", transform=axes[1].transAxes,
                 ha="right", va="top",
                 bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.2})
    panel_label(axes[1], "b")
    _open(axes[1])
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.23)
    save_figure(fig, output_dir / "Fig_D3_context_independence")


def figure_v1(benchmark_path: Path, output_dir: Path) -> None:
    curves = pd.read_excel(benchmark_path, sheet_name="roc_pr_curves")
    summary = pd.read_excel(benchmark_path, sheet_name="summary")
    fig, axes = plt.subplots(1, 2, figsize=(183 / 25.4, 75 / 25.4), gridspec_kw={"wspace": 0.32})
    colors = [PALETTE["blue"], PALETTE["orange"], PALETTE["green"], PALETTE["purple"]]
    labels = {"unilateral_drift": "Drift", "unilateral_step": "Step",
              "unilateral_freeze": "Freeze", "unilateral_spike": "Spike"}
    for color, injection in zip(colors, labels):
        roc = curves[(curves["injection"] == injection) & (curves["curve"] == "ROC")]
        pr = curves[(curves["injection"] == injection) & (curves["curve"] == "PR")]
        auc_value = summary[(summary["validation"] == injection) & (summary["metric"] == "ROC_AUC")]["value"].iloc[0]
        axes[0].plot(roc["x"], roc["y"], color=color, lw=1.1, label=f"{labels[injection]} ({auc_value:.2f})")
        axes[1].plot(pr["x"], pr["y"], color=color, lw=1.1, label=labels[injection])
    axes[0].plot([0, 1], [0, 1], color=PALETTE["gray"], lw=0.7, ls="--")
    axes[0].set(xlim=(0, 1), ylim=(0, 1), xlabel="False-positive rate", ylabel="True-positive rate")
    axes[1].axhline(0.5, color=PALETTE["gray"], lw=0.7, ls="--", label="Chance prevalence")
    axes[1].set(xlim=(0, 1), ylim=(0, 1), xlabel="Recall", ylabel="Precision")
    for index, ax in enumerate(axes):
        ax.legend(loc="lower right", fontsize=6)
        panel_label(ax, chr(97 + index))
        _boxed(ax)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.94, bottom=0.18)
    save_figure(fig, output_dir / "Fig_V1_roc_pr")


def figure_v2(benchmark_path: Path, output_dir: Path) -> None:
    ablation = pd.read_excel(benchmark_path, sheet_name="ablation")
    labels = ablation["condition"].str.replace("_", " ").tolist()
    x = np.arange(len(ablation))
    fig, axes = plt.subplots(1, 2, figsize=(183 / 25.4, 72 / 25.4), gridspec_kw={"wspace": 0.32})
    auc_error = np.vstack([
        ablation["ROC_AUC"] - ablation["AUC_CI_low"],
        ablation["AUC_CI_high"] - ablation["ROC_AUC"],
    ])
    axes[0].bar(x, ablation["ROC_AUC"], color=[PALETTE["blue"]] + [PALETTE["gray"]] * (len(x) - 1),
                width=0.72, yerr=auc_error, capsize=2,
                error_kw={"elinewidth": 0.7, "ecolor": PALETTE["gray"]})
    axes[0].axhline(0.5, color=PALETTE["gray"], lw=0.7, ls="--")
    axes[0].set_ylim(0.45, 0.86)
    axes[0].set_ylabel("ROC AUC: unilateral faults")
    axes[0].set_xticks(x, labels, rotation=35, ha="right")
    panel_label(axes[0], "a")
    _open(axes[0])
    far_error = np.vstack([
        ablation["synchronous_FAR"] - ablation["FAR_CI_low"],
        ablation["FAR_CI_high"] - ablation["synchronous_FAR"],
    ])
    axes[1].bar(x, ablation["synchronous_FAR"], color=[PALETTE["teal"]] + [PALETTE["gray"]] * (len(x) - 1),
                width=0.72, yerr=far_error, capsize=2,
                error_kw={"elinewidth": 0.7, "ecolor": PALETTE["gray"]})
    axes[1].axhline(0.10, color=PALETTE["red"], lw=0.7, ls="--", label="Acceptance limit")
    axes[1].set_ylim(0, max(0.12, float(ablation["synchronous_FAR"].max()) * 1.25))
    axes[1].set_ylabel("Conditional new false-alarm rate")
    axes[1].set_xticks(x, labels, rotation=35, ha="right")
    axes[1].legend(loc="upper right")
    panel_label(axes[1], "b")
    _open(axes[1])
    fig.subplots_adjust(left=0.09, right=0.99, top=0.94, bottom=0.28)
    save_figure(fig, output_dir / "Fig_V2_ablation")


def make_all_figures(cfg: D6Config, data_dir: Path, output_dir: Path) -> None:
    configure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    main = pd.read_excel(data_dir / "D6_main_scores.xlsx", sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    profile = pd.read_excel(data_dir / "D6_pair_profile_summary.xlsx", sheet_name="pair_profile")
    raw = pd.read_excel(data_dir / "D6_detector_outputs_raw.xlsx", sheet_name="detector_outputs")
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    figure_m1(cfg, main, output_dir)
    figure_m2(main, profile, output_dir)
    figure_m3(raw, output_dir)
    figure_d1(main, output_dir)
    figure_d2(main, output_dir)
    figure_d3(main, output_dir)
    figure_v1(data_dir / "D6_benchmark_results.xlsx", output_dir)
    figure_v2(data_dir / "D6_benchmark_results.xlsx", output_dir)
