# plot_data/ — figure reproduction kit

Every stacked / combined figure produced by the pipeline is backed by a
**data bundle** so it can be reproduced or restyled without re-running the heavy
decomposition/whitening.

## Where things live
- **Reproduction script (version-controlled):** [`replot.py`](replot.py) — this folder.
- **Data bundles (regenerated, git-ignored):** `../outputs/plot_data/`
  - `<name>.csv` — the exact plotted series. Column `x` is the ISO timestamp
    (date/time x-axis); the remaining columns are the panels (one per subplot).
  - `<name>.json` — the render spec: `title`, `panels` (`col` / `ylabel` /
    `color`), `x_is_time`, `xlabel`, `out_png`, layout.

Bundle names mirror the figures:
`decomp_stack_<channel>` (per-variable 4-level decomposition) and
`combined_{DO,ORP,flow,influent,effluent}` (group overviews).

## Usage
```bash
# 1) populate ../outputs/plot_data/ (only needed once)
python run_pipeline.py

# 2) reproduce ALL figures from the bundles (no raw data / no re-run)
python plot_data/replot.py

# 2b) or just selected ones
python plot_data/replot.py decomp_stack_DO_1_3 combined_influent
```

`replot.py` renders through the same `src/outputs/figstyle.py` renderer the
pipeline uses, so the output is byte-for-byte the pipeline figure. The CSV holds
the real timestamps, so the same data can be re-plotted against a plain sample
index instead of dates if ever required.
