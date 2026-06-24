"""Generate project directory PDF with script descriptions."""
from pathlib import Path
from datetime import date
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).parent
OUT_PDF = ROOT / "outputs" / "D1_Project_Directory.pdf"

# ─── Script catalogue ───────────────────────────────────────────────────────
# Format: (relative_path, one-line description)
SCRIPTS = [
    # ── Entry-point scripts (root) ──────────────────────────────────────────
    ("load_real_data_v11.py",
     "# [ENTRY] Load 1-min/1-h data; run Hampel/KS/PLS/Freeze/Regime detectors; "
     "cache strict_v1_inputs.pkl"),
    ("run_v11_pipeline.py",
     "# [ENTRY] Run 5-state cooldown machine; re-aggregate D1 v1.1; "
     "save v11_state.pkl (32 MB)"),
    ("make_baseline_figures_v11.py",
     "# [ENTRY] Generate Fig 1–11 baseline figures (D1 matrix, heatmap, "
     "violin, regime, PLS…)"),
    ("make_figures_v11.py",
     "# [ENTRY] Generate Fig V12–V15 (v1.1 vs STRICT V1 hero, state machine, "
     "Veto-3, PELT)"),
    ("make_figures_v11_part2.py",
     "# [ENTRY] Generate Fig V16–V18 (regime templates, QR/QIR scope, "
     "aggregate summary)"),
    ("excel_exporter_v11.py",
     "# [ENTRY] Export 16 Excel deliverables to outputs/data/ "
     "(scores, events, audit, QR/QIR…)"),
    ("run_v12_P2_sensitivity.py",
     "# [OPT-P2] Regime sensitivity: R30/R60/R90/R60W14 variants → "
     "10 figures + 13 CSVs in outputs/v12_P2/"),
    ("generate_mock_data.py",
     "# [UTIL] Generate synthetic DO/ORP mock dataset for unit testing"),

    # ── src/detectors/ ───────────────────────────────────────────────────────
    ("src/detectors/base.py",
     "# Abstract BaseDetector interface; defines score() contract"),
    ("src/detectors/spike_hampel.py",
     "# HampelSpikeDetector: MAD outlier on 1-min window=21; "
     "6h rolling mean → hourly Q_spike"),
    ("src/detectors/freeze_response_loss.py",
     "# CompositeFreezeDetector: RLE + low-variance + unique-ratio "
     "on 1-min → hourly Q_freeze"),
    ("src/detectors/freeze_rules.py",
     "# Hard freeze rules & break-point scoring (15/30/60/360 min thresholds)"),
    ("src/detectors/step_adjacent_ks.py",
     "# AdjacentKSStepDetector: dual-window KS (24h + 36h) → Q_step"),
    ("src/detectors/drift_pls.py",
     "# PLSVirtualSensorDetector: cross-channel PLS residual → Q_drift"),
    ("src/detectors/regime_two_tier.py",
     "# TwoTierRegimeDetector: Wasserstein (Tier-1) + adjacent KS (Tier-2); "
     "static R90 reference"),
    ("src/detectors/pelt_batch.py",
     "# PELT change-point detection (ruptures) across all scored channels"),
    ("src/detectors/ffpca_aux.py",
     "# FF-PCA auxiliary anomaly detector (experimental, offline only)"),

    # ── src/mapping/ ─────────────────────────────────────────────────────────
    ("src/mapping/mapper.py",
     "# Raw detector score → [1,5] quality score via logistic / linear mapping"),
    ("src/mapping/__init__.py",
     "# Package init"),

    # ── src/aggregation/ ─────────────────────────────────────────────────────
    ("src/aggregation/d1_aggregator.py",
     "# Weighted D1_base + D1_pre computation; applies Veto rules 1/2/3"),
    ("src/aggregation/cooldown_state_machine.py",
     "# 5-state FSM: Normal→Refractory→SustainedAnomaly→RecoveryCandidate→Recovered"),
    ("src/aggregation/multiscale_export.py",
     "# Aggregate hourly D1 → daily / weekly multi-scale summaries"),
    ("src/aggregation/process_aware_mask.py",
     "# Process-aware masking (maintenance windows, startup transients)"),
    ("src/aggregation/__init__.py",
     "# Package init"),

    # ── src/pipeline/ ────────────────────────────────────────────────────────
    ("src/pipeline/d1_pipeline.py",
     "# STRICT V1 pipeline orchestrator (original D1 v1.0)"),
    ("src/pipeline/d1_pipeline_v11.py",
     "# D1 v1.1 pipeline: wraps state machine + signal-only Veto-3"),
    ("src/pipeline/window_manager.py",
     "# WindowManager: 16 named scoring windows (spike/step/drift/freeze/regime)"),
    ("src/pipeline/__init__.py",
     "# Package init"),

    # ── src/state/ ───────────────────────────────────────────────────────────
    ("src/state/state_blackboard.py",
     "# StateBlackboard: shared in-memory store for per-channel FSM state"),
    ("src/state/auxiliary_modules.py",
     "# Auxiliary state helpers: event uniqueness, refractory duration logic"),
    ("src/state/__init__.py",
     "# Package init"),

    # ── src/baseline/ ────────────────────────────────────────────────────────
    ("src/baseline/deperiodise.py",
     "# Harmonic decomposition: remove daily (T=24h) + weekly (T=168h) seasonality"),
    ("src/baseline/local_baseline.py",
     "# Local rolling baseline (median ± IQR) for residual normalisation"),
    ("src/baseline/regime_clustering.py",
     "# k-means regime template clustering (k=4) for FigV16 visualisation"),
    ("src/baseline/__init__.py",
     "# Package init"),

    # ── src/config/ ──────────────────────────────────────────────────────────
    ("src/config/loader.py",
     "# YAML config loader: reads mapping.yaml / state_machine.yaml / rules.yaml"),
    ("src/config/models.py",
     "# Pydantic config models: CooldownConfig, MappingConfig, WeightConfig"),
    ("src/config/__init__.py",
     "# Package init"),

    # ── src/data/ ────────────────────────────────────────────────────────────
    ("src/data/loader.py",
     "# Data loader: read Excel raw data → df_h (1h) + df_min (1min) DataFrames"),
    ("src/data/__init__.py",
     "# Package init"),
]

# ─── Directory tree structure ────────────────────────────────────────────────
TREE_LINES = [
    ("D1 Sensor health/                    # Project root", 0),
    ("├── load_real_data_v11.py            # ENTRY: data loading + all detectors", 1),
    ("├── run_v11_pipeline.py              # ENTRY: state machine + D1 v1.1", 1),
    ("├── make_baseline_figures_v11.py     # ENTRY: Fig 1-11", 1),
    ("├── make_figures_v11.py              # ENTRY: Fig V12-V15", 1),
    ("├── make_figures_v11_part2.py        # ENTRY: Fig V16-V18", 1),
    ("├── excel_exporter_v11.py            # ENTRY: 16 Excel deliverables", 1),
    ("├── run_v12_P2_sensitivity.py        # OPT-P2: regime sensitivity", 1),
    ("├── generate_mock_data.py            # UTIL: synthetic test data", 1),
    ("├── generate_project_pdf.py          # UTIL: this PDF generator", 1),
    ("│", 0),
    ("├── configs/                         # YAML configuration files", 1),
    ("│   ├── mapping.yaml                 # Score mapping: logistic k=8,x0=0.40", 2),
    ("│   ├── state_machine.yaml           # FSM params: refractory=48h, recovery=12h", 2),
    ("│   ├── rules.yaml                   # Veto rules & thresholds", 2),
    ("│   ├── windows.yaml                 # 16 scoring window definitions", 2),
    ("│   └── paths.yaml                   # Data / cache / output paths", 2),
    ("│", 0),
    ("├── src/                             # Core library (importable package)", 1),
    ("│   ├── detectors/                   # Detection algorithms", 2),
    ("│   │   ├── spike_hampel.py          # Hampel MAD spike detector (1-min)", 3),
    ("│   │   ├── freeze_response_loss.py  # Composite freeze detector (1-min)", 3),
    ("│   │   ├── freeze_rules.py          # Freeze hard/soft rules & breakpoints", 3),
    ("│   │   ├── step_adjacent_ks.py      # Dual-window KS step detector", 3),
    ("│   │   ├── drift_pls.py             # PLS virtual sensor drift detector", 3),
    ("│   │   ├── regime_two_tier.py       # W1+KS regime detector (R90 baseline)", 3),
    ("│   │   ├── pelt_batch.py            # PELT batch change-point detector", 3),
    ("│   │   ├── ffpca_aux.py             # FF-PCA auxiliary (experimental)", 3),
    ("│   │   └── base.py                  # Abstract BaseDetector interface", 3),
    ("│   ├── mapping/                     # Score mapping", 2),
    ("│   │   └── mapper.py                # Raw score → [1,5] via logistic/linear", 3),
    ("│   ├── aggregation/                 # Scoring & state machine", 2),
    ("│   │   ├── d1_aggregator.py         # D1_base/pre + Veto-1/2/3 application", 3),
    ("│   │   ├── cooldown_state_machine.py# 5-state FSM per channel", 3),
    ("│   │   ├── multiscale_export.py     # Hourly → daily/weekly aggregation", 3),
    ("│   │   └── process_aware_mask.py    # Maintenance window masking", 3),
    ("│   ├── pipeline/                    # Pipeline orchestration", 2),
    ("│   │   ├── d1_pipeline_v11.py       # D1 v1.1 pipeline wrapper", 3),
    ("│   │   ├── window_manager.py        # 16 scoring window manager", 3),
    ("│   │   └── d1_pipeline.py           # STRICT V1 pipeline (original)", 3),
    ("│   ├── baseline/                    # Baseline computation", 2),
    ("│   │   ├── deperiodise.py           # Harmonic decomposition (24h+168h)", 3),
    ("│   │   ├── local_baseline.py        # Rolling median/IQR baseline", 3),
    ("│   │   └── regime_clustering.py     # k=4 regime template clustering", 3),
    ("│   ├── config/                      # Configuration loading", 2),
    ("│   │   ├── loader.py                # YAML config reader", 3),
    ("│   │   └── models.py                # Pydantic config models", 3),
    ("│   └── data/                        # Data I/O", 2),
    ("│       └── loader.py                # Excel → df_h / df_min", 3),
    ("│", 0),
    ("├── cache/                           # Intermediate pickles (auto-generated)", 1),
    ("│   ├── df_h_aligned.pkl             # Hourly aligned DataFrame", 2),
    ("│   ├── df_min_aligned.pkl           # Minute-level DataFrame", 2),
    ("│   ├── spike/freeze/step/drift_*.pkl# Per-detector cached results", 2),
    ("│   ├── regime_R90.pkl               # R90 regime scores (final baseline)", 2),
    ("│   └── strict_v1_inputs.pkl         # Merged detector outputs (10.9 MB)", 2),
    ("│", 0),
    ("└── outputs/                         # All deliverables", 1),
    ("    ├── figures/                      # Fig 1-11, FigV12-V18 (600 DPI PNG)", 2),
    ("    ├── data/                         # 16 Excel deliverables", 2),
    ("    ├── plot_data/                    # Per-figure xlsx data tables", 2),
    ("    └── v12_P2/                       # P2 regime sensitivity: 10 figures + CSVs", 2),
]

# ─── Key pipeline data flow ──────────────────────────────────────────────────
FLOW_LINES = [
    "DATA FLOW  (R90 baseline  |  255 days 2025-08-01~2026-04-13  |  14 scored channels)",
    "",
    "  Raw Excel data (1-min + 1-hour)",
    "       │",
    "       ▼  load_real_data_v11.py",
    "  ┌────────────────────────────────────────────────────┐",
    "  │  Detectors (on 1-min raw):                         │",
    "  │    HampelSpikeDetector   → Q_spike  (hourly mean)  │",
    "  │    CompositeFreezeDetect → Q_freeze (hourly max)   │",
    "  │  Detectors (on 1-hour):                            │",
    "  │    AdjacentKSStepDetect  → Q_step   (dual 24+36h)  │",
    "  │    PLSVirtualSensor      → Q_drift  (cross-channel)│",
    "  │    TwoTierRegimeDetect   → Q_regime (W1+KS, R90)   │",
    "  └───────────────── strict_v1_inputs.pkl ─────────────┘",
    "       │",
    "       ▼  Mapping (mapping.yaml: logistic k=8.0, x0=0.40)",
    "  [Q_raw] → [Q_mapped 1-5]  →  D1_base (weighted sum)",
    "       │",
    "       ▼  run_v11_pipeline.py",
    "  ┌────────────────────────────────────────────────────┐",
    "  │  5-State Cooldown FSM per channel:                 │",
    "  │    Normal → Refractory (48h) → SustainedAnomaly   │",
    "  │    → RecoveryCandidate (12h streak) → Recovered   │",
    "  │  Veto rules: freeze≤2→D1≤2; regime≤2→D1≤2.5;     │",
    "  │              Veto-3 (step≤2, ≥36h, ≥6ev)→D1≤2.5  │",
    "  └───────────────── v11_state.pkl (32 MB) ───────────┘",
    "       │",
    "       ▼  Figure scripts + Excel exporter",
    "  outputs/figures/  (18 SCI PNG, 600 DPI)",
    "  outputs/data/     (16 Excel deliverables)",
]

# ─── Configuration summary ───────────────────────────────────────────────────
CONFIG_LINES = [
    "KEY CONFIGURATION  (configs/*.yaml)",
    "",
    "  Weights:   spike=0.15  step=0.20  drift=0.25  freeze=0.20  regime=0.20",
    "  Lambda:    0.70  (D1_pre = 0.70×D1_base + 0.30×min(Q_*) )",
    "",
    "  Mapping (configs/mapping.yaml):",
    "    step:    logistic  k=8.0   x0=0.40   [P1-2 relaxed from k=12/x0=0.30]",
    "    spike:   logistic  k=3.0   x0=0.50",
    "    freeze:  logistic  k=4.0   x0=0.50",
    "    drift:   logistic  k=1.5   x0=2.50",
    "    regime:  logistic  k=1.8   x0=1.00",
    "",
    "  State Machine (configs/state_machine.yaml):",
    "    refractory.step_h        = 48 h   [P1-3 extended from 24h]",
    "    event_uniqueness.min_sep = 24 h   [P1-3 extended from 12h]",
    "    recovery.Q_step_min      = 3.0    [P1-4 relaxed from 3.2]",
    "    recovery.Q_freeze_min    = 3.0    [P1-4 relaxed from 3.5]",
    "    recovery.min_streak_h    = 12 h   [P1-4 shortened from 24h]",
    "",
    "  Regime (R90 final baseline):",
    "    ref_days = 90   (2025-08-01 ~ 2025-10-29, 35% of 255-day dataset)",
    "    w1_win_days = 7  ks_win_days = 7",
    "    Scoring starts day 7 (W1) / day 14 (KS) — NOT after ref period",
    "    Scorable period: 165 days (day 7 to day 255)",
]

# ─── Results summary ─────────────────────────────────────────────────────────
RESULTS_LINES = [
    "PIPELINE RESULTS  (R90 baseline, v1.1 with P1 optimisations)",
    "",
    "  D1_strict_V1 mean : 3.667  (pre-state-machine baseline)",
    "  D1_v1.1 mean      : 3.527  (Δ = -0.140 after FSM + signal-only Veto-3)",
    "",
    "  State coverage (all 14 channels × 6138 h = 85 932 channel-hours):",
    "    Normal            : 67.1%",
    "    Refractory        : 19.3%",
    "    SustainedAnomaly  : 12.5%",
    "    RecoveryCandidate :  1.2%",
    "    Recovered         :  0.03%",
    "",
    "  Per-channel D1_v1.1 range: 3.15 (ORP_1_3) ~ 3.78 (DO_1_2)",
    "  Largest drop: DO_2_1  ΔD1 = -0.369 (25% SustainedAnomaly)",
    "  Smallest drop: DO_1_4  ΔD1 = -0.016 (93% Normal)",
    "",
    "  Regime sensitivity (P2, 90-day common period skip):",
    "    R30  Q_regime_mean=3.44  Q_regime<2%=8.3%",
    "    R60  Q_regime_mean=3.52  Q_regime<2%=5.1%",
    "    R90  Q_regime_mean=3.61  Q_regime<2%=2.7%  ← selected",
    "    R60W14  Q_regime_mean=3.49  Q_regime<2%=6.8%",
]


def make_page(pdf, lines, title, fontsize=7.8, bg="#F7F9FB", col="#1A1A2E",
              mono=True):
    fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.axis("off")

    # Header bar
    hbar = mpatches.FancyBboxPatch((0, 0.965), 1, 0.035,
                                    boxstyle="square,pad=0", linewidth=0,
                                    facecolor="#1B4F72", transform=ax.transAxes,
                                    clip_on=False)
    ax.add_patch(hbar)
    ax.text(0.012, 0.981, title, transform=ax.transAxes,
            fontsize=10, fontweight="bold", color="white", va="center",
            fontfamily="DejaVu Sans Mono" if mono else "DejaVu Sans")
    ax.text(0.988, 0.981,
            f"D1 Sensor Health  |  R90 baseline  |  {date.today()}",
            transform=ax.transAxes, fontsize=7.5, color="#BDC3C7",
            ha="right", va="center")

    # Body text
    body = "\n".join(lines)
    ax.text(0.012, 0.955, body, transform=ax.transAxes,
            fontsize=fontsize, va="top", color=col,
            fontfamily="DejaVu Sans Mono" if mono else "DejaVu Sans",
            linespacing=1.55, wrap=False)

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


def fmt_scripts_page(scripts):
    """Format script list as lines for display."""
    out = []
    current_group = None
    group_map = {
        "": "Entry-point scripts (project root)",
        "src/detectors": "src/detectors/  —  Detection algorithms",
        "src/mapping": "src/mapping/  —  Score mapping",
        "src/aggregation": "src/aggregation/  —  Scoring & state machine",
        "src/pipeline": "src/pipeline/  —  Pipeline orchestration",
        "src/state": "src/state/  —  State management",
        "src/baseline": "src/baseline/  —  Baseline computation",
        "src/config": "src/config/  —  Configuration",
        "src/data": "src/data/  —  Data I/O",
    }

    def group_key(p):
        parts = Path(p).parts
        if len(parts) == 1:
            return ""
        return "/".join(parts[:2])

    pages = []
    current_lines = []
    for path, desc in scripts:
        gk = group_key(path)
        label = group_map.get(gk, gk)
        if gk != current_group:
            if current_group is not None:
                current_lines.append("")
            current_lines.append(f"  {'─'*60}")
            current_lines.append(f"  {label}")
            current_lines.append(f"  {'─'*60}")
            current_group = gk
        name = Path(path).name
        desc_short = desc.replace("# ", "").strip()
        # wrap description at ~75 chars
        prefix = f"  {name:<38s}  "
        if len(prefix) + len(desc_short) <= 100:
            current_lines.append(f"  {name:<38s}  {desc_short}")
        else:
            current_lines.append(f"  {name:<38s}")
            current_lines.append(f"    {desc_short}")
        if len(current_lines) > 52:
            pages.append(current_lines)
            current_lines = []
            current_group = None
    if current_lines:
        pages.append(current_lines)
    return pages


with PdfPages(OUT_PDF) as pdf:
    # Page 1 — Title page
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    fig.patch.set_facecolor("#1B4F72")
    ax.set_facecolor("#1B4F72")
    ax.axis("off")
    ax.text(0.5, 0.75,
            "Project D1\nSensor Health Assessment",
            transform=ax.transAxes, fontsize=28, fontweight="bold",
            color="white", ha="center", va="center", linespacing=1.6)
    ax.text(0.5, 0.60,
            "Python Project Directory",
            transform=ax.transAxes, fontsize=18, color="#AED6F1",
            ha="center", va="center")
    ax.text(0.5, 0.50,
            "DO / ORP Sensor Health  |  D1 v1.1 + P1 Optimisations",
            transform=ax.transAxes, fontsize=11, color="#85C1E9",
            ha="center", va="center")
    ax.text(0.5, 0.42,
            "255 days  |  2025-08-01 ~ 2026-04-13  |  14 scored channels",
            transform=ax.transAxes, fontsize=10, color="#AEB6BF",
            ha="center", va="center")
    ax.text(0.5, 0.32,
            f"Regime baseline: R90  (ref_days=90, w1/ks_win=7 days)\n"
            f"Generated: {date.today()}",
            transform=ax.transAxes, fontsize=10, color="#AEB6BF",
            ha="center", va="center", linespacing=1.7)
    # divider
    ax.axhline(0.27, xmin=0.1, xmax=0.9, color="#AED6F1", lw=0.6)
    ax.text(0.5, 0.21,
            "Contents\n"
            "  Page 2-3 : Directory tree\n"
            "  Page 4-6 : Script catalogue (all .py files)\n"
            "  Page 7   : Data flow diagram\n"
            "  Page 8   : Key configuration\n"
            "  Page 9   : Pipeline results",
            transform=ax.transAxes, fontsize=10, color="#D5D8DC",
            ha="center", va="center", linespacing=1.8)
    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)

    # Page 2-3 — Directory tree
    tree_text = [line for line, _ in TREE_LINES]
    make_page(pdf, tree_text[:55], "Directory Tree  (part 1/2)", fontsize=7.5)
    make_page(pdf, tree_text[55:], "Directory Tree  (part 2/2)", fontsize=7.5)

    # Page 4-6 — Script catalogue
    script_pages = fmt_scripts_page(SCRIPTS)
    for i, page_lines in enumerate(script_pages):
        make_page(pdf, page_lines,
                  f"Script Catalogue  (part {i+1}/{len(script_pages)})",
                  fontsize=7.5)

    # Page 7 — Data flow
    make_page(pdf, FLOW_LINES, "Data Flow Diagram", fontsize=8.0)

    # Page 8 — Configuration
    make_page(pdf, CONFIG_LINES, "Key Configuration", fontsize=8.0)

    # Page 9 — Results
    make_page(pdf, RESULTS_LINES, "Pipeline Results  (R90 baseline)", fontsize=8.0)

print(f"[OK] PDF saved: {OUT_PDF}")
print(f"     Pages: title + 2 tree + {len(script_pages)} catalogue + 3 detail = "
      f"{1+2+len(script_pages)+3} pages total")
