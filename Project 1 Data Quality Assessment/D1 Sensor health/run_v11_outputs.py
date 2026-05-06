"""run_v11_outputs.py
Generate v1.1 figures and Excel files using cached v11 results.
"""
from __future__ import annotations
import sys, time, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from v11.figures_v11 import make_all_v11_figures
from v11.excel_exporter_v11 import export_all_v11


V11_DIR = Path("/mnt/user-data/outputs/d1_fsd_results/v11")


def main():
    t0 = time.time()
    print("=" * 80)
    print("D1 FSD v1.1 — outputs generation")
    print("=" * 80)

    print("[1] Loading v11 cache ...")
    with open("/home/claude/d1_fsd/cache/results_v11.pkl", "rb") as f:
        R = pickle.load(f)
    print(f"    Loaded; D1_h_v11 shape {R['D1_h_v11'].shape}")

    print("[2] Generating v11 Excel files ...")
    excel_paths = export_all_v11(R, V11_DIR / "data",
                                   V11_DIR / "state_blackboard.json")
    print(f"    {len(excel_paths)} Excel files written.")

    print("[3] Generating v11 figures ...")
    fig_paths = make_all_v11_figures(R, V11_DIR / "figures",
                                       V11_DIR / "plot_data")
    print(f"    {len(fig_paths)-1} figures + 1 plot-data workbook written.")

    elapsed = time.time() - t0
    print(f"\nDONE in {elapsed/60:.1f} min")
    print(f"Outputs at: {V11_DIR}")


if __name__ == "__main__":
    main()
