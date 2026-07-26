"""Generate Supplementary Fig. S1: production-active D1 PLS peer topology."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch, Rectangle


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from publication_style import (  # noqa: E402
    PALETTE,
    configure_publication_style,
    save_publication_bundle,
)


FIGURE_STEM = "FigS1_pls_formal_peer_topology"
FIGURE_DIR = ROOT / "outputs" / "figures"
PLOT_DATA_DIR = ROOT / "outputs" / "plot_data"


def _parse_peers(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(peer).strip() for peer in value if str(peer).strip()]
    if pd.isna(value):
        return []
    return [peer.strip() for peer in str(value).split(";") if peer.strip()]


def _sensor_parts(sensor_id: str) -> tuple[str, int, int]:
    parts = sensor_id.split("_")
    if len(parts) != 3 or parts[0] not in {"DO", "ORP"}:
        raise ValueError(f"Unsupported sensor identifier: {sensor_id}")
    return parts[0], int(parts[1]), int(parts[2])


def _relation(target: str, peer: str, noncore_peers: set[str]) -> tuple[int, str]:
    target_kind, target_train, target_position = _sensor_parts(target)
    peer_kind, peer_train, peer_position = _sensor_parts(peer)
    if target_kind != peer_kind:
        raise ValueError(f"Cross-analyte formal PLS edge is not allowed: {peer} -> {target}")
    if peer in noncore_peers:
        return 3, "validated same-train second-order"
    if target_train == peer_train and abs(target_position - peer_position) == 1:
        return 1, "same-train adjacent core"
    if target_train != peer_train and target_position == peer_position:
        return 2, "same-position twin-pool core"
    raise ValueError(f"Unclassified formal PLS edge: {peer} -> {target}")


def build_peer_tables(state: dict) -> dict[str, pd.DataFrame]:
    channels = list(state["scored_channels"])
    detector_tables = state["detectors_raw"]
    audit = detector_tables["pls_peer_selection_audit"].reindex(channels).copy()
    matrix = detector_tables["pls_peer_matrix"].reindex(
        index=channels, columns=channels
    ).fillna(0).astype(int)
    if audit.index.has_duplicates or matrix.index.has_duplicates:
        raise ValueError("Duplicate sensor identifiers in the PLS peer audit")

    class_matrix = pd.DataFrame(0, index=channels, columns=channels, dtype=int)
    label_matrix = pd.DataFrame("", index=channels, columns=channels, dtype=object)
    model_rows = []
    pair_rows = []

    for target in channels:
        selected = _parse_peers(audit.at[target, "selected_peers"])
        noncore = set(_parse_peers(audit.at[target, "selected_noncore_peers"]))
        matrix_selected = matrix.columns[matrix.loc[target].ne(0)].tolist()
        if set(selected) != set(matrix_selected):
            raise ValueError(
                f"Stale PLS matrix for {target}: audit={selected}, matrix={matrix_selected}"
            )

        n_components = int(audit.at[target, "selected_n_components"])
        if not selected or not 1 <= n_components <= len(selected):
            raise ValueError(
                f"Invalid effective PLS model for {target}: "
                f"peers={selected}, n_components={n_components}"
            )
        for peer in selected:
            code, relation = _relation(target, peer, noncore)
            class_matrix.at[target, peer] = code
            label_matrix.at[target, peer] = relation
            pair_rows.append(
                {
                    "target": target,
                    "predictor": peer,
                    "relation": relation,
                    "formal": True,
                    "n_components": n_components,
                }
            )
        model_rows.append(
            {
                "target": target,
                "formal_predictors": ";".join(selected),
                "n_peers": len(selected),
                "n_components": n_components,
                "redundancy_status": audit.at[target, "redundancy_status"],
                "validation_status": audit.at[target, "validation_status"],
            }
        )

    excluded = sorted(
        channel
        for channel, mode in state.get("scoring_mode", {}).items()
        if channel in channels and mode == "floor_freeze"
    )
    active_predictors = set(pd.DataFrame(pair_rows)["predictor"])
    invalid_exclusions = active_predictors.intersection(excluded)
    if invalid_exclusions:
        raise ValueError(
            "Process-floor channels entered formal PLS predictors: "
            + ", ".join(sorted(invalid_exclusions))
        )

    exclusions = pd.DataFrame(
        [
            {
                "sensor_id": channel,
                "predictor_status": "excluded",
                "reason": "process-floor routing; not exchangeable as a PLS predictor",
            }
            for channel in excluded
        ]
    )
    return {
        "formal_peer_matrix": matrix,
        "topology_class_matrix": class_matrix,
        "topology_label_matrix": label_matrix,
        "formal_model_summary": pd.DataFrame(model_rows),
        "formal_peer_pairs": pd.DataFrame(pair_rows),
        "predictor_exclusions": exclusions,
    }


def make_figure(state: dict, tables: dict[str, pd.DataFrame]):
    channels = list(state["scored_channels"])
    class_matrix = tables["topology_class_matrix"]
    model_summary = tables["formal_model_summary"].set_index("target").loc[channels]
    excluded = set(tables["predictor_exclusions"].get("sensor_id", []))
    n_channels = len(channels)

    configure_publication_style()
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 7.2,
            "axes.titlesize": 8.2,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 6.6,
            "ytick.labelsize": 6.8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(7.2, 5.35))
    grid = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.34, 1.10],
        left=0.105,
        right=0.985,
        top=0.87,
        bottom=0.26,
        wspace=0.18,
    )
    ax_matrix = fig.add_subplot(grid[0, 0])
    ax_models = fig.add_subplot(grid[0, 1])

    cmap = ListedColormap(["#F5F5F5", PALETTE["blue"], PALETTE["purple"], PALETTE["amber"]])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    ax_matrix.imshow(class_matrix.to_numpy(), cmap=cmap, norm=norm, aspect="equal")
    ax_matrix.set_xticks(np.arange(n_channels))
    ax_matrix.set_xticklabels(channels, rotation=58, ha="right", rotation_mode="anchor")
    ax_matrix.set_yticks(np.arange(n_channels))
    ax_matrix.set_yticklabels(channels)
    ax_matrix.set_xlabel("Formal predictor")
    ax_matrix.set_ylabel("Target channel")
    ax_matrix.set_title("(a) Production-active topology matrix", loc="left")
    ax_matrix.grid(False)
    for boundary in np.arange(-0.5, n_channels + 0.5, 1.0):
        ax_matrix.axhline(boundary, color="white", linewidth=0.45, zorder=2)
        ax_matrix.axvline(boundary, color="white", linewidth=0.45, zorder=2)
    group_boundary = sum(channel.startswith("DO_") for channel in channels) - 0.5
    ax_matrix.axhline(group_boundary, color="0.35", linewidth=0.9, zorder=3)
    ax_matrix.axvline(group_boundary, color="0.35", linewidth=0.9, zorder=3)
    for index, channel in enumerate(channels):
        if channel in excluded:
            ax_matrix.add_patch(
                Rectangle(
                    (index - 0.5, -0.5),
                    1.0,
                    n_channels,
                    facecolor="none",
                    edgecolor="0.60",
                    hatch="////",
                    linewidth=0.65,
                    zorder=4,
                )
            )
    for spine in ax_matrix.spines.values():
        spine.set_visible(True)
    ax_matrix.tick_params(
        axis="both",
        which="major",
        direction="in",
        top=True,
        right=True,
        labeltop=False,
        labelright=False,
        length=3.2,
    )

    ax_models.set_xlim(0, 1)
    ax_models.set_ylim(n_channels - 0.5, -1.35)
    ax_models.set_xticks([])
    ax_models.set_yticks([])
    for spine in ax_models.spines.values():
        spine.set_visible(False)
    ax_models.set_title("(b) Effective model specification", loc="left")
    ax_models.text(0.00, -0.84, "Target", ha="left", va="center",
                   fontsize=6.8, fontweight="bold")
    ax_models.text(0.29, -0.84, "Formal predictors", ha="left", va="center",
                   fontsize=6.8, fontweight="bold")
    ax_models.text(0.97, -0.84, "p / k", ha="right", va="center",
                   fontsize=6.8, fontweight="bold")
    ax_models.axhline(-0.5, color="0.35", linewidth=0.65, zorder=2)

    for row_index, channel in enumerate(channels):
        model = model_summary.loc[channel]
        is_limited = model["redundancy_status"] == "limited_single_peer"
        background = "#FFF4D4" if is_limited else ("#F6F8FA" if row_index % 2 else "white")
        ax_models.add_patch(
            Rectangle((0, row_index - 0.47), 1, 0.94, facecolor=background,
                      edgecolor="none", zorder=0)
        )
        peers = ", ".join(_parse_peers(model["formal_predictors"]))
        ax_models.text(0.00, row_index, channel, ha="left", va="center",
                       fontsize=6.45, fontweight="bold" if is_limited else "normal")
        ax_models.text(0.29, row_index, peers, ha="left", va="center", fontsize=6.2)
        ax_models.text(
            0.97,
            row_index,
            f"{int(model['n_peers'])} / {int(model['n_components'])}",
            ha="right",
            va="center",
            fontsize=6.3,
            fontweight="bold" if is_limited else "normal",
        )
        ax_models.axhline(row_index + 0.5, color="0.87", linewidth=0.4, zorder=1)
    ax_models.axhline(group_boundary, color="0.35", linewidth=0.9, zorder=2)
    legend_handles = [
        Patch(facecolor=PALETTE["blue"], label="Same-train adjacent core"),
        Patch(facecolor=PALETTE["purple"], label="Same-position twin-pool core"),
    ]
    if (class_matrix == 3).to_numpy().any():
        legend_handles.append(
            Patch(facecolor=PALETTE["amber"], label="Validated second-order addition")
        )
    if excluded:
        legend_handles.append(
            Patch(facecolor="white", edgecolor="0.60", hatch="////",
                  label="Excluded as predictor (process floor)")
        )
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.075),
        ncol=2,
        frameon=False,
        fontsize=6.7,
        handlelength=1.6,
        columnspacing=1.5,
    )
    fig.text(
        0.5,
        0.012,
        "Rows are targets and columns are predictors; only production-active links are shown. "
        "DO_1_4 is excluded as a predictor, and DO_2_2 to DO_2_4 was rejected in Fig. 11.\n"
        "Validation depth: DO_2_4 uses the full forward/hold-out/injection audit; other targets "
        "use topology-constrained three-fold blocked CV. p = peer count; k = retained components.",
        ha="center",
        va="bottom",
        fontsize=6.15,
        color="0.28",
    )
    fig.suptitle(
        "Supplementary Figure S1. Formal PLS peer topology used in D1 drift scoring",
        x=0.105,
        y=0.965,
        ha="left",
        fontsize=9.2,
        fontweight="bold",
    )
    return fig


def export_source_workbook(state: dict, tables: dict[str, pd.DataFrame]) -> Path:
    output = PLOT_DATA_DIR / f"{FIGURE_STEM}_data.xlsx"
    metadata = pd.DataFrame(
        [
            {
                "run_id": state.get("run_id"),
                "algorithm_version": state.get("algorithm_version"),
                "figure_role": "formal production PLS peer topology",
                "source_state": "v11_state.pkl",
            }
        ]
    )
    codebook = pd.DataFrame(
        [
            {"code": 0, "meaning": "not selected"},
            {"code": 1, "meaning": "same-train adjacent core"},
            {"code": 2, "meaning": "same-position twin-pool core"},
            {"code": 3, "meaning": "validated same-train second-order addition"},
        ]
    )
    PLOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="figure_metadata", index=False)
        tables["formal_peer_matrix"].to_excel(
            writer, sheet_name="formal_peer_matrix", index_label="target"
        )
        tables["topology_class_matrix"].to_excel(
            writer, sheet_name="topology_class_matrix", index_label="target"
        )
        tables["topology_label_matrix"].to_excel(
            writer, sheet_name="topology_label_matrix", index_label="target"
        )
        tables["formal_model_summary"].to_excel(
            writer, sheet_name="formal_model_summary", index=False
        )
        tables["formal_peer_pairs"].to_excel(
            writer, sheet_name="formal_peer_pairs", index=False
        )
        tables["predictor_exclusions"].to_excel(
            writer, sheet_name="predictor_exclusions", index=False
        )
        codebook.to_excel(writer, sheet_name="codebook", index=False)
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                values = [str(cell.value) if cell.value is not None else "" for cell in column_cells]
                width = min(max(max(map(len, values), default=0) + 2, 11), 54)
                worksheet.column_dimensions[column_cells[0].column_letter].width = width
    return output


def main() -> None:
    with open(ROOT / "v11_state.pkl", "rb") as handle:
        state = pickle.load(handle)
    tables = build_peer_tables(state)
    figure = make_figure(state, tables)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    save_publication_bundle(
        figure,
        FIGURE_DIR / FIGURE_STEM,
        version_label=state.get("algorithm_version", "unknown"),
    )
    plt.close(figure)
    svg_path = FIGURE_DIR / f"{FIGURE_STEM}.svg"
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )
    workbook = export_source_workbook(state, tables)
    print(
        f"[OK] {FIGURE_STEM}: {len(tables['formal_peer_pairs'])} formal edges; "
        f"source={workbook.name}"
    )


if __name__ == "__main__":
    main()
