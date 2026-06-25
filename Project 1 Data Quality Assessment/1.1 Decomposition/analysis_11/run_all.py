"""analysis_11/run_all.py — run the three §1.1 results-analysis work-streams.

  Work 1  variance-contribution profile   (why differentiated decomposition)
  Work 2  residual-whitening efficacy      (core method + physical mechanism)
  Work 3  spike-event sanity check         (§1.1 sufficiency; detection → §1.2)

All three are manifest-driven (scoring_mode/group/zone), strictly causal, and
emit each figure's data to outputs/plot_data/.  Run from this directory:
    python run_all.py
"""
import work1_variance, work2_whitening, work3_spikes

if __name__ == "__main__":
    print("=" * 70); print("§1.1 results analysis — Work 1: variance partition"); print("=" * 70)
    work1_variance.main()
    print("=" * 70); print("§1.1 results analysis — Work 2: whitening efficacy"); print("=" * 70)
    work2_whitening.main()
    print("=" * 70); print("§1.1 results analysis — Work 3: spike sanity check"); print("=" * 70)
    work3_spikes.main()
    print("=" * 70); print("DONE — 6 figures + 3 tables + 7 plot-data bundles"); print("=" * 70)
