#!/usr/bin/env python
"""plot_data/replot.py — reproduce every §1.1 stacked / combined figure from the
data bundles in this directory.

The pipeline writes one bundle PER FIGURE into  outputs/plot_data/ :
    <name>.csv   the plotted series (column 'x' = ISO timestamp + one col/panel)
    <name>.json  the render spec (title, panels[col,ylabel,color], out_png, ...)

This script re-renders the PNGs (full-frame style) purely from those bundles via
the shared renderer in src/outputs/figstyle.py — no pipeline re-run, no raw data
needed. Run the pipeline once to populate outputs/plot_data/, then use this to
reproduce or restyle any figure.

Usage:
    python plot_data/replot.py                # re-render ALL bundles
    python plot_data/replot.py decomp_stack_DO_1_3 combined_DO   # selected
"""
from __future__ import annotations
import json
import sys
from glob import glob
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUNDLE_DIR = ROOT / "outputs" / "plot_data"          # where the pipeline dumps bundles
sys.path.insert(0, str(ROOT))

import pandas as pd                                   # noqa: E402
from src.outputs.figstyle import (setup_style, render_stack,   # noqa: E402
                                  render_grid)


def main(argv):
    setup_style()
    names = argv or sorted(Path(p).stem for p in glob(str(BUNDLE_DIR / "*.json")))
    if not names:
        print("no bundles found in", BUNDLE_DIR, "— run run_pipeline.py first")
        return
    for nm in names:
        jp = BUNDLE_DIR / f"{nm}.json"
        if not jp.exists():
            print("skip (no json):", nm)
            continue
        meta = json.loads(jp.read_text(encoding="utf-8"))
        df = pd.read_csv(BUNDLE_DIR / meta["csv"])
        out = Path(meta["out_png"])
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        if meta.get("kind") == "grid":
            render_grid(df, meta, out)
        else:
            render_stack(df, meta, out)
        print("replotted", nm, "->", out)


if __name__ == "__main__":
    main(sys.argv[1:])
