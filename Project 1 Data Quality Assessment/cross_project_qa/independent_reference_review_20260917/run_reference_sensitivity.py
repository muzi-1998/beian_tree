"""Compare reference admission on identical evidence; never select production thresholds."""
from __future__ import annotations

import copy
import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
D3 = PROJECT / "D3 Physical rationality and rate constraints"
D4 = PROJECT / "D4 Parallel-redundancy Temporal Consistency"
sys.path.insert(0, str(D4 / "src"))
from d4.config import load_config
from d4.pipeline import _add_context, _fit_and_score, _load_interpretation
from d4.scoring import aggregate_scores, score_from_quantiles


def comparison(left, right, key, value, threshold=3.0):
    joined = left[key + [value]].merge(right[key + [value]], on=key, suffixes=("_old", "_new"), validate="one_to_one")
    rows = []
    for identity, group in joined.groupby(key[-1]):
        valid = group[[value + "_old", value + "_new"]].dropna()
        a, b = valid[value + "_old"], valid[value + "_new"]
        low_a, low_b = a.lt(threshold), b.lt(threshold)
        union = (low_a | low_b).sum()
        rows.append({"identity": identity, "n_common": len(valid), "mean_delta": (b-a).mean(),
                     "mean_abs_delta": (b-a).abs().mean(), "max_abs_delta": (b-a).abs().max(),
                     "old_low_hours": int(low_a.sum()), "new_low_hours": int(low_b.sum()),
                     "low_window_jaccard": (low_a & low_b).sum()/union if union else np.nan,
                     "spearman": a.corr(b, method="spearman") if a.nunique()>1 and b.nunique()>1 else np.nan})
    return pd.DataFrame(rows)


def d3_audit():
    old = pd.read_parquet(HERE / "frozen_baseline/D3_scores.parquet")
    current = pd.read_excel(D3 / "outputs/data/D3_window_scores.xlsx")
    delta = comparison(old, current, ["ts", "sensor_id"], "D3_total")
    delta = delta.rename(columns={"old_low_hours": "old_low_2h_windows", "new_low_hours": "new_low_2h_windows"})
    joined = old[["ts", "sensor_id", "D3_gate_status"]].merge(
        current[["ts", "sensor_id", "D3_gate_status"]], on=["ts", "sensor_id"], suffixes=("_old", "_new"), validate="one_to_one")
    gate = joined.groupby(["sensor_id", "D3_gate_status_old", "D3_gate_status_new"], dropna=False).size().rename("n_2h_windows").reset_index()
    lock = json.loads((HERE / "neutral_alpha_lock.json").read_text())
    print("D3 alpha lock", lock, flush=True)
    book = D3 / "outputs/validation/D3_temperature_conditioned_DO_upper.xlsx"
    registry = pd.read_excel(book, sheet_name="frozen_registry_check")
    warning = pd.read_excel(book, sheet_name="reference_comparison")
    # Legacy field names are retained upstream solely for file-schema compatibility.
    warning = warning.rename(columns={c: c.replace("high_quality", "neutral_eligible").replace("_hq_", "_neutral_") for c in warning})
    detail = pd.read_parquet(D3 / "outputs/validation/D3_temperature_conditioned_DO_upper.parquet")
    baseline = pd.read_parquet(HERE / "frozen_baseline/D3_screened_reference.parquet")
    detail = detail.merge(baseline[["ts", "sensor_id", "frozen_alpha"]], on=["ts", "sensor_id"], suffixes=("", "_screened"), validate="one_to_one")
    detail["screened_warning"] = detail.DO_minute_mg_L.gt(detail.frozen_alpha_screened * detail.Csat_reference_mg_L)
    event_rows = []
    for (sensor, phase), group in detail.loc[detail.high_quality_evaluable].groupby(["sensor_id", "phase"]):
        a, b = group.screened_warning, group.dynamic_warning
        event_rows.append({"sensor_id": sensor, "phase": phase, "n_neutral_minutes": len(group),
                           "screened_warning_minutes": int(a.sum()), "neutral_warning_minutes": int(b.sum()),
                           "warning_minute_jaccard": (a & b).sum()/(a | b).sum() if (a | b).any() else np.nan,
                           "screened_alpha": group.frozen_alpha_screened.iloc[0], "neutral_alpha": group.frozen_alpha.iloc[0]})
    events = pd.DataFrame(event_rows)
    with pd.ExcelWriter(HERE / "D3_reference_comparison.xlsx") as writer:
        for name, frame in {"alpha_registry": registry, "same_support_warning": warning, "warning_overlap": events,
                            "score_delta": delta, "gate_transition": gate}.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return {"alpha": events.drop_duplicates("sensor_id")[["sensor_id", "screened_alpha", "neutral_alpha"]],
            "warning": warning, "delta": delta}


def d4_audit():
    cfg = load_config(D4 / "configs/d4.yaml", PROJECT)
    raw = pd.read_parquet(D4 / "outputs/data/D4_neutral_core_input.parquet")
    primary = pd.read_excel(D4 / "outputs/data/D4_main_scores.xlsx")
    old = pd.read_parquet(HERE / "frozen_baseline/D4_scores.parquet")
    baseline_delta = comparison(old, primary, ["timestamp", "pair_id"], "D4_total")
    primary_fit, primary_params, benchmark = _fit_and_score(raw, cfg)
    np.testing.assert_allclose(primary_fit.D4_raw, primary.D4_raw, equal_nan=True, atol=1e-12)
    d1, d2, _, _ = _load_interpretation(cfg)
    regime = raw.drop_duplicates("timestamp").set_index("timestamp").regime_id
    annotated = _add_context(raw, d1, d2, regime, cfg)
    results, mappings, admissions = [], [], []
    variants = [("D1D2_screened", "screened_sensitivity", .90), ("purity_080", "neutral_primary", .80),
                ("purity_100", "neutral_primary", 1.0)]
    for name, route, purity in variants:
        params = copy.deepcopy(cfg.benchmark)
        params.update(reference_route=route, context_min_purity=purity)
        scores, mapping, admitted = _fit_and_score(annotated, replace(cfg, benchmark=params))
        scores.to_parquet(HERE / f"D4_{name}_scores.parquet", index=False)
        results.append(comparison(primary, scores, ["timestamp", "pair_id"], "D4_total").assign(scenario=name))
        mappings.append(mapping.assign(scenario=name))
        admissions.append({"scenario": name, "admitted_pair_hours": len(admitted)})
        print(name, len(admitted), flush=True)
    # Predeclared robust alternatives use the SAME reference pool/scope. No tuning on validation.
    levels = cfg.benchmark["quantiles"]
    anchor = pd.Timestamp(cfg.phase_contract["development_start"])
    for variant in ("block_median_quantiles", "winsor_p99", "leave_high_risk_block_out"):
        candidate = primary_fit.copy()
        rows = []
        for _, param in primary_params.loc[primary_params.mapping_role.eq("production")].iterrows():
            pool = benchmark.loc[benchmark.variable.eq(param.variable)]
            if param.mapping_scope == "variable_regime_public":
                pool = pool.loc[pool.regime_id.eq(param.regime_id)]
            elif param.mapping_scope == "global_normalized_fallback":
                pool = benchmark
            pool = pool.loc[pool[param.risk_metric].notna()].copy()
            pool["block"] = (pd.to_datetime(pool.timestamp)-anchor).dt.days // 7
            if variant == "block_median_quantiles":
                thresholds = pool.groupby("block")[param.risk_metric].quantile(levels).unstack().median().to_numpy()
            elif variant == "winsor_p99":
                values = pool[param.risk_metric].clip(upper=pool[param.risk_metric].quantile(.99))
                thresholds = values.quantile(levels).to_numpy()
            else:
                worst = pool.groupby("block")[param.risk_metric].median().idxmax()
                thresholds = pool.loc[pool.block.ne(worst), param.risk_metric].quantile(levels).to_numpy()
            mask = candidate.variable.eq(param.variable) & candidate.regime_id.eq(param.regime_id)
            candidate.loc[mask, param.subscore] = score_from_quantiles(candidate.loc[mask, param.risk_metric].to_numpy(), thresholds)
            rows.append({"scenario": variant, "variable": param.variable, "regime_id": param.regime_id,
                         "subscore": param.subscore, **dict(zip(["q50", "q75", "q90", "q97_5"], thresholds))})
        candidate.loc[candidate.deadband_active, "Q_var"] = 5.0
        _, candidate["D4_raw"] = aggregate_scores(*(candidate[c].to_numpy() for c in ["Q_dist", "Q_trend", "Q_var", "Q_cp"]), weights=cfg.weights, lambda_blend=cfg.lambda_blend)
        candidate["D4_total"] = candidate.D4_raw.where(candidate.usable_for_D4)
        results.append(comparison(primary, candidate, ["timestamp", "pair_id"], "D4_total").assign(scenario=variant))
        mappings.append(pd.DataFrame(rows))
    sensitivity = pd.concat(results, ignore_index=True)
    params = pd.concat([primary_params.assign(scenario="neutral_primary"), *mappings], ignore_index=True)
    with pd.ExcelWriter(HERE / "D4_reference_comparison.xlsx") as writer:
        for name, frame in {"same_evidence_sensitivity": sensitivity, "mapping": params,
                            "admission": pd.DataFrame(admissions), "frozen_old_vs_new_combined": baseline_delta}.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return sensitivity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-d4", action="store_true", help="Reuse completed, unchanged D4 sensitivity tables")
    args = parser.parse_args()
    HERE.mkdir(parents=True, exist_ok=True)
    d3 = d3_audit()
    d4 = (pd.read_excel(HERE / "D4_reference_comparison.xlsx", sheet_name="same_evidence_sensitivity")
          if args.reuse_d4 else d4_audit())
    from d4.figure_style import configure_style, finalize, panel_label
    import matplotlib.pyplot as plt
    configure_style()
    plt.rcParams.update({"font.family": "Arial", "font.size": 7,
                         "svg.fonttype": "none", "pdf.fonttype": 42})
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.7), layout="constrained")
    alpha = d3["alpha"].groupby(d3["alpha"].sensor_id.str[-1]).first()
    for _, row in alpha.iterrows():
        p = int(row.sensor_id[-1])
        axes[0,0].plot([0,1], [row.screened_alpha, row.neutral_alpha], marker="o", label=f"Position {p}")
    axes[0,0].set(xticks=[0,1], xticklabels=["D1/D2 screened", "Neutral raw"], ylabel=r"Envelope coefficient $\alpha$", title="D3 reference admission")
    axes[0,0].legend()
    w = d3["warning"].loc[d3["warning"].phase.eq("validation")]
    sensors = sorted(w.sensor_id.unique())
    for offset, (name, frame) in zip([-.12,.12], w.groupby("reference_route")):
        vals = frame.set_index("sensor_id").reindex(sensors)
        axes[0,1].scatter(np.arange(6)+offset, vals.warning_2h_window_rate_neutral_eligible*100,
                          marker="s" if "screened" in name else "o", label="Screened" if "screened" in name else "Neutral")
    axes[0,1].set(xticks=np.arange(6), xticklabels=sensors, ylabel="2 h warning windows (%)", title="Same neutral evaluation support")
    axes[0,1].tick_params(axis="x", labelrotation=50)
    axes[0,1].axhline(2, color="gray", ls="--", lw=.7)
    axes[0,1].legend()
    primary = d4.loc[d4.scenario.eq("D1D2_screened")]
    axes[1,0].barh(primary.identity, primary.mean_delta, color="#0072B2")
    axes[1,0].axvline(0, color="gray", lw=.7)
    axes[1,0].set(xlabel="Screened minus neutral mean D4", title="D4: admission-only contrast")
    for n, (name, group) in enumerate(d4.groupby("scenario", sort=False)):
        axes[1,1].scatter(group.mean_abs_delta, np.full(len(group), n), s=16, alpha=.75)
    names = [n for n, _ in d4.groupby("scenario", sort=False)]
    axes[1,1].set(yticks=range(len(names)), yticklabels=[n.replace("_", " ") for n in names], xlabel="Mean absolute D4 difference", title="Sensitivity only; no model selection")
    axes[1,1].yaxis.set_label_position("right")
    axes[1,1].yaxis.tick_right()
    for ax, letter in zip(axes.flat,"abcd"):
        ax.spines[["top","right"]].set_visible(False)
        panel_label(ax, letter)
    axes[1,1].spines["left"].set_visible(False)
    axes[1,1].spines["right"].set_visible(True)
    finalize(fig)
    fig.savefig(HERE / "Fig_reference_admission_sensitivity.png", dpi=600)
    fig.savefig(HERE / "Fig_reference_admission_sensitivity.pdf")
    fig.savefig(HERE / "Fig_reference_admission_sensitivity.svg")
    fig.savefig(HERE / "Fig_reference_admission_sensitivity.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    svg = HERE / "Fig_reference_admission_sensitivity.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n", encoding="utf-8")
    plt.close(fig)
    manifest = {"role": "sensitivity_only_no_threshold_selection", "contrast": "same_raw_metrics_and_frozen_context",
                "historical_comparison": "joint_raw_support_context_and_admission_revision_not_admission_only",
                "future_period_claim": "revised_temporal_out_of_sample_re_evaluation_not_first_blind_validation",
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob("*.xlsx")}}
    (HERE / "sensitivity_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(d3["delta"].to_string(index=False))
    print(d4.to_string(index=False))


if __name__ == "__main__":
    main()
