"""run_all.py
Top-level CLI: pipeline → 11 Excel deliverables → 9 SCI figures →
2 plot-data Excel → analysis report.
"""
from __future__ import annotations
import sys, time, pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline.d1_pipeline import run as run_pipeline
from outputs import export_all, make_all_figures, make_class_c_dim_matrix


OUTPUT_ROOT = Path("/mnt/user-data/outputs/d1_fsd_strict_results")
DATA_DIR    = OUTPUT_ROOT / "data"
FIG_DIR     = OUTPUT_ROOT / "figures"
PLOT_DIR    = OUTPUT_ROOT / "plot_data"
for d in (DATA_DIR, FIG_DIR, PLOT_DIR):
    d.mkdir(parents=True, exist_ok=True)


def main(use_cache: bool = True):
    cache_results = Path("/home/claude/d1_fsd_strict/cache/results.pkl")
    print("=" * 80)
    print("Class C-minDQR  D1 FSD STRICT V1 — full run")
    print("=" * 80)

    t0 = time.time()
    if use_cache and cache_results.exists():
        with open(cache_results, "rb") as f:
            R = pickle.load(f)
        print(f"[main] Loaded pipeline results from cache (D1_h shape {R['D1_h'].shape})")
    else:
        R = run_pipeline()
        with open(cache_results, "wb") as f:
            pickle.dump(R, f)

    print()
    print("[main] Generating Excel deliverables ...")
    excel_paths = export_all(R, DATA_DIR)

    print()
    print("[main] Generating SCI-grade figures ...")
    fig_paths = make_all_figures(R, FIG_DIR, PLOT_DIR)

    print()
    print("[main] Generating Class C 8-dimension reference figure ...")
    classC_fig, classC_data = make_class_c_dim_matrix(
        FIG_DIR / "FigC1_ClassC_8D_matrix.png")
    print(f"[main]   → {classC_fig}")

    import pandas as pd
    classC_data.to_excel(PLOT_DIR / "ClassC_8D_matrix_data.xlsx", index=False)

    elapsed = time.time() - t0
    print()
    print("=" * 80)
    print(f"DONE in {elapsed/60:.1f} min")
    print(f"Outputs at: {OUTPUT_ROOT}")
    print("=" * 80)
    return excel_paths, fig_paths, classC_fig


if __name__ == "__main__":
    main(use_cache=True)
