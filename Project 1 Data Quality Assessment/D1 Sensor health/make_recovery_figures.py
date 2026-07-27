"""Nature-style event-level recovery figures for the final D1 pipeline."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap


ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publication_style import (
    PALETTE,
    STATE_COLORS,
    configure_publication_style,
    save_publication_bundle,
)


configure_publication_style()
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "font.size": 8.0,
    "axes.titlesize": 9.2,
    "axes.titleweight": "bold",
    "axes.titlepad": 5.0,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 6.8,
})
OUT = ROOT / "outputs" / "figures"
PLOT_DATA = ROOT / "outputs" / "plot_data"
OUT.mkdir(parents=True, exist_ok=True)
PLOT_DATA.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    with open(ROOT / "v11_state.pkl", "rb") as handle:
        return pickle.load(handle)


def _save(fig, name: str, state: dict, sheets: dict[str, pd.DataFrame]) -> None:
    save_publication_bundle(
        fig,
        OUT / name,
        version_label=state["algorithm_version"],
    )
    metadata = pd.DataFrame([{
        "run_id": state["run_id"],
        "algorithm_version": state["algorithm_version"],
        "figure": name,
    }])
    with pd.ExcelWriter(PLOT_DATA / f"{name}_plot_data.xlsx", engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="metadata", index=False)
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    plt.close(fig)


def make_recovery_validation_figure(state: dict) -> None:
    validation_path = ROOT / "outputs" / "data" / "D1_recovery_validation.xlsx"
    sensitivity = pd.read_excel(validation_path, sheet_name="natural_sensitivity")
    injections = pd.read_excel(validation_path, sheet_name="injection_summary")
    episodes = state["recovery_episodes"].copy()
    km = state["recovery_km"].copy()

    variants = sensitivity["variant"].tolist()
    short_names = ["A\nLegacy", "B\nNo W1", "C\nProduction", "D\nHysteresis"]
    scenarios = [
        "transient_step",
        "stable_new_regime",
        "persistent_fault",
        "recurrent_independent_step",
    ]
    scenario_labels = ["Step", "New\nregime", "Fault", "Re-trigger"]

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.9))
    ax = axes[0, 0]
    outcome_order = [
        "direct_recovery", "adapted_recovery", "superseded", "right_censored"
    ]
    outcome_labels = ["Direct", "Adapted", "Superseded", "Right-censored"]
    outcome_colors = [PALETTE["green"], PALETTE["blue"], PALETTE["gray"], PALETTE["orange"]]
    counts = episodes["outcome"].value_counts().reindex(outcome_order, fill_value=0)
    bars = ax.bar(np.arange(4), counts.values, color=outcome_colors, width=0.68)
    ax.set_xticks(np.arange(4), outcome_labels, rotation=18, ha="right")
    ax.set_ylabel("Episodes (n)")
    ax.set_title("(a) Event outcomes", loc="left", fontweight="bold")
    ax.bar_label(bars, padding=2, fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, max(counts.max() * 1.18, 1))

    ax = axes[0, 1]
    if not km.empty:
        x = np.r_[0.0, km["time_h"].to_numpy(float)]
        y = np.r_[0.0, km["cumulative_recovery"].to_numpy(float)]
        ax.step(x, y, where="post", color=PALETTE["blue"], linewidth=1.5)
        censored = km[km["n_censored"] > 0]
        if not censored.empty:
            ax.scatter(censored["time_h"], censored["cumulative_recovery"],
                       marker="+", s=24, color=PALETTE["orange"], label="Censored")
    ax.axhline(0.5, color=PALETTE["gray"], linewidth=0.7, linestyle="--")
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1.03)
    ax.set_xlabel("Time from event onset (h)")
    ax.set_ylabel("Cumulative recovery probability")
    ax.set_title("(b) Time-to-recovery", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1, 0]
    x = np.arange(len(variants))
    event_rate = sensitivity["event_recovery_rate"].to_numpy(float)
    confirmation = sensitivity["candidate_attempt_confirmation_rate"].to_numpy(float)
    ax.plot(x, event_rate, marker="o", markersize=4.5, linewidth=1.1,
            color=PALETTE["green"], label="Event recovery")
    ax.plot(x, confirmation, marker="s", markersize=4.2, linewidth=1.1,
            color=PALETTE["purple"], label="Candidate confirmation")
    selected = sensitivity["selected_for_production"].astype(bool).to_numpy()
    ax.scatter(x[selected], event_rate[selected], s=54, facecolors="none",
               edgecolors=PALETTE["red"], linewidths=1.0, zorder=5)
    ax.scatter(x[selected], confirmation[selected], s=54, facecolors="none",
               edgecolors=PALETTE["red"], linewidths=1.0, zorder=5)
    ax.set_xticks(x, short_names)
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Rate")
    ax.set_title("(c) Natural-data sensitivity", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1, 1]
    matrix = (
        injections.pivot(index="variant", columns="scenario", values="pass_rate")
        .reindex(index=variants, columns=scenarios)
        .to_numpy(float)
    )
    cmap = ListedColormap(["#F2D5D5", "#DCEBDD", PALETTE["green"]])
    image = ax.imshow(matrix, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    ax.set_xticks(np.arange(4), scenario_labels)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_yticks(np.arange(4), short_names)
    ax.set_title("(d) Mechanism challenge pass rate", loc="left", fontweight="bold")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = matrix[row, col]
            ax.text(col, row, f"{value:.0%}", ha="center", va="center",
                    fontsize=7, color="black")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("Expected-outcome pass rate")

    fig.suptitle(
        "Figure V19. Event-level recovery performance and mechanism validation",
        fontsize=9.8, fontweight="bold", fontfamily="Arial", y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97), h_pad=1.5, w_pad=1.4)
    outcome_data = pd.DataFrame({
        "outcome": outcome_order,
        "label": outcome_labels,
        "n_episodes": counts.values,
    })
    _save(fig, "FigV19_recovery_validation", state, {
        "event_outcomes": outcome_data,
        "kaplan_meier": km,
        "natural_sensitivity": sensitivity,
        "mechanism_challenges": injections,
    })


def make_recovery_case_figure(state: dict) -> None:
    episodes = state["recovery_episodes"]
    preferred = episodes[
        (episodes["outcome"] == "adapted_recovery")
        & (episodes["relapse_within_72h"] == False)  # noqa: E712
        & (episodes["candidate_entry_count"] == 1)
    ].sort_values("time_to_recovery_h")
    if preferred.empty:
        preferred = episodes[episodes["outcome"] == "adapted_recovery"].sort_values(
            "time_to_recovery_h"
        )
    episode = preferred.iloc[0]
    channel = episode["sensor_id"]
    log = state["state_log_dict"][channel]
    start = pd.Timestamp(episode["episode_start"]) - pd.Timedelta(hours=12)
    end = pd.Timestamp(episode["episode_end"]) + pd.Timedelta(hours=30)
    case = log.loc[start:end].copy()
    subs = state["subs_v11"][channel]
    peer = state["detectors_raw"].get("pls_residual_z_hourly")
    x = (case.index - pd.Timestamp(episode["episode_start"])) / pd.Timedelta(hours=1)

    fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.8), sharex=True)
    ax = axes[0]
    ax.plot(x, subs["Q_step"].loc[case.index], linewidth=1.0,
            color=PALETTE["red"], label=r"$Q_{step}$")
    ax.plot(x, subs["Q_regime"].loc[case.index], linewidth=1.0,
            color=PALETTE["purple"], label=r"$Q_{regime}$")
    ax.plot(x, subs["Q_freeze"].loc[case.index], linewidth=1.0,
            color=PALETTE["blue"], label=r"$Q_{freeze}$")
    ax.axhline(3.0, color=PALETTE["gray"], linestyle="--", linewidth=0.7,
               label="Recovery threshold")
    ax.set_ylabel("Quality score")
    ax.set_ylim(0, 5.15)
    ax.set_title(f"(a) Recovery gates: {channel}", loc="left", fontweight="bold")
    ax.legend(frameon=False, ncol=1, fontsize=6.5, loc="center left",
              bbox_to_anchor=(1.01, 0.5), borderaxespad=0)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    ax.plot(x, case["local_z"], linewidth=1.0, color=PALETTE["navy"],
            label="Local residual z")
    if peer is not None:
        ax.plot(x, peer[channel].loc[case.index].abs(), linewidth=0.9,
                color=PALETTE["teal"], label="Peer residual |z|")
    ax.axhline(2.0, color=PALETTE["navy"], linestyle="--", linewidth=0.7,
               label="Local gate")
    ax.axhline(2.5, color=PALETTE["teal"], linestyle=":", linewidth=0.8,
               label="Peer gate")
    ax.set_ylabel("Standardised residual")
    ax.set_title("(b) Independent recovery evidence", loc="left", fontweight="bold")
    ax.legend(frameon=False, ncol=1, fontsize=6.5, loc="center left",
              bbox_to_anchor=(1.01, 0.5), borderaxespad=0)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[2]
    state_order = list(STATE_COLORS)
    state_codes = case["state_name"].map({name: i for i, name in enumerate(state_order)})
    for i, state_name in enumerate(state_order):
        active = state_codes.eq(i).to_numpy()
        if not active.any():
            continue
        ax.fill_between(x, 0, 1, where=active, step="mid",
                        color=STATE_COLORS[state_name], alpha=0.85,
                        label=state_name)
    event_x = 0.0
    recovery_x = float(episode["time_to_recovery_h"])
    ax.axvline(event_x, color="black", linewidth=0.8, linestyle="--")
    ax.axvline(recovery_x, color=PALETTE["blue"], linewidth=0.9, linestyle="--")
    ax.text(event_x, 0.92, "Event", ha="left", va="top", fontsize=7,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.15})
    ax.text(recovery_x, 0.92, "Recovered", ha="right", va="top", fontsize=7,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.15})
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("Time from event onset (h)")
    ax.set_title("(c) Causal state path and 24 h observation", loc="left", fontweight="bold")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, frameon=False, ncol=3, fontsize=6.5,
              loc="upper center", bbox_to_anchor=(0.5, -0.28))

    for ax in axes:
        ax.axvline(0, color="black", linewidth=0.6, linestyle="--", alpha=0.55)
    fig.suptitle(
        "Figure V20. Adapted recovery after a persistent regime departure",
        fontsize=9.8, fontweight="bold", fontfamily="Arial", y=0.995,
    )
    fig.tight_layout(rect=(0, 0.05, 0.82, 0.97), h_pad=1.1)
    export = case.reset_index().rename(columns={case.index.name or "index": "timestamp"})
    export.insert(1, "hours_from_event", x.to_numpy(float))
    export["Q_step"] = subs["Q_step"].loc[case.index].to_numpy()
    export["Q_regime"] = subs["Q_regime"].loc[case.index].to_numpy()
    export["Q_freeze"] = subs["Q_freeze"].loc[case.index].to_numpy()
    if peer is not None:
        export["peer_residual_abs_z"] = peer[channel].loc[case.index].abs().to_numpy()
    _save(fig, "FigV20_adapted_recovery_case", state, {
        "case_timeseries": export,
        "episode_metadata": pd.DataFrame([episode.to_dict()]),
    })


def main() -> None:
    state = _load_state()
    make_recovery_validation_figure(state)
    make_recovery_case_figure(state)
    print("Saved FigV19 and FigV20 in SVG/PDF/PNG/TIFF with source workbooks.")


if __name__ == "__main__":
    main()
