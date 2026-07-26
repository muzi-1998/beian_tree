"""run_stage_a.py — resumable full-period Stage-A driver.

Loads the full ~255-day dataset, computes residuals + upstream proxies, then runs
the expensive Stage-A detector pass ONE PAIR AT A TIME, checkpointing each pair's
raw table to artifacts/d6/stage_a/<pair>.pkl. Safe to re-run: completed pairs are
skipped. On completion, concatenates to artifacts/d6/stage_a_raw_full.pkl and
saves the upstream tables.
"""
from __future__ import annotations
import os, sys, time
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from d6.config.loader import load_d6_config
from d6.pair_manager import PairManager
from d6.pipeline import data_loader as DL
from d6.pipeline.d6_pipeline import D6Pipeline

ROOT = os.path.dirname(os.path.abspath(__file__))
RAWDIR = "/mnt/project"
ART = os.path.join(ROOT, "artifacts", "d6")
SA = os.path.join(ART, "stage_a")
os.makedirs(SA, exist_ok=True)


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


class _One:
    def __init__(self, pc): self.pc = pc
    def iter_all(self): return iter([self.pc])


def main():
    t0 = time.time()
    cfg = load_d6_config(os.path.join(ROOT, "configs", "d6"))
    pm = PairManager(cfg)

    if os.path.exists(os.path.join(ART, "residuals_full.pkl")) and \
       os.path.exists(os.path.join(ART, "upstream.pkl")):
        resid = pd.read_pickle(os.path.join(ART, "residuals_full.pkl"))
        up = pd.read_pickle(os.path.join(ART, "upstream.pkl"))
        d1, d2, regime, d7 = up["d1"], up["d2"], up["regime"], up["d7"]
        df_idx = up["index"]
        log("loaded cached residuals_full %s" % (resid.shape,))
    else:
        df = DL.load_raw(f"{RAWDIR}/beian_min_1_DO_25082604.xlsx",
                         f"{RAWDIR}/beian_min_2_ORP082604.xlsx",
                         f"{RAWDIR}/beian_min_3_QRQIR082604.xlsx", nrows_minutes=None)
        log("raw %s span %s..%s" % (df.shape, df.index.min(), df.index.max()))
        resid = DL.compute_residuals(df, DL.DO_COLS + DL.ORP_COLS)
        resid.to_pickle(os.path.join(ART, "residuals_full.pkl"))
        d1 = DL.derive_d1_proxy(df, resid, DL.DO_COLS + DL.ORP_COLS)
        d2 = DL.derive_d2_usability(df, DL.DO_COLS + DL.ORP_COLS)
        regime = DL.derive_regime(df)
        d7 = DL.derive_d7_consensus(resid, cfg.pairs, cfg.zoning)
        df_idx = pd.DatetimeIndex([df.index.min(), df.index.max()])
        pd.to_pickle({"d1": d1, "d2": d2, "regime": regime, "d7": d7, "index": df_idx},
                     os.path.join(ART, "upstream.pkl"))
        log("residuals %s + upstream cached" % (resid.shape,))

    end_times = pd.date_range(df_idx[0] + pd.Timedelta(hours=24), df_idx[-1], freq="1h")
    log("windows/pair=%d total~%d" % (len(end_times), len(end_times) * len(cfg.pairs)))

    pipe = D6Pipeline(cfg, pm, d1, d2, regime, d7, trend_mad=None)
    for pc in pm.iter_all():
        ckpt = os.path.join(SA, f"{pc.pair_id}.pkl")
        if os.path.exists(ckpt):
            log("skip %s (cached)" % pc.pair_id); continue
        tp = time.time()
        sub_resid = resid[[pc.target, pc.ref]]
        pipe.pair_mgr = _One(pc)
        raw = pipe.compute_raw(sub_resid, end_times)
        raw.to_pickle(ckpt)
        log("pair %s -> %d rows in %ds" % (pc.pair_id, len(raw), time.time() - tp))
    pipe.pair_mgr = pm

    parts = [pd.read_pickle(os.path.join(SA, f"{pc.pair_id}.pkl")) for pc in pm.iter_all()]
    full = pd.concat(parts, ignore_index=True)
    full.to_pickle(os.path.join(ART, "stage_a_raw_full.pkl"))
    log("STAGE-A FULL DONE %s in %.1fs; deadband rate=%.3f" %
        (full.shape, time.time() - t0, full["deadband_active"].mean()))


if __name__ == "__main__":
    main()
